"""
webhook_server.py
-----------------
FastAPI webhook receiver for EMPIREX-OS TradingView → MT5 execution pipeline.

Endpoint:  POST /webhook/tradingview
Port:      8080  (override with PORT env var)

Environment variables required:
    WEBHOOK_SECRET      – shared secret validated against the 'secret' field in the payload
    MT5_LOGIN           – MT5 account number
    MT5_PASSWORD        – MT5 account password
    MT5_SERVER          – MT5 broker server name
    MT5_PATH            – (optional) path to terminal64.exe
    MT5_MAGIC           – (optional) magic number, default 20260101
    MAX_DAILY_TRADES    – (optional) default 2
    FIXED_LOT_SIZE      – (optional) default 1.0
    MAX_DAILY_DRAWDOWN_USD – (optional) default 1000.0
    TRADE_GUARD_STATE_FILE – (optional) path to state JSON file
    LOG_LEVEL           – (optional) DEBUG | INFO | WARNING | ERROR (default INFO)

Run:
    uvicorn webhook_server:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Logging setup (must happen before importing our modules)
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("empirex.webhook")

# ---------------------------------------------------------------------------
# Local imports
# ---------------------------------------------------------------------------

from mt5_executor import MT5Connection, OrderExecutor  # noqa: E402
from trade_guard import TradeGuard  # noqa: E402

# ---------------------------------------------------------------------------
# Global singletons (initialized at startup)
# ---------------------------------------------------------------------------

mt5_connection: Optional[MT5Connection] = None
order_executor: Optional[OrderExecutor] = None
trade_guard: Optional[TradeGuard] = None

WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialize MT5 connection and TradeGuard on startup; clean up on shutdown."""
    global mt5_connection, order_executor, trade_guard

    if not WEBHOOK_SECRET:
        logger.critical(
            "WEBHOOK_SECRET environment variable is not set. "
            "All incoming webhooks will be rejected."
        )

    logger.info("EMPIREX webhook server starting up…")

    mt5_connection = MT5Connection()
    connected = mt5_connection.connect()
    if not connected:
        logger.warning(
            "MT5 connection failed at startup. "
            "Orders will be rejected until MT5 is available."
        )

    order_executor = OrderExecutor(mt5_connection)
    trade_guard = TradeGuard(executor=order_executor)

    logger.info("TradeGuard initialized. Daily state: %s", trade_guard.daily_state)
    logger.info("EMPIREX webhook server ready.")

    yield  # Server runs here

    logger.info("EMPIREX webhook server shutting down…")
    if mt5_connection:
        mt5_connection.disconnect()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="EMPIREX-OS Webhook Server",
    description="TradingView alert → MT5 execution bridge",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Pydantic request model
# ---------------------------------------------------------------------------


