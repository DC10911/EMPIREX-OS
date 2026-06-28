"""
strategies.py — Trading strategy implementations for EMPIREX-OS Quant Engine
=============================================================================

All strategies inherit from BaseStrategy and implement on_bar().

Anti-lookahead contract
-----------------------
- on_bar() receives `prev_bars`: a slice of the DataFrame containing only
  CLOSED bars up to (but NOT including) the current bar.
- The current bar's OPEN is the earliest price available for fills.
- Signals may only reference prev_bars[-1] and earlier.
- No peeking at current bar high/low/close for signal generation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
import pandas as pd

from backtest_engine import DailyState, Indicators


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class BaseStrategy(ABC):
    """
    Interface all strategies must implement.

    on_bar() return value
    ----------------------
    None  → no trade
    (direction, stop_loss, take_profit, session) → open a trade
        direction : "long" | "short"
        stop_loss : float (price)
        take_profit : float (price)
        session   : "London" | "NY" | "Asian" | "Other"
    """

    name: str = "BaseStrategy"

    def reset(self) -> None:
        """Called once before a backtest run begins."""
        pass

    @abstractmethod
    def on_bar(
        self,
        bar_time: pd.Timestamp,
        bar: pd.Series,
        prev_bars: pd.DataFrame,
        daily_state: DailyState,
        symbol: str,
        lot_size: float,
    ) -> Optional[tuple[str, float, float, str]]:
        ...


# ---------------------------------------------------------------------------
# Strategy 1 — London Range Breakout (LRB)  [BENCHMARK]
# ---------------------------------------------------------------------------

class LRBStrategy(BaseStrategy):
    """
    London Range Breakout — benchmark strategy.

    Pre-London range defined as the highest high and lowest low between
    06:00–08:00 UTC on 1H bars.  A breakout above/below that range after
    08:00 UTC triggers an entry at the breakout level.

    Rules
    -----
    - Range window : 06:00 UTC (inclusive) to 08:00 UTC (exclusive)
    - Entry window : 08:00 UTC to 12:59 UTC
    - Stop         : Opposite side of range
    - Target       : Entry ± range_size × 1.5
    - Time exit    : 13:00 UTC (handled by engine)
    - Max 2 trades per day; first breakout direction only per day
    - Uses closed bar signal bar, fills on next bar open
    """

    name = "LRB"
    MAX_TRADES_PER_DAY = 2

    def __init__(self, range_multiplier: float = 1.5):
        self.range_multiplier = range_multiplier
        self._day_cache: dict = {}   # date string → {range_high, range_low, direction_taken}

    def reset(self) -> None:
        self._day_cache = {}

    def on_bar(
        self,
        bar_time: pd.Timestamp,
        bar: pd.Series,
        prev_bars: pd.DataFrame,
        daily_state: DailyState,
        symbol: str,
        lot_size: float,
    ) -> Optional[tuple[str, float, float, str]]:

        # Only trade in entry window
        if not (8 <= bar_time.hour < 13):
            return None

        # Max trades per day guard
        if daily_state.trades_today >= self.MAX_TRADES_PER_DAY:
            return None

        date_str = bar_time.date().isoformat()

        # ---- Compute or retrieve pre-London range ----
        if date_str not in self._day_cache:
            rng = self._compute_range(prev_bars, date_str)
            if rng is None:
                return None
            self._day_cache[date_str] = {
                "range_high": rng[0],
                "range_low": rng[1],
                "direction_taken": None,  # first breakout direction only
            }

        cache = self._day_cache[date_str]
        rh = cache["range_high"]
        rl = cache["range_low"]

        if rh is None or rl is None or math.isnan(rh) or math.isnan(rl):
            return None

        range_size = rh - rl
        if range_size <= 0:
            return None

        # Use the PREVIOUS closed bar's close for the breakout check
        # (anti-lookahead: prev_bars[-1] is the bar just closed before current)
        prev_close = float(prev_bars["close"].iloc[-1])

        direction = None
        if prev_close > rh and cache["direction_taken"] is None:
            direction = "long"
        elif prev_close < rl and cache["direction_taken"] is None:
            direction = "short"

        if direction is None:
            return None

        # Mark direction taken (first breakout only)
        cache["direction_taken"] = direction

        if direction == "long":
            sl = rl
            tp = rh + range_size * self.range_multiplier
        else:
            sl = rh
            tp = rl - range_size * self.range_multiplier

        return direction, sl, tp, "London"

    # ---- helpers ----

    @staticmethod
    def _compute_range(prev_bars: pd.DataFrame, date_str: str) -> Optional[tuple[float, float]]:
        """
        Extract high/low of the 06:00–08:00 UTC window from previous bars.
        Returns (range_high, range_low) or None if insufficient data.
        """
        today = pd.Timestamp(date_str, tz="UTC")
        window_start = today.replace(hour=6, minute=0)
        window_end = today.replace(hour=8, minute=0)

        mask = (prev_bars.index >= window_start) & (prev_bars.index < window_end)
        window = prev_bars[mask]

        if window.empty:
            return None

        return float(window["high"].max()), float(window["low"].min())


import math  # moved here to avoid top-level circular; also needed above


# ---------------------------------------------------------------------------
# Strategy 2 — EMP Session Momentum  [ORIGINAL]
# ---------------------------------------------------------------------------

class EMPSessionMomentumStrategy(BaseStrategy):
    """
    EMP Session Momentum — original EMPIREX strategy.

    Uses session VWAP (from 08:00 UTC) + ATR bands + RSI filter.

    Rules
    -----
    - Session VWAP recalculates from 08:00 UTC each day
    - ATR(14) bands: VWAP ± ATR × 1.2
    - Long  : price crosses VWAP from below, RSI(14) > 50, 08:00–12:59 UTC
    - Short : price crosses VWAP from above, RSI(14) < 50, 08:00–12:59 UTC
    - SL    : ATR × 1.5
    - TP    : ATR × 2.5
    - Time exit: 13:00 UTC (handled by engine)
    - Max 2 trades per day
    """

    name = "EMPSessionMomentum"
    MAX_TRADES_PER_DAY = 2
    ATR_PERIOD = 14
    RSI_PERIOD = 14
    ATR_BAND_MULT = 1.2
    SL_MULT = 1.5
    TP_MULT = 2.5
    RSI_LONG_THRESHOLD = 50.0
    RSI_SHORT_THRESHOLD = 50.0

    def reset(self) -> None:
        self._prev_above_vwap: dict[str, Optional[bool]] = {}  # date → bool

    def on_bar(
        self,
        bar_time: pd.Timestamp,
        bar: pd.Series,
        prev_bars: pd.DataFrame,
        daily_state: DailyState,
        symbol: str,
        lot_size: float,
    ) -> Optional[tuple[str, float, float, str]]:

        # Only trade in London session entry window
        if not (8 <= bar_time.hour < 13):
            return None

        if daily_state.trades_today >= self.MAX_TRADES_PER_DAY:
            return None

        if len(prev_bars) < self.ATR_PERIOD + 2:
            return None

        date_str = bar_time.date().isoformat()

        # ---- Session VWAP (08:00 UTC today, using closed bars only) ----
        today = pd.Timestamp(date_str, tz="UTC")
        session_start = today.replace(hour=8, minute=0)
        session_bars = prev_bars[prev_bars.index >= session_start]

        if session_bars.empty:
            return None

        vwap = Indicators.session_vwap(session_bars)
        if math.isnan(vwap):
            return None

        # ---- ATR from all prev bars ----
        atr = Indicators.atr(
            prev_bars["high"].values,
            prev_bars["low"].values,
            prev_bars["close"].values,
            period=self.ATR_PERIOD,
        )
        if math.isnan(atr) or atr <= 0:
            return None

        # ---- RSI from all prev bars ----
        rsi = Indicators.rsi(prev_bars["close"].values, period=self.RSI_PERIOD)
        if math.isnan(rsi):
            return None

        # ---- Crossover detection (anti-lookahead) ----
        # Use prev_bars[-1] (signal bar close) vs prev_bars[-2] close
        cur_close = float(prev_bars["close"].iloc[-1])
        prev_close = float(prev_bars["close"].iloc[-2]) if len(prev_bars) >= 2 else cur_close

        cur_above = cur_close > vwap
        prev_above = prev_close > vwap

        # Store per-day cross state
        if date_str not in self._prev_above_vwap:
            self._prev_above_vwap[date_str] = prev_above

        direction = None

        # Long cross: was below VWAP, now above → price crossed from below
        if not prev_above and cur_above and rsi > self.RSI_LONG_THRESHOLD:
            direction = "long"
        # Short cross: was above VWAP, now below → price crossed from above
        elif prev_above and not cur_above and rsi < self.RSI_SHORT_THRESHOLD:
            direction = "short"

        self._prev_above_vwap[date_str] = cur_above

        if direction is None:
            return None

        # ---- SL / TP ----
        entry_mid = float(bar["open"])  # indicative for SL/TP calc; fill on open

        if direction == "long":
            sl = entry_mid - atr * self.SL_MULT
            tp = entry_mid + atr * self.TP_MULT
        else:
            sl = entry_mid + atr * self.SL_MULT
            tp = entry_mid - atr * self.TP_MULT

        return direction, sl, tp, "London"
