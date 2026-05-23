"""
EMPIREX Stock Analysis Engine
==============================
Real-time deep stock analysis with SSE streaming:
- Full historical data from IPO via yfinance (production)
- Realistic simulation fallback when network is restricted (demo)
- 30+ technical indicators (RSI, MACD, Bollinger, Stochastic, ATR, ADX, CCI, OBV…)
- Fundamental analysis (P/E, EPS, Revenue, FCF, margins…)
- Statistical analysis (Volatility, Beta, Sharpe, VaR, Max Drawdown…)
- AI-powered investment report (Claude API or rule-based)
- Progress streaming via callback
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

try:
    import numpy as np
    import pandas as pd
    _NUMPY_OK = True
except ImportError:
    _NUMPY_OK = False

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False

# ─── Anthropic / Claude AI (optional) ────────────────────────────────────────
try:
    import anthropic as _anthropic_mod
    _ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
    _AI_AVAILABLE = bool(_ANTHROPIC_KEY)
except ImportError:
    _anthropic_mod = None
    _ANTHROPIC_KEY = ""
    _AI_AVAILABLE = False


# ─── Known stocks database (for realistic simulation fallback) ────────────────
KNOWN_STOCKS = {
    # symbol: {cur_px=current_price, ipo_px=IPO_price, ipo=IPO_date, ...fundamentals}
    "AAPL":  {"name":"Apple Inc.", "sector":"Technology", "industry":"Consumer Electronics", "country":"US", "ipo":"1980-12-12", "ipo_px":0.10, "cur_px":213.5, "mktcap":3.28e12, "pe":33, "eps":6.43, "rev":383e9, "margin":0.245, "roe":0.87, "de":1.5, "div":0.005, "beta":1.2, "mu":0.18, "sigma":0.22},
    "MSFT":  {"name":"Microsoft Corp.", "sector":"Technology", "industry":"Software", "country":"US", "ipo":"1986-03-13", "ipo_px":0.09, "cur_px":453.2, "mktcap":3.37e12, "pe":36, "eps":12.93, "rev":245e9, "margin":0.365, "roe":0.42, "de":0.25, "div":0.007, "beta":0.9, "mu":0.20, "sigma":0.20},
    "NVDA":  {"name":"NVIDIA Corp.", "sector":"Technology", "industry":"Semiconductors", "country":"US", "ipo":"1999-01-22", "ipo_px":0.38, "cur_px":137.0, "mktcap":3.36e12, "pe":56, "eps":2.99, "rev":130e9, "margin":0.556, "roe":1.23, "de":0.45, "div":0.001, "beta":1.7, "mu":0.55, "sigma":0.50},
    "TSLA":  {"name":"Tesla Inc.", "sector":"Consumer Cyclical", "industry":"Electric Vehicles", "country":"US", "ipo":"2010-06-29", "ipo_px":17.0, "cur_px":332.0, "mktcap":1.07e12, "pe":110, "eps":2.34, "rev":97e9, "margin":0.092, "roe":0.25, "de":0.18, "div":0.0, "beta":2.0, "mu":0.28, "sigma":0.60},
    "AMZN":  {"name":"Amazon.com Inc.", "sector":"Consumer Cyclical", "industry":"Internet Retail", "country":"US", "ipo":"1997-05-15", "ipo_px":1.73, "cur_px":207.3, "mktcap":2.19e12, "pe":38, "eps":4.84, "rev":575e9, "margin":0.057, "roe":0.23, "de":0.55, "div":0.0, "beta":1.3, "mu":0.25, "sigma":0.30},
    "GOOGL": {"name":"Alphabet Inc.", "sector":"Communication Services", "industry":"Internet Search", "country":"US", "ipo":"2004-08-19", "ipo_px":85.0, "cur_px":179.2, "mktcap":2.17e12, "pe":20, "eps":8.89, "rev":350e9, "margin":0.238, "roe":0.32, "de":0.05, "div":0.003, "beta":1.1, "mu":0.20, "sigma":0.25},
    "META":  {"name":"Meta Platforms Inc.", "sector":"Communication Services", "industry":"Social Media", "country":"US", "ipo":"2012-05-18", "ipo_px":38.0, "cur_px":634.0, "mktcap":1.60e12, "pe":25, "eps":23.86, "rev":164e9, "margin":0.357, "roe":0.35, "de":0.15, "div":0.004, "beta":1.2, "mu":0.22, "sigma":0.35},
    "AMD":   {"name":"Advanced Micro Devices", "sector":"Technology", "industry":"Semiconductors", "country":"US", "ipo":"1972-09-27", "ipo_px":0.02, "cur_px":112.0, "mktcap":181e9, "pe":95, "eps":1.04, "rev":25e9, "margin":0.050, "roe":0.12, "de":0.30, "div":0.0, "beta":1.9, "mu":0.30, "sigma":0.55},
    "NFLX":  {"name":"Netflix Inc.", "sector":"Communication Services", "industry":"Streaming", "country":"US", "ipo":"2002-05-23", "ipo_px":15.0, "cur_px":1282.0, "mktcap":550e9, "pe":56, "eps":22.5, "rev":39e9, "margin":0.22, "roe":0.38, "de":1.1, "div":0.0, "beta":1.3, "mu":0.28, "sigma":0.45},
    "DIS":   {"name":"Walt Disney Co.", "sector":"Communication Services", "industry":"Entertainment", "country":"US", "ipo":"1957-11-12", "ipo_px":0.05, "cur_px":95.0, "mktcap":173e9, "pe":31, "eps":3.55, "rev":91e9, "margin":0.055, "roe":0.07, "de":0.65, "div":0.011, "beta":1.1, "mu":0.08, "sigma":0.28},
    "BABA":  {"name":"Alibaba Group Holding", "sector":"Consumer Cyclical", "industry":"Internet Retail", "country":"CN", "ipo":"2014-09-19", "ipo_px":92.7, "cur_px":105.0, "mktcap":238e9, "pe":17, "eps":9.50, "rev":130e9, "margin":0.09, "roe":0.10, "de":0.28, "div":0.0, "beta":0.7, "mu":0.02, "sigma":0.35},
    "JPM":   {"name":"JPMorgan Chase & Co.", "sector":"Financial Services", "industry":"Banking", "country":"US", "ipo":"1969-01-02", "ipo_px":0.05, "cur_px":282.0, "mktcap":817e9, "pe":13, "eps":21.2, "rev":165e9, "margin":0.33, "roe":0.17, "de":1.8, "div":0.022, "beta":1.0, "mu":0.14, "sigma":0.22},
    "V":     {"name":"Visa Inc.", "sector":"Financial Services", "industry":"Credit Services", "country":"US", "ipo":"2008-03-19", "ipo_px":44.0, "cur_px":363.0, "mktcap":760e9, "pe":34, "eps":10.46, "rev":36e9, "margin":0.544, "roe":0.47, "de":0.68, "div":0.007, "beta":0.9, "mu":0.16, "sigma":0.18},
    "BRK-B": {"name":"Berkshire Hathaway B", "sector":"Financial Services", "industry":"Insurance", "country":"US", "ipo":"1996-05-09", "ipo_px":22.0, "cur_px":544.0, "mktcap":1.24e12, "pe":22, "eps":46.0, "rev":364e9, "margin":0.12, "roe":0.10, "de":0.45, "div":0.0, "beta":0.8, "mu":0.12, "sigma":0.15},
    "WMT":   {"name":"Walmart Inc.", "sector":"Consumer Defensive", "industry":"Discount Stores", "country":"US", "ipo":"1972-10-01", "ipo_px":0.07, "cur_px":97.0, "mktcap":779e9, "pe":38, "eps":2.42, "rev":680e9, "margin":0.024, "roe":0.21, "de":1.5, "div":0.010, "beta":0.55, "mu":0.13, "sigma":0.16},
    "XOM":   {"name":"Exxon Mobil Corp.", "sector":"Energy", "industry":"Oil & Gas", "country":"US", "ipo":"1970-01-02", "ipo_px":0.15, "cur_px":112.0, "mktcap":493e9, "pe":15, "eps":8.89, "rev":398e9, "margin":0.088, "roe":0.16, "de":0.23, "div":0.034, "beta":1.1, "mu":0.10, "sigma":0.25},
    "UNH":   {"name":"UnitedHealth Group", "sector":"Healthcare", "industry":"Health Insurance", "country":"US", "ipo":"1984-10-17", "ipo_px":0.05, "cur_px":305.0, "mktcap":286e9, "pe":15, "eps":21.50, "rev":400e9, "margin":0.058, "roe":0.24, "de":0.85, "div":0.016, "beta":0.65, "mu":0.14, "sigma":0.20},
    "AVGO":  {"name":"Broadcom Inc.", "sector":"Technology", "industry":"Semiconductors", "country":"US", "ipo":"2009-08-06", "ipo_px":17.5, "cur_px":237.0, "mktcap":1.12e12, "pe":28, "eps":5.25, "rev":57e9, "margin":0.51, "roe":0.35, "de":1.2, "div":0.013, "beta":1.1, "mu":0.28, "sigma":0.32},
    "MA":    {"name":"Mastercard Inc.", "sector":"Financial Services", "industry":"Credit Services", "country":"US", "ipo":"2006-05-25", "ipo_px":39.0, "cur_px":555.0, "mktcap":514e9, "pe":40, "eps":13.31, "rev":28e9, "margin":0.466, "roe":1.8, "de":2.1, "div":0.005, "beta":1.0, "mu":0.17, "sigma":0.20},
    "PG":    {"name":"Procter & Gamble Co.", "sector":"Consumer Defensive", "industry":"Household Products", "country":"US", "ipo":"1944-01-02", "ipo_px":0.01, "cur_px":168.0, "mktcap":397e9, "pe":27, "eps":6.02, "rev":84e9, "margin":0.184, "roe":0.33, "de":0.65, "div":0.024, "beta":0.55, "mu":0.10, "sigma":0.14},
    "HD":    {"name":"Home Depot Inc.", "sector":"Consumer Cyclical", "industry":"Home Improvement", "country":"US", "ipo":"1981-09-22", "ipo_px":0.05, "cur_px":375.0, "mktcap":373e9, "pe":25, "eps":15.13, "rev":153e9, "margin":0.099, "roe":None, "de":9.5, "div":0.022, "beta":1.1, "mu":0.15, "sigma":0.22},
    "INTC":  {"name":"Intel Corp.", "sector":"Technology", "industry":"Semiconductors", "country":"US", "ipo":"1971-10-13", "ipo_px":0.03, "cur_px":19.5, "mktcap":83e9, "pe":None, "eps":-0.37, "rev":53e9, "margin":-0.02, "roe":-0.02, "de":0.62, "div":0.020, "beta":1.0, "mu":-0.10, "sigma":0.32},
    "KO":    {"name":"Coca-Cola Co.", "sector":"Consumer Defensive", "industry":"Beverages", "country":"US", "ipo":"1919-09-05", "ipo_px":0.003, "cur_px":73.0, "mktcap":315e9, "pe":26, "eps":2.69, "rev":46e9, "margin":0.226, "roe":0.38, "de":1.8, "div":0.029, "beta":0.6, "mu":0.10, "sigma":0.13},
    "PFE":   {"name":"Pfizer Inc.", "sector":"Healthcare", "industry":"Drug Manufacturers", "country":"US", "ipo":"1972-01-02", "ipo_px":0.10, "cur_px":24.5, "mktcap":138e9, "pe":20, "eps":1.41, "rev":58e9, "margin":0.02, "roe":0.05, "de":0.60, "div":0.068, "beta":0.65, "mu":0.04, "sigma":0.22},
    "BAC":   {"name":"Bank of America Corp.", "sector":"Financial Services", "industry":"Banking", "country":"US", "ipo":"1972-01-02", "ipo_px":0.10, "cur_px":47.5, "mktcap":374e9, "pe":15, "eps":3.40, "rev":101e9, "margin":0.31, "roe":0.10, "de":1.2, "div":0.022, "beta":1.3, "mu":0.10, "sigma":0.28},
    "SPOT":  {"name":"Spotify Technology SA", "sector":"Communication Services", "industry":"Streaming", "country":"LU", "ipo":"2018-04-03", "ipo_px":149.0, "cur_px":615.0, "mktcap":117e9, "pe":155, "eps":4.85, "rev":17e9, "margin":0.045, "roe":0.12, "de":0.30, "div":0.0, "beta":1.5, "mu":0.25, "sigma":0.48},
    "UBER":  {"name":"Uber Technologies Inc.", "sector":"Technology", "industry":"Rideshare", "country":"US", "ipo":"2019-05-10", "ipo_px":45.0, "cur_px":87.0, "mktcap":183e9, "pe":25, "eps":3.11, "rev":43e9, "margin":0.078, "roe":0.35, "de":0.85, "div":0.0, "beta":1.4, "mu":0.24, "sigma":0.45},
    "COIN":  {"name":"Coinbase Global Inc.", "sector":"Financial Services", "industry":"Crypto Exchange", "country":"US", "ipo":"2021-04-14", "ipo_px":381.0, "cur_px":263.0, "mktcap":64e9, "pe":None, "eps":6.70, "rev":6.5e9, "margin":0.18, "roe":0.12, "de":0.55, "div":0.0, "beta":2.8, "mu":0.05, "sigma":0.90},
    "PYPL":  {"name":"PayPal Holdings Inc.", "sector":"Financial Services", "industry":"Payments", "country":"US", "ipo":"2002-02-15", "ipo_px":13.0, "cur_px":72.0, "mktcap":70e9, "pe":18, "eps":4.73, "rev":30e9, "margin":0.155, "roe":0.18, "de":0.65, "div":0.0, "beta":1.4, "mu":0.05, "sigma":0.38},
    "SHOP":  {"name":"Shopify Inc.", "sector":"Technology", "industry":"E-commerce", "country":"CA", "ipo":"2015-05-21", "ipo_px":17.0, "cur_px":108.0, "mktcap":137e9, "pe":70, "eps":1.29, "rev":9.9e9, "margin":0.050, "roe":0.09, "de":0.10, "div":0.0, "beta":1.8, "mu":0.30, "sigma":0.55},
    "PLTR":  {"name":"Palantir Technologies", "sector":"Technology", "industry":"Data Analytics", "country":"US", "ipo":"2020-09-30", "ipo_px":9.5, "cur_px":124.0, "mktcap":282e9, "pe":280, "eps":0.41, "rev":3.5e9, "margin":0.135, "roe":0.10, "de":0.05, "div":0.0, "beta":2.2, "mu":0.35, "sigma":0.75},
    "SNOW":  {"name":"Snowflake Inc.", "sector":"Technology", "industry":"Cloud Computing", "country":"US", "ipo":"2020-09-16", "ipo_px":120.0, "cur_px":155.0, "mktcap":51e9, "pe":None, "eps":-0.80, "rev":3.9e9, "margin":-0.04, "roe":-0.04, "de":0.15, "div":0.0, "beta":1.8, "mu":0.08, "sigma":0.60},
    "ARM":   {"name":"Arm Holdings PLC", "sector":"Technology", "industry":"Semiconductors", "country":"GB", "ipo":"2023-09-14", "ipo_px":51.0, "cur_px":148.0, "mktcap":155e9, "pe":215, "eps":0.65, "rev":3.9e9, "margin":0.338, "roe":0.25, "de":0.05, "div":0.0, "beta":1.5, "mu":0.40, "sigma":0.55},
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _safe(v, default=None):
    if v is None:
        return default
    try:
        if math.isnan(float(v)) or math.isinf(float(v)):
            return default
    except (TypeError, ValueError):
        pass
    return v


def _rnd(v, d=2):
    v = _safe(v)
    if v is None:
        return None
    try:
        return round(float(v), d)
    except (TypeError, ValueError):
        return None


def _pct(v):
    return _rnd(v * 100, 2) if v is not None else None


def _fmt_large(n):
    n = _safe(n)
    if n is None:
        return "N/A"
    n = float(n)
    if abs(n) >= 1e12:
        return f"${n/1e12:.2f}T"
    if abs(n) >= 1e9:
        return f"${n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"${n/1e6:.2f}M"
    if abs(n) >= 1e3:
        return f"${n/1e3:.2f}K"
    return f"${n:.2f}"


# ─── Simulation Engine ────────────────────────────────────────────────────────

def _simulate_stock(symbol: str) -> dict:
    """
    Generate realistic simulated stock data using Geometric Brownian Motion.
    Used when real network access is unavailable.
    """
    meta = KNOWN_STOCKS.get(symbol.upper(), {})

    # Seed random from symbol for reproducibility
    seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    if _NUMPY_OK:
        np.random.seed(seed % (2**31))

    # Parameters
    name = meta.get("name", f"{symbol} Corp.")
    sector = meta.get("sector", "Technology")
    industry = meta.get("industry", "Software")
    country = meta.get("country", "US")
    ipo_str = meta.get("ipo", "2015-01-04")
    ipo_px = meta.get("ipo_px", rng.uniform(10.0, 80.0))
    target_cur_px = meta.get("cur_px", None)   # ← known current price for normalization
    mu = meta.get("mu", rng.uniform(0.05, 0.25))
    sigma = meta.get("sigma", rng.uniform(0.20, 0.55))
    mktcap = meta.get("mktcap", rng.uniform(1e9, 500e9))
    pe_ratio = meta.get("pe", rng.uniform(15, 50))
    eps = meta.get("eps", rng.uniform(0.5, 20))
    rev = meta.get("rev", rng.uniform(1e9, 100e9))
    margin = meta.get("margin", rng.uniform(0.05, 0.35))
    roe = meta.get("roe", rng.uniform(0.05, 0.40))
    de = meta.get("de", rng.uniform(0.1, 2.0))
    div = meta.get("div", 0.0)
    beta = meta.get("beta", rng.uniform(0.7, 2.0))

    # Date range: from IPO to today (cap very old IPOs at 20 years for sim speed)
    try:
        ipo_dt = datetime.strptime(ipo_str, "%Y-%m-%d")
    except Exception:
        ipo_dt = datetime(2010, 1, 4)

    today = datetime.now()
    max_history_start = today - timedelta(days=20 * 365)
    sim_start = max(ipo_dt, max_history_start)  # cap at 20 years for simulation
    if sim_start > today - timedelta(days=30):
        sim_start = today - timedelta(days=365)

    # Generate business days
    dates = []
    cur = sim_start
    while cur <= today:
        if cur.weekday() < 5:
            dates.append(cur)
        cur += timedelta(days=1)

    n = len(dates)
    dt = 1.0 / 252.0

    # GBM simulation
    if _NUMPY_OK:
        z = np.random.standard_normal(n)
        log_returns = (mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z
        prices = np.zeros(n)
        prices[0] = float(ipo_px)
        for i in range(1, n):
            prices[i] = prices[i-1] * math.exp(log_returns[i])

        # Add earnings surprises every ~63 trading days
        for i in range(62, n, 63):
            surprise = rng.gauss(mu * 0.1, sigma * 0.1)
            prices[i:] *= (1 + surprise)

        # Normalize: scale so that last price ≈ target current price
        if target_cur_px and prices[-1] > 0:
            scale = target_cur_px / prices[-1]
            prices = prices * scale

        close = pd.Series(prices, index=pd.DatetimeIndex(dates))
        daily_range = sigma * math.sqrt(dt) * close
        range_mults = pd.Series([rng.uniform(0.3, 1.0) for _ in range(n)], index=close.index)
        high = close + daily_range.abs() * range_mults
        low  = close - daily_range.abs() * range_mults
        low  = low.clip(lower=0.01)
        open_p = close.shift(1).fillna(close.iloc[0])
        vol_base = max(float(mktcap) / float(close.mean()) / 50, 1e4)
        volume = pd.Series([max(int(rng.gauss(vol_base, vol_base * 0.5)), 1000) for _ in range(n)], index=close.index)

        hist_df = pd.DataFrame({"open": open_p, "high": high, "low": low, "close": close, "volume": volume})
    else:
        prices = [float(ipo_px)]
        for _ in range(1, n):
            r = rng.gauss((mu - 0.5*sigma**2)*dt, sigma*math.sqrt(dt))
            prices.append(prices[-1] * math.exp(r))
        if target_cur_px and prices[-1] > 0:
            scale = target_cur_px / prices[-1]
            prices = [p * scale for p in prices]
        hist_df = None

    current_price = target_cur_px or float(prices[-1])

    # Compute ipo_px from the first simulated price (already scaled)
    actual_ipo_px = float(prices[0]) if _NUMPY_OK and hist_df is not None else float(ipo_px)

    return {
        "name": name, "sector": sector, "industry": industry, "country": country,
        "ipo_str": ipo_str, "ipo_px": round(actual_ipo_px, 4),
        "mktcap": mktcap, "pe": pe_ratio, "eps": eps, "rev": rev,
        "margin": margin, "roe": roe, "de": de, "div": div, "beta": beta,
        "mu": mu, "sigma": sigma,
        "hist_df": hist_df,
        "current_price": round(current_price, 2),
        "simulated": True,
    }


# ─── Technical Indicators ────────────────────────────────────────────────────

def calc_sma(series, period):
    return series.rolling(window=period, min_periods=1).mean()

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False, min_periods=1).mean()

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))

def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = calc_ema(series, fast)
    ema_slow = calc_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line

def calc_bollinger(series, period=20, std_dev=2):
    sma = calc_sma(series, period)
    std = series.rolling(window=period, min_periods=1).std()
    return sma + std_dev * std, sma, sma - std_dev * std

def calc_stochastic(high, low, close, k=14, d=3):
    ll = low.rolling(window=k, min_periods=1).min()
    hh = high.rolling(window=k, min_periods=1).max()
    stoch_k = 100 * (close - ll) / (hh - ll).replace(0, float("nan"))
    return stoch_k, stoch_k.rolling(window=d, min_periods=1).mean()

def calc_atr(high, low, close, period=14):
    prev_close = close.shift(1)
    tr = pd.concat([high-low, (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(com=period-1, adjust=False, min_periods=1).mean()

def calc_obv(close, volume):
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * volume).cumsum()

def calc_williams_r(high, low, close, period=14):
    hh = high.rolling(window=period, min_periods=1).max()
    ll = low.rolling(window=period, min_periods=1).min()
    return -100 * (hh - close) / (hh - ll).replace(0, float("nan"))

def calc_cci(high, low, close, period=20):
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(window=period, min_periods=1).mean()
    mad = tp.rolling(window=period, min_periods=1).apply(
        lambda x: float(np.mean(np.abs(x - np.mean(x)))) if _NUMPY_OK else sum(abs(v - sum(x)/len(x)) for v in x)/len(x),
        raw=True
    )
    return (tp - sma_tp) / (0.015 * mad.replace(0, float("nan")))

def calc_adx(high, low, close, period=14):
    up_move = high.diff()
    down_move = -low.diff()
    pos_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    neg_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = calc_atr(high, low, close, period)
    pos_di = 100 * pos_dm.ewm(com=period-1, adjust=False, min_periods=1).mean() / atr.replace(0, float("nan"))
    neg_di = 100 * neg_dm.ewm(com=period-1, adjust=False, min_periods=1).mean() / atr.replace(0, float("nan"))
    dx = 100 * (pos_di - neg_di).abs() / (pos_di + neg_di).replace(0, float("nan"))
    return dx.ewm(com=period-1, adjust=False, min_periods=1).mean(), pos_di, neg_di

def calc_vwap(high, low, close, volume):
    tp = (high + low + close) / 3
    return (tp * volume).cumsum() / volume.cumsum().replace(0, float("nan"))

def calc_fibonacci_levels(high, low):
    diff = high - low
    return {
        "0.0%": round(high, 2), "23.6%": round(high - diff*0.236, 2),
        "38.2%": round(high - diff*0.382, 2), "50.0%": round(high - diff*0.500, 2),
        "61.8%": round(high - diff*0.618, 2), "78.6%": round(high - diff*0.786, 2),
        "100%": round(low, 2),
    }

def calc_support_resistance(close, window=30, n=5):
    try:
        rolling_max = close.rolling(window=window, center=True, min_periods=1).max()
        rolling_min = close.rolling(window=window, center=True, min_periods=1).min()
        resistances = sorted([float(close.loc[i]) for i in close[close == rolling_max].nlargest(n).index], reverse=True)[:3]
        supports = sorted([float(close.loc[i]) for i in close[close == rolling_min].nsmallest(n).index])[:3]
        return {"resistance": [_rnd(r) for r in resistances], "support": [_rnd(s) for s in supports]}
    except Exception:
        return {"resistance": [], "support": []}

def calc_sharpe(returns, risk_free=0.045):
    if returns.empty or returns.std() == 0:
        return 0.0
    excess = returns - risk_free / 252
    return float((excess.mean() / excess.std()) * math.sqrt(252))

def calc_max_drawdown(close):
    roll_max = close.cummax()
    return float(((close - roll_max) / roll_max).min() * 100)

def calc_var(returns, confidence=0.95):
    if returns.empty:
        return 0.0
    if _NUMPY_OK:
        return float(np.percentile(returns.dropna(), (1 - confidence) * 100) * 100)
    sorted_r = sorted(returns.dropna().tolist())
    idx = int((1 - confidence) * len(sorted_r))
    return sorted_r[idx] * 100

def calc_beta_vs_market(stock_returns, market_returns):
    try:
        common = stock_returns.align(market_returns, join="inner")
        s, m = common[0].dropna(), common[1].dropna()
        if len(s) < 30:
            return 1.0
        if _NUMPY_OK:
            cov = np.cov(s, m)
            return float(cov[0][1] / cov[1][1]) if cov[1][1] != 0 else 1.0
        return 1.0
    except Exception:
        return 1.0


# ─── Signal Interpretation ────────────────────────────────────────────────────

def interpret_rsi(rsi):
    if rsi >= 80: return "קנייה יתר חזקה (Extremely Overbought)"
    if rsi >= 70: return "קנייה יתר (Overbought)"
    if rsi >= 55: return "מגמה עולה (Bullish)"
    if rsi >= 45: return "ניטרלי (Neutral)"
    if rsi >= 30: return "מגמה יורדת (Bearish)"
    return "מכירה יתר (Oversold)"

def interpret_macd(macd, signal, hist):
    if macd > signal and hist > 0: return "צלב זהב עולה (Bullish Crossover)"
    if macd < signal and hist < 0: return "צלב מוות יורד (Bearish Crossover)"
    return "מומנטום חיובי" if macd > 0 else "מומנטום שלילי"

def interpret_bb(price, upper, lower, middle):
    if price >= upper: return "מחיר מעל הרצועה העליונה – קנייה יתר"
    if price <= lower: return "מחיר מתחת לרצועה התחתונה – מכירה יתר"
    return "מחיר מעל אמצע – מגמה חיובית" if price > middle else "מחיר מתחת לאמצע – מגמה שלילית"


# ─── AI Report Generator ─────────────────────────────────────────────────────

def _ai_report_claude(symbol, analysis_data):
    """Professional investment report via Claude API."""
    client = _anthropic_mod.Anthropic(api_key=_ANTHROPIC_KEY)
    info = analysis_data.get("info", {})
    tech = analysis_data.get("technical", {})
    fund = analysis_data.get("fundamental", {})
    stats = analysis_data.get("statistical", {})
    hist = analysis_data.get("history_summary", {})
    simulated = analysis_data.get("simulated", False)

    prompt = f"""
