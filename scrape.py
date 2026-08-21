import json
import asyncio
import re
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        # Launch headless Chromium
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        print("Navigating to Basketball Monster...")
        try:
            await page.goto("https://basketballmonster.com/PlayerRankings.aspx", wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"Navigation warning/timeout: {e}. Attempting to parse DOM anyway...")

        # Wait for table container to populate
        try:
            await page.wait_for_selector("table", timeout=15000)
        except Exception:
            print("Table selector timeout. Page failed to render expected table structure.")
            await browser.close()
            return

        # Find the primary grid table
        tables = await page.query_selector_all("table")
        target_table = None
        
        # Identify the table containing rankings
        for t in tables:
            text = await t.inner_text()
            if "Rank" in text or "Value" in text or "Player" in text:
                target_table = t
                break

        if not target_table:
            print("Could not find rankings table.")
            await browser.close()
            return

        # Locate header row to build dynamic column indices
        headers = []
        header_elems = await target_table.query_selector_all("tr th")
        if not header_elems:
            # Fallback if headers use <td> instead of <th>
            first_row = await target_table.query_selector("tr")
            if first_row:
                header_elems = await first_row.query_selector_all("td")

        for idx, h in enumerate(header_elems):
            txt = (await h.inner_text()).strip().upper()
            headers.append((txt, idx))

        print("Detected headers:", [h[0] for h in headers])

        rows = await target_table.query_selector_all("tr")
        players = []

        for row in rows:
            cols = await row.query_selector_all("td")
            if not cols or len(cols) < 5:
                continue

            cell_texts = [(await c.inner_text()).strip() for c in cols]
            row_str = " ".join(cell_texts)

            # Skip header re-prints or total rows
            if "PLAYER" in row_str.upper() or "RANK" in row_str.upper():
                continue

            # Extract Player Name
            name = ""
            name_elem = await row.query_selector("a")
            if name_elem:
                name = (await name_elem.inner_text()).strip()

            if not name or len(name) < 2:
                # Fallback to column text if link is missing
                name = cell_texts[1] if len(cell_texts) > 1 else ""

            if not name or name.upper() in ["PLAYER", "NAME"]:
                continue

            # Position parsing
            pos = "Util"
            for txt in cell_texts:
                if any(p in txt for p in ["PG", "SG", "SF", "PF", "C"]) and len(txt) <= 10:
                    pos = txt
                    break

            # Cost parsing (look for explicit $ or numeric auction estimate)
            cost = 1.0
            for txt in cell_texts:
                if "$" in txt:
                    clean = txt.replace("$", "").strip()
                    try:
                        cost = float(clean)
                        break
                    except ValueError:
                        pass

            # Parse numeric stats safely
            num_vals = []
            for txt in cell_texts:
                clean = txt.replace("$", "").replace("%", "").strip()
                try:
                    num_vals.append(float(clean))
                except ValueError:
                    continue

            # Games played default
            games = 82
            for val in num_vals:
                if val.is_integer() and 1 <= val <= 82:
                    games = int(val)
                    break

            # Map category stats safely from numeric extractions
            # Basketball Monster layout: Total V, then 9-cat individual values
            total_v = num_vals[0] if len(num_vals) > 0 else 0.0

            cat_v = {
                "pts_v": num_vals[1] if len(num_vals) > 1 else 0.0,
                "m3_v":  num_vals[2] if len(num_vals) > 2 else 0.0,
                "reb_v": num_vals[3] if len(num_vals) > 3 else 0.0,
                "ast_v": num_vals[4] if len(num_vals) > 4 else 0.0,
                "stl_v": num_vals[5] if len(num_vals) > 5 else 0.0,
                "blk_v": num_vals[6] if len(num_vals) > 6 else 0.0,
                "fg_v":  num_vals[7] if len(num_vals) > 7 else 0.0,
                "ft_v":  num_vals[8] if len(num_vals) > 8 else 0.0,
                "to_v":  num_vals[9] if len(num_vals) > 9 else 0.0,
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

        print(f"Scraped {len(players)} players.")

        await browser.close()

        # Output payload
        with open("data.json", "w") as f:
            json.dump(players, f, indent=2)

if __name__ == "__main__":
    asyncio.run(run())
