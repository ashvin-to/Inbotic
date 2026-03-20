#!/usr/bin/env python3
"""
User management script for Inbotic
"""
import sys
from database import SessionLocal, User, create_tables

def list_users():
    """List all users in the database"""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            print("📭 No users found in database")
            print("💡 The database is empty - you can register the first user")
            return

        print(f"👥 Found {len(users)} users:")
        for user in users:
            print(f"   • {user.username} ({user.email}) - Created: {user.created_at.strftime('%Y-%m-%d %H:%M')}")
    finally:
        db.close()

def clear_database():
    """Clear all data from database (WARNING: This deletes everything)"""
    confirm = input("⚠️  This will delete ALL users and data. Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ Operation cancelled")
        return

    db = SessionLocal()
    try:
        # Delete all data
        db.query(User).delete()
        db.commit()
        print("✅ Database cleared successfully")
        print("💡 You can now register new users")
    except Exception as e:
        print(f"❌ Error clearing database: {e}")
        db.rollback()
    finally:
        db.close()

def create_first_user():
    """Create the first user interactively"""
    print("👤 Creating first user...")

    email = input("Enter email: ").strip()
    username = input("Enter username: ").strip()
    password = input("Enter password (min 6 chars): ").strip()

    if len(password) < 6:
        print("❌ Password must be at least 6 characters")
        return

    db = SessionLocal()
    try:
        # Check if user already exists
        existing = db.query(User).filter(
            (User.email == email) | (User.username == username)
        ).first()

        if existing:
            print(f"❌ User already exists: {existing.username}")
            return

        # Create new user
        from auth import get_password_hash
        hashed_password = get_password_hash(password)

        new_user = User(
            email=email,
            username=username,
            hashed_password=hashed_password
        )

        db.add(new_user)
        db.commit()
        print(f"✅ Created user: {username}")
        print("💡 You can now login at http://localhost:8000/login")

    except Exception as e:
        print(f"❌ Error creating user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python manage_users.py [list|clear|create]")
        print("  list   - Show all users")
        print("  clear  - Clear all data (WARNING: deletes everything)")
        print("  create - Create first user interactively")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        list_users()
    elif command == "clear":
        clear_database()
    elif command == "create":
        create_first_user()
    else:
        print("❌ Unknown command. Use: list, clear, or create")
