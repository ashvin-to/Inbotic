# Contributing to Inbotic

Thanks for your interest in contributing.

## Development setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install backend dependencies:

```bash
pip install -r requirements.txt
```

3. Create env file from template:

```bash
cp .env.example .env
```

4. Start backend app:

```bash
python start_web.py
```

5. (Optional) Start frontend in a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

## Pull request guidelines

- Keep changes focused and minimal
- Do not commit secrets, tokens, logs, local DB files, or dependency folders
- Update documentation when behavior or setup changes
- Keep code style consistent with the surrounding files

## Safety checklist before opening a PR

- `.env` is not committed
- credential files are not committed
- local database/log files are not committed
- app still starts with documented commands
