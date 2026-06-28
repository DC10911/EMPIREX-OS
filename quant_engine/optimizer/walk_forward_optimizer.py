"""
Walk-Forward Optimizer
======================
Finds robust strategy parameters for LRB and EMP Session Momentum strategies
using a rolling walk-forward methodology to prevent in-sample overfitting.

Python 3.10+ | Dependencies: pandas, numpy, itertools only
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator, Literal

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Compatibility shim so this module can run standalone OR with the real engine
# ---------------------------------------------------------------------------
_ENGINE_PATH = Path(__file__).resolve().parents[1] / "python_backtest"
if str(_ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(_ENGINE_PATH))

try:
    from backtest_engine import BacktestEngine  # type: ignore[import]
except ImportError:  # pragma: no cover – stub used when engine not present
    class BacktestEngine:  # type: ignore[no-redef]
        """
        Minimal stub so the optimizer can be imported and unit-tested
        without the full backtest engine installed.

        Replace this class with the real implementation once
        python_backtest/backtest_engine.py exists.

        Expected real interface
        -----------------------
        engine = BacktestEngine(strategy="LRB" | "EMP", params=dict)
        results = engine.run(ohlcv_df: pd.DataFrame)
        # results is a dict with at minimum:
        #   trades      -> list[dict] each with keys: entry_dt, exit_dt, pnl
        #   equity_curve -> list[float]
        #   sharpe       -> float
        #   profit_factor -> float
        #   win_rate      -> float  (0-1)
        #   max_drawdown  -> float  (0-1, positive number)
        #   total_return  -> float
        """

        def __init__(self, strategy: str, params: dict[str, Any]) -> None:
            self.strategy = strategy
            self.params = params

        def run(self, ohlcv_df: pd.DataFrame) -> dict[str, Any]:
            """
            Stub: generates synthetic results that scale weakly with param
            values so the optimizer has something to optimise against.
            In production, replace with the real backtest calculation.
            """
            rng = np.random.default_rng(
                seed=abs(hash(json.dumps(self.params, sort_keys=True, default=str))) % (2**31)
            )
            n_bars = len(ohlcv_df)
            n_trades = max(0, int(n_bars / 20 + rng.normal(0, 3)))
            if n_trades == 0:
                return _empty_results()

            pnls = rng.normal(loc=0.002, scale=0.012, size=n_trades)
            equity = np.cumprod(1 + pnls)
            peak = np.maximum.accumulate(equity)
            drawdowns = (peak - equity) / peak
            wins = (pnls > 0).sum()

            sharpe = _compute_sharpe(pnls)
            pf = (pnls[pnls > 0].sum() / abs(pnls[pnls < 0].sum())
                  if (pnls < 0).any() else float("inf"))

            trades = []
            base_dt = ohlcv_df.index[0] if hasattr(ohlcv_df.index[0], "hour") else datetime(2020, 1, 1)
            for i, p in enumerate(pnls):
                entry = base_dt + timedelta(hours=i * 8)
                trades.append({
                    "entry_dt": entry,
                    "exit_dt": entry + timedelta(hours=4),
                    "pnl": float(p),
                })

            return {
                "trades": trades,
                "equity_curve": equity.tolist(),
                "sharpe": float(sharpe),
                "profit_factor": float(pf),
                "win_rate": float(wins / n_trades),
                "max_drawdown": float(drawdowns.max()),
                "total_return": float(equity[-1] - 1),
            }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_results() -> dict[str, Any]:
    return {
        "trades": [],
        "equity_curve": [],
        "sharpe": float("-inf"),
        "profit_factor": 0.0,
        "win_rate": 0.0,
        "max_drawdown": 1.0,
        "total_return": -1.0,
    }


def _compute_sharpe(pnls: np.ndarray, risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    """Annualised Sharpe ratio from a 1-D array of per-trade P&L fractions."""
    if len(pnls) < 2:
        return float("-inf")
    excess = pnls - risk_free / periods_per_year
    std = excess.std(ddof=1)
    if std == 0:
        return float("-inf")
    return float(excess.mean() / std * math.sqrt(periods_per_year))


def _monthly_profits(trades: list[dict[str, Any]]) -> dict[str, float]:
    """Return {YYYY-MM: total_pnl} for all trades."""
    buckets: dict[str, float] = {}
    for t in trades:
        dt = t["entry_dt"]
        key = f"{dt.year}-{dt.month:02d}" if isinstance(dt, datetime) else str(dt)[:7]
        buckets[key] = buckets.get(key, 0.0) + t["pnl"]
    return buckets


def _concentration_risk(trades: list[dict[str, Any]]) -> float:
    """
    Fraction of total profit attributable to the single best month.
    Returns 0.0 if total profit <= 0 (concentration is not meaningful).
    """
    monthly = _monthly_profits(trades)
    if not monthly:
        return 1.0
    total = sum(monthly.values())
    if total <= 0:
        return 1.0
    best_month = max(monthly.values())
    return best_month / total


# ---------------------------------------------------------------------------
# Parameter grid builders
# ---------------------------------------------------------------------------

def _frange(start: float, stop: float, step: float) -> list[float]:
    """Inclusive float range with rounding to avoid float drift."""
    result: list[float] = []
    val = start
    while val <= stop + 1e-9:
        result.append(round(val, 10))
        val = round(val + step, 10)
    return result


def _irange(start: int, stop: int, step: int = 1) -> list[int]:
    return list(range(start, stop + 1, step))


LRB_GRID: dict[str, list] = {
    "pre_session_start": _frange(5.0, 7.0, 0.5),   # UTC hours
    "pre_session_end":   _frange(7.5, 8.5, 0.5),
    "tp_multiplier":     _frange(1.0, 3.0, 0.25),
    "sl_from_opposite":  [True, False],
    "time_exit_hour":    _irange(12, 15, 1),         # UTC hours
}

EMP_GRID: dict[str, list] = {
    "atr_period":     _irange(10, 21, 1),
    "atr_band_mult":  _frange(0.8, 2.0, 0.2),
    "rsi_period":     _irange(10, 21, 1),
    "rsi_threshold":  _irange(45, 55, 1),
    "sl_atr_mult":    _frange(1.0, 2.5, 0.25),
    "tp_atr_mult":    _frange(1.5, 4.0, 0.25),
}

STRATEGY_GRIDS: dict[str, dict[str, list]] = {
    "LRB": LRB_GRID,
    "EMP": EMP_GRID,
}

# Boundary values per param (for boundary-flag detection)
_GRID_BOUNDS: dict[str, dict[str, tuple]] = {
    "LRB": {
        "pre_session_start": (5.0, 7.0),
        "pre_session_end":   (7.5, 8.5),
        "tp_multiplier":     (1.0, 3.0),
        "time_exit_hour":    (12, 15),
    },
    "EMP": {
        "atr_period":    (10, 21),
        "atr_band_mult": (0.8, 2.0),
        "rsi_period":    (10, 21),
        "rsi_threshold": (45, 55),
        "sl_atr_mult":   (1.0, 2.5),
        "tp_atr_mult":   (1.5, 4.0),
    },
}


def _is_boundary(strategy: str, params: dict[str, Any]) -> list[str]:
    """Return list of param names that sit on the boundary of the search space."""
    flags: list[str] = []
    bounds = _GRID_BOUNDS.get(strategy, {})
    for key, (lo, hi) in bounds.items():
        val = params.get(key)
        if val is None:
            continue
        if abs(float(val) - float(lo)) < 1e-9 or abs(float(val) - float(hi)) < 1e-9:
            flags.append(key)
    return flags


def _grid_combos(grid: dict[str, list]) -> Generator[dict[str, Any], None, None]:
    """Yield every combination in the parameter grid."""
    keys = list(grid.keys())
    for combo in itertools.product(*[grid[k] for k in keys]):
        yield dict(zip(keys, combo))


# ---------------------------------------------------------------------------
# Data slicing helpers
# ---------------------------------------------------------------------------

def _slice_window(
    df: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Return rows where index is in [start, end)."""
    mask = (df.index >= start) & (df.index < end)
    return df.loc[mask]


