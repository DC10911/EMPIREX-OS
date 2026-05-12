from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import queue
import threading
import time
import concurrent.futures
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("EMPIREX_DB_PATH", str(ROOT / "empirex_leads.db"))).expanduser().resolve()
ENV_PATH = ROOT / ".env"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5501"))

# Ensure the script's directory is in sys.path so agent_brain can be imported
import sys as _sys
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))

# ── Agent brain (optional — loads only when DB is ready) ───────────────
_agent_brain = None
def _get_brain():
    global _agent_brain
    if _agent_brain is None:
        try:
            import agent_brain
            _agent_brain = agent_brain
        except Exception:
            _agent_brain = None
    return _agent_brain

FX_BASE = {
    "EURUSD": {"symbol": "EUR/USD", "name": "Euro / US Dollar", "price": 1.1761, "change": 0.18},
    "GBPUSD": {"symbol": "GBP/USD", "name": "British Pound / US Dollar", "price": 1.3611, "change": 0.11},
    "USDJPY": {"symbol": "USD/JPY", "name": "US Dollar / Japanese Yen", "price": 156.76, "change": -0.09},
    "AUDUSD": {"symbol": "AUD/USD", "name": "Australian Dollar / US Dollar", "price": 0.6618, "change": 0.07},
    "USDCAD": {"symbol": "USD/CAD", "name": "US Dollar / Canadian Dollar", "price": 1.3724, "change": -0.04},
    "EURGBP": {"symbol": "EUR/GBP", "name": "Euro / British Pound", "price": 0.8641, "change": 0.03},
}

STOCK_BASE = {
    "NVDA": {"symbol": "NVDA", "name": "NVIDIA", "price": 214.8, "change": 1.56, "currency": "USD"},
    "AAPL": {"symbol": "AAPL", "name": "Apple", "price": 293.63, "change": 2.15, "currency": "USD"},
    "MSFT": {"symbol": "MSFT", "name": "Microsoft", "price": 414.76, "change": -1.43, "currency": "USD"},
    "AMZN": {"symbol": "AMZN", "name": "Amazon", "price": 186.55, "change": 0.84, "currency": "USD"},
    "META": {"symbol": "META", "name": "Meta Platforms", "price": 642.31, "change": 1.07, "currency": "USD"},
    "TSLA": {"symbol": "TSLA", "name": "Tesla", "price": 248.19, "change": -0.62, "currency": "USD"},
}

HTTP_HEADERS = {
    "User-Agent": "EMPIREX-OS/1.0 (+https://localhost)",
    "Accept": "application/json",
}

TV_FOREX_SCAN_URL = "https://scanner.tradingview.com/forex/scan"
TV_STOCKS_SCAN_URL = "https://scanner.tradingview.com/america/scan"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(ENV_PATH)


def validate_production_config() -> None:
    if APP_ENV != "production":
        return

    problems: list[str] = []
    if OTP_SECRET in {"", "dev_otp_secret", "change_me_super_secret"} or len(OTP_SECRET) < 32:
        problems.append("OTP_SECRET must be set to a strong value with at least 32 characters")

    app_base_url = os.getenv("APP_BASE_URL", "").strip()
    if not app_base_url:
        problems.append("APP_BASE_URL must be set in production")
    elif not app_base_url.startswith("https://"):
        problems.append("APP_BASE_URL must start with https:// in production")

    if problems:
        raise RuntimeError("Production configuration invalid: " + "; ".join(problems))


# ── MetaTrader5 optional integration ─────────────────────────────────────────
try:
    import MetaTrader5 as _mt5  # type: ignore[import-untyped]
    _MT5_AVAILABLE = True
except ImportError:
    _mt5 = None  # type: ignore[assignment]
    _MT5_AVAILABLE = False

_MT5_LOCK = threading.Lock()


def _generate_trading_summary(daily_pnl: float, daily_trades: int, daily_wins: int, balance: float) -> str:
    """Generate a Hebrew AI-style summary of the trading day."""
    if daily_trades == 0:
        return "לא בוצעו עסקאות היום. השוק פתוח — הגדר אסטרטגיה ברורה לפני הכניסה."
    losses = daily_trades - daily_wins
    win_rate = (daily_wins / daily_trades * 100) if daily_trades else 0.0
    pnl_pct = (daily_pnl / balance * 100) if balance else 0.0
    parts: list[str] = []
    if daily_pnl > 0:
        parts.append(f"יום מסחר חיובי — רווח של ${daily_pnl:,.2f} ({pnl_pct:+.2f}%).")
    elif daily_pnl < 0:
        parts.append(f"יום מסחר שלילי — הפסד של ${abs(daily_pnl):,.2f} ({abs(pnl_pct):.2f}%).")
    else:
        parts.append("יום מסחר מאוזן — ללא שינוי בחשבון.")
    parts.append(
        f"בוצעו {daily_trades} עסקאות: {daily_wins} מוצלחות ו-{losses} הפסדים (שיעור הצלחה {win_rate:.0f}%)."
    )
    if win_rate >= 70:
        parts.append("ביצועים מצוינים — שמור על הריתמוס ואל תסטה מהאסטרטגיה.")
    elif win_rate >= 55:
        parts.append("ביצועים טובים — שקול לשפר את יחס סיכון/תשואה בעסקאות הבאות.")
    elif win_rate >= 40:
        parts.append("ביצועים ממוצעים — נתח את הגישה וחפש תבניות בהפסדים.")
    else:
        parts.append("אחוז הצלחה נמוך — מומלץ להפחית גודל פוזיציה ולבחון את האסטרטגיה.")
    if daily_pnl < 0 and abs(pnl_pct) > 2:
        parts.append("⚠️ הפסד חורג מ-2% — שקול לעצור מסחר להיום.")
    elif daily_pnl > 0 and pnl_pct > 5:
        parts.append("🔥 ביצועים יוצאי דופן — היזהר מ-overtrading שעלול לסכן את הרווחים.")
    return " ".join(parts)


def _is_mt5_terminal_running() -> bool:
    """Check if MetaTrader5 terminal64.exe / terminal.exe is running."""
    try:
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=4,
        )
        output_lower = result.stdout.lower()
        return "terminal64.exe" in output_lower or "terminal.exe" in output_lower
    except Exception:
        return False


def _connect_fetch_mt5(server: str, login: str, password: str) -> tuple[dict | None, str | None]:
    """Connect to a running MT5 terminal and return account + today's trading data."""
    if not _MT5_AVAILABLE or _mt5 is None:
        return None, "MetaTrader5 Python library is not available on this server."
    if not _is_mt5_terminal_running():
        return None, "MT5_TERMINAL_NOT_RUNNING"
    try:
        login_int = int(login)
    except (ValueError, TypeError):
        return None, "מספר חשבון לא תקין — חייב להיות מספר שלם."

    def _do_connect():
        with _MT5_LOCK:
            try:
                if not _mt5.initialize(server=server, login=login_int, password=str(password)):
                    err = _mt5.last_error()
                    err_msg = str(err[1]) if (err and len(err) > 1) else str(err)
                    try:
                        _mt5.shutdown()
                    except Exception:
                        pass
                    low = err_msg.lower()
                    if any(k in low for k in ("terminal", "ipc", "connect", "not found", "2")):
                        return None, "MT5_TERMINAL_NOT_RUNNING"
                    return None, f"MT5 connection failed: {err_msg}"
                acct = _mt5.account_info()
                if not acct:
                    _mt5.shutdown()
                    return None, "Failed to retrieve account info from MT5 terminal."
                tz = timezone.utc
                now = datetime.now(tz)
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                tomorrow = today_start + timedelta(days=1)
                buy_sell = (_mt5.DEAL_TYPE_BUY, _mt5.DEAL_TYPE_SELL)
                today_deals = _mt5.history_deals_get(today_start, tomorrow) or []
                closed_today = [d for d in today_deals if d.type in buy_sell]
                daily_pnl = sum(float(d.profit) for d in closed_today)
                daily_trades = len(closed_today)
                daily_wins = sum(1 for d in closed_today if float(d.profit) > 0)
                all_deals = _mt5.history_deals_get(datetime(2000, 1, 1, tzinfo=tz), tomorrow) or []
                total_trades = sum(1 for d in all_deals if d.type in buy_sell)
                open_positions = _mt5.positions_total() or 0
                _mt5.shutdown()
                return {
                    "balance": round(float(acct.balance), 2),
                    "equity": round(float(acct.equity), 2),
                    "marginFree": round(float(acct.margin_free), 2),
                    "currency": acct.currency,
                    "leverage": int(acct.leverage),
                    "server": acct.server,
                    "name": acct.name,
                    "company": acct.company,
                    "totalTrades": int(total_trades),
                    "openPositions": int(open_positions),
                    "dailyPnl": round(float(daily_pnl), 2),
                    "dailyTrades": int(daily_trades),
                    "dailyWins": int(daily_wins),
                    "aiSummary": _generate_trading_summary(daily_pnl, daily_trades, daily_wins, float(acct.balance)),
                }, None
            except Exception as exc:
                try:
                    _mt5.shutdown()
                except Exception:
                    pass
                return None, f"MT5 error: {exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_do_connect)
        try:
            return future.result(timeout=15)
        except concurrent.futures.TimeoutError:
            return None, "MT5_TERMINAL_NOT_RUNNING"
# ─────────────────────────────────────────────────────────────────────────────

APP_ENV = os.getenv("APP_ENV", "development").lower()
OTP_SECRET = os.getenv("OTP_SECRET", "dev_otp_secret")
OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", "10"))
OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "EMPIREX OS <no-reply@empirex.local>").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "1").strip() == "1"