אתה אנליסט מניות מקצועי ברמה עולמית (Goldman Sachs, Morgan Stanley, JP Morgan).
ניתחת את המניה {symbol} לעומק. בצע ניתוח השקעה מקיף ומקצועי בעברית.
{"⚠️ שים לב: הנתונים מבוססים על סימולציה (אין גישה לנתונים חיים כרגע). ציין זאת בתחילת הדוח." if simulated else ""}

== נתוני החברה ==
שם: {info.get("name")} | סקטור: {info.get("sector")} | תעשייה: {info.get("industry")} | מדינה: {info.get("country")}
שווי שוק: {fund.get("market_cap_fmt")} | עובדים: {info.get("employees", "N/A")} | IPO: {info.get("ipo_date")}

== נתוני מחיר ==
מחיר נוכחי: ${hist.get("current_price")} | 52W גבוה: ${hist.get("high_52w")} | 52W נמוך: ${hist.get("low_52w")}
ביצועים מאז IPO: {hist.get("since_ipo_pct")}% | שנה: {hist.get("ytd_pct")}% | 5 שנים: {hist.get("5y_pct")}%

== אינדיקטורים טכניים ==
RSI={tech.get("rsi")} ({tech.get("rsi_signal")}) | MACD={tech.get("macd_line")}/{tech.get("macd_signal_val")} ({tech.get("macd_signal")})
BB: {tech.get("bb_upper")}/{tech.get("bb_lower")} ({tech.get("bb_signal")}) | ADX={tech.get("adx")} | Stoch%K={tech.get("stoch_k")}
SMA20={tech.get("sma20")} SMA50={tech.get("sma50")} SMA200={tech.get("sma200")} | {'🟢 צלב זהב' if tech.get("golden_cross") else '🔴 צלב מוות'}
ATR={tech.get("atr")} | Williams%R={tech.get("williams_r")} | CCI={tech.get("cci")} | OBV: {tech.get("obv_trend")}
פיבונאצ'י: {json.dumps(tech.get("fibonacci", {}), ensure_ascii=False)}
תמיכה: {tech.get("support")} | התנגדות: {tech.get("resistance")}

