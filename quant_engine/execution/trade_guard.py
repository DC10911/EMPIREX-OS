"""
trade_guard.py
--------------
Business-rule enforcement layer for EMPIREX-OS.

All trading constraints are evaluated HERE before any order touches MT5.

Rules enforced:
  1. Maximum 2 trades per day (hard limit, resets at 00:00 UTC).
  2. No duplicate position in same symbol + same direction (no averaging down).
  3. No martingale: reject if a previous trade in the same direction on the
     same symbol is still open AND in a losing state.
  4. Stop-loss REQUIRED on every order.
  5. Lot size FIXED at 1.0 (any other value is rejected).
  6. Kill switch: halt all trading when daily drawdown > $1,000.

Daily state is persisted to a JSON file (TRADE_GUARD_STATE_FILE env var,
default: /tmp/empirex_trade_guard_state.json) so that server restarts
within the same UTC day do not reset the counters.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_STATE_FILE = Path(
    os.environ.get(
        "TRADE_GUARD_STATE_FILE",
        "/home/user/EMPIREX-OS/quant_engine/execution/trade_guard_state.json",
    )
)

MAX_DAILY_TRADES: int = int(os.environ.get("MAX_DAILY_TRADES", "2"))
FIXED_LOT_SIZE: float = float(os.environ.get("FIXED_LOT_SIZE", "1.0"))
MAX_DAILY_DRAWDOWN_USD: float = float(os.environ.get("MAX_DAILY_DRAWDOWN_USD", "1000.0"))

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Returned by TradeGuard.validate_order()."""
    allowed: bool
    reason: str = ""


@dataclass
class DailyState:
    """Persisted daily counters — reset when the UTC date changes."""
    date_utc: str = ""                   # "YYYY-MM-DD"
    trade_count: int = 0
    kill_switch_active: bool = False
    kill_switch_reason: str = ""
    cumulative_realized_pnl: float = 0.0  # updated externally by webhook_server
    filled_tickets: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TradeGuard
# ---------------------------------------------------------------------------


