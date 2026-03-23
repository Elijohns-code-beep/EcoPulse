import sqlite3
import matplotlib.pyplot as plt
import pandas as pd

# Connect to EcoPulse database
conn = sqlite3.connect("ecopulse.py")

# Load data into a DataFrame
df = pd.read_sql_query("SELECT * FROM consumption", conn)

# Convert timestamp column to datetime
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Extract month name
df['month'] = df['timestamp'].dt.strftime('%B')

# Group by month and appliance
monthly_summary = df.groupby(['month', 'appliance'])['usage_kwh'].sum().reset_index()

# Pivot for plotting (appliances as columns)
pivot_table = monthly_summary.pivot(index='month', columns='appliance', values='usage_kwh').fillna(0)

# Plot bar chart
pivot_table.plot(kind='bar', stacked=True, figsize=(10,6))

plt.title("EcoPulse Monthly Energy Consumption by Appliance")
plt.xlabel("Month")
plt.ylabel("Total Usage (kWh)")
plt.legend(title="Appliance")
plt.tight_layout()

# Save chart as image
plt.savefig("monthly_summary.png")
plt.show()

conn.close()