== ניתוח יסודי ==
P/E={fund.get("pe_ratio")} | Forward P/E={fund.get("forward_pe")} | P/B={fund.get("pb_ratio")} | P/S={fund.get("ps_ratio")}
EPS={fund.get("eps_ttm")} | Revenue={fund.get("revenue_fmt")} | צמיחה={fund.get("revenue_growth")}%
רווח גולמי={fund.get("gross_margins")}% | רווח נקי={fund.get("profit_margins")}% | ROE={fund.get("roe")}% | ROA={fund.get("roa")}%
D/E={fund.get("debt_to_equity")} | Current Ratio={fund.get("current_ratio")} | FCF={fund.get("free_cashflow_fmt")}
דיבידנד={fund.get("dividend_yield")}%

== ניתוח סטטיסטי ==
תנודתיות={stats.get("annual_volatility")}% | בטא={stats.get("beta")} | Sharpe={stats.get("sharpe")}
MaxDD={stats.get("max_drawdown")}% | VaR(95%)={stats.get("var_95")}% | ימים חיוביים={stats.get("positive_days")}%

כתוב דוח מקצועי מלא בעברית עם הסעיפים:
## 1. תקציר מנהלים
## 2. פרופיל החברה
## 3. ניתוח טכני מפורט
## 4. ניתוח יסודי מפורט
## 5. ניתוח סיכונים
## 6. תרחישים (שורי/דובי/בסיס)
## 7. רמות מחיר מפתח
## 8. המלצת השקעה ⭐ (קנה/מכור/המתן) עם: מחיר כניסה, Stop Loss, יעד 12 חודשים, % מהתיק, טווח השקעה

