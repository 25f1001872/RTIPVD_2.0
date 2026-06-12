import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.db_manager import DatabaseManager

def main():
    db = DatabaseManager()
    if db._conn is None:
        print("Database not connected or doesn't exist.")
        return

    cursor = db._conn.cursor()
    cursor.execute("DELETE FROM violations;")
    db._conn.commit()
    print("Dashboard database has been cleared.")

if __name__ == "__main__":
    main()
