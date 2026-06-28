"""
reporting.py — Performance analytics and report generation for EMPIREX-OS
==========================================================================

All metrics are computed from the trades DataFrame produced by BacktestEngine.

Outputs
-------
- Monthly P/L table (rows = year-month, cols = metric)
- Monthly trade count table
- Win rate, profit factor, max drawdown
- Best / worst month
- Long vs short breakdown
- Session breakdown (London, NY, Asian, Other)
- Benchmark comparison table
- Average R multiple
- CSV export
"""

from __future__ import annotations

import io
import math
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOW_TRADE_COUNT_FLAG = 20  # flag months with fewer trades than this
SESSION_HOURS = {
    "Asian":  (0, 8),    # 00:00–08:00 UTC
    "London": (8, 13),   # 08:00–13:00 UTC
    "NY":     (13, 21),  # 13:00–21:00 UTC
    "Other":  (21, 24),
}


# ---------------------------------------------------------------------------
# Core metric helpers
# ---------------------------------------------------------------------------

def _profit_factor(pnl_series: pd.Series) -> float:
    gross_profit = pnl_series[pnl_series > 0].sum()
    gross_loss = abs(pnl_series[pnl_series < 0].sum())
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _max_drawdown(equity_curve: pd.Series) -> tuple[float, float]:
    """Returns (max_drawdown_$, max_drawdown_%)."""
    if equity_curve.empty:
        return 0.0, 0.0
    peak = equity_curve.cummax()
    dd = equity_curve - peak
    max_dd_abs = float(dd.min())
    max_dd_pct = float((dd / peak).min() * 100)
    return max_dd_abs, max_dd_pct


def _win_rate(pnl_series: pd.Series) -> float:
    if pnl_series.empty:
        return 0.0
    return float((pnl_series > 0).sum() / len(pnl_series) * 100)


def _avg_r(r_series: pd.Series) -> float:
    if r_series.empty:
        return 0.0
    return float(r_series.mean())


def _sharpe(pnl_series: pd.Series, periods_per_year: int = 252) -> float:
    """Annualised Sharpe (assumes daily P&L series)."""
    if pnl_series.empty or pnl_series.std() == 0:
        return 0.0
    return float(pnl_series.mean() / pnl_series.std() * math.sqrt(periods_per_year))


def _calmar(total_pnl: float, max_dd: float, years: float) -> float:
    if max_dd == 0 or years == 0:
        return 0.0
    annualised = total_pnl / years
    return annualised / abs(max_dd)


# ---------------------------------------------------------------------------
# Monthly breakdown builder
# ---------------------------------------------------------------------------

