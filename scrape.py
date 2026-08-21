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

        print("Navigating to Basketball Monster Rankings...")
        await page.goto("https://basketballmonster.com/PlayerRankings.aspx", wait_until="networkidle", timeout=30000)

        # 1. Configure Basketball Monster Form Controls for Yahoo Auction & Z-Scores
        try:
            # Look for Value Type dropdown (Per Game / Value / Total)
            value_dropdown = page.locator("select[id*='ValueType']").first
            if await value_dropdown.count() > 0:
                await value_dropdown.select_option(label="Value") # Force Z-scores

            # Look for Provider/Auction source dropdown
            provider_dropdown = page.locator("select[id*='Source'], select[id*='Provider']").first
            if await provider_dropdown.count() > 0:
                # Attempt to select Yahoo if present
                try:
                    await provider_dropdown.select_option(label="Yahoo")
                except:
                    pass

            # Click the Filter / Refresh button to force grid reload
            filter_btn = page.locator("input[type='submit'][value*='Filter'], button:has-text('Filter')").first
            if await filter_btn.count() > 0:
                await filter_btn.click()
                await page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"Form configuration notice: {e}")

        # Wait for data table
        await page.wait_for_selector("table", timeout=15000)

        # Locate the main data grid
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

        rows = await target_table.query_selector_all("tr")
        players = []

        for row in rows:
            cols = await row.query_selector_all("td")
            if not cols or len(cols) < 8:
                continue

            # Extract cell text and anchor links
            cell_texts = [(await c.inner_text()).strip() for c in cols]
            row_str = " ".join(cell_texts).upper()

            if "PLAYER" in row_str or "RANK" in row_str or "TEAMS" in row_str:
                continue

            # 2. Extract Name & Positions cleanly from links and spans
            name_elem = await row.query_selector("a")
            if not name_elem:
                continue
            name = (await name_elem.inner_text()).strip()
            if not name or name.upper() in ["PLAYER", "NAME", "RANK"]:
                continue

            # Positions: BBM usually puts positions inside a specific span or adjacent cell
            pos = "Util"
            # Inspect row HTML for standard position patterns
            row_html = await row.inner_html()
            positions_found = []
            for p_code in ["PG", "SG", "SF", "PF", "C"]:
                # Match standalone position tags in HTML or text
                if f" {p_code} " in f" {row_str} " or f">{p_code}<" in row_html or f"/{p_code}" in row_html or f"{p_code}/" in row_html:
                    positions_found.append(p_code)
            
            if positions_found:
                # Preserve unique positions order
                pos = "/".join(dict.fromkeys(positions_found))

            # 3. Cost Extraction: Look explicitly for auction dollar values ($)
            cost = 1.0
            for txt in cell_texts:
                if "$" in txt:
                    clean = txt.replace("$", "").strip()
                    try:
                        cost_val = float(clean)
                        if cost_val > 0:
                            cost = cost_val
                            break
                    except ValueError:
                        pass

            # 4. Extract Z-Scores safely
            # Identify numeric values in row, ignoring Rank and GP
            floats = []
            for txt in cell_texts:
                clean = txt.replace("$", "").replace("%", "").replace(",", "").strip()
                try:
                    floats.append(float(clean))
                except ValueError:
                    continue

            # Filter out obvious Rank (1, 2, 3...) and GP (60-82) to get true stat values
            # BBM Stat columns in Value mode: TotalV, PTS, 3PT, REB, AST, STL, BLK, FG%, FT%, TO
            stat_floats = [f for f in floats if not (f.is_integer() and 1 <= f <= 82 and f == floats[0])]

            total_v = stat_floats[0] if len(stat_floats) > 0 else 0.0

            # Map category Z-Scores
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

            # Find Games Played
            games = 82
            for f in floats:
                if f.is_integer() and 40 <= f <= 82:
                    games = int(f)
                    break

            players.append({
                "Name": name,
                "Pos": pos,
                "Cost": max(1.0, cost),
                "G": games,
                "TotalV": total_v,
                "Stats": cat_v,
                "locked": False
            })

        print(f"Successfully scraped {len(players)} players.")

        await browser.close()

        with open("data.json", "w") as f:
            json.dump(players, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run())
