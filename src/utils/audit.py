"""
SEBI-Compliant Audit Trail (Phase 4)
─────────────────────────────────────
Append-only JSONL log of every broker-facing order lifecycle event. The
exchange/broker already stores orders server-side (tagged with our Algo-ID),
but SEBI's April-2026 algo framework expects the originator to keep a
local, tamper-evident audit. JSONL is append-only and each line is a
self-contained record.

Events captured:
    * order_place
    * order_place_failed
    * order_fill
    * slm_place / slm_cancel / slm_modify / slm_fired
    * order_close
    * order_close_aborted
    * order_rejected
    * reconcile_drift
    * kill_switch_triggered
    * startup / shutdown
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from config import settings


_LOCK = threading.Lock()


def _audit_path() -> Path:
    override = getattr(settings, "AUDIT_LOG_PATH", None)
    if override:
        p = Path(override)
    else:
        p = Path(settings.LOG_DIR) / "audit" / "audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def audit(event: str, **fields: Any) -> None:
    """Append one JSON line to the audit log. Never raises."""
    try:
        rec = {
            "ts": datetime.now(settings.IST).isoformat(timespec="milliseconds"),
            "event": event,
            "mode": getattr(settings, "TRADING_MODE", "paper"),
            "algo_id": getattr(settings, "ALGO_ID", "") or "",
            "pid": os.getpid(),
        }
        # Sanitize non-JSON-serializable values
        for k, v in fields.items():
            if isinstance(v, datetime):
                rec[k] = v.isoformat()
            else:
                try:
                    json.dumps(v)
                    rec[k] = v
                except (TypeError, ValueError):
                    rec[k] = repr(v)

        line = json.dumps(rec, separators=(",", ":"), ensure_ascii=False)
        path = _audit_path()
        with _LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        # Audit MUST NOT break the trading path.
        pass
