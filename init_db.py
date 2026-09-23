import sqlite3

connection = sqlite3.connect("farm.db")

cursor = connection.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS farms (
    farm_id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_name TEXT NOT NULL,
    location TEXT NOT NULL,
    total_area_acres REAL NOT NULL
)
""")

connection.commit()
connection.close()

print("🌱 Farm database initialized successfully!")
