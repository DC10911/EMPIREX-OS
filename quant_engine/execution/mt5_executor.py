"""
mt5_executor.py
---------------
MetaTrader 5 execution layer for EMPIREX-OS.

Provides:
  - MT5Connection  : manages the MT5 terminal session
  - OrderExecutor  : places, monitors, and closes orders with full error handling
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# MetaTrader5 is a Windows-only package; guard the import so tests can run
# on non-Windows environments by mocking it.
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:  # pragma: no cover
    mt5 = None  # type: ignore[assignment]
    MT5_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES: int = 3
RETRY_DELAY_S: float = 0.5  # 500 ms between retries

# Broker symbol map: TradingView name → list of possible broker suffixes.
SYMBOL_MAP: dict[str, list[str]] = {
    "EURUSD": ["EURUSD", "EURUSDm", "EURUSD."],
    "GBPUSD": ["GBPUSD", "GBPUSDm", "GBPUSD."],
    "XAUUSD": ["XAUUSD", "GOLDm", "GOLD", "XAUUSD."],
    "NAS100": ["NAS100", "US100", "USTEC", "NAS100m", "NDX"],
    "GBPJPY": ["GBPJPY", "GBPJPYm", "GBPJPY."],
    "USDJPY": ["USDJPY", "USDJPYm", "USDJPY."],
}

# MT5 order-type constants (duplicated here so code is importable without MT5)
_ORDER_TYPE_BUY = 0
_ORDER_TYPE_SELL = 1

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: str          # "buy" | "sell"
    lots: float
    open_price: float
    current_price: float
    sl: float
    tp: float
    profit: float
    open_time: datetime
    comment: str


@dataclass
class OrderResult:
    success: bool
    ticket: Optional[int] = None
    retcode: Optional[int] = None
    comment: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# MT5Connection
# ---------------------------------------------------------------------------


class MT5Connection:
    """
    Manages the lifecycle of the MT5 terminal connection.

    Configuration is read from environment variables:
        MT5_LOGIN    – account number (integer)
        MT5_PASSWORD – account password
        MT5_SERVER   – broker server name
        MT5_PATH     – optional path to terminal64.exe
    """

    def __init__(self) -> None:
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Open (or verify) an MT5 terminal connection. Returns True on success."""
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 package not available on this platform.")
            return False

        if self._connected and mt5.terminal_info() is not None:
            return True

        login = int(os.environ.get("MT5_LOGIN", "0"))
        password = os.environ.get("MT5_PASSWORD", "")
        server = os.environ.get("MT5_SERVER", "")
        path = os.environ.get("MT5_PATH", "")  # empty → auto-detect

        init_kwargs: dict = {}
        if path:
            init_kwargs["path"] = path
        if login:
            init_kwargs["login"] = login
        if password:
            init_kwargs["password"] = password
        if server:
            init_kwargs["server"] = server

        if not mt5.initialize(**init_kwargs):
            err = mt5.last_error()
            logger.error("MT5 initialize failed: %s", err)
            return False

        info = mt5.account_info()
        if info is None:
            logger.error("MT5 account_info() returned None after initialize.")
            mt5.shutdown()
            return False

        self._connected = True
        logger.info(
            "MT5 connected: account=%s server=%s balance=%.2f",
            info.login,
            info.server,
            info.balance,
        )
        return True

    def disconnect(self) -> None:
        """Gracefully shut down the MT5 connection."""
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 disconnected.")

    @property
    def is_connected(self) -> bool:
        return self._connected and MT5_AVAILABLE and mt5.terminal_info() is not None

    def ensure_connected(self) -> bool:
        """Re-connect if the terminal dropped."""
        if self.is_connected:
            return True
        logger.warning("MT5 connection lost – attempting reconnect.")
        return self.connect()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "MT5Connection":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_broker_symbol(symbol: str) -> Optional[str]:
    """
    Translate a canonical symbol name to the broker's actual symbol name.
    Tries each candidate in the SYMBOL_MAP; returns the first one found in
    MT5's symbol list.  Falls back to the raw symbol if not in the map.
    """
    if not MT5_AVAILABLE:
        return symbol

    candidates = SYMBOL_MAP.get(symbol, [symbol])
    for candidate in candidates:
        info = mt5.symbol_info(candidate)
        if info is not None:
            # Enable the symbol in MarketWatch if not already visible
            if not info.visible:
                mt5.symbol_select(candidate, True)
            return candidate

    logger.error("Symbol '%s' not found under any known broker alias.", symbol)
    return None


