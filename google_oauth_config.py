import json
import os
from pathlib import Path
from typing import Optional, Tuple


def _extract_client_fields(payload: dict) -> Tuple[Optional[str], Optional[str]]:
    """Extract OAuth client_id/client_secret from Google credentials JSON."""
    for section in ("web", "installed"):
        block = payload.get(section)
        if isinstance(block, dict):
            client_id = (block.get("client_id") or "").strip() or None
            client_secret = (block.get("client_secret") or "").strip() or None
            if client_id and client_secret:
                return client_id, client_secret

    client_id = (payload.get("client_id") or "").strip() or None
    client_secret = (payload.get("client_secret") or "").strip() or None
    return client_id, client_secret


def _load_from_json_file(path: Path) -> Tuple[Optional[str], Optional[str]]:
    if not path.exists() or not path.is_file():
        return None, None

    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None, None

    return _extract_client_fields(payload)


def resolve_google_oauth_client_config() -> Tuple[Optional[str], Optional[str]]:
    """Resolve CLIENT_ID and CLIENT_SECRET from env or common credentials JSON files.

    Priority:
    1) Explicit env vars CLIENT_ID/CLIENT_SECRET
    2) Inline JSON in GOOGLE_OAUTH_CREDENTIALS_JSON
    3) File path from GOOGLE_CREDENTIALS_PATH (default .secrets/google-credentials.json)
    4) Auto-detect common credential file names in project root/.secrets
    """
    client_id = (os.getenv("CLIENT_ID") or "").strip() or None
    client_secret = (os.getenv("CLIENT_SECRET") or "").strip() or None
    if client_id and client_secret:
        return client_id, client_secret

    inline_json = (os.getenv("GOOGLE_OAUTH_CREDENTIALS_JSON") or "").strip()
    if inline_json:
        try:
            payload = json.loads(inline_json)
            parsed_id, parsed_secret = _extract_client_fields(payload)
            client_id = client_id or parsed_id
            client_secret = client_secret or parsed_secret
        except Exception:
            pass

    candidates = []
    configured_path = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", ".secrets/google-credentials.json"))
    candidates.append(configured_path)

    root = Path.cwd()
    candidates.extend(sorted(root.glob("client_secret*.json")))
    candidates.extend(sorted(root.glob("credentials*.json")))
    candidates.extend(sorted((root / ".secrets").glob("*.json")))

    seen = set()
    for candidate in candidates:
        resolved = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)

        parsed_id, parsed_secret = _load_from_json_file(candidate)
        client_id = client_id or parsed_id
        client_secret = client_secret or parsed_secret
        if client_id and client_secret:
            break

    if client_id:
        os.environ.setdefault("CLIENT_ID", client_id)
    if client_secret:
        os.environ.setdefault("CLIENT_SECRET", client_secret)

    return client_id, client_secret
