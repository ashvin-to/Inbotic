# 📧 Inbotic - Web Interface

A beautiful web interface for the Inbotic that allows you to connect your Gmail account and automatically create tasks from your emails.

## 🚀 Features

- **Beautiful Dashboard** - Clean, modern interface built with Tailwind CSS
- **Gmail OAuth2 Integration** - Secure authentication with your Gmail account
- **Real-time Email Processing** - Process emails and create tasks with one click
- **Task Management** - View all your tasks organized by lists
- **Email History** - See processed emails and extracted information
- **Statistics Dashboard** - Monitor your Inbotic activity
- **Responsive Design** - Works on desktop and mobile devices

## 🛠️ Setup

### 1. Install Dependencies
```bash
cd inbotic
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Start the Web Interface
```bash
python start_web.py
```

### 3. Open in Browser
Visit: **http://localhost:8000**

## 🔑 Authentication

1. **First Time Setup**:
   - Click "Connect Gmail" on the homepage
   - Complete OAuth2 authentication in your browser
   - Grant permissions for Gmail (read-only) and Google Tasks

2. **Subsequent Uses**:
   - The authentication token is saved automatically
   - You'll stay logged in between sessions

## 📋 Usage

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

## 🎨 Interface Features

- **Modern Design** - Clean, professional interface
- **Responsive Layout** - Works on all screen sizes
- **Real-time Updates** - See results immediately
- **Intuitive Navigation** - Easy to find what you need
- **Status Indicators** - Clear visual feedback

## 🔧 Configuration

The web interface uses the same configuration as the command-line version:

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

## 🚀 API Endpoints

The web interface provides these endpoints:

- `GET /` - Dashboard/Home page
- `GET /auth/gmail` - Initiate OAuth2 authentication
- `GET /auth/callback` - OAuth2 callback handler
- `POST /process-emails` - Manually trigger email processing
- `GET /tasks` - View all tasks
- `GET /emails` - View processed emails
- `GET /stats` - View statistics

## 🛡️ Security

- **OAuth2 Authentication** - Secure Google account connection
- **Token-based Sessions** - Automatic session management
- **HTTPS Ready** - Can be deployed with SSL certificates
- **CORS Protection** - Configurable cross-origin policies

## 🎯 What It Does

1. **Connect Gmail** - Secure OAuth2 authentication
2. **Scan Emails** - Find important emails with deadlines and action items
3. **Extract Information** - Use AI-like pattern matching to find key details
4. **Create Tasks** - Generate actionable tasks in Google Tasks
5. **Set Deadlines** - Automatically set due dates when found
6. **Organize** - Keep everything organized in task lists

## 📱 Mobile Friendly

The interface is fully responsive and works great on:
- Desktop computers
- Tablets
- Mobile phones
- Any modern web browser

## 🔄 Integration

The web interface seamlessly integrates with:
- **Gmail API** - Read emails securely
- **Google Tasks API** - Create and manage tasks
- **OAuth2 Flow** - Secure authentication
- **Local Processing** - All processing happens locally

## 🆘 Troubleshooting

### "Not Authenticated" Error
- Make sure you've completed the OAuth2 setup
- Check that your OAuth token file exists in the project directory
- Try refreshing the page or re-authenticating

### "Configuration error: Missing CLIENT_ID/CLIENT_SECRET"
- Set `CLIENT_ID` and `CLIENT_SECRET` in `.env`
- Restart the server after changing `.env`

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

## 🚀 Production Deployment

For production use:

1. **Set up a reverse proxy** (nginx recommended)
2. **Configure HTTPS** with SSL certificates
3. **Set up a process manager** (systemd, supervisor, etc.)
4. **Configure environment variables** for production URLs

## 📞 Support

The web interface provides the same functionality as the command-line version but with a user-friendly interface. All the core email processing and task creation logic remains the same.

---

**🎉 Enjoy your new Inbotic web interface!**
