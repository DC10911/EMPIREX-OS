# 05 – EMPIREX-OS Execution Architecture

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          TradingView                                     │
│   Pine Script Strategy                                                   │
│   alertcondition(...)  ──► Alert fires on candle close / real-time      │
│                            Webhook URL: https://your-server:8080/        │
│                                         webhook/tradingview              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │  HTTPS POST  (JSON payload)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    webhook_server.py  (FastAPI, port 8080)               │
│                                                                          │
│  1. Parse JSON → WebhookPayload (Pydantic)                              │
│  2. Validate WEBHOOK_SECRET  (hmac.compare_digest)                      │
│  3. Signal age check  (reject if > 60 s old)                            │
│  4. TradeGuard.validate_order()  ◄─── trade_guard.py                   │
│        ├─ kill switch active?                                            │
│        ├─ daily limit reached? (max 2 trades)                           │
│        ├─ SL missing?                                                   │
│        ├─ lots ≠ 1.0?                                                   │
│        ├─ duplicate position same symbol+direction?                      │
│        └─ martingale (same dir, losing position)?                       │
│  5. OrderExecutor.place_order()  ◄─── mt5_executor.py                  │
│  6. TradeGuard.record_trade()   (persist daily counter)                 │
│  7. Return 200 (filled) / 4xx (rejected) / 502 (MT5 error)             │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │  MetaTrader5 Python API
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    mt5_executor.py                                       │
│                                                                          │
│  MT5Connection ──► mt5.initialize() / mt5.shutdown()                    │
│  OrderExecutor                                                           │
│      place_order()          – market order with SL/TP                   │
│      get_open_positions()   – live position query                        │
│      get_daily_trade_count()– from deal history                         │
│      get_daily_pnl()        – realised + unrealised                     │
│      close_position(ticket) – close specific trade                      │
│      close_all_positions()  – emergency close (kill switch)             │
│                                                                          │
│  Retry logic: max 3 attempts, 500 ms delay                              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │  IPC / Terminal
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    MetaTrader 5 Terminal (Windows)                       │
│                    → Broker connection (FIX / proprietary)              │
│                    → Order placed on live/demo account                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## File Overview

| File | Purpose |
|------|---------|
| `webhook_server.py` | FastAPI HTTP server – receives TradingView alerts |
| `mt5_executor.py`   | MT5 connection and order management |
| `trade_guard.py`    | Business rule enforcement + daily state persistence |
| `trade_guard_state.json` | Auto-created – survives server restart |

---

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `WEBHOOK_SECRET` | Shared secret – must match `secret` field in TradingView alert JSON | `s3cr3t_abc123` |
| `MT5_LOGIN` | MT5 account number (integer) | `12345678` |
| `MT5_PASSWORD` | MT5 account password | `MyBrokerPass` |
| `MT5_SERVER` | Broker server name (as shown in MT5 terminal) | `ICMarketsSC-Demo` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `MT5_PATH` | auto-detect | Full path to `terminal64.exe` |
| `MT5_MAGIC` | `20260101` | Magic number to tag EMPIREX orders |
| `MAX_DAILY_TRADES` | `2` | Hard limit on trades per UTC day |
| `FIXED_LOT_SIZE` | `1.0` | Required lot size (reject anything else) |
| `MAX_DAILY_DRAWDOWN_USD` | `1000.0` | Kill-switch drawdown threshold |
| `TRADE_GUARD_STATE_FILE` | `./trade_guard_state.json` | Path to daily state persistence file |
| `ADMIN_TOKEN` | _(none – disables admin endpoints)_ | Token for `/admin/*` routes |
| `PORT` | `8080` | HTTP server port |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

---

## Setup Instructions

### 1. Prerequisites

- Windows machine (MetaTrader5 Python API is Windows-only)
- MetaTrader 5 terminal installed and logged in
- Python 3.10+

### 2. Install Dependencies

```bash
pip install fastapi uvicorn pydantic MetaTrader5
```

### 3. Create `.env` File (never commit this)

```env
WEBHOOK_SECRET=your_very_long_random_secret_here
MT5_LOGIN=12345678
MT5_PASSWORD=YourBrokerPassword
MT5_SERVER=ICMarketsSC-Demo
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
ADMIN_TOKEN=admin_secret_token
MAX_DAILY_TRADES=2
FIXED_LOT_SIZE=1.0
MAX_DAILY_DRAWDOWN_USD=1000.0
LOG_LEVEL=INFO
```

### 4. Start the Server

```bash
# Load env vars and start
set -a && source .env && set +a
cd quant_engine/execution
uvicorn webhook_server:app --host 0.0.0.0 --port 8080
```

On Windows (PowerShell):

