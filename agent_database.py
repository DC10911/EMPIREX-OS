"""
EMPIREX AI Agent — Financial Market Database
============================================
Generates and populates 30,000+ rows of realistic financial market data
into the existing SQLite database. Run once, then the agent reads live.

Tables created:
  market_ohlcv          — OHLCV price bars (daily + 4H) for 15 instruments
  economic_calendar     — Major economic events, 2024-2026
  market_news           — Market news & headlines
  agent_alerts          — Persistent alert store
  agent_investigations  — Investigation records
  agent_reports         — Generated reports
  agent_chat_history    — Chat log
  signal_performance    — Historical signal P&L
  strategy_stats        — Per-strategy performance stats
  correlation_snapshots — Weekly correlation matrix
  volatility_snapshots  — Daily ATR/volatility data
  session_analysis      — Trading session performance
"""

import sqlite3
import random
import math
import json
import os
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────
random.seed(42)          # reproducible
DB_PATH = Path(os.getenv("EMPIREX_DB_PATH", str(Path(__file__).resolve().parent / "empirex_leads.db"))).expanduser().resolve()

TODAY    = datetime(2026, 5, 12)
START_D  = datetime(2024, 1, 2)      # 2-year history
START_4H = datetime(2025, 1, 6)      # 1-year 4H history

# 15 instruments — forex majors, crosses, commodities, indices
INSTRUMENTS = [
    dict(symbol="EURUSD",  base=1.0350, vol=0.0065, trend=+0.0000, cat="major",     digits=5, pip=0.0001),
    dict(symbol="GBPUSD",  base=1.2250, vol=0.0082, trend=+0.0001, cat="major",     digits=5, pip=0.0001),
    dict(symbol="USDJPY",  base=143.0,  vol=0.0070, trend=+0.0004, cat="major",     digits=3, pip=0.01),
    dict(symbol="AUDUSD",  base=0.6380, vol=0.0075, trend=-0.0001, cat="major",     digits=5, pip=0.0001),
    dict(symbol="USDCAD",  base=1.3550, vol=0.0055, trend=+0.0001, cat="major",     digits=5, pip=0.0001),
    dict(symbol="USDCHF",  base=0.9150, vol=0.0060, trend=-0.0001, cat="major",     digits=5, pip=0.0001),
    dict(symbol="NZDUSD",  base=0.5980, vol=0.0080, trend=-0.0001, cat="minor",     digits=5, pip=0.0001),
    dict(symbol="GBPJPY",  base=175.0,  vol=0.0095, trend=+0.0004, cat="cross",     digits=3, pip=0.01),
    dict(symbol="EURJPY",  base=148.0,  vol=0.0085, trend=+0.0003, cat="cross",     digits=3, pip=0.01),
    dict(symbol="EURGBP",  base=0.8450, vol=0.0045, trend=+0.0000, cat="cross",     digits=5, pip=0.0001),
    dict(symbol="XAUUSD",  base=2050.0, vol=0.0085, trend=+0.0007, cat="commodity", digits=2, pip=0.01),
    dict(symbol="XAGUSD",  base=24.50,  vol=0.0130, trend=+0.0004, cat="commodity", digits=3, pip=0.001),
    dict(symbol="USOIL",   base=78.0,   vol=0.0160, trend=-0.0002, cat="commodity", digits=2, pip=0.01),
    dict(symbol="NASDAQ",  base=16400,  vol=0.0095, trend=+0.0006, cat="index",     digits=2, pip=0.01),
    dict(symbol="SP500",   base=4900,   vol=0.0072, trend=+0.0005, cat="index",     digits=2, pip=0.01),
]

# Economic indicator types
INDICATORS = [
    ("USD", "NFP",                   "high",   "United States"),
    ("USD", "CPI m/m",               "high",   "United States"),
    ("USD", "Core CPI m/m",          "high",   "United States"),
    ("USD", "PPI m/m",               "medium", "United States"),
    ("USD", "Retail Sales m/m",      "high",   "United States"),
    ("USD", "Fed Rate Decision",     "high",   "United States"),
    ("USD", "FOMC Minutes",          "high",   "United States"),
    ("USD", "GDP q/q",               "high",   "United States"),
    ("USD", "Unemployment Claims",   "medium", "United States"),
    ("USD", "ISM Manufacturing PMI", "medium", "United States"),
    ("USD", "Trade Balance",         "medium", "United States"),
    ("EUR", "ECB Rate Decision",     "high",   "Eurozone"),
    ("EUR", "CPI Flash Estimate",    "high",   "Eurozone"),
    ("EUR", "GDP Flash Estimate",    "high",   "Eurozone"),
    ("EUR", "German IFO",            "medium", "Germany"),
    ("EUR", "German CPI m/m",        "medium", "Germany"),
    ("EUR", "French CPI m/m",        "low",    "France"),
    ("GBP", "BoE Rate Decision",     "high",   "United Kingdom"),
    ("GBP", "CPI y/y",               "high",   "United Kingdom"),
    ("GBP", "GDP m/m",               "high",   "United Kingdom"),
    ("GBP", "Retail Sales m/m",      "medium", "United Kingdom"),
    ("JPY", "BoJ Rate Decision",     "high",   "Japan"),
    ("JPY", "CPI y/y",               "medium", "Japan"),
    ("JPY", "GDP q/q",               "medium", "Japan"),
    ("AUD", "RBA Rate Decision",     "high",   "Australia"),
    ("AUD", "Employment Change",     "high",   "Australia"),
    ("AUD", "CPI q/q",               "high",   "Australia"),
    ("CAD", "BoC Rate Decision",     "high",   "Canada"),
    ("CAD", "Employment Change",     "medium", "Canada"),
    ("NZD", "RBNZ Rate Decision",    "high",   "New Zealand"),
    ("CHF", "SNB Rate Decision",     "high",   "Switzerland"),
]

