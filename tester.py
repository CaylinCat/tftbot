import requests
from bs4 import BeautifulSoup

def get_tft_data(summoner_name):
    url = f"https://lolchess.gg/profile/na/{summoner_name.replace(' ', '%20')}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    res = requests.get(url, headers=headers)
    
    if res.status_code != 200:
        print(f"Error: Failed to retrieve data for {summoner_name}")
        return

    soup = BeautifulSoup(res.text, 'html.parser')
    
    # Find all elements with the class 'labels'
    labels = soup.select('.labels')
    
    # If labels are found, print their contents
    if labels:
        for label in labels:
            print(label.text.strip())  # Print the text content of each label
    else:
        print("No 'labels' class found.")

# Replace 'set6god' with any summoner name
get_tft_data('dali-097')