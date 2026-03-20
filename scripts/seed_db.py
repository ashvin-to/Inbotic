#!/usr/bin/env python3
"""
Seed or reset the Inbotic database.

Usage:
  - Run directly to drop and recreate tables, then seed default users from env.
  - Controlled by environment variables (see below).

Environment variables:
  RESET_DB: "true" to drop and recreate tables (default: true when running this script)
  USERS_SEED: JSON array of objects with email, username, password
      e.g. USERS_SEED='[{"email":"a@b.com","username":"alice","password":"pass123"}]'
  DEFAULT_USER_EMAIL, DEFAULT_USER_USERNAME, DEFAULT_USER_PASSWORD: used if USERS_SEED is not provided
  DATABASE_URL: points to SQLite file or other DB (loaded via database.py)
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import List, Dict

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from database import Base, engine, create_tables, SessionLocal, User
from auth import get_password_hash


def parse_users_seed() -> List[Dict[str, str]]:
    raw = os.getenv("USERS_SEED")
    if raw:
        try:
            data = json.loads(raw)
            assert isinstance(data, list)
            return data
        except Exception:
            print("❌ USERS_SEED is not valid JSON; ignoring")
    # Fallback to single default user
    email = os.getenv("ADMIN_EMAIL")
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    if email and username and password:
        return [{"email": email, "username": username, "password": password}]
    # Final fallback: a dev test user
    return [{
        "email": "dev@example.com",
        "username": "devuser",
        "password": "devpass123"
    }]


def reset_db():
    print("🗑️  Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("🧱 Recreating tables...")
    create_tables()
    print("✅ Database schema reset complete")


def seed_users(users: List[Dict[str, str]]):
    db = SessionLocal()
    try:
        created = 0
        for u in users:
            email = u.get("email", "").strip()
            username = u.get("username", "").strip()
            password = u.get("password", "").strip()
            if not (email and username and password):
                print(f"⚠️  Skipping invalid user seed: {u}")
                continue
            exists = db.query(User).filter((User.email == email) | (User.username == username)).first()
            if exists:
                print(f"ℹ️  User exists, skipping: {username} ({email})")
                continue
            hashed = get_password_hash(password)
            db.add(User(email=email, username=username, hashed_password=hashed))
            created += 1
        db.commit()
        print(f"✅ Seeded {created} new user(s)")
    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding users: {e}")
        raise
    finally:
        db.close()


def main():
    # When invoked directly, always reset unless RESET_DB explicitly set false
    reset = os.getenv("RESET_DB", "true").lower() == "true"
    if reset:
        reset_db()
    users = parse_users_seed()
    seed_users(users)
    print("🎉 Seeding complete")


if __name__ == "__main__":
    main()