def _walk_forward_windows(
    df: pd.DataFrame,
    train_months: int = 3,
    test_months: int = 1,
) -> Generator[tuple[pd.DataFrame, pd.DataFrame, datetime, datetime], None, None]:
    """
    Yield (train_df, test_df, test_start, test_end) rolling windows.

    The walk advances one test_months step each iteration.
    """
    if df.empty:
        return

    idx_min: datetime = df.index.min().to_pydatetime()  # type: ignore[attr-defined]
    idx_max: datetime = df.index.max().to_pydatetime()  # type: ignore[attr-defined]

    # Align to start of month
    window_start = idx_min.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    while True:
        # Training window
        train_end_month = window_start.month + train_months
        train_end_year  = window_start.year + (train_end_month - 1) // 12
        train_end_month = (train_end_month - 1) % 12 + 1
        train_end = datetime(train_end_year, train_end_month, 1)

        # Test window
        test_end_month = train_end_month + test_months
        test_end_year  = train_end_year + (test_end_month - 1) // 12
        test_end_month = (test_end_month - 1) % 12 + 1
        test_end = datetime(test_end_year, test_end_month, 1)

        if test_end > idx_max + timedelta(days=32):
            break

        train_df = _slice_window(df, window_start, train_end)
        test_df  = _slice_window(df, train_end, test_end)

        if not train_df.empty and not test_df.empty:
            yield train_df, test_df, train_end, test_end

        # Advance by one test period
        next_month = window_start.month + test_months
        next_year  = window_start.year + (next_month - 1) // 12
        next_month = (next_month - 1) % 12 + 1
        window_start = datetime(next_year, next_month, 1)


