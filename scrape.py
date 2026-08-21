import json
import requests
from bs4 import BeautifulSoup

def scrape_basketball_monster():
    url = "https://basketballmonster.com/PlayerRankings.aspx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to fetch page: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Locate the main player rankings table
    table = soup.find("table", {"id": "datatable"}) or soup.find("table", class_="grid")
    if not table:
        print("Could not find rankings table.")
        return

    players = []
    rows = table.find_all("tr")[1:]  # Skip header row

    for row in rows:
        cols = row.find_all(["td", "th"])
        if len(cols) < 5:
            continue

        try:
            # Note: Column indices correspond to standard Basketball Monster layout
            name = cols[1].text.strip()
            pos = cols[2].text.strip()
            cost_text = cols[3].text.strip().replace("$", "")
            cost = float(cost_text) if cost_text else 1.0
            
            games_text = cols[4].text.strip()
            games = int(games_text) if games_text.isdigit() else 82

            # Total value column (sum of V scores)
            total_v_text = cols[5].text.strip()
            total_v = float(total_v_text) if total_v_text else 0.0

            if cost > 0:
                players.append({
                    "Name": name,
                    "Pos": pos,
                    "Cost": cost,
                    "G": games,
                    "TotalV": total_v,
                    "locked": False
                })
        except Exception as e:
            continue

    # Save to data.json in repo root
    with open("data.json", "w") as f:
        json.dump(players, f, indent=2)

    print(f"Successfully saved {len(players)} players to data.json")

if __name__ == "__main__":
    scrape_basketball_monster()
