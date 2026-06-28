"""
qa_validator.py — EMPIREX-OS Quantitative Strategy QA Validation Framework
===========================================================================
Author  : EMPIREX-OS / qa-agent
Version : 1.0.0
Date    : 2026-06-28

PURPOSE
-------
Validate strategy results BEFORE they are approved for forward testing or live
trading.  Every mandatory check must pass; a single failure produces a REJECTED
verdict.

VERDICT LADDER
--------------
  REJECTED          — Any mandatory check fails.
  RESEARCH-VALID    — All mandatory checks pass; warnings present.
  FORWARD-TEST READY — All checks pass, no warnings, profit factor > 1.5.
  LIVE-READY        — FORWARD-TEST READY + min 3 months out-of-sample validation.

USAGE
-----
    from qa_validator import QAValidator

    validator = QAValidator()
    report = validator.run_all_checks(strategy_results)
    print(report.summary())
    print(report.verdict)

INPUT SCHEMA  (strategy_results dict)
--------------------------------------
Required keys
  "symbol"              : str              e.g. "EURUSD"
  "strategy_name"       : str
  "backtest_start"      : str | datetime   ISO-8601 date
  "backtest_end"        : str | datetime   ISO-8601 date
  "trades"              : pd.DataFrame     one row per closed trade (see columns below)
  "equity_curve"        : pd.Series        account equity after each bar
  "initial_capital"     : float
  "final_equity"        : float
  "spread_included"     : bool
  "commission_included" : bool
  "slippage_included"   : bool
  "cost_per_trade_usd"  : float            documented round-trip cost
  "broker_spread_pips"  : float            broker spec spread
  "broker_commission"   : float            broker spec commission RT
  "broker_slippage_pips": float            broker spec slippage
  "london_filter_present": bool
  "stop_at_order_time"  : bool             SL set at order-creation time
  "uses_martingale"     : bool
  "uses_grid"           : bool
  "uses_averaging_down" : bool
  "fixed_lot_size"      : bool
  "entry_market_order"  : bool
  "slippage_model"      : str              "ecn" | "market_maker"
  "broker_type"         : str              "ecn" | "market_maker"
  "kill_switch_defined" : bool
  "oos_months"          : int              out-of-sample months validated (0 if none)
  "pine_script_code"    : str | None       optional; enables repainting checks

Optional keys (auto-derived when possible)
  "max_drawdown_pct"    : float            if not provided, derived from equity_curve
  "max_consecutive_losses" : int           if not provided, derived from trades
  "profit_factor"       : float            if not provided, derived from trades

Trades DataFrame expected columns
  entry_time  : datetime / Timestamp
  exit_time   : datetime / Timestamp
  pnl_net     : float    net P&L in USD
  is_winner   : bool
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Result primitives
# ---------------------------------------------------------------------------

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"
CHECK_WARN = "WARN"
CHECK_SKIP = "SKIP"   # not enough data to evaluate


@dataclass
class CheckResult:
    name: str
    status: str                  # PASS | FAIL | WARN | SKIP
    detail: str = ""
    value: Any = None            # raw value that was checked


@dataclass
class QAReport:
    strategy_name: str
    symbol: str
    backtest_start: str
    backtest_end: str
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> List[CheckResult]:
        return [c for c in self.checks if c.status == CHECK_PASS]

    @property
    def failed(self) -> List[CheckResult]:
        return [c for c in self.checks if c.status == CHECK_FAIL]

    @property
    def warnings(self) -> List[CheckResult]:
        return [c for c in self.checks if c.status == CHECK_WARN]

    @property
    def skipped(self) -> List[CheckResult]:
        return [c for c in self.checks if c.status == CHECK_SKIP]

    @property
    def verdict(self) -> str:
        """Compute final verdict based on check results."""
        if self.failed:
            return "REJECTED"

        has_warnings = bool(self.warnings)

        # Derive profit factor from checks
        pf_check = self._get_check("profit_factor_gt_1_2")
        pf_value = pf_check.value if pf_check else None

        oos_check = self._get_check("oos_validation")
        oos_value = oos_check.value if oos_check else 0

        if has_warnings:
            return "RESEARCH-VALID"

        if pf_value is not None and pf_value > 1.5 and (oos_value or 0) >= 3:
            return "LIVE-READY"

        if pf_value is not None and pf_value > 1.5:
            return "FORWARD-TEST READY"

        return "RESEARCH-VALID"

    def _get_check(self, name: str) -> Optional[CheckResult]:
        for c in self.checks:
            if c.name == name:
                return c
        return None

    def summary(self) -> str:
        lines = [
            "=" * 70,
            f"  QA REPORT: {self.strategy_name} | {self.symbol}",
            f"  Backtest period: {self.backtest_start} → {self.backtest_end}",
            "=" * 70,
            f"  PASSED  : {len(self.passed)}",
            f"  FAILED  : {len(self.failed)}",
            f"  WARNINGS: {len(self.warnings)}",
            f"  SKIPPED : {len(self.skipped)}",
            "-" * 70,
        ]

        if self.failed:
            lines.append("  FAILURES:")
            for c in self.failed:
                lines.append(f"    [FAIL] {c.name}: {c.detail}")

        if self.warnings:
            lines.append("  WARNINGS:")
            for c in self.warnings:
                lines.append(f"    [WARN] {c.name}: {c.detail}")

        lines.append("-" * 70)
        lines.append(f"  VERDICT: >>> {self.verdict} <<<")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "backtest_start": self.backtest_start,
            "backtest_end": self.backtest_end,
            "verdict": self.verdict,
            "passed": [(c.name, c.detail) for c in self.passed],
            "failed": [(c.name, c.detail) for c in self.failed],
            "warnings": [(c.name, c.detail) for c in self.warnings],
            "skipped": [(c.name, c.detail) for c in self.skipped],
        }


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _require(results: Dict, key: str, default=None):
    """Return value from results dict or default."""
    return results.get(key, default)


def _derive_monthly_table(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a trades DataFrame with 'exit_time' and 'pnl_net', return a monthly
    summary DataFrame with columns: year, month, trade_count, total_pnl.
    """
    if trades_df.empty:
        return pd.DataFrame(columns=["year", "month", "trade_count", "total_pnl"])

    df = trades_df.copy()
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
    df["year"] = df["exit_time"].dt.year
    df["month"] = df["exit_time"].dt.month

    monthly = (
        df.groupby(["year", "month"])
        .agg(trade_count=("pnl_net", "count"), total_pnl=("pnl_net", "sum"))
        .reset_index()
    )
    return monthly