# ---------------------------------------------------------------------------
# Anti-overfitting checks (applied inline during optimisation)
# ---------------------------------------------------------------------------

@dataclass
class AntiOverfitResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def _anti_overfit_checks(
    is_metrics: dict[str, Any],
    oos_metrics: dict[str, Any],
    is_trades: list[dict],
    oos_trades: list[dict],
    min_oos_sharpe: float = 0.5,
    min_trades_per_window: int = 20,
    overfit_winrate_gap: float = 0.35,   # IS win% - OOS win% threshold
    max_concentration: float = 0.40,
) -> AntiOverfitResult:
    """
    Run all anti-overfitting checks.  Returns AntiOverfitResult.

    Rule 1  – Win-rate collapse:   IS win% > 80% AND OOS win% < 45%
    Rule 2  – Min OOS Sharpe:      OOS Sharpe < 0.5
    Rule 3  – Concentration risk:  best month > 40% of total OOS profit
    Rule 4  – Minimum trade count: < 20 trades in OOS window
    Rule 5  – Boundary flag:       checked externally, recorded in WFResult
    """
    reasons: list[str] = []

    is_wr  = is_metrics.get("win_rate", 0.0)
    oos_wr = oos_metrics.get("win_rate", 0.0)
    oos_sh = oos_metrics.get("sharpe", float("-inf"))
    n_oos  = len(oos_trades)

    # Rule 1
    if is_wr > 0.80 and oos_wr < 0.45:
        reasons.append(
            f"RULE1_OVERFIT_FLAG: IS win-rate={is_wr:.1%} > 80% but "
            f"OOS win-rate={oos_wr:.1%} < 45%"
        )

    # Rule 2
    if oos_sh < min_oos_sharpe:
        reasons.append(
            f"RULE2_LOW_OOS_SHARPE: OOS Sharpe={oos_sh:.3f} < {min_oos_sharpe}"
        )

    # Rule 3
    conc = _concentration_risk(oos_trades)
    if conc > max_concentration:
        reasons.append(
            f"RULE3_CONCENTRATION: best OOS month = {conc:.1%} of total profit "
            f"(threshold {max_concentration:.0%})"
        )

    # Rule 4
    if n_oos < min_trades_per_window:
        reasons.append(
            f"RULE4_TOO_FEW_TRADES: only {n_oos} trades in OOS window "
            f"(minimum {min_trades_per_window})"
        )

    return AntiOverfitResult(passed=len(reasons) == 0, reasons=reasons)


# ---------------------------------------------------------------------------
# Walk-forward result data class
# ---------------------------------------------------------------------------

@dataclass
class WFWindowResult:
    """Result for a single walk-forward window."""
    test_start: str
    test_end: str
    params: dict[str, Any]
    is_sharpe: float
    is_win_rate: float
    is_profit_factor: float
    is_max_drawdown: float
    is_trade_count: int
    oos_sharpe: float
    oos_win_rate: float
    oos_profit_factor: float
    oos_max_drawdown: float
    oos_trade_count: int
    oos_total_return: float
    efficiency_ratio: float          # OOS Sharpe / IS Sharpe (robustness measure)
    passed_anti_overfit: bool
    overfit_reasons: list[str]
    boundary_params: list[str]
    rank_percentile_is: float = 0.0  # set after all combos scored in window
    rank_percentile_oos: float = 0.0


