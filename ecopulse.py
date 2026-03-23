import sqlite3
import matplotlib.pyplot as plt

# -----------------------------
# Insert readings into table
# -----------------------------
def insert_reading(date, kwh):
    conn = sqlite3.connect("ecopulse.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO consumption (date, kwh) VALUES (?, ?)", (date, kwh))
    conn.commit()
    conn.close()

# -----------------------------
# Alert System (Simulation)
# -----------------------------
threshold = 500

def check_alert(consumption):
    if consumption > threshold:
        print("----- Simulated Alert -----")
        print(f"ALERT: Consumption reached {consumption} kWh (Threshold {threshold})")
        print("---------------------------")
    else:
        print("Consumption is within safe limits.")

# -----------------------------
# Visualization (Charts)
# -----------------------------
def plot_monthly():
    conn = sqlite3.connect("ecopulse.db")
    cursor = conn.cursor()
    cursor.execute("SELECT date, kwh FROM consumption")
    data = cursor.fetchall()
    conn.close()

    if not data:
        print("No data available to plot.")
        return

    dates = [d for d, _ in data]
    values = [v for _, v in data]

    plt.figure(figsize=(8, 5))
    plt.bar(dates, values, color="skyblue")
    plt.xlabel("Month")
    plt.ylabel("Consumption (kWh)")
    plt.title("EcoPulse Energy Consumption")
    plt.tight_layout()
    plt.show()

# -----------------------------
# Demo Run
# -----------------------------
if __name__ == "__main__":
    # Insert sample readings (these go into your consumption table)
    insert_reading("Jan", 450)
    insert_reading("Feb", 480)
    insert_reading("Mar", 520)

    # Check alert for March
    check_alert(520)

    # Show chart from table data
    plot_monthly()