def _derive_max_drawdown(equity: pd.Series) -> float:
    """Return maximum drawdown as a positive percentage (0–100)."""
    if equity is None or len(equity) == 0:
        return float("nan")
    eq = np.array(equity, dtype=float)
    peak = np.maximum.accumulate(eq)
    drawdown = (peak - eq) / peak
    return float(np.nanmax(drawdown)) * 100.0


def _derive_profit_factor(trades_df: pd.DataFrame) -> float:
    """Return profit factor = gross_wins / abs(gross_losses). nan if no losses."""
    if trades_df.empty or "pnl_net" not in trades_df.columns:
        return float("nan")
    wins = trades_df[trades_df["pnl_net"] > 0]["pnl_net"].sum()
    losses = abs(trades_df[trades_df["pnl_net"] <= 0]["pnl_net"].sum())
    if losses == 0:
        return float("inf")
    return float(wins / losses)


def _derive_max_consecutive_losses(trades_df: pd.DataFrame) -> int:
    """Count longest streak of negative pnl_net trades."""
    if trades_df.empty or "pnl_net" not in trades_df.columns:
        return 0
    is_loss = (trades_df["pnl_net"] <= 0).astype(int).values
    max_streak = 0
    streak = 0
    for v in is_loss:
        if v:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _derive_win_rate(trades_df: pd.DataFrame) -> float:
    """Return win rate 0–100."""
    if trades_df.empty or "pnl_net" not in trades_df.columns:
        return float("nan")
    wins = (trades_df["pnl_net"] > 0).sum()
    return float(wins / len(trades_df)) * 100.0


# ---------------------------------------------------------------------------
# Main validator class
# ---------------------------------------------------------------------------

