"""
Confluence Scoring Engine (Phase 3B — 4 orthogonal axes)
─────────────────────────────────────────────────────────
Assigns a 0-100 confidence score using four **orthogonal** axes of 0-25
points each, designed to eliminate the double-counting the previous
5-component engine suffered from (EMA↔VWAP↔volume overlap):

    1. TREND         — HTF EMA slope + ADX strength / direction agreement.
    2. MOMENTUM      — RSI level + z-scored rate-of-change.
    3. LOCATION      — Distance to VWAP AND nearest multi-touch S/R cluster
                       (combined, so "where price sits in structure" is
                       counted once).
    4. PARTICIPATION — Volume z-score + OBV slope.

`ConfluenceScore.components` uses the new 4-axis keys:
    {"trend", "momentum", "location", "participation"}.
`ConfluenceScore.total` ∈ [0, 100].
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.strategy.base import Signal


AXIS_MAX = 25.0  # Each axis 0..25; four axes total 100.


@dataclass
class ConfluenceScore:
    total: float = 0.0
    components: dict = field(default_factory=dict)


def calculate_confluence(
    signal: Signal,
    df: pd.DataFrame,
    df_htf: pd.DataFrame = None,
    regime=None,
) -> ConfluenceScore:
    """Score a trade signal on four orthogonal axes. Returns 0-100."""
    score = ConfluenceScore()
    score.components["trend"] = _score_trend(signal, df, df_htf, regime)
    score.components["momentum"] = _score_momentum(signal, df)
    score.components["location"] = _score_location(signal, df)
    score.components["participation"] = _score_participation(signal, df)
    score.total = float(sum(score.components.values()))
    return score


# ──────────────────────────────────────────────────────────────────────────
# Axis 1 — TREND (HTF EMA slope + ADX / regime direction agreement)
# ──────────────────────────────────────────────────────────────────────────
def _score_trend(signal: Signal, df: pd.DataFrame, df_htf, regime) -> float:
    """0..25. Rewards HTF EMA slope agreeing with signal + regime + ADX strength."""
    points = 0.0
    have_info = False

    if df_htf is not None and not df_htf.empty and len(df_htf) >= 3:
        if "ema_fast" in df_htf.columns and "ema_slow" in df_htf.columns:
            fast = df_htf["ema_fast"].iloc[-1]
            slow = df_htf["ema_slow"].iloc[-1]
            prev_fast = df_htf["ema_fast"].iloc[-3]
            if pd.notna(fast) and pd.notna(slow) and pd.notna(prev_fast):
                have_info = True
                slope = float(fast) - float(prev_fast)
                htf_bullish = fast > slow
                if signal == Signal.BUY and htf_bullish and slope > 0:
                    points += 12
                elif signal == Signal.SELL and (not htf_bullish) and slope < 0:
                    points += 12
                elif signal == Signal.BUY and htf_bullish:
                    points += 8
                elif signal == Signal.SELL and not htf_bullish:
                    points += 8

    if regime is not None:
        have_info = True
        if signal == Signal.BUY and getattr(regime, "is_bullish", False):
            points += 8
        elif signal == Signal.SELL and getattr(regime, "is_bearish", False):
            points += 8
        elif getattr(regime, "is_trending", False):
            points += 4

    if "adx" in df.columns and pd.notna(df["adx"].iloc[-1]):
        have_info = True
        adx = float(df["adx"].iloc[-1])
        if adx >= 30:
            points += 5
        elif adx >= 20:
            points += 3

    if not have_info:
        return AXIS_MAX / 2  # 12.5 neutral
    return min(points, AXIS_MAX)


# ──────────────────────────────────────────────────────────────────────────
# Axis 2 — MOMENTUM (RSI + ROC z-score)
# ──────────────────────────────────────────────────────────────────────────
def _score_momentum(signal: Signal, df: pd.DataFrame) -> float:
    """0..25. RSI in favourable band + strong directional ROC z-score."""
    if len(df) < 6:
        return AXIS_MAX / 2

    points = 0.0

    if "rsi" in df.columns and pd.notna(df["rsi"].iloc[-1]):
        rsi = float(df["rsi"].iloc[-1])
        prev = float(df["rsi"].iloc[-3]) if pd.notna(df["rsi"].iloc[-3]) else rsi
        accel = (
            (signal == Signal.BUY and rsi > prev)
            or (signal == Signal.SELL and rsi < prev)
        )
        if signal == Signal.BUY:
            if 35 <= rsi <= 55 and accel:
                points += 13
            elif 30 <= rsi <= 60:
                points += 9
            elif rsi < 30:
                points += 6
            elif rsi > 70:
                points += 1
            else:
                points += 5
        elif signal == Signal.SELL:
            if 45 <= rsi <= 65 and accel:
                points += 13
            elif 40 <= rsi <= 70:
                points += 9
            elif rsi > 70:
                points += 6
            elif rsi < 30:
                points += 1
            else:
                points += 5

    if "close" in df.columns:
        closes = df["close"].astype(float)
        roc = closes.pct_change().dropna()
        if len(roc) >= 10:
            win = roc.tail(20) if len(roc) >= 20 else roc
            mu = win.mean()
            sd = win.std()
            if sd and sd > 0 and pd.notna(sd):
                z = (roc.iloc[-1] - mu) / sd
                if signal == Signal.BUY:
                    if z >= 1.5:
                        points += 12
                    elif z >= 0.5:
                        points += 8
                    elif z >= 0:
                        points += 4
                else:
                    if z <= -1.5:
                        points += 12
                    elif z <= -0.5:
                        points += 8
                    elif z <= 0:
                        points += 4

    return min(points, AXIS_MAX)


# ──────────────────────────────────────────────────────────────────────────
# Axis 3 — LOCATION (VWAP position + multi-touch S/R proximity)
# ──────────────────────────────────────────────────────────────────────────
def _score_location(signal: Signal, df: pd.DataFrame) -> float:
    """0..25. Combines VWAP position (0..12) and multi-touch S/R (0..13)."""
    return min(_vwap_location(signal, df) + _sr_location(signal, df), AXIS_MAX)


def _vwap_location(signal: Signal, df: pd.DataFrame) -> float:
    if "vwap" not in df.columns or "close" not in df.columns:
        return 6.0
    close = float(df["close"].iloc[-1])
    vwap = float(df["vwap"].iloc[-1])
    if not np.isfinite(close) or not np.isfinite(vwap) or vwap <= 0:
        return 6.0
    vwap_rising = False
    if len(df) >= 3 and pd.notna(df["vwap"].iloc[-3]):
        vwap_rising = vwap > float(df["vwap"].iloc[-3])
    if signal == Signal.BUY:
        if close > vwap and vwap_rising:
            return 12
        if close > vwap:
            return 9
        if abs(close - vwap) / vwap < 0.002:
            return 6
        return 2
    if signal == Signal.SELL:
        if close < vwap and not vwap_rising:
            return 12
        if close < vwap:
            return 9
        if abs(close - vwap) / vwap < 0.002:
            return 6
        return 2
    return 6


def _sr_location(signal: Signal, df: pd.DataFrame) -> float:
    """Multi-touch swing-pivot clustering with ATR tolerance → 0..13."""
    lookback = min(len(df), 60)
    if lookback < 20:
        return 6
    window = df.iloc[-lookback:]
    close = float(window["close"].iloc[-1])

    if "atr" in window.columns and pd.notna(window["atr"].iloc[-1]):
        tol = float(window["atr"].iloc[-1]) * 0.5
    else:
        tol = close * 0.003

    highs = window["high"].values
    lows = window["low"].values
    n = len(window)

    pivot_highs, pivot_lows = [], []
    for i in range(2, n - 2):
        if (
            highs[i] > highs[i-1] and highs[i] > highs[i-2]
            and highs[i] > highs[i+1] and highs[i] > highs[i+2]
        ):
            pivot_highs.append((i, float(highs[i])))
        if (
            lows[i] < lows[i-1] and lows[i] < lows[i-2]
            and lows[i] < lows[i+1] and lows[i] < lows[i+2]
        ):
            pivot_lows.append((i, float(lows[i])))

    def _cluster(pivots):
        if not pivots:
            return []
        s = sorted(pivots, key=lambda p: p[1])
        clusters = [[s[0]]]
        for idx, px in s[1:]:
            if abs(px - clusters[-1][-1][1]) <= tol:
                clusters[-1].append((idx, px))
            else:
                clusters.append([(idx, px)])
        out = []
        for cl in clusters:
            touches = len(cl)
            avg_px = sum(p[1] for p in cl) / touches
            last_idx = max(p[0] for p in cl)
            recency = last_idx / max(1, n - 1)
            out.append({
                "price": avg_px,
                "touches": touches,
                "strength": touches * (0.5 + 0.5 * recency),
            })
        return out

    res = [c for c in _cluster(pivot_highs) if c["touches"] >= 2]
    sup = [c for c in _cluster(pivot_lows) if c["touches"] >= 2]
    if not res and not sup:
        return 6

    def _near(clusters):
        return min(clusters, key=lambda c: abs(c["price"] - close)) if clusters else None

    near_res = _near(res)
    near_sup = _near(sup)
    near_pct = 0.005

    if signal == Signal.BUY:
        if near_res and close > near_res["price"]:
            return min(13, 8 + int(near_res["strength"]))
        if near_sup and abs(close - near_sup["price"]) / close < near_pct:
            return min(13, 8 + int(near_sup["strength"]))
        if near_res and abs(close - near_res["price"]) / close < near_pct:
            return 3
        return 6
    if signal == Signal.SELL:
        if near_sup and close < near_sup["price"]:
            return min(13, 8 + int(near_sup["strength"]))
        if near_res and abs(close - near_res["price"]) / close < near_pct:
            return min(13, 8 + int(near_res["strength"]))
        if near_sup and abs(close - near_sup["price"]) / close < near_pct:
            return 3
        return 6
    return 6


# ──────────────────────────────────────────────────────────────────────────
# Axis 4 — PARTICIPATION (volume z-score + OBV slope)
# ──────────────────────────────────────────────────────────────────────────
def _score_participation(signal: Signal, df: pd.DataFrame) -> float:
    """0..25. Volume z-score (0..15) + OBV slope direction (0..10)."""
    if "volume" not in df.columns or len(df) < 6:
        return AXIS_MAX / 2

    points = 0.0
    vol = df["volume"].astype(float)
    recent = vol.iloc[-1]
    window = vol.iloc[-21:-1] if len(vol) >= 21 else vol.iloc[:-1]
    mu = window.mean()
    sd = window.std()
    if pd.notna(recent) and sd and sd > 0 and pd.notna(sd):
        z = (recent - mu) / sd
        if z >= 2.0:
            points += 15
        elif z >= 1.0:
            points += 11
        elif z >= 0.3:
            points += 7
        elif z >= -0.3:
            points += 4
        # below -0.3: 0 (weak participation)
    else:
        points += 7  # neutral when undefined

    if "close" in df.columns:
        closes = df["close"].astype(float).values
        vols = vol.values
        if "obv" in df.columns and df["obv"].notna().any():
            obv = df["obv"].astype(float).values
        else:
            obv = np.zeros(len(closes))
            for i in range(1, len(closes)):
                if closes[i] > closes[i-1]:
                    obv[i] = obv[i-1] + vols[i]
                elif closes[i] < closes[i-1]:
                    obv[i] = obv[i-1] - vols[i]
                else:
                    obv[i] = obv[i-1]
        if len(obv) >= 6:
            slope = obv[-1] - obv[-6]
            if signal == Signal.BUY and slope > 0:
                points += 10
            elif signal == Signal.SELL and slope < 0:
                points += 10
            elif slope == 0:
                points += 4


    return min(points, AXIS_MAX)
