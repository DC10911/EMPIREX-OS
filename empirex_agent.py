#!/usr/bin/env python3
"""
EMPIREX Local MT5 Execution Agent
===================================
Runs on the Windows machine alongside MetaTrader 5.
Polls the Render (or local) server for pending signals and executes them via MT5.

Usage:
    python empirex_agent.py --server https://your-app.onrender.com --key YOUR_WEBHOOK_KEY

Or set environment variables:
    EMPIREX_SERVER=https://your-app.onrender.com
    EMPIREX_AGENT_KEY=your_webhook_key
    MT5_LOGIN=12345
    MT5_PASSWORD=your_password
    MT5_SERVER=demo.ftmo.com:443

Then run:
    python empirex_agent.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# ── MT5 ──────────────────────────────────────────────────────────────────────
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    MT5_AVAILABLE = False
    print("[WARN] MetaTrader5 not installed. Run: pip install MetaTrader5")

_MT5_LOCK = threading.Lock()

# ── Config ───────────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent / ".env"


def _load_env() -> None:
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _api(server: str, method: str, path: str, key: str, data: dict | None = None) -> dict:
    url = server.rstrip("/") + path
    body = json.dumps(data).encode() if data else None
    req = Request(
        url,
        data=body,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Agent-Key": key,
        },
    )
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read())


# ── Lot-size calculation ──────────────────────────────────────────────────────

def _calc_lots(symbol: str, entry_price: float, sl_price: float, sl_dollars: float) -> float:
    """Return lot size so that hitting SL costs ~sl_dollars."""
    if not MT5_AVAILABLE or not sl_price or sl_dollars <= 0:
        return 0.0
    try:
        info = mt5.symbol_info(symbol)
        if not info:
            return 0.0
        is_5d = info.digits in (5, 3)
        pip = info.point * (10 if is_5d else 1)
        sl_pips = abs(entry_price - sl_price) / pip
        if sl_pips < 0.01:
            return 0.0
        tick_val = info.trade_tick_value
        tick_size = info.trade_tick_size
        if tick_size <= 0 or tick_val <= 0:
            return 0.0
        pip_val_per_lot = tick_val * pip / tick_size
        if pip_val_per_lot <= 0:
            return 0.0
        lots = sl_dollars / (sl_pips * pip_val_per_lot)
        step = info.volume_step if info.volume_step > 0 else 0.01
        lots = round(round(lots / step) * step, 2)
        lots = max(info.volume_min, min(lots, info.volume_max))
        return round(lots, 2)
    except Exception as e:
        print(f"[Agent] lot calc error: {e}")
        return 0.0


# ── MT5 execution ─────────────────────────────────────────────────────────────

def _execute(signal: dict, settings: dict, creds: dict) -> tuple[bool, str, dict]:
    if not MT5_AVAILABLE:
        return False, "MT5 not installed", {}

    symbol = str(signal.get("symbol", "")).upper().replace("/", "")
    action = str(signal.get("action", "")).lower()
    if action in ("long",): action = "buy"
    if action in ("short",): action = "sell"
    if action not in ("buy", "sell"):
        return False, f"Invalid action: {action}", {}

    sl_level = int(signal.get("sl_level", 1) or 1)
    sl_key = f"sl{sl_level}_dollars"
    sl_dollars = float(settings.get(sl_key, settings.get("sl1_dollars", 50)))
    tp_dollars = float(settings.get("tp_dollars", sl_dollars * 2))
    default_lots = float(settings.get("default_lots", 0.01))

    sl_price_raw = signal.get("sl")
    tp_price_raw = signal.get("tp")

    with _MT5_LOCK:
        try:
            login = int(creds["login"])
            if not mt5.initialize(
                login=login,
                password=str(creds["password"]),
                server=str(creds["server"]),
            ):
                return False, f"MT5 init failed: {mt5.last_error()}", {}

            info = mt5.symbol_info(symbol)
            if not info:
                mt5.shutdown()
                return False, f"Symbol '{symbol}' not found", {}
            if not info.visible:
                mt5.symbol_select(symbol, True)

            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                mt5.shutdown()
                return False, f"No tick for {symbol}", {}

            entry = tick.ask if action == "buy" else tick.bid

            # SL price
            sl_price = None
            if sl_price_raw is not None:
                try:
                    sl_price = float(sl_price_raw)
                except Exception:
                    pass

            # Lot size
            if sl_price is not None and sl_dollars > 0:
                lots = _calc_lots(symbol, entry, sl_price, sl_dollars)
                if lots <= 0:
                    lots = default_lots
            else:
                lots = float(signal.get("lots", default_lots))

            # TP price — from signal or auto-calculated from tp_dollars
            tp_price = None
            if tp_price_raw is not None:
                try:
                    tp_price = float(tp_price_raw)
                except Exception:
                    pass
            if tp_price is None and sl_price is not None and tp_dollars > 0 and sl_dollars > 0:
                sl_dist = abs(entry - sl_price)
                if sl_dist > 0:
                    tp_dist = sl_dist * (tp_dollars / sl_dollars)
                    tp_price = round(
                        entry + tp_dist if action == "buy" else entry - tp_dist,
                        info.digits,
                    )

            order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": round(lots, 2),
                "type": order_type,
                "price": entry,
                "deviation": 30,
                "magic": 20260512,
                "comment": str(signal.get("comment", "EMPIREX"))[:31],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            if sl_price is not None:
                req["sl"] = round(sl_price, info.digits)
            if tp_price is not None:
                req["tp"] = round(tp_price, info.digits)

            result = mt5.order_send(req)
            mt5.shutdown()

            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return True, "OK", {
                    "ticket": int(result.order),
                    "symbol": symbol,
                    "direction": action,
                    "lots": round(lots, 2),
                    "entry_price": round(entry, 5),
                    "sl": req.get("sl"),
                    "tp": req.get("tp"),
                }
            else:
                code = result.retcode if result else "?"
                msg = result.comment if result else ""
                return False, f"order_send retcode={code}: {msg}", {}

        except Exception as e:
            try:
                mt5.shutdown()
            except Exception:
                pass
            return False, f"MT5 error: {e}", {}


# ── Main polling loop ─────────────────────────────────────────────────────────

def poll_loop(server: str, key: str, creds: dict) -> None:
    print(f"[EMPIREX Agent] Polling {server} every 3s for pending signals...")
    settings: dict = {}

    while True:
        try:
            # Refresh settings from server
            try:
                s = _api(server, "GET", "/api/bot/settings", key)
                if s.get("ok"):
                    settings = {k: v for k, v in s["data"].items() if not k.startswith("_")}
            except Exception:
                pass

            # Fetch pending signals
            resp = _api(server, "GET", f"/api/bot/signals/pending?key={key}", key)
            signals = resp.get("data", [])

            for sig in signals:
                sig_id = sig["id"]
                signal = sig["signal"]
                sym = signal.get("symbol", "?")
                act = signal.get("action", "?")
                print(f"[Agent] ▶ Signal #{sig_id}: {act.upper()} {sym}")

                ok, msg, result = _execute(signal, settings, creds)

                try:
                    _api(server, "POST", "/api/bot/signals/ack", key, {
                        "key": key,
                        "id": sig_id,
                        "ok": ok,
                        "message": msg,
                        "result": result,
                    })
                except Exception as e:
                    print(f"[Agent] ack failed: {e}")

                status = "✅" if ok else "❌"
                print(f"[Agent] {status} #{sig_id} {sym}: {msg}")

        except URLError as e:
            print(f"[Agent] Network error: {e}")
        except Exception as e:
            print(f"[Agent] Error: {e}")

        time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="EMPIREX Local MT5 Execution Agent")
    parser.add_argument(
        "--server",
        default=os.getenv("EMPIREX_SERVER", "http://localhost:5501"),
        help="Server URL (e.g. https://your-app.onrender.com)",
    )
    parser.add_argument(
        "--key",
        default=os.getenv("EMPIREX_AGENT_KEY", ""),
        help="Webhook key (copy from Bot Settings → TradingView tab)",
    )
    parser.add_argument("--login", default=os.getenv("MT5_LOGIN", ""), help="MT5 account login")
    parser.add_argument("--password", default=os.getenv("MT5_PASSWORD", ""), help="MT5 account password")
    parser.add_argument("--mt5server", default=os.getenv("MT5_SERVER", ""), help="MT5 broker server address")
    args = parser.parse_args()

    if not args.key:
        print("❌ ERROR: --key required. Copy it from the Bot → TradingView tab in the dashboard.")
        sys.exit(1)
    if not args.login or not args.password or not args.mt5server:
        print("❌ ERROR: MT5 credentials required (--login, --password, --mt5server).")
        print("   Or set MT5_LOGIN / MT5_PASSWORD / MT5_SERVER in the .env file.")
        sys.exit(1)
    if not MT5_AVAILABLE:
        print("❌ ERROR: MetaTrader5 not installed. Run: pip install MetaTrader5")
        sys.exit(1)

    creds = {"login": args.login, "password": args.password, "server": args.mt5server}
    print(f"[EMPIREX Agent] Server: {args.server}")
    print(f"[EMPIREX Agent] MT5: login={args.login} server={args.mt5server}")

    try:
        poll_loop(args.server, args.key, creds)
    except KeyboardInterrupt:
        print("\n[Agent] Stopped.")


if __name__ == "__main__":
    main()
