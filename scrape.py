import json
import asyncio
from playwright.async_api import async_playwright

VALID_POSITIONS = {"PG", "SG", "SF", "PF", "C"}

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

        await page.wait_for_selector("table", timeout=15000)

        # 1. Attempt to set display to 'Value'
        try:
            value_dropdown = page.locator("select[id*='ValueType']").first
            if await value_dropdown.count() > 0:
                await value_dropdown.select_option(label="Value")

            filter_btn = page.locator("input[type='submit'][value*='Filter'], button:has-text('Filter')").first
            if await filter_btn.count() > 0:
                await filter_btn.click()
                await page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"Form interaction note: {e}")

        # 2. Find the main rankings table
        tables = await page.query_selector_all("table")
        target_table = None
        for t in tables:
            txt = await t.inner_text()
            if "Rank" in txt or "Player" in txt or "Name" in txt:
                target_table = t
                break

        if not target_table:
            print("Rankings table not found.")
            await browser.close()
            return

        rows = await target_table.query_selector_all("tr")

        # 3. Dynamically map exact column header positions
        col_indices = {
            "name": None,
            "pos": None,
            "team": None,
            "cost": None,
            "gp": None
        }

        for r in rows:
            cells = await r.query_selector_all("th, td")
            if len(cells) < 4:
                continue

            cell_texts = [(await c.inner_text()).strip().upper() for c in cells]
            
            if "NAME" in cell_texts or "PLAYER" in cell_texts or "POS" in cell_texts:
                for idx, text in enumerate(cell_texts):
                    if text in ["NAME", "PLAYER"]:
                        col_indices["name"] = idx
                    elif text in ["POS", "POSITION"]:
                        col_indices["pos"] = idx
                    elif text in ["TEAM", "TEAMS"]:
                        col_indices["team"] = idx
                    elif text in ["COST", "$", "PRICE"]:
                        col_indices["cost"] = idx
                    elif text in ["G", "GP", "GAMES"]:
                        col_indices["gp"] = idx
                break

        print("Mapped Column Header Indices:", col_indices)

        players = []

        # 4. Extract Row Data using Index Map
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
            name = (await name_elem.inner_text()).strip() if name_elem else ""
            
            if not name and col_indices["name"] is not None and col_indices["name"] < len(cell_texts):
                name = cell_texts[col_indices["name"]]

            if not name or name.upper() in ["PLAYER", "NAME", "RANK"]:
                continue

            # --- POSITION EXTRACTION ---
            pos = ""
            
            # Direct index lookup if POS column header was found
            if col_indices["pos"] is not None and col_indices["pos"] < len(cell_texts):
                raw_pos = cell_texts[col_indices["pos"]].strip()
                # Split multi-positions (e.g., PG/SG)
                pos_parts = [p.strip().upper() for p in raw_pos.replace("-", "/").replace(",", "/").split("/") if p.strip().upper() in VALID_POSITIONS]
                if pos_parts:
                    pos = "/".join(pos_parts)

            # Fallback: Scan cells specifically for position tokens while ignoring Team codes
            if not pos:
                for idx, txt in enumerate(cell_texts):
                    # Skip the player name cell and team cell index
                    if idx == col_indices["name"] or idx == col_indices["team"]:
                        continue
                    
                    tokens = [t.strip().upper() for t in txt.replace("/", " ").replace("-", " ").split()]
                    matched = [t for t in tokens if t in VALID_POSITIONS]
                    if matched:
                        pos = "/".join(dict.fromkeys(matched))
                        break

            if not pos:
                pos = "Util"

            # --- COST EXTRACTION ---
            cost = 1.0
            if col_indices["cost"] is not None and col_indices["cost"] < len(cell_texts):
                try:
                    cost = float(cell_texts[col_indices["cost"]].replace("$", "").strip())
                except ValueError:
                    pass

            if cost == 1.0:
                for txt in cell_texts:
                    if "$" in txt:
                        try:
                            cost = float(txt.replace("$", "").strip())
                            break
                        except ValueError:
                            pass

            # --- NUMERIC VALUES & STATS ---
            floats = []
            for txt in cell_texts:
                clean = txt.replace("$", "").replace("%", "").replace(",", "").strip()
                try:
                    floats.append(float(clean))
                except ValueError:
                    continue

            # Games Played
            games = 82
            if col_indices["gp"] is not None and col_indices["gp"] < len(cell_texts):
                try:
                    games = int(float(cell_texts[col_indices["gp"]]))
                except ValueError:
                    pass
            else:
                for f in floats:
                    if f.is_integer() and 40 <= f <= 82:
                        games = int(f)
                        break

            # Stat V-Scores
            stat_floats = [f for f in floats if not (f.is_integer() and 40 <= f <= 82)]
            total_v = stat_floats[0] if len(stat_floats) > 0 else 0.0

            cat_v = {
                "pts_v": stat_floats[1] if len(stat_floats) > 1 else 0.0,
                "m3_v":  stat_floats[2] if len(stat_floats) > 2 else 0.0,
                "reb_v": stat_floats[3] if len(stat_floats) > 3 else 0.0,
                "ast_v": stat_floats[4] if len(stat_floats) > 4 else 0.0,
                "stl_v": stat_floats[5] if len(stat_floats) > 5 else 0.0,
                "blk_v": stat_floats[6] if len(stat_floats) > 6 else 0.0,
                "fg_v":  stat_floats[7] if len(stat_floats) > 7 else 0.0,
                "ft_v":  stat_floats[8] if len(stat_floats) > 8 else 0.0,
                "to_v":  stat_floats[9] if len(stat_floats) > 9 else 0.0,
            }

            players.append({
                "Name": name,
                "Pos": pos,
                "Cost": max(1.0, cost),
                "G": games,
                "TotalV": total_v,
                "Stats": cat_v,
                "locked": False
            })

        print(f"Scraped {len(players)} players with header-mapped position logic.")
        await browser.close()

        with open("data.json", "w") as f:
            json.dump(players, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run())
