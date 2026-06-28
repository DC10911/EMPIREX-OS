"""
Overfitting Test Suite
======================
Statistical tests to validate that walk-forward optimised parameters are
genuinely robust and not artefacts of data mining.

Python 3.10+ | Dependencies: pandas, numpy only
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    name: str
    passed: bool
    value: float | None
    threshold: float | None
    detail: str
    raw: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        val_str = f"{self.value:.4f}" if self.value is not None else "N/A"
        thr_str = f"{self.threshold:.4f}" if self.threshold is not None else "N/A"
        return f"[{status}] {self.name}: value={val_str} | threshold={thr_str} | {self.detail}"


@dataclass
class OverfitTestSuite:
    strategy: str
    all_tests: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(t.passed for t in self.all_tests)

    @property
    def n_passed(self) -> int:
        return sum(1 for t in self.all_tests if t.passed)

    @property
    def n_failed(self) -> int:
        return sum(1 for t in self.all_tests if not t.passed)

    def summary(self) -> str:
        lines = [
            f"{'=' * 60}",
            f"OVERFITTING TEST SUITE — {self.strategy}",
            f"Overall: {'PASS' if self.passed else 'FAIL'} "
            f"({self.n_passed}/{len(self.all_tests)} tests passed)",
            f"{'=' * 60}",
        ]
        for t in self.all_tests:
            lines.append(str(t))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "overall_pass": self.passed,
            "n_passed": self.n_passed,
            "n_failed": self.n_failed,
            "tests": [
                {
                    "name": t.name,
                    "passed": t.passed,
                    "value": t.value,
                    "threshold": t.threshold,
                    "detail": t.detail,
                }
                for t in self.all_tests
            ],
        }


# ---------------------------------------------------------------------------
# Helper: equity curve from trade P&L list
# ---------------------------------------------------------------------------

def _equity_from_pnls(pnls: np.ndarray) -> np.ndarray:
    """Compound equity curve from fractional P&L array."""
    return np.cumprod(1.0 + pnls)


def _sharpe_from_pnls(pnls: np.ndarray, periods_per_year: int = 252) -> float:
    if len(pnls) < 2:
        return float("-inf")
    std = pnls.std(ddof=1)
    if std == 0:
        return 0.0
    return float(pnls.mean() / std * math.sqrt(periods_per_year))


def _max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 1.0
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak
    return float(dd.max())


def _sortino_ratio(pnls: np.ndarray, periods_per_year: int = 252) -> float:
    downside = pnls[pnls < 0]
    if len(downside) < 2:
        return float("inf")
    downside_std = downside.std(ddof=1)
    if downside_std == 0:
        return float("inf")
    return float(pnls.mean() / downside_std * math.sqrt(periods_per_year))


# ---------------------------------------------------------------------------
# Test 1: Monte Carlo Permutation Test
# ---------------------------------------------------------------------------

def monte_carlo_permutation_test(
    trades: list[dict[str, Any]],
    n_permutations: int = 1000,
    confidence: float = 0.95,
    metric: str = "sharpe",
    seed: int = 42,
) -> TestResult:
    """
    Shuffle trade P&L ordering n_permutations times. Check whether the real
    strategy's metric (Sharpe by default) beats >= confidence fraction of
    shuffled variants.

    Intuition: if the strategy has genuine edge, the real trade sequence should
    outperform most random orderings of the same trades. If it doesn't, the
    performance is likely driven by luck rather than alpha.

    Parameters
    ----------
    trades        : list of trade dicts, each with 'pnl' key (fractional)
    n_permutations: number of shuffled equity curves to generate
    confidence    : fraction of shuffled variants the real metric must beat
    metric        : "sharpe", "sortino", or "total_return"
    seed          : RNG seed for reproducibility

    Returns
    -------
    TestResult  (passed if real metric > confidence-th percentile of shuffled)
    """
    name = "Monte Carlo Permutation Test"

    if len(trades) < 10:
        return TestResult(
            name=name, passed=False,
            value=None, threshold=confidence,
            detail=f"Insufficient trades ({len(trades)}), need >= 10",
        )

    pnls = np.array([float(t["pnl"]) for t in trades])
    rng = np.random.default_rng(seed)

    def _metric(arr: np.ndarray) -> float:
        if metric == "sharpe":
            return _sharpe_from_pnls(arr)
        elif metric == "sortino":
            return _sortino_ratio(arr)
        else:  # total_return
            return float(_equity_from_pnls(arr)[-1] - 1)

    real_value = _metric(pnls)

    shuffled_values: list[float] = []
    for _ in range(n_permutations):
        perm = rng.permutation(pnls)
        shuffled_values.append(_metric(perm))

    shuffled_arr = np.array(shuffled_values)
    p_value = float((shuffled_arr >= real_value).mean())
    percentile_rank = float((shuffled_arr < real_value).mean())

    passed = percentile_rank >= confidence

    return TestResult(
        name=name,
        passed=passed,
        value=percentile_rank,
        threshold=confidence,
        detail=(
            f"Real {metric}={real_value:.4f} beats {percentile_rank:.1%} of "
            f"{n_permutations} shuffled curves (need >= {confidence:.1%}). "
            f"p-value={p_value:.4f}"
        ),
        raw={
            "real_metric": real_value,
            "shuffled_mean": float(shuffled_arr.mean()),
            "shuffled_p5": float(np.percentile(shuffled_arr, 5)),
            "shuffled_p95": float(np.percentile(shuffled_arr, 95)),
            "p_value": p_value,
            "n_permutations": n_permutations,
        },
    )


# ---------------------------------------------------------------------------
# Test 2: Parameter Stability Analysis
# ---------------------------------------------------------------------------

def parameter_stability_analysis(
    param_name: str,
    param_values: list,
    metric_values: list[float],
    boundary_lo: float | None = None,
    boundary_hi: float | None = None,
    stability_threshold: float = 0.25,
) -> TestResult:
    """
    Show how performance (Sharpe) varies as a single parameter changes while
    all others are held fixed. A stable parameter shows a broad plateau rather
    than a sharp spike.

    Passes if the performance plateau width (fraction of range where metric is
    within 20% of the peak) spans at least stability_threshold of the grid.

    Parameters
    ----------
    param_name          : name of the parameter being analysed
    param_values        : ordered list of parameter values tested
    metric_values       : corresponding metric (Sharpe) for each param value
    boundary_lo / hi    : boundary values of the search space
    stability_threshold : minimum plateau fraction (default 0.25 = 25% of range)

    Returns
    -------
    TestResult
    """
    name = f"Parameter Stability: {param_name}"

    if len(param_values) < 3:
        return TestResult(
            name=name, passed=False,
            value=None, threshold=stability_threshold,
            detail="Need at least 3 distinct values to assess stability",
        )

    vals = np.array([float(v) for v in param_values])
    metrics = np.array([float(m) for m in metric_values])

    peak = metrics.max()
    if peak <= 0:
        return TestResult(
            name=name, passed=False,
            value=0.0, threshold=stability_threshold,
            detail=f"Peak metric non-positive ({peak:.4f}), param adds no value",
        )

    # Plateau: metric within 20% of peak
    plateau_mask = metrics >= 0.80 * peak
    plateau_fraction = float(plateau_mask.mean())

    # Peak param value
    best_idx = int(metrics.argmax())
    best_val = float(vals[best_idx])

    # Boundary check
    at_boundary = False
    if boundary_lo is not None and abs(best_val - boundary_lo) < 1e-9:
        at_boundary = True
    if boundary_hi is not None and abs(best_val - boundary_hi) < 1e-9:
        at_boundary = True

    passed = plateau_fraction >= stability_threshold and not at_boundary

    # Sensitivity: slope magnitude (finite difference of metric w.r.t. param)
    if len(vals) > 1:
        slopes = np.diff(metrics) / np.diff(vals)
        max_slope = float(np.abs(slopes).max())
        mean_slope = float(np.abs(slopes).mean())
    else:
        max_slope = mean_slope = 0.0

    detail = (
        f"Plateau fraction={plateau_fraction:.1%} (need >= {stability_threshold:.1%}). "
        f"Best val={best_val} | peak metric={peak:.4f}. "
        f"{'AT SEARCH BOUNDARY — possible artifact. ' if at_boundary else ''}"
        f"Max sensitivity={max_slope:.4f}/unit"
    )

    return TestResult(
        name=name,
        passed=passed,
        value=plateau_fraction,
        threshold=stability_threshold,
        detail=detail,
        raw={
            "param_values": list(vals),
            "metric_values": list(metrics),
            "plateau_fraction": plateau_fraction,
            "best_val": best_val,
            "at_boundary": at_boundary,
            "max_slope": max_slope,
            "mean_slope": mean_slope,
        },
    )


def run_all_param_stability(
    param_grid: dict[str, list],
    param_metric_map: dict[str, tuple[list, list[float]]],
    grid_bounds: dict[str, tuple] | None = None,
    stability_threshold: float = 0.25,
) -> list[TestResult]:
    """
    Run parameter_stability_analysis for every param in the grid.

    Parameters
    ----------
    param_grid       : {param_name: [values]}
    param_metric_map : {param_name: ([values], [metric_values])}
                       — populated by varying one param while fixing others
    grid_bounds      : {param_name: (lo, hi)} optional
    stability_threshold: plateau fraction threshold

    Returns
    -------
    List of TestResult (one per parameter)
    """
    results: list[TestResult] = []
    bounds = grid_bounds or {}

    for param_name, (vals, metrics) in param_metric_map.items():
        lo, hi = bounds.get(param_name, (None, None))
        results.append(
            parameter_stability_analysis(
                param_name=param_name,
                param_values=vals,
                metric_values=metrics,
                boundary_lo=lo if lo is not None else None,
                boundary_hi=hi if hi is not None else None,
                stability_threshold=stability_threshold,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Test 3: Parameter-Performance Correlation Matrix
# ---------------------------------------------------------------------------

def parameter_correlation_matrix(
    results_df: pd.DataFrame,
    param_cols: list[str],
    metric_col: str = "oos_sharpe",
) -> tuple[pd.DataFrame, list[TestResult]]:
    """
    Compute Pearson correlation between each parameter and OOS performance.

    Flags parameters with |correlation| > 0.7 as potential overfitting
    indicators (too strong a linear relationship between a single param and
    outcome usually means curve-fitting).

    Parameters
    ----------
    results_df : DataFrame from walk_forward_optimizer CSV output
    param_cols : list of column names that are parameters
    metric_col : performance column to correlate against

    Returns
    -------
    (correlation_df, list[TestResult])
    """
    if results_df.empty or metric_col not in results_df.columns:
        return pd.DataFrame(), []

    # Convert bool params to int for correlation calculation
    work = results_df[param_cols + [metric_col]].copy()
    for col in param_cols:
        if work[col].dtype == object:
            work[col] = pd.Categorical(work[col]).codes
        elif work[col].dtype == bool:
            work[col] = work[col].astype(int)

    corr_rows: list[dict[str, Any]] = []
    test_results: list[TestResult] = []

    for pc in param_cols:
        if pc not in work.columns:
            continue
        col_data = pd.to_numeric(work[pc], errors="coerce")
        metric_data = pd.to_numeric(work[metric_col], errors="coerce")

        valid = col_data.notna() & metric_data.notna()
        if valid.sum() < 5:
            continue

        # Pearson correlation (manual to avoid scipy)
        x = col_data[valid].to_numpy(dtype=float)
        y = metric_data[valid].to_numpy(dtype=float)
        corr = _pearson_corr(x, y)

        corr_rows.append({"parameter": pc, "pearson_r": round(corr, 4)})

        # Flag strong correlations
        abs_corr = abs(corr)
        passed = abs_corr < 0.70
        test_results.append(
            TestResult(
                name=f"Param-Perf Correlation: {pc}",
                passed=passed,
                value=abs_corr,
                threshold=0.70,
                detail=(
                    f"|r|={abs_corr:.4f} with {metric_col}. "
                    f"{'HIGH — may indicate curve-fitting.' if not passed else 'Acceptable.'}"
                ),
                raw={"pearson_r": corr},
            )
        )

    corr_df = pd.DataFrame(corr_rows).set_index("parameter") if corr_rows else pd.DataFrame()
    return corr_df, test_results


def _pearson_corr(x: np.ndarray, y: np.ndarray) -> float:
    """Pure-numpy Pearson correlation coefficient."""
    if len(x) < 2:
        return 0.0
    xm = x - x.mean()
    ym = y - y.mean()
    denom = math.sqrt((xm ** 2).sum() * (ym ** 2).sum())
    if denom == 0:
        return 0.0
    return float((xm * ym).sum() / denom)


# ---------------------------------------------------------------------------
# Test 4: Efficiency Ratio Distribution
# ---------------------------------------------------------------------------

def efficiency_ratio_test(
    efficiency_ratios: list[float],
    min_median_er: float = 0.5,
    max_negative_fraction: float = 0.30,
) -> TestResult:
    """
    Analyse the distribution of efficiency ratios (OOS Sharpe / IS Sharpe)
    across all walk-forward windows.

    A healthy strategy should have:
    - Median efficiency ratio >= 0.5 (OOS retains at least 50% of IS edge)
    - No more than 30% of windows with negative efficiency ratio

    Parameters
    ----------
    efficiency_ratios      : list of window-level efficiency ratios
    min_median_er          : minimum acceptable median ER
    max_negative_fraction  : maximum allowed fraction of negative ERs
    """
    name = "Efficiency Ratio Distribution"
    valid = [e for e in efficiency_ratios if not math.isnan(e) and not math.isinf(e)]

    if len(valid) < 3:
        return TestResult(
            name=name, passed=False,
            value=None, threshold=min_median_er,
            detail=f"Too few valid efficiency ratios ({len(valid)}), need >= 3",
        )

    arr = np.array(valid)
    median_er = float(np.median(arr))
    neg_frac = float((arr < 0).mean())

    passed = median_er >= min_median_er and neg_frac <= max_negative_fraction

    return TestResult(
        name=name,
        passed=passed,
        value=median_er,
        threshold=min_median_er,
        detail=(
            f"Median ER={median_er:.4f} (need >= {min_median_er}). "
            f"Negative fraction={neg_frac:.1%} (max {max_negative_fraction:.1%}). "
            f"Mean={arr.mean():.4f}, p25={np.percentile(arr, 25):.4f}, "
            f"p75={np.percentile(arr, 75):.4f}"
        ),
        raw={
            "median": median_er,
            "mean": float(arr.mean()),
            "std": float(arr.std(ddof=1)),
            "negative_fraction": neg_frac,
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
        },
    )


# ---------------------------------------------------------------------------
# Test 5: Walk-Forward Consistency (OOS Sharpe across windows)
# ---------------------------------------------------------------------------

def walk_forward_consistency_test(
    oos_sharpes: list[float],
    min_positive_fraction: float = 0.60,
    min_mean_sharpe: float = 0.3,
) -> TestResult:
    """
    Check that the strategy produces positive OOS Sharpe ratios consistently
    across walk-forward windows.

    A robust strategy should:
    - Have positive Sharpe in >= 60% of OOS windows
    - Have mean OOS Sharpe >= 0.3 annualised

    Parameters
    ----------
    oos_sharpes            : Sharpe ratio for each OOS window
    min_positive_fraction  : minimum fraction of windows with positive Sharpe
    min_mean_sharpe        : minimum mean OOS Sharpe
    """
    name = "Walk-Forward OOS Consistency"
    valid = [s for s in oos_sharpes if not math.isnan(s) and not math.isinf(s)]

    if not valid:
        return TestResult(
            name=name, passed=False, value=None, threshold=min_positive_fraction,
            detail="No valid OOS Sharpe values found",
        )

    arr = np.array(valid)
    pos_frac = float((arr > 0).mean())
    mean_sh = float(arr.mean())

    passed = pos_frac >= min_positive_fraction and mean_sh >= min_mean_sharpe

    return TestResult(
        name=name,
        passed=passed,
        value=pos_frac,
        threshold=min_positive_fraction,
        detail=(
            f"Positive-OOS fraction={pos_frac:.1%} (need >= {min_positive_fraction:.1%}). "
            f"Mean OOS Sharpe={mean_sh:.4f} (need >= {min_mean_sharpe}). "
            f"Std={arr.std(ddof=1):.4f}, Min={arr.min():.4f}, Max={arr.max():.4f}"
        ),
        raw={
            "positive_fraction": pos_frac,
            "mean_sharpe": mean_sh,
            "std": float(arr.std(ddof=1)),
            "min": float(arr.min()),
            "max": float(arr.max()),
            "n_windows": len(arr),
        },
    )


# ---------------------------------------------------------------------------
# Test 6: Drawdown Symmetry (IS vs OOS)
# ---------------------------------------------------------------------------

def drawdown_symmetry_test(
    is_drawdowns: list[float],
    oos_drawdowns: list[float],
    max_ratio: float = 2.0,
) -> TestResult:
    """
    Compare median in-sample max drawdown to median OOS max drawdown.
    If OOS drawdown is more than `max_ratio` times the IS drawdown, it suggests
    the optimiser found parameters that avoid IS drawdowns by fitting noise.

    Parameters
    ----------
    is_drawdowns  : list of IS max drawdown fractions (0-1)
    oos_drawdowns : list of OOS max drawdown fractions (0-1)
    max_ratio     : maximum acceptable OOS/IS drawdown ratio
    """
    name = "Drawdown Symmetry (IS vs OOS)"

    if len(is_drawdowns) < 2 or len(oos_drawdowns) < 2:
        return TestResult(
            name=name, passed=False, value=None, threshold=max_ratio,
            detail="Insufficient drawdown data",
        )

    median_is = float(np.median(is_drawdowns))
    median_oos = float(np.median(oos_drawdowns))

    if median_is == 0:
        ratio = float("inf")
    else:
        ratio = median_oos / median_is

    passed = ratio <= max_ratio

    return TestResult(
        name=name,
        passed=passed,
        value=ratio,
        threshold=max_ratio,
        detail=(
            f"Median IS DD={median_is:.4f} | Median OOS DD={median_oos:.4f} | "
            f"Ratio={ratio:.4f} (max {max_ratio:.1f}). "
            f"{'OOS DD much worse than IS — likely overfitting.' if not passed else 'Within bounds.'}"
        ),
        raw={
            "median_is_dd": median_is,
            "median_oos_dd": median_oos,
            "ratio": ratio,
        },
    )


# ---------------------------------------------------------------------------
# Master runner: collect all tests from a WFO result
# ---------------------------------------------------------------------------

def run_full_overfit_suite(
    strategy: str,
    wfo_results_df: pd.DataFrame,
    best_trades: list[dict[str, Any]],
    param_metric_map: dict[str, tuple[list, list[float]]] | None = None,
    grid_bounds: dict[str, tuple] | None = None,
    monte_carlo_n: int = 1000,
    mc_confidence: float = 0.95,
) -> OverfitTestSuite:
    """
    Run the complete overfitting test suite against walk-forward results.

    Parameters
    ----------
    strategy         : "LRB" or "EMP"
    wfo_results_df   : DataFrame loaded from walk_forward_optimizer CSV output
    best_trades      : list of trade dicts (pnl, entry_dt, exit_dt) from best params
    param_metric_map : {param: ([values], [metrics])} for stability analysis
                       — if None, stability tests are skipped
    grid_bounds      : {param: (lo, hi)} for boundary detection
    monte_carlo_n    : number of MC permutations
    mc_confidence    : confidence level for MC test

    Returns
    -------
    OverfitTestSuite
    """
    suite = OverfitTestSuite(strategy=strategy)

    # ---- 1. Monte Carlo permutation test ----------------------------------
    suite.all_tests.append(
        monte_carlo_permutation_test(
            trades=best_trades,
            n_permutations=monte_carlo_n,
            confidence=mc_confidence,
            metric="sharpe",
        )
    )

    # ---- 2. Parameter stability (if data provided) ------------------------
    if param_metric_map:
        stability_tests = run_all_param_stability(
            param_grid={k: v[0] for k, v in param_metric_map.items()},
            param_metric_map=param_metric_map,
            grid_bounds=grid_bounds,
        )
        suite.all_tests.extend(stability_tests)

    # ---- 3. Param-Performance correlation matrix --------------------------
    param_cols = [c for c in wfo_results_df.columns if c.startswith("param_")]
    if param_cols and "oos_sharpe" in wfo_results_df.columns:
        _, corr_tests = parameter_correlation_matrix(
            results_df=wfo_results_df,
            param_cols=param_cols,
            metric_col="oos_sharpe",
        )
        suite.all_tests.extend(corr_tests)

    # ---- 4. Efficiency ratio distribution ---------------------------------
    if "efficiency_ratio" in wfo_results_df.columns:
        ers = wfo_results_df["efficiency_ratio"].replace([float("inf"), float("-inf")], float("nan")).dropna().tolist()
        suite.all_tests.append(efficiency_ratio_test(ers))

    # ---- 5. Walk-forward OOS consistency ----------------------------------
    if "oos_sharpe" in wfo_results_df.columns:
        # Use the best OOS Sharpe per window (each window has multiple combos)
        if "test_start" in wfo_results_df.columns:
            best_per_window = (
                wfo_results_df.groupby("test_start")["oos_sharpe"].max().tolist()
            )
        else:
            best_per_window = wfo_results_df["oos_sharpe"].tolist()
        suite.all_tests.append(walk_forward_consistency_test(best_per_window))

    # ---- 6. Drawdown symmetry ---------------------------------------------
    if "is_max_drawdown" in wfo_results_df.columns and "oos_max_drawdown" in wfo_results_df.columns:
        suite.all_tests.append(
            drawdown_symmetry_test(
                is_drawdowns=wfo_results_df["is_max_drawdown"].tolist(),
                oos_drawdowns=wfo_results_df["oos_max_drawdown"].tolist(),
            )
        )

    return suite


# ---------------------------------------------------------------------------
# Standalone anti-overfit checks (single-window, same as optimizer inline)
# ---------------------------------------------------------------------------

def check_all_anti_overfit_rules(
    is_metrics: dict[str, Any],
    oos_metrics: dict[str, Any],
    is_trades: list[dict],
    oos_trades: list[dict],
    params: dict[str, Any],
    strategy: str,
    min_oos_sharpe: float = 0.5,
    min_trades: int = 20,
    max_concentration: float = 0.40,
) -> list[TestResult]:
    """
    Run all five anti-overfitting rules on a single window result.

    This provides the same checks as the inline optimizer logic but exposed as
    TestResult objects for reporting.

    Returns list of TestResult (one per rule).
    """
    results: list[TestResult] = []

    is_wr  = is_metrics.get("win_rate", 0.0)
    oos_wr = oos_metrics.get("win_rate", 0.0)
    oos_sh = oos_metrics.get("sharpe", float("-inf"))
    n_oos  = len(oos_trades)

    # Rule 1: win-rate collapse
    r1_pass = not (is_wr > 0.80 and oos_wr < 0.45)
    results.append(TestResult(
        name="Rule 1: Win-Rate Collapse",
        passed=r1_pass,
        value=is_wr - oos_wr,
        threshold=0.35,
        detail=(
            f"IS win-rate={is_wr:.1%}, OOS win-rate={oos_wr:.1%}. "
            f"{'FAIL — IS>80% and OOS<45%.' if not r1_pass else 'PASS.'}"
        ),
    ))

    # Rule 2: minimum OOS Sharpe
    r2_pass = oos_sh >= min_oos_sharpe
    results.append(TestResult(
        name="Rule 2: Minimum OOS Sharpe",
        passed=r2_pass,
        value=oos_sh,
        threshold=min_oos_sharpe,
        detail=f"OOS Sharpe={oos_sh:.4f} vs minimum {min_oos_sharpe}",
    ))

    # Rule 3: concentration risk
    monthly = {}
    for t in oos_trades:
        dt = t["entry_dt"]
        key = f"{dt.year}-{dt.month:02d}" if hasattr(dt, "month") else str(dt)[:7]
        monthly[key] = monthly.get(key, 0.0) + t["pnl"]
    total_pnl = sum(monthly.values())
    best_month_pnl = max(monthly.values()) if monthly else 0.0
    conc = best_month_pnl / total_pnl if total_pnl > 0 else 1.0
    r3_pass = conc <= max_concentration
    results.append(TestResult(
        name="Rule 3: Concentration Risk",
        passed=r3_pass,
        value=conc,
        threshold=max_concentration,
        detail=(
            f"Best OOS month = {conc:.1%} of total profit "
            f"(max {max_concentration:.0%}). "
            f"{'FAIL — too concentrated.' if not r3_pass else 'PASS.'}"
        ),
    ))

    # Rule 4: minimum trade count
    r4_pass = n_oos >= min_trades
    results.append(TestResult(
        name="Rule 4: Minimum Trade Count",
        passed=r4_pass,
        value=float(n_oos),
        threshold=float(min_trades),
        detail=f"{n_oos} OOS trades (minimum {min_trades}).",
    ))

    # Rule 5: boundary detection
    from walk_forward_optimizer import _is_boundary  # type: ignore[import]
    boundary = _is_boundary(strategy, params)
    r5_pass = len(boundary) == 0
    results.append(TestResult(
        name="Rule 5: Search Space Boundary",
        passed=r5_pass,
        value=float(len(boundary)),
        threshold=0.0,
        detail=(
            f"Boundary params: {', '.join(boundary) if boundary else 'none'}. "
            f"{'FAIL — params at edge of search space.' if not r5_pass else 'PASS.'}"
        ),
    ))

    return results


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def print_correlation_matrix(corr_df: pd.DataFrame) -> None:
    """Pretty-print the parameter correlation matrix."""
    if corr_df.empty:
        print("(No correlation data available)")
        return
    print(f"\n{'Param':<30} {'Pearson r':>12} {'Signal'}")
    print("-" * 55)
    for param, row in corr_df.iterrows():
        r = row["pearson_r"]
        signal = "HIGH-CORR" if abs(r) >= 0.70 else ("moderate" if abs(r) >= 0.40 else "low")
        print(f"{param:<30} {r:>12.4f} {'<-- ' + signal if signal != 'low' else signal}")


def save_suite_report(suite: OverfitTestSuite, path: str) -> None:
    """Save OverfitTestSuite summary to a plain-text report file."""
    import json
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(suite.summary())
        f.write("\n\n--- RAW DATA (JSON) ---\n")
        json.dump(suite.to_dict(), f, indent=2, default=str)
    print(f"Suite report saved → {p}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import csv as csv_mod

    parser = argparse.ArgumentParser(description="Overfitting Test Suite")
    parser.add_argument("--strategy", choices=["LRB", "EMP"], required=True)
    parser.add_argument("--wfo-csv", type=str, required=True, help="CSV output from walk_forward_optimizer")
    parser.add_argument("--output", type=str, default="overfit_report.txt")
    parser.add_argument("--mc-n", type=int, default=1000)
    args = parser.parse_args()

    df = pd.read_csv(args.wfo_csv)

    # Use all OOS trades from the CSV as synthetic trade list for MC test
    # In production pass the actual trade list from the best param set
    best_trades: list[dict] = []
    from datetime import datetime as _dt
    for _, row in df.iterrows():
        pnl = row.get("oos_total_return", 0.0)
        n = max(1, int(row.get("oos_trade_count", 1)))
        # Distribute return equally across trades (approximation)
        per_trade = pnl / n if n else 0.0
        for i in range(n):
            best_trades.append({
                "pnl": per_trade,
                "entry_dt": _dt(2022, 1, 1),
                "exit_dt": _dt(2022, 1, 2),
            })

    suite = run_full_overfit_suite(
        strategy=args.strategy,
        wfo_results_df=df,
        best_trades=best_trades,
        monte_carlo_n=args.mc_n,
    )

    print(suite.summary())
    save_suite_report(suite, args.output)
