import json
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        # Launch headless browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Navigate to Basketball Monster Player Rankings
        print("Navigating to Basketball Monster...")
        await page.goto("https://basketballmonster.com/PlayerRankings.aspx", wait_until="networkidle")
        
        # Wait for the main datatable to load
        await page.wait_for_selector("#datatable", timeout=15000)
        
        # Extract rows
        rows = await page.query_selector_all("#datatable tr")
        players = []
        
        for row in rows:
            # Check if this is a header or filter row
            is_header = await row.query_selector("th")
            if is_header:
                continue

            cols = await row.query_selector_all("td")
            if len(cols) < 12:
                continue

            try:
                # Extract text contents across cells
                cell_texts = [await c.inner_text() for c in cols]
                
                # Player Name
                name_elem = await row.query_selector("a")
                if not name_elem:
                    continue
                name = (await name_elem.inner_text()).strip()
                if not name or name.lower() in ["player", "name"]:
                    continue

                # Position (usually col index 2 or 3)
                pos = cell_texts[2].strip() if len(cell_texts) > 2 else "Util"
                
                # Games Played
                g_text = cell_texts[3].strip() if len(cell_texts) > 3 else "82"
                games = int(g_text) if g_text.isdigit() else 82

                # Yahoo Auction Price (Y!Avg$)
                cost = 1.0
                for txt in cell_texts:
                    if "$" in txt:
                        try:
                            cost = float(txt.replace("$", "").strip())
                            break
                        except ValueError:
                            pass

                # Parse individual 9-cat _V stat scores
                # Basketball Monster typically orders them: TotalV, Value, PTS, 3PT, REB, AST, STL, BLK, FG%, FT%, TO
                # We map available numeric float cells:
                floats = []
                for txt in cell_texts:
                    clean_txt = txt.replace("$", "").strip()
                    try:
                        val = float(clean_txt)
                        floats.append(val)
                    except ValueError:
                        continue

                # Fallback assignment for stats if enough numeric columns exist
                total_v = floats[0] if len(floats) > 0 else 0.0
                
                # Category V-values
                cat_v = {
                    "pts_v": floats[1] if len(floats) > 1 else 0.0,
                    "m3_v":  floats[2] if len(floats) > 2 else 0.0,
                    "reb_v": floats[3] if len(floats) > 3 else 0.0,
                    "ast_v": floats[4] if len(floats) > 4 else 0.0,
                    "stl_v": floats[5] if len(floats) > 5 else 0.0,
                    "blk_v": floats[6] if len(floats) > 6 else 0.0,
                    "fg_v":  floats[7] if len(floats) > 7 else 0.0,
                    "ft_v":  floats[8] if len(floats) > 8 else 0.0,
                    "to_v":  floats[9] if len(floats) > 9 else 0.0,
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

            except Exception as e:
                continue

        print(f"Successfully scraped {len(players)} players with full category stats.")
        
        await browser.close()

        with open("data.json", "w") as f:
            json.dump(players, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run())
