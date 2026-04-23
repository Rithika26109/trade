#!/usr/bin/env python3
"""
refresh_kite_token.py
─────────────────────
Run by a local cron at ~06:30 IST each weekday. Performs TOTP auto-login
to Zerodha, then pushes the fresh access token into a GitHub repo secret
named KITE_ACCESS_TOKEN so the 07:30 IST Claude Routine can use it.

Kite access tokens expire at 06:00 IST daily and require interactive (TOTP)
login that routines can't perform themselves.

Requires:
  - config/.env fully populated (KITE_API_KEY, KITE_API_SECRET, KITE_USER_ID,
    KITE_TOTP_SECRET, KITE_PASSWORD)
  - GitHub CLI `gh` authenticated with repo scope
  - Env var GITHUB_REPO (owner/repo) OR passed via --repo

Usage:
  python scripts/refresh_kite_token.py --repo rithika/trade
  python scripts/refresh_kite_token.py --dry-run    # login only, skip gh
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _set_secret(repo: str, name: str, value: str) -> int:
    p = subprocess.run(
        ["gh", "secret", "set", name, "--repo", repo, "--body", value],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        print(f"[refresh_kite_token] gh secret set failed: {p.stderr.strip()}",
              file=sys.stderr)
    return p.returncode


def _send_telegram(msg: str):
    """Send a Telegram message via kite.sh. Best-effort, never raises."""
    try:
        script = REPO_ROOT / "scripts" / "kite.sh"
        subprocess.run([str(script), "telegram", msg],
                       capture_output=True, text=True, timeout=15)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPO", ""),
                    help="owner/repo for gh secret set (or env GITHUB_REPO)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Login + print token; skip gh secret set")
    args = ap.parse_args()

    # Import only now so a missing dep doesn't break arg parsing
    from src.auth.login import ZerodhaAuth
    from src.utils.logger import logger

    try:
        auth = ZerodhaAuth()
        kite = auth.login()
    except Exception as e:
        print(f"[refresh_kite_token] login failed: {e}", file=sys.stderr)
        _send_telegram(f"❌ 06:30 Token refresh FAILED: {e}")
        return 1

    token = getattr(auth, "access_token", None) or kite.access_token  # type: ignore[attr-defined]
    if not token:
        print("[refresh_kite_token] login succeeded but no access_token found",
              file=sys.stderr)
        _send_telegram("❌ 06:30 Token refresh: login OK but no token found")
        return 1

    masked = f"{token[:4]}…{token[-4:]}"
    logger.info(f"[refresh_kite_token] obtained access token {masked}")

    if args.dry_run:
        print(f"dry-run: access_token={masked} (length={len(token)})")
        _send_telegram(f"✅ 06:30 Token refresh OK (dry-run)")
        return 0

    if not args.repo:
        print("[refresh_kite_token] --repo or GITHUB_REPO env required",
              file=sys.stderr)
        return 2
    if not _gh_available():
        print("[refresh_kite_token] `gh` CLI not found on PATH", file=sys.stderr)
        return 2

    rc = _set_secret(args.repo, "KITE_ACCESS_TOKEN", token)
    if rc == 0:
        logger.info(f"[refresh_kite_token] pushed KITE_ACCESS_TOKEN to {args.repo}")
        _send_telegram(f"✅ 06:30 Token refresh OK, pushed to GitHub")
    else:
        _send_telegram(f"⚠️ 06:30 Token refresh: login OK but GitHub push failed")
    return rc


if __name__ == "__main__":
    sys.exit(main())