def _mt5_position_to_dataclass(pos) -> Position:
    direction = "buy" if pos.type == _ORDER_TYPE_BUY else "sell"
    return Position(
        ticket=pos.ticket,
        symbol=pos.symbol,
        direction=direction,
        lots=pos.volume,
        open_price=pos.price_open,
        current_price=pos.price_current,
        sl=pos.sl,
        tp=pos.tp,
        profit=pos.profit,
        open_time=datetime.fromtimestamp(pos.time, tz=timezone.utc),
        comment=pos.comment,
    )


def _with_retry(fn, *args, retries: int = MAX_RETRIES, delay: float = RETRY_DELAY_S, **kwargs):
    """Call *fn* up to *retries* times, sleeping *delay* seconds between attempts."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("Attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"All {retries} attempts failed") from last_exc


# ---------------------------------------------------------------------------
# OrderExecutor
# ---------------------------------------------------------------------------


class OrderExecutor:
    """
    High-level MT5 order management.

    Usage::

        conn = MT5Connection()
        conn.connect()
        executor = OrderExecutor(conn)
        result = executor.place_order("EURUSD", "buy", 1.0, sl=1.082, tp=1.0895)
    """

    def __init__(self, connection: MT5Connection) -> None:
        self._conn = connection

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        direction: str,
        lots: float,
        sl: float,
        tp: float,
        comment: str = "",
        magic: int = 20260101,
    ) -> OrderResult:
        """
        Place a market order with mandatory stop-loss and take-profit.

        Args:
            symbol    : canonical symbol, e.g. "EURUSD"
            direction : "buy" or "sell"
            lots      : lot size (enforced externally to 1.0 by TradeGuard)
            sl        : stop-loss price (required)
            tp        : take-profit price (required)
            comment   : order comment (max 31 chars for MT5)
            magic     : magic number to identify EMPIREX orders

        Returns:
            OrderResult with success flag and details.
        """
        if not self._conn.ensure_connected():
            return OrderResult(success=False, error="MT5 not connected")

        if direction not in ("buy", "sell"):
            return OrderResult(success=False, error=f"Invalid direction: {direction!r}")

        broker_symbol = _resolve_broker_symbol(symbol)
        if broker_symbol is None:
            return OrderResult(success=False, error=f"Symbol {symbol!r} not found in MT5")

        order_type = _ORDER_TYPE_BUY if direction == "buy" else _ORDER_TYPE_SELL

        # Retrieve current price for the appropriate side
        tick = mt5.symbol_info_tick(broker_symbol)
        if tick is None:
            return OrderResult(success=False, error=f"No tick data for {broker_symbol}")

        price = tick.ask if direction == "buy" else tick.bid

        # Filling mode: try IOC first, then FOK (broker-dependent)
        filling_type = mt5.ORDER_FILLING_IOC

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": broker_symbol,
            "volume": float(lots),
            "type": order_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 10,          # max slippage in points
            "magic": magic,
            "comment": comment[:31],  # MT5 limit
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }

        logger.info(
            "Sending order: symbol=%s direction=%s lots=%.2f price=%.5f sl=%.5f tp=%.5f",
            broker_symbol, direction, lots, price, sl, tp,
        )

        def _send() -> OrderResult:
            result = mt5.order_send(request)
            if result is None:
                err = mt5.last_error()
                raise RuntimeError(f"order_send returned None; last_error={err}")
            return result

        try:
            result = _with_retry(_send)
        except RuntimeError as exc:
            logger.error("place_order failed after retries: %s", exc)
            return OrderResult(success=False, error=str(exc))

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(
                "Order placed: ticket=%s symbol=%s direction=%s lots=%.2f",
                result.order, broker_symbol, direction, lots,
            )
            return OrderResult(
                success=True,
                ticket=result.order,
                retcode=result.retcode,
                comment=result.comment,
            )

        # Handle common retcodes
        error_msg = _retcode_description(result.retcode)
        logger.error(
            "Order rejected: retcode=%s (%s) comment=%s",
            result.retcode, error_msg, result.comment,
        )
        return OrderResult(
            success=False,
            retcode=result.retcode,
            comment=result.comment,
            error=error_msg,
        )

    # ------------------------------------------------------------------
    # Position queries
    # ------------------------------------------------------------------

    def get_open_positions(self, symbol: Optional[str] = None) -> list[Position]:
        """
        Return open positions, optionally filtered by canonical symbol name.
        Resolves the broker symbol automatically.
        """
        if not self._conn.ensure_connected():
            logger.warning("get_open_positions: not connected.")
            return []

        if symbol is not None:
            broker_symbol = _resolve_broker_symbol(symbol)
            if broker_symbol is None:
                return []
            raw = mt5.positions_get(symbol=broker_symbol)
        else:
            raw = mt5.positions_get()

        if raw is None:
            err = mt5.last_error()
            if err[0] != 0:  # 0 = ERR_SUCCESS with no positions
                logger.error("positions_get error: %s", err)
            return []

        return [_mt5_position_to_dataclass(p) for p in raw]

    # ------------------------------------------------------------------
    # Daily statistics
    # ------------------------------------------------------------------

    def get_daily_trade_count(self) -> int:
        """
        Count trades executed today (UTC midnight boundary).
        Uses MT5 history deals filtered by the EMPIREX magic number.
        """
        if not self._conn.ensure_connected():
            return 0

        today_start = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        now = datetime.now(tz=timezone.utc)

        deals = mt5.history_deals_get(today_start, now)
        if deals is None:
            return 0

        # Count only entry deals (DEAL_ENTRY_IN = 0) with the EMPIREX magic number
        magic = int(os.environ.get("MT5_MAGIC", "20260101"))
        count = sum(
            1
            for d in deals
            if d.magic == magic and d.entry == 0  # DEAL_ENTRY_IN
        )
        return count

    def get_daily_pnl(self) -> float:
        """
        Return sum of realised P&L for today (UTC) plus unrealised P&L of open positions.
        Negative value means a loss.
        """
        if not self._conn.ensure_connected():
            return 0.0

        today_start = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        now = datetime.now(tz=timezone.utc)

        deals = mt5.history_deals_get(today_start, now)
        realised = sum(d.profit for d in deals) if deals else 0.0

        positions = mt5.positions_get()
        unrealised = sum(p.profit for p in positions) if positions else 0.0

        return realised + unrealised

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def close_position(self, ticket: int) -> OrderResult:
        """Close a specific position by ticket number."""
        if not self._conn.ensure_connected():
            return OrderResult(success=False, error="MT5 not connected")

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return OrderResult(success=False, error=f"No open position with ticket {ticket}")

        pos = positions[0]
        direction = "sell" if pos.type == _ORDER_TYPE_BUY else "buy"
        order_type = _ORDER_TYPE_SELL if pos.type == _ORDER_TYPE_BUY else _ORDER_TYPE_BUY

        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return OrderResult(success=False, error=f"No tick for {pos.symbol}")

        price = tick.bid if direction == "sell" else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 10,
            "magic": pos.magic,
            "comment": "EMPIREX_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        def _send():
            result = mt5.order_send(request)
            if result is None:
                raise RuntimeError(f"order_send None; last_error={mt5.last_error()}")
            return result

        try:
            result = _with_retry(_send)
        except RuntimeError as exc:
            return OrderResult(success=False, error=str(exc))

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info("Position %s closed successfully.", ticket)
            return OrderResult(success=True, ticket=ticket, retcode=result.retcode)

        error_msg = _retcode_description(result.retcode)
        logger.error("Close position %s failed: %s", ticket, error_msg)
        return OrderResult(success=False, retcode=result.retcode, error=error_msg)

    def close_all_positions(self) -> list[OrderResult]:
        """Close every open position (used by kill switch)."""
        positions = self.get_open_positions()
        results: list[OrderResult] = []
        for pos in positions:
            logger.warning("Kill-switch closing position ticket=%s", pos.ticket)
            results.append(self.close_position(pos.ticket))
        return results


# ---------------------------------------------------------------------------
# MT5 retcode decoder
# ---------------------------------------------------------------------------


def _retcode_description(retcode: Optional[int]) -> str:
    _MAP = {
        10004: "REQUOTE",
        10006: "REQUEST_REJECTED",
        10007: "REQUEST_CANCELLED",
        10008: "ORDER_PLACED",
        10009: "TRADE_RETCODE_DONE",
        10010: "TRADE_RETCODE_DONE_PARTIAL",
        10011: "TRADE_RETCODE_ERROR",
        10012: "TRADE_RETCODE_TIMEOUT",
        10013: "TRADE_RETCODE_INVALID",
        10014: "TRADE_RETCODE_INVALID_VOLUME",
        10015: "TRADE_RETCODE_INVALID_PRICE",
        10016: "TRADE_RETCODE_INVALID_STOPS",
        10017: "TRADE_RETCODE_TRADE_DISABLED",
        10018: "TRADE_RETCODE_MARKET_CLOSED",
        10019: "TRADE_RETCODE_NO_MONEY",
        10020: "TRADE_RETCODE_PRICE_CHANGED",
        10021: "TRADE_RETCODE_PRICE_OFF",
        10022: "TRADE_RETCODE_INVALID_EXPIRATION",
        10023: "TRADE_RETCODE_ORDER_CHANGED",
        10024: "TRADE_RETCODE_TOO_MANY_REQUESTS",
        10025: "TRADE_RETCODE_NO_CHANGES",
        10026: "TRADE_RETCODE_SERVER_DISABLES_AT",
        10027: "TRADE_RETCODE_CLIENT_DISABLES_AT",
        10028: "TRADE_RETCODE_LOCKED",
        10029: "TRADE_RETCODE_FROZEN",
        10030: "TRADE_RETCODE_INVALID_FILL",
        10031: "TRADE_RETCODE_CONNECTION",
        10032: "TRADE_RETCODE_ONLY_REAL",
        10033: "TRADE_RETCODE_LIMIT_ORDERS",
        10034: "TRADE_RETCODE_LIMIT_VOLUME",
        10035: "TRADE_RETCODE_INVALID_ORDER",
        10036: "TRADE_RETCODE_POSITION_CLOSED",
        10038: "TRADE_RETCODE_INVALID_CLOSE_VOLUME",
        10039: "TRADE_RETCODE_CLOSE_ORDER_EXIST",
        10040: "TRADE_RETCODE_LIMIT_POSITIONS",
        10041: "TRADE_RETCODE_REJECT_CANCEL",
        10042: "TRADE_RETCODE_LONG_ONLY",
        10043: "TRADE_RETCODE_SHORT_ONLY",
        10044: "TRADE_RETCODE_CLOSE_LONG_ONLY",
        10045: "TRADE_RETCODE_CLOSE_SHORT_ONLY",
    }
    return _MAP.get(retcode, f"UNKNOWN_RETCODE_{retcode}")
