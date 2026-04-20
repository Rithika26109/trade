"""
SEBI Compliance Helpers (Phase 4)
──────────────────────────────────
Startup-time checks that must pass before the bot is allowed to submit
live orders.

    * Algo-ID format:  ^[A-Za-z0-9_]{1,20}$   (Kite `tag` field limit)
    * Static IP pin:   if STATIC_IP_EXPECTED is configured, the machine's
                       outbound IP must match. SEBI's April-2026 framework
                       requires algo clients to register a static IP.
    * Order-rate cap:  personal-use algos must stay ≤ 10 orders/sec.
                       Enforced via RateLimiter on every broker call.
"""

from __future__ import annotations

import re
import socket
from urllib.request import urlopen

from config import settings
from src.utils.logger import logger


_ALGO_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,20}$")


class ComplianceError(RuntimeError):
    """Raised on hard compliance failures (live mode only)."""


def validate_algo_id(strict: bool) -> str:
    """Return sanitised Algo-ID.

    Format is ALWAYS validated (an invalid ALGO_ID is a config bug regardless
    of mode). ``strict`` only controls whether an empty value is a hard error.
    """
    tag = (getattr(settings, "ALGO_ID", "") or "").strip()
    if not tag:
        if strict:
            raise ComplianceError("ALGO_ID is empty; required for live trading (SEBI Apr-2026).")
        logger.warning("ALGO_ID empty — orders will be untagged (PAPER mode).")
        return ""
    if not _ALGO_ID_RE.match(tag):
        # Malformed ALGO_ID is always a hard error — a silent warning in paper
        # would let a typo make it all the way to live without ever surfacing.
        raise ComplianceError(
            f"ALGO_ID '{tag}' invalid. Must be 1-20 chars, "
            "alphanumeric or underscore."
        )
    return tag


def _public_ip(timeout: float = 3.0) -> str | None:
    """Best-effort detection of the current egress IP."""
    for url in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ):
        try:
            with urlopen(url, timeout=timeout) as r:  # noqa: S310 - trusted URLs
                ip = r.read().decode().strip()
                socket.inet_aton(ip)  # validates IPv4
                return ip
        except Exception:
            continue
    return None


def validate_static_ip(strict: bool) -> str | None:
    """Check that the outbound IP matches STATIC_IP_EXPECTED if set.

    The actual IP is intentionally NOT logged — it is information-disclosure
    for anyone who reads the log file. We log only PASS/FAIL.
    """
    expected = (getattr(settings, "STATIC_IP_EXPECTED", "") or "").strip()
    if not expected:
        logger.info("STATIC_IP_EXPECTED not configured — skipping IP pin check.")
        return None
    # Validate the EXPECTED value format always (config hygiene).
    try:
        socket.inet_aton(expected)
    except OSError:
        raise ComplianceError(
            f"STATIC_IP_EXPECTED is not a valid IPv4 address."
        )
    actual = _public_ip()
    if actual is None:
        msg = "Could not determine public IP — skipping pin check."
        if strict:
            raise ComplianceError(msg)
        logger.warning(msg)
        return None
    if actual != expected:
        msg = "Static-IP check FAILED (outbound IP does not match STATIC_IP_EXPECTED). SEBI algo framework requires registered IP."
        if strict:
            raise ComplianceError(msg)
        logger.warning(msg)
    else:
        logger.info("Static-IP check OK.")
    return actual


def startup_compliance_check(mode: str) -> dict:
    """Run all compliance checks. strict == (mode == 'live')."""
    strict = (mode == "live")
    algo_id = validate_algo_id(strict)
    ip_ok = validate_static_ip(strict) is not None
    report = {
        "algo_id": algo_id,
        "ip_pin": "configured" if ip_ok else "not-set-or-skipped",
        "mode": mode,
        "order_rate_limit_per_sec": getattr(settings, "ORDER_RATE_LIMIT_PER_SEC", 8),
    }
    # NOTE: do not include the actual egress IP in the compliance report —
    # it gets logged by callers and could leak infra details.
    logger.info(f"[COMPLIANCE] {report}")
    return report