validate_production_config()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "").strip()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime) -> str:
    return value.isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    safe = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(safe)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def phone_to_virtual_email(phone: str) -> str:
    digits = "".join(char for char in phone if char.isdigit())
    return f"phone_{digits}@phone.local"


def normalize_phone(phone: str) -> str:
    cleaned = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    if cleaned and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def make_otp_code() -> str:
    return f"{secrets.randbelow(900000) + 100000}"


def hash_otp(identifier: str, code: str) -> str:
    payload = f"{identifier.lower()}:{code}:{OTP_SECRET}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                profile TEXT NOT NULL,
                notes TEXT,
                phone TEXT,
                email_verified INTEGER NOT NULL DEFAULT 0,
                phone_verified INTEGER NOT NULL DEFAULT 0,
                verification_channel TEXT,
                verification_code_hash TEXT,
                verification_expires_at TEXT,
                verification_attempts INTEGER NOT NULL DEFAULT 0,
                last_code_sent_at TEXT,
                verified_at TEXT,
                source TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        migrations = [
            ("phone", "ALTER TABLE registrations ADD COLUMN phone TEXT"),
            ("email_verified", "ALTER TABLE registrations ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0"),
            ("phone_verified", "ALTER TABLE registrations ADD COLUMN phone_verified INTEGER NOT NULL DEFAULT 0"),
            ("verification_channel", "ALTER TABLE registrations ADD COLUMN verification_channel TEXT"),
            ("verification_code_hash", "ALTER TABLE registrations ADD COLUMN verification_code_hash TEXT"),
            ("verification_expires_at", "ALTER TABLE registrations ADD COLUMN verification_expires_at TEXT"),
            ("verification_attempts", "ALTER TABLE registrations ADD COLUMN verification_attempts INTEGER NOT NULL DEFAULT 0"),
            ("last_code_sent_at", "ALTER TABLE registrations ADD COLUMN last_code_sent_at TEXT"),
            ("verified_at", "ALTER TABLE registrations ADD COLUMN verified_at TEXT"),
        ]
        for column_name, ddl in migrations:
            if not column_exists(conn, "registrations", column_name):
                conn.execute(ddl)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registration_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registration_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (registration_id) REFERENCES registrations(id)
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_registrations_phone_unique ON registrations(phone) WHERE phone IS NOT NULL")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_settings (
                id INTEGER PRIMARY KEY DEFAULT 1,
                settings_json TEXT NOT NULL DEFAULT '{}',
                webhook_key TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket INTEGER,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                lots REAL NOT NULL,
                entry_price REAL,
                exit_price REAL,
                sl REAL,
                tp REAL,
                pnl REAL,
                status TEXT NOT NULL DEFAULT 'open',
                source TEXT DEFAULT 'tradingview',
                opened_at TEXT NOT NULL,
                closed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                processed_at TEXT,
                result_json TEXT
            )
            """
        )
        # Ensure at least one bot_settings row with a webhook key
        existing_bot = conn.execute("SELECT id FROM bot_settings WHERE id=1").fetchone()
        if not existing_bot:
            wk = secrets.token_urlsafe(24)
            conn.execute(
                "INSERT OR IGNORE INTO bot_settings (id, settings_json, webhook_key, active) VALUES (1,'{}',?,0)",
                (wk,),
            )
        conn.commit()


def send_email_code(recipient_email: str, code: str, full_name: str) -> tuple[bool, str]:
    subject = "EMPIREX OS Verification Code"
    body = (
        f"שלום {full_name},\n\n"
        f"קוד האימות שלך הוא: {code}\n"
        f"הקוד תקף ל-{OTP_EXPIRY_MINUTES} דקות.\n\n"
        "אם לא ביקשת הרשמה, אפשר להתעלם מהמייל הזה."
    )

    if not (SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD):
        if APP_ENV != "production":
            print(f"[DEV OTP EMAIL] to={recipient_email} code={code}")
            return True, "DEV mode: code printed in server logs"
        return False, "SMTP not configured"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = recipient_email
    msg.set_content(body)

    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15, context=ssl.create_default_context()) as server:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        return True, "Verification email sent"
    except Exception as exc:  # noqa: BLE001
        return False, f"Email send failed: {exc}"


def send_sms_code(phone: str, code: str) -> tuple[bool, str]:
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
        if APP_ENV != "production":
            print(f"[DEV OTP SMS] to={phone} code={code}")
            return True, "DEV mode: SMS code printed in server logs"
        return False, "Twilio not configured"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    payload = urlencode(
        {
            "To": phone,
            "From": TWILIO_FROM_NUMBER,
            "Body": f"Your EMPIREX OS verification code is: {code}",
        }
    ).encode("utf-8")

    auth_value = base64.b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode("utf-8")).decode("ascii")
    request = Request(url, data=payload, method="POST")
    request.add_header("Authorization", f"Basic {auth_value}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310
            if 200 <= response.status < 300:
                return True, "Verification SMS sent"
    except Exception as exc:  # noqa: BLE001
        return False, f"SMS send failed: {exc}"

    return False, "SMS send failed"


def parse_symbols(parsed_path: str, default_symbols: list[str]) -> list[str]:
    parsed = urlparse(parsed_path)
    query = parse_qs(parsed.query)
    raw = (query.get("symbols") or [""])[0]
    symbols = [item.strip().upper() for item in raw.split(",") if item.strip()]
    return symbols or default_symbols


def parse_limit(parsed_path: str, default: int = 30, minimum: int = 1, maximum: int = 400) -> int:
    parsed = urlparse(parsed_path)
    query = parse_qs(parsed.query)
    raw = (query.get("limit") or [str(default)])[0]
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def fetch_json(url: str) -> dict:
    request = Request(url, headers=HTTP_HEADERS)
    with urlopen(request, timeout=12) as response:  # noqa: S310
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def post_json(url: str, payload: dict) -> dict:
    raw_payload = json.dumps(payload).encode("utf-8")
    request = Request(url, data=raw_payload, method="POST", headers={**HTTP_HEADERS, "Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:  # noqa: S310
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def fetch_yahoo_spark(symbols: list[str], interval: str = "5m", range_value: str = "1d") -> dict[str, list[float]]:
    if not symbols:
        return {}

    query_symbols = ",".join(symbols)
    payload = fetch_json(f"https://query1.finance.yahoo.com/v7/finance/spark?symbols={query_symbols}&interval={interval}&range={range_value}")
    results = ((payload.get("spark") or {}).get("result")) or []
    by_symbol: dict[str, list[float]] = {}

    for raw in results:
        symbol = str((raw or {}).get("symbol") or "").upper()
        if not symbol:
            continue
        response_list = (raw or {}).get("response") or []
        if not response_list:
            continue
        response = response_list[0]
        closes = (((response.get("indicators") or {}).get("quote") or [{}])[0].get("close")) or []
        cleaned = [float(value) for value in closes if isinstance(value, (int, float))]
        if cleaned:
            by_symbol[symbol.upper()] = cleaned[-60:]
    return by_symbol


def to_yahoo_forex_ticker(display_symbol: str) -> str:
    compact = display_symbol.replace("/", "").upper()
    return f"{compact}=X"


def fetch_yahoo_candles(symbol: str, interval: str = "5m", range_: str = "1d") -> list[dict]:
    """Fetch real OHLC candlestick data from Yahoo Finance v8 chart API."""
    allowed_intervals = {"1m", "2m", "5m", "15m", "30m", "60m", "1h", "1d", "1wk"}
    allowed_ranges = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y"}
    safe_interval = interval if interval in allowed_intervals else "5m"
    safe_range = range_ if range_ in allowed_ranges else "1d"
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval={safe_interval}&range={safe_range}&includePrePost=false"
    )
    yf_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        req = Request(url, headers=yf_headers)
        with urlopen(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        result = ((data.get("chart") or {}).get("result")) or []
        if not result:
            return []
        r = result[0]
        timestamps = r.get("timestamp") or []
        quote = (((r.get("indicators") or {}).get("quote")) or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        candles: list[dict] = []
        for i, ts in enumerate(timestamps):
            o = opens[i] if i < len(opens) else None
            h = highs[i] if i < len(highs) else None
            lo = lows[i] if i < len(lows) else None
            c = closes[i] if i < len(closes) else None
            if None in (o, h, lo, c):
                continue
            try:
                candles.append({
                    "time": int(ts),
                    "open": round(float(o), 5),
                    "high": round(float(h), 5),
                    "low": round(float(lo), 5),
                    "close": round(float(c), 5),
                })
            except (TypeError, ValueError):
                continue
        return candles
    except Exception as exc:  # noqa: BLE001
        print(f"[candles] {symbol} {safe_interval}/{safe_range} error: {exc}")
        return []


def enrich_with_history(items: list[dict], type_name: str) -> list[dict]:
    if not items:
        return items

    if type_name == "fx":
        ticker_map = {to_yahoo_forex_ticker(item["symbol"]): item["symbol"] for item in items}
    else:
        ticker_map = {str(item["symbol"]).upper(): str(item["symbol"]).upper() for item in items}

    spark = fetch_yahoo_spark(list(ticker_map.keys()))
    by_display = {ticker_map[ticker]: values for ticker, values in spark.items() if ticker in ticker_map}

    enriched: list[dict] = []
    for item in items:
        display_symbol = str(item.get("symbol", "")).upper()
        item_copy = dict(item)
        item_copy["history"] = by_display.get(display_symbol, [])
        enriched.append(item_copy)
    return enriched


def safe_pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100.0


def latest_and_previous_rates(to_currencies: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    to_list = ",".join(sorted(set(to_currencies)))
    latest_url = f"https://api.frankfurter.app/latest?from=USD&to={to_list}"
    prev_date = (utc_now() - timedelta(days=1)).date().isoformat()
    prev_url = f"https://api.frankfurter.app/{prev_date}?from=USD&to={to_list}"

    latest = fetch_json(latest_url)
    previous = fetch_json(prev_url)

    latest_rates = latest.get("rates") or {}
    previous_rates = previous.get("rates") or {}
    if not latest_rates or not previous_rates:
        raise ValueError("Missing FX rates from provider")
    return latest_rates, previous_rates


def fetch_live_fx_data(symbols: list[str]) -> list[dict]:
    wanted = [symbol for symbol in symbols if symbol in FX_BASE]
    if not wanted:
        return []

    latest_usd, previous_usd = latest_and_previous_rates(["EUR", "GBP", "JPY", "AUD", "CAD"])

    def pair_value(pair: str, rates: dict[str, float]) -> float:
        if pair == "EURUSD":
            return 1.0 / rates["EUR"]
        if pair == "GBPUSD":
            return 1.0 / rates["GBP"]
        if pair == "USDJPY":
            return rates["JPY"]
        if pair == "AUDUSD":
            return 1.0 / rates["AUD"]
        if pair == "USDCAD":
            return rates["CAD"]
        if pair == "EURGBP":
            return rates["GBP"] / rates["EUR"]
        raise KeyError(pair)

    data: list[dict] = []
    for symbol in wanted:
        current_price = pair_value(symbol, latest_usd)
        previous_price = pair_value(symbol, previous_usd)
        meta = FX_BASE[symbol]
        data.append(
            {
                "symbol": meta["symbol"],
                "name": meta["name"],
                "price": round(current_price, 5),
                "change": round(safe_pct_change(current_price, previous_price), 2),
                "live": True,
                "source": "live-external",
            }
        )
    return data


def fetch_top_forex_from_tradingview(limit: int) -> list[dict]:
    payload = {
        "filter": [
            {"left": "type", "operation": "equal", "right": "forex"},
            {"left": "exchange", "operation": "nempty"},
        ],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name", "description", "close", "change", "volume"],
        "sort": {"sortBy": "volume", "sortOrder": "desc"},
        "range": [0, max(0, limit - 1)],
    }

    response = post_json(TV_FOREX_SCAN_URL, payload)
    rows = response.get("data") or []
    data: list[dict] = []
    for row in rows:
        symbol_full = str(row.get("s", ""))
        symbol = symbol_full.split(":")[-1].upper()
        fields = row.get("d") or []
        if len(fields) < 5:
            continue

        price = fields[2]
        change = fields[3]
        if price is None or change is None:
            continue

        display_symbol = symbol
        if len(symbol) == 6 and symbol.isalpha():
            display_symbol = f"{symbol[:3]}/{symbol[3:]}"

        data.append(
            {
                "symbol": display_symbol,
                "name": fields[1] or fields[0] or symbol,
                "price": round(float(price), 5),
                "change": round(float(change), 2),
                "volume": float(fields[4] or 0),
                "live": True,
                "source": "live-external",
            }
        )
    return data[:limit]


def fetch_live_stock_data(symbols: list[str]) -> list[dict]:
    wanted = [symbol for symbol in symbols if symbol in STOCK_BASE]
    if not wanted:
        return []

    symbols_param = ",".join(wanted)
    data: list[dict] = []

    try:
        payload = fetch_json(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols_param}")
        results = ((payload.get("quoteResponse") or {}).get("result")) or []
        by_symbol = {str(item.get("symbol", "")).upper(): item for item in results}

        for symbol in wanted:
            item = by_symbol.get(symbol)
            if not item:
                continue

            price = item.get("regularMarketPrice")
            change_pct = item.get("regularMarketChangePercent")
            if price is None or change_pct is None:
                continue

            meta = STOCK_BASE[symbol]
            data.append(
                {
                    "symbol": symbol,
                    "name": item.get("shortName") or meta["name"],
                    "price": round(float(price), 2),
                    "change": round(float(change_pct), 2),
                    "currency": item.get("currency") or meta.get("currency") or "USD",
                    "live": True,
                    "source": "live-external",
                }
            )
    except Exception:
        data = []

    if data:
        return data

    # Secondary free provider fallback for real prices (daily interval)
    by_symbol: dict[str, dict] = {}
    for symbol in wanted:
        meta = STOCK_BASE[symbol]
        stooq_symbol = symbol.lower() + ".us"
        request = Request(f"https://stooq.com/q/l/?s={stooq_symbol}&f=sd2t2ohlcv&h&e=csv", headers=HTTP_HEADERS)
        try:
            with urlopen(request, timeout=12) as response:  # noqa: S310
                csv_text = response.read().decode("utf-8").strip()
        except Exception:
            continue

        lines = [line for line in csv_text.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        parts = [part.strip() for part in lines[1].split(",")]
        if len(parts) < 9:
            continue

        try:
            close_price = float(parts[6])
            open_price = float(parts[4])
        except ValueError:
            continue

        change_pct = safe_pct_change(close_price, open_price)
        by_symbol[symbol] = {
            "symbol": symbol,
            "name": meta["name"],
            "price": round(close_price, 2),
            "change": round(change_pct, 2),
            "currency": meta.get("currency") or "USD",
            "live": True,
            "source": "live-external",
        }

    return [by_symbol[symbol] for symbol in wanted if symbol in by_symbol]


def fetch_top_stocks_from_tradingview(limit: int) -> list[dict]:
    payload = {
        "filter": [
            {"left": "type", "operation": "equal", "right": "stock"},
            {"left": "subtype", "operation": "nempty"},
        ],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name", "description", "close", "change", "volume", "currency"],
        "sort": {"sortBy": "volume", "sortOrder": "desc"},
        "range": [0, max(0, limit - 1)],
    }

    response = post_json(TV_STOCKS_SCAN_URL, payload)
    rows = response.get("data") or []
    data: list[dict] = []
    for row in rows:
        symbol_full = str(row.get("s", ""))
        symbol = symbol_full.split(":")[-1].upper()
        fields = row.get("d") or []
        if len(fields) < 6:
            continue

        price = fields[2]
        change = fields[3]
        if price is None or change is None:
            continue

        data.append(
            {
                "symbol": symbol,
                "name": fields[1] or fields[0] or symbol,
                "price": round(float(price), 2),
                "change": round(float(change), 2),
                "volume": float(fields[4] or 0),
                "currency": fields[5] or "USD",
                "live": True,
                "source": "live-external",
            }
        )
    return data[:limit]


# ── Market data in-memory cache (TTL = 20s) ──────────────────────────────────
_market_cache: dict = {}
_MARKET_CACHE_TTL = 20.0  # seconds
_cache_lock = threading.Lock()


def cached_market(key: str, fetch_fn):
    """Return cached result or call fetch_fn and cache the result."""
    with _cache_lock:
        entry = _market_cache.get(key)
        if entry and (time.monotonic() - entry[0]) < _MARKET_CACHE_TTL:
            return entry[1]
    data = fetch_fn()
    with _cache_lock:
        _market_cache[key] = (time.monotonic(), data)
    return data
# ─────────────────────────────────────────────────────────────────────────────


def get_fx_data(symbols: list[str], limit: int = 30) -> list[dict]:
    if not symbols:
        try:
            dynamic = fetch_top_forex_from_tradingview(limit)
        except Exception:
            dynamic = []
        if dynamic:
            try:
                enriched = enrich_with_history(dynamic, "fx")
                with_history = [item for item in enriched if len(item.get("history") or []) > 3]
                if len(with_history) >= min(3, limit):
                    return with_history[:limit]

                fallback_symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "EURGBP"]
                fallback_live = fetch_live_fx_data(fallback_symbols)
                fallback_enriched = enrich_with_history(fallback_live, "fx")
                merged: list[dict] = []
                seen: set[str] = set()
                for item in [*with_history, *fallback_enriched]:
                    symbol_key = str(item.get("symbol", ""))
                    if symbol_key in seen:
                        continue
                    seen.add(symbol_key)
                    merged.append(item)
                return merged[:limit]
            except Exception:
                return dynamic

    try:
        live_data = fetch_live_fx_data(symbols)
    except Exception:
        live_data = []

    if live_data:
        requested = {symbol for symbol in symbols if symbol in FX_BASE}
        resolved = {item["symbol"].replace("/", "") for item in live_data}
        missing = requested - resolved
        for symbol in missing:
            fallback = dict(FX_BASE[symbol])
            fallback["live"] = False
            fallback["source"] = "fallback"
            live_data.append(fallback)
        try:
            return enrich_with_history(live_data, "fx")
        except Exception:
            return live_data

    data: list[dict] = []
    for symbol in symbols:
        if symbol not in FX_BASE:
            continue
        fallback = dict(FX_BASE[symbol])
        fallback["live"] = False
        fallback["source"] = "fallback"
        data.append(fallback)
    fallback_data = data[:limit]
    try:
        return enrich_with_history(fallback_data, "fx")
    except Exception:
        return fallback_data


def get_stock_data(symbols: list[str], limit: int = 30) -> list[dict]:
    if not symbols:
        try:
            dynamic = fetch_top_stocks_from_tradingview(limit)
        except Exception:
            dynamic = []
        if dynamic:
            try:
                enriched = enrich_with_history(dynamic, "stock")
                with_history = [item for item in enriched if len(item.get("history") or []) > 3]
                if len(with_history) >= min(3, limit):
                    return with_history[:limit]

                fallback_symbols = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "TSLA", "GOOGL", "AMD", "NFLX", "AVGO"]
                fallback_live = fetch_live_stock_data(fallback_symbols)
                fallback_enriched = enrich_with_history(fallback_live, "stock")
                merged: list[dict] = []
                seen: set[str] = set()
                for item in [*with_history, *fallback_enriched]:
                    symbol_key = str(item.get("symbol", ""))
                    if symbol_key in seen:
                        continue
                    seen.add(symbol_key)
                    merged.append(item)
                return merged[:limit]
            except Exception:
                return dynamic

    try:
        live_data = fetch_live_stock_data(symbols)
    except Exception:
        live_data = []

    if live_data:
        requested = {symbol for symbol in symbols if symbol in STOCK_BASE}
        resolved = {item["symbol"] for item in live_data}
        missing = requested - resolved
        for symbol in missing:
            fallback = dict(STOCK_BASE[symbol])
            fallback["live"] = False
            fallback["source"] = "fallback"
            live_data.append(fallback)
        try:
            return enrich_with_history(live_data, "stock")
        except Exception:
            return live_data

    data: list[dict] = []
    for symbol in symbols:
        if symbol not in STOCK_BASE:
            continue
        fallback = dict(STOCK_BASE[symbol])
        fallback["live"] = False
        fallback["source"] = "fallback"
        data.append(fallback)
    fallback_data = data[:limit]
    try:
        return enrich_with_history(fallback_data, "stock")
    except Exception:
        return fallback_data


# ── SSE infrastructure ────────────────────────────────────────────────────────
_sse_queues: list = []
_sse_queues_lock = threading.Lock()


def _sse_push(data: dict) -> None:
    msg = json.dumps(data, ensure_ascii=False)
    with _sse_queues_lock:
        dead = []
        for q in _sse_queues:
            try:
                q.put_nowait(msg)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                _sse_queues.remove(q)
            except ValueError:
                pass


def _market_broadcast_thread() -> None:
    """Background thread: pushes market data to SSE clients every 3 seconds."""
    while True:
        try:
            fx_key = "fx:10:"
            st_key = "stocks:10:"
            with _cache_lock:
                fx_entry = _market_cache.get(fx_key)
                st_entry = _market_cache.get(st_key)
                fx_ok = fx_entry and (time.monotonic() - fx_entry[0]) < 6.0
                st_ok = st_entry and (time.monotonic() - st_entry[0]) < 6.0
            if fx_ok and st_ok:
                fx_data = fx_entry[1]  # type: ignore[index]
                st_data = st_entry[1]  # type: ignore[index]
            else:
                fx_data = get_fx_data([], limit=10)
                st_data = get_stock_data([], limit=10)
                with _cache_lock:
                    _market_cache[fx_key] = (time.monotonic(), fx_data)
                    _market_cache[st_key] = (time.monotonic(), st_data)
            _sse_push({"type": "market", "fx": fx_data, "stocks": st_data, "ts": time.time()})
        except Exception as exc:
            print(f"[SSE market] {exc}")
        time.sleep(3)


# ── Bot Engine ─────────────────────────────────────────────────────────────────

def _queue_signal(signal: dict) -> int:
    """Store a TradingView signal in the queue for the local agent to execute."""
    now_iso = utc_iso(utc_now())
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO signal_queue (signal_json, status, created_at) VALUES (?, 'pending', ?)",
            (json.dumps(signal, ensure_ascii=False), now_iso),
        )
        conn.commit()
        return cur.lastrowid


def _calc_lots_from_dollar_risk(sym_info: object, sl_price: float, entry_price: float, sl_dollars: float) -> float:
    """Calculate lot size so that hitting the SL costs approximately sl_dollars."""
    try:
        is_5digit = getattr(sym_info, "digits", 5) in (5, 3)
        pip = getattr(sym_info, "point", 0.00001) * (10 if is_5digit else 1)
        sl_pips = abs(entry_price - sl_price) / pip
        if sl_pips < 0.01:
            return 0.0
        tick_val = getattr(sym_info, "trade_tick_value", 0)
        tick_size = getattr(sym_info, "trade_tick_size", 0)
        if tick_size <= 0 or tick_val <= 0:
            return 0.0
        pip_value_per_lot = tick_val * pip / tick_size
        if pip_value_per_lot <= 0:
            return 0.0
        lots = sl_dollars / (sl_pips * pip_value_per_lot)
        step = getattr(sym_info, "volume_step", 0.01)
        if step <= 0:
            step = 0.01
        lots = round(round(lots / step) * step, 2)
        v_min = getattr(sym_info, "volume_min", 0.01)
        v_max = getattr(sym_info, "volume_max", 100.0)
        lots = max(v_min, min(lots, v_max))
        return round(lots, 2)
    except Exception:
        return 0.0


class BotEngine:
    """EMPIREX Trading Bot: FTMO rules, MT5 execution, trade logging, position monitoring."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._monitor_thread: threading.Thread | None = None
        self._creds: dict | None = None
        self._settings: dict = {}

    def start(self, creds: dict, settings: dict) -> tuple[bool, str]:
        with self._lock:
            if self._running:
                return False, "Bot is already running"
            if not creds or not creds.get("server") or not creds.get("login") or not creds.get("password"):
                return False, "Broker credentials not found — connect a broker first"
            self._creds = creds
            self._settings = settings
            self._running = True
            t = threading.Thread(target=self._monitor_loop, daemon=True, name="empirex-bot-monitor")
            self._monitor_thread = t
            t.start()
            self._update_db_active(True)
            return True, "Bot started"

    def stop(self) -> None:
        with self._lock:
            self._running = False
        self._update_db_active(False)

    def is_running(self) -> bool:
        return self._running

    def update_settings(self, settings: dict) -> None:
        with self._lock:
            self._settings = settings

    def execute_signal(self, signal: dict) -> tuple[bool, str]:
        """Process a TradingView webhook signal and execute on MT5."""
        if not self._running:
            return False, "Bot is not active — start the bot first"
        creds = self._creds
        if not creds:
            return False, "No broker credentials"
        symbol_raw = str(signal.get("symbol", "")).strip().upper().replace("/", "").replace(":", "")
        if not symbol_raw:
            return False, "Missing symbol"
        action = str(signal.get("action", "")).strip().lower()
        if action in ("long", "buy"):
            action = "buy"
        elif action in ("short", "sell"):
            action = "sell"
        else:
            return False, f"Invalid action: {action}"

        # Determine sl_dollars from sl_level (1/2/3)
        sl_level = int(signal.get("sl_level", 0) or 0)
        if sl_level in (1, 2, 3):
            sl_dollars: float | None = float(self._settings.get(f"sl{sl_level}_dollars", self._settings.get("sl1_dollars", 50)))
        else:
            sl_dollars = None

        # Default lots — may be overridden in _mt5_execute based on sl_dollars
        lots = round(max(0.01, min(float(signal.get("lots", self._settings.get("default_lots", 0.01))), 100.0)), 2)
        sl = signal.get("sl")
        tp = signal.get("tp")
        comment = str(signal.get("comment", "EMPIREX BOT"))[:31]
        ok, msg = self._check_ftmo_rules()
        if not ok:
            _sse_push({"type": "bot_blocked", "reason": msg, "ts": time.time()})
            return False, f"FTMO rule violation: {msg}"
        return self._mt5_execute(creds, symbol_raw, action, lots, sl, tp, comment, sl_dollars)

    def _check_ftmo_rules(self) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        if now.weekday() >= 5:
            return False, "מסחר בסוף שבוע אסור לפי חוקי FTMO"
        settings = self._settings
        today = now.date().isoformat()
        max_pos = int(settings.get("max_positions", 5))
        try:
            with get_conn() as conn:
                open_ct = conn.execute("SELECT COUNT(*) FROM bot_trades WHERE status='open'").fetchone()[0]
            if open_ct >= max_pos:
                return False, f"הגעת למגבלת {max_pos} פוזיציות פתוחות"
        except Exception:
            pass
        max_daily = int(settings.get("max_daily_trades", 20))
        try:
            with get_conn() as conn:
                daily_ct = conn.execute("SELECT COUNT(*) FROM bot_trades WHERE date(opened_at)=?", (today,)).fetchone()[0]
            if daily_ct >= max_daily:
                return False, f"הגעת למגבלת {max_daily} עסקאות ביום"
        except Exception:
            pass
        # Daily profit target / loss limit in dollars
        daily_profit_target = float(settings.get("daily_profit_target", 0) or 0)
        daily_loss_limit = float(settings.get("daily_loss_limit", 0) or 0)
        if daily_profit_target > 0 or daily_loss_limit > 0:
            try:
                with get_conn() as conn:
                    today_pnl = conn.execute(
                        "SELECT COALESCE(SUM(pnl),0) FROM bot_trades WHERE date(closed_at)=? AND status='closed'",
                        (today,)
                    ).fetchone()[0] or 0.0
                if daily_profit_target > 0 and today_pnl >= daily_profit_target:
                    return False, f"יעד הרווח היומי הושג: ${today_pnl:.2f} / ${daily_profit_target:.2f}"
                if daily_loss_limit > 0 and today_pnl <= -daily_loss_limit:
                    return False, f"מגבלת ההפסד היומי הושגה: ${abs(today_pnl):.2f} / ${daily_loss_limit:.2f}"
            except Exception:
                pass
        return True, ""

    def _mt5_execute(self, creds: dict, symbol: str, action: str, lots: float, sl, tp, comment: str, sl_dollars: float | None = None) -> tuple[bool, str]:
        if not _MT5_AVAILABLE:
            return False, "MetaTrader5 library not installed on server"
        if not _is_mt5_terminal_running():
            return False, "MT5 terminal is not running"
        try:
            login_int = int(creds["login"])
        except (ValueError, TypeError):
            return False, "Invalid login ID"
        with _MT5_LOCK:
            try:
                if not _mt5.initialize(server=creds["server"], login=login_int, password=creds["password"]):
                    err = _mt5.last_error()
                    _mt5.shutdown()
                    return False, f"MT5 connection failed: {err}"
                sym_info = _mt5.symbol_info(symbol)
                if not sym_info:
                    _mt5.shutdown()
                    return False, f"Symbol '{symbol}' not found in MT5"
                if not sym_info.visible:
                    _mt5.symbol_select(symbol, True)
                tick = _mt5.symbol_info_tick(symbol)
                if not tick:
                    _mt5.shutdown()
                    return False, f"Cannot get price for {symbol}"
                order_type = _mt5.ORDER_TYPE_BUY if action == "buy" else _mt5.ORDER_TYPE_SELL
                price = tick.ask if action == "buy" else tick.bid

                # Calculate lots from dollar risk if sl price and sl_dollars provided
                sl_price_float = None
                if sl is not None:
                    try:
                        sl_price_float = float(sl)
                    except (TypeError, ValueError):
                        sl_price_float = None
                if sl_dollars and sl_price_float is not None:
                    calc = _calc_lots_from_dollar_risk(sym_info, sl_price_float, price, sl_dollars)
                    if calc > 0:
                        lots = calc

                # Auto-compute TP from tp_dollars if not supplied
                tp_price_float = None
                if tp is not None:
                    try:
                        tp_price_float = float(tp)
                    except (TypeError, ValueError):
                        tp_price_float = None
                if tp_price_float is None and sl_price_float is not None and sl_dollars:
                    tp_dollars = float(self._settings.get("tp_dollars", sl_dollars * 2))
                    sl_dist = abs(price - sl_price_float)
                    if sl_dist > 0 and tp_dollars > 0:
                        tp_dist = sl_dist * (tp_dollars / sl_dollars)
                        tp_price_float = round(price + tp_dist if action == "buy" else price - tp_dist, sym_info.digits)

                request: dict = {
                    "action": _mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": lots,
                    "type": order_type,
                    "price": price,
                    "deviation": 30,
                    "magic": 20260512,
                    "comment": comment,
                    "type_time": _mt5.ORDER_TIME_GTC,
                    "type_filling": _mt5.ORDER_FILLING_IOC,
                }
                if sl_price_float is not None:
                    request["sl"] = round(sl_price_float, sym_info.digits)
                if tp_price_float is not None:
                    request["tp"] = round(tp_price_float, sym_info.digits)
                result = _mt5.order_send(request)
                _mt5.shutdown()
                if result and result.retcode == _mt5.TRADE_RETCODE_DONE:
                    ticket = int(result.order)
                    now_iso = utc_iso(utc_now())
                    with get_conn() as conn:
                        conn.execute(
                            "INSERT INTO bot_trades (ticket,symbol,direction,lots,entry_price,sl,tp,status,source,opened_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (ticket, symbol, action, lots, round(price, 5), request.get("sl"), request.get("tp"), "open", "tradingview", now_iso),
                        )
                        conn.commit()
                    _sse_push({"type": "bot_trade_opened", "ticket": ticket, "symbol": symbol, "direction": action, "lots": lots, "price": round(price, 5), "ts": time.time()})
                    return True, f"{symbol} {action.upper()} {lots}L @ {round(price, 5)} (ticket #{ticket})"
                else:
                    code = result.retcode if result else "unknown"
                    cmt = result.comment if result else ""
                    return False, f"MT5 order failed — retcode={code}: {cmt}"
            except Exception as exc:
                try:
                    _mt5.shutdown()
                except Exception:
                    pass
                return False, f"MT5 error: {exc}"

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                self._monitor_tick()
            except Exception as exc:
                print(f"[Bot monitor] {exc}")
            time.sleep(5)

    def _monitor_tick(self) -> None:
        creds = self._creds
        if not creds or not _MT5_AVAILABLE or not _is_mt5_terminal_running():
            return
        try:
            with get_conn() as conn:
                open_rows = conn.execute(
                    "SELECT id,ticket,symbol,direction,lots,entry_price FROM bot_trades WHERE status='open'"
                ).fetchall()
        except Exception:
            return
        if not open_rows:
            return
        try:
            login_int = int(creds["login"])
        except (ValueError, TypeError):
            return
        with _MT5_LOCK:
            try:
                if not _mt5.initialize(server=creds["server"], login=login_int, password=creds["password"]):
                    _mt5.shutdown()
                    return
                mt5_positions = {p.ticket: p for p in (_mt5.positions_get() or [])}
                symbols_needed = {str(r["symbol"]) for r in open_rows}
                ticks: dict = {}
                for sym in symbols_needed:
                    tick = _mt5.symbol_info_tick(sym)
                    if tick:
                        ticks[sym] = {"bid": round(tick.bid, 5), "ask": round(tick.ask, 5)}
                acct = _mt5.account_info()
                acct_data = None
                if acct:
                    acct_data = {"balance": round(float(acct.balance), 2), "equity": round(float(acct.equity), 2), "profit": round(float(acct.profit), 2)}
                _mt5.shutdown()
                now_iso = utc_iso(utc_now())
                positions_data = []
                with get_conn() as conn:
                    for row in open_rows:
                        tid = int(row["id"])
                        ticket = row["ticket"]
                        sym = row["symbol"]
                        if ticket and ticket not in mt5_positions:
                            conn.execute(
                                "UPDATE bot_trades SET status='closed', closed_at=? WHERE id=?",
                                (now_iso, tid),
                            )
                            conn.commit()
                            _sse_push({"type": "bot_trade_closed", "ticket": ticket, "symbol": sym, "ts": time.time()})
                        else:
                            mt5_pos = mt5_positions.get(ticket)
                            live_pnl = round(float(mt5_pos.profit), 2) if mt5_pos else None
                            positions_data.append({"id": tid, "ticket": ticket, "symbol": sym, "direction": row["direction"], "lots": row["lots"], "entry_price": row["entry_price"], "pnl": live_pnl, **ticks.get(sym, {})})
                _sse_push({"type": "bot_positions", "positions": positions_data, "account": acct_data, "ts": time.time()})
            except Exception as exc:
                try:
                    _mt5.shutdown()
                except Exception:
                    pass
                print(f"[Bot monitor tick] {exc}")

    @staticmethod
    def _update_db_active(active: bool) -> None:
        try:
            with get_conn() as conn:
                conn.execute("UPDATE bot_settings SET active=? WHERE id=1", (1 if active else 0,))
                conn.commit()
        except Exception:
            pass