class WebhookPayload(BaseModel):
    symbol: str = Field(..., description="Trading symbol, e.g. EURUSD")
    action: str = Field(..., description="'buy' or 'sell'")
    price: float = Field(..., gt=0, description="Signal price")
    sl: float = Field(..., gt=0, description="Stop-loss price (required)")
    tp: float = Field(..., gt=0, description="Take-profit price (required)")
    lots: float = Field(..., gt=0, description="Lot size (must be 1.0)")
    strategy: str = Field(default="", description="Strategy identifier")
    comment: str = Field(default="", description="Order comment")
    timestamp: str = Field(default="", description="ISO 8601 signal timestamp")
    secret: str = Field(..., description="Webhook authentication secret")

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("action")
    @classmethod
    def action_lower(cls, v: str) -> str:
        val = v.strip().lower()
        if val not in ("buy", "sell"):
            raise ValueError(f"action must be 'buy' or 'sell', got {v!r}")
        return val

    @field_validator("sl", "tp", "price")
    @classmethod
    def positive_price(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Price/SL/TP must be positive")
        return v


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def _validate_secret(provided_secret: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    if not WEBHOOK_SECRET:
        logger.error("WEBHOOK_SECRET not configured – rejecting all requests.")
        return False
    return hmac.compare_digest(provided_secret.encode(), WEBHOOK_SECRET.encode())


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@app.post(
    "/webhook/tradingview",
    summary="Receive TradingView alert and execute MT5 order",
    response_description="Order result or rejection reason",
)
async def tradingview_webhook(request: Request) -> JSONResponse:
    received_at = datetime.now(tz=timezone.utc).isoformat()
    remote_ip = request.client.host if request.client else "unknown"

    # ---- Parse raw body for logging before Pydantic validation ----
    try:
        raw_body = await request.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Malformed JSON from %s: %s", remote_ip, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # Sanitize the secret from logs
    log_body = {k: ("***" if k == "secret" else v) for k, v in raw_body.items()}
    logger.info("Webhook received from %s at %s: %s", remote_ip, received_at, log_body)

    # ---- Pydantic validation ----
    try:
        payload = WebhookPayload(**raw_body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Payload validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Payload validation failed: {exc}",
        )

    # ---- Authenticate ----
    if not _validate_secret(payload.secret):
        logger.warning(
            "UNAUTHORIZED webhook from %s – invalid secret.", remote_ip
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )

    # ---- Signal age check (reject stale signals > 60 s) ----
    if payload.timestamp:
        try:
            sig_time = datetime.fromisoformat(
                payload.timestamp.replace("Z", "+00:00")
            )
            age_s = (datetime.now(tz=timezone.utc) - sig_time).total_seconds()
            if age_s > 60:
                logger.warning(
                    "Stale signal rejected: age=%.1f s (limit 60 s) from %s",
                    age_s, remote_ip,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Signal too old: {age_s:.0f}s (max 60s)",
                )
        except ValueError:
            logger.warning("Could not parse timestamp '%s'; skipping age check.", payload.timestamp)

    # ---- MT5 connectivity check ----
    if mt5_connection is None or not mt5_connection.ensure_connected():
        logger.error("MT5 not connected. Cannot process order.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MT5 connection unavailable",
        )

    # ---- Business rule validation (TradeGuard) ----
    order_dict = {
        "symbol": payload.symbol,
        "action": payload.action,
        "sl": payload.sl,
        "tp": payload.tp,
        "lots": payload.lots,
        "price": payload.price,
    }

    validation = trade_guard.validate_order(order_dict)
    if not validation.allowed:
        logger.warning(
            "Order REJECTED by TradeGuard: %s | symbol=%s action=%s",
            validation.reason, payload.symbol, payload.action,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "status": "rejected",
                "reason": validation.reason,
                "symbol": payload.symbol,
                "action": payload.action,
                "received_at": received_at,
            },
        )

    # ---- Execute order ----
    comment = (payload.comment or f"{payload.strategy}_{payload.action}_{payload.symbol}")[:31]

    logger.info(
        "Executing order: symbol=%s action=%s lots=%.2f sl=%.5f tp=%.5f comment=%s",
        payload.symbol, payload.action, payload.lots, payload.sl, payload.tp, comment,
    )

    t_start = time.monotonic()
    result = order_executor.place_order(
        symbol=payload.symbol,
        direction=payload.action,
        lots=payload.lots,
        sl=payload.sl,
        tp=payload.tp,
        comment=comment,
    )
    latency_ms = (time.monotonic() - t_start) * 1000

    if result.success:
        trade_guard.record_trade(ticket=result.ticket)
        logger.info(
            "Order FILLED: ticket=%s symbol=%s action=%s latency=%.1fms",
            result.ticket, payload.symbol, payload.action, latency_ms,
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "filled",
                "ticket": result.ticket,
                "symbol": payload.symbol,
                "action": payload.action,
                "lots": payload.lots,
                "sl": payload.sl,
                "tp": payload.tp,
                "comment": comment,
                "strategy": payload.strategy,
                "latency_ms": round(latency_ms, 1),
                "received_at": received_at,
                "daily_trade_count": trade_guard.daily_state.trade_count,
            },
        )

    # Execution failed
    logger.error(
        "Order FAILED: symbol=%s action=%s error=%s retcode=%s",
        payload.symbol, payload.action, result.error, result.retcode,
    )
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "status": "error",
            "error": result.error,
            "retcode": result.retcode,
            "symbol": payload.symbol,
            "action": payload.action,
            "received_at": received_at,
        },
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@app.get("/health", summary="Health check")
async def health_check() -> JSONResponse:
    connected = mt5_connection is not None and mt5_connection.is_connected
    state = trade_guard.daily_state if trade_guard else None
    return JSONResponse(
        content={
            "status": "healthy" if connected else "degraded",
            "mt5_connected": connected,
            "kill_switch_active": state.kill_switch_active if state else None,
            "daily_trades": state.trade_count if state else None,
            "date_utc": state.date_utc if state else None,
        }
    )


@app.post("/admin/kill-switch/activate", summary="Manually activate kill switch")
async def activate_kill_switch(request: Request) -> JSONResponse:
    """
    Manually halt all trading for the remainder of the day.
    Requires the X-Admin-Token header to match ADMIN_TOKEN env var.
    """
    _require_admin_token(request)
    reason = (await request.json()).get("reason", "Manual activation")
    trade_guard.activate_kill_switch(reason)
    order_executor.close_all_positions()
    return JSONResponse({"status": "kill_switch_activated", "reason": reason})


@app.post("/admin/kill-switch/deactivate", summary="Manually deactivate kill switch")
async def deactivate_kill_switch(request: Request) -> JSONResponse:
    _require_admin_token(request)
    trade_guard.deactivate_kill_switch()
    return JSONResponse({"status": "kill_switch_deactivated"})


@app.get("/admin/positions", summary="List open MT5 positions")
async def list_positions(request: Request) -> JSONResponse:
    _require_admin_token(request)
    if not mt5_connection or not mt5_connection.is_connected:
        raise HTTPException(status_code=503, detail="MT5 not connected")
    positions = order_executor.get_open_positions()
    return JSONResponse(
        {
            "count": len(positions),
            "positions": [
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "direction": p.direction,
                    "lots": p.lots,
                    "open_price": p.open_price,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "open_time": p.open_time.isoformat(),
                    "comment": p.comment,
                }
                for p in positions
            ],
        }
    )


@app.get("/admin/daily-state", summary="Return daily TradeGuard state")
async def daily_state(request: Request) -> JSONResponse:
    _require_admin_token(request)
    from dataclasses import asdict
    return JSONResponse(asdict(trade_guard.daily_state))


# ---------------------------------------------------------------------------
# Admin auth helper
# ---------------------------------------------------------------------------


def _require_admin_token(request: Request) -> None:
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    provided = request.headers.get("X-Admin-Token", "")
    if not admin_token or not hmac.compare_digest(provided.encode(), admin_token.encode()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing admin token",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "webhook_server:app",
        host="0.0.0.0",
        port=port,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )
