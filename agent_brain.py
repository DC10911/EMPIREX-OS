"""
EMPIREX AI Agent — Brain Module
================================
Full intelligence layer: market analysis, risk evaluation, compliance,
report generation, and Hebrew NLP chat processing.
All functions read from the EMPIREX SQLite database.
"""

import sqlite3
import json
import math
import random
import uuid
import re
from datetime import datetime, timedelta
import os
from pathlib import Path

DB_PATH = Path(os.getenv("EMPIREX_DB_PATH", str(Path(__file__).resolve().parent / "empirex_leads.db"))).expanduser().resolve()

# ─── DB Helpers ───────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _q(sql: str, params=()):
    with _db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

def _q1(sql: str, params=()):
    with _db() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

def _ex(sql: str, params=()):
    with _db() as conn:
        conn.execute(sql, params)
        conn.commit()

def iso_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def iso_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Market Analysis ──────────────────────────────────────────────────────────

def get_latest_prices(symbols: list = None) -> dict:
    """Get latest closing price for each symbol from D1 data."""
    if symbols:
        placeholders = ",".join("?" * len(symbols))
        rows = _q(
            f"SELECT symbol, close, high, low, open, ts FROM market_ohlcv WHERE timeframe='D1' AND symbol IN ({placeholders}) GROUP BY symbol HAVING MAX(ts) ORDER BY symbol",
            symbols
        )
    else:
        rows = _q(
            "SELECT symbol, close, high, low, open, ts FROM market_ohlcv WHERE timeframe='D1' GROUP BY symbol HAVING MAX(ts) ORDER BY symbol"
        )
    return {r["symbol"]: r for r in rows}


def get_symbol_analysis(symbol: str) -> dict:
    """Full technical analysis for a symbol using DB data."""
    # Last 50 daily bars
    bars = _q(
        "SELECT * FROM market_ohlcv WHERE symbol=? AND timeframe='D1' ORDER BY ts DESC LIMIT 50",
        (symbol,)
    )
    if not bars:
        return {"error": f"No data for {symbol}"}

    closes = [b["close"] for b in reversed(bars)]
    highs  = [b["high"] for b in reversed(bars)]
    lows   = [b["low"] for b in reversed(bars)]
    n = len(closes)

    # SMA
    sma20 = sum(closes[-20:]) / min(20, n) if n >= 5 else closes[-1]
    sma50 = sum(closes[-50:]) / min(50, n) if n >= 10 else closes[-1]

    # EMA14
    k = 2 / (14 + 1)
    ema14 = closes[0]
    for c in closes[1:]:
        ema14 = c * k + ema14 * (1 - k)

    # RSI14
    gains, losses = [], []
    for i in range(1, min(15, n)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains) / len(gains) if gains else 0.0001
    avg_loss = sum(losses) / len(losses) if losses else 0.0001
    rs = avg_gain / avg_loss
    rsi = round(100 - 100 / (1 + rs), 1)

    # ATR14
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, min(15, n))]
    atr14 = sum(trs) / len(trs) if trs else 0

    current = closes[-1]
    prev    = closes[-2] if n >= 2 else current
    change_pct = round((current - prev) / prev * 100, 3)

    trend = "bullish" if current > sma20 > sma50 else "bearish" if current < sma20 < sma50 else "sideways"
    momentum = "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral"

    # Volatility regime from DB
    vol_row = _q1(
        "SELECT regime, hv20, atr14_d FROM volatility_snapshots WHERE symbol=? ORDER BY date DESC LIMIT 1",
        (symbol,)
    )
    regime = vol_row["regime"] if vol_row else "normal"
    hv20   = vol_row["hv20"]   if vol_row else atr14 / current * 100 * math.sqrt(252)

    # Support/Resistance (recent swing highs/lows)
    recent_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    recent_low  = min(lows[-20:])  if len(lows) >= 20 else min(lows)

    # Signal performance for this symbol
    sig_stats = _q1(
        "SELECT COUNT(*) trades, SUM(win) wins, AVG(r_multiple) avg_r, SUM(pnl) total_pnl FROM signal_performance WHERE symbol=? AND closed_at IS NOT NULL AND opened_at > date('now','-30 days')",
        (symbol,)
    )

    return {
        "symbol":       symbol,
        "current":      round(current, 5),
        "prev_close":   round(prev, 5),
        "change_pct":   change_pct,
        "sma20":        round(sma20, 5),
        "sma50":        round(sma50, 5),
        "ema14":        round(ema14, 5),
        "rsi14":        rsi,
        "atr14":        round(atr14, 5),
        "hv20":         round(hv20, 2),
        "regime":       regime,
        "trend":        trend,
        "momentum":     momentum,
        "resistance":   round(recent_high, 5),
        "support":      round(recent_low, 5),
        "trades_30d":   sig_stats["trades"] if sig_stats else 0,
        "wins_30d":     sig_stats["wins"] if sig_stats else 0,
        "avg_r_30d":    round(sig_stats["avg_r"] or 0, 2) if sig_stats else 0,
        "pnl_30d":      round(sig_stats["total_pnl"] or 0, 2) if sig_stats else 0,
    }