_bot_engine = BotEngine()
# ─────────────────────────────────────────────────────────────────────────────


def create_session(conn: sqlite3.Connection, registration_id: int) -> str:
    token = secrets.token_urlsafe(36)
    now = utc_now()
    expires_at = now + timedelta(days=7)
    conn.execute(
        "INSERT INTO registration_sessions (registration_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (registration_id, token, utc_iso(now), utc_iso(expires_at)),
    )
    return token


class EmpirexHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _allowed_origins(self) -> set[str]:
        origins = {"http://localhost:5501", "http://127.0.0.1:5501"}
        app_base_url = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
        if app_base_url:
            origins.add(app_base_url)
        return origins

    def _apply_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "").strip().rstrip("/")
        if not origin or origin not in self._allowed_origins():
            return
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Vary", "Origin")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if APP_ENV == "production":
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        super().end_headers()

    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._apply_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _send_verification(self, channel: str, email: str, phone: str, code: str, full_name: str) -> tuple[bool, str]:
        if channel == "phone":
            return send_sms_code(phone, code)
        return send_email_code(email, code, full_name)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._apply_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/market/stream":
            # SSE: send real-time market + bot updates to browser
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self._apply_cors_headers()
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            q: queue.Queue = queue.Queue(maxsize=20)
            with _sse_queues_lock:
                _sse_queues.append(q)
            try:
                while True:
                    try:
                        msg = q.get(timeout=15)
                        self.wfile.write(f"data: {msg}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except Exception:
                pass
            finally:
                with _sse_queues_lock:
                    try:
                        _sse_queues.remove(q)
                    except ValueError:
                        pass
            return

        if parsed.path == "/api/bot/settings":
            with get_conn() as conn:
                row = conn.execute("SELECT settings_json, webhook_key, active FROM bot_settings WHERE id=1").fetchone()
            if row:
                settings = json.loads(row["settings_json"] or "{}")
                settings["_active"] = bool(row["active"]) or _bot_engine.is_running()
                settings["_webhookKey"] = row["webhook_key"]
            else:
                wk = secrets.token_urlsafe(24)
                with get_conn() as conn:
                    conn.execute("INSERT OR IGNORE INTO bot_settings (id, settings_json, webhook_key, active) VALUES (1,'{}',?,0)", (wk,))
                    conn.commit()
                settings = {"_active": False, "_webhookKey": wk}
            self._json_response(200, {"ok": True, "data": settings})
            return

        if parsed.path == "/api/bot/status":
            with get_conn() as conn:
                row = conn.execute("SELECT active FROM bot_settings WHERE id=1").fetchone()
                open_trades = conn.execute(
                    "SELECT id,ticket,symbol,direction,lots,entry_price,sl,tp,pnl,opened_at FROM bot_trades WHERE status='open' ORDER BY opened_at DESC"
                ).fetchall()
            self._json_response(200, {"ok": True, "data": {"active": _bot_engine.is_running(), "openTrades": [dict(t) for t in open_trades]}})
            return

        if parsed.path == "/api/bot/trades":
            query = parse_qs(parsed.query)
            limit = min(200, int((query.get("limit") or ["50"])[0]))
            date_filter = (query.get("date") or [""])[0].strip()
            with get_conn() as conn:
                if date_filter:
                    rows = conn.execute(
                        "SELECT * FROM bot_trades WHERE date(opened_at)=? ORDER BY opened_at DESC LIMIT ?",
                        (date_filter, limit),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM bot_trades ORDER BY opened_at DESC LIMIT ?", (limit,)).fetchall()
            self._json_response(200, {"ok": True, "data": [dict(r) for r in rows]})
            return

        if parsed.path == "/api/bot/signals/pending":
            provided_key = parse_qs(parsed.query).get("key", [""])[0] or self.headers.get("X-Agent-Key", "")
            with get_conn() as conn:
                row = conn.execute("SELECT webhook_key FROM bot_settings WHERE id=1").fetchone()
            if not row or not provided_key or not hmac.compare_digest(str(provided_key), str(row["webhook_key"])):
                self._json_response(403, {"ok": False, "error": "Invalid key"})
                return
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, signal_json, created_at FROM signal_queue WHERE status='pending' ORDER BY id ASC LIMIT 20"
                ).fetchall()
                # Mark as 'executing' to avoid double-pick
                ids = [r["id"] for r in rows]
                if ids:
                    conn.execute(f"UPDATE signal_queue SET status='executing' WHERE id IN ({','.join('?'*len(ids))})", ids)
                    conn.commit()
            signals = [{"id": r["id"], "signal": json.loads(r["signal_json"]), "created_at": r["created_at"]} for r in rows]
            self._json_response(200, {"ok": True, "data": signals})
            return

        if parsed.path == "/api/health":
            self._json_response(200, {"ok": True, "service": "empirex-registration-api", "env": APP_ENV})
            return

        if parsed.path == "/api/registrations":
            with get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT id, full_name, email, phone, profile, notes, source,
                           email_verified, phone_verified, verification_channel, created_at
                    FROM registrations
                    ORDER BY id DESC LIMIT 200
                    """
                ).fetchall()

            data = [dict(row) for row in rows]
            self._json_response(200, {"ok": True, "count": len(data), "data": data})
            return

        if parsed.path == "/api/market/fx":
            symbols = parse_symbols(self.path, [])
            limit = parse_limit(self.path, default=30)
            cache_key = f"fx:{limit}:{','.join(sorted(symbols))}"
            data = cached_market(cache_key, lambda: get_fx_data(symbols, limit=limit))
            self._json_response(200, {"ok": True, "source": "empirex-market-api", "count": len(data), "data": data})
            return

        if parsed.path == "/api/market/stocks":
            symbols = parse_symbols(self.path, [])
            limit = parse_limit(self.path, default=30)
            cache_key = f"stocks:{limit}:{','.join(sorted(symbols))}"
            data = cached_market(cache_key, lambda: get_stock_data(symbols, limit=limit))
            self._json_response(200, {"ok": True, "source": "empirex-market-api", "count": len(data), "data": data})
            return

        if parsed.path == "/api/market/candles":
            query = parse_qs(parsed.query)
            symbol = (query.get("symbol") or [""])[0].strip()
            interval = (query.get("interval") or ["5m"])[0].strip()
            range_ = (query.get("range") or ["1d"])[0].strip()
            if not symbol:
                self._json_response(400, {"ok": False, "error": "symbol required"})
                return
            if not re.match(r'^[\w/=\-\.]{1,20}$', symbol):
                self._json_response(400, {"ok": False, "error": "invalid symbol"})
                return
            candles = fetch_yahoo_candles(symbol, interval, range_)
            self._json_response(200, {"ok": True, "symbol": symbol, "interval": interval, "candles": candles})
            return

        if parsed.path == "/api/session/validate":
            query = parse_qs(parsed.query)
            token = (query.get("token") or [""])[0].strip()
            if not token:
                self._json_response(400, {"ok": False, "error": "Missing token"})
                return

            with get_conn() as conn:
                row = conn.execute(
                    """
                    SELECT s.token, s.expires_at, r.id, r.full_name, r.email, r.phone,
                           r.email_verified, r.phone_verified
                    FROM registration_sessions s
                    JOIN registrations r ON r.id = s.registration_id
                    WHERE s.token = ?
                    """,
                    (token,),
                ).fetchone()

            if not row:
                self._json_response(401, {"ok": False, "error": "Invalid session"})
                return

            expires = parse_iso(row["expires_at"])
            if not expires or utc_now() > expires:
                self._json_response(401, {"ok": False, "error": "Session expired"})
                return

            self._json_response(
                200,
                {
                    "ok": True,
                    "data": {
                        "id": row["id"],
                        "fullName": row["full_name"],
                        "email": row["email"],
                        "phone": row["phone"],
                        "emailVerified": bool(row["email_verified"]),
                        "phoneVerified": bool(row["phone_verified"]),
                    },
                },
            )
            return

        # ── Agent API (GET) ─────────────────────────────────────────────
        if parsed.path.startswith("/api/agent/"):
            self._handle_agent_get(parsed)
            return

        super().do_GET()

    def send_response(self, code, message=None):
        super().send_response(code, message)
        # Disable browser caching for all responses so fresh HTML is always served
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/register":
            self._handle_register()
            return

        if parsed.path == "/api/verify-code":
            self._handle_verify_code()
            return

        if parsed.path == "/api/resend-code":
            self._handle_resend_code()
            return

        if parsed.path == "/api/logout":
            self._handle_logout()
            return

        if parsed.path == "/api/bot/settings":
            body = self._read_json_body()
            settings_clean = {k: v for k, v in body.items() if not k.startswith("_")}
            settings_str = json.dumps(settings_clean, ensure_ascii=False)
            with get_conn() as conn:
                # Preserve existing webhook_key — only generate once
                conn.execute(
                    "INSERT INTO bot_settings (id, settings_json, webhook_key, active, updated_at)"
                    " VALUES (1, ?, ?, 0, ?)"
                    " ON CONFLICT(id) DO UPDATE SET"
                    " settings_json=excluded.settings_json,"
                    " updated_at=excluded.updated_at",
                    (settings_str, secrets.token_urlsafe(24), utc_iso(utc_now())),
                )
                conn.commit()
            _bot_engine.update_settings(settings_clean)
            self._json_response(200, {"ok": True})
            return

        if parsed.path == "/api/bot/toggle":
            body = self._read_json_body()
            activate = bool(body.get("active", False))
            creds_raw = body.get("creds")
            settings_raw = body.get("settings") or {}
            if activate:
                if not creds_raw:
                    self._json_response(400, {"ok": False, "error": "Credentials required to start bot"})
                    return
                ok, msg = _bot_engine.start(creds_raw, settings_raw)
                if not ok:
                    self._json_response(400, {"ok": False, "error": msg})
                    return
            else:
                _bot_engine.stop()
            self._json_response(200, {"ok": True, "active": activate})
            return

        if parsed.path == "/api/bot/signals/ack":
            body = self._read_json_body()
            provided_key = str(body.get("key", self.headers.get("X-Agent-Key", ""))).strip()
            with get_conn() as conn:
                row = conn.execute("SELECT webhook_key FROM bot_settings WHERE id=1").fetchone()
            if not row or not provided_key or not hmac.compare_digest(provided_key, str(row["webhook_key"])):
                self._json_response(403, {"ok": False, "error": "Invalid key"})
                return
            sig_id = int(body.get("id", 0))
            ok_exec = bool(body.get("ok", False))
            result = body.get("result") or {}
            now_iso = utc_iso(utc_now())
            with get_conn() as conn:
                conn.execute(
                    "UPDATE signal_queue SET status=?, processed_at=?, result_json=? WHERE id=?",
                    ("done" if ok_exec else "failed", now_iso, json.dumps(result), sig_id),
                )
                if ok_exec and result.get("ticket"):
                    conn.execute(
                        "INSERT INTO bot_trades (ticket,symbol,direction,lots,entry_price,sl,tp,status,source,opened_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (result["ticket"], result.get("symbol",""), result.get("direction",""),
                         result.get("lots",0), result.get("entry_price"), result.get("sl"),
                         result.get("tp"), "open", "agent", now_iso),
                    )
                conn.commit()
            if ok_exec and result.get("ticket"):
                _sse_push({"type": "bot_trade_opened", "ticket": result["ticket"],
                           "symbol": result.get("symbol"), "direction": result.get("direction"),
                           "lots": result.get("lots"), "price": result.get("entry_price"), "ts": time.time()})
            self._json_response(200, {"ok": True})
            return

        if parsed.path == "/api/tradingview/webhook":
            body = self._read_json_body()
            provided_key = str(body.get("key", "")).strip()
            with get_conn() as conn:
                row = conn.execute("SELECT webhook_key FROM bot_settings WHERE id=1").fetchone()
            if not row or not provided_key:
                self._json_response(403, {"ok": False, "error": "Bot not configured or missing key"})
                return
            if not hmac.compare_digest(provided_key, str(row["webhook_key"])):
                self._json_response(403, {"ok": False, "error": "Invalid webhook key"})
                return
            # If MT5 available locally, execute directly; otherwise queue for local agent
            if _MT5_AVAILABLE and _bot_engine.is_running():
                ok, msg = _bot_engine.execute_signal(body)
                if ok:
                    self._json_response(200, {"ok": True, "message": msg})
                else:
                    self._json_response(400, {"ok": False, "error": msg})
            else:
                # Queue signal for local MT5 agent to pick up
                _queue_signal(body)
                self._json_response(200, {"ok": True, "message": "Signal queued for local execution agent"})
            return

        if parsed.path == "/api/broker/connect":
            self._handle_broker_connect()
            return

        if parsed.path == "/api/broker/trades":
            self._handle_broker_trades()
            return

        # ── Agent API (POST) ────────────────────────────────────────────
        if parsed.path.startswith("/api/agent/"):
            self._handle_agent_post(parsed)
            return

        self._json_response(404, {"ok": False, "error": "Route not found"})

    # ── Agent handlers ────────────────────────────────────────────────────
    def _handle_agent_get(self, parsed):
        brain = _get_brain()
        path = parsed.path

        if path == "/api/agent/dashboard":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded. Run agent_database.py first."})
                return
            try:
                data = brain.get_agent_dashboard()
                self._json_response(200, {"ok": True, "data": data})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/market":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                data = brain.get_market_overview()
                self._json_response(200, {"ok": True, "data": data})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/calendar":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                query = parse_qs(parsed.query)
                days = int((query.get("days") or ["3"])[0])
                days = min(max(days, 1), 14)
                data = brain.get_upcoming_events(days_ahead=days)
                self._json_response(200, {"ok": True, "data": data})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/alerts":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                query = parse_qs(parsed.query)
                status = (query.get("status") or [None])[0]
                data = brain.get_alerts(status=status, limit=50)
                self._json_response(200, {"ok": True, "data": data})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/investigations":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                data = brain.get_investigations(limit=20)
                self._json_response(200, {"ok": True, "data": data})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/reports":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                data = brain.get_reports(limit=20)
                self._json_response(200, {"ok": True, "data": data})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/symbol":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                query = parse_qs(parsed.query)
                symbol = (query.get("symbol") or ["EURUSD"])[0].strip().upper()
                if not re.match(r'^[A-Z0-9]{3,10}$', symbol):
                    self._json_response(400, {"ok": False, "error": "Invalid symbol"})
                    return
                data = brain.get_symbol_analysis(symbol)
                corrs = brain.get_correlations(symbol)
                self._json_response(200, {"ok": True, "data": {**data, "correlations": corrs}})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/risk":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                query = parse_qs(parsed.query)
                # Use default demo account for now
                account = {
                    "balance": 10842.75, "equity": 10728.42, "initialBalance": 10000,
                    "dailyPnl": -214.36, "totalPnl": 842.75,
                    "dailyLossLimit": 500, "maxLossLimit": 1000,
                    "openRiskPercent": 1.82, "maxDrawdownPercent": 4.31, "profitTarget": 1000,
                }
                data = {
                    "risk": brain.evaluate_risk(account),
                    "compliance": brain.evaluate_compliance(account),
                }
                self._json_response(200, {"ok": True, "data": data})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/strategy":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                query = parse_qs(parsed.query)
                days = int((query.get("days") or ["30"])[0])
                days = min(max(days, 7), 90)
                strategy = (query.get("strategy") or [None])[0]
                perf = brain.get_strategy_performance(strategy=strategy, days=days)
                sess = brain.get_session_performance(days=days)
                sym  = brain.get_symbol_performance(days=days)
                pnl  = brain.get_daily_pnl_series(days=days)
                self._json_response(200, {"ok": True, "data": {"strategies": perf, "sessions": sess, "symbols": sym, "daily": pnl}})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/briefing":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                data = brain.generate_daily_briefing()
                self._json_response(200, {"ok": True, "data": data})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/chat/history":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                query = parse_qs(parsed.query)
                session_id = (query.get("session") or ["default"])[0].strip()
                history = brain.get_chat_history(session_id, limit=30)
                self._json_response(200, {"ok": True, "data": history})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        self._json_response(404, {"ok": False, "error": "Agent route not found"})

    def _handle_agent_post(self, parsed):
        brain = _get_brain()
        path = parsed.path

        if path == "/api/agent/chat":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded. Run agent_database.py first."})
                return
            try:
                body = self._read_json_body()
                message = str(body.get("message", "")).strip()[:500]
                if not message:
                    self._json_response(400, {"ok": False, "error": "message required"})
                    return
                session_id = str(body.get("sessionId", "default"))[:64]
                context    = body.get("context") or {}
                result = brain.process_chat(message, session_id=session_id, context=context)
                self._json_response(200, {"ok": True, "data": result})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/alerts/update":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                body = self._read_json_body()
                alert_id = str(body.get("id", "")).strip()
                status   = str(body.get("status", "resolved")).strip()
                if status not in ("resolved", "acknowledged", "open"):
                    self._json_response(400, {"ok": False, "error": "Invalid status"})
                    return
                brain.update_alert_status(alert_id, status)
                self._json_response(200, {"ok": True})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        if path == "/api/agent/actions/execute":
            if not brain:
                self._json_response(503, {"ok": False, "error": "Agent brain not loaded."})
                return
            try:
                body = self._read_json_body()
                action_type = str(body.get("actionType", "")).strip()
                params      = body.get("params") or {}
                allowed_actions = {"REDUCE_RISK_MODE", "BLOCK_SYMBOL", "PAUSE_BOT", "RESUME_BOT", "CREATE_JOURNAL_NOTE", "CREATE_ALERT"}
                if action_type not in allowed_actions:
                    self._json_response(400, {"ok": False, "error": f"Unknown action: {action_type}"})
                    return

                result_msg = f"Action {action_type} received"
                if action_type == "CREATE_ALERT":
                    aid = brain.create_alert(
                        params.get("severity", "info"),
                        params.get("category", "manual"),
                        params.get("title", "Manual Alert"),
                        params.get("message", ""),
                        action_required=False
                    )
                    result_msg = f"Alert created: {aid}"
                elif action_type in ("PAUSE_BOT", "RESUME_BOT"):
                    if _bot_engine:
                        if action_type == "PAUSE_BOT":
                            _bot_engine.stop()
                        # RESUME is handled elsewhere
                    result_msg = f"Bot {action_type.lower().replace('_bot','d')}"

                self._json_response(200, {"ok": True, "message": result_msg})
            except Exception as e:
                self._json_response(500, {"ok": False, "error": str(e)})
            return

        self._json_response(404, {"ok": False, "error": "Agent POST route not found"})

    def _handle_register(self) -> None:
        payload = self._read_json_body()
        full_name = str(payload.get("fullName", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        phone = normalize_phone(str(payload.get("phone", "")).strip())
        profile = str(payload.get("profile", "")).strip()
        notes = str(payload.get("notes", "")).strip()
        channel = str(payload.get("verificationChannel", "email")).strip().lower()

        if channel not in {"email", "phone"}:
            self._json_response(400, {"ok": False, "error": "Invalid verification channel"})
            return

        if not full_name or not profile:
            self._json_response(400, {"ok": False, "error": "Missing required fields"})
            return

        if channel == "email" and not email:
            self._json_response(400, {"ok": False, "error": "Email is required for email verification"})
            return

        if channel == "phone" and not phone:
            self._json_response(400, {"ok": False, "error": "Phone is required for phone verification"})
            return

        if not email and phone:
            email = phone_to_virtual_email(phone)

        if email and ("@" not in email or "." not in email) and not email.endswith("@phone.local"):
            self._json_response(400, {"ok": False, "error": "Invalid email"})
            return

        created_at = utc_iso(utc_now())
        user_agent = self.headers.get("User-Agent", "")
        source = self.headers.get("Origin") or self.headers.get("Host", "")

        lookup_sql = "SELECT * FROM registrations WHERE email = ?"
        lookup_params: tuple = (email,)
        if phone:
            lookup_sql = "SELECT * FROM registrations WHERE email = ? OR phone = ?"
            lookup_params = (email, phone)

        code = make_otp_code()
        identifier_for_hash = phone if channel == "phone" else email
        code_hash = hash_otp(identifier_for_hash, code)
        expires_at = utc_iso(utc_now() + timedelta(minutes=OTP_EXPIRY_MINUTES))
        sent_at = utc_iso(utc_now())

        with get_conn() as conn:
            existing = conn.execute(lookup_sql, lookup_params).fetchone()

            if existing:
                already_verified = bool(existing["email_verified"]) if channel == "email" else bool(existing["phone_verified"])
                if already_verified:
                    self._json_response(409, {"ok": False, "error": "User already verified. Please login."})
                    return

                conn.execute(
                    """
                    UPDATE registrations
                    SET full_name = ?, email = ?, phone = ?, profile = ?, notes = ?,
                        verification_channel = ?, verification_code_hash = ?, verification_expires_at = ?,
                        verification_attempts = 0, last_code_sent_at = ?, source = ?, user_agent = ?
                    WHERE id = ?
                    """,
                    (
                        full_name,
                        email,
                        phone or existing["phone"],
                        profile,
                        notes,
                        channel,
                        code_hash,
                        expires_at,
                        sent_at,
                        source,
                        user_agent,
                        existing["id"],
                    ),
                )
                registration_id = int(existing["id"])
            else:
                conn.execute(
                    """
                    INSERT INTO registrations (
                        full_name, email, phone, profile, notes,
                        verification_channel, verification_code_hash, verification_expires_at,
                        verification_attempts, last_code_sent_at, source, user_agent,
                        email_verified, phone_verified, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 0, 0, ?)
                    """,
                    (
                        full_name,
                        email,
                        phone or None,
                        profile,
                        notes,
                        channel,
                        code_hash,
                        expires_at,
                        sent_at,
                        source,
                        user_agent,
                        created_at,
                    ),
                )
                registration_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()

        ok, delivery_message = self._send_verification(channel, email, phone, code, full_name)
        if not ok:
            self._json_response(500, {"ok": False, "error": delivery_message})
            return

        response_payload = {
            "ok": True,
            "message": "Verification code sent",
            "data": {
                "registrationId": registration_id,
                "channel": channel,
                "email": None if email.endswith("@phone.local") else email,
                "phone": phone or None,
                "expiresInMinutes": OTP_EXPIRY_MINUTES,
                "deliveryMessage": delivery_message,
            },
        }

        if APP_ENV != "production":
            response_payload["data"]["devCode"] = code

        self._json_response(201, response_payload)

    def _handle_verify_code(self) -> None:
        payload = self._read_json_body()
        code = str(payload.get("code", "")).strip()
        channel = str(payload.get("verificationChannel", "email")).strip().lower()
        email = str(payload.get("email", "")).strip().lower()
        phone = normalize_phone(str(payload.get("phone", "")).strip())

        if channel not in {"email", "phone"}:
            self._json_response(400, {"ok": False, "error": "Invalid verification channel"})
            return
        if not code:
            self._json_response(400, {"ok": False, "error": "Missing verification code"})
            return

        identifier = email if channel == "email" else phone
        if not identifier:
            self._json_response(400, {"ok": False, "error": "Missing contact identifier"})
            return

        with get_conn() as conn:
            if channel == "email":
                row = conn.execute("SELECT * FROM registrations WHERE email = ?", (email,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM registrations WHERE phone = ?", (phone,)).fetchone()

            if not row:
                self._json_response(404, {"ok": False, "error": "Registration not found"})
                return

            if int(row["verification_attempts"] or 0) >= OTP_MAX_ATTEMPTS:
                self._json_response(429, {"ok": False, "error": "Too many invalid attempts. Request a new code."})
                return

            expires_at = parse_iso(row["verification_expires_at"])
            if not expires_at or utc_now() > expires_at:
                self._json_response(400, {"ok": False, "error": "Verification code expired. Please request a new code."})
                return

            expected_hash = str(row["verification_code_hash"] or "")
            provided_hash = hash_otp(identifier, code)
            if not expected_hash or not hmac.compare_digest(expected_hash, provided_hash):
                conn.execute(
                    "UPDATE registrations SET verification_attempts = verification_attempts + 1 WHERE id = ?",
                    (row["id"],),
                )
                conn.commit()
                self._json_response(400, {"ok": False, "error": "Invalid verification code"})
                return

            verified_at = utc_iso(utc_now())
            if channel == "email":
                conn.execute(
                    """
                    UPDATE registrations
                    SET email_verified = 1, verification_code_hash = NULL,
                        verification_expires_at = NULL, verification_attempts = 0, verified_at = ?
                    WHERE id = ?
                    """,
                    (verified_at, row["id"]),
                )
            else:
                conn.execute(
                    """
                    UPDATE registrations
                    SET phone_verified = 1, verification_code_hash = NULL,
                        verification_expires_at = NULL, verification_attempts = 0, verified_at = ?
                    WHERE id = ?
                    """,
                    (verified_at, row["id"]),
                )

            token = create_session(conn, int(row["id"]))
            conn.commit()

        self._json_response(
            200,
            {
                "ok": True,
                "message": "Verification successful",
                "data": {
                    "sessionToken": token,
                    "fullName": row["full_name"],
                    "email": row["email"],
                    "phone": row["phone"],
                    "redirectTo": "/home-live.html",
                },
            },
        )

    def _handle_resend_code(self) -> None:
        payload = self._read_json_body()
        channel = str(payload.get("verificationChannel", "email")).strip().lower()
        email = str(payload.get("email", "")).strip().lower()
        phone = normalize_phone(str(payload.get("phone", "")).strip())

        if channel not in {"email", "phone"}:
            self._json_response(400, {"ok": False, "error": "Invalid verification channel"})
            return

        with get_conn() as conn:
            if channel == "email":
                row = conn.execute("SELECT * FROM registrations WHERE email = ?", (email,)).fetchone()
                identifier = email
            else:
                row = conn.execute("SELECT * FROM registrations WHERE phone = ?", (phone,)).fetchone()
                identifier = phone

            if not row:
                self._json_response(404, {"ok": False, "error": "Registration not found"})
                return

            last_sent = parse_iso(row["last_code_sent_at"])
            if last_sent:
                elapsed = (utc_now() - last_sent).total_seconds()
                if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                    wait_sec = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
                    self._json_response(429, {"ok": False, "error": f"Please wait {wait_sec}s before requesting a new code"})
                    return

            code = make_otp_code()
            code_hash = hash_otp(identifier, code)
            expires_at = utc_iso(utc_now() + timedelta(minutes=OTP_EXPIRY_MINUTES))
            sent_at = utc_iso(utc_now())

            conn.execute(
                """
                UPDATE registrations
                SET verification_code_hash = ?, verification_expires_at = ?,
                    verification_attempts = 0, last_code_sent_at = ?
                WHERE id = ?
                """,
                (code_hash, expires_at, sent_at, row["id"]),
            )
            conn.commit()

        ok, delivery_message = self._send_verification(channel, row["email"], row["phone"] or "", code, row["full_name"])
        if not ok:
            self._json_response(500, {"ok": False, "error": delivery_message})
            return

        response_payload = {
            "ok": True,
            "message": "Verification code resent",
            "data": {"channel": channel, "deliveryMessage": delivery_message},
        }
        if APP_ENV != "production":
            response_payload["data"]["devCode"] = code
        self._json_response(200, response_payload)

    def _handle_logout(self) -> None:
        payload = self._read_json_body()
        token = str(payload.get("token", "")).strip()
        if not token:
            self._json_response(400, {"ok": False, "error": "Missing token"})
            return

        with get_conn() as conn:
            conn.execute("DELETE FROM registration_sessions WHERE token = ?", (token,))
            conn.commit()

        self._json_response(200, {"ok": True, "message": "Logged out"})

    def _handle_broker_connect(self) -> None:
        """Connect to a broker and return real account data."""
        payload = self._read_json_body()
        platform_id = str(payload.get("platformId", "")).strip().lower()

        if platform_id in ("mt4", "mt5"):
            server = str(payload.get("server", "")).strip()
            login = str(payload.get("login", "")).strip()
            password = str(payload.get("password", "")).strip()
            if not (server and login and password):
                self._json_response(400, {"ok": False, "error": "server, login ו-password נדרשים לחיבור MT"})
                return
            data, err = _connect_fetch_mt5(server, login, password)
            if err:
                if err == "MT5_TERMINAL_NOT_RUNNING":
                    friendly = "MetaTrader 5 לא פועל — אנא פתח את אפליקציית MT5 במחשב שלך ונסה שוב."
                elif any(k in err.lower() for k in ("invalid", "password", "authorization")):
                    friendly = "פרטי ההתחברות שגויים — בדוק את מספר החשבון, הסיסמה וכתובת השרת."
                else:
                    friendly = err
                self._json_response(400, {"ok": False, "error": friendly})
                return
            self._json_response(200, {"ok": True, "data": data})
            return

        # Non-MT platform: return simulated connection stub
        try:
            account_size = float(payload.get("accountSize") or 0)
        except (TypeError, ValueError):
            account_size = 0.0
        import random as _rnd, time as _tm
        _rnd.seed(int(_tm.time() // 86400))  # seed by calendar day — stable for the day
        _demo_pnl = round(_rnd.uniform(-350, 600), 2)
        _demo_trades = _rnd.randint(3, 12)
        _demo_wins = _rnd.randint(1, _demo_trades)
        _bal = account_size if account_size > 0 else 10000.0
        self._json_response(200, {
            "ok": True,
            "simulated": True,
            "data": {
                "balance": _bal,
                "equity": round(_bal + _demo_pnl * 0.6, 2),
                "currency": "USD",
                "totalTrades": _rnd.randint(40, 200),
                "openPositions": _rnd.randint(0, 3),
                "dailyPnl": _demo_pnl,
                "dailyTrades": _demo_trades,
                "dailyWins": _demo_wins,
                "aiSummary": (
                    "חיבור ישיר לממשק ה-API של ברוקר זה טרם הוגדר. "
                    "נתוני מסחר בזמן אמת יהיו זמינים לאחר אינטגרציה מלאה."
                ),
            },
        })

    def _handle_broker_trades(self) -> None:
        """Fetch latest account + today's trading data from MT5 for polling."""
        payload = self._read_json_body()
        platform_id = str(payload.get("platformId", "")).strip().lower()
        if platform_id not in ("mt4", "mt5"):
            self._json_response(400, {"ok": False, "error": "Only MT4/MT5 platforms support live trade fetching"})
            return
        server = str(payload.get("server", "")).strip()
        login = str(payload.get("login", "")).strip()
        password = str(payload.get("password", "")).strip()
        if not (server and login and password):
            self._json_response(400, {"ok": False, "error": "פרטי חיבור חסרים"})
            return
        data, err = _connect_fetch_mt5(server, login, password)
        if err:
            self._json_response(400, {"ok": False, "error": err})
            return
        self._json_response(200, {"ok": True, "data": data})


def run() -> None:
    init_db()
    # Start SSE market broadcast background thread
    t_sse = threading.Thread(target=_market_broadcast_thread, daemon=True, name="empirex-sse-market")
    t_sse.start()

    # Retry binding if port is briefly still occupied from a previous instance
    for attempt in range(8):
        try:
            server = ThreadingHTTPServer((HOST, PORT), EmpirexHandler)
            break
        except OSError as e:
            if attempt < 7:
                print(f"[server] Port {PORT} busy, retrying in 2s... ({e})")
                time.sleep(2)
            else:
                print(f"[server] FATAL: Cannot bind to port {PORT} after 8 attempts: {e}")
                raise

    print(f"Serving EMPIREX landing + API on http://{HOST}:{PORT}")
    print(f"API health: http://{HOST}:{PORT}/api/health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Shutdown requested.")
    except Exception as exc:
        print(f"[server] CRASHED: {exc}")
        raise
    finally:
        try:
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    import sys as _main_sys
    MAX_RESTARTS = 100
    restart_count = 0
    while restart_count < MAX_RESTARTS:
        try:
            run()
            break  # Clean exit (KeyboardInterrupt)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            restart_count += 1
            print(f"[server] Auto-restart #{restart_count} after crash: {exc}")
            time.sleep(3)
