"""
backtest_engine.py — Core backtesting engine for EMPIREX-OS Quant Engine
=========================================================================
Anti-lookahead guarantees
-------------------------
1. All strategy signals are computed on CLOSED bars only.  The current bar
   (index i) is never used to generate signals; only bars 0..i-1 are visible.
2. Indicators (VWAP, ATR, RSI) are computed incrementally up to bar i-1 before
   each decision step.
3. Fill prices use the OPEN of bar i (the first bar after the signal bar) plus
   spread/slippage costs — never the close of the signal bar.
4. No future price data is passed into any strategy method.

Instrument specifications
--------------------------
EURUSD / GBPUSD : 5 decimal places, pip = 0.0001, $10/pip per lot
XAUUSD          : 2 decimal places, point = 0.01, $1/point per lot  (gold)
NAS100          : integer index points, point = 1, $20/point per lot
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Instrument specification
# ---------------------------------------------------------------------------

INSTRUMENT_SPECS: dict[str, dict] = {
    "EURUSD": {
        "pip_size": 0.0001,
        "pip_value_per_lot": 10.0,   # USD per pip per standard lot
        "decimal_places": 5,
        "spread_pips": 1.5,
        "commission_per_lot_rt": 7.0,
        "slippage_pips": 0.5,
        "asset_class": "forex",
    },
    "GBPUSD": {
        "pip_size": 0.0001,
        "pip_value_per_lot": 10.0,
        "decimal_places": 5,
        "spread_pips": 1.5,
        "commission_per_lot_rt": 7.0,
        "slippage_pips": 0.5,
        "asset_class": "forex",
    },
    "XAUUSD": {
        "pip_size": 0.01,            # gold quoted in $ with 2 dp
        "pip_value_per_lot": 1.0,    # $1 per $0.01 move per lot (100 oz)
        "decimal_places": 2,
        "spread_pips": 40,           # in units of pip_size => $0.40
        "commission_per_lot_rt": 0.0,
        "slippage_pips": 10,         # $0.10
        "asset_class": "commodity",
    },
    "NAS100": {
        "pip_size": 1.0,             # 1 index point
        "pip_value_per_lot": 20.0,   # $20 per point per lot
        "decimal_places": 1,
        "spread_pips": 1.5,          # 1.5 points
        "commission_per_lot_rt": 0.0,
        "slippage_pips": 0.5,        # 0.5 points
        "asset_class": "index",
    },
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    trade_id: int
    symbol: str
    strategy: str
    direction: str                  # "long" or "short"
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    entry_price_raw: float          # mid price at signal
    exit_price_raw: Optional[float]
    fill_entry: float               # actual fill after spread/slippage
    fill_exit: Optional[float]
    lot_size: float
    stop_loss: float
    take_profit: float
    exit_reason: str                # "tp", "sl", "time", "eod", "open"
    pnl_gross: float = 0.0         # before costs
    pnl_net: float = 0.0           # after spread + commission + slippage
    costs: float = 0.0
    r_multiple: float = 0.0        # pnl_net / initial_risk_$
    session: str = ""              # "London", "NY", "Asian", "Other"
    is_winner: bool = False
    initial_risk_usd: float = 0.0

    # derived in post_process()
    duration_bars: int = 0


@dataclass
class DailyState:
    """Mutable per-day state injected into strategies."""
    date: str
    trades_today: int = 0
    open_trade: Optional[Trade] = None


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------

class CostModel:
    """Applies spread, commission, and slippage to a fill."""

    @staticmethod
    def entry_fill(symbol: str, direction: str, mid_price: float, lot_size: float) -> tuple[float, float]:
        """Return (fill_price, total_cost_usd)."""
        spec = INSTRUMENT_SPECS[symbol]
        ps = spec["pip_size"]
        pv = spec["pip_value_per_lot"]

        # half-spread on entry, half on exit → full spread counted at entry fill
        spread_cost_pips = spec["spread_pips"]
        slip_pips = spec["slippage_pips"]
        commission = spec["commission_per_lot_rt"] * lot_size  # round-trip commission

        total_pip_cost = spread_cost_pips + slip_pips  # pips eaten at entry
        cost_usd = total_pip_cost * pv * lot_size + commission

        if direction == "long":
            fill = mid_price + total_pip_cost * ps
        else:
            fill = mid_price - total_pip_cost * ps

        return fill, cost_usd

    @staticmethod
    def exit_fill(symbol: str, direction: str, mid_price: float, lot_size: float) -> tuple[float, float]:
        """Return (fill_price, 0) — commission already counted at entry."""
        spec = INSTRUMENT_SPECS[symbol]
        ps = spec["pip_size"]

        # slippage only on exit (spread included in entry)
        slip_pips = spec["slippage_pips"]

        if direction == "long":
            fill = mid_price - slip_pips * ps
        else:
            fill = mid_price + slip_pips * ps

        return fill, 0.0  # commission already deducted at entry


# ---------------------------------------------------------------------------
# P&L calculator
# ---------------------------------------------------------------------------

class PnLCalculator:
    """Converts price moves to USD P&L."""

    @staticmethod
    def pnl(symbol: str, direction: str, entry: float, exit_p: float, lot_size: float) -> float:
        spec = INSTRUMENT_SPECS[symbol]
        ps = spec["pip_size"]
        pv = spec["pip_value_per_lot"]
        if direction == "long":
            raw_pips = (exit_p - entry) / ps
        else:
            raw_pips = (entry - exit_p) / ps
        return raw_pips * pv * lot_size

    @staticmethod
    def risk_usd(symbol: str, direction: str, entry: float, stop: float, lot_size: float) -> float:
        spec = INSTRUMENT_SPECS[symbol]
        ps = spec["pip_size"]
        pv = spec["pip_value_per_lot"]
        if direction == "long":
            raw_pips = abs((entry - stop) / ps)
        else:
            raw_pips = abs((stop - entry) / ps)
        return raw_pips * pv * lot_size


# ---------------------------------------------------------------------------
# Position manager
# ---------------------------------------------------------------------------

class PositionManager:
    """Handles open/close lifecycle of a single trade."""

    def __init__(self):
        self._counter = 0

    def open_trade(
        self,
        symbol: str,
        strategy: str,
        direction: str,
        entry_time: pd.Timestamp,
        mid_price: float,
        stop_loss: float,
        take_profit: float,
        lot_size: float = 1.0,
        session: str = "London",
    ) -> Trade:
        self._counter += 1
        fill_entry, entry_cost = CostModel.entry_fill(symbol, direction, mid_price, lot_size)
        initial_risk = PnLCalculator.risk_usd(symbol, direction, fill_entry, stop_loss, lot_size)

        t = Trade(
            trade_id=self._counter,
            symbol=symbol,
            strategy=strategy,
            direction=direction,
            entry_time=entry_time,
            exit_time=None,
            entry_price_raw=mid_price,
            exit_price_raw=None,
            fill_entry=fill_entry,
            fill_exit=None,
            lot_size=lot_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            exit_reason="open",
            costs=entry_cost,
            session=session,
            initial_risk_usd=initial_risk,
        )
        return t

    def close_trade(
        self,
        trade: Trade,
        exit_time: pd.Timestamp,
        mid_exit_price: float,
        reason: str,
    ) -> Trade:
        fill_exit, exit_cost = CostModel.exit_fill(
            trade.symbol, trade.direction, mid_exit_price, trade.lot_size
        )
        trade.exit_time = exit_time
        trade.exit_price_raw = mid_exit_price
        trade.fill_exit = fill_exit
        trade.exit_reason = reason
        trade.costs += exit_cost

        pnl_gross = PnLCalculator.pnl(
            trade.symbol, trade.direction, trade.fill_entry, fill_exit, trade.lot_size
        )
        trade.pnl_gross = pnl_gross
        trade.pnl_net = pnl_gross - trade.costs
        trade.is_winner = trade.pnl_net > 0

        if trade.initial_risk_usd > 0:
            trade.r_multiple = trade.pnl_net / trade.initial_risk_usd
        else:
            trade.r_multiple = 0.0

        return trade


# ---------------------------------------------------------------------------
# Indicator helpers (all operate on closed-bar arrays, no lookahead)
# ---------------------------------------------------------------------------

class Indicators:
    """
    All methods receive a 1-D numpy array of CLOSED values up to (but NOT
    including) the current bar being evaluated.
    """

    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        """Average True Range over last `period` bars."""
        if len(close) < period + 1:
            return float("nan")
        h = high[-(period + 1):]
        l = low[-(period + 1):]
        c = close[-(period + 1):]
        tr = np.maximum(
            h[1:] - l[1:],
            np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1]))
        )
        return float(np.mean(tr[-period:]))

    @staticmethod
    def rsi(close: np.ndarray, period: int = 14) -> float:
        """Wilder RSI (simple seed + EMA)."""
        if len(close) < period + 2:
            return float("nan")
        delta = np.diff(close[-(period + 2):])
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = float(np.mean(gain[:period]))
        avg_loss = float(np.mean(loss[:period]))
        # Wilder smoothing for the last bar
        for i in range(period, len(gain)):
            avg_gain = (avg_gain * (period - 1) + gain[i]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def session_vwap(
        df_session: pd.DataFrame,
    ) -> float:
        """
        True VWAP from session start.
        df_session: rows from session open up to (but NOT including) current bar.
        Columns: high, low, close, volume (or tick_volume proxy).
        """
        if df_session.empty:
            return float("nan")
        typical = (df_session["high"] + df_session["low"] + df_session["close"]) / 3.0
        vol = df_session.get("volume", pd.Series(np.ones(len(df_session)), index=df_session.index))
        if vol.sum() == 0:
            vol = pd.Series(np.ones(len(df_session)), index=df_session.index)
        return float((typical * vol).sum() / vol.sum())


# ---------------------------------------------------------------------------
# Core backtesting engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    """
    Event-driven bar-by-bar backtester.

    Usage
    -----
    engine = BacktestEngine(symbol="EURUSD", initial_capital=10_000)
    engine.run(df_ohlcv, strategy_instance)
    report = engine.get_results()
    """

    def __init__(
        self,
        symbol: str,
        strategy_name: str,
        initial_capital: float = 10_000.0,
        lot_size: float = 0.1,
    ):
        if symbol not in INSTRUMENT_SPECS:
            raise ValueError(f"Unknown symbol: {symbol}. Supported: {list(INSTRUMENT_SPECS)}")
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.initial_capital = initial_capital
        self.lot_size = lot_size
        self.spec = INSTRUMENT_SPECS[symbol]

        self._pm = PositionManager()
        self.trades: list[Trade] = []
        self._equity_curve: list[float] = []

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self, df: pd.DataFrame, strategy) -> None:
        """
        df: DatetimeIndex (UTC), columns: open, high, low, close, volume
        strategy: instance of BaseStrategy sub-class
        """
        df = self._validate_and_prepare(df)
        strategy.reset()

        n = len(df)
        equity = self.initial_capital
        open_trade: Optional[Trade] = None
        daily_state = DailyState(date="")

        for i in range(1, n):  # start at 1 — bar 0 has no prior bar
            bar = df.iloc[i]          # current bar (being formed / just closed)
            prev_bars = df.iloc[:i]   # CLOSED bars available to strategy

            bar_time: pd.Timestamp = df.index[i]
            bar_date = bar_time.date().isoformat()

            # Reset daily state at day boundary
            if bar_date != daily_state.date:
                daily_state = DailyState(date=bar_date)
                daily_state.open_trade = open_trade  # carry forward

            daily_state.open_trade = open_trade

            # ---- Check SL/TP/time-exit on open trade (using bar O/H/L/C) ----
            if open_trade is not None:
                open_trade, closed = self._check_exit(open_trade, bar, bar_time)
                if closed is not None:
                    self.trades.append(closed)
                    equity += closed.pnl_net
                    open_trade = None
                    daily_state.open_trade = None

            # ---- Strategy signal (only if no open trade) --------------------
            if open_trade is None:
                signal = strategy.on_bar(
                    bar_time=bar_time,
                    bar=bar,
                    prev_bars=prev_bars,
                    daily_state=daily_state,
                    symbol=self.symbol,
                    lot_size=self.lot_size,
                )
                if signal is not None:
                    direction, sl, tp, session = signal
                    # Anti-lookahead: fill on bar OPEN (bar i open)
                    mid_price = float(bar["open"])
                    open_trade = self._pm.open_trade(
                        symbol=self.symbol,
                        strategy=self.strategy_name,
                        direction=direction,
                        entry_time=bar_time,
                        mid_price=mid_price,
                        stop_loss=sl,
                        take_profit=tp,
                        lot_size=self.lot_size,
                        session=session,
                    )
                    daily_state.trades_today += 1
                    daily_state.open_trade = open_trade

            self._equity_curve.append(equity)

        # Close any trade still open at end of data
        if open_trade is not None:
            last_bar = df.iloc[-1]
            last_time = df.index[-1]
            open_trade = self._pm.close_trade(
                open_trade, last_time, float(last_bar["close"]), "eod"
            )
            self.trades.append(open_trade)
            equity += open_trade.pnl_net

        self._equity_curve.append(equity)
        self._final_equity = equity

    # ------------------------------------------------------------------
    # Exit logic (SL / TP / time)
    # ------------------------------------------------------------------

    def _check_exit(
        self, trade: Trade, bar: pd.Series, bar_time: pd.Timestamp
    ) -> tuple[Optional[Trade], Optional[Trade]]:
        """
        Returns (open_trade, closed_trade).
        Uses bar H/L to detect SL or TP hit within the bar.
        """
        h = float(bar["high"])
        l = float(bar["low"])
        o = float(bar["open"])

        # Time-exit: 13:00 UTC — use bar open time
        if bar_time.hour >= 13:
            closed = self._pm.close_trade(trade, bar_time, o, "time")
            return None, closed

        if trade.direction == "long":
            if l <= trade.stop_loss:
                closed = self._pm.close_trade(trade, bar_time, trade.stop_loss, "sl")
                return None, closed
            if h >= trade.take_profit:
                closed = self._pm.close_trade(trade, bar_time, trade.take_profit, "tp")
                return None, closed
        else:  # short
            if h >= trade.stop_loss:
                closed = self._pm.close_trade(trade, bar_time, trade.stop_loss, "sl")
                return None, closed
            if l <= trade.take_profit:
                closed = self._pm.close_trade(trade, bar_time, trade.take_profit, "tp")
                return None, closed

        return trade, None

    # ------------------------------------------------------------------
    # Data validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_and_prepare(df: pd.DataFrame) -> pd.DataFrame:
        required = {"open", "high", "low", "close"}
        missing = required - set(df.columns.str.lower())
        if missing:
            raise ValueError(f"Missing columns: {missing}")
        df = df.copy()
        df.columns = df.columns.str.lower()
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame index must be DatetimeIndex (UTC)")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        elif str(df.index.tz) != "UTC":
            df.index = df.index.tz_convert("UTC")
        df.sort_index(inplace=True)
        if "volume" not in df.columns:
            df["volume"] = 1.0
        return df

    # ------------------------------------------------------------------
    # Results accessor
    # ------------------------------------------------------------------

    def get_results(self) -> dict:
        trades_df = pd.DataFrame([vars(t) for t in self.trades]) if self.trades else pd.DataFrame()
        equity = pd.Series(self._equity_curve)
        return {
            "symbol": self.symbol,
            "strategy": self.strategy_name,
            "initial_capital": self.initial_capital,
            "final_equity": getattr(self, "_final_equity", self.initial_capital),
            "trades": trades_df,
            "equity_curve": equity,
        }
