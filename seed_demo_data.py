"""
FoodieSafe - optional demo data seeder.

This script is NOT run automatically. It exists only so that a student or
teacher can quickly demonstrate the prediction feature on a fresh install
without typing two weeks of records by hand.

The data it inserts is clearly sample data, generated from a simple, readable
pattern (weekends busier, each item with its own popularity). It is written
into the normal daily_records table, exactly as if the manager had typed it,
so every screen and the ML model treat it as real history.

Usage:
    python seed_demo_data.py            # insert 14 days of sample history
    python seed_demo_data.py --reset    # wipe existing records first

Do not run this on a database that already holds real canteen records.
"""

import argparse
import math
import random
from datetime import date, timedelta

from database import database as db

# Rough "popularity" of each item, used to shape the sample quantities.
POPULARITY = {
    "Maggi": 1.15,
    "Chole Bhature": 1.00,
    "Matra Kulcha": 0.85,
    "Veg Roll": 0.95,
    "Egg Roll": 0.80,
    "Paneer Roll": 0.70,
    "Cold Drink": 1.30,
    "Big Cold Drink": 0.75,
    "Haldiram Chips": 0.65,
    "TakaTak": 0.60,
}


def seed(days=14, reset=False):
    db.init_db()
    conn = db._connect()
    try:
        if reset:
            conn.execute("DELETE FROM daily_records")
            conn.execute("DELETE FROM predictions")
            conn.execute("DELETE FROM menu")

        items = conn.execute(
            "SELECT id, name FROM food_items ORDER BY id"
        ).fetchall()

        rng = random.Random(42)
        today = date.today()
        inserted = 0

        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            # Weekends are busier; Monday is quieter.
            weekend_boost = 1.25 if day.weekday() >= 5 else 1.0
            monday_dip = 0.85 if day.weekday() == 0 else 1.0
            # A gentle upward trend over the two weeks.
            trend = 1.0 + (days - offset) * 0.01
            # A slow weekly wave so the trend feature has something to learn.
            wave = 1.0 + 0.08 * math.sin((days - offset) / 7.0 * 2 * math.pi)

            for item in items:
                base = 30 * POPULARITY.get(item["name"], 1.0)
                demand = base * weekend_boost * monday_dip * trend * wave
                demand *= rng.uniform(0.9, 1.1)
                sold = max(0, int(round(demand)))
                # The manager prepares a little more than expected.
                prepared = sold + rng.randint(1, 6)
                wasted = prepared - sold
                conn.execute(
                    """INSERT INTO daily_records
                           (date, food_item_id, prepared, sold, wasted)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT (date, food_item_id)
                       DO UPDATE SET prepared = excluded.prepared,
                                     sold = excluded.sold,
                                     wasted = excluded.wasted""",
                    (day.isoformat(), item["id"], prepared, sold, wasted),
                )
                inserted += 1
        conn.commit()
        print(f"Inserted/updated {inserted} sample daily records "
              f"across {days} days.")
        print("Start the app with:  python app.py  and open "
              "http://127.0.0.1:5000")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed FoodieSafe demo data.")
    parser.add_argument("--days", type=int, default=14,
                        help="how many days of history to create (default 14)")
    parser.add_argument("--reset", action="store_true",
                        help="delete existing records first")
    args = parser.parse_args()
    seed(days=args.days, reset=args.reset)