```powershell
$env:WEBHOOK_SECRET = "your_secret"
$env:MT5_LOGIN = "12345678"
# ... (set all vars)
uvicorn webhook_server:app --host 0.0.0.0 --port 8080
```

### 5. Expose to the Internet (for TradingView)

TradingView requires an HTTPS endpoint. Options:

- **ngrok** (quick testing): `ngrok http 8080`
- **Cloudflare Tunnel**: `cloudflared tunnel --url http://localhost:8080`
- **VPS + nginx reverse proxy** (production): terminate SSL at nginx, proxy to `127.0.0.1:8080`
- **Render / Railway** (cloud deploy): use `render.yaml` already in this repo

### 6. TradingView Alert Configuration

In TradingView → Alert → Notifications → Webhook URL:
```
https://your-server.com/webhook/tradingview
```

Message body (JSON):
```json
{
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "price": {{close}},
  "sl": {{plot_0}},
  "tp": {{plot_1}},
  "lots": 1.0,
  "strategy": "EMP-LRB",
  "comment": "LRB_Long_{{timenow}}",
  "timestamp": "{{timenow}}",
  "secret": "your_very_long_random_secret_here"
}
```

---

## MT5 Configuration Requirements

### Broker-Specific Notes

Brokers use different symbol names. The SYMBOL_MAP in `mt5_executor.py` handles automatic resolution:

| Canonical Name | Common Broker Aliases |
|---------------|----------------------|
| `EURUSD` | `EURUSD`, `EURUSDm`, `EURUSD.` |
| `GBPUSD` | `GBPUSD`, `GBPUSDm`, `GBPUSD.` |
| `XAUUSD` | `XAUUSD`, `GOLDm`, `GOLD`, `XAUUSD.` |
| `NAS100` | `NAS100`, `US100`, `USTEC`, `NAS100m`, `NDX` |

To add a new symbol or broker alias, edit `SYMBOL_MAP` in `mt5_executor.py`.

### MT5 Terminal Settings

1. Enable **Algo Trading** (AutoTrading button in toolbar must be green)
2. Tools → Options → Expert Advisors:
   - [x] Allow automated trading
   - [x] Allow DLL imports (if using EAs alongside)
3. Ensure the account is logged in and the terminal shows `Connected` in the status bar.
4. The MT5 Python API uses IPC to communicate with the running terminal on the same machine.

### Filling Mode

The server defaults to `ORDER_FILLING_IOC` (Immediate-or-Cancel). If your broker requires `FOK` (Fill-or-Kill), change `filling_type` in `OrderExecutor.place_order()`.

### Swap / Commission Symbols (XAUUSD)

Gold typically has a spread of 20–50 points. The `deviation` parameter in the order request is set to 10 points — increase this to 50 for XAUUSD to avoid frequent `REQUOTE` rejections:

```python
# In mt5_executor.py place_order():
deviation = 50 if "XAU" in broker_symbol or "GOLD" in broker_symbol else 10
```

---

## Latency Considerations for London Open Entries

London open (08:00 UTC, 09:00 BST) is the highest-liquidity window but also the highest-spread window in the first 5–15 minutes.

### Typical Latency Budget

| Stage | Typical Latency |
|-------|----------------|
| Pine Script → TradingView alert | 0–2 s (candle close) |
| TradingView → webhook HTTP POST | 1–5 s |
| Webhook validation + TradeGuard | < 10 ms |
| MT5 order_send → broker | 50–200 ms |
| **Total** | **1–7 s** |

### Recommendations

- **Use `barstate.isconfirmed`** in Pine Script to fire alerts only on confirmed candle closes (not real-time), reducing false triggers.
- **Set `deviation = 20`** minimum for London open to absorb spread spikes.
- **Signal age check (60 s window)** in the webhook server rejects stale alerts caused by TradingView queuing delays.
- **Co-locate** the webhook server on the same Windows machine as MT5 (eliminates internal network latency).
- **Do NOT trade the first 5 candles** after London open if spread > 3 pips for major pairs. Add this filter to Pine Script.

---

## Business Rules Summary

| Rule | Implementation | Rejection Code |
|------|---------------|----------------|
| Max 2 trades/day | `check_daily_limit()` | `DAILY_LIMIT` |
| No averaging down | `check_no_duplicate_position()` | `DUPLICATE_POSITION` |
| No martingale | `check_no_martingale()` | `MARTINGALE_BLOCKED` |
| SL required | `validate_order()` field check | `MISSING_SL` |
| Fixed 1.0 lot | `validate_order()` field check | `INVALID_LOTS` |
| Kill switch | `check_kill_switch()` | `KILL_SWITCH` |

---

