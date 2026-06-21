import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

load_dotenv()

from app.config import _build_allowed_hosts, _build_cors_origins, limiter, logger
from database import create_tables

app = FastAPI(
    title="Inbotic",
    description="Gmail-first multi-user web interface for email to tasks automation",
    version="3.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_build_allowed_hosts())


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

create_tables()

from app.routes import auth, emails, home, profile, tasks

app.include_router(auth.router)
app.include_router(home.router)
app.include_router(emails.router)
app.include_router(tasks.router)
app.include_router(profile.router)

from app.auto_process import shutdown_auto_process, startup_auto_process

app.add_event_handler("startup", startup_auto_process)
app.add_event_handler("shutdown", shutdown_auto_process)

# Serve built React frontend
frontend_dist = Path("frontend/dist")
if frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="frontend_assets")

    @app.exception_handler(404)
    async def serve_spa(request, exc):
        accept = request.headers.get("accept", "")
        if "text/html" in accept and not request.url.path.startswith("/api/"):
            return FileResponse(str(frontend_dist / "index.html"), media_type="text/html")
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Not Found"}, status_code=404)
