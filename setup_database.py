"""
setup_database.py
-----------------
Run this script to DROP and RECREATE all tables from sql_scripts/create_tables.sql
inside the PostgreSQL database configured in .env

Usage:
    python setup_database.py
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("POSTGRES_HOST", "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname":   os.getenv("POSTGRES_DB",   "billing_db"),
    "user":     os.getenv("POSTGRES_USER", "billing_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "billing_pass"),
}

SQL_SCRIPT_PATH = Path(__file__).parent / "sql_scripts" / "create_tables.sql"


def run_setup():
    print("=" * 60)
    print("  Billing Software — Database Setup")
    print("=" * 60)
    print(f"  Host    : {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"  Database: {DB_CONFIG['dbname']}")
    print(f"  User    : {DB_CONFIG['user']}")
    print("=" * 60)

    if not SQL_SCRIPT_PATH.exists():
        print(f"[ERROR] SQL script not found: {SQL_SCRIPT_PATH}")
        sys.exit(1)

    sql = SQL_SCRIPT_PATH.read_text(encoding="utf-8")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()

        print("\n[INFO] Connected to PostgreSQL successfully.")
        print("[INFO] Dropping existing schema ...")
        cursor.execute("DROP SCHEMA public CASCADE;")
        cursor.execute("CREATE SCHEMA public;")
        cursor.execute("GRANT ALL ON SCHEMA public TO PUBLIC;")
        print("[INFO] Schema dropped and recreated.")

        print("[INFO] Executing SQL script ...\n")

        cursor.execute(sql)

        print("[SUCCESS] All tables created successfully!")
        print("\nTables created:")
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        for (table,) in cursor.fetchall():
            print(f"  [OK] {table}")

        cursor.close()
        conn.close()
        print("\n[INFO] Database connection closed.")

    except psycopg2.OperationalError as e:
        print(f"\n[ERROR] Could not connect to PostgreSQL:\n  {e}")
        print("\nMake sure the Docker containers are running:")
        print("  docker-compose up -d")
        sys.exit(1)
    except psycopg2.Error as e:
        print(f"\n[ERROR] Failed to execute SQL script:\n  {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_setup()
