import sqlite3
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./email_extractor.db")
DB_PATH = DATABASE_URL.replace("sqlite:///", "")

def migrate():
    print(f"Migrating database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "profile_photo" not in columns:
            print("Adding profile_photo column to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN profile_photo TEXT")
            conn.commit()
            print("Migration successful!")
        else:
            print("Column profile_photo already exists.")
            
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
