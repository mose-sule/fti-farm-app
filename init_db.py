#!/usr/bin/env python3
"""Initialize the FTI database from the authoritative schema.sql."""

import os
import shutil
import time
import sqlite3
import sys

DATABASE = "farm.db"


def init_database():
    if not os.path.isfile("schema.sql"):
        print("Error: schema.sql not found.")
        sys.exit(1)

    if os.path.isfile(DATABASE) and os.path.getsize(DATABASE) > 0:
        if "--force" not in sys.argv:
            print("Refusing to run: farm.db already exists and this would ERASE it.")
            print("To really start over, run: python init_db.py --force")
            sys.exit(1)
        backup = DATABASE + ".before-reset-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(DATABASE, backup)
        print("Backup saved to " + backup)

    connection = sqlite3.connect(DATABASE)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with open("schema.sql", encoding="utf-8") as schema_file:
            connection.executescript(schema_file.read())
        connection.commit()
    except (OSError, sqlite3.Error) as error:
        connection.rollback()
        print(f"Database initialization failed: {error}")
        sys.exit(1)
    finally:
        connection.close()

    print("🌱 Farm database initialized successfully!")


if __name__ == "__main__":
    init_database()
