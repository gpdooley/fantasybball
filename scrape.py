import json
import asyncio
from playwright.async_api import async_playwright

# Known position map as a fallback for high-profile players if DOM fails
KNOWN_POSITIONS = {
    "Nikola Jokic": "C",
    "Victor Wembanyama": "C",
    "Shai Gilgeous-Alexander": "PG",
    "Kawhi Leonard": "SF/PF",
    "Tyrese Maxey": "PG/SG",
    "Luka Doncic": "PG",
    "Donovan Mitchell": "SG",
    "Giannis Antetokounmpo": "PF/C",
    "Anthony Davis": "PF/C",
    "Jayson Tatum": "SF/PF",
    "Stephen Curry": "PG",
    "Kevin Durant": "SF/PF",
    "Devin Booker": "PG/SG",
    "Anthony Edwards": "SG/SF",
    "Domantas Sabonis": "PF/C",
    "Trae Young": "PG",
    "Damian Lillard": "PG",
    "James Harden": "PG/SG",
    "Kyrie Irving": "PG/SG",
    "Jalen Brunson": "PG",
    "De'Aaron Fox": "PG",
    "Tyrese Haliburton": "PG",
    "Bam Adebayo": "C",
    "Karl-Anthony Towns": "PF/C",
    "Chet Holmgren": "PF/C",
    "Pascal Siakam": "PF",
    "LaMelo Ball": "PG",
    "Cade Cunningham": "PG/SG",
    "Evan Mobley": "PF/C",
    "Alperen Sengun": "C"
}

VALID_POS = {"PG", "SG", "SF", "PF", "C"}

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
        await page.wait_for_selector("table", timeout=15000)

        # 1. Switch display settings to 'Value' Mode if controls exist
        try:
            val_dropdown = page.locator("select[id*='ValueType']").first
            if await val_dropdown.count() > 0:
                await val_dropdown.select_option(label="Value")

            btn = page.locator("input[type='submit'][value*='Filter'], button:has-text('Filter')").first
            if await btn.count() > 0:
                await btn.click()
                await page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"Filter interaction note: {e}")

        # 2. Locate Main Table
        tables = await page.query_selector_all("table")
        target_table = None
        for t in tables:
            txt = await t.inner_text()
            if "Rank" in txt and "Player" in txt or "Name" in txt:
                target_table = t
                break

        if not target_table:
            print("Table not found.")
            await browser.close()
            return

        rows = await target_table.query_selector_all("tr")

        # 3. Dynamic Header Location
        header_indices = {}
        for r in rows:
            headers = await r.query_selector_all("th, td")
            if len(headers) < 5:
                continue
            
            h_texts = [(await h.inner_text()).strip().upper() for h in headers]
            if "NAME" in h_texts or "PLAYER" in h_texts:
                for idx, text in enumerate(h_texts):
                    if text in ["NAME", "PLAYER"]:
                        header_indices["name"] = idx
                    elif text in ["POS", "POSITION"]:
                        header_indices["pos"] = idx
                    elif text in ["TEAM", "TEAMS"]:
                        header_indices["team"] = idx
                    elif text in ["$","COST","PRICE"]:
                        header_indices["cost"] = idx
                    elif text in ["G","GP"]:
                        header_indices["gp"] = idx
                    elif text in ["VALUE","TOT","TOTAL"]:
                        header_indices["total_v"] = idx
                break

        print("Header mapping results:", header_indices)

        players = []

        # 4. Extract Row Information
        for row in rows:
            cols = await row.query_selector_all("td")
            if not cols or len(cols) < 8:
                continue

            cell_texts = [(await c.inner_text()).strip() for c in cols]
            row_text = " ".join(cell_texts).upper()

            if "PLAYER" in row_text or "RANK" in row_text or "TEAMS" in row_text:
                continue

            # --- NAME ---
            name_elem = await row.query_selector("a")
            name = (await name_elem.inner_text()).strip() if name_elem else ""
            if not name and "name" in header_indices and header_indices["name"] < len(cell_texts):
                name = cell_texts[header_indices["name"]]

            if not name or name.upper() in ["PLAYER", "NAME", "RANK"]:
                continue

            # --- POSITION RESOLUTION ---
            pos = ""

            # Check dynamic header column
            if "pos" in header_indices and header_indices["pos"] < len(cell_texts):
                raw_p = cell_texts[header_indices["pos"]].upper()
                pos_list = [p for p in raw_p.replace("-", "/").replace(" ", "/").split("/") if p in VALID_POS]
                if pos_list:
                    pos = "/".join(pos_list)

            # Check inner HTML tags for pos badges
            if not pos:
                row_html = await row.inner_html()
                for p_code in ["PG", "SG", "SF", "PF", "C"]:
                    if f">{p_code}<" in row_html or f"/{p_code}" in row_html or f"{p_code}/" in row_html:
                        pos = p_code
                        break

            # Check known positions map
            if not pos or pos == "Util":
                pos = KNOWN_POSITIONS.get(name, "Util")

            # --- COST ---
            cost = 1.0
            if "cost" in header_indices and header_indices["cost"] < len(cell_texts):
                try:
                    cost = float(cell_texts[header_indices["cost"]].replace("$", "").strip())
                except ValueError:
                    pass

            if cost == 1.0:
                for t in cell_texts:
                    if "$" in t:
                        try:
                            cost = float(t.replace("$", "").strip())
                            break
                        except ValueError:
                            pass

            # --- GAMES PLAYED ---
            games = 82
            if "gp" in header_indices and header_indices["gp"] < len(cell_texts):
                try:
                    games = int(float(cell_texts[header_indices["gp"]]))
                except ValueError:
                    pass
            else:
                for t in cell_texts:
                    try:
                        v = float(t)
                        if v.is_integer() and 40 <= v <= 82:
                            games = int(v)
                            break
                    except ValueError:
                        pass

            # --- STAT Z-SCORES ---
            # Total Value is column 2 (Value) on Basketball Monster standard table
            total_v = 0.0
            try:
                total_v = float(cell_texts[2])
            except (IndexError, ValueError):
                pass

            # Gather all non-integer float values past the PPG/MPG basic stats
            floats = []
            for t in cell_texts:
                clean = t.replace("$", "").replace("%", "").strip()
                try:
                    floats.append(float(clean))
                except ValueError:
                    continue

            # Filter out Rank, GP, and large counting stat integers (e.g., PTS/MPG > 10)
            z_scores = [f for f in floats if not (f.is_integer() and 40 <= f <= 82) and abs(f) < 15.0]

            # Categorical z-scores fall in positions 2:11 of float row
            pts_v = z_scores[1] if len(z_scores) > 1 else 0.0
            m3_v  = z_scores[2] if len(z_scores) > 2 else 0.0
            reb_v = z_scores[3] if len(z_scores) > 3 else 0.0
            ast_v = z_scores[4] if len(z_scores) > 4 else 0.0
            stl_v = z_scores[5] if len(z_scores) > 5 else 0.0
            blk_v = z_scores[6] if len(z_scores) > 6 else 0.0
            fg_v  = z_scores[7] if len(z_scores) > 7 else 0.0
            ft_v  = z_scores[8] if len(z_scores) > 8 else 0.0
            to_v  = z_scores[9] if len(z_scores) > 9 else 0.0

            players.append({
                "Name": name,
                "Pos": pos,
                "Cost": max(1.0, cost),
                "G": games,
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

        print(f"Scraped {len(players)} players.")
        await browser.close()

        with open("data.json", "w") as f:
            json.dump(players, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run())
