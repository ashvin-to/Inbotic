#!/usr/bin/env python3
"""
Migration: Add due_time column to tasks table
This stores the extracted time (HH:MM:SS format) from email deadlines
"""

import sqlite3
from pathlib import Path

def migrate():
    db_path = Path(__file__).parent.parent / "inbox_agent.db"
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'due_time' in columns:
            print("Column 'due_time' already exists in tasks table")
            conn.close()
            return True
        
        # Add the column
        print("Adding 'due_time' column to tasks table...")
        cursor.execute("ALTER TABLE tasks ADD COLUMN due_time VARCHAR(20) DEFAULT NULL")
        conn.commit()
        
        # Verify
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'due_time' in columns:
            print("✓ Successfully added 'due_time' column")
            print(f"  Updated columns: {columns}")
            conn.close()
            return True
        else:
            print("✗ Failed to add column")
            conn.close()
            return False
            
    except Exception as e:
        print(f"✗ Error during migration: {e}")
        return False

if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
