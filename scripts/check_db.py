#!/usr/bin/env python3
"""
Quick database status checker
"""
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database import SessionLocal, User

def check_database_status():
    """Check database status and provide guidance"""
    db_file = "inbox_agent.db"

    if not os.path.exists(db_file):
        print("Database file not found")
        print("Run: python -c \"from database import create_tables; create_tables()\"")
        return

    # Check file size
    size = os.path.getsize(db_file)
    print(f"Database file: {db_file} ({size} bytes)")

    # Check users
    db = SessionLocal()
    try:
        users = db.query(User).all()
        print(f"Users in database: {len(users)}")

        if users:
            print("Existing users:")
            for user in users:
                print(f"• {user.username} ({user.email})")
            print("Try logging in with one of these credentials")
        else:
            print("No users found - database is empty")
            print("Run: python manage_users.py create")

    except Exception as e:
        print(f"Database error: {e}")
        print("Try: python manage_users.py clear")
    finally:
        db.close()

if __name__ == "__main__":
    check_database_status()
