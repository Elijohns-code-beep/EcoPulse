import sqlite3

def init_db():
    conn = sqlite3.connect("ecopulse.db")   # creates ecopulse.db file in your project folder
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS consumption (
        id INTEGER PRIMARY KEY,
        date TEXT,
        kwh REAL
    )
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("✅ consumption table created successfully")