class TradeGuard:
    """
    Stateful gate that enforces all EMPIREX business rules.

    Parameters
    ----------
    state_file : Path
        JSON file used to persist daily counters across server restarts.
    executor : OrderExecutor | None
        Live MT5 executor used to query open positions and P&L.
        If None, position-based checks are skipped (useful for unit tests).
    """

    def __init__(
        self,
        state_file: Path = DEFAULT_STATE_FILE,
        executor=None,
    ) -> None:
        self._state_file = state_file
        self._executor = executor
        self._state: DailyState = self._load_state()

    # ------------------------------------------------------------------
    # Public checks
    # ------------------------------------------------------------------

    def check_daily_limit(self) -> bool:
        """
        Return True if another trade is permitted today.
        False means the daily limit has been reached.
        """
        self._refresh_state_date()
        allowed = self._state.trade_count < MAX_DAILY_TRADES
        if not allowed:
            logger.warning(
                "Daily limit reached: %d/%d trades used today.",
                self._state.trade_count, MAX_DAILY_TRADES,
            )
        return allowed

    def check_no_duplicate_position(self, symbol: str, direction: str) -> bool:
        """
        Return True if there is NO existing open position in the same
        symbol + direction combination (no averaging down).
        """
        if self._executor is None:
            return True  # cannot check without live connection

        positions = self._executor.get_open_positions(symbol=symbol)
        for pos in positions:
            if pos.direction == direction:
                logger.warning(
                    "Duplicate position rejected: symbol=%s direction=%s ticket=%s",
                    symbol, direction, pos.ticket,
                )
                return False
        return True

    def check_no_martingale(self, symbol: str, direction: str) -> bool:
        """
        Return True if no open position in the same symbol + direction is
        currently at a loss (anti-martingale rule).
        """
        if self._executor is None:
            return True

        positions = self._executor.get_open_positions(symbol=symbol)
        for pos in positions:
            if pos.direction == direction and pos.profit < 0:
                logger.warning(
                    "Martingale rejected: open position ticket=%s profit=%.2f is losing.",
                    pos.ticket, pos.profit,
                )
                return False
        return True

    def check_kill_switch(self) -> bool:
        """
        Return True if trading is permitted (kill switch is NOT active).
        Automatically activates the kill switch if daily drawdown > threshold.
        """
        self._refresh_state_date()

        if self._state.kill_switch_active:
            logger.error(
                "Kill switch ACTIVE: %s — trading halted.",
                self._state.kill_switch_reason,
            )
            return False

        # Live P&L check
        if self._executor is not None:
            daily_pnl = self._executor.get_daily_pnl()
            if daily_pnl < -MAX_DAILY_DRAWDOWN_USD:
                reason = (
                    f"Daily drawdown ${abs(daily_pnl):.2f} exceeded "
                    f"limit ${MAX_DAILY_DRAWDOWN_USD:.2f}"
                )
                self._activate_kill_switch(reason)
                return False

        return True

    # ------------------------------------------------------------------
    # Master validation
    # ------------------------------------------------------------------

    def validate_order(self, order: dict) -> ValidationResult:
        """
        Run all business-rule checks against an incoming order dict.

        Expected keys: symbol, action (buy/sell), sl, tp, lots, price.

        Returns ValidationResult(allowed=True) if everything passes,
        or ValidationResult(allowed=False, reason=<why>) on first failure.
        """
        # --- 0. Kill switch first ---
        if not self.check_kill_switch():
            reason = self._state.kill_switch_reason or "Kill switch active"
            return ValidationResult(allowed=False, reason=f"KILL_SWITCH: {reason}")

        # --- 1. Daily limit ---
        if not self.check_daily_limit():
            return ValidationResult(
                allowed=False,
                reason=f"DAILY_LIMIT: {self._state.trade_count}/{MAX_DAILY_TRADES} trades used today",
            )

        # --- 2. Required fields ---
        required = ("symbol", "action", "sl", "tp", "lots")
        for key in required:
            if key not in order or order[key] is None:
                return ValidationResult(allowed=False, reason=f"MISSING_FIELD: {key} is required")

        symbol: str = str(order["symbol"]).upper()
        direction: str = str(order["action"]).lower()
        sl = order.get("sl")
        lots = order.get("lots")

        # --- 3. Direction validation ---
        if direction not in ("buy", "sell"):
            return ValidationResult(
                allowed=False, reason=f"INVALID_ACTION: must be 'buy' or 'sell', got {direction!r}"
            )

        # --- 4. Stop-loss required ---
        try:
            sl_val = float(sl)
        except (TypeError, ValueError):
            return ValidationResult(allowed=False, reason="MISSING_SL: stop_loss must be a valid number")

        if sl_val <= 0:
            return ValidationResult(allowed=False, reason="INVALID_SL: stop_loss must be > 0")

        # --- 5. Fixed lot size ---
        try:
            lots_val = float(lots)
        except (TypeError, ValueError):
            return ValidationResult(allowed=False, reason="INVALID_LOTS: lots must be a number")

        if abs(lots_val - FIXED_LOT_SIZE) > 1e-6:
            return ValidationResult(
                allowed=False,
                reason=f"INVALID_LOTS: only {FIXED_LOT_SIZE} lot(s) allowed, got {lots_val}",
            )

        # --- 6. No duplicate position (averaging down) ---
        if not self.check_no_duplicate_position(symbol, direction):
            return ValidationResult(
                allowed=False,
                reason=f"DUPLICATE_POSITION: already have open {direction} on {symbol}",
            )

        # --- 7. No martingale ---
        if not self.check_no_martingale(symbol, direction):
            return ValidationResult(
                allowed=False,
                reason=f"MARTINGALE_BLOCKED: existing {direction} position on {symbol} is losing",
            )

        return ValidationResult(allowed=True, reason="All checks passed")

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def record_trade(self, ticket: Optional[int] = None) -> None:
        """Increment the daily trade counter. Call after a successful order."""
        self._refresh_state_date()
        self._state.trade_count += 1
        if ticket is not None:
            self._state.filled_tickets.append(ticket)
        logger.info(
            "Trade recorded: daily_count=%d ticket=%s",
            self._state.trade_count, ticket,
        )
        self._save_state()

    def update_daily_pnl(self, pnl: float) -> None:
        """
        Update the cached realised P&L.  The kill-switch check uses the
        live MT5 value; this is kept for informational logging.
        """
        self._refresh_state_date()
        self._state.cumulative_realized_pnl = pnl
        self._save_state()

    def activate_kill_switch(self, reason: str) -> None:
        """Externally activate the kill switch (e.g. from a manual API call)."""
        self._activate_kill_switch(reason)

    def deactivate_kill_switch(self) -> None:
        """Reset the kill switch (e.g. at start of new day or manual override)."""
        self._refresh_state_date()
        self._state.kill_switch_active = False
        self._state.kill_switch_reason = ""
        logger.warning("Kill switch deactivated.")
        self._save_state()

    @property
    def daily_state(self) -> DailyState:
        self._refresh_state_date()
        return self._state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _today_utc(self) -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    def _refresh_state_date(self) -> None:
        """Reset daily counters when the UTC date has rolled over."""
        today = self._today_utc()
        if self._state.date_utc != today:
            if self._state.date_utc:
                logger.info(
                    "UTC day changed from %s to %s — resetting daily state.",
                    self._state.date_utc, today,
                )
            self._state = DailyState(date_utc=today)
            self._save_state()

    def _activate_kill_switch(self, reason: str) -> None:
        self._state.kill_switch_active = True
        self._state.kill_switch_reason = reason
        logger.error("Kill switch ACTIVATED: %s", reason)
        self._save_state()

        # Attempt to close all open positions
        if self._executor is not None:
            logger.warning("Kill switch: closing all open positions.")
            results = self._executor.close_all_positions()
            for r in results:
                if r.success:
                    logger.info("Closed position ticket=%s", r.ticket)
                else:
                    logger.error("Failed to close position: %s", r.error)

    def _load_state(self) -> DailyState:
        """Load persisted state from disk, or return fresh state."""
        today = self._today_utc()
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                if data.get("date_utc") == today:
                    logger.info("Loaded today's trade guard state from %s", self._state_file)
                    return DailyState(
                        date_utc=data["date_utc"],
                        trade_count=int(data.get("trade_count", 0)),
                        kill_switch_active=bool(data.get("kill_switch_active", False)),
                        kill_switch_reason=str(data.get("kill_switch_reason", "")),
                        cumulative_realized_pnl=float(data.get("cumulative_realized_pnl", 0.0)),
                        filled_tickets=list(data.get("filled_tickets", [])),
                    )
                else:
                    logger.info(
                        "State file date (%s) differs from today (%s); starting fresh.",
                        data.get("date_utc"), today,
                    )
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Could not parse state file: %s; starting fresh.", exc)

        return DailyState(date_utc=today)

    def _save_state(self) -> None:
        """Persist current daily state to disk."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(asdict(self._state), indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to persist trade guard state: %s", exc)
