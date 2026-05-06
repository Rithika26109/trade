"""
Zerodha Kite Connect Authentication
────────────────────────────────────
Handles login, TOTP generation, session management.
Access token (enctoken) is valid for one trading day — re-authenticate every morning.
"""

import json
import os
import time
from pathlib import Path

import pyotp
import requests
from kiteconnect import KiteConnect

from config import settings
from src.utils.logger import logger


# File to cache today's access token (avoid re-login during same day)
TOKEN_CACHE_FILE = settings.BASE_DIR / "config" / ".access_token"

# kiteconnect version range we've validated the monkey-patch against.
# If a future upgrade renames `_routes` or `reqsession`, _make_enctoken_kite
# will raise a clear error pointing here instead of silently misbehaving.
_KITECONNECT_TESTED_MAJOR = 5


def _make_enctoken_kite(enctoken: str) -> KiteConnect:
    """Configure a KiteConnect instance to use enctoken auth.

    Zerodha's authorize step can no longer be automated via API, so we use
    the enctoken cookie obtained after login + TOTP. This works with the
    /oms endpoints on kite.zerodha.com.

    WARNING: relies on kiteconnect internals (_routes, reqsession.headers).
    Tested with kiteconnect 5.1.0. requirements.txt pins the major version;
    this function probes the attributes at runtime and fails loudly if a
    future upgrade renames them.
    """
    kite = KiteConnect(api_key=settings.KITE_API_KEY)
    if not hasattr(kite, "_routes") or not isinstance(kite._routes, dict):
        raise AuthenticationError(
            "kiteconnect compat: KiteConnect._routes missing or not a dict. "
            "Pin kiteconnect to a major <= "
            f"{_KITECONNECT_TESTED_MAJOR + 1} or update _make_enctoken_kite."
        )
    if not hasattr(kite, "reqsession") or not hasattr(kite.reqsession, "headers"):
        raise AuthenticationError(
            "kiteconnect compat: KiteConnect.reqsession.headers missing. "
            "Pin kiteconnect to a major <= "
            f"{_KITECONNECT_TESTED_MAJOR + 1} or update _make_enctoken_kite."
        )
    kite.root = "https://kite.zerodha.com"
    # _routes is a class-level dict — copy to avoid mutating it globally
    kite._routes = {k: "/oms" + v if not v.startswith("/oms") else v
                    for k, v in kite._routes.items()}
    # Prevent kiteconnect from setting its own "token api_key:access_token" header
    kite.api_key = ""
    kite.access_token = ""
    kite.reqsession.headers["Authorization"] = f"enctoken {enctoken}"
    return kite