def _build_monthly_df(
    trades: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """
    Return a monthly pivot with:
    pnl_net, trade_count, win_rate, profit_factor, avg_r, low_count_flag
    """
    # Generate all months in range (inclusive) — ensures months with 0 trades appear
    all_months = pd.period_range(start=start, end=end, freq="M")

    if trades.empty:
        empty_rows = []
        for m in all_months:
            empty_rows.append({
                "month": str(m),
                "pnl_net": 0.0,
                "trade_count": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "avg_r": 0.0,
                "low_count": True,
            })
        return pd.DataFrame(empty_rows).set_index("month")

    df = trades.copy()
    df["month"] = pd.PeriodIndex(df["entry_time"], freq="M").astype(str)

    grouped = df.groupby("month")
    rows = []
    for m in all_months:
        ms = str(m)
        if ms in grouped.groups:
            g = grouped.get_group(ms)
            pnl = g["pnl_net"].sum()
            tc = len(g)
            wr = _win_rate(g["pnl_net"])
            pf = _profit_factor(g["pnl_net"])
            ar = _avg_r(g["r_multiple"])
        else:
            pnl, tc, wr, pf, ar = 0.0, 0, 0.0, 0.0, 0.0

        rows.append({
            "month": ms,
            "pnl_net": round(pnl, 2),
            "trade_count": tc,
            "win_rate_pct": round(wr, 1),
            "profit_factor": round(pf, 2),
            "avg_r": round(ar, 2),
            "low_count": tc < LOW_TRADE_COUNT_FLAG,
        })

    return pd.DataFrame(rows).set_index("month")


# ---------------------------------------------------------------------------
# Main reporter class
# ---------------------------------------------------------------------------

class PerformanceReporter:
    """
    Compute and format all performance metrics for one strategy run.
    """

    def __init__(
        self,
        results: dict,
        start: pd.Timestamp,
        end: pd.Timestamp,
        is_simulated: bool = False,
    ):
        self.results = results
        self.start = start
        self.end = end
        self.is_simulated = is_simulated
        self.symbol = results["symbol"]
        self.strategy = results["strategy"]
        self.initial_capital = results["initial_capital"]
        self.final_equity = results["final_equity"]
        self.trades: pd.DataFrame = results["trades"]
        self.equity_curve: pd.Series = results["equity_curve"]

        self._monthly = _build_monthly_df(self.trades, start, end)

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        t = self.trades
        eq = self.equity_curve

        if t.empty:
            return self._empty_summary()

        total_pnl = float(t["pnl_net"].sum())
        total_trades = len(t)
        wr = _win_rate(t["pnl_net"])
        pf = _profit_factor(t["pnl_net"])
        avg_r = _avg_r(t["r_multiple"])
        best_trade = float(t["pnl_net"].max())
        worst_trade = float(t["pnl_net"].min())

        max_dd_abs, max_dd_pct = _max_drawdown(eq + self.initial_capital)

        years = max((self.end - self.start).days / 365.25, 1 / 365.25)
        calmar = _calmar(total_pnl, max_dd_abs, years)

        # daily P&L for Sharpe
        if "entry_time" in t.columns:
            daily = t.groupby(t["entry_time"].dt.date)["pnl_net"].sum()
            sharpe = _sharpe(daily)
        else:
            sharpe = 0.0

        monthly_pnl = self._monthly["pnl_net"]
        best_month = monthly_pnl.idxmax() if not monthly_pnl.empty else "N/A"
        worst_month = monthly_pnl.idxmin() if not monthly_pnl.empty else "N/A"

        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "simulated": self.is_simulated,
            "period": f"{self.start.date()} → {self.end.date()}",
            "total_pnl_usd": round(total_pnl, 2),
            "total_trades": total_trades,
            "win_rate_pct": round(wr, 1),
            "profit_factor": round(pf, 2),
            "avg_r_multiple": round(avg_r, 2),
            "best_trade_usd": round(best_trade, 2),
            "worst_trade_usd": round(worst_trade, 2),
            "max_drawdown_usd": round(max_dd_abs, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "sharpe_ratio": round(sharpe, 2),
            "calmar_ratio": round(calmar, 2),
            "best_month": best_month,
            "worst_month": worst_month,
            "initial_capital": self.initial_capital,
            "final_equity": round(self.final_equity, 2),
            "net_return_pct": round((self.final_equity / self.initial_capital - 1) * 100, 2),
        }

    def _empty_summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "simulated": self.is_simulated,
            "period": f"{self.start.date()} → {self.end.date()}",
            "total_pnl_usd": 0.0,
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_r_multiple": 0.0,
            "best_trade_usd": 0.0,
            "worst_trade_usd": 0.0,
            "max_drawdown_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "calmar_ratio": 0.0,
            "best_month": "N/A",
            "worst_month": "N/A",
            "initial_capital": self.initial_capital,
            "final_equity": self.initial_capital,
            "net_return_pct": 0.0,
        }

    # ------------------------------------------------------------------
    # Direction breakdown
    # ------------------------------------------------------------------

    def direction_breakdown(self) -> pd.DataFrame:
        t = self.trades
        if t.empty:
            return pd.DataFrame()
        rows = []
        for d in ["long", "short"]:
            sub = t[t["direction"] == d]
            rows.append({
                "direction": d,
                "trades": len(sub),
                "pnl_net": round(sub["pnl_net"].sum(), 2),
                "win_rate_pct": round(_win_rate(sub["pnl_net"]), 1),
                "profit_factor": round(_profit_factor(sub["pnl_net"]), 2),
                "avg_r": round(_avg_r(sub["r_multiple"]), 2),
            })
        return pd.DataFrame(rows).set_index("direction")

    # ------------------------------------------------------------------
    # Session breakdown
    # ------------------------------------------------------------------

    def session_breakdown(self) -> pd.DataFrame:
        t = self.trades
        if t.empty:
            return pd.DataFrame()
        rows = []
        for sess in ["London", "NY", "Asian", "Other"]:
            sub = t[t["session"] == sess]
            rows.append({
                "session": sess,
                "trades": len(sub),
                "pnl_net": round(sub["pnl_net"].sum(), 2) if not sub.empty else 0.0,
                "win_rate_pct": round(_win_rate(sub["pnl_net"]), 1) if not sub.empty else 0.0,
                "profit_factor": round(_profit_factor(sub["pnl_net"]), 2) if not sub.empty else 0.0,
            })
        return pd.DataFrame(rows).set_index("session")

    # ------------------------------------------------------------------
    # Exit reason breakdown
    # ------------------------------------------------------------------

    def exit_reason_breakdown(self) -> pd.DataFrame:
        t = self.trades
        if t.empty:
            return pd.DataFrame()
        rows = []
        for reason in ["tp", "sl", "time", "eod"]:
            sub = t[t["exit_reason"] == reason]
            rows.append({
                "exit_reason": reason,
                "count": len(sub),
                "pnl_net": round(sub["pnl_net"].sum(), 2) if not sub.empty else 0.0,
                "pct_of_trades": round(len(sub) / max(len(t), 1) * 100, 1),
            })
        return pd.DataFrame(rows).set_index("exit_reason")

    # ------------------------------------------------------------------
    # Print helpers
    # ------------------------------------------------------------------

    def _sim_banner(self) -> str:
        if self.is_simulated:
            return (
                "\n" + "!" * 70 + "\n"
                "!!! SIMULATED DATA — DO NOT USE FOR LIVE TRADING DECISIONS !!!!\n"
                + "!" * 70 + "\n"
            )
        return ""

    def print_monthly_pnl(self) -> None:
        print(self._sim_banner())
        print(f"\n{'='*60}")
        print(f"  Monthly P&L — {self.strategy} on {self.symbol}")
        print(f"{'='*60}")
        m = self._monthly[["pnl_net", "trade_count", "win_rate_pct", "profit_factor", "avg_r", "low_count"]].copy()
        m["flag"] = m["low_count"].apply(lambda x: " *** LOW TRADE COUNT" if x else "")
        m = m.drop(columns="low_count")
        m.columns = ["P&L ($)", "Trades", "Win %", "PF", "Avg R", "Note"]
        print(m.to_string())
        print()

    def print_summary(self) -> None:
        print(self._sim_banner())
        s = self.summary()
        print(f"\n{'='*60}")
        print(f"  Performance Summary — {s['strategy']} on {s['symbol']}")
        if self.is_simulated:
            print("  [SIMULATED DATA — NOT FOR LIVE TRADING]")
        print(f"  Period: {s['period']}")
        print(f"{'='*60}")
        for k, v in s.items():
            if k in ("symbol", "strategy", "simulated", "period"):
                continue
            print(f"  {k:<25} {v}")
        print()

    def print_direction_breakdown(self) -> None:
        print(f"\n{'='*60}")
        print("  Long vs Short Breakdown")
        print(f"{'='*60}")
        print(self.direction_breakdown().to_string())
        print()

    def print_session_breakdown(self) -> None:
        print(f"\n{'='*60}")
        print("  Session Breakdown")
        print(f"{'='*60}")
        print(self.session_breakdown().to_string())
        print()

    def print_exit_reason_breakdown(self) -> None:
        print(f"\n{'='*60}")
        print("  Exit Reason Breakdown")
        print(f"{'='*60}")
        print(self.exit_reason_breakdown().to_string())
        print()

    def print_all(self) -> None:
        self.print_summary()
        self.print_monthly_pnl()
        self.print_direction_breakdown()
        self.print_session_breakdown()
        self.print_exit_reason_breakdown()

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------

    def export_csv(self, output_dir: str) -> list[str]:
        """Export all tables to CSV. Returns list of written file paths."""
        import os
        os.makedirs(output_dir, exist_ok=True)
        prefix = f"{output_dir}/{self.strategy}_{self.symbol}"
        files = []

        # trades
        if not self.trades.empty:
            p = f"{prefix}_trades.csv"
            self.trades.to_csv(p, index=False)
            files.append(p)

        # monthly P&L
        p = f"{prefix}_monthly_pnl.csv"
        self._monthly.to_csv(p)
        files.append(p)

        # summary
        p = f"{prefix}_summary.csv"
        pd.Series(self.summary()).to_frame("value").to_csv(p)
        files.append(p)

        # direction
        if not self.direction_breakdown().empty:
            p = f"{prefix}_direction.csv"
            self.direction_breakdown().to_csv(p)
            files.append(p)

        # session
        if not self.session_breakdown().empty:
            p = f"{prefix}_session.csv"
            self.session_breakdown().to_csv(p)
            files.append(p)

        return files