@dataclass
class WFOptimizationResult:
    """Aggregated result across all walk-forward windows for one strategy."""
    strategy: str
    windows: list[WFWindowResult] = field(default_factory=list)
    recommended_params: dict[str, Any] = field(default_factory=dict)
    avg_efficiency_ratio: float = 0.0
    avg_oos_sharpe: float = 0.0
    param_stability_summary: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core optimizer
# ---------------------------------------------------------------------------

class WalkForwardOptimizer:
    """
    Rolling walk-forward optimiser for LRB and EMP strategies.

    Usage
    -----
    opt = WalkForwardOptimizer(strategy="LRB", train_months=3, test_months=1)
    result = opt.optimize(ohlcv_df)
    opt.save_results(result, "lrb_wfo_results.csv")

    Parameters
    ----------
    strategy        : "LRB" or "EMP"
    train_months    : in-sample window length (default 3)
    test_months     : out-of-sample window length (default 1)
    top_pct         : top fraction of IS combos evaluated on OOS (default 0.40)
    min_oos_sharpe  : minimum acceptable OOS Sharpe (default 0.5)
    min_trades      : minimum OOS trades required (default 20)
    verbose         : print progress (default True)
    param_grid      : override default grid (optional)
    """

    def __init__(
        self,
        strategy: Literal["LRB", "EMP"],
        train_months: int = 3,
        test_months: int = 1,
        top_pct: float = 0.40,
        min_oos_sharpe: float = 0.5,
        min_trades: int = 20,
        verbose: bool = True,
        param_grid: dict[str, list] | None = None,
    ) -> None:
        if strategy not in STRATEGY_GRIDS:
            raise ValueError(f"Unknown strategy '{strategy}'. Choose from {list(STRATEGY_GRIDS)}")
        self.strategy = strategy
        self.train_months = train_months
        self.test_months = test_months
        self.top_pct = top_pct
        self.min_oos_sharpe = min_oos_sharpe
        self.min_trades = min_trades
        self.verbose = verbose
        self.grid = param_grid if param_grid is not None else STRATEGY_GRIDS[strategy]

        # Pre-materialise grid so we can show progress
        self._all_combos: list[dict[str, Any]] = list(_grid_combos(self.grid))
        self._n_combos = len(self._all_combos)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(self, ohlcv_df: pd.DataFrame) -> WFOptimizationResult:
        """
        Run the full walk-forward optimisation.

        Parameters
        ----------
        ohlcv_df : pd.DataFrame with DatetimeIndex and at minimum columns:
                   [open, high, low, close, volume]

        Returns
        -------
        WFOptimizationResult
        """
        self._log(
            f"Starting Walk-Forward Optimisation | strategy={self.strategy} "
            f"| {self._n_combos:,} parameter combos "
            f"| train={self.train_months}m  test={self.test_months}m"
        )

        all_window_results: list[WFWindowResult] = []

        windows = list(_walk_forward_windows(ohlcv_df, self.train_months, self.test_months))
        if not windows:
            raise ValueError(
                "Insufficient data to create even one walk-forward window. "
                f"Need at least {self.train_months + self.test_months} months of data."
            )

        for w_idx, (train_df, test_df, test_start, test_end) in enumerate(windows):
            self._log(
                f"\n--- Window {w_idx + 1}/{len(windows)} | "
                f"IS={train_df.index[0].date()}→{train_df.index[-1].date()} | "
                f"OOS={test_df.index[0].date()}→{test_df.index[-1].date()} ---"
            )

            window_results = self._run_window(train_df, test_df, test_start, test_end)
            all_window_results.extend(window_results)

        result = self._aggregate(all_window_results)
        self._log(
            f"\nOptimisation complete. "
            f"Avg OOS Sharpe={result.avg_oos_sharpe:.3f} | "
            f"Avg Efficiency Ratio={result.avg_efficiency_ratio:.3f}"
        )
        return result

    def save_results(
        self,
        result: WFOptimizationResult,
        output_path: str | Path,
    ) -> Path:
        """
        Save all walk-forward window results to a CSV file.

        Returns the resolved output path.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rows: list[dict[str, Any]] = []
        for w in result.windows:
            row: dict[str, Any] = {
                "strategy": result.strategy,
                "test_start": w.test_start,
                "test_end": w.test_end,
                "is_sharpe": round(w.is_sharpe, 4),
                "is_win_rate": round(w.is_win_rate, 4),
                "is_profit_factor": round(w.is_profit_factor, 4),
                "is_max_drawdown": round(w.is_max_drawdown, 4),
                "is_trade_count": w.is_trade_count,
                "oos_sharpe": round(w.oos_sharpe, 4),
                "oos_win_rate": round(w.oos_win_rate, 4),
                "oos_profit_factor": round(w.oos_profit_factor, 4),
                "oos_max_drawdown": round(w.oos_max_drawdown, 4),
                "oos_trade_count": w.oos_trade_count,
                "oos_total_return": round(w.oos_total_return, 4),
                "efficiency_ratio": round(w.efficiency_ratio, 4),
                "passed_anti_overfit": w.passed_anti_overfit,
                "overfit_reasons": " | ".join(w.overfit_reasons),
                "boundary_params": ", ".join(w.boundary_params),
                "rank_percentile_is": round(w.rank_percentile_is, 4),
                "rank_percentile_oos": round(w.rank_percentile_oos, 4),
            }
            # Flatten params
            for k, v in w.params.items():
                row[f"param_{k}"] = v
            rows.append(row)

        if rows:
            keys = list(rows[0].keys())
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(rows)

        # Also save recommended params as JSON
        json_path = output_path.with_suffix(".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "strategy": result.strategy,
                    "recommended_params": result.recommended_params,
                    "avg_oos_sharpe": round(result.avg_oos_sharpe, 4),
                    "avg_efficiency_ratio": round(result.avg_efficiency_ratio, 4),
                    "param_stability_summary": result.param_stability_summary,
                },
                f,
                indent=2,
                default=str,
            )

        self._log(f"Results saved → {output_path}  |  {json_path}")
        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_window(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        test_start: datetime,
        test_end: datetime,
    ) -> list[WFWindowResult]:
        """
        1. Score every param combo on the IS (training) window.
        2. Select top top_pct% by IS Sharpe.
        3. Score those combos on OOS (test) window.
        4. Apply anti-overfitting checks.
        5. Return WFWindowResult list (all that reached OOS evaluation).
        """
        # ---- Step 1: IS scoring -------------------------------------------
        is_scores: list[tuple[float, dict, dict, list[dict]]] = []
        for idx, params in enumerate(self._all_combos):
            if self.verbose and idx % max(1, self._n_combos // 10) == 0:
                pct = 100 * idx / self._n_combos
                print(f"  IS scoring: {pct:5.1f}%  ({idx:,}/{self._n_combos:,})", end="\r")

            engine = BacktestEngine(strategy=self.strategy, params=params)
            res = engine.run(train_df)
            is_scores.append((res["sharpe"], params, res, res["trades"]))

        if self.verbose:
            print()  # newline after \r

        # ---- Step 2: rank and select top combos ---------------------------
        is_scores.sort(key=lambda x: x[0], reverse=True)

        # Compute IS percentile rank for all combos
        is_sharpes_all = [s[0] for s in is_scores]
        n_select = max(1, int(len(is_scores) * self.top_pct))
        top_combos = is_scores[:n_select]

        self._log(
            f"  IS scoring done. Top {self.top_pct:.0%} = {n_select:,} combos "
            f"selected for OOS eval. Best IS Sharpe={is_scores[0][0]:.3f}"
        )

        # ---- Step 3: OOS scoring ------------------------------------------
        window_results: list[WFWindowResult] = []

        oos_sharpes: list[float] = []
        oos_raw: list[tuple[float, dict, dict, list[dict], float]] = []  # (oos_sh, params, oos_res, is_metrics, is_sh)

        for is_sharpe, params, is_res, is_trades in top_combos:
            engine = BacktestEngine(strategy=self.strategy, params=params)
            oos_res = engine.run(test_df)
            oos_sharpes.append(oos_res["sharpe"])
            oos_raw.append((oos_res["sharpe"], params, oos_res, is_res, is_sharpe))

        # ---- Step 4: build results with percentile ranks ------------------
        oos_sharpes_arr = np.array(oos_sharpes)

        for oos_sh, params, oos_res, is_res, is_sh in oos_raw:
            # Percentile rank within IS universe
            is_rank_pct = float(
                np.searchsorted(np.sort(is_sharpes_all), is_sh) / len(is_sharpes_all)
            )
            # Percentile rank within OOS evaluated set
            oos_rank_pct = float(
                np.searchsorted(np.sort(oos_sharpes_arr), oos_sh) / len(oos_sharpes_arr)
            )

            # Efficiency ratio: OOS Sharpe / IS Sharpe
            if is_sh > 0 and not math.isnan(is_sh) and not math.isinf(is_sh):
                eff_ratio = oos_sh / is_sh if is_sh != 0 else float("-inf")
            else:
                eff_ratio = float("-inf")

            # Anti-overfit checks
            ao = _anti_overfit_checks(
                is_metrics=is_res,
                oos_metrics=oos_res,
                is_trades=is_res["trades"],
                oos_trades=oos_res["trades"],
                min_oos_sharpe=self.min_oos_sharpe,
                min_trades_per_window=self.min_trades,
            )

            # Boundary flag (Rule 5)
            boundary = _is_boundary(self.strategy, params)

            wr = WFWindowResult(
                test_start=test_start.strftime("%Y-%m-%d"),
                test_end=test_end.strftime("%Y-%m-%d"),
                params=params.copy(),
                is_sharpe=is_sh,
                is_win_rate=is_res["win_rate"],
                is_profit_factor=is_res["profit_factor"],
                is_max_drawdown=is_res["max_drawdown"],
                is_trade_count=len(is_res["trades"]),
                oos_sharpe=oos_sh,
                oos_win_rate=oos_res["win_rate"],
                oos_profit_factor=oos_res["profit_factor"],
                oos_max_drawdown=oos_res["max_drawdown"],
                oos_trade_count=len(oos_res["trades"]),
                oos_total_return=oos_res["total_return"],
                efficiency_ratio=eff_ratio,
                passed_anti_overfit=ao.passed and not boundary,
                overfit_reasons=ao.reasons
                + ([f"RULE5_BOUNDARY: {', '.join(boundary)}"] if boundary else []),
                boundary_params=boundary,
                rank_percentile_is=is_rank_pct,
                rank_percentile_oos=oos_rank_pct,
            )
            window_results.append(wr)

        passed = [w for w in window_results if w.passed_anti_overfit]
        self._log(
            f"  OOS scoring done. {len(passed)}/{len(window_results)} combos "
            f"passed anti-overfit checks."
        )
        return window_results

    def _aggregate(self, all_results: list[WFWindowResult]) -> WFOptimizationResult:
        """
        Aggregate across windows, derive recommended params and efficiency stats.

        Recommended params = median of the top-ranked, passed params across all
        windows (frequency-weighted for categorical params).
        """
        passed = [r for r in all_results if r.passed_anti_overfit]

        avg_oos_sharpe = float(np.mean([r.oos_sharpe for r in all_results])) if all_results else 0.0
        eff_ratios = [r.efficiency_ratio for r in all_results
                      if not math.isinf(r.efficiency_ratio) and not math.isnan(r.efficiency_ratio)]
        avg_eff = float(np.mean(eff_ratios)) if eff_ratios else 0.0

        # Recommend params from passed windows (or all if none passed)
        pool = passed if passed else all_results
        recommended = self._derive_recommended_params(pool)
        stability = self._param_stability_summary(pool)

        return WFOptimizationResult(
            strategy=self.strategy,
            windows=all_results,
            recommended_params=recommended,
            avg_efficiency_ratio=avg_eff,
            avg_oos_sharpe=avg_oos_sharpe,
            param_stability_summary=stability,
        )

    def _derive_recommended_params(
        self, results: list[WFWindowResult]
    ) -> dict[str, Any]:
        """
        For numeric params: use the median of selected param values.
        For boolean/categorical params: use the mode.
        Weight each result by its OOS Sharpe (only positive contributions).
        """
        if not results:
            return {}

        param_keys = list(results[0].params.keys())
        recommended: dict[str, Any] = {}

        for key in param_keys:
            values = [r.params[key] for r in results]
            sample = values[0]

            if isinstance(sample, bool):
                true_count = sum(1 for v in values if v)
                recommended[key] = true_count >= len(values) / 2
            elif isinstance(sample, (int, float)):
                recommended[key] = _round_to_grid(
                    float(np.median([float(v) for v in values])),
                    self.grid.get(key, [sample]),
                )
            else:
                from collections import Counter
                recommended[key] = Counter(values).most_common(1)[0][0]

        return recommended

    def _param_stability_summary(
        self, results: list[WFWindowResult]
    ) -> dict[str, Any]:
        """
        For each numeric param: compute std dev of selected values across windows.
        A high std dev relative to grid range indicates instability.
        """
        if not results:
            return {}

        param_keys = list(results[0].params.keys())
        summary: dict[str, Any] = {}

        for key in param_keys:
            values = [r.params[key] for r in results]
            sample = values[0]
            if isinstance(sample, bool):
                true_frac = sum(1 for v in values if v) / len(values)
                summary[key] = {"type": "bool", "true_fraction": round(true_frac, 3)}
            elif isinstance(sample, (int, float)):
                fvals = [float(v) for v in values]
                grid_vals = self.grid.get(key, fvals)
                grid_range = max(grid_vals) - min(grid_vals) if len(grid_vals) > 1 else 1.0
                std = float(np.std(fvals, ddof=1)) if len(fvals) > 1 else 0.0
                summary[key] = {
                    "type": "numeric",
                    "mean": round(float(np.mean(fvals)), 4),
                    "std": round(std, 4),
                    "cv": round(std / grid_range, 4),  # coefficient of variation vs grid range
                    "stable": std / grid_range < 0.25,  # stable if CV < 25% of grid range
                }

        return summary

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)


# ---------------------------------------------------------------------------
# Utility: snap a median value to nearest grid point
# ---------------------------------------------------------------------------

def _round_to_grid(value: float, grid_values: list) -> Any:
    """Return the grid value closest to `value`."""
    numeric = [v for v in grid_values if isinstance(v, (int, float))]
    if not numeric:
        return value
    return min(numeric, key=lambda g: abs(g - value))


# ---------------------------------------------------------------------------
# Convenience runner (single-strategy, no data dependency)
# ---------------------------------------------------------------------------

def run_optimization(
    strategy: Literal["LRB", "EMP"],
    ohlcv_df: pd.DataFrame,
    output_dir: str | Path = ".",
    train_months: int = 3,
    test_months: int = 1,
    top_pct: float = 0.40,
    verbose: bool = True,
) -> WFOptimizationResult:
    """
    End-to-end walk-forward optimisation with automatic CSV/JSON saving.

    Parameters
    ----------
    strategy    : "LRB" or "EMP"
    ohlcv_df    : price data with DatetimeIndex
    output_dir  : directory to save CSV/JSON results
    train_months: IS window length in months
    test_months : OOS window length in months
    top_pct     : fraction of IS combos taken to OOS evaluation
    verbose     : print progress

    Returns
    -------
    WFOptimizationResult
    """
    opt = WalkForwardOptimizer(
        strategy=strategy,
        train_months=train_months,
        test_months=test_months,
        top_pct=top_pct,
        verbose=verbose,
    )
    result = opt.optimize(ohlcv_df)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_name = f"{strategy.lower()}_walk_forward_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    opt.save_results(result, output_dir / csv_name)
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Walk-Forward Optimizer")
    parser.add_argument("--strategy", choices=["LRB", "EMP"], required=True)
    parser.add_argument("--data", type=str, required=True, help="Path to OHLCV CSV")
    parser.add_argument("--output-dir", type=str, default="./wfo_results")
    parser.add_argument("--train-months", type=int, default=3)
    parser.add_argument("--test-months", type=int, default=1)
    parser.add_argument("--top-pct", type=float, default=0.40)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    df = pd.read_csv(args.data, index_col=0, parse_dates=True)
    result = run_optimization(
        strategy=args.strategy,
        ohlcv_df=df,
        output_dir=args.output_dir,
        train_months=args.train_months,
        test_months=args.test_months,
        top_pct=args.top_pct,
        verbose=not args.quiet,
    )
    print(f"\nRecommended params for {args.strategy}:")
    for k, v in result.recommended_params.items():
        print(f"  {k}: {v}")
    print(f"\nAvg OOS Sharpe : {result.avg_oos_sharpe:.3f}")
    print(f"Avg Eff. Ratio : {result.avg_efficiency_ratio:.3f}")