## Failure Modes and Recovery Procedures

### MT5 Terminal Disconnects

**Symptom:** `/health` returns `mt5_connected: false`. Orders fail with 503.

**Recovery:**
1. Confirm MT5 terminal is running and shows `Connected`.
2. Call any endpoint — `ensure_connected()` will auto-reconnect on next request.
3. If terminal is crashed: restart terminal, wait for it to log in, then restart the webhook server.

### Kill Switch Activated Incorrectly

**Symptom:** All orders rejected with `KILL_SWITCH` reason.

**Recovery:**
```bash
curl -X POST https://your-server/admin/kill-switch/deactivate \
  -H "X-Admin-Token: your_admin_token"
```

Or manually delete/edit `trade_guard_state.json` and restart the server.

### Daily Counter Incorrect After Restart

**Symptom:** Trades accepted when they should be blocked.

**Recovery:** The `trade_guard_state.json` file is the source of truth. If corrupted, delete it. The server will start fresh (0 trades for today). Manually check MT5 deal history and set the correct count:

```json
{
  "date_utc": "2026-01-15",
  "trade_count": 2,
  "kill_switch_active": false,
  "kill_switch_reason": "",
  "cumulative_realized_pnl": -250.0,
  "filled_tickets": [12345678, 12345679]
}
```

### Stale Signal Rejected (> 60 s old)

**Symptom:** 400 response `Signal too old: 75s (max 60s)`.

**Cause:** TradingView alert delivery delay or server clock drift.

**Recovery:**
1. Sync server clock: `ntpdate pool.ntp.org`
2. Temporarily increase the age window in `webhook_server.py` (line: `if age_s > 60`).
3. Consider using `barstate.isconfirmed` alerts which fire quickly after candle close.

### Order Rejected with REQUOTE (retcode 10004)

**Symptom:** `OrderResult.error = "REQUOTE"`. Most common at London open.

**Recovery:**
1. Increase `deviation` in `place_order()` to 20–50 points.
2. The retry logic (3 retries, 500 ms delay) will re-attempt automatically.

### Broker Server Unavailable

**Symptom:** MT5 shows `No connection`. All orders fail.

**Recovery:**
1. Check broker server status page.
2. In MT5: File → Login → re-enter credentials if session expired.
3. Webhook server will auto-reconnect (`ensure_connected()`) when terminal recovers.

---

## Webhook Security Best Practices

1. **Rotate the WEBHOOK_SECRET regularly** (monthly minimum). Store it in a secrets manager (HashiCorp Vault, AWS Secrets Manager, or at minimum an `.env` file with `chmod 600`).

2. **NEVER put the secret in Pine Script source code** that is published or shared. Use TradingView's alert message text field (not visible in public scripts).

3. **HTTPS is mandatory.** TradingView will not send webhooks to plain HTTP endpoints in production. Use Let's Encrypt + nginx or a managed TLS provider.

4. **IP allowlisting** (optional hardening): TradingView publishes its webhook IP ranges. Add them to your firewall:
   ```
   # TradingView webhook IPs (verify at tradingview.com/support)
   # As of 2025: check their documentation for current ranges
   ufw allow from 52.89.214.238 to any port 8080
   ```

5. **Rate limiting**: Consider adding a rate limiter (e.g., `slowapi`) to prevent webhook flooding:
   ```python
   from slowapi import Limiter
   limiter = Limiter(key_func=get_remote_address)
   @limiter.limit("10/minute")
   ```

6. **Log retention**: Keep webhook logs for at least 30 days for audit purposes. Rotate logs with `logrotate` or a cloud logging service.

7. **Admin endpoints** (`/admin/*`) should be behind a separate port or VPN — not exposed to the public internet. Use `ADMIN_TOKEN` with a strong random value.

8. **Never log the raw secret**. The webhook server already masks it with `***` in all log output.

---

## Running Tests (Without MT5)

The executor guards against `MT5_AVAILABLE = False` allowing unit tests on non-Windows:

```python
# tests/test_trade_guard.py
from trade_guard import TradeGuard, DailyState
import tempfile, pathlib

def test_daily_limit():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        guard = TradeGuard(state_file=pathlib.Path(f.name))
        assert guard.check_daily_limit() is True
        guard.record_trade(ticket=1)
        guard.record_trade(ticket=2)
        assert guard.check_daily_limit() is False

def test_kill_switch():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        guard = TradeGuard(state_file=pathlib.Path(f.name))
        guard.activate_kill_switch("test")
        assert guard.check_kill_switch() is False
        guard.deactivate_kill_switch()
        assert guard.check_kill_switch() is True
```

```bash
pip install pytest httpx fastapi
pytest tests/
```
