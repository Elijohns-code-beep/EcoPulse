import sqlite3
from datetime import datetime

# Connect to (or create) EcoPulse database
conn = sqlite3.connect("ecopulse.py")
cursor = conn.cursor()

# Create table if not exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS consumption (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    appliance TEXT NOT NULL,
    usage_kwh REAL NOT NULL
)
""")

# Example data entry (replace with sensor input)
appliance_name = "Refrigerator"
usage_value = 2.5  # kWh
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Insert record
cursor.execute("INSERT INTO consumption (timestamp, appliance, usage_kwh) VALUES (?, ?, ?)",
               (timestamp, appliance_name, usage_value))

conn.commit()
print("Data logged successfully!")

# Query example: total usage today
cursor.execute("""
SELECT SUM(usage_kwh) 
FROM consumption 
WHERE date(timestamp) = date('now')
""")
total_today = cursor.fetchone()[0]
print(f"Total consumption today: {total_today} kWh")

conn.close()
