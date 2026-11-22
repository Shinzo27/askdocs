"""Anonymous sessions: a signed httpOnly cookie, no accounts (ADR-008).

The signature is HMAC-SHA256 over `<session-id>.<expiry>` with `SESSION_SECRET`;
nothing is stored server-side, so a conversation is only ever reachable by the
browser that holds the cookie. No email, no provider, no retention policy to write.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid

from askdocs_api.config import get_settings

COOKIE = "askdocs_session"
MAX_AGE = 30 * 24 * 3600  # 30 days


def _sign(payload: str) -> str:
    secret = get_settings().session_secret.encode("utf-8")
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def issue() -> tuple[str, str]:
    """Return `(session_id, cookie_value)`."""
    session_id = uuid.uuid4().hex
    expiry = int(time.time()) + MAX_AGE
    payload = f"{session_id}.{expiry}"
    return session_id, f"{payload}.{_sign(payload)}"


def verify(value: str | None) -> str | None:
    """The session id when the signature and expiry hold, else None."""
    if not value:
        return None
    parts = value.rsplit(".", 1)
    if len(parts) != 2:
        return None
    payload, signature = parts
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        session_id, expiry = payload.rsplit(".", 1)
        if int(expiry) < int(time.time()):
            return None
    except ValueError:
        return None
    return session_id


def cookie_header(value: str) -> str:
    return (
        f"{COOKIE}={value}; Path=/; HttpOnly; SameSite=Lax; "
        f"Max-Age={MAX_AGE}"
    )


def decode_existing(value: str | None) -> str | None:
    """Base64 helper kept for symmetry with the TypeScript client fixture."""
    if not value:
        return None
    try:
        return base64.urlsafe_b64decode(value).decode("utf-8")
    except Exception:
        return None
