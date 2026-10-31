"""Security helpers: SSRF guard, password hashing, signed sessions, CSRF, rate limits."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import os
import re
import socket
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import settings

# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

BLOCKED_HOSTNAMES = {
    "localhost", "localhost.localdomain", "metadata.google.internal",
    "metadata", "instance-data", "169.254.169.254",
}
ALLOWED_SCHEMES = {"http", "https"}


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def resolve_public(host: str) -> bool:
    """Resolve every address for a host; reject if any is non-public."""
    host = host.strip().strip("[]").lower()
    if not host or host in BLOCKED_HOSTNAMES:
        return False
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            return False
        if not _ip_is_public(ip):
            return False
    return True


def is_safe_url(url: str, allow_ports: set[int] | None = None) -> tuple[bool, str]:
    if not url or len(url) > 2000:
        return False, "empty or too long"
    try:
        parts = urlparse(url)
    except ValueError:
        return False, "unparseable"
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        return False, "scheme not allowed"
    if not parts.hostname:
        return False, "missing host"
    if parts.username or parts.password:
        return False, "credentials in URL"
    if allow_ports is not None and parts.port and parts.port not in allow_ports:
        return False, "port not allowed"
    if not resolve_public(parts.hostname):
        return False, "private or unresolvable host"
    return True, ""


async def safe_fetch(
    url: str,
    *,
    method: str = "GET",
    max_redirects: int = 5,
    timeout: float = 12.0,
    max_bytes: int = 600_000,
    allow_ports: set[int] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[httpx.Response | None, bytes, str]:
    """Fetch a URL with SSRF protection and a size cap.

    Redirects are followed manually so every hop is re-validated.
    """
    current = url
    request_headers = {"User-Agent": "EuroJobsPro/2.0 (link validation)"}
    if headers:
        request_headers.update(headers)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            ok, reason = await asyncio.to_thread(is_safe_url, current, allow_ports)
            if not ok:
                return None, b"", f"blocked: {reason}"
            try:
                async with client.stream(method, current, headers=request_headers) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            return response, b"", "redirect without location"
                        current = str(httpx.URL(current).join(location))
                        continue
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            break
                        chunks.append(chunk)
                    return response, b"".join(chunks), ""
            except (httpx.HTTPError, ValueError) as exc:
                return None, b"", f"fetch failed: {exc}"
    return None, b"", "too many redirects"


# ---------------------------------------------------------------------------
# Password hashing (stdlib scrypt)
# ---------------------------------------------------------------------------

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Signed session cookie (no server-side session store needed)
# ---------------------------------------------------------------------------

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="ejp-session-v1")
SESSION_COOKIE = "ejp_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30


def new_session(user_id: int | None = None, locale: str | None = None) -> dict[str, Any]:
    return {
        "uid": user_id,
        "vid": base64.urlsafe_b64encode(os.urandom(12)).decode().rstrip("="),
        "csrf": base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip("="),
        "locale": locale,
        "ts": int(time.time()),
    }


def dump_session(data: dict[str, Any]) -> str:
    return _serializer.dumps(data)


def load_session(cookie: str | None) -> dict[str, Any] | None:
    if not cookie:
        return None
    try:
        data = _serializer.loads(cookie, max_age=SESSION_MAX_AGE)
        if not isinstance(data, dict):
            return None
        return data
    except BadSignature:
        return None


def valid_csrf(session: dict[str, Any] | None, token: str | None) -> bool:
    if not session or not token:
        return False
    return hmac.compare_digest(str(session.get("csrf", "")), str(token))


# ---------------------------------------------------------------------------
# In-memory rate limiting (swap for Redis if REDIS_URL is set)
# ---------------------------------------------------------------------------

_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(key: str, limit: int, window_seconds: int = 60) -> bool:
    now = time.monotonic()
    bucket = _buckets[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def utc_today_pacific() -> str:
    """Gemini free-tier daily counters reset at midnight Pacific time."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()
    except Exception:  # pragma: no cover - tzdata missing
        return datetime.now(timezone.utc).date().isoformat()


def pacific_reset_utc() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        tomorrow = (now + __import__("datetime").timedelta(days=1)).date()
        reset_local = datetime.combine(tomorrow, datetime.min.time(), tzinfo=ZoneInfo("America/Los_Angeles"))
        return reset_local.astimezone(timezone.utc)
    except Exception:  # pragma: no cover
        return datetime.now(timezone.utc)


def clean_text(value: str | None, max_length: int = 500) -> str:
    if not value:
        return ""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value)).strip()
    return text[:max_length]