# ---------------------------------------------------------------------------
# Benchmark comparison table
# ---------------------------------------------------------------------------

def print_benchmark_comparison(reporters: list[PerformanceReporter]) -> None:
    """Side-by-side comparison of multiple strategy reporters."""
    rows = []
    for r in reporters:
        s = r.summary()
        rows.append({
            "Strategy": s["strategy"],
            "Symbol": s["symbol"],
            "Simulated": "YES" if s["simulated"] else "NO",
            "Total P&L ($)": s["total_pnl_usd"],
            "Trades": s["total_trades"],
            "Win %": s["win_rate_pct"],
            "Profit Factor": s["profit_factor"],
            "Max DD ($)": s["max_drawdown_usd"],
            "Max DD %": s["max_drawdown_pct"],
            "Avg R": s["avg_r_multiple"],
            "Sharpe": s["sharpe_ratio"],
            "Net Return %": s["net_return_pct"],
        })
    df = pd.DataFrame(rows)
    print("\n" + "=" * 80)
    print("  BENCHMARK COMPARISON TABLE")
    print("=" * 80)
    print(df.to_string(index=False))
    print()


def export_benchmark_comparison_csv(
    reporters: list[PerformanceReporter], output_dir: str
) -> str:
    import os
    os.makedirs(output_dir, exist_ok=True)
    rows = [r.summary() for r in reporters]
    df = pd.DataFrame(rows)
    p = f"{output_dir}/benchmark_comparison.csv"
    df.to_csv(p, index=False)
    return p
