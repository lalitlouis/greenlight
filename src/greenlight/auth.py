"""Sign in with Google: server-side OAuth code flow + stdlib-signed session cookie.

No auth framework: the flow is ~three requests, the session is an HMAC-signed
JSON payload, and Google's id_token is verified with google-auth (already a
transitive dependency). If OAuth env vars are absent, /api/auth/status reports
unconfigured and the UI simply doesn't offer sign-in — the site never breaks.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any

CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_COOKIE = "sr_session"
SESSION_TTL_S = 30 * 24 * 3600
STATE_TTL_S = 600

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and SESSION_SECRET)


def _sign(payload: bytes) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload, hashlib.sha256).hexdigest()


def make_session(user: dict[str, Any]) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({**user, "exp": int(time.time()) + SESSION_TTL_S}).encode()
    )
    return payload.decode() + "." + _sign(payload)


def read_session(cookie: str | None) -> dict[str, Any] | None:
    if not cookie or "." not in cookie or not SESSION_SECRET:
        return None
    payload_s, sig = cookie.rsplit(".", 1)
    payload = payload_s.encode()
    if not hmac.compare_digest(_sign(payload), sig):
        return None
    try:
        user = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None
    if user.get("exp", 0) < time.time():
        return None
    return user


def make_state() -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"ts": int(time.time())}).encode())
    return payload.decode() + "." + _sign(payload)


def check_state(state: str | None) -> bool:
    if not state or "." not in state:
        return False
    payload_s, sig = state.rsplit(".", 1)
    payload = payload_s.encode()
    if not hmac.compare_digest(_sign(payload), sig):
        return False
    try:
        ts = json.loads(base64.urlsafe_b64decode(payload))["ts"]
    except Exception:
        return False
    return time.time() - ts < STATE_TTL_S


def login_url(redirect_uri: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": make_state(),
        "prompt": "select_account",
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    """Code -> verified identity {sub, email, name, picture}. Raises on failure."""
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        tokens = json.loads(resp.read())

    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    info = google_id_token.verify_oauth2_token(
        tokens["id_token"], google_requests.Request(), CLIENT_ID
    )
    return {
        "sub": info["sub"],
        "email": info.get("email", ""),
        "name": info.get("name", info.get("email", "")),
        "picture": info.get("picture", ""),
    }
