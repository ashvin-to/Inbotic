# Scripts

This folder contains maintenance and one-off utilities that are not part of normal app runtime.

## Available scripts

- `check_db.py` - quick local database status check
- `migrate_db.py` - adds `profile_photo` column to users table (legacy migration)
- `migrate_chat_history.py` - creates `chat_history` table (legacy migration)
- `migrate_reset_token.py` - adds password reset columns (legacy migration)
- `seed_db.py` - reset and seed users from environment variables

## Usage

Run scripts from the repository root:

```bash
python scripts/check_db.py
python scripts/migrate_db.py
python scripts/migrate_chat_history.py
python scripts/migrate_reset_token.py
python scripts/seed_db.py
```

These scripts are kept for development and maintenance workflows.