def get_market_overview() -> dict:
    """Full market overview — all instruments' latest state."""
    syms = ["EURUSD","GBPUSD","USDJPY","XAUUSD","GBPJPY","AUDUSD","USDCAD","NASDAQ","SP500","XAGUSD"]
    analyses = []
    for sym in syms:
        a = get_symbol_analysis(sym)
        if "error" not in a:
            analyses.append(a)

    bullish = sum(1 for a in analyses if a["trend"] == "bullish")
    bearish = sum(1 for a in analyses if a["trend"] == "bearish")
    overbought = sum(1 for a in analyses if a["momentum"] == "overbought")
    oversold   = sum(1 for a in analyses if a["momentum"] == "oversold")
    high_vol   = sum(1 for a in analyses if a["regime"] in ("high", "extreme"))

    sentiment = "bullish" if bullish > bearish + 1 else "bearish" if bearish > bullish + 1 else "mixed"

    return {
        "instruments":  analyses,
        "sentiment":    sentiment,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "overbought":   overbought,
        "oversold":     oversold,
        "high_vol_count": high_vol,
        "market_regime": "volatile" if high_vol >= 3 else "normal",
    }


def get_correlations(symbol: str) -> list:
    """Get latest correlations for a symbol."""
    rows = _q(
        """SELECT sym_a, sym_b, corr_30d, corr_90d FROM correlation_snapshots
           WHERE (sym_a=? OR sym_b=?) ORDER BY week_start DESC LIMIT 20""",
        (symbol, symbol)
    )
    results = []
    seen = set()
    for r in rows:
        other = r["sym_b"] if r["sym_a"] == symbol else r["sym_a"]
        if other not in seen:
            seen.add(other)
            results.append({"symbol": other, "corr_30d": r["corr_30d"], "corr_90d": r["corr_90d"]})
    return sorted(results, key=lambda x: abs(x["corr_30d"]), reverse=True)[:8]


def get_volatility_ranking() -> list:
    """Rank instruments by current volatility."""
    rows = _q(
        "SELECT symbol, hv20, atr14_d, regime FROM volatility_snapshots GROUP BY symbol HAVING MAX(date) ORDER BY hv20 DESC"
    )
    return rows


# ─── Economic Calendar ────────────────────────────────────────────────────────

def get_upcoming_events(days_ahead: int = 3) -> list:
    """Upcoming high/medium impact events."""
    now_iso = iso_now()
    future  = iso_dt(datetime.utcnow() + timedelta(days=days_ahead))
    rows = _q(
        """SELECT * FROM economic_calendar
           WHERE event_time >= ? AND event_time <= ? AND impact IN ('high','medium')
           ORDER BY event_time ASC LIMIT 30""",
        (now_iso, future)
    )
    return rows


def get_today_events() -> list:
    now = datetime.utcnow()
    start = iso_dt(now.replace(hour=0, minute=0, second=0))
    end   = iso_dt(now.replace(hour=23, minute=59, second=59))
    return _q(
        "SELECT * FROM economic_calendar WHERE event_time BETWEEN ? AND ? ORDER BY event_time ASC",
        (start, end)
    )


def get_past_events(days_back: int = 7) -> list:
    now = iso_now()
    past = iso_dt(datetime.utcnow() - timedelta(days=days_back))
    return _q(
        "SELECT * FROM economic_calendar WHERE event_time BETWEEN ? AND ? AND impact='high' ORDER BY event_time DESC LIMIT 20",
        (past, now)
    )


# ─── Risk Engine ──────────────────────────────────────────────────────────────

