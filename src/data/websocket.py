"""
WebSocket Real-Time Data
────────────────────────
Stream live tick data from Zerodha via KiteTicker WebSocket.
"""

import threading
import time
from collections import defaultdict
from typing import Callable

from kiteconnect import KiteTicker

from config import settings
from src.utils.logger import logger


class TickerManager:
    """Manages real-time tick data streaming via WebSocket."""

    def __init__(self, api_key: str, access_token: str):
        self.kws = KiteTicker(api_key=api_key, access_token=access_token)
        self._callbacks: list[Callable] = []
        self._order_update_callbacks: list[Callable] = []
        self._latest_ticks: dict[int, dict] = {}
        self._subscribed_tokens: list[int] = []
        self._connected = False
        self._last_tick_ts: float = 0.0  # heartbeat monitor
        self._thread: threading.Thread | None = None

        # Wire up KiteTicker callbacks
        self.kws.on_ticks = self._on_ticks
        self.kws.on_connect = self._on_connect
        self.kws.on_close = self._on_close
        self.kws.on_error = self._on_error
        self.kws.on_reconnect = self._on_reconnect
        # Order state updates (SLM triggers, fills, rejections)
        self.kws.on_order_update = self._on_order_update

    def subscribe(self, tokens: list[int], mode: str = "quote"):
        """
        Subscribe to instrument tokens for live data.

        Args:
            tokens: List of instrument tokens
            mode: "ltp" (price only), "quote" (OHLC+vol), "full" (everything+depth)
        """
        self._subscribed_tokens = tokens
        mode_map = {
            "ltp": self.kws.MODE_LTP,
            "quote": self.kws.MODE_QUOTE,
            "full": self.kws.MODE_FULL,
        }
        self._subscribe_mode = mode_map.get(mode, self.kws.MODE_QUOTE)

        if self._connected:
            self.kws.subscribe(tokens)
            self.kws.set_mode(self._subscribe_mode, tokens)

    def on_tick(self, callback: Callable):
        """Register a callback function that receives tick data."""
        self._callbacks.append(callback)

    def on_order_update(self, callback: Callable):
        """Register a callback that receives broker order updates
        (SLM triggers, rejections, fills). Callback receives the raw
        KiteTicker order-update dict."""
        self._order_update_callbacks.append(callback)

    def seconds_since_last_tick(self) -> float:
        """Return how long since the most recent tick. 0 if never received."""
        if self._last_tick_ts == 0:
            return 0.0
        return time.time() - self._last_tick_ts

    def get_ltp(self, token: int) -> float | None:
        """Get the latest price for an instrument token."""
        tick = self._latest_ticks.get(token)
        if tick:
            return tick.get("last_price")
        return None

    def get_tick(self, token: int) -> dict | None:
        """Get the latest full tick data for an instrument token."""
        return self._latest_ticks.get(token)

    def start(self, threaded: bool = True):
        """Start the WebSocket connection."""
        if threaded:
            self._thread = threading.Thread(target=self.kws.connect, daemon=True)
            self._thread.start()
            logger.info("WebSocket started in background thread")
        else:
            self.kws.connect()

    def stop(self):
        """Stop the WebSocket connection."""
        self.kws.close()
        self._connected = False
        logger.info("WebSocket stopped")

    def _on_ticks(self, ws, ticks: list[dict]):
        """Handle incoming tick data."""
        self._last_tick_ts = time.time()
        for tick in ticks:
            token = tick["instrument_token"]
            self._latest_ticks[token] = tick

        # Notify all registered callbacks
        for callback in self._callbacks:
            try:
                callback(ticks)
            except Exception as e:
                logger.error(f"Tick callback error: {e}")

    def _on_order_update(self, ws, data):
        """KiteTicker order-update hook. Fans out to registered listeners."""
        for cb in self._order_update_callbacks:
            try:
                cb(data)
            except Exception as e:
                logger.error(f"Order update callback error: {e}")

    def _on_connect(self, ws, response):
        """Handle successful WebSocket connection."""
        self._connected = True
        logger.info("WebSocket connected")

        if self._subscribed_tokens:
            self.kws.subscribe(self._subscribed_tokens)
            self.kws.set_mode(self._subscribe_mode, self._subscribed_tokens)
            logger.info(f"Subscribed to {len(self._subscribed_tokens)} instruments")

    def _on_close(self, ws, code, reason):
        """Handle WebSocket disconnection."""
        self._connected = False
        logger.warning(f"WebSocket closed: {code} — {reason}")

    def _on_error(self, ws, code, reason):
        """Handle WebSocket errors."""
        logger.error(f"WebSocket error: {code} — {reason}")

    def _on_reconnect(self, ws, attempts_count):
        """Handle WebSocket reconnection attempts."""
        logger.info(f"WebSocket reconnecting... attempt {attempts_count}")