class ZerodhaAuth:
    """Manages Zerodha Kite Connect authentication."""

    def __init__(self):
        self.kite = KiteConnect(api_key=settings.KITE_API_KEY)
        self.access_token = None

    def login(self) -> KiteConnect:
        """
        Full login flow:
        1. Check if cached token from today is still valid
        2. If not, perform fresh login with auto-TOTP
        Returns authenticated KiteConnect instance.
        """
        # Try cached token first
        if self._load_cached_token():
            logger.info("Using cached access token")
            return self.kite

        # Fresh login needed
        logger.info("Performing fresh login to Zerodha...")
        enctoken = self._login_and_get_enctoken()
        self.access_token = enctoken
        self.kite = _make_enctoken_kite(enctoken)
        self._save_cached_token()

        logger.success(f"Logged in as {settings.KITE_USER_ID}")
        return self.kite

    def _load_cached_token(self) -> bool:
        """Load access token from cache if it was saved today.

        Refuses to use the cache if the file is readable by group/world
        (a tampered or sloppily-restored 0644 file would otherwise leak
        the enctoken silently). On any unexpected failure the cache is
        deleted so the next call performs a fresh login.
        """
        if not TOKEN_CACHE_FILE.exists():
            return False

        # Permission check — token grants full account access
        try:
            mode = TOKEN_CACHE_FILE.stat().st_mode & 0o777
            if mode & 0o077:
                logger.warning(
                    f"Refusing to use cached token: {TOKEN_CACHE_FILE} has "
                    f"mode {oct(mode)} (group/world readable). Deleting."
                )
                TOKEN_CACHE_FILE.unlink(missing_ok=True)
                return False
        except OSError as e:
            logger.debug(f"Cached token stat failed: {e}")
            return False

        # Parse
        try:
            data = json.loads(TOKEN_CACHE_FILE.read_text())
            if data.get("date") != str(settings.now_ist().date()):
                return False
            enctoken = data["access_token"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Cached token unreadable, discarding: {e}")
            TOKEN_CACHE_FILE.unlink(missing_ok=True)
            return False

        # Verify token is still valid; on failure delete so next call re-logs in
        try:
            self.kite = _make_enctoken_kite(enctoken)
            self.access_token = enctoken
            self.kite.profile()
            return True
        except Exception as e:
            logger.info(f"Cached token rejected by Kite, refreshing: {e}")
            TOKEN_CACHE_FILE.unlink(missing_ok=True)
            self.kite = KiteConnect(api_key=settings.KITE_API_KEY)
            self.access_token = None
            return False

    def _save_cached_token(self):
        """Save access token to file for reuse during the day.

        The token grants full account access until midnight IST, so the file
        is created with owner-only permissions (0600) and its parent directory
        with 0700. On POSIX only; chmod is a no-op on Windows.
        """
        data = {
            "date": str(settings.now_ist().date()),
            "access_token": self.access_token,
        }
        parent = TOKEN_CACHE_FILE.parent
        parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(parent, 0o700)
        except (OSError, NotImplementedError):
            pass
        TOKEN_CACHE_FILE.write_text(json.dumps(data))
        try:
            os.chmod(TOKEN_CACHE_FILE, 0o600)
        except (OSError, NotImplementedError):
            pass

    def _login_and_get_enctoken(self) -> str:
        """
        Automate the login flow:
        1. POST credentials to Zerodha login
        2. Submit TOTP
        3. Extract enctoken from session cookies
        """
        session = requests.Session()

        # Step 1: POST login credentials
        login_url = "https://kite.zerodha.com/api/login"
        login_data = {
            "user_id": settings.KITE_USER_ID,
            "password": self._get_password(),
        }

        logger.debug("Submitting login credentials...")
        resp = self._post_with_retry(session, login_url, login_data,
                                     label="login")
        result = resp.json()

        if result.get("status") != "success":
            raise AuthenticationError(f"Login failed: {result}")

        request_id = result["data"]["request_id"]

        # Step 2: Submit TOTP
        totp = pyotp.TOTP(settings.KITE_TOTP_SECRET)
        twofa_url = "https://kite.zerodha.com/api/twofa"
        twofa_data = {
            "user_id": settings.KITE_USER_ID,
            "request_id": request_id,
            "twofa_value": totp.now(),
            "twofa_type": "totp",
        }

        logger.debug("Submitting TOTP...")
        # TOTP is time-sensitive (30s window) so don't retry on transient
        # failures with the same value — regenerate on retry.
        resp = self._post_with_retry(session, twofa_url, twofa_data,
                                     label="twofa", regenerate_totp=totp,
                                     totp_field=("twofa_value",))
        result = resp.json()

        if result.get("status") != "success":
            raise AuthenticationError(f"TOTP verification failed: {result}")

        # Step 3: Extract enctoken from cookies
        enctoken = None
        for cookie in session.cookies:
            if cookie.name == "enctoken":
                enctoken = cookie.value
                break

        if not enctoken:
            raise AuthenticationError(
                "Login succeeded but no enctoken cookie found"
            )

        logger.debug(f"Got enctoken: {enctoken[:8]}...")
        return enctoken

    @staticmethod
    def _post_with_retry(session: requests.Session, url: str, data: dict,
                         label: str, *, max_attempts: int = 3,
                         regenerate_totp: "pyotp.TOTP | None" = None,
                         totp_field: tuple = ()) -> requests.Response:
        """POST with retry on transient network errors only.

        HTTP 4xx/5xx responses from Kite (raise_for_status) are NOT retried —
        those indicate auth issues that retrying won't fix. Connection
        resets, DNS hiccups, and timeouts are retried with exponential
        backoff (1s, 2s).
        """
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            if regenerate_totp is not None and attempt > 1 and totp_field:
                # Refresh the TOTP value on each retry to avoid using a
                # value from a previous 30s window.
                data = {**data, totp_field[0]: regenerate_totp.now()}
            try:
                resp = session.post(url, data=data, timeout=30)
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                if attempt == max_attempts:
                    break
                backoff = 2 ** (attempt - 1)
                logger.warning(
                    f"{label} POST transient failure "
                    f"(attempt {attempt}/{max_attempts}): {e}. "
                    f"Retrying in {backoff}s..."
                )
                time.sleep(backoff)
            except requests.HTTPError as e:
                # Don't retry — Kite said no.
                raise AuthenticationError(
                    f"{label} POST returned HTTP error: {e}"
                ) from e
        raise AuthenticationError(
            f"{label} POST failed after {max_attempts} attempts: {last_exc}"
        )

    def _get_password(self) -> str:
        """
        Get Zerodha password.
        Uses KITE_PASSWORD from .env if set (required for cron/unattended runs),
        otherwise falls back to interactive prompt.
        """
        if settings.KITE_PASSWORD:
            return settings.KITE_PASSWORD

        import getpass
        return getpass.getpass("Enter Zerodha password: ")

    def get_kite(self) -> KiteConnect:
        """Return the authenticated KiteConnect instance."""
        if self.access_token is None:
            self.login()
        return self.kite


class AuthenticationError(Exception):
    """Raised when Zerodha authentication fails."""

    pass