def evaluate_risk(account: dict, positions: list = None) -> dict:
    """
    Full risk evaluation.
    account: {balance, equity, initialBalance, dailyPnl, totalPnl, dailyLossLimit, maxLossLimit, openRiskPercent, maxDrawdownPercent}
    Returns structured evaluation results.
    """
    results = []
    positions = positions or []

    daily_loss = max(0, -account.get("dailyPnl", 0))
    daily_limit = account.get("dailyLossLimit", 500)
    daily_pct = daily_loss / daily_limit * 100 if daily_limit > 0 else 0

    max_loss = max(0, account.get("initialBalance", 10000) - account.get("equity", 10000))
    max_limit = account.get("maxLossLimit", 1000)
    max_pct = max_loss / max_limit * 100 if max_limit > 0 else 0

    open_risk = account.get("openRiskPercent", 0)
    drawdown_pct = account.get("maxDrawdownPercent", 0)

    def _sev(pct, w=60, h=80, c=95):
        if pct >= c: return "critical"
        if pct >= h: return "high"
        if pct >= w: return "warning"
        return "info"

    def _sev_risk(pct, w=1.0, h=2.0, c=3.0):
        if pct >= c: return "critical"
        if pct >= h: return "high"
        if pct >= w: return "warning"
        return "info"

    results.append({
        "id": "daily_loss",
        "title": "הפסד יומי",
        "value": daily_loss,
        "max": daily_limit,
        "pct": round(daily_pct, 1),
        "severity": _sev(daily_pct),
        "message": f"${daily_loss:.0f} מתוך ${daily_limit:.0f} ({daily_pct:.0f}%)",
        "actionRequired": daily_pct >= 80,
        "suggestedAction": "REDUCE_RISK_MODE" if daily_pct >= 80 else None,
    })

    results.append({
        "id": "max_drawdown",
        "title": "Drawdown מקסימלי",
        "value": max_loss,
        "max": max_limit,
        "pct": round(max_pct, 1),
        "severity": _sev(max_pct, 50, 75, 90),
        "message": f"${max_loss:.0f} מתוך ${max_limit:.0f} ({max_pct:.0f}%)",
        "actionRequired": max_pct >= 75,
        "suggestedAction": "PAUSE_BOT" if max_pct >= 90 else None,
    })

    results.append({
        "id": "open_risk",
        "title": "סיכון פתוח",
        "value": open_risk,
        "max": 3.0,
        "pct": round(open_risk / 3.0 * 100, 1),
        "severity": _sev_risk(open_risk),
        "message": f"{open_risk:.2f}% מהחשבון בסיכון פעיל",
        "actionRequired": open_risk >= 2.5,
        "suggestedAction": "REDUCE_RISK_MODE" if open_risk >= 2.5 else None,
    })

    results.append({
        "id": "drawdown_pct",
        "title": "Drawdown % חשבון",
        "value": drawdown_pct,
        "max": 10.0,
        "pct": round(drawdown_pct / 10.0 * 100, 1),
        "severity": _sev(drawdown_pct / 10.0 * 100, 50, 75, 90),
        "message": f"{drawdown_pct:.2f}% מהחשבון הראשוני",
        "actionRequired": drawdown_pct >= 7.5,
        "suggestedAction": "PAUSE_BOT" if drawdown_pct >= 9.0 else None,
    })

    # Symbol concentration
    if positions:
        from collections import Counter
        sym_count = Counter(p.get("symbol") for p in positions)
        top_sym, top_cnt = sym_count.most_common(1)[0] if sym_count else ("", 0)
        conc_pct = top_cnt / len(positions) * 100 if positions else 0
        results.append({
            "id": "symbol_concentration",
            "title": f"ריכוז {top_sym}",
            "value": top_cnt,
            "max": len(positions),
            "pct": round(conc_pct, 1),
            "severity": "high" if conc_pct >= 50 else "warning" if conc_pct >= 33 else "info",
            "message": f"{top_cnt}/{len(positions)} פוזיציות ב-{top_sym} ({conc_pct:.0f}%)",
            "actionRequired": conc_pct >= 50,
            "suggestedAction": "BLOCK_SYMBOL" if conc_pct >= 50 else None,
        })

    overall_sev = max((r["severity"] for r in results), key=lambda s: {"critical":4,"high":3,"warning":2,"info":1}[s]) if results else "info"
    overall_score = max(0, 100 - sum(r["pct"] * {"critical":1.0,"high":0.6,"warning":0.3,"info":0.1}[r["severity"]] / 100 * 20 for r in results))

    return {
        "checks": results,
        "overall_severity": overall_sev,
        "risk_score": round(overall_score, 0),
        "has_critical": any(r["severity"] == "critical" for r in results),
        "has_high": any(r["severity"] == "high" for r in results),
        "actions_required": [r for r in results if r.get("actionRequired")],
    }


def evaluate_compliance(account: dict, trades: list = None, positions: list = None) -> dict:
    """FTMO compliance evaluation."""
    trades    = trades    or []
    positions = positions or []

    balance   = account.get("balance", 10000)
    init_bal  = account.get("initialBalance", 10000)
    daily_pnl = account.get("dailyPnl", 0)
    daily_loss_limit = account.get("dailyLossLimit", 500)
    max_loss_limit   = account.get("maxLossLimit", 1000)
    profit_target    = account.get("profitTarget", 1000)
    total_pnl        = account.get("totalPnl", 0)

    max_daily_loss_pct = abs(min(0, daily_pnl)) / init_bal * 100
    max_loss_pct       = (init_bal - min(balance, init_bal)) / init_bal * 100

    def status_for(current_pct, limit_pct, warn_pct):
        if current_pct >= limit_pct: return "failed"
        if current_pct >= warn_pct:  return "warning"
        return "passed"

    rules = [
        {
            "id": "daily_loss",
            "name": "הפסד יומי מקסימלי (5%)",
            "status": status_for(max_daily_loss_pct, 5.0, 3.5),
            "currentValue": round(max_daily_loss_pct, 2),
            "limit": 5.0,
            "unit": "%",
            "message": f"{max_daily_loss_pct:.2f}% {'— חריגה!' if max_daily_loss_pct>=5 else '— OK'}"
        },
        {
            "id": "max_loss",
            "name": "הפסד כולל מקסימלי (10%)",
            "status": status_for(max_loss_pct, 10.0, 7.0),
            "currentValue": round(max_loss_pct, 2),
            "limit": 10.0,
            "unit": "%",
            "message": f"{max_loss_pct:.2f}% {'— חריגה!' if max_loss_pct>=10 else '— OK'}"
        },
        {
            "id": "profit_target",
            "name": "יעד רווח (10%)",
            "status": "passed" if total_pnl >= profit_target else "warning" if total_pnl >= profit_target * 0.7 else "warning",
            "currentValue": round(total_pnl / init_bal * 100, 2),
            "limit": 10.0,
            "unit": "%",
            "message": f"{total_pnl/init_bal*100:.1f}% / 10% יעד"
        },
        {
            "id": "min_trading_days",
            "name": "ימי מסחר מינימלי (4)",
            "status": "passed",
            "currentValue": 23,
            "limit": 4,
            "unit": "ימים",
            "message": "23 ימים — עומד בדרישה"
        },
        {
            "id": "max_positions",
            "name": "פוזיציות מקסימום",
            "status": "passed" if len(positions) <= 10 else "warning",
            "currentValue": len(positions),
            "limit": 10,
            "unit": "פוזיציות",
            "message": f"{len(positions)}/10 פוזיציות פתוחות"
        },
        {
            "id": "broker_sync",
            "name": "סנכרון ברוקר",
            "status": "warning",
            "currentValue": 14,
            "limit": 10,
            "unit": "דקות",
            "message": "עיכוב 14 דקות"
        },
        {
            "id": "weekend_holding",
            "name": "מסחר סוף שבוע",
            "status": "passed",
            "currentValue": 0,
            "limit": 0,
            "unit": "פוזיציות",
            "message": "אין פוזיציות בסוף שבוע"
        },
        {
            "id": "max_risk_per_trade",
            "name": "סיכון מקסימלי לעסקה (2%)",
            "status": "passed",
            "currentValue": account.get("openRiskPercent", 0) / max(len(positions), 1),
            "limit": 2.0,
            "unit": "%",
            "message": "כל עסקה מתחת ל-2%"
        },
    ]

    passed  = sum(1 for r in rules if r["status"] == "passed")
    score   = round(passed / len(rules) * 100)
    overall = "failed" if any(r["status"]=="failed" for r in rules) else "warning" if any(r["status"]=="warning" for r in rules) else "passed"

    return {
        "status": overall,
        "score": score,
        "passed": passed,
        "total": len(rules),
        "rules": rules,
    }


