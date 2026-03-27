import os
import sys
import subprocess
import secrets
from pathlib import Path

from dotenv import load_dotenv

def main():
    """Start the Inbotic web interface"""
    load_dotenv()

    print("🚀 Starting Inbotic Web Interface")
    print("=" * 50)

    # Check if virtual environment exists
    venv_path = Path("venv")
    if not venv_path.exists():
        print("❌ Virtual environment not found. Please run:")
        print("   python3 -m venv venv")
        print("   source venv/bin/activate")
        print("   pip install -r requirements.txt")
        return False

    # Check if dependencies are installed
    try:
        import fastapi
        import jinja2
        import google
        print("✅ Dependencies verified")
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        print("Please install dependencies:")
        print("   source venv/bin/activate")
        print("   pip install -r requirements.txt")
        return False

    # Check if OAuth2 token exists
    if not os.path.exists('token.pickle'):
        print("⚠️  OAuth2 token not found")
        print("Please authenticate first:")
        print("1. Visit: http://localhost:8000")
        print("2. Click 'Connect Gmail'")
        print("3. Complete OAuth2 authentication")

    # Keep local development usable even if .env is missing.
    if not os.getenv("SECRET_KEY", "").strip():
        temp_secret = secrets.token_urlsafe(48)
        os.environ["SECRET_KEY"] = temp_secret
        os.environ.setdefault("DECODER_SECRET_KEY", temp_secret)
        print("⚠️  SECRET_KEY not found in environment")
        print("Using a temporary in-memory key for this session only.")
        print("Set SECRET_KEY in .env for persistent logins and production use.")

    # Start the web server
    print("🌐 Starting web server at http://localhost:8000")
    print("📧 Open your browser and navigate to: http://localhost:8000")
    print("⏹️  Press Ctrl+C to stop the server")

    try:
        # Use uvicorn with proper import string for reload
        cmd = [
            sys.executable, "-m", "uvicorn",
            "web_app:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload"
        ]

        subprocess.run(cmd)

    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return False

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