NEWS_TEMPLATES = [
    "Fed officials signal {signal} rate path ahead of {event}",
    "Dollar {direction} as {indicator} beats/misses expectations",
    "ECB holds rates steady, signals {outlook} for {quarter}",
    "Gold {direction} to {level} amid {catalyst}",
    "Risk {sentiment} spreads across markets; JPY {direction}",
    "GBPUSD {direction} after UK inflation data surprises",
    "BoE's {name} warns of {risk} in housing market",
    "OPEC+ extends production cuts through {month}",
    "Tech sector {direction} on {earnings} earnings; NASDAQ {move}",
    "US Treasury yields {direction}; impact on USD pairs",
    "{pair} breaks key support/resistance at {level}",
    "Commodity currencies {direction} on China PMI data",
    "Safe-haven demand lifts {asset} amid {geopolitical}",
    "BoJ intervention speculation grows as USDJPY near {level}",
    "Inflation expectations {direction} post-{indicator} data",
]

STRATEGIES = ["Breakout", "Momentum", "Scalp", "Mean Reversion", "Trend Following", "News Trading", "Session Open"]
SESSIONS   = ["Asia", "London", "New York", "Overlap London-NY"]
SYMBOLS_TRADE = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "GBPJPY", "AUDUSD"]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def trading_days(start: datetime, end: datetime):
    """Yield all trading days (Mon-Fri, no weekend) between start and end."""
    cur = start
    while cur <= end:
        if cur.weekday() < 5:   # 0=Mon ... 4=Fri
            yield cur
        cur += timedelta(days=1)

def four_hour_bars(start: datetime, end: datetime):
    """Yield 4H candle open times (6 per trading day: 0,4,8,12,16,20)."""
    hours = [0, 4, 8, 12, 16, 20]
    for day in trading_days(start, end):
        for h in hours:
            yield day.replace(hour=h, minute=0, second=0)

def gbm(price: float, mu: float, sigma: float, n: int):
    """Geometric Brownian Motion price series."""
    prices = [price]
    for _ in range(n - 1):
        ret = random.gauss(mu, sigma)
        prices.append(max(prices[-1] * (1 + ret), prices[-1] * 0.5))
    return prices

def ohlcv_from_open(o: float, intra_vol: float):
    """Generate realistic OHLCV from open price."""
    move = abs(random.gauss(0, intra_vol * o))
    direction = 1 if random.random() > 0.5 else -1
    close  = o + direction * move * random.uniform(0.3, 1.0)
    hi     = max(o, close) + abs(random.gauss(0, move * 0.4))
    lo     = min(o, close) - abs(random.gauss(0, move * 0.4))
    vol    = int(random.uniform(5000, 150000))
    return round(o, 5), round(hi, 5), round(lo, 5), round(close, 5), vol

def atr(ohlcvs: list) -> float:
    """Average True Range from last 14 bars."""
    if len(ohlcvs) < 2:
        return 0.0
    trs = [row[1] - row[2] for row in ohlcvs[-14:]]  # hi - lo
    return sum(trs) / len(trs) if trs else 0.0

def round_p(v, p):
    """Round to pip precision."""
    if p >= 1:
        return round(v, 2)
    decs = len(str(p).rstrip("0").split(".")[-1]) if "." in str(p) else 0
    return round(v, decs)


# ─── Table creation ───────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS market_ohlcv (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT    NOT NULL,
    timeframe  TEXT    NOT NULL,     -- 'D1', 'H4', 'H1'
    ts         TEXT    NOT NULL,     -- ISO8601
    open       REAL    NOT NULL,
    high       REAL    NOT NULL,
    low        REAL    NOT NULL,
    close      REAL    NOT NULL,
    volume     INTEGER NOT NULL,
    atr14      REAL,
    category   TEXT,
    UNIQUE(symbol, timeframe, ts)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_sym_tf ON market_ohlcv(symbol, timeframe, ts DESC);

CREATE TABLE IF NOT EXISTS economic_calendar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time    TEXT NOT NULL,
    currency      TEXT NOT NULL,
    event_name    TEXT NOT NULL,
    impact        TEXT NOT NULL,    -- high/medium/low
    country       TEXT NOT NULL,
    actual        REAL,
    forecast      REAL,
    previous      REAL,
    surprise_pct  REAL,
    market_move   REAL,             -- approx pip move after event
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS market_news (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    published   TEXT NOT NULL,
    headline    TEXT NOT NULL,
    summary     TEXT,
    sentiment   TEXT NOT NULL,      -- bullish/bearish/neutral
    asset       TEXT,
    source      TEXT,
    impact      TEXT                -- high/medium/low
);