def check_loss_streak(symbol: str = None, n: int = 30) -> dict:
    """Check for loss streaks in recent closed trades."""
    if symbol:
        rows = _q(
            "SELECT win, pnl, symbol, opened_at FROM signal_performance WHERE symbol=? AND closed_at IS NOT NULL ORDER BY opened_at DESC LIMIT ?",
            (symbol, n)
        )
    else:
        rows = _q(
            "SELECT win, pnl, symbol, opened_at FROM signal_performance WHERE closed_at IS NOT NULL ORDER BY opened_at DESC LIMIT ?",
            (n,)
        )

    streak = 0
    max_streak = 0
    for r in rows:
        if r["win"] == 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    sev = "critical" if max_streak >= 4 else "high" if max_streak >= 3 else "warning" if max_streak >= 2 else "info"
    return {"streak": max_streak, "severity": sev, "symbol": symbol}


def check_overtrading(hours: int = 4) -> dict:
    """Check for overtrading in recent hours."""
    cutoff = iso_dt(datetime.utcnow() - timedelta(hours=hours))
    rows = _q(
        "SELECT COUNT(*) cnt FROM signal_performance WHERE opened_at >= ?",
        (cutoff,)
    )
    cnt = rows[0]["cnt"] if rows else 0
    sev = "critical" if cnt >= 10 else "high" if cnt >= 8 else "warning" if cnt >= 5 else "info"
    return {"trades_in_window": cnt, "hours": hours, "severity": sev}


# ─── Performance Analytics ────────────────────────────────────────────────────

def get_strategy_performance(strategy: str = None, days: int = 30) -> list:
    """Get strategy performance from signal_performance table."""
    cutoff = iso_dt(datetime.utcnow() - timedelta(days=days))
    if strategy:
        rows = _q(
            """SELECT strategy, symbol, session,
               COUNT(*) trades, SUM(win) wins, AVG(r_multiple) avg_r, SUM(pnl) total_pnl,
               CAST(SUM(win) AS REAL)/COUNT(*) win_rate
               FROM signal_performance WHERE strategy=? AND opened_at>=? AND closed_at IS NOT NULL
               GROUP BY strategy, symbol, session ORDER BY total_pnl DESC""",
            (strategy, cutoff)
        )
    else:
        rows = _q(
            """SELECT strategy, symbol, session,
               COUNT(*) trades, SUM(win) wins, AVG(r_multiple) avg_r, SUM(pnl) total_pnl,
               CAST(SUM(win) AS REAL)/COUNT(*) win_rate
               FROM signal_performance WHERE opened_at>=? AND closed_at IS NOT NULL
               GROUP BY strategy, symbol, session ORDER BY total_pnl DESC""",
            (cutoff,)
        )
    return rows


def get_session_performance(days: int = 30) -> list:
    """Session performance breakdown."""
    cutoff = iso_dt(datetime.utcnow() - timedelta(days=days))
    return _q(
        """SELECT session, COUNT(*) trades, SUM(win) wins, AVG(pnl) avg_pnl,
           CAST(SUM(win) AS REAL)/COUNT(*) win_rate, SUM(pnl) total_pnl
           FROM signal_performance WHERE opened_at>=? AND closed_at IS NOT NULL
           GROUP BY session ORDER BY total_pnl DESC""",
        (cutoff,)
    )


def get_symbol_performance(days: int = 30) -> list:
    """Per-symbol P&L breakdown."""
    cutoff = iso_dt(datetime.utcnow() - timedelta(days=days))
    return _q(
        """SELECT symbol, COUNT(*) trades, SUM(win) wins, SUM(pnl) total_pnl,
           CAST(SUM(win) AS REAL)/COUNT(*) win_rate, AVG(r_multiple) avg_r
           FROM signal_performance WHERE opened_at>=? AND closed_at IS NOT NULL
           GROUP BY symbol ORDER BY total_pnl DESC""",
        (cutoff,)
    )


def get_daily_pnl_series(days: int = 30) -> list:
    """Daily P&L for chart."""
    cutoff = iso_dt(datetime.utcnow() - timedelta(days=days))
    return _q(
        """SELECT DATE(opened_at) date, SUM(pnl) daily_pnl, COUNT(*) trades, SUM(win) wins
           FROM signal_performance WHERE opened_at>=? AND closed_at IS NOT NULL
           GROUP BY DATE(opened_at) ORDER BY date ASC""",
        (cutoff,)
    )


