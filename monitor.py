import random
import sqlite3
from datetime import datetime

# Connect to EcoPulse database
conn = sqlite3.connect("ecopulse.py")
cursor = conn.cursor()

# Ensure table exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS consumption (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    appliance TEXT NOT NULL,
    usage_kwh REAL NOT NULL
)
""")

# Example appliances
appliances = ["Refrigerator", "TV", "Air Conditioner", "Lighting", "Washing Machine"]

def simulate_reading():
    # Pick random appliance
    appliance = random.choice(appliances)
    # Generate random usage between 0.5 and 5 kWh
    usage = round(random.uniform(0.5, 5.0), 2)
    # Current timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return timestamp, appliance, usage

# Simulate 10 readings
for _ in range(10):
    ts, app, val = simulate_reading()
    cursor.execute("INSERT INTO consumption (timestamp, appliance, usage_kwh) VALUES (?, ?, ?)",
                   (ts, app, val))
    print(f"Logged: {app} used {val} kWh at {ts}")

conn.commit()
conn.close()