CREATE TABLE IF NOT EXISTS agent_alerts (
    id              TEXT PRIMARY KEY,
    severity        TEXT NOT NULL,
    category        TEXT NOT NULL,
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    action_required INTEGER NOT NULL DEFAULT 0,
    suggested_action TEXT,
    created_at      TEXT NOT NULL,
    resolved_at     TEXT,
    resolved_by     TEXT
);

CREATE TABLE IF NOT EXISTS agent_investigations (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'open',
    severity        TEXT NOT NULL,
    title           TEXT NOT NULL,
    trigger_reason  TEXT,
    scope           TEXT,
    timeline_json   TEXT,
    checks_json     TEXT,
    findings_json   TEXT,
    root_cause      TEXT,
    conclusion      TEXT,
    actions_json    TEXT,
    created_at      TEXT NOT NULL,
    completed_at    TEXT
);

CREATE TABLE IF NOT EXISTS agent_reports (
    id              TEXT PRIMARY KEY,
    report_type     TEXT NOT NULL,
    title           TEXT NOT NULL,
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    summary         TEXT,
    metrics_json    TEXT,
    insights_json   TEXT,
    anomalies_json  TEXT,
    actions_json    TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,      -- user/agent
    message     TEXT NOT NULL,
    context_json TEXT,
    ts          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_performance (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id     TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    direction     TEXT NOT NULL,    -- BUY/SELL
    strategy      TEXT NOT NULL,
    session       TEXT NOT NULL,
    entry_price   REAL NOT NULL,
    exit_price    REAL,
    sl_price      REAL,
    tp_price      REAL,
    lot_size      REAL NOT NULL,
    pnl           REAL,
    r_multiple    REAL,
    opened_at     TEXT NOT NULL,
    closed_at     TEXT,
    duration_min  INTEGER,
    opened_by     TEXT NOT NULL DEFAULT 'bot',
    win           INTEGER,          -- 1=win, 0=loss, NULL=open
    notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_sig_sym ON signal_performance(symbol, opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_sig_strat ON signal_performance(strategy, opened_at DESC);

CREATE TABLE IF NOT EXISTS strategy_stats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy     TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    session      TEXT NOT NULL,
    period       TEXT NOT NULL,     -- YYYY-MM or YYYY-WNN
    trades       INTEGER NOT NULL,
    wins         INTEGER NOT NULL,
    losses       INTEGER NOT NULL,
    total_pnl    REAL NOT NULL,
    avg_pnl      REAL NOT NULL,
    avg_r        REAL NOT NULL,
    max_dd       REAL NOT NULL,
    win_rate     REAL NOT NULL,
    profit_factor REAL NOT NULL,
    computed_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS correlation_snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    sym_a      TEXT NOT NULL,
    sym_b      TEXT NOT NULL,
    corr_30d   REAL NOT NULL,
    corr_90d   REAL NOT NULL,
    UNIQUE(week_start, sym_a, sym_b)
);

CREATE TABLE IF NOT EXISTS volatility_snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT NOT NULL,
    date      TEXT NOT NULL,
    atr14_d   REAL NOT NULL,
    atr14_4h  REAL NOT NULL,
    hv20      REAL NOT NULL,        -- 20-day historical volatility %
    regime    TEXT NOT NULL,        -- low/normal/high/extreme
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS session_analysis (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    session    TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    trades     INTEGER NOT NULL,
    wins       INTEGER NOT NULL,
    total_pnl  REAL NOT NULL,
    avg_range  REAL NOT NULL,
    UNIQUE(week_start, session, symbol)
);
"""

# ─── Populate functions ───────────────────────────────────────────────────────

def populate_ohlcv(cur: sqlite3.Cursor) -> int:
    """Generate 30,000+ rows of OHLCV data."""
    rows_inserted = 0

    for inst in INSTRUMENTS:
        sym = inst["symbol"]
        vol = inst["vol"]
        trend = inst["trend"]
        cat = inst["cat"]

        # ── Daily bars (2 years) ──────────────────────────────────────
        d_days = list(trading_days(START_D, TODAY))
        n_d    = len(d_days)
        d_closes = gbm(inst["base"], trend / 252, vol / math.sqrt(252), n_d)

        d_bars = []
        for i, (day, close) in enumerate(zip(d_days, d_closes)):
            o = d_bars[i-1][4] if i > 0 else close * random.uniform(0.999, 1.001)
            o_v, h, l, c, vv = ohlcv_from_open(o, vol / math.sqrt(252))
            # Force close toward GBM path
            c = close
            h = max(h, c, o_v)
            l = min(l, c, o_v)
            d_bars.append((o_v, h, l, c, vv))

        atr14_d = atr(d_bars)

        batch = []
        for i, (day, bar) in enumerate(zip(d_days, d_bars)):
            batch.append((sym, "D1", iso(day), bar[0], bar[1], bar[2], bar[3], bar[4], round(atr(d_bars[max(0,i-14):i+1]), 6), cat))

        cur.executemany(
            "INSERT OR IGNORE INTO market_ohlcv(symbol,timeframe,ts,open,high,low,close,volume,atr14,category) VALUES(?,?,?,?,?,?,?,?,?,?)",
            batch
        )
        rows_inserted += len(batch)

        # ── 4H bars (1 year) ─────────────────────────────────────────
        h4_times = list(four_hour_bars(START_4H, TODAY))
        n_h4     = len(h4_times)
        h4_closes = gbm(d_closes[len(d_closes)//2], trend / 252 / 6, vol / math.sqrt(252 * 6), n_h4)

        h4_bars = []
        for i, close in enumerate(h4_closes):
            o = h4_bars[i-1][3] if i > 0 else close * random.uniform(0.9998, 1.0002)
            o_v, h, l, c, vv = ohlcv_from_open(o, vol / math.sqrt(252 * 6))
            c = close
            h = max(h, c, o_v)
            l = min(l, c, o_v)
            h4_bars.append((o_v, h, l, c, vv))

        batch4 = []
        for i, (ts, bar) in enumerate(zip(h4_times, h4_bars)):
            batch4.append((sym, "H4", iso(ts), bar[0], bar[1], bar[2], bar[3], bar[4], round(atr(h4_bars[max(0,i-14):i+1]), 6), cat))

        cur.executemany(
            "INSERT OR IGNORE INTO market_ohlcv(symbol,timeframe,ts,open,high,low,close,volume,atr14,category) VALUES(?,?,?,?,?,?,?,?,?,?)",
            batch4
        )
        rows_inserted += len(batch4)

    return rows_inserted


def populate_economic_calendar(cur: sqlite3.Cursor) -> int:
    """Generate ~700 rows of economic events."""
    rows = []
    cur_date = START_D

    while cur_date <= TODAY:
        weekday = cur_date.weekday()
        if weekday < 5:   # trading day
            # Randomly pick 1-4 events per day
            n_events = random.choices([0, 1, 2, 3, 4], weights=[30, 35, 20, 10, 5])[0]
            for _ in range(n_events):
                ind = random.choice(INDICATORS)
                cur_code, name, impact, country = ind
                hour = random.choice([6, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 21])
                minute = random.choice([0, 15, 30, 45])
                evt_dt = cur_date.replace(hour=hour, minute=minute, second=0)

                forecast = round(random.gauss(0.3, 0.8), 2)
                surprise = round(random.gauss(0, 0.4), 2)
                actual   = round(forecast + surprise, 2)
                previous = round(forecast + random.gauss(0, 0.3), 2)
                move_pips = round(abs(random.gauss(0, 25)) * (3 if impact=="high" else 1.5 if impact=="medium" else 0.8), 1)

                rows.append((iso(evt_dt), cur_code, name, impact, country, actual, forecast, previous, round(surprise/max(abs(forecast),0.01)*100,1), move_pips, ""))

        cur_date += timedelta(days=1)

    cur.executemany(
        "INSERT OR IGNORE INTO economic_calendar(event_time,currency,event_name,impact,country,actual,forecast,previous,surprise_pct,market_move,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        rows
    )
    return len(rows)


def populate_news(cur: sqlite3.Cursor) -> int:
    """Generate ~400 market news items."""
    rows = []
    signals = ["hawkish", "dovish", "cautious", "data-dependent"]
    directions = ["surges", "tumbles", "edges higher", "slips", "consolidates"]
    sentiments = ["bullish", "bearish", "neutral"]
    assets = list(set(i["symbol"] for i in INSTRUMENTS))
    sources = ["Reuters", "Bloomberg", "FXStreet", "ForexFactory", "CNBC", "WSJ", "FT"]

    cur_date = START_D
    while cur_date <= TODAY:
        if cur_date.weekday() < 5:
            n = random.choices([0,1,2,3], weights=[20,40,30,10])[0]
            for _ in range(n):
                hour = random.randint(6, 22)
                pub = cur_date.replace(hour=hour, minute=random.randint(0,59))
                tmpl = random.choice(NEWS_TEMPLATES)
                asset = random.choice(assets)
                headline = tmpl.replace("{signal}", random.choice(signals)) \
                               .replace("{event}", "FOMC") \
                               .replace("{direction}", random.choice(directions)) \
                               .replace("{indicator}", "CPI") \
                               .replace("{outlook}", random.choice(["positive", "uncertain", "cautious"])) \
                               .replace("{quarter}", "Q2") \
                               .replace("{level}", f"{random.uniform(100,160):.2f}") \
                               .replace("{catalyst}", "geopolitical tensions") \
                               .replace("{sentiment}", random.choice(["appetite", "aversion"])) \
                               .replace("{name}", "Bailey") \
                               .replace("{risk}", "overheating") \
                               .replace("{month}", "Q3") \
                               .replace("{earnings}", "Apple") \
                               .replace("{move}", "+2.1%") \
                               .replace("{pair}", asset) \
                               .replace("{asset}", "Gold") \
                               .replace("{geopolitical}", "Middle East tensions") \
                               .replace("{quarter}", "Q3")
                rows.append((iso(pub), headline[:200], "", random.choice(sentiments), asset, random.choice(sources), random.choice(["high","medium","low"])))
        cur_date += timedelta(days=1)

    cur.executemany(
        "INSERT OR IGNORE INTO market_news(published,headline,summary,sentiment,asset,source,impact) VALUES(?,?,?,?,?,?,?)",
        rows
    )
    return len(rows)


def populate_signal_performance(cur: sqlite3.Cursor) -> int:
    """Generate ~2,500 historical trade signals."""
    rows = []
    cur_date = START_D

    while cur_date <= TODAY:
        if cur_date.weekday() < 5:
            n_signals = random.choices([0, 1, 2, 3, 4, 5], weights=[10, 20, 30, 25, 12, 3])[0]
            for _ in range(n_signals):
                sym  = random.choice(SYMBOLS_TRADE)
                inst = next((i for i in INSTRUMENTS if i["symbol"]==sym), INSTRUMENTS[0])
                strat = random.choice(STRATEGIES)
                sess  = random.choice(SESSIONS)
                direction = random.choice(["BUY", "SELL"])
                hour = {"Asia": 3, "London": 9, "New York": 15, "Overlap London-NY": 13}[sess] + random.randint(-1,2)
                open_dt = cur_date.replace(hour=max(0,min(23,hour)), minute=random.randint(0,59))

                # Simulate a realistic entry
                daily_vol = inst["vol"] / math.sqrt(252)
                base_price = inst["base"] * random.uniform(0.90, 1.10)
                entry = round(base_price * random.uniform(0.998, 1.002), inst["digits"])

                sl_pips = random.uniform(15, 80)
                tp_pips = sl_pips * random.uniform(1.2, 3.0)
                sl = round(entry - sl_pips * inst["pip"] * (1 if direction=="BUY" else -1), inst["digits"])
                tp = round(entry + tp_pips * inst["pip"] * (1 if direction=="BUY" else -1), inst["digits"])
                lots = round(random.choice([0.01, 0.02, 0.03, 0.05, 0.08, 0.10]), 2)

                # Outcome — strategy-biased win rates
                win_rates = {"Breakout": 0.62, "Momentum": 0.58, "Scalp": 0.65, "Mean Reversion": 0.55, "Trend Following": 0.60, "News Trading": 0.50, "Session Open": 0.57}
                win = 1 if random.random() < win_rates.get(strat, 0.58) else 0

                # Duration
                dur = int(random.exponential if hasattr(random, "exponential") else abs(random.gauss(120, 80)))
                dur = max(5, int(abs(random.gauss(120, 80))))
                close_dt = open_dt + timedelta(minutes=dur)
                if close_dt > TODAY: close_dt = None

                if close_dt:
                    if win:
                        exit_price = tp
                        r_mult = round(tp_pips / sl_pips, 2)
                    else:
                        exit_price = sl
                        r_mult = -1.0
                    pips_gained = (exit_price - entry) / inst["pip"] * (1 if direction=="BUY" else -1)
                    pnl = round(pips_gained * lots * 10, 2)   # approx $10/pip/0.1lot
                else:
                    exit_price = None
                    pnl = None
                    r_mult = None
                    win = None

                rows.append((
                    f"sig_{cur_date.strftime('%Y%m%d')}_{random.randint(1000,9999)}",
                    sym, direction, strat, sess,
                    entry, exit_price, sl, tp, lots,
                    pnl, r_mult,
                    iso(open_dt), iso(close_dt) if close_dt else None,
                    dur if close_dt else None,
                    "bot", win, ""
                ))

        cur_date += timedelta(days=1)

    cur.executemany(
        """INSERT OR IGNORE INTO signal_performance
           (signal_id,symbol,direction,strategy,session,entry_price,exit_price,sl_price,tp_price,lot_size,
            pnl,r_multiple,opened_at,closed_at,duration_min,opened_by,win,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows
    )
    return len(rows)


def populate_strategy_stats(cur: sqlite3.Cursor) -> int:
    """Aggregate strategy stats by month."""
    rows = []
    cur_date = datetime(2024, 1, 1)
    while cur_date <= TODAY.replace(day=1):
        period = cur_date.strftime("%Y-%m")
        for strat in STRATEGIES:
            for sym in SYMBOLS_TRADE:
                for sess in SESSIONS:
                    trades = random.randint(3, 40)
                    wr     = random.uniform(0.45, 0.72)
                    wins   = int(trades * wr)
                    losses = trades - wins
                    avg_r  = round(random.uniform(-0.1, 1.2), 2)
                    avg_pnl = round(random.gauss(15, 40), 2)
                    total  = round(avg_pnl * trades, 2)
                    maxdd  = round(abs(random.gauss(0, 120)), 2)
                    pf     = round(wins * avg_r / max(losses, 1) * 1.1, 2) if losses > 0 else 3.0
                    rows.append((strat, sym, sess, period, trades, wins, losses, total, avg_pnl, avg_r, maxdd, round(wr,3), max(0.1,pf), iso(cur_date)))

        # next month
        if cur_date.month == 12:
            cur_date = cur_date.replace(year=cur_date.year+1, month=1)
        else:
            cur_date = cur_date.replace(month=cur_date.month+1)

    cur.executemany(
        """INSERT OR IGNORE INTO strategy_stats
           (strategy,symbol,session,period,trades,wins,losses,total_pnl,avg_pnl,avg_r,max_dd,win_rate,profit_factor,computed_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows
    )
    return len(rows)


def populate_volatility(cur: sqlite3.Cursor) -> int:
    """Daily volatility snapshots for each instrument."""
    rows = []
    for inst in INSTRUMENTS:
        sym = inst["symbol"]
        vol = inst["vol"]
        cur_date = START_D
        prev_atr_d = vol / math.sqrt(252) * inst["base"] * 14
        prev_atr_4h = prev_atr_d / 4
        while cur_date <= TODAY:
            if cur_date.weekday() < 5:
                atr_d  = max(0.0001, prev_atr_d  * random.uniform(0.92, 1.08))
                atr_4h = max(0.0001, prev_atr_4h * random.uniform(0.92, 1.08))
                hv20   = round(vol * random.uniform(0.7, 1.4) * 100, 2)
                regime = "low" if hv20 < vol*80 else "extreme" if hv20 > vol*160 else "high" if hv20 > vol*130 else "normal"
                rows.append((sym, cur_date.strftime("%Y-%m-%d"), round(atr_d,6), round(atr_4h,6), hv20, regime))
                prev_atr_d = atr_d
                prev_atr_4h = atr_4h
            cur_date += timedelta(days=1)

    cur.executemany(
        "INSERT OR IGNORE INTO volatility_snapshots(symbol,date,atr14_d,atr14_4h,hv20,regime) VALUES(?,?,?,?,?,?)",
        rows
    )
    return len(rows)


def populate_correlations(cur: sqlite3.Cursor) -> int:
    """Weekly correlation matrix snapshots."""
    rows = []
    syms = [i["symbol"] for i in INSTRUMENTS[:10]]
    # Known rough correlations
    corr_map = {
        ("EURUSD","GBPUSD"): 0.85, ("EURUSD","AUDUSD"): 0.70, ("EURUSD","NZDUSD"): 0.68,
        ("EURUSD","USDCAD"): -0.75, ("EURUSD","USDCHF"): -0.88, ("EURUSD","USDJPY"): -0.40,
        ("GBPUSD","AUDUSD"): 0.65, ("GBPUSD","GBPJPY"): 0.72, ("EURUSD","XAUUSD"): 0.55,
        ("USDJPY","XAUUSD"): -0.45, ("USDCAD","USOIL"): -0.65, ("XAUUSD","XAGUSD"): 0.88,
    }
    def get_corr(a, b):
        key = (a,b) if (a,b) in corr_map else (b,a) if (b,a) in corr_map else None
        base = corr_map.get(key, random.uniform(-0.3, 0.3)) if key else random.uniform(-0.3, 0.3)
        return round(max(-1, min(1, base + random.gauss(0, 0.05))), 4)

    week = START_D
    while week <= TODAY:
        if week.weekday() == 0:
            ws = week.strftime("%Y-%m-%d")
            for i, a in enumerate(syms):
                for b in syms[i+1:]:
                    c30 = get_corr(a, b)
                    c90 = round(max(-1, min(1, c30 + random.gauss(0, 0.08))), 4)
                    rows.append((ws, a, b, c30, c90))
        week += timedelta(days=1)

    cur.executemany(
        "INSERT OR IGNORE INTO correlation_snapshots(week_start,sym_a,sym_b,corr_30d,corr_90d) VALUES(?,?,?,?,?)",
        rows
    )
    return len(rows)


def populate_session_analysis(cur: sqlite3.Cursor) -> int:
    """Weekly session performance analysis."""
    rows = []
    week = START_D
    while week <= TODAY:
        if week.weekday() == 0:
            ws = week.strftime("%Y-%m-%d")
            for sess in SESSIONS:
                for sym in SYMBOLS_TRADE:
                    trades = random.randint(1, 12)
                    wr = {"Asia": 0.52, "London": 0.65, "New York": 0.60, "Overlap London-NY": 0.63}[sess]
                    wins = int(trades * (wr + random.gauss(0, 0.1)))
                    wins = max(0, min(trades, wins))
                    pnl  = round((wins * random.uniform(30, 80)) - ((trades-wins) * random.uniform(25, 60)), 2)
                    rng  = round(abs(random.gauss(50, 20)), 2)
                    rows.append((ws, sess, sym, trades, wins, pnl, rng))
        week += timedelta(days=1)

    cur.executemany(
        "INSERT OR IGNORE INTO session_analysis(week_start,session,symbol,trades,wins,total_pnl,avg_range) VALUES(?,?,?,?,?,?,?)",
        rows
    )
    return len(rows)


def seed_initial_alerts(cur: sqlite3.Cursor):
    """Seed a handful of live alerts."""
    import uuid
    alerts = [
        ("high",    "risk",       "מגבלת הפסד יומי ב-72%",              "ההפסד היומי הגיע ל-$214.36 מתוך $500. נדרשת הפחתת סיכון.",    1, "REDUCE_RISK_MODE"),
        ("high",    "risk",       "חשיפת XAUUSD מעל סף",                 "3 פוזיציות כוללות XAUUSD — ריכוז 35% מהסיכון הפעיל.",          1, "BLOCK_SYMBOL"),
        ("high",    "strategy",   "3 הפסדים רצופים — XAUUSD",            "הפסדים: -$34, -$48, -$43 ב-12 שעות האחרונות.",               1, "BLOCK_SYMBOL"),
        ("warning", "broker",     "סנכרון ברוקר מאוחר",                  "עיכוב 14 דקות — נתוני סיכון עלולים להיות לא מדויקים.",       0, None),
        ("warning", "news",       "CPI אמריקאי ב-21:30",                  "השפעה גבוהה. מומלץ לסגור פוזיציות USD 30 דקות לפני.",        0, None),
        ("warning", "strategy",   "מסחר יתר אחרי 18:00",                 "5 עסקאות בסשן NY המאוחר — מעל הסף הפנימי.",                  0, None),
        ("info",    "bot",        "הבוט עצר — כלל בטיחות",               "עצירה אוטומטית ב-22:14 עקב רצף הפסדים.",                     0, None),
        ("warning", "strategy",   "GBPUSD Momentum חלשה",                 "Win rate 33% השבוע vs. 61% ממוצע 30 ימים.",                  0, None),
    ]
    now = iso(TODAY)
    for sev, cat, title, msg, req, sug in alerts:
        cur.execute(
            "INSERT OR IGNORE INTO agent_alerts(id,severity,category,title,message,status,action_required,suggested_action,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), sev, cat, title, msg, "open", req, sug, now)
        )


def seed_initial_investigations(cur: sqlite3.Cursor):
    """Seed initial investigation records."""
    timeline = json.dumps([
        {"time": "08:10", "title": "עסקה ראשונה", "description": "XAUUSD BUY 0.05"},
        {"time": "10:32", "title": "סגירה בהפסד", "description": "-$34"},
        {"time": "16:05", "title": "עסקה שנייה", "description": "XAUUSD SELL — כיוון הפוך"},
        {"time": "17:44", "title": "הפסד שני", "description": "-$48"},
        {"time": "18:12", "title": "עסקה שלישית", "description": "XAUUSD BUY — 28 דקות אחרי"},
        {"time": "19:05", "title": "הפסד שלישי", "description": "-$43 · כלל בטיחות הופעל"},
    ])
    findings = json.dumps([
        {"title": "ריכוז XAUUSD", "description": "67% מהפסד היום מנכס אחד", "impact": "high"},
        {"title": "כניסות נגד trend", "description": "3 עסקאות נגד trend יומי", "impact": "high"},
        {"title": "מסחר יתר 18-21", "description": "3 עסקאות XAUUSD ב-3 שעות", "impact": "medium"},
        {"title": "ATR קיצוני", "description": "ATR שעתי 8.2 — 150% מהממוצע", "impact": "medium"},
    ])
    actions = json.dumps([
        {"label": "חסום XAUUSD", "actionType": "BLOCK_SYMBOL", "requiresApproval": False},
        {"label": "הפחת סיכון", "actionType": "REDUCE_RISK_MODE", "requiresApproval": False},
        {"label": "הערת יומן", "actionType": "CREATE_JOURNAL_NOTE", "requiresApproval": False},
    ])
    cur.execute(
        """INSERT OR IGNORE INTO agent_investigations
           (id,status,severity,title,trigger_reason,scope,timeline_json,checks_json,findings_json,root_cause,conclusion,actions_json,created_at,completed_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("inv-001", "completed", "high",
         "חקירת ריכוז XAUUSD — קפיצת הפסד",
         "3 הפסדים רצופים ב-XAUUSD",
         "last_24h",
         timeline,
         json.dumps(["ריכוז נכס", "pattern הפסד", "שעות מסחר", "כיוון vs trend", "קורלציה EUR/USD", "volatility ATR"]),
         findings,
         "הבוט סחר ב-XAUUSD תחת volatility גבוהה מחוץ לשעות האופטימליות — 3 כניסות ב-3 שעות, כולן נגד trend יומי.",
         "הבעיה אינה כללית. רוב ההפסד מ-XAUUSD בסשן NY המאוחר. מומלץ לחסום XAUUSD לאחר 2 הפסדים רצופים.",
         actions,
         iso(TODAY.replace(hour=9, minute=10)),
         iso(TODAY.replace(hour=9, minute=25)))
    )


def seed_initial_reports(cur: sqlite3.Cursor):
    """Seed initial report records."""
    metrics_daily = json.dumps({"pnl": -14.20, "trades": 7, "winRate": 57.1, "averageR": 0.12, "drawdown": 1.42, "riskUsed": 72})
    metrics_weekly = json.dumps({"pnl": 842.75, "trades": 34, "winRate": 64.7, "averageR": 0.62, "drawdown": 4.31, "riskUsed": 43.1})
    metrics_risk = json.dumps({"pnl": -214.36, "trades": 0, "winRate": 0, "averageR": 0, "drawdown": 4.31, "riskUsed": 72})
    metrics_bot = json.dumps({"pnl": 213.45, "trades": 7, "winRate": 68.4, "averageR": 0.71, "drawdown": 2.1, "riskUsed": 35})

    reports = [
        ("rep-001", "daily",   "דוח מסחר יומי — אתמול",         "2026-05-11", "2026-05-11", "יום מסחר מעורב. 7 עסקאות, 4 ברווח.", metrics_daily,
         json.dumps(["עסקאות לונדון — 75% win rate", "XAUUSD — 3 הפסדים", "Best: EURUSD +$37"]),
         json.dumps(["3 הפסדים רצופים XAUUSD", "5 עסקאות אחרי 18:00"]),
         json.dumps(["הגבל XAUUSD", "הוסף Time Filter", "בדוק signal quality"])),
        ("rep-002", "weekly",  "דוח שבועי — שבוע 19/2026",      "2026-05-06", "2026-05-11", "שבוע חיובי — $842.75 רווח.", metrics_weekly,
         json.dumps(["London Breakout — מצויין", "GBPUSD Momentum — חלשה"]),
         json.dumps(["GBPUSD win rate ירד ל-33%"]),
         json.dumps(["בדוק GBPUSD Momentum", "המשך Breakout London"])),
        ("rep-003", "risk",    "דוח סיכון — מצב נוכחי",         "2026-05-12", "2026-05-12", "סיכון גבוה. 72% מגבלה יומית.", metrics_risk,
         json.dumps(["Daily Loss $214/$500", "Drawdown 4.31%", "XAUUSD 35% חשיפה"]),
         json.dumps(["ריכוז XAUUSD", "הפסד מואץ"]),
         json.dumps(["הפחת סיכון", "חסום XAUUSD"])),
        ("rep-004", "bot",     "דוח בוט — Breakout Pro v2.1",   "2026-04-19", "2026-05-12", "23 ימים פעיל. Win rate 68.4%.", metrics_bot,
         json.dumps(["London 75% win rate", "NY Late (18-22) 22%"]),
         json.dumps(["ביצועים חלשים 18-22"]),
         json.dumps(["הוסף Time Filter", "הגבל XAUUSD"])),
    ]
    for r in reports:
        cur.execute(
            """INSERT OR IGNORE INTO agent_reports
               (id,report_type,title,period_start,period_end,summary,metrics_json,insights_json,anomalies_json,actions_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (*r, iso(TODAY))
        )


# ─── Main ─────────────────────────────────────────────────────────────────────

def build_database(verbose=True):
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    if verbose:
        print(f"[DB] Opening: {DB_PATH}")

    # Create all tables
    for stmt in DDL.strip().split(";\n\n"):
        cur.executescript(stmt + ";")
    conn.commit()
    if verbose:
        print("[DB] Tables created ✓")

    # OHLCV (biggest dataset)
    n = populate_ohlcv(cur)
    conn.commit()
    if verbose:
        print(f"[DB] market_ohlcv: {n:,} rows ✓")

    # Economic calendar
    n = populate_economic_calendar(cur)
    conn.commit()
    if verbose:
        print(f"[DB] economic_calendar: {n:,} rows ✓")

    # News
    n = populate_news(cur)
    conn.commit()
    if verbose:
        print(f"[DB] market_news: {n:,} rows ✓")

    # Signals
    n = populate_signal_performance(cur)
    conn.commit()
    if verbose:
        print(f"[DB] signal_performance: {n:,} rows ✓")

    # Strategy stats
    n = populate_strategy_stats(cur)
    conn.commit()
    if verbose:
        print(f"[DB] strategy_stats: {n:,} rows ✓")

    # Volatility
    n = populate_volatility(cur)
    conn.commit()
    if verbose:
        print(f"[DB] volatility_snapshots: {n:,} rows ✓")

    # Correlations
    n = populate_correlations(cur)
    conn.commit()
    if verbose:
        print(f"[DB] correlation_snapshots: {n:,} rows ✓")

    # Session analysis
    n = populate_session_analysis(cur)
    conn.commit()
    if verbose:
        print(f"[DB] session_analysis: {n:,} rows ✓")

    # Seed live data
    seed_initial_alerts(cur)
    seed_initial_investigations(cur)
    seed_initial_reports(cur)
    conn.commit()

    # Print total rows
    cur.execute("""
        SELECT SUM(cnt) FROM (
          SELECT COUNT(*) cnt FROM market_ohlcv
          UNION ALL SELECT COUNT(*) FROM economic_calendar
          UNION ALL SELECT COUNT(*) FROM market_news
          UNION ALL SELECT COUNT(*) FROM signal_performance
          UNION ALL SELECT COUNT(*) FROM strategy_stats
          UNION ALL SELECT COUNT(*) FROM volatility_snapshots
          UNION ALL SELECT COUNT(*) FROM correlation_snapshots
          UNION ALL SELECT COUNT(*) FROM session_analysis
        )
    """)
    total = cur.fetchone()[0]
    if verbose:
        print(f"\n[DB] ✅ Total rows in financial database: {total:,}")

    conn.close()
    return total


if __name__ == "__main__":
    total = build_database(verbose=True)
    print(f"\nDone. Database ready at: {DB_PATH}")