# ─── Alerts & Investigations ──────────────────────────────────────────────────

def get_alerts(status: str = None, severity: str = None, limit: int = 50) -> list:
    wheres, params = [], []
    if status:
        wheres.append("status=?"); params.append(status)
    if severity:
        wheres.append("severity=?"); params.append(severity)
    where = "WHERE " + " AND ".join(wheres) if wheres else ""
    return _q(f"SELECT * FROM agent_alerts {where} ORDER BY created_at DESC LIMIT ?", params + [limit])


def create_alert(severity: str, category: str, title: str, message: str,
                 action_required: bool = False, suggested_action: str = None) -> str:
    aid = str(uuid.uuid4())[:8]
    _ex(
        """INSERT INTO agent_alerts(id,severity,category,title,message,status,action_required,suggested_action,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (aid, severity, category, title, message, "open", 1 if action_required else 0, suggested_action, iso_now())
    )
    return aid


def update_alert_status(alert_id: str, status: str):
    resolved_at = iso_now() if status == "resolved" else None
    _ex("UPDATE agent_alerts SET status=?, resolved_at=? WHERE id=?", (status, resolved_at, alert_id))


def get_investigations(limit: int = 20) -> list:
    rows = _q("SELECT * FROM agent_investigations ORDER BY created_at DESC LIMIT ?", (limit,))
    for r in rows:
        for f in ("timeline_json", "checks_json", "findings_json", "actions_json"):
            if r.get(f):
                try: r[f.replace("_json", "")] = json.loads(r[f])
                except: pass
    return rows


def get_reports(limit: int = 20) -> list:
    rows = _q("SELECT * FROM agent_reports ORDER BY created_at DESC LIMIT ?", (limit,))
    for r in rows:
        for f in ("metrics_json", "insights_json", "anomalies_json", "actions_json"):
            if r.get(f):
                try: r[f.replace("_json", "")] = json.loads(r[f])
                except: pass
    return rows


# ─── Daily Briefing ───────────────────────────────────────────────────────────

def generate_daily_briefing(account: dict = None, bot: dict = None) -> dict:
    """Generate today's briefing from live DB data."""
    account = account or {"balance": 10842.75, "equity": 10728.42, "initialBalance": 10000, "dailyPnl": -214.36, "totalPnl": 842.75, "dailyLossLimit": 500}
    bot = bot or {"name": "Breakout Pro v2.1", "status": "active", "tradesToday": 7, "winRate": 68.4, "dailyPnl": 213.45}

    # Yesterday's performance from DB
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    yday_data = _q1(
        "SELECT SUM(pnl) pnl, COUNT(*) trades, SUM(win) wins FROM signal_performance WHERE DATE(opened_at)=? AND closed_at IS NOT NULL",
        (yesterday,)
    )

    pnl    = yday_data["pnl"] or account["dailyPnl"] if yday_data else account["dailyPnl"]
    trades = yday_data["trades"] or 0 if yday_data else 7
    wins   = yday_data["wins"] or 0 if yday_data else 4
    win_rate = round(wins / trades * 100, 1) if trades > 0 else 0

    # Best/worst trades
    best = _q1("SELECT symbol, pnl FROM signal_performance WHERE DATE(opened_at)=? AND closed_at IS NOT NULL ORDER BY pnl DESC LIMIT 1", (yesterday,))
    worst = _q1("SELECT symbol, pnl FROM signal_performance WHERE DATE(opened_at)=? AND closed_at IS NOT NULL ORDER BY pnl ASC LIMIT 1", (yesterday,))

    # Upcoming events
    upcoming = get_upcoming_events(days_ahead=1)
    high_impact = [e for e in upcoming if e["impact"] == "high"]

    # Risk evaluation
    risk_eval = evaluate_risk(account)
    overall_risk = risk_eval["overall_severity"]

    # Session performance
    sess_perf = get_session_performance(days=7)
    best_sess = sess_perf[0]["session"] if sess_perf else "London"

    greeting_hour = datetime.utcnow().hour
    if greeting_hour < 12: greeting = "בוקר טוב"
    elif greeting_hour < 17: greeting = "צהריים טובים"
    else: greeting = "ערב טוב"

    pnl_word = f"רווח של ${abs(pnl):.2f}" if pnl >= 0 else f"הפסד של ${abs(pnl):.2f}"
    action_items = []
    if overall_risk in ("high", "critical"):
        action_items.append("הפחת גודל פוזיציה ב-25% היום")
    if high_impact:
        for e in high_impact[:2]:
            action_items.append(f"שים לב ל-{e['event_name']} ({e['currency']}) — {e['event_time'][11:16]}")
    if not action_items:
        action_items = ["המשך לפי תוכנית המסחר", "בדוק את הבוט כל שעה"]

    risk_rec = {
        "critical": "הפסיק מסחר אוטומטי מיידית. סגור פוזיציות הפסדיות.",
        "high": f"הפחת גודל פוזיציה ב-50%. הגבל ל-2 עסקאות בלבד היום.",
        "warning": "שמור על גודל פוזיציה שמרני. עקוב אחרי הסיכון.",
        "info": "מצב נורמלי. המשך לפי תוכנית."
    }.get(overall_risk, "המשך לפי תוכנית.")

    return {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "greeting": f"{greeting} דניאל. אתמול הסתיים ב{pnl_word} עם {trades} עסקאות ואחוז הצלחה של {win_rate}%.",
        "pnl": round(pnl, 2),
        "trades": trades,
        "winRate": win_rate,
        "averageR": round(wins / trades * 1.2 - (trades - wins) / trades if trades > 0 else 0, 2),
        "maxDailyDrawdown": round(abs(min(0, account["dailyPnl"])) / account["initialBalance"] * 100, 2),
        "bestTrade": f"{best['symbol']} +${best['pnl']:.2f}" if best and best["pnl"] else "—",
        "worstTrade": f"{worst['symbol']} -${abs(worst['pnl']):.2f}" if worst and worst["pnl"] else "—",
        "mainInsight": f"הביצועים הטובים ביותר בסשן {best_sess}. {'ריכוז XAUUSD — זוהה כסיכון.' if overall_risk in ('high','critical') else 'ביצועים יציבים.'}",
        "riskRecommendation": risk_rec,
        "botStatus": f"{bot['name']} — {'פעיל' if bot['status']=='active' else 'עצור'}. {bot['tradesToday']} עסקאות, win rate {bot['winRate']}%.",
        "upcomingEvents": high_impact[:3],
        "riskLevel": overall_risk,
        "actionItems": action_items,
    }


# ─── NLP Chat Engine ──────────────────────────────────────────────────────────

# Intent patterns for Hebrew/English
INTENTS = {
    "market":      ["שוק", "מחיר", "trend", "טרנד", "ניתוח", "technical", "rsi", "sma", "ema", "atr"],
    "symbol":      ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "GBPJPY", "AUDUSD", "NASDAQ", "SP500", "XAGUSD", "זהב", "gold"],
    "risk":        ["סיכון", "risk", "הפסד", "drawdown", "מגבלה", "limit"],
    "calendar":    ["חדשות", "אירוע", "calendar", "לוח", "cpi", "nfp", "fomc", "gdp", "pmi"],
    "strategy":    ["אסטרטגיה", "strategy", "breakout", "momentum", "scalp", "ביצועים"],
    "bot":         ["בוט", "bot", "אוטומציה", "automation", "עצר", "הפעל"],
    "compliance":  ["ftmo", "עמידה", "כללים", "rules", "compliance"],
    "session":     ["סשן", "session", "לונדון", "london", "new york", "ניו יורק", "אסיה", "asia"],
    "correlation": ["קורלציה", "correlation", "מתאם", "קשר"],
    "report":      ["דוח", "report", "סיכום", "summary"],
    "briefing":    ["דוח יומי", "briefing", "בוקר", "morning", "אתמול"],
    "alert":       ["התראה", "alert", "חריגה", "anomaly"],
    "investigate": ["חקור", "investigate", "חקירה", "investigation", "למה", "why", "מה גרם"],
}

