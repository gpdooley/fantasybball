import json
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        print("Navigating to Basketball Monster...")
        await page.goto("https://basketballmonster.com/PlayerRankings.aspx", wait_until="networkidle", timeout=30000)

        # Wait for main table container
        await page.wait_for_selector("table", timeout=15000)

        # Attempt to configure settings for Yahoo Auction & Z-Scores if drop-downs exist
        try:
            # Check for value type select (e.g. Per Game, Total, Auction)
            value_select = await page.query_selector("select[id*='ValueType'], select[id*='Value']")
            if value_select:
                await value_select.select_option(index=0) # Value/Z-Score mode
            
            # Click Refresh/Filter button if present on page
            refresh_btn = await page.query_selector("input[type='submit'][value*='Filter'], input[type='submit'][value*='Refresh']")
            if refresh_btn:
                await refresh_btn.click()
                await page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"Option selection skipped or failed: {e}")

        # Locate table
        tables = await page.query_selector_all("table")
        target_table = None
        for t in tables:
            txt = await t.inner_text()
            if "Rank" in txt or "Player" in txt:
                target_table = t
                break

        if not target_table:
            print("Rankings table not found.")
            await browser.close()
            return

        # Parse Headers dynamically to map column indices exactly
        header_map = {}
        rows = await target_table.query_selector_all("tr")
        
        header_row = None
        for r in rows:
            ths = await r.query_selector_all("th")
            if len(ths) > 3:
                header_row = ths
                break
            tds = await r.query_selector_all("td")
            # If th wasn't used, check for a header row wrapped in td
            if len(tds) > 5 and "PLAYER" in (await tds[1].inner_text()).upper():
                header_row = tds
                break

        if header_row:
            for idx, cell in enumerate(header_row):
                header_text = (await cell.inner_text()).strip().upper().replace("\N{DEGREE SIGN}", "").replace("\n", " ")
                header_map[header_text] = idx

        print("Mapped Headers:", header_map)

        players = []

        for row in rows:
            cols = await row.query_selector_all("td")
            if not cols or len(cols) < 5:
                continue

            cell_texts = [(await c.inner_text()).strip() for c in cols]
            row_str = " ".join(cell_texts).upper()

            if "PLAYER" in row_str or "RANK" in row_str or "TEAMS" in row_str:
                continue

            # Player Name
            name_elem = await row.query_selector("a")
            name = (await name_elem.inner_text()).strip() if name_elem else cell_texts[1] if len(cell_texts) > 1 else ""

            if not name or name.upper() in ["PLAYER", "NAME", "RANK"]:
                continue

            # Position Extraction: Look for explicit position tags (PG, SG, SF, PF, C)
            pos = "Util"
            for txt in cell_texts:
                clean_p = txt.upper().replace(" ", "")
                if any(p in clean_p for p in ["PG", "SG", "SF", "PF", "C"]) and len(clean_p) <= 12 and not any(char.isdigit() for char in clean_p):
                    # Filter out team codes like LAC or OKC unless they contain a position
                    if clean_p not in ["OKC", "LAC", "CLE", "BOS", "PHI", "LAL", "GSW"]:
                        pos = txt
                        break

            # Cost Extraction
            cost = 1.0
            # Search for dollar amounts in cell texts
            for txt in cell_texts:
                if "$" in txt:
                    try:
                        cost = float(txt.replace("$", "").strip())
                        break
                    except ValueError:
                        pass

            # Safe numeric parser helper
            def get_col_val(possible_keys, default=0.0):
                for k in possible_keys:
                    for h_text, idx in header_map.items():
                        if k in h_text and idx < len(cell_texts):
                            try:
                                val_str = cell_texts[idx].replace("$", "").replace("%", "").strip()
                                return float(val_str)
                            except ValueError:
                                pass
                return default

            # Games Played
            games = int(get_col_val(["g", "gp", "games"], 82))

            # Stat V-Scores / Values
            total_v = get_col_val(["round", "value", "v", "tot"], 0.0)
            pts_v   = get_col_val(["pts"], 0.0)
            m3_v    = get_col_val(["3pt", "3p", "m3"], 0.0)
            reb_v   = get_col_val(["reb", "rebounds"], 0.0)
            ast_v   = get_col_val(["ast", "assists"], 0.0)
            stl_v   = get_col_val(["stl", "steals"], 0.0)
            blk_v   = get_col_val(["blk", "blocks"], 0.0)
            fg_v    = get_col_val(["fg%", "fg"], 0.0)
            ft_v    = get_col_val(["ft%", "ft"], 0.0)
            to_v    = get_col_val(["to", "turnovers"], 0.0)

            # Fallback for stats if header map failed
            if total_v == 0.0 and len(cell_texts) > 10:
                nums = []
                for t in cell_texts:
                    try:
                        nums.append(float(t.replace("$", "").replace("%", "").strip()))
                    except ValueError:
                        pass
                if len(nums) >= 10:
                    total_v = nums[0]
                    pts_v, m3_v, reb_v, ast_v, stl_v, blk_v, fg_v, ft_v, to_v = nums[1:10]

            players.append({
                "Name": name,
                "Pos": pos,
                "Cost": max(1.0, cost),
                "G": games if games > 0 else 82,
                "TotalV": total_v,
                "Stats": {
                    "pts_v": pts_v,
                    "m3_v": m3_v,
                    "reb_v": reb_v,
                    "ast_v": ast_v,
                    "stl_v": stl_v,
                    "blk_v": blk_v,
                    "fg_v": fg_v,
                    "ft_v": ft_v,
                    "to_v": to_v
                },
                "locked": False
            })

        print(f"Scraped {len(players)} players with header mapping.")

        await browser.close()

        with open("data.json", "w") as f:
            json.dump(players, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run())
