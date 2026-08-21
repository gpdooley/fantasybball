import json
import requests
from bs4 import BeautifulSoup

def scrape_basketball_monster():
    # URL configured for 9-cat, Yahoo default settings, top players
    url = "https://basketballmonster.com/PlayerRankings.aspx"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"HTTP Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Failed to fetch page. Status code: {response.status_code}")
            save_empty_json()
            return

        soup = BeautifulSoup(response.text, "html.parser")
        
        # Locate main grid table
        table = soup.find("table", {"id": "datatable"}) or soup.find("table", {"class": "grid"}) or soup.find("table")
        
        if not table:
            print("Could not locate player table in HTML output.")
            save_empty_json()
            return

        players = []
        rows = table.find_all("tr")

        for row in rows:
            cols = row.find_all(["td", "th"])
            
            # Skip short or non-data rows
            if len(cols) < 6:
                continue

            # Skip header or control rows
            row_text = row.text.lower()
            if "rank" in row_text or "player" in row_text or "value" in row_text:
                continue

            try:
                # Find player link or text (BM puts player links in specific anchor tags)
                name_elem = row.find("a", href=lambda h: h and "player" in h.lower())
                if not name_elem:
                    continue
                name = name_elem.text.strip()

                # Search through column cells to find Position, Cost, Games, and Value
                cell_texts = [c.text.strip() for c in cols]

                # Position cell (contains PG, SG, SF, PF, C)
                pos = "Util"
                for text in cell_texts:
                    if any(p in text for p in ["PG", "SG", "SF", "PF", "C"]):
                        pos = text
                        break

                # Extract dollar cost (look for '$' or Yahoo auction price column)
                cost = 1.0
                for text in cell_texts:
                    if text.startswith("$"):
                        try:
                            cost = float(text.replace("$", "").strip())
                            break
                        except ValueError:
                            pass

                # Extract games played
                games = 82
                for text in cell_texts[3:8]:
                    if text.isdigit() and 1 <= int(text) <= 82:
                        games = int(text)
                        break

                # Extract overall total V value (usually a decimal like 8.42 or 0.75)
                total_v = 0.0
                for text in cell_texts[4:10]:
                    try:
                        val = float(text)
                        if -10.0 <= val <= 25.0:
                            total_v = val
                            break
                    except ValueError:
                        continue

                players.append({
                    "Name": name,
                    "Pos": pos,
                    "Cost": max(1.0, cost),
                    "G": games,
                    "TotalV": total_v,
                    "locked": False
                })

            except Exception:
                continue

        print(f"Successfully scraped {len(players)} players.")
        
        if len(players) > 0:
            with open("data.json", "w") as f:
                json.dump(players, f, indent=2)
        else:
            save_empty_json()

    except Exception as e:
        print(f"An error occurred during scraping: {e}")
        save_empty_json()

def save_empty_json():
    with open("data.json", "w") as f:
        json.dump([], f)
    print("Created fallback empty data.json")

if __name__ == "__main__":
    scrape_basketball_monster()