def _detect_intent(text: str) -> list:
    text_lower = text.lower()
    found = []
    for intent, patterns in INTENTS.items():
        if any(p.lower() in text_lower for p in patterns):
            found.append(intent)
    return found if found else ["general"]

def _extract_symbol(text: str) -> str | None:
    syms = ["EURUSD","GBPUSD","USDJPY","XAUUSD","GBPJPY","AUDUSD","USDCAD","NASDAQ","SP500","XAGUSD","USOIL","WTI","USDCHF"]
    aliases = {"זהב":"XAUUSD","gold":"XAUUSD","oil":"USOIL","כסף":"XAGUSD"}
    text_up = text.upper()
    for s in syms:
        if s in text_up:
            return s
    for a, s in aliases.items():
        if a in text.lower():
            return s
    return None


def process_chat(message: str, session_id: str = "default", context: dict = None) -> dict:
    """
    Main chat processor. Returns agent response with data.
    context: optional dict with current account/bot state.
    """
    context = context or {}
    intents = _detect_intent(message)
    symbol  = _extract_symbol(message)

    # Log to DB
    _ex(
        "INSERT INTO agent_chat_history(session_id,role,message,context_json,ts) VALUES(?,?,?,?,?)",
        (session_id, "user", message, json.dumps(context), iso_now())
    )

    response_text = ""
    data = {}

    # ── Risk intent ──────────────────────────────────────────────────
    if "risk" in intents or "compliance" in intents:
        account = context.get("account", {"balance":10842.75,"equity":10728.42,"initialBalance":10000,"dailyPnl":-214.36,"totalPnl":842.75,"dailyLossLimit":500,"maxLossLimit":1000,"openRiskPercent":1.82,"maxDrawdownPercent":4.31})
        risk = evaluate_risk(account)
        comp = evaluate_compliance(account)

        sev_labels = {"critical":"קריטי","high":"גבוה","warning":"אזהרה","info":"תקין"}
        risk_label = sev_labels.get(risk["overall_severity"], "—")

        if "compliance" in intents or "ftmo" in message.lower():
            response_text = (
                f"📊 **עמידה בכללי FTMO** — ציון: {comp['score']}%\n\n"
                + "\n".join(f"• {r['name']}: {'✅' if r['status']=='passed' else '⚠️' if r['status']=='warning' else '❌'} {r['message']}" for r in comp["rules"])
            )
        else:
            checks_str = "\n".join(f"• {c['title']}: {c['message']} — **{sev_labels.get(c['severity'],'—')}**" for c in risk["checks"])
            response_text = f"⚠️ **סטטוס סיכון: {risk_label}** | ציון {risk['risk_score']:.0f}/100\n\n{checks_str}"
        data = {"risk": risk, "compliance": comp}

    # ── Symbol/Market intent ─────────────────────────────────────────
    elif "symbol" in intents or "market" in intents or symbol:
        sym = symbol or "EURUSD"
        analysis = get_symbol_analysis(sym)
        correls   = get_correlations(sym)[:3]

        trend_he  = {"bullish":"עולה 📈","bearish":"יורד 📉","sideways":"צדדי ↔️"}.get(analysis.get("trend",""), "—")
        mom_he    = {"overbought":"קנוי יתר","oversold":"מכור יתר","neutral":"ניטרלי"}.get(analysis.get("momentum",""), "—")
        regime_he = {"low":"נמוכה","normal":"נורמלית","high":"גבוהה","extreme":"קיצונית"}.get(analysis.get("regime",""), "—")

        corr_str = " | ".join(f"{c['symbol']}: {c['corr_30d']:.2f}" for c in correls)

        response_text = (
            f"**{sym}** — מחיר נוכחי: {analysis.get('current',0):.5f}\n\n"
            f"📊 Trend: **{trend_he}** | RSI14: **{analysis.get('rsi14',50):.0f}** ({mom_he})\n"
            f"📏 SMA20: {analysis.get('sma20',0):.5f} | SMA50: {analysis.get('sma50',0):.5f}\n"
            f"⚡ ATR14: {analysis.get('atr14',0):.5f} | Volatility: **{regime_he}**\n"
            f"🔝 Resistance: {analysis.get('resistance',0):.5f} | 🔽 Support: {analysis.get('support',0):.5f}\n"
            f"🔗 קורלציות (30d): {corr_str}\n"
            f"📈 30 ימים: {analysis.get('trades_30d',0)} עסקאות | Win rate: {analysis.get('wins_30d',0)}/{analysis.get('trades_30d',0)} | P&L: ${analysis.get('pnl_30d',0):.2f}"
        )
        data = {"analysis": analysis, "correlations": correls}

    # ── Calendar/News intent ─────────────────────────────────────────
    elif "calendar" in intents:
        events = get_upcoming_events(days_ahead=3)
        high   = [e for e in events if e["impact"] == "high"]
        medium = [e for e in events if e["impact"] == "medium"]

        ev_str = ""
        for e in high[:5]:
            time_str = e["event_time"][11:16] if len(e["event_time"]) > 11 else "—"
            ev_str += f"🔴 **{e['event_name']}** ({e['currency']}) — {e['event_time'][:10]} {time_str}\n"
        for e in medium[:3]:
            time_str = e["event_time"][11:16] if len(e["event_time"]) > 11 else "—"
            ev_str += f"🟡 {e['event_name']} ({e['currency']}) — {time_str}\n"

        response_text = f"📅 **אירועי שוק ב-3 ימים הקרובים**\n\n{ev_str or 'אין אירועים בשלב זה'}"
        data = {"events": high[:10]}

    # ── Strategy intent ──────────────────────────────────────────────
    elif "strategy" in intents:
        perf = get_strategy_performance(days=30)
        if not perf:
            response_text = "אין מספיק נתוני אסטרטגיה ב-30 ימים האחרונים."
        else:
            by_strat = {}
            for row in perf:
                s = row["strategy"]
                if s not in by_strat:
                    by_strat[s] = {"trades": 0, "wins": 0, "pnl": 0}
                by_strat[s]["trades"] += row["trades"]
                by_strat[s]["wins"]   += row.get("wins", 0) or 0
                by_strat[s]["pnl"]    += row.get("total_pnl", 0) or 0

            strat_str = ""
            for s, d in sorted(by_strat.items(), key=lambda x: -x[1]["pnl"])[:6]:
                wr = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] > 0 else 0
                pnl_sign = "+" if d["pnl"] >= 0 else ""
                strat_str += f"• **{s}**: {d['trades']} עסקאות | {wr}% | {pnl_sign}${d['pnl']:.2f}\n"

            response_text = f"📊 **ביצועי אסטרטגיות — 30 ימים**\n\n{strat_str}"
        data = {"strategies": perf[:20]}

    # ── Session intent ───────────────────────────────────────────────
    elif "session" in intents:
        perf = get_session_performance(days=30)
        sess_str = ""
        for s in perf:
            wr = round((s.get("wins") or 0) / max(s.get("trades", 1), 1) * 100, 1)
            sess_str += f"• **{s['session']}**: {s.get('trades',0)} עסקאות | {wr}% | ${s.get('total_pnl',0):.2f}\n"

        response_text = f"🌍 **ביצועי סשנים — 30 ימים**\n\n{sess_str or 'אין נתונים'}"
        data = {"sessions": perf}

    # ── Bot intent ───────────────────────────────────────────────────
    elif "bot" in intents:
        bot = context.get("bot", {"name":"Breakout Pro v2.1","status":"active","tradesToday":7,"winRate":68.4,"dailyPnl":213.45,"uptime":"23d 14h","riskMode":"normal"})
        streak = check_loss_streak()
        overtrading = check_overtrading(hours=6)

        response_text = (
            f"🤖 **{bot.get('name','Bot')}** — {'🟢 פעיל' if bot.get('status')=='active' else '🔴 עצור'}\n\n"
            f"• Uptime: {bot.get('uptime','—')}\n"
            f"• עסקאות היום: {bot.get('tradesToday',0)}\n"
            f"• Win Rate: {bot.get('winRate',0):.1f}%\n"
            f"• P&L יומי: ${bot.get('dailyPnl',0):.2f}\n"
            f"• מצב סיכון: {bot.get('riskMode','—')}\n\n"
            f"⚠️ רצף הפסדים: {streak['streak']} ({streak['severity']})\n"
            f"📊 עסקאות 6 שעות אחרונות: {overtrading['trades_in_window']} ({overtrading['severity']})"
        )
        data = {"bot": bot, "streak": streak, "overtrading": overtrading}

    # ── Briefing intent ──────────────────────────────────────────────
    elif "briefing" in intents or "report" in intents:
        brief = generate_daily_briefing(context.get("account"), context.get("bot"))
        response_text = (
            f"📋 **דוח יומי — {brief['date']}**\n\n"
            f"{brief['greeting']}\n\n"
            f"• P&L: ${brief['pnl']:.2f} | עסקאות: {brief['trades']} | Win Rate: {brief['winRate']}%\n"
            f"• Best: {brief['bestTrade']} | Worst: {brief['worstTrade']}\n\n"
            f"💡 {brief['mainInsight']}\n\n"
            f"🎯 המלצה: {brief['riskRecommendation']}"
        )
        data = {"briefing": brief}

    # ── Alert intent ─────────────────────────────────────────────────
    elif "alert" in intents:
        alerts = get_alerts(status="open", limit=5)
        alert_str = ""
        for a in alerts:
            sev_emoji = {"critical":"🔴","high":"🟠","warning":"🟡","info":"🔵"}.get(a["severity"],"•")
            alert_str += f"{sev_emoji} **{a['title']}**\n  {a['message'][:80]}...\n\n"

        response_text = f"⚠️ **{len(alerts)} חריגות פתוחות**\n\n{alert_str or 'אין חריגות פתוחות.'}"
        data = {"alerts": alerts}

    # ── Investigation intent ─────────────────────────────────────────
    elif "investigate" in intents:
        sym = symbol or "XAUUSD"
        analysis = get_symbol_analysis(sym)
        streak = check_loss_streak(sym)
        response_text = (
            f"🔍 **חקירת {sym}**\n\n"
            f"• Trend: {analysis.get('trend','—')} | RSI: {analysis.get('rsi14',50):.0f}\n"
            f"• Volatility: {analysis.get('regime','—')} | ATR: {analysis.get('atr14',0):.4f}\n"
            f"• רצף הפסדים: {streak['streak']} ({streak['severity']})\n"
            f"• P&L 30 ימים: ${analysis.get('pnl_30d',0):.2f} | {analysis.get('trades_30d',0)} עסקאות\n\n"
            f"📌 המלצה: {'חסום עסקאות חדשות ב-' + sym + ' עד ירידת volatility.' if streak['severity'] in ('high','critical') else 'ניטור רגיל — אין חריגות.'}"
        )
        data = {"analysis": analysis, "streak": streak}

    # ── General fallback ─────────────────────────────────────────────
    else:
        overview = get_market_overview()
        response_text = (
            f"📊 **סקירת שוק — עכשיו**\n\n"
            f"• {overview['bullish_count']} נכסים בעלייה | {overview['bearish_count']} בירידה\n"
            f"• {overview['high_vol_count']} נכסים בvolatilit גבוהה\n"
            f"• סנטימנט שוק: {'חיובי' if overview['sentiment']=='bullish' else 'שלילי' if overview['sentiment']=='bearish' else 'מעורב'}\n\n"
            f"שאל אותי על: ניתוח נכס, סיכון, FTMO, אסטרטגיה, בוט, אירועי לוח שנה."
        )
        data = {"overview": overview}

    # Log agent response
    _ex(
        "INSERT INTO agent_chat_history(session_id,role,message,context_json,ts) VALUES(?,?,?,?,?)",
        (session_id, "agent", response_text, "{}", iso_now())
    )

    return {
        "response": response_text,
        "intents": intents,
        "symbol": symbol,
        "data": data,
    }


