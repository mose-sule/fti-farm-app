#!/usr/bin/env python3
"""Initialize the FTI database from the authoritative schema.sql."""

import os
import sqlite3
import sys

DATABASE = "farm.db"


def init_database():
    if not os.path.isfile("schema.sql"):
        print("Error: schema.sql not found.")
        sys.exit(1)

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
