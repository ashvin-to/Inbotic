# Inbotic

Inbotic turns important Gmail messages into actionable Google Tasks through a multi-user web app with optional AI-assisted chat context.

## Tech stack

- Backend: FastAPI, SQLAlchemy, Jinja2
- Frontend: React + Vite
- Integrations: Gmail API, Google Tasks API
- Database: SQLite (default via `DATABASE_URL`)

## What this project showcases

- FastAPI backend with authentication, rate-limiting, and Gmail/Google Tasks integration
- Server-rendered web interface (FastAPI + Jinja templates)
- React frontend implementation for modern client-side UI
- Email parsing and task creation workflow with LLM-assisted features
- SQLite-backed user/task/email persistence

## Interface options (both kept intentionally)

1. **FastAPI + Jinja interface (current backend-served UI)**
   - Entry point: `python start_web.py`
   - Docs: [WEB_INTERFACE_README.md](WEB_INTERFACE_README.md)

2. **React frontend (Vite)**
   - Source: [frontend](frontend)
   - Docs: [frontend/README.md](frontend/README.md)

## Prerequisites

- Python 3.10+
- Node.js 18+
- A Google Cloud project with OAuth client credentials

## Backend setup (recommended first)

### 1) Clone and enter the project

```bash
git clone <your-repo-url>
cd inbotic
```

### 2) Create Python environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Create local environment config

```bash
cp .env.example .env
```

### 4) Configure Google OAuth and secrets

Edit `.env` and set at minimum:

- `CLIENT_ID`
- `CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI` (default: `http://localhost:8000/auth/callback`)
- `SECRET_KEY`

Generate a strong secret key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Create a local secrets folder and place your Google credentials JSON there:

```bash
mkdir -p .secrets
# put your credentials file at .secrets/google-credentials.json
```

Important:
- Keep Google credentials outside git, e.g. `.secrets/google-credentials.json`
- Do not commit `.env`, credential JSON, database files, or logs

### 5) Run backend

```bash
python start_web.py
```

Open `http://localhost:8000`.

## Frontend setup (React)

Run in a separate terminal after backend is up:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Build for production:

```bash
npm run build
```

## API docs

When backend is running, FastAPI docs are available at:
- `http://localhost:8000/docs`

## Project structure

- `web_app.py` - FastAPI app and routes
- `database.py` - database models/session setup
- `auth.py` - auth/token helpers
- `gmail_service.py` / `google_tasks_service.py` - Google integrations
- `llm_features/` - LLM-related integration utilities
- `templates/` - backend-rendered pages
- `frontend/` - React app
- `scripts/` - maintenance and migration utilities

## Google Cloud OAuth checklist

1. In Google Cloud Console, enable Gmail API and Google Tasks API.
2. Configure OAuth consent screen.
3. Create an OAuth Client ID (Web application).
4. Add redirect URI: `http://localhost:8000/auth/callback`.
5. Copy client ID/secret into `.env`.

## Troubleshooting

- **Missing `SECRET_KEY` error:** set `SECRET_KEY` in `.env` (required at startup).
- **OAuth callback errors:** verify `GOOGLE_REDIRECT_URI` exactly matches Google Cloud settings.
- **Gmail/Tasks auth failures:** ensure APIs are enabled in your Google Cloud project.
- **Module import issues:** confirm `.venv` is activated and dependencies installed.

## Security note for public repos

If secrets were ever committed in history, clean git history before first public push (for example with `git filter-repo` or BFG), then rotate exposed secrets.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
