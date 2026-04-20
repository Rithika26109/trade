"""
Zerodha Kite Connect Authentication
────────────────────────────────────
Handles login, TOTP generation, session management.
Access token is valid for one trading day — re-authenticate every morning.
"""

import json
import os
import time
import urllib.parse
from pathlib import Path

import pyotp
import requests
from kiteconnect import KiteConnect

from config import settings
from src.utils.logger import logger


# File to cache today's access token (avoid re-login during same day)
TOKEN_CACHE_FILE = settings.BASE_DIR / "config" / ".access_token"


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
        request_token = self._get_request_token()
        self._generate_session(request_token)

        logger.success(f"Logged in as {settings.KITE_USER_ID}")
        return self.kite

    def _load_cached_token(self) -> bool:
        """Load access token from cache if it was saved today."""
        try:
            if not TOKEN_CACHE_FILE.exists():
                return False

            data = json.loads(TOKEN_CACHE_FILE.read_text())

            if data.get("date") != str(settings.now_ist().date()):
                return False

            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)

            # Verify token is still valid
            self.kite.profile()
            return True
        except Exception:
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

    def _get_request_token(self) -> str:
        """
        Automate the login flow:
        1. POST credentials to Zerodha login
        2. Submit TOTP
        3. Extract request_token from redirect URL
        """
        session = requests.Session()

        # Step 1: POST login credentials
        login_url = "https://kite.zerodha.com/api/login"
        login_data = {
            "user_id": settings.KITE_USER_ID,
            "password": self._get_password(),
        }

        logger.debug("Submitting login credentials...")
        resp = session.post(login_url, data=login_data, timeout=30)
        resp.raise_for_status()
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
        resp = session.post(twofa_url, data=twofa_data, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        if result.get("status") != "success":
            raise AuthenticationError(f"TOTP verification failed: {result}")

        # Step 3: Get request_token from redirect
        redirect_url = (
            f"https://kite.trade/connect/login?api_key={settings.KITE_API_KEY}&v=3"
        )
        resp = session.get(redirect_url, allow_redirects=False, timeout=30)

        if resp.status_code in (301, 302):
            location = resp.headers.get("Location", "")
        else:
            # Sometimes the token is in the response URL after redirects
            resp = session.get(redirect_url, allow_redirects=True, timeout=30)
            location = str(resp.url)

        # Parse request_token from redirect URL
        parsed = urllib.parse.urlparse(location)
        params = urllib.parse.parse_qs(parsed.query)

        if "request_token" not in params:
            raise AuthenticationError(
                f"Could not extract request_token from redirect. URL: {location}"
            )

        request_token = params["request_token"][0]
        logger.debug(f"Got request_token: {request_token[:8]}...")
        return request_token

    def _generate_session(self, request_token: str):
        """Exchange request_token for access_token."""
        data = self.kite.generate_session(
            request_token=request_token,
            api_secret=settings.KITE_API_SECRET,
        )
        self.access_token = data["access_token"]
        self.kite.set_access_token(self.access_token)
        self._save_cached_token()

    def _get_password(self) -> str:
        """
        Get Zerodha password.
        Always prompt at runtime via getpass — never read from env or disk,
        so the master password cannot leak via .env backups or process env.
        """
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
