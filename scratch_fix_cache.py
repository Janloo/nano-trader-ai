import sqlite3
import os

db_path = 'data/backtest_cache.db'
if not os.path.exists(db_path):
    print("DB NOT FOUND")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Update the first chunk start date
cursor.execute("UPDATE bars_cache SET start_date='2026-07-04T00:00:00+00:00' WHERE start_date LIKE '2026-07-04%'")
print(f"Updated {cursor.rowcount} chunks for 07-04")

# Update the second chunk start date
cursor.execute("UPDATE bars_cache SET start_date='2026-08-01T00:00:00+00:00' WHERE start_date LIKE '2026-08-01%'")
print(f"Updated {cursor.rowcount} chunks for 08-01")

# Update the end date for all chunks that have an end date matching today
cursor.execute("UPDATE bars_cache SET end_date='2026-08-03T00:00:00+00:00' WHERE end_date LIKE '2026-08-03%'")
print(f"Updated {cursor.rowcount} chunks for end date 08-03")

conn.commit()
conn.close()
print("Done.")