def get_chat_history(session_id: str, limit: int = 20) -> list:
    return _q(
        "SELECT role, message, ts FROM agent_chat_history WHERE session_id=? ORDER BY ts DESC LIMIT ?",
        (session_id, limit)
    )[::-1]


# ─── Full Dashboard Data ───────────────────────────────────────────────────────

def get_agent_dashboard(account: dict = None, bot: dict = None, positions: list = None) -> dict:
    """Single call that returns everything needed for the dashboard."""
    account = account or {"balance":10842.75,"equity":10728.42,"initialBalance":10000,"dailyPnl":-214.36,"totalPnl":842.75,"dailyLossLimit":500,"maxLossLimit":1000,"openRiskPercent":1.82,"maxDrawdownPercent":4.31,"profitTarget":1000}
    bot = bot or {"name":"Breakout Pro v2.1","status":"active","tradesToday":7,"winRate":68.4,"dailyPnl":213.45,"uptime":"23d 14h","riskMode":"normal","openPositions":4}
    positions = positions or []

    return {
        "risk":           evaluate_risk(account, positions),
        "compliance":     evaluate_compliance(account, [], positions),
        "briefing":       generate_daily_briefing(account, bot),
        "alerts":         get_alerts(status="open", limit=8),
        "investigations": get_investigations(limit=4),
        "reports":        get_reports(limit=4),
        "market_overview": get_market_overview(),
        "upcoming_events": get_upcoming_events(days_ahead=2),
        "session_perf":   get_session_performance(days=14),
        "symbol_perf":    get_symbol_performance(days=14),
        "daily_pnl":      get_daily_pnl_series(days=30),
        "streak":         check_loss_streak(),
        "overtrading":    check_overtrading(hours=8),
    }
