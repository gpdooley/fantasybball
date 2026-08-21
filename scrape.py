import json
import asyncio
import re
from playwright.async_api import async_playwright

# Positional tokens to recognize
VALID_POSITIONS = ["PG", "SG", "SF", "PF", "C"]

def extract_positions(text_content):
    """
    Extracts all valid positions (PG, SG, SF, PF, C) from a raw string.
    Preserves order and handles multi-eligibility (e.g., PG/SG).
    """
    if not text_content:
        return ""
    
    # Standardize delimiters
    clean_text = text_content.upper().replace("-", " ").replace("/", " ").replace(",", " ")
    tokens = clean_text.split()
    
    found_positions = []
    for token in tokens:
        if token in VALID_POSITIONS and token not in found_positions:
            found_positions.append(token)
            
    return "/".join(found_positions) if found_positions else ""

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

        # 1. Ensure page is loaded
        await page.wait_for_selector("table", timeout=15000)

        # 2. Configure Form Controls if available
        try:
            value_dropdown = page.locator("select[id*='ValueType']").first
            if await value_dropdown.count() > 0:
                await value_dropdown.select_option(label="Value")

            filter_btn = page.locator("input[type='submit'][value*='Filter'], button:has-text('Filter')").first
            if await filter_btn.count() > 0:
                await filter_btn.click()
                await page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"Form configuration note: {e}")

        # 3. Locate Target Data Table
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

        # Map header columns dynamically to verify position index
        header_pos_idx = None
        for r in rows:
            ths = await r.query_selector_all("th")
            if ths:
                for idx, th in enumerate(ths):
                    t_text = (await th.inner_text()).strip().upper()
                    if t_text == "POS" or t_text == "POSITION":
                        header_pos_idx = idx
                        break
            if header_pos_idx is not None:
                break

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
            if not name_elem:
                continue
            name = (await name_elem.inner_text()).strip()
            if not name or name.upper() in ["PLAYER", "NAME", "RANK"]:
                continue

            # --- DEDICATED POSITION RESOLUTION LOGIC ---
            pos = ""

            # Strategy A: Header Index Match
            if header_pos_idx is not None and header_pos_idx < len(cell_texts):
                pos = extract_positions(cell_texts[header_pos_idx])

            # Strategy B: Cell inspection around player name cell
            if not pos:
                for idx, text in enumerate(cell_texts):
                    # Skip columns that contain full player names or team abbreviations like DEN/OKC
                    if name.upper() in text.upper():
                        continue
                    extracted = extract_positions(text)
                    if extracted:
                        pos = extracted
                        break

            # Strategy C: Check inner HTML for hidden spans/classes containing positions
            if not pos:
                row_html = await row.inner_html()
                # Find position occurrences wrapped in HTML tags
                html_matches = re.findall(r'>\s*(PG|SG|SF|PF|C)\s*<', row_html, re.IGNORECASE)
                if html_matches:
                    pos = "/".join(dict.fromkeys([m.upper() for m in html_matches]))

            # Fallback only if no valid positions were detected anywhere
            if not pos:
                pos = "Util"

            # Cost Extraction
            cost = 1.0
            for txt in cell_texts:
                if "$" in txt:
                    try:
                        cost = float(txt.replace("$", "").strip())
                        break
                    except ValueError:
                        pass

            # Numeric Floats Parser
            floats = []
            for txt in cell_texts:
                clean = txt.replace("$", "").replace("%", "").replace(",", "").strip()
                try:
                    floats.append(float(clean))
                except ValueError:
                    continue

            # Identify Games Played (GP)
            games = 82
            for f in floats:
                if f.is_integer() and 40 <= f <= 82:
                    games = int(f)
                    break

            # Stat V-Scores / Values
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

        print(f"Scraped {len(players)} players with position matching.")
        await browser.close()

        with open("data.json", "w") as f:
            json.dump(players, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run())
