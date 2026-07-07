import os
import sys

# Ensure the app module can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.scheduler import fetch_all_keywords_news

if __name__ == "__main__":
    print("Starting manual scrape cycle via GitHub Actions...")
    fetch_all_keywords_news()
    print("Scrape cycle finished.")