class QAValidator:
    """
    Run all mandatory QA checks on a strategy backtest result dictionary.

    Each check_* method returns a CheckResult.
    run_all_checks() runs every check and returns a QAReport.
    """

    # -----------------------------------------------------------------------
    # SECTION 1: TECHNICAL QUALITY
    # -----------------------------------------------------------------------

    def check_no_repainting_declared(self, results: Dict) -> CheckResult:
        """
        Check that the strategy author has declared no-repainting measures.
        If Pine Script code is provided, delegate to RepaintingChecker.
        """
        pine_code = _require(results, "pine_script_code")
        if pine_code:
            from repainting_checker import RepaintingChecker
            checker = RepaintingChecker()
            violations = checker.check(pine_code)
            if violations:
                details = "; ".join(
                    f"Line {v['line']}: {v['rule']}" for v in violations[:5]
                )
                return CheckResult(
                    "no_repainting",
                    CHECK_FAIL,
                    f"Repainting violations found: {details}",
                    violations,
                )
            return CheckResult("no_repainting", CHECK_PASS, "No repainting patterns detected in Pine Script code.")

        # Fallback: ask for explicit declaration
        no_repaint = _require(results, "no_repainting_declared", None)
        if no_repaint is True:
            return CheckResult("no_repainting", CHECK_PASS, "Author declares: no repainting.")
        if no_repaint is False:
            return CheckResult("no_repainting", CHECK_FAIL, "Author declares repainting present.")
        return CheckResult("no_repainting", CHECK_WARN,
                           "No repainting declaration found and no Pine Script provided for automated check.")

    def check_no_lookahead_bias(self, results: Dict) -> CheckResult:
        """
        Check no lookahead: either Python engine enforces closed-bar-only access
        or Pine Script has no security(lookahead=true) calls.
        """
        pine_code = _require(results, "pine_script_code")
        if pine_code:
            from repainting_checker import RepaintingChecker
            checker = RepaintingChecker()
            violations = checker.check(pine_code)
            lookahead_violations = [v for v in violations if "lookahead" in v["rule"].lower()]
            if lookahead_violations:
                details = "; ".join(f"Line {v['line']}: {v['rule']}" for v in lookahead_violations)
                return CheckResult("no_lookahead_bias", CHECK_FAIL,
                                   f"Lookahead violations: {details}", lookahead_violations)

        no_lookahead = _require(results, "no_lookahead_bias_declared", None)
        if no_lookahead is True:
            return CheckResult("no_lookahead_bias", CHECK_PASS,
                               "Signals computed on closed bars only (verified or declared).")
        if no_lookahead is False:
            return CheckResult("no_lookahead_bias", CHECK_FAIL, "Lookahead bias present.")
        return CheckResult("no_lookahead_bias", CHECK_WARN,
                           "No lookahead declaration provided. Manual code review required.")

    def check_confirmed_bars_only(self, results: Dict) -> CheckResult:
        """
        Verify signals are generated on confirmed (closed) bars only.
        For Python backtests, the BacktestEngine enforces this architecturally
        (signals from prev_bars slice, fills on next bar open).
        """
        confirmed = _require(results, "confirmed_bars_only", None)
        engine_type = _require(results, "engine_type", "")

        if engine_type == "backtest_engine_v1":
            return CheckResult("confirmed_bars_only", CHECK_PASS,
                               "BacktestEngine v1 enforces closed-bar-only signal generation by design.")
        if confirmed is True:
            return CheckResult("confirmed_bars_only", CHECK_PASS,
                               "Confirmed bars only: declared True.")
        if confirmed is False:
            return CheckResult("confirmed_bars_only", CHECK_FAIL,
                               "Signals generated on non-confirmed bars.")
        return CheckResult("confirmed_bars_only", CHECK_WARN,
                           "Confirmed-bar enforcement not declared. Verify manually.")

    # -----------------------------------------------------------------------
    # SECTION 2: COST REALISM
    # -----------------------------------------------------------------------

    def check_spread_included(self, results: Dict) -> CheckResult:
        spread = _require(results, "spread_included", None)
        if spread is True:
            return CheckResult("spread_included", CHECK_PASS, "Spread included in backtest.")
        if spread is False:
            return CheckResult("spread_included", CHECK_FAIL,
                               "Spread NOT included. Backtest P&L is overstated.")
        return CheckResult("spread_included", CHECK_FAIL,
                           "spread_included key missing. Assume not included — REJECTED.")

    def check_commission_included(self, results: Dict) -> CheckResult:
        commission = _require(results, "commission_included", None)
        if commission is True:
            return CheckResult("commission_included", CHECK_PASS, "Commission included in backtest.")
        if commission is False:
            return CheckResult("commission_included", CHECK_FAIL,
                               "Commission NOT included. Backtest P&L is overstated.")
        return CheckResult("commission_included", CHECK_FAIL,
                           "commission_included key missing. Assume not included — REJECTED.")

    def check_slippage_included(self, results: Dict) -> CheckResult:
        slippage = _require(results, "slippage_included", None)
        if slippage is True:
            return CheckResult("slippage_included", CHECK_PASS, "Slippage included in backtest.")
        if slippage is False:
            return CheckResult("slippage_included", CHECK_FAIL,
                               "Slippage NOT included. Backtest P&L is overstated.")
        return CheckResult("slippage_included", CHECK_FAIL,
                           "slippage_included key missing. Assume not included — REJECTED.")

    def check_cost_documentation(self, results: Dict) -> CheckResult:
        """
        Verify that documented cost per trade is consistent with broker specs.
        Tolerance: within 20% of broker spec total cost.
        """
        cost_doc = _require(results, "cost_per_trade_usd", None)
        spread_pips = _require(results, "broker_spread_pips", None)
        commission = _require(results, "broker_commission", None)
        slip_pips = _require(results, "broker_slippage_pips", None)

        if cost_doc is None:
            return CheckResult("cost_documentation", CHECK_FAIL,
                               "cost_per_trade_usd not documented.")

        if spread_pips is None or commission is None or slip_pips is None:
            return CheckResult("cost_documentation", CHECK_WARN,
                               f"Cost documented as ${cost_doc:.2f}/trade but broker specs incomplete. "
                               "Cannot verify against broker spec.",
                               cost_doc)

        # Rough broker spec total: pips * $10/pip (EURUSD/GBPUSD assumed) + commission
        pip_value = 10.0  # approximate for major forex; adjust per instrument
        broker_cost = (spread_pips + slip_pips) * pip_value + commission
        ratio = cost_doc / broker_cost if broker_cost > 0 else float("inf")

        if 0.80 <= ratio <= 1.20:
            return CheckResult("cost_documentation", CHECK_PASS,
                               f"Documented cost ${cost_doc:.2f} is within 20% of broker spec ${broker_cost:.2f}.",
                               cost_doc)
        return CheckResult("cost_documentation", CHECK_WARN,
                           f"Documented cost ${cost_doc:.2f} deviates >20% from broker spec ${broker_cost:.2f}. "
                           "Verify cost model.",
                           cost_doc)

    # -----------------------------------------------------------------------
    # SECTION 3: STATISTICAL VALIDITY
    # -----------------------------------------------------------------------

    def check_min_trades_per_month(self, results: Dict) -> CheckResult:
        """Reject if any calendar month has < 20 trades."""
        trades_df = _require(results, "trades", pd.DataFrame())
        if trades_df.empty:
            return CheckResult("min_trades_per_month", CHECK_FAIL,
                               "No trades in results.")

        monthly = _derive_monthly_table(trades_df)
        if monthly.empty:
            return CheckResult("min_trades_per_month", CHECK_FAIL,
                               "Cannot derive monthly table from trades.")

        bad_months = monthly[monthly["trade_count"] < 20]
        if bad_months.empty:
            min_count = int(monthly["trade_count"].min())
            return CheckResult("min_trades_per_month", CHECK_PASS,
                               f"All months have >= 20 trades. Min: {min_count}.",
                               monthly)

        details = ", ".join(
            f"{int(r.year)}-{int(r.month):02d}({int(r.trade_count)})"
            for _, r in bad_months.iterrows()
        )
        return CheckResult("min_trades_per_month", CHECK_FAIL,
                           f"Months with < 20 trades: {details}",
                           monthly)

    def check_monthly_profit_concentration(self, results: Dict) -> CheckResult:
        """Reject if any single month contributes > 40% of total profit."""
        trades_df = _require(results, "trades", pd.DataFrame())
        if trades_df.empty:
            return CheckResult("monthly_profit_concentration", CHECK_FAIL, "No trades.")

        monthly = _derive_monthly_table(trades_df)
        total_profit = monthly["total_pnl"].sum()
        if total_profit <= 0:
            return CheckResult("monthly_profit_concentration", CHECK_WARN,
                               "Total profit <= 0; concentration check not meaningful.")

        monthly["pct_of_total"] = monthly["total_pnl"] / total_profit * 100.0
        max_pct = float(monthly["pct_of_total"].max())
        max_row = monthly.loc[monthly["pct_of_total"].idxmax()]

        if max_pct > 40.0:
            return CheckResult("monthly_profit_concentration", CHECK_FAIL,
                               f"{int(max_row.year)}-{int(max_row.month):02d} contributes "
                               f"{max_pct:.1f}% of total profit (limit: 40%).",
                               max_pct)
        return CheckResult("monthly_profit_concentration", CHECK_PASS,
                           f"Max single-month profit share: {max_pct:.1f}% (limit: 40%).",
                           max_pct)

    def check_minimum_backtest_duration(self, results: Dict) -> CheckResult:
        """Reject if backtest covers < 6 calendar months."""
        start = _require(results, "backtest_start")
        end = _require(results, "backtest_end")
        if start is None or end is None:
            return CheckResult("minimum_backtest_duration", CHECK_FAIL,
                               "backtest_start or backtest_end not provided.")

        try:
            s = pd.to_datetime(start)
            e = pd.to_datetime(end)
        except Exception as ex:
            return CheckResult("minimum_backtest_duration", CHECK_FAIL,
                               f"Cannot parse dates: {ex}")

        months = (e.year - s.year) * 12 + (e.month - s.month)
        if months < 6:
            return CheckResult("minimum_backtest_duration", CHECK_FAIL,
                               f"Backtest duration is {months} months (minimum: 6).",
                               months)
        return CheckResult("minimum_backtest_duration", CHECK_PASS,
                           f"Backtest duration: {months} months.",
                           months)

    def check_win_rate_plausible(self, results: Dict) -> CheckResult:
        """
        Flag (WARN) if win rate is outside [30%, 70%].
        Very high win rates (>70%) may indicate overfitting or curve-fitting.
        Very low win rates (<30%) may indicate poor strategy design.
        """
        trades_df = _require(results, "trades", pd.DataFrame())
        if trades_df.empty:
            return CheckResult("win_rate_plausible", CHECK_FAIL, "No trades.")

        wr = _derive_win_rate(trades_df)
        if math.isnan(wr):
            return CheckResult("win_rate_plausible", CHECK_SKIP, "Cannot compute win rate.")

        if wr > 70.0:
            return CheckResult("win_rate_plausible", CHECK_WARN,
                               f"Win rate {wr:.1f}% > 70%. Verify — possible overfitting or data issue.",
                               wr)
        if wr < 30.0:
            return CheckResult("win_rate_plausible", CHECK_WARN,
                               f"Win rate {wr:.1f}% < 30%. Verify strategy viability.",
                               wr)
        return CheckResult("win_rate_plausible", CHECK_PASS,
                           f"Win rate {wr:.1f}% is within plausible range [30%, 70%].",
                           wr)

    def check_profit_factor_gt_1_2(self, results: Dict) -> CheckResult:
        """Reject if profit factor <= 1.0; warn if between 1.0 and 1.2."""
        trades_df = _require(results, "trades", pd.DataFrame())
        pf = _require(results, "profit_factor", None)

        if pf is None:
            if trades_df.empty:
                return CheckResult("profit_factor_gt_1_2", CHECK_FAIL, "No trades — cannot compute profit factor.")
            pf = _derive_profit_factor(trades_df)

        if math.isnan(pf):
            return CheckResult("profit_factor_gt_1_2", CHECK_SKIP, "Cannot compute profit factor (no losses).")
        if math.isinf(pf):
            return CheckResult("profit_factor_gt_1_2", CHECK_PASS,
                               "Profit factor: infinite (no losing trades recorded). Verify data.",
                               pf)

        if pf <= 1.0:
            return CheckResult("profit_factor_gt_1_2", CHECK_FAIL,
                               f"Profit factor {pf:.3f} <= 1.0. Strategy loses money net of costs.",
                               pf)
        if pf < 1.2:
            return CheckResult("profit_factor_gt_1_2", CHECK_WARN,
                               f"Profit factor {pf:.3f} is between 1.0 and 1.2 (minimum threshold: 1.2). "
                               "Marginal strategy.",
                               pf)
        return CheckResult("profit_factor_gt_1_2", CHECK_PASS,
                           f"Profit factor: {pf:.3f} (threshold: 1.2).",
                           pf)

    # -----------------------------------------------------------------------
    # SECTION 4: MONTHLY BREAKDOWN
    # -----------------------------------------------------------------------

    def check_monthly_pnl_table_exists(self, results: Dict) -> CheckResult:
        """Verify that a monthly P/L breakdown can be derived from trades."""
        trades_df = _require(results, "trades", pd.DataFrame())
        if trades_df.empty:
            return CheckResult("monthly_pnl_table_exists", CHECK_FAIL, "No trades to build monthly table.")

        required_cols = {"exit_time", "pnl_net"}
        missing = required_cols - set(trades_df.columns)
        if missing:
            return CheckResult("monthly_pnl_table_exists", CHECK_FAIL,
                               f"Trades DataFrame missing columns: {missing}")

        monthly = _derive_monthly_table(trades_df)
        if monthly.empty:
            return CheckResult("monthly_pnl_table_exists", CHECK_FAIL, "Monthly table is empty.")

        return CheckResult("monthly_pnl_table_exists", CHECK_PASS,
                           f"Monthly P/L table present: {len(monthly)} months of data.",
                           monthly.to_dict("records"))

    def check_monthly_trade_count_table_exists(self, results: Dict) -> CheckResult:
        """Check that monthly trade count can be derived."""
        trades_df = _require(results, "trades", pd.DataFrame())
        if trades_df.empty:
            return CheckResult("monthly_trade_count_table_exists", CHECK_FAIL, "No trades.")

        monthly = _derive_monthly_table(trades_df)
        if monthly.empty:
            return CheckResult("monthly_trade_count_table_exists", CHECK_FAIL, "Cannot build monthly table.")

        return CheckResult("monthly_trade_count_table_exists", CHECK_PASS,
                           f"Monthly trade count table present: {len(monthly)} months.",
                           monthly[["year", "month", "trade_count"]].to_dict("records"))

    def check_no_zero_trade_months(self, results: Dict) -> CheckResult:
        """Flag months with 0 trades (unless they are holiday months)."""
        trades_df = _require(results, "trades", pd.DataFrame())
        holiday_months = _require(results, "holiday_months", [])  # list of "YYYY-MM" strings

        if trades_df.empty:
            return CheckResult("no_zero_trade_months", CHECK_FAIL, "No trades.")

        # Build a full month range from backtest_start to backtest_end
        start = _require(results, "backtest_start")
        end = _require(results, "backtest_end")
        if start is None or end is None:
            return CheckResult("no_zero_trade_months", CHECK_SKIP,
                               "Cannot check without backtest_start and backtest_end.")

        all_months = pd.date_range(start=pd.to_datetime(start),
                                   end=pd.to_datetime(end), freq="MS")
        monthly = _derive_monthly_table(trades_df)
        monthly["ym"] = monthly.apply(lambda r: f"{int(r.year)}-{int(r.month):02d}", axis=1)
        traded_months = set(monthly["ym"])

        zero_months = []
        for m in all_months:
            ym = m.strftime("%Y-%m")
            if ym not in traded_months and ym not in holiday_months:
                zero_months.append(ym)

        if zero_months:
            return CheckResult("no_zero_trade_months", CHECK_WARN,
                               f"Months with 0 trades: {', '.join(zero_months)}. "
                               "If not holidays, investigate strategy inactivity.",
                               zero_months)
        return CheckResult("no_zero_trade_months", CHECK_PASS,
                           "No unexplained zero-trade months.")

    def check_best_worst_month_identified(self, results: Dict) -> CheckResult:
        """Identify best and worst month for documentation."""
        trades_df = _require(results, "trades", pd.DataFrame())
        if trades_df.empty:
            return CheckResult("best_worst_month", CHECK_FAIL, "No trades.")

        monthly = _derive_monthly_table(trades_df)
        if monthly.empty:
            return CheckResult("best_worst_month", CHECK_SKIP, "Monthly table empty.")

        best = monthly.loc[monthly["total_pnl"].idxmax()]
        worst = monthly.loc[monthly["total_pnl"].idxmin()]

        detail = (
            f"Best: {int(best.year)}-{int(best.month):02d} (${best.total_pnl:,.2f}) | "
            f"Worst: {int(worst.year)}-{int(worst.month):02d} (${worst.total_pnl:,.2f})"
        )
        return CheckResult("best_worst_month", CHECK_PASS, detail,
                           {"best": best.to_dict(), "worst": worst.to_dict()})

    # -----------------------------------------------------------------------
    # SECTION 5: BENCHMARK COMPARISON
    # -----------------------------------------------------------------------

    def check_vs_buy_and_hold(self, results: Dict) -> CheckResult:
        """Compare strategy net return to passive buy-and-hold on same instrument."""
        strategy_pnl = _require(results, "final_equity", None)
        initial_capital = _require(results, "initial_capital", None)
        bah_return_pct = _require(results, "buy_and_hold_return_pct", None)

        if strategy_pnl is None or initial_capital is None:
            return CheckResult("vs_buy_and_hold", CHECK_SKIP,
                               "final_equity or initial_capital not provided.")

        strategy_return_pct = (strategy_pnl - initial_capital) / initial_capital * 100.0

        if bah_return_pct is None:
            return CheckResult("vs_buy_and_hold", CHECK_WARN,
                               f"Strategy return: {strategy_return_pct:.1f}%. "
                               "Buy-and-hold return not provided — cannot compare.",
                               strategy_return_pct)

        if strategy_return_pct > bah_return_pct:
            return CheckResult("vs_buy_and_hold", CHECK_PASS,
                               f"Strategy {strategy_return_pct:.1f}% > Buy-and-Hold {bah_return_pct:.1f}%.",
                               {"strategy": strategy_return_pct, "bah": bah_return_pct})
        return CheckResult("vs_buy_and_hold", CHECK_FAIL,
                           f"Strategy {strategy_return_pct:.1f}% does NOT beat Buy-and-Hold {bah_return_pct:.1f}%.",
                           {"strategy": strategy_return_pct, "bah": bah_return_pct})

    def check_vs_lrb_benchmark(self, results: Dict) -> CheckResult:
        """Compare strategy to LRB benchmark strategy."""
        strategy_pf = _require(results, "profit_factor", None)
        trades_df = _require(results, "trades", pd.DataFrame())
        lrb_pf = _require(results, "lrb_benchmark_profit_factor", None)
        lrb_return = _require(results, "lrb_benchmark_return_pct", None)
        initial_capital = _require(results, "initial_capital", None)
        final_equity = _require(results, "final_equity", None)

        if strategy_pf is None and not trades_df.empty:
            strategy_pf = _derive_profit_factor(trades_df)

        strategy_return = None
        if initial_capital and final_equity:
            strategy_return = (final_equity - initial_capital) / initial_capital * 100.0

        if lrb_pf is None and lrb_return is None:
            return CheckResult("vs_lrb_benchmark", CHECK_WARN,
                               "LRB benchmark results not provided. Run LRB_Benchmark_v6.pine first.",
                               {"strategy_pf": strategy_pf, "strategy_return": strategy_return})

        beats_pf = (strategy_pf > lrb_pf) if (strategy_pf and lrb_pf) else None
        beats_return = (strategy_return > lrb_return) if (strategy_return and lrb_return) else None

        if beats_pf and beats_return:
            return CheckResult("vs_lrb_benchmark", CHECK_PASS,
                               f"Strategy beats LRB on both profit factor "
                               f"({strategy_pf:.2f} > {lrb_pf:.2f}) and "
                               f"return ({strategy_return:.1f}% > {lrb_return:.1f}%).")
        if beats_pf or beats_return:
            return CheckResult("vs_lrb_benchmark", CHECK_WARN,
                               "Strategy beats LRB on one metric but not both. Review carefully.")
        return CheckResult("vs_lrb_benchmark", CHECK_FAIL,
                           f"Strategy does not beat LRB benchmark on either metric.")

    # -----------------------------------------------------------------------
    # SECTION 6: RISK CHECKS
    # -----------------------------------------------------------------------

    def check_max_drawdown_documented(self, results: Dict) -> CheckResult:
        """Verify max drawdown is documented and within acceptable bounds."""
        mdd = _require(results, "max_drawdown_pct", None)
        equity = _require(results, "equity_curve", None)

        if mdd is None:
            if equity is not None and len(equity) > 0:
                mdd = _derive_max_drawdown(pd.Series(equity))
            else:
                return CheckResult("max_drawdown_documented", CHECK_FAIL,
                                   "max_drawdown_pct not documented and equity_curve not available.")

        if mdd > 30.0:
            return CheckResult("max_drawdown_documented", CHECK_WARN,
                               f"Max drawdown: {mdd:.1f}%. Exceeds 30% warning threshold.",
                               mdd)
        return CheckResult("max_drawdown_documented", CHECK_PASS,
                           f"Max drawdown documented: {mdd:.1f}%.",
                           mdd)

    def check_max_consecutive_losses(self, results: Dict) -> CheckResult:
        """Document max consecutive losses and flag if > 10."""
        mcl = _require(results, "max_consecutive_losses", None)
        trades_df = _require(results, "trades", pd.DataFrame())

        if mcl is None:
            if not trades_df.empty:
                mcl = _derive_max_consecutive_losses(trades_df)
            else:
                return CheckResult("max_consecutive_losses", CHECK_FAIL,
                                   "max_consecutive_losses not documented and no trades provided.")

        if mcl > 10:
            return CheckResult("max_consecutive_losses", CHECK_WARN,
                               f"Max consecutive losses: {mcl}. Exceeds 10 — review risk tolerance.",
                               mcl)
        return CheckResult("max_consecutive_losses", CHECK_PASS,
                           f"Max consecutive losses: {mcl}.",
                           mcl)

    def check_kill_switch_defined(self, results: Dict) -> CheckResult:
        kill_switch = _require(results, "kill_switch_defined", None)
        if kill_switch is True:
            return CheckResult("kill_switch_defined", CHECK_PASS,
                               "Kill switch defined (auto-halt on drawdown trigger).")
        if kill_switch is False:
            return CheckResult("kill_switch_defined", CHECK_FAIL,
                               "No kill switch defined. MANDATORY for live trading protection.")
        return CheckResult("kill_switch_defined", CHECK_FAIL,
                           "kill_switch_defined not specified. Assumed absent — REJECTED.")

    def check_no_martingale_or_grid(self, results: Dict) -> CheckResult:
        """Reject if martingale, grid, or averaging-down detected."""
        martingale = _require(results, "uses_martingale", False)
        grid = _require(results, "uses_grid", False)
        avg_down = _require(results, "uses_averaging_down", False)

        bad = []
        if martingale:
            bad.append("martingale position sizing")
        if grid:
            bad.append("grid trading")
        if avg_down:
            bad.append("averaging down")

        if bad:
            return CheckResult("no_martingale_grid_averaging", CHECK_FAIL,
                               f"Prohibited techniques detected: {', '.join(bad)}.",
                               bad)
        return CheckResult("no_martingale_grid_averaging", CHECK_PASS,
                           "No martingale / grid / averaging down detected.")

    def check_fixed_lot_size(self, results: Dict) -> CheckResult:
        fixed = _require(results, "fixed_lot_size", None)
        if fixed is True:
            return CheckResult("fixed_lot_size", CHECK_PASS,
                               "Fixed lot size enforced (not risk-percent variable sizing).")
        if fixed is False:
            return CheckResult("fixed_lot_size", CHECK_WARN,
                               "Variable lot size detected. Ensure this is intentional and documented.")
        return CheckResult("fixed_lot_size", CHECK_WARN,
                           "fixed_lot_size not specified. Verify lot-sizing method.")

    # -----------------------------------------------------------------------
    # SECTION 7: EXECUTION FEASIBILITY
    # -----------------------------------------------------------------------

    def check_entry_achievable_market_orders(self, results: Dict) -> CheckResult:
        market_order = _require(results, "entry_market_order", None)
        if market_order is True:
            return CheckResult("entry_market_orders", CHECK_PASS,
                               "Entry via market orders — achievable in live execution.")
        if market_order is False:
            return CheckResult("entry_market_orders", CHECK_WARN,
                               "Entry uses limit/stop orders. Verify fill rate and phantom fill risk.")
        return CheckResult("entry_market_orders", CHECK_WARN,
                           "entry_market_order not specified. Verify execution method.")

    def check_stop_loss_at_order_time(self, results: Dict) -> CheckResult:
        sl_at_order = _require(results, "stop_at_order_time", None)
        if sl_at_order is True:
            return CheckResult("stop_loss_at_order_time", CHECK_PASS,
                               "Stop loss set at order creation time.")
        if sl_at_order is False:
            return CheckResult("stop_loss_at_order_time", CHECK_FAIL,
                               "Stop loss NOT set at order time. Risk undefined at entry — REJECTED.")
        return CheckResult("stop_loss_at_order_time", CHECK_FAIL,
                           "stop_at_order_time not specified. Assume SL not pre-set — REJECTED.")

    def check_slippage_model_matches_broker(self, results: Dict) -> CheckResult:
        model = _require(results, "slippage_model", None)
        broker_type = _require(results, "broker_type", None)

        if model is None:
            return CheckResult("slippage_model_matches_broker", CHECK_WARN,
                               "slippage_model not specified.")
        if broker_type is None:
            return CheckResult("slippage_model_matches_broker", CHECK_WARN,
                               f"slippage_model={model} but broker_type not specified.")

        if model.lower() == broker_type.lower():
            return CheckResult("slippage_model_matches_broker", CHECK_PASS,
                               f"Slippage model '{model}' matches broker type '{broker_type}'.")
        return CheckResult("slippage_model_matches_broker", CHECK_WARN,
                           f"Slippage model '{model}' differs from broker type '{broker_type}'. "
                           "Backtest costs may not match live costs.")

    def check_london_session_filter(self, results: Dict) -> CheckResult:
        london_filter = _require(results, "london_filter_present", None)
        if london_filter is True:
            return CheckResult("london_session_filter", CHECK_PASS,
                               "London session filter present (08:00–13:00 UTC).")
        if london_filter is False:
            return CheckResult("london_session_filter", CHECK_WARN,
                               "London session filter NOT present. Strategy trades outside London session. "
                               "Higher spread and lower liquidity outside this window increases costs.")
        return CheckResult("london_session_filter", CHECK_WARN,
                           "london_filter_present not specified. Verify session filtering in code.")

    # -----------------------------------------------------------------------
    # SECTION 8: OOS VALIDATION (for LIVE-READY upgrade)
    # -----------------------------------------------------------------------

    def check_oos_validation(self, results: Dict) -> CheckResult:
        """
        Out-of-sample validation: LIVE-READY requires >= 3 months of OOS data.
        This check is WARN-level (not mandatory reject), but gates LIVE-READY verdict.
        """
        oos_months = _require(results, "oos_months", 0)
        if oos_months >= 3:
            return CheckResult("oos_validation", CHECK_PASS,
                               f"Out-of-sample validation: {oos_months} months (minimum 3 for LIVE-READY).",
                               oos_months)
        if oos_months > 0:
            return CheckResult("oos_validation", CHECK_WARN,
                               f"Only {oos_months} months of OOS validation (need 3 for LIVE-READY). "
                               "Continue forward testing.",
                               oos_months)
        return CheckResult("oos_validation", CHECK_WARN,
                           "No out-of-sample validation completed. "
                           "Strategy is at most FORWARD-TEST READY until OOS data is available.",
                           0)

    # -----------------------------------------------------------------------
    # MASTER RUNNER
    # -----------------------------------------------------------------------

    def run_all_checks(self, strategy_results: dict) -> QAReport:
        """
        Run every mandatory check in sequence.

        Parameters
        ----------
        strategy_results : dict
            See module docstring for full key schema.

        Returns
        -------
        QAReport
            Contains all CheckResult objects and final verdict.
        """
        name = _require(strategy_results, "strategy_name", "UNKNOWN")
        symbol = _require(strategy_results, "symbol", "UNKNOWN")
        start = str(_require(strategy_results, "backtest_start", "N/A"))
        end = str(_require(strategy_results, "backtest_end", "N/A"))

        report = QAReport(
            strategy_name=name,
            symbol=symbol,
            backtest_start=start,
            backtest_end=end,
        )

        # --- SECTION 1: Technical Quality ---
        report.checks.append(self.check_no_repainting_declared(strategy_results))
        report.checks.append(self.check_no_lookahead_bias(strategy_results))
        report.checks.append(self.check_confirmed_bars_only(strategy_results))

        # --- SECTION 2: Cost Realism ---
        report.checks.append(self.check_spread_included(strategy_results))
        report.checks.append(self.check_commission_included(strategy_results))
        report.checks.append(self.check_slippage_included(strategy_results))
        report.checks.append(self.check_cost_documentation(strategy_results))

        # --- SECTION 3: Statistical Validity ---
        report.checks.append(self.check_min_trades_per_month(strategy_results))
        report.checks.append(self.check_monthly_profit_concentration(strategy_results))
        report.checks.append(self.check_minimum_backtest_duration(strategy_results))
        report.checks.append(self.check_win_rate_plausible(strategy_results))
        report.checks.append(self.check_profit_factor_gt_1_2(strategy_results))

        # --- SECTION 4: Monthly Breakdown ---
        report.checks.append(self.check_monthly_pnl_table_exists(strategy_results))
        report.checks.append(self.check_monthly_trade_count_table_exists(strategy_results))
        report.checks.append(self.check_no_zero_trade_months(strategy_results))
        report.checks.append(self.check_best_worst_month_identified(strategy_results))

        # --- SECTION 5: Benchmark Comparison ---
        report.checks.append(self.check_vs_buy_and_hold(strategy_results))
        report.checks.append(self.check_vs_lrb_benchmark(strategy_results))

        # --- SECTION 6: Risk Checks ---
        report.checks.append(self.check_max_drawdown_documented(strategy_results))
        report.checks.append(self.check_max_consecutive_losses(strategy_results))
        report.checks.append(self.check_kill_switch_defined(strategy_results))
        report.checks.append(self.check_no_martingale_or_grid(strategy_results))
        report.checks.append(self.check_fixed_lot_size(strategy_results))

        # --- SECTION 7: Execution Feasibility ---
        report.checks.append(self.check_entry_achievable_market_orders(strategy_results))
        report.checks.append(self.check_stop_loss_at_order_time(strategy_results))
        report.checks.append(self.check_slippage_model_matches_broker(strategy_results))
        report.checks.append(self.check_london_session_filter(strategy_results))

        # --- SECTION 8: OOS Validation (gates LIVE-READY) ---
        report.checks.append(self.check_oos_validation(strategy_results))

        return report


