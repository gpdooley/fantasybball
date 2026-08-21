import json
import requests
from bs4 import BeautifulSoup

def scrape_basketball_monster():
    url = "https://basketballmonster.com/PlayerRankings.aspx"
    
    # Realistic browser headers to prevent getting blocked
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
        
        # Try finding the rankings table by common Basketball Monster IDs/classes
        table = soup.find("table", {"id": "datatable"}) or soup.find("table", {"class": "grid"}) or soup.find("table")
        
        if not table:
            print("Could not locate player table in HTML output.")
            save_empty_json()
            return

        players = []
        rows = table.find_all("tr")

        for row in rows:
            cols = row.find_all(["td", "th"])
            if len(cols) < 5:
                continue

            try:
                # Column parsing with fallback defaults
                name_elem = cols[1].find("a") or cols[1]
                name = name_elem.text.strip()
                pos = cols[2].text.strip()
                
                cost_text = cols[3].text.strip().replace("$", "")
                cost = float(cost_text) if cost_text and cost_text.replace('.', '', 1).isdigit() else 1.0
                
                games_text = cols[4].text.strip()
                games = int(games_text) if games_text.isdigit() else 82

                total_v_text = cols[5].text.strip()
                total_v = float(total_v_text) if total_v_text and not total_v_text.isalpha() else 0.0

                # Skip header rows and zero-cost entries
                if name.lower() not in ["player", "name"] and cost > 0:
                    players.append({
                        "Name": name,
                        "Pos": pos,
                        "Cost": cost,
                        "G": games,
                        "TotalV": total_v,
                        "locked": False
                    })
            except Exception as row_err:
                continue

        print(f"Successfully scraped {len(players)} players.")
        
        with open("data.json", "w") as f:
            json.dump(players, f, indent=2)

    except Exception as e:
        print(f"An error occurred during scraping: {e}")
        save_empty_json()

def save_empty_json():
    """Ensures data.json always exists so Git doesn't throw pathspec error."""
    with open("data.json", "w") as f:
        json.dump([], f)
    print("Created fallback empty data.json")

if __name__ == "__main__":
    scrape_basketball_monster()
