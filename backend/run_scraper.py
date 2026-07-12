import os
import sys
import pytz
from datetime import datetime

# Ensure the app module can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.scheduler import fetch_all_keywords_news
from app.database import SessionLocal
from app import models

if __name__ == "__main__":
    event_name = os.getenv("GITHUB_EVENT_NAME", "unknown")
    print(f"Triggered by GitHub Event: {event_name}")
    
    if event_name == "schedule":
        # Triggered by 15-minute cron. Check if any DB jobs match.
        db = SessionLocal()
        try:
            jobs = db.query(models.ScheduledJob).filter(models.ScheduledJob.paused == 0).all()
            tz = pytz.timezone("Asia/Taipei")
            now = datetime.now(tz)
            now_mins = now.hour * 60 + now.minute
            
            should_run = False
            for job in jobs:
                job_mins = job.hour * 60 + job.minute
                diff = (now_mins - job_mins) % 1440
                if diff < 15:
                    should_run = True
                    break
                    
            if not should_run:
                print(f"[{now}] No scheduled jobs match the current time. Skipping scrape cycle.")
                sys.exit(0)
        except Exception as e:
            print(f"Error checking schedule: {e}")
            sys.exit(1)
        finally:
            db.close()
            
    print("Starting scrape cycle via GitHub Actions...")
    fetch_all_keywords_news()
    print("Scrape cycle finished.")
