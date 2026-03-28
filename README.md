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

## Setup

### 1) Clone and install

```bash
git clone <your-repo-url>
cd inbotic
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure environment

```bash
cp .env.example .env
```

Set at least these values in `.env`:

- `SECRET_KEY`
- `GOOGLE_REDIRECT_URI` (default: `http://localhost:8000/auth/callback`)

Generate `SECRET_KEY` quickly:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3) Choose OAuth mode

The app supports two OAuth paths:

1. Hosted OAuth (recommended for end users):
   - You set `CLIENT_ID` and `CLIENT_SECRET` on the backend.
   - Users only click Continue with Google.

2. Manual OAuth:
   - Users upload OAuth JSON or paste Client ID/Secret in the setup page.
   - Uploaded JSON is stored at `.secrets/google-credentials.json`.

### 4) Run backend

```bash
python start_web.py
```

Open `http://localhost:8000` and click Connect Gmail.

## Quick start (least technical)

If you just want to run locally fast:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python start_web.py
```

Then open `http://localhost:8000` and use either hosted login or manual setup in-app.

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

## Deployment note (Vercel / Netlify)

- Vercel/Netlify are great for hosting the React frontend.
- This project's FastAPI backend (OAuth callbacks, token exchange, DB access) should be hosted on a backend platform such as Render, Railway, Fly.io, or a VPS/container host.
- Point the frontend API base URL to your backend domain and add that backend callback URL in Google OAuth redirect URIs.
- Manual OAuth setup is disabled by default on hosted/production deployments.
- To enable manual mode explicitly, set `INBOTIC_ALLOW_MANUAL_OAUTH=true` on backend env vars.
- Recommended production env vars:
   - `CLIENT_ID`
   - `CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI` (your deployed callback URL)
   - `SECRET_KEY`

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
5. For hosted OAuth, set `CLIENT_ID`/`CLIENT_SECRET` in backend env vars.
6. For manual OAuth, download OAuth JSON and upload it in the app setup page, or paste Client ID/Secret in that page.

## Troubleshooting

- **Missing `SECRET_KEY` error:** set `SECRET_KEY` in `.env` (required at startup).
- **OAuth callback errors:** verify `GOOGLE_REDIRECT_URI` exactly matches Google Cloud settings.
- **After Google login, browser says unable to connect:**
   - If using backend UI only, unset `FRONTEND_URL` so callback returns to `http://localhost:8000/`.
   - If using React UI, ensure frontend dev server is running at `FRONTEND_URL` (default `http://localhost:5173`).
- **Gmail/Tasks auth failures:** ensure APIs are enabled in your Google Cloud project.
- **Module import issues:** confirm `.venv` is activated and dependencies installed.

## Security note for public repos

If secrets were ever committed in history, clean git history before first public push (for example with `git filter-repo` or BFG), then rotate exposed secrets.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
