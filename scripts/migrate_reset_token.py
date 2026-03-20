import sqlite3
import os

DATABASE_URL = os.getenv("DATABASE_URL", "email_extractor.db")
DB_FILE = DATABASE_URL.replace("sqlite:///", "").replace("./", "")

def migrate():
    print(f"Migrating database: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Add reset_token column
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
            print("Added reset_token column")
        except sqlite3.OperationalError:
            print("reset_token column already exists")
            
        # Add reset_token_expires column
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP")
            print("Added reset_token_expires column")
        except sqlite3.OperationalError:
            print("reset_token_expires column already exists")
            
        conn.commit()
        print("Migration completed successfully")
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
