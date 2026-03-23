import tkinter as tk
from tkinter import messagebox
import sqlite3
import matplotlib.pyplot as plt

threshold = 500

def insert_reading(date, kwh):
    conn = sqlite3.connect("ecopulse.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO consumption (date, kwh) VALUES (?, ?)", (date, kwh))
    conn.commit()
    conn.close()

def check_alert(consumption):
    if consumption > threshold:
        messagebox.showwarning("EcoPulse Alert", f"Consumption {consumption} kWh exceeds threshold {threshold}!")
    else:
        messagebox.showinfo("EcoPulse Status", "Consumption is within safe limits.")

def plot_monthly():
    conn = sqlite3.connect("ecopulse.db")
    cursor = conn.cursor()
    cursor.execute("SELECT date, kwh FROM consumption")
    data = cursor.fetchall()
    conn.close()

    if not data:
        messagebox.showinfo("EcoPulse Chart", "No data available to plot.")
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

def run_ecopulse():
    date = entry_date.get()
    try:
        kwh = float(entry_kwh.get())
    except ValueError:
        messagebox.showerror("Input Error", "Please enter a valid number for kWh.")
        return

    insert_reading(date, kwh)
    check_alert(kwh)
    plot_monthly()

# GUI setup
root = tk.Tk()
root.title("EcoPulse Dashboard")

tk.Label(root, text="Enter Month:").pack()
entry_date = tk.Entry(root)
entry_date.pack()

tk.Label(root, text="Enter Consumption (kWh):").pack()
entry_kwh = tk.Entry(root)
entry_kwh.pack()

tk.Button(root, text="Run EcoPulse", command=run_ecopulse).pack()

root.mainloop()
