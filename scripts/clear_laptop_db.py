import sqlite3

try:
    conn = sqlite3.connect('output/db/rtipvd_laptop.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM violations;")
    conn.commit()
    conn.close()
    print("Dashboard database (rtipvd_laptop.db) has been successfully cleared.")
except Exception as e:
    print(f"Error clearing database: {e}")