היה ספציפי ומדויק. השתמש בנתונים שנמסרו.
"""
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def _rule_based_report(symbol, analysis_data):
    """Comprehensive rule-based investment report."""
    info = analysis_data.get("info", {})
    tech = analysis_data.get("technical", {})
    fund = analysis_data.get("fundamental", {})
    stats = analysis_data.get("statistical", {})
    hist = analysis_data.get("history_summary", {})
    simulated = analysis_data.get("simulated", False)

    score = 50
    signals = []

    rsi = _safe(tech.get("rsi"), 50)
    if rsi < 30: score += 15; signals.append("✅ RSI באזור מכירת יתר – הזדמנות קנייה")
    elif rsi < 45: score += 5; signals.append("✅ RSI נמוך – מגמה שלילית מתמתנת")
    elif rsi > 70: score -= 10; signals.append("⚠️ RSI באזור קנייה יתר – סיכון לתיקון")
    elif rsi > 55: score += 8; signals.append("✅ RSI גבוה – מומנטום חיובי")

    macd_hist = _safe(tech.get("macd_histogram"), 0)
    if macd_hist > 0: score += 8; signals.append("✅ MACD הגיסטוגרם חיובי – מומנטום עולה")
    elif macd_hist < 0: score -= 5; signals.append("⚠️ MACD הגיסטוגרם שלילי – לחץ מכירה")

    current = _safe(hist.get("current_price"), 0) or 1
    sma50 = _safe(tech.get("sma50"), current)
    sma200 = _safe(tech.get("sma200"), current)
    if current > sma50: score += 7; signals.append("✅ מחיר מעל SMA-50 – מגמה עולה בינונית")
    if current > sma200: score += 10; signals.append("✅ מחיר מעל SMA-200 – מגמה עולה ארוכת-טווח")
    elif current < sma200: score -= 8; signals.append("⚠️ מחיר מתחת ל-SMA-200 – מגמה שלילית")

    if tech.get("golden_cross"): score += 10; signals.append("✅ צלב זהב (SMA50>SMA200) – אות קנייה חזק")
    else: score -= 8; signals.append("⚠️ צלב מוות (SMA50<SMA200) – אות שלילי")

    pe = _safe(fund.get("pe_ratio"))
    if pe and 0 < pe < 20: score += 8; signals.append(f"✅ P/E={pe} – מניה זולה ביחס לרווחים")
    elif pe and pe > 60: score -= 5; signals.append(f"⚠️ P/E={pe} – מניה יקרה מאוד")

    rev_growth = _safe(fund.get("revenue_growth"))
    if rev_growth and rev_growth > 20: score += 10; signals.append(f"✅ צמיחת הכנסות {rev_growth}% – צמיחה מהירה")
    elif rev_growth and rev_growth > 10: score += 5; signals.append(f"✅ צמיחת הכנסות {rev_growth}% – צמיחה סבירה")
    elif rev_growth and rev_growth < 0: score -= 10; signals.append(f"⚠️ ירידה בהכנסות {rev_growth}%")

    profit_margin = _safe(fund.get("profit_margins"))
    if profit_margin and profit_margin > 20: score += 8; signals.append(f"✅ שולי רווח {profit_margin}% – עסק רווחי מאוד")
    elif profit_margin and profit_margin < 0: score -= 10; signals.append(f"⚠️ חברה מפסידה ({profit_margin}%)")

    sharpe = _safe(stats.get("sharpe"), 0)
    if sharpe > 1.5: score += 8; signals.append(f"✅ Sharpe={sharpe} – תשואה מעולה ביחס לסיכון")
    elif sharpe < 0: score -= 5; signals.append(f"⚠️ Sharpe={sharpe} – תשואה גרועה ביחס לסיכון")

    since_ipo = _safe(hist.get("since_ipo_pct"), 0)
    if since_ipo > 200: score += 10; signals.append(f"✅ ביצועים {since_ipo}% מאז IPO – מניה מצטיינת")
    elif since_ipo < 0: score -= 10; signals.append(f"⚠️ ביצועים {since_ipo}% מאז IPO – מתחת להנפקה")

    score = max(10, min(95, score))

    if score >= 70: rec = "🟢 קנייה"; action = "קנה"; rec_cls = "buy"
    elif score >= 55: rec = "🟡 קנייה מותנית"; action = "המתן לכניסה טובה"; rec_cls = "hold"
    elif score >= 40: rec = "⚪ ניטרלי"; action = "המתן"; rec_cls = "hold"
    else: rec = "🔴 מכירה / הימנעות"; action = "מכור / הימנע"; rec_cls = "sell"

    beta = _safe(stats.get("beta"), 1.0)
    sl_pct = 0.88 if beta and beta > 1.5 else 0.92
    stop_loss = _rnd(current * sl_pct)
    target_12m = _rnd(current * (1.25 if score >= 70 else 1.12 if score >= 55 else 0.90))
    entry = _rnd(current * 0.97) if score >= 55 else None

    sim_notice = "\n⚠️ הערה: דוח זה מבוסס על נתונים מסומלצים. בסביבת פרודקשן יופיעו נתונים חיים.\n" if simulated else ""

    signals_text = "\n".join(f"   {s}" for s in signals) if signals else "   אין אותות ברורים"

    return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊  דוח ניתוח מקצועי | {symbol} — {info.get("name", symbol)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 תאריך: {datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")} UTC{sim_notice}

## 1️⃣  תקציר מנהלים

ציון כולל: {score}/100
המלצה: {rec}
פעולה: {action}

ניתחנו את {symbol} ({info.get("name")}) לעומק מלא מאז ה-IPO ({info.get("ipo_date")}).
הניתוח כולל 30+ אינדיקטורים טכניים, ניתוח יסודי מלא, וסטטיסטיקות מקיפות.

## 2️⃣  פרופיל החברה

• שם: {info.get("name")}
• סקטור: {info.get("sector")} | תעשייה: {info.get("industry")}
• מדינה: {info.get("country")} | שווי שוק: {fund.get("market_cap_fmt")}
• IPO: {info.get("ipo_date")} | מחיר IPO: ${hist.get("ipo_price")}

## 3️⃣  ביצועים היסטוריים

• מחיר נוכחי: ${hist.get("current_price")}
• 52W גבוה/נמוך: ${hist.get("high_52w")} / ${hist.get("low_52w")}
• מאז IPO: {hist.get("since_ipo_pct")}% | שנה: {hist.get("ytd_pct")}% | 5Y: {hist.get("5y_pct")}%
• ימי מסחר: {hist.get("total_trading_days", "─"):,}

## 4️⃣  ניתוח טכני

### מומנטום
• RSI (14): {tech.get("rsi")} → {tech.get("rsi_signal")}
• Stochastic %K/{tech.get("stoch_d")}: {tech.get("stoch_k")} | Williams %R: {tech.get("williams_r")}
• CCI (20): {tech.get("cci")}

### MACD
• Line: {tech.get("macd_line")} | Signal: {tech.get("macd_signal_val")} | Hist: {tech.get("macd_histogram")}
• → {tech.get("macd_signal")}

### Bollinger Bands (20,2)
• עליון: ${tech.get("bb_upper")} | אמצע: ${tech.get("bb_middle")} | תחתון: ${tech.get("bb_lower")}
• → {tech.get("bb_signal")}

### ממוצעים נעים
• SMA: 20={tech.get("sma20")} | 50={tech.get("sma50")} | 100={tech.get("sma100")} | 200={tech.get("sma200")}
• EMA: 12={tech.get("ema12")} | 20={tech.get("ema20")} | 26={tech.get("ema26")} | 50={tech.get("ema50")}
• {'🟢 צלב זהב (SMA50>SMA200)' if tech.get("golden_cross") else '🔴 צלב מוות (SMA50<SMA200)'}

### עוצמת מגמה
• ADX: {tech.get("adx")} ({'חזק' if (_safe(tech.get("adx"),0)>25) else 'חלש'}) | +DI={tech.get("plus_di")} | -DI={tech.get("minus_di")}
• ATR (14): ${tech.get("atr")} | VWAP: ${tech.get("vwap")}
• OBV: {tech.get("obv_trend")}

### פיבונאצ'י (52W)
{chr(10).join(f"  • {k}: ${v}" for k,v in (tech.get("fibonacci") or {}).items())}

### רמות מפתח
• התנגדויות: {", ".join(f"${r}" for r in (tech.get("resistance") or []))}
• תמיכות: {", ".join(f"${s}" for s in (tech.get("support") or []))}
• Pivot: ${tech.get("pivot")} | R1=${tech.get("r1")} | S1=${tech.get("s1")}

## 5️⃣  ניתוח יסודי

| מדד | ערך |
|-----|-----|
| P/E (TTM) | {fund.get("pe_ratio", "N/A")} |
| Forward P/E | {fund.get("forward_pe", "N/A")} |
| P/B | {fund.get("pb_ratio", "N/A")} |
| P/S | {fund.get("ps_ratio", "N/A")} |
| EPS (TTM) | ${fund.get("eps_ttm", "N/A")} |
| Revenue | {fund.get("revenue_fmt", "N/A")} |
| צמיחת Revenue | {fund.get("revenue_growth", "N/A")}% |
| שולי רווח גולמי | {fund.get("gross_margins", "N/A")}% |
| שולי רווח נקי | {fund.get("profit_margins", "N/A")}% |
| ROE | {fund.get("roe", "N/A")}% |
| ROA | {fund.get("roa", "N/A")}% |
| Debt/Equity | {fund.get("debt_to_equity", "N/A")} |
| FCF | {fund.get("free_cashflow_fmt", "N/A")} |
| מזומנים | {fund.get("total_cash_fmt", "N/A")} |
| Dividend Yield | {fund.get("dividend_yield", 0) or 0}% |

## 6️⃣  ניתוח סיכונים

| מדד | ערך | פרשנות |
|-----|-----|---------|
| תנודתיות שנתית | {stats.get("annual_volatility")}% | {'גבוהה' if (_safe(stats.get("annual_volatility"),0)>35) else 'בינונית' if (_safe(stats.get("annual_volatility"),0)>20) else 'נמוכה'} |
| בטא | {stats.get("beta")} | {'סיכון גבוה מהשוק' if (_safe(stats.get("beta"),1)>1.2) else 'דומה לשוק' if (_safe(stats.get("beta"),1)>0.8) else 'סיכון נמוך מהשוק'} |
| Sharpe Ratio | {stats.get("sharpe")} | {'מעולה' if (_safe(stats.get("sharpe"),0)>1.5) else 'טוב' if (_safe(stats.get("sharpe"),0)>1) else 'ממוצע' if (_safe(stats.get("sharpe"),0)>0.5) else 'חלש'} |
| Max Drawdown | {stats.get("max_drawdown")}% | ירידה מרבית היסטורית |
| VaR (95%) | {stats.get("var_95")}% | הפסד מרבי יומי |
| ימים חיוביים | {stats.get("positive_days")}% | מהימי מסחר |

## 7️⃣  אותות מסחר

{signals_text}

## 8️⃣  תרחישים

🟢 **שורי** (הסתברות {35 if score>=60 else 25}%):
   יעד: ${_rnd(current*1.40)} | זמן: 18-24 חודשים
   תנאים: המשך צמיחה, שיפור רווחיות

⚪ **בסיס** (הסתברות {45 if 40<=score<=70 else 35}%):
   יעד: ${target_12m} | זמן: 12 חודשים
   תנאים: צמיחה יציבה, תנאי שוק רגילים

🔴 **דובי** (הסתברות {20 if score>=60 else 40}%):
   יעד: ${_rnd(current*0.75)} | תנאים: האטה כלכלית, תחרות

## 9️⃣  המלצת השקעה סופית

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 ציון: {score}/100 | {rec}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| פרמטר | ערך |
|-------|-----|
| פעולה | {action} |
| מחיר נוכחי | ${current} |
| כניסה מומלצת | ${entry or "שוק נוכחי"} |
| Stop Loss | ${stop_loss} ({100-int(sl_pct*100)}% מתחת) |
| יעד 12 חודשים | ${target_12m} |
| פוטנציאל | {_rnd(((target_12m-current)/current*100) if current else 0)}% |
| % מהתיק | {'3-5%' if score>=70 else '1-2%' if score>=55 else '0%'} |
| טווח | {'ארוך (3+ שנים)' if score>=70 else 'בינוני (1-2 שנים)' if score>=55 else 'לא מומלץ'} |

### ⚠️ גורמי סיכון
• תנודתיות {stats.get("annual_volatility")}% שנתי | Beta={stats.get("beta")}
• Max Drawdown היסטורי: {stats.get("max_drawdown")}%
• סיכונים מאקרו: ריבית, אינפלציה, מחזור עסקי
• סיכונים סקטוריאליים: {info.get("sector")}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ כתב ויתור: לצרכי מידע בלבד. אינו ייעוץ השקעות.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


# ─── Main Analyzer Class ─────────────────────────────────────────────────────

class StockAnalyzer:
    def __init__(self, symbol: str, progress_callback: Callable[[dict], None] | None = None):
        self.symbol = symbol.upper().strip()
        self.cb = progress_callback

    def _emit(self, step, status, message, data=None, pct=0, step_num=0, total_steps=9):
        if self.cb:
            self.cb({
                "type": "progress", "step": step, "status": status,
                "message": message, "data": data,
                "percentage": pct, "step_num": step_num,
                "total_steps": total_steps, "ts": time.time(),
            })

    def _emit_done(self, report, analysis_data):
        if self.cb:
            self.cb({
                "type": "done", "report": report,
                "analysis": analysis_data, "symbol": self.symbol, "ts": time.time(),
            })

    def _emit_error(self, message):
        if self.cb:
            self.cb({"type": "error", "message": message, "symbol": self.symbol, "ts": time.time()})

    def analyze(self):
        if not _NUMPY_OK:
            self._emit_error("numpy/pandas not installed — run: pip install numpy pandas yfinance")
            return {}
        try:
            return self._run_pipeline()
        except Exception as exc:
            self._emit_error(f"ניתוח נכשל: {exc}\n{traceback.format_exc()}")
            return {}

    def _try_fetch_real(self):
        """Attempt to fetch real data via yfinance. Returns (hist_df, info) or (None, None)."""
        if not _YF_OK:
            return None, None
        try:
            ticker = yf.Ticker(self.symbol)
            info = ticker.info or {}
            # Quick check that info actually has useful data
            if not any(info.get(k) for k in ["regularMarketPrice", "currentPrice", "previousClose", "longName", "shortName"]):
                return None, {}
            hist_df = ticker.history(period="max", interval="1d", auto_adjust=True)
            if hist_df is None or hist_df.empty:
                return None, info
            hist_df.columns = [c.lower() for c in hist_df.columns]
            hist_df.index = pd.to_datetime(hist_df.index)
            return hist_df.sort_index(), info
        except Exception:
            return None, None

    def _run_pipeline(self):
        symbol = self.symbol
        total = 9

        # ── STEP 1: Connect ──────────────────────────────────────────────────
        self._emit("connect", "running", f"🔌 מתחבר למקורות מידע עבור {symbol}…", pct=5, step_num=1, total_steps=total)

        simulated = False
        hist_df = None
        yf_info = {}

        # Try real data
        try:
            hist_df, yf_info = self._try_fetch_real()
        except Exception:
            hist_df, yf_info = None, {}

        if hist_df is None or hist_df.empty:
            # Fallback to simulation
            simulated = True
            sim = _simulate_stock(symbol)
            hist_df = sim["hist_df"]
            if hist_df is None or hist_df.empty:
                self._emit_error(f"לא ניתן לנתח את {symbol}. נסה טיקר תקין: AAPL, TSLA, NVDA, MSFT")
                return {}

            meta = KNOWN_STOCKS.get(symbol, sim)
            yf_info = {
                "longName": meta.get("name", symbol),
                "sector": meta.get("sector", "Technology"),
                "industry": meta.get("industry", "Software"),
                "country": meta.get("country", "US"),
                "fullTimeEmployees": None,
                "regularMarketPrice": sim["current_price"],
                "marketCap": meta.get("mktcap"),
                "trailingPE": meta.get("pe"),
                "trailingEps": meta.get("eps"),
                "totalRevenue": meta.get("rev"),
                "profitMargins": meta.get("margin"),
                "returnOnEquity": meta.get("roe"),
                "debtToEquity": meta.get("de") * 100 if meta.get("de") else None,
                "dividendYield": meta.get("div"),
                "beta": meta.get("beta"),
                "grossMargins": meta.get("margin", 0) * 1.4 if meta.get("margin") else None,
                "revenueGrowth": sim["mu"] * 0.4,
                "freeCashflow": (meta.get("rev", 0) * meta.get("margin", 0) * 0.7) or None,
                "totalCash": (meta.get("mktcap", 0) * 0.05) or None,
                "totalDebt": (meta.get("mktcap", 0) * 0.1) if meta.get("de", 0) > 0.3 else None,
                "currentRatio": round(random.uniform(1.2, 3.5), 2),
                "forwardPE": meta.get("pe") * 0.85 if meta.get("pe") else None,
                "priceToBook": round(meta.get("mktcap", 1e10) / max((meta.get("rev", 1e9) * 0.3), 1), 1),
                "priceToSalesTrailing12Months": round(meta.get("mktcap", 1e10) / max(meta.get("rev", 1e9), 1), 1),
                "ebitdaMargins": meta.get("margin", 0) * 1.3 if meta.get("margin") else None,
                "returnOnAssets": meta.get("roe", 0) * 0.4 if meta.get("roe") else None,
                "forwardEps": meta.get("eps", 0) * 1.1 if meta.get("eps") else None,
                "ebitda": (meta.get("rev", 0) * meta.get("margin", 0) * 1.3) or None,
                "payoutRatio": meta.get("div", 0) * 5 if meta.get("div") else None,
                "heldPercentInstitutions": round(random.uniform(0.55, 0.90), 2),
                "heldPercentInsiders": round(random.uniform(0.02, 0.15), 2),
                "enterpriseToEbitda": round(random.uniform(10, 40), 1),
                "shortRatio": round(random.uniform(1, 5), 1),
                "numberOfAnalystOpinions": random.randint(15, 45),
                "targetMeanPrice": sim["current_price"] * 1.15,
                "targetHighPrice": sim["current_price"] * 1.35,
                "targetLowPrice": sim["current_price"] * 0.85,
                "recommendationKey": "buy" if sim["mu"] > 0.15 else "hold" if sim["mu"] > 0.05 else "underperform",
            }
            data_source = "סימולציה ריאליסטית (GBM)"
        else:
            data_source = "Yahoo Finance (Live)"

        conn_msg = f"✅ {'סימולציה ריאליסטית' if simulated else 'חיבור בורסה הצליח'} | {data_source} | {yf_info.get('longName', symbol)}"
        self._emit("connect", "done", conn_msg, pct=10, step_num=1, total_steps=total)

        # ── STEP 2: Company info ─────────────────────────────────────────────
        self._emit("info", "running", "🏢 מושך פרופיל חברה…", pct=12, step_num=2, total_steps=total)

        company_info = {
            "name": yf_info.get("longName") or yf_info.get("shortName") or symbol,
            "sector": yf_info.get("sector", "N/A"),
            "industry": yf_info.get("industry", "N/A"),
            "country": yf_info.get("country", "US"),
            "website": yf_info.get("website", "N/A"),
            "employees": yf_info.get("fullTimeEmployees"),
            "description": (yf_info.get("longBusinessSummary") or "")[:300],
            "ipo_date": "N/A",
            "exchange": yf_info.get("exchange", "NASDAQ"),
            "currency": yf_info.get("currency", "USD"),
        }

        self._emit("info", "done",
                   f"✅ {company_info['name']} | {company_info['sector']} | {company_info['country']}",
                   data=company_info, pct=18, step_num=2, total_steps=total)

        # ── STEP 3: Historical data ──────────────────────────────────────────
        self._emit("history", "running",
                   f"📈 מנתח היסטוריה מלאה מאז IPO ({symbol})…",
                   pct=20, step_num=3, total_steps=total)

        hist_df = hist_df.sort_index()
        ipo_dt = hist_df.index[0]
        ipo_date_str = ipo_dt.strftime("%d/%m/%Y")
        company_info["ipo_date"] = ipo_date_str
        ipo_px = _rnd(float(hist_df["close"].iloc[0]))

        current_price = _safe(
            yf_info.get("regularMarketPrice") or yf_info.get("currentPrice") or
            yf_info.get("previousClose") or float(hist_df["close"].iloc[-1])
        )
        high_52w = float(hist_df["close"].tail(252).max())
        low_52w = float(hist_df["close"].tail(252).min())

        since_ipo_pct = _rnd(((current_price - ipo_px) / ipo_px * 100) if ipo_px else None)

        def perf_from_n_years(n):
            cutoff = hist_df.index[-1] - pd.DateOffset(years=n)
            sub = hist_df[hist_df.index >= cutoff]
            if len(sub) < 2: return None
            return _rnd((current_price - float(sub["close"].iloc[0])) / float(sub["close"].iloc[0]) * 100)

        ytd_pct = perf_from_n_years(1)
        pct_3y = perf_from_n_years(3)
        pct_5y = perf_from_n_years(5)
        pct_10y = perf_from_n_years(10)

        history_summary = {
            "current_price": _rnd(current_price),
            "ipo_price": ipo_px,
            "ipo_date": ipo_date_str,
            "high_52w": _rnd(high_52w),
            "low_52w": _rnd(low_52w),
            "since_ipo_pct": since_ipo_pct,
            "ytd_pct": ytd_pct,
            "3y_pct": pct_3y,
            "5y_pct": pct_5y,
            "10y_pct": pct_10y,
            "total_trading_days": len(hist_df),
            "years_traded": round((hist_df.index[-1] - hist_df.index[0]).days / 365.25, 1),
        }

        # Chart data (last 252 days)
        chart_df = hist_df.tail(252)
        chart_data = {
            "dates": [d.strftime("%Y-%m-%d") for d in chart_df.index],
            "close": [_rnd(v) for v in chart_df["close"].tolist()],
            "volume": [int(v) for v in chart_df.get("volume", pd.Series()).tolist()] if "volume" in chart_df else [],
            "open":  [_rnd(v) for v in chart_df.get("open",  pd.Series()).tolist()] if "open"  in chart_df else [],
            "high":  [_rnd(v) for v in chart_df.get("high",  pd.Series()).tolist()] if "high"  in chart_df else [],
            "low":   [_rnd(v) for v in chart_df.get("low",   pd.Series()).tolist()] if "low"   in chart_df else [],
        }

        self._emit("history", "done",
                   f"✅ {len(hist_df):,} ימי מסחר | מאז {ipo_date_str} | IPO: ${ipo_px} | מאז IPO: {since_ipo_pct}%",
                   data={**history_summary, "chart": chart_data},
                   pct=35, step_num=3, total_steps=total)

        # ── STEP 4: Technical indicators ─────────────────────────────────────
        self._emit("technical", "running",
                   "📊 מחשב 30+ אינדיקטורים (RSI, MACD, Bollinger, Stochastic, ATR, ADX, CCI, OBV, Fibonacci…)",
                   pct=37, step_num=4, total_steps=total)

        close = hist_df["close"].astype(float)
        high_s = hist_df.get("high", close).astype(float)
        low_s  = hist_df.get("low",  close).astype(float)
        vol_s  = hist_df.get("volume", pd.Series(dtype=float)).astype(float)

        rsi_val = _rnd(float(calc_rsi(close).iloc[-1]))
        macd_line, macd_sig, macd_hist_s = calc_macd(close)
        macd_v  = _rnd(float(macd_line.iloc[-1]), 4)
        macd_sv = _rnd(float(macd_sig.iloc[-1]), 4)
        macd_hv = _rnd(float(macd_hist_s.iloc[-1]), 4)

        bb_up, bb_mid, bb_dn = calc_bollinger(close)
        bb_upper  = _rnd(float(bb_up.iloc[-1]))
        bb_middle = _rnd(float(bb_mid.iloc[-1]))
        bb_lower  = _rnd(float(bb_dn.iloc[-1]))

        sma20  = _rnd(float(calc_sma(close, 20).iloc[-1]))
        sma50  = _rnd(float(calc_sma(close, 50).iloc[-1]))
        sma100 = _rnd(float(calc_sma(close, 100).iloc[-1]))
        sma200 = _rnd(float(calc_sma(close, 200).iloc[-1]))
        ema12  = _rnd(float(calc_ema(close, 12).iloc[-1]))
        ema20  = _rnd(float(calc_ema(close, 20).iloc[-1]))
        ema26  = _rnd(float(calc_ema(close, 26).iloc[-1]))
        ema50  = _rnd(float(calc_ema(close, 50).iloc[-1]))
        ema200 = _rnd(float(calc_ema(close, 200).iloc[-1]))

        stoch_k, stoch_d = calc_stochastic(high_s, low_s, close)
        stoch_kv = _rnd(float(stoch_k.iloc[-1]))
        stoch_dv = _rnd(float(stoch_d.iloc[-1]))

        atr_v = _rnd(float(calc_atr(high_s, low_s, close).iloc[-1]))
        wr_v  = _rnd(float(calc_williams_r(high_s, low_s, close).iloc[-1]))
        cci_v = _rnd(float(calc_cci(high_s, low_s, close).iloc[-1]))

        adx_s, plus_di_s, minus_di_s = calc_adx(high_s, low_s, close)
        adx_v      = _rnd(float(adx_s.iloc[-1]))
        plus_di_v  = _rnd(float(plus_di_s.iloc[-1]))
        minus_di_v = _rnd(float(minus_di_s.iloc[-1]))

        obv_s = calc_obv(close, vol_s) if not vol_s.empty else pd.Series(dtype=float)
        obv_trend = "עולה 📈" if (len(obv_s) > 20 and float(obv_s.iloc[-1]) > float(obv_s.iloc[-20])) else "יורד 📉"

        vwap_s = calc_vwap(high_s, low_s, close, vol_s) if not vol_s.empty else pd.Series(dtype=float)
        vwap_v = _rnd(float(vwap_s.iloc[-1])) if not vwap_s.empty else None

        h52 = float(hist_df["close"].tail(252).max())
        l52 = float(hist_df["close"].tail(252).min())
        fib_levels = calc_fibonacci_levels(h52, l52)
        sr = calc_support_resistance(close)

        last_high  = float(high_s.iloc[-1])
        last_low   = float(low_s.iloc[-1])
        last_close = float(close.iloc[-1])
        pivot = _rnd((last_high + last_low + last_close) / 3)
        r1 = _rnd(2*pivot - last_low)
        s1 = _rnd(2*pivot - last_high)
        r2 = _rnd(pivot + (last_high - last_low))
        s2 = _rnd(pivot - (last_high - last_low))

        technical = {
            "rsi": rsi_val, "rsi_signal": interpret_rsi(rsi_val or 50),
            "macd_line": macd_v, "macd_signal_val": macd_sv, "macd_histogram": macd_hv,
            "macd_signal": interpret_macd(macd_v or 0, macd_sv or 0, macd_hv or 0),
            "bb_upper": bb_upper, "bb_middle": bb_middle, "bb_lower": bb_lower,
            "bb_signal": interpret_bb(float(current_price or 0), bb_upper or 0, bb_lower or 0, bb_middle or 0),
            "sma20": sma20, "sma50": sma50, "sma100": sma100, "sma200": sma200,
            "ema12": ema12, "ema20": ema20, "ema26": ema26, "ema50": ema50, "ema200": ema200,
            "stoch_k": stoch_kv, "stoch_d": stoch_dv,
            "atr": atr_v, "williams_r": wr_v, "cci": cci_v,
            "adx": adx_v, "plus_di": plus_di_v, "minus_di": minus_di_v,
            "obv_trend": obv_trend, "vwap": vwap_v,
            "fibonacci": fib_levels,
            "resistance": sr["resistance"], "support": sr["support"],
            "pivot": pivot, "r1": r1, "r2": r2, "s1": s1, "s2": s2,
            "golden_cross": (sma50 or 0) > (sma200 or 0),
        }

        self._emit("technical", "done",
                   f"✅ RSI={rsi_val} | MACD={macd_v} | BB={bb_upper}/{bb_lower} | ADX={adx_v} | SMA200=${sma200}",
                   data=technical, pct=52, step_num=4, total_steps=total)

        # ── STEP 5: Fundamentals ─────────────────────────────────────────────
        self._emit("fundamentals", "running", "💰 מחשב ניתוח יסודי (P/E, EPS, Revenue, FCF, ROE…)", pct=54, step_num=5, total_steps=total)

        mktcap = yf_info.get("marketCap")
        fundamental = {
            "market_cap": _safe(mktcap),
            "market_cap_fmt": _fmt_large(mktcap),
            "pe_ratio": _rnd(yf_info.get("trailingPE")),
            "forward_pe": _rnd(yf_info.get("forwardPE")),
            "pb_ratio": _rnd(yf_info.get("priceToBook")),
            "ps_ratio": _rnd(yf_info.get("priceToSalesTrailing12Months")),
            "ev_ebitda": _rnd(yf_info.get("enterpriseToEbitda")),
            "eps_ttm": _rnd(yf_info.get("trailingEps")),
            "eps_forward": _rnd(yf_info.get("forwardEps")),
            "revenue_fmt": _fmt_large(yf_info.get("totalRevenue")),
            "revenue_growth": _pct(yf_info.get("revenueGrowth")),
            "earnings_growth": _pct(yf_info.get("earningsGrowth")),
            "gross_margins": _pct(yf_info.get("grossMargins")),
            "ebitda_margins": _pct(yf_info.get("ebitdaMargins")),
            "profit_margins": _pct(yf_info.get("profitMargins")),
            "roe": _pct(yf_info.get("returnOnEquity")),
            "roa": _pct(yf_info.get("returnOnAssets")),
            "debt_to_equity": _rnd(yf_info.get("debtToEquity")),
            "current_ratio": _rnd(yf_info.get("currentRatio")),
            "quick_ratio": _rnd(yf_info.get("quickRatio")),
            "ebitda_fmt": _fmt_large(yf_info.get("ebitda")),
            "free_cashflow_fmt": _fmt_large(yf_info.get("freeCashflow")),
            "total_cash_fmt": _fmt_large(yf_info.get("totalCash")),
            "total_debt_fmt": _fmt_large(yf_info.get("totalDebt")),
            "dividend_yield": _pct(yf_info.get("dividendYield")),
            "payout_ratio": _pct(yf_info.get("payoutRatio")),
            "institutional_holders_pct": _pct(yf_info.get("heldPercentInstitutions")),
            "insider_holders_pct": _pct(yf_info.get("heldPercentInsiders")),
            "short_ratio": _rnd(yf_info.get("shortRatio")),
            "analyst_count": yf_info.get("numberOfAnalystOpinions"),
            "target_mean_price": _rnd(yf_info.get("targetMeanPrice")),
            "target_high": _rnd(yf_info.get("targetHighPrice")),
            "target_low": _rnd(yf_info.get("targetLowPrice")),
            "recommendation": yf_info.get("recommendationKey", "N/A"),
        }

        self._emit("fundamentals", "done",
                   f"✅ P/E={fundamental['pe_ratio']} | EPS=${fundamental['eps_ttm']} | Rev={fundamental['revenue_fmt']} | ROE={fundamental['roe']}%",
                   data=fundamental, pct=65, step_num=5, total_steps=total)

        # ── STEP 6: Statistical ──────────────────────────────────────────────
        self._emit("statistical", "running", "📉 מחשב ניתוח סטטיסטי (Beta, Sharpe, VaR, MaxDD, תנודתיות…)", pct=67, step_num=6, total_steps=total)

        daily_returns = close.pct_change().dropna()
        annual_vol = _rnd(float(daily_returns.std()) * math.sqrt(252) * 100) if len(daily_returns) > 20 else None

        beta_val = _safe(yf_info.get("beta"))

        sharpe_v = _rnd(calc_sharpe(daily_returns))
        max_dd   = _rnd(calc_max_drawdown(close))
        var_95   = _rnd(calc_var(daily_returns))

        avg_vol = hist_df.get("volume", pd.Series(dtype=float))
        avg_vol_30 = float(avg_vol.tail(30).mean()) if not avg_vol.empty else 0
        avg_vol_10 = float(avg_vol.tail(10).mean()) if not avg_vol.empty else 0

        positive_days = _rnd(float((daily_returns > 0).sum() / len(daily_returns) * 100)) if len(daily_returns) > 0 else None

        monthly = close.resample("ME").last().pct_change().dropna() * 100
        statistical = {
            "annual_volatility": annual_vol,
            "beta": _rnd(beta_val),
            "sharpe": sharpe_v,
            "max_drawdown": max_dd,
            "var_95": var_95,
            "positive_days": positive_days,
            "avg_volume": _rnd(avg_vol_30),
            "avg_volume_fmt": _fmt_large(avg_vol_30).replace("$", ""),
            "avg_vol_10d_fmt": _fmt_large(avg_vol_10).replace("$", ""),
            "best_month_pct":  _rnd(float(monthly.max()))  if not monthly.empty else None,
            "worst_month_pct": _rnd(float(monthly.min()))  if not monthly.empty else None,
            "avg_monthly_return": _rnd(float(monthly.mean())) if not monthly.empty else None,
            "calmar_ratio": _rnd(abs(annual_vol / max_dd)) if annual_vol and max_dd and max_dd != 0 else None,
        }

        self._emit("statistical", "done",
                   f"✅ תנודתיות={annual_vol}% | בטא={beta_val} | Sharpe={sharpe_v} | MaxDD={max_dd}% | VaR(95%)={var_95}%",
                   data=statistical, pct=78, step_num=6, total_steps=total)

        # ── STEP 7: News ─────────────────────────────────────────────────────
        self._emit("news", "running", "📰 מחפש חדשות ועדכונים אחרונים…", pct=80, step_num=7, total_steps=total)

        news_items = []
        if not simulated:
            try:
                raw_news = yf.Ticker(symbol).news or []
                for item in raw_news[:5]:
                    news_items.append({
                        "title": item.get("title", ""),
                        "publisher": item.get("publisher", ""),
                        "link": item.get("link", ""),
                        "published": datetime.fromtimestamp(
                            item.get("providerPublishTime", 0), tz=timezone.utc
                        ).strftime("%d/%m/%Y %H:%M") if item.get("providerPublishTime") else "",
                    })
            except Exception:
                pass
        else:
            # Simulated news headlines
            now = datetime.now()
            news_items = [
                {"title": f"{company_info['name']} מדווחת על תוצאות Q2 שעלו על הציפיות", "publisher": "Reuters", "link": "#", "published": (now-timedelta(days=2)).strftime("%d/%m/%Y")},
                {"title": f"אנליסטים מעלים יעד מחיר ל-{symbol} לאחר תוצאות חזקות", "publisher": "Bloomberg", "link": "#", "published": (now-timedelta(days=5)).strftime("%d/%m/%Y")},
                {"title": f"גל קנייה מוסדי ב-{symbol} — קרנות גידור מגדילות פוזיציות", "publisher": "WSJ", "link": "#", "published": (now-timedelta(days=8)).strftime("%d/%m/%Y")},
            ]

        self._emit("news", "done", f"✅ {len(news_items)} עדכונים",
                   data={"news": news_items}, pct=83, step_num=7, total_steps=total)

        # ── STEP 8: AI Report ────────────────────────────────────────────────
        analysis_data = {
            "info": company_info,
            "history_summary": history_summary,
            "technical": technical,
            "fundamental": fundamental,
            "statistical": statistical,
            "news": news_items,
            "chart": chart_data,
            "simulated": simulated,
        }

        self._emit("ai_report", "running", "🤖 מייצר דוח השקעה מקצועי…", pct=85, step_num=8, total_steps=total)

        try:
            if _AI_AVAILABLE:
                report = _ai_report_claude(symbol, analysis_data)
            else:
                report = _rule_based_report(symbol, analysis_data)
        except Exception:
            report = _rule_based_report(symbol, analysis_data)

        self._emit("ai_report", "done", "✅ דוח מקצועי מוכן", pct=95, step_num=8, total_steps=total)

        # ── STEP 9: Finalize ─────────────────────────────────────────────────
        self._emit("finalize", "done",
                   f"🎉 ניתוח {symbol} הושלם! {'(נתונים סימולציה)' if simulated else '(נתונים חיים)'}",
                   pct=100, step_num=9, total_steps=total)

        self._emit_done(report, analysis_data)
        return {"report": report, "analysis": analysis_data}


# ─── CLI test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    def printer(event):
        t = event.get("type")
        if t == "progress":
            pct = event.get("percentage", 0)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"[{bar}] {pct:3d}% | {event['message'][:80]}")
        elif t == "done":
            print("\n" + "="*60)
            print(event["report"][:3000])
        elif t == "error":
            print(f"ERROR: {event['message']}")

    StockAnalyzer(sym, progress_callback=printer).analyze()
