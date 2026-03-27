# Inbotic Web Interface

Web app for connecting Gmail and creating Google Tasks from email content.

## Features

- **Beautiful Dashboard** - Clean, modern interface built with Tailwind CSS
- **Dual OAuth Modes** - Hosted OAuth (shared app credentials) or manual OAuth setup
- **Real-time Email Processing** - Process emails and create tasks with one click
- **Task Management** - View all your tasks organized by lists
- **Email History** - See processed emails and extracted information
- **Statistics Dashboard** - Monitor your Inbotic activity
- **Responsive Design** - Works on desktop and mobile devices

## Setup

### 1. Install dependencies
```bash
cd inbotic
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set a `SECRET_KEY` in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then set:

```env
SECRET_KEY=<paste-generated-value>
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
```

### 2. Start the web interface
```bash
python start_web.py
```

### 3. Open in browser
Visit: **http://localhost:8000**

## Authentication

### Mode A: Hosted OAuth (recommended)

- You (app owner) set `CLIENT_ID` and `CLIENT_SECRET` on the backend.
- Users click **Continue with Google** and finish login.
- Best for non-technical end users.

### Mode B: Manual OAuth

- Users click **Manual OAuth setup**.
- They can either:
  - Upload Google OAuth JSON, or
  - Paste `CLIENT_ID` and `CLIENT_SECRET` directly.
- Uploaded JSON is saved to `.secrets/google-credentials.json`.

### Production default

- Manual OAuth is disabled by default on hosted/prod environments.
- To enable it explicitly, set:

```env
INBOTIC_ALLOW_MANUAL_OAUTH=true
```

## Google OAuth Checklist

1. Create/select a Google Cloud project.
2. Enable Gmail API and Google Tasks API.
3. Configure OAuth consent screen.
4. Create OAuth Client ID (Web application).
5. Add redirect URI: `http://localhost:8000/auth/callback` (and your deployed callback URL if hosting).

## Usage

### Dashboard
- View statistics and recent activity
- Process emails manually with customizable settings
- See recent tasks created from emails

### Process Emails
- **Days Back**: How far back to look for emails (1-30 days)
- **Max Emails**: Maximum number of emails to process (1-50)
- Click "Process Emails" to start the magic!

### View Tasks
- Browse all tasks organized by Google Tasks lists
- See task details, due dates, and notes
- Monitor task completion status

### Email History
- View recently processed emails
- See extracted deadlines and action items
- Track which emails have been processed

### Statistics
- Monitor task creation activity
- View system status and health
- Quick access to all features

## Interface Features

- **Modern Design** - Clean, professional interface
- **Responsive Layout** - Works on all screen sizes
- **Real-time Updates** - See results immediately
- **Intuitive Navigation** - Easy to find what you need
- **Status Indicators** - Clear visual feedback

## Configuration

The web interface uses the same config as the backend:

```env
# Google API Configuration
GOOGLE_CREDENTIALS_PATH=.secrets/google-credentials.json
CLIENT_ID=your-google-oauth-client-id
CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# Security (required)
SECRET_KEY=replace-with-strong-random-secret

# Web Interface Configuration
WEB_HOST=0.0.0.0
WEB_PORT=8000
WEB_URL=http://localhost:8000
```

## API Endpoints

The web interface provides these endpoints:

- `GET /` - Dashboard/Home page
- `GET /auth/gmail` - OAuth entry (auto-chooser when applicable)
- `GET /auth/gmail?mode=shared` - Force hosted OAuth
- `GET /auth/gmail?mode=manual` - Force manual setup
- `GET /setup/google-credentials` - Manual OAuth setup page
- `GET /auth/callback` - OAuth2 callback handler
- `POST /process-emails` - Manually trigger email processing
- `GET /tasks` - View all tasks
- `GET /emails` - View processed emails
- `GET /stats` - View statistics

## Security

- **OAuth2 Authentication** - Secure Google account connection
- **Token-based Sessions** - Automatic session management
- **HTTPS Ready** - Can be deployed with SSL certificates
- **CORS Protection** - Configurable cross-origin policies

## What It Does

1. **Connect Gmail** - Secure OAuth2 authentication
2. **Scan Emails** - Find important emails with deadlines and action items
3. **Extract Information** - Use AI-like pattern matching to find key details
4. **Create Tasks** - Generate actionable tasks in Google Tasks
5. **Set Deadlines** - Automatically set due dates when found
6. **Organize** - Keep everything organized in task lists

## Mobile Friendly

The interface is fully responsive and works great on:
- Desktop computers
- Tablets
- Mobile phones
- Any modern web browser

## Integration

The web interface seamlessly integrates with:
- **Gmail API** - Read emails securely
- **Google Tasks API** - Create and manage tasks
- **OAuth2 Flow** - Secure authentication
- **Local Processing** - All processing happens locally

## Troubleshooting

### "Not Authenticated" Error
- Make sure you've completed the OAuth2 setup
- Check that your OAuth token file exists in the project directory
- Try refreshing the page or re-authenticating

### "OAuth not configured"
- Hosted mode: set backend `CLIENT_ID` and `CLIENT_SECRET`
- Manual mode disabled: set `INBOTIC_ALLOW_MANUAL_OAUTH=true`
- Then restart backend

### "Configuration error: Missing CLIENT_ID/CLIENT_SECRET"
- Use manual setup page (`/setup/google-credentials`) and upload JSON/paste values, or
- Set `CLIENT_ID`/`CLIENT_SECRET` in backend env
- Restart backend

### "Missing required environment variable: SECRET_KEY"
- Set `SECRET_KEY` in `.env`
- Generate one with: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`

### "No Emails Found"
- Check your Gmail connection
- Try processing with fewer days back
- Verify your Gmail has unread or recent emails

### "Service Unavailable"
- Make sure the web server is running
- Check the terminal for error messages
- Verify all dependencies are installed

## Production Deployment

For production use:

1. Host FastAPI backend on a backend platform (Render, Railway, Fly.io, VPS, container host).
2. Host React frontend on Vercel/Netlify if desired.
3. Set backend env vars: `CLIENT_ID`, `CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `SECRET_KEY`.
4. Add deployed callback URL in Google OAuth redirect URIs.

## Support

The web interface provides the same functionality as the command-line version but with a user-friendly interface. All the core email processing and task creation logic remains the same.

---

Inbotic web interface is ready for both beginner local setup and production hosted OAuth.