# ---------------------------------------------------------------------------
# CLI entry point (for quick standalone runs)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    print("QAValidator — EMPIREX-OS")
    print("Usage: from qa_validator import QAValidator")
    print("       report = QAValidator().run_all_checks(strategy_results_dict)")
    print("       print(report.summary())")
    print()
    print("Run with demo data? Pass --demo as argument.")

    if "--demo" in sys.argv:
        # Minimal demo to show structure
        demo_trades = pd.DataFrame({
            "entry_time": pd.date_range("2025-01-02", periods=200, freq="1D", tz="UTC"),
            "exit_time":  pd.date_range("2025-01-03", periods=200, freq="1D", tz="UTC"),
            "pnl_net":    np.random.normal(50, 200, 200),
            "is_winner":  np.random.choice([True, False], 200, p=[0.45, 0.55]),
        })

        demo_results = {
            "strategy_name":      "DEMO-LRB",
            "symbol":             "EURUSD",
            "backtest_start":     "2025-01-01",
            "backtest_end":       "2025-12-31",
            "trades":             demo_trades,
            "equity_curve":       pd.Series(10000 + demo_trades["pnl_net"].cumsum().values),
            "initial_capital":    10000.0,
            "final_equity":       10000 + float(demo_trades["pnl_net"].sum()),
            "spread_included":    True,
            "commission_included": True,
            "slippage_included":  True,
            "cost_per_trade_usd": 20.0,
            "broker_spread_pips": 1.5,
            "broker_commission":  7.0,
            "broker_slippage_pips": 0.5,
            "london_filter_present": True,
            "stop_at_order_time": True,
            "uses_martingale":    False,
            "uses_grid":          False,
            "uses_averaging_down": False,
            "fixed_lot_size":     True,
            "entry_market_order": True,
            "slippage_model":     "ecn",
            "broker_type":        "ecn",
            "kill_switch_defined": True,
            "oos_months":         0,
            "no_repainting_declared": True,
            "no_lookahead_bias_declared": True,
            "engine_type":        "backtest_engine_v1",
        }

        v = QAValidator()
        r = v.run_all_checks(demo_results)
        print(r.summary())
        print()
        print(json.dumps(r.to_dict(), indent=2, default=str))
