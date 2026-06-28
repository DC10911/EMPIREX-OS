# Walk-Forward Optimization Report
## EMPIREX-OS Quantitative Strategy Research Pipeline

**Report Version:** 1.0  
**Strategies Covered:** LRB (London Range Breakout) | EMP (Session Momentum)  
**Methodology:** Rolling Walk-Forward with Anti-Overfitting Enforcement  

---

## 1. Methodology

### 1.1 Why Walk-Forward Over Simple In-Sample Optimization

Simple in-sample optimization (fit all parameters to the full historical dataset,
pick the best) is the single most common source of false alpha in strategy research.
The problem is not fitting per se — it is fitting without any mechanism to distinguish
genuine signal from data mining.

**The core issue:** a grid search over N parameters with M values each evaluates
M^N combinations. Given enough combinations, some will appear excellent *on the
data used to select them* through pure chance. The Sharpe ratio of the best
combination is biased upward by the search process itself. The degree of bias grows
with the ratio of combinations tested to the length of the dataset.

Walk-forward optimization addresses this by enforcing a strict temporal separation:

```
Timeline:
  [--- Training (3m) ---][Test (1m)]
           [--- Training (3m) ---][Test (1m)]
                    [--- Training (3m) ---][Test (1m)]
                              ...
```

- **In-sample (IS):** Parameters are selected here. Any overfitting will manifest
  as strong IS metrics.
- **Out-of-sample (OOS):** Parameters are evaluated here, on data never seen during
  selection. This is the only honest estimate of forward performance.

The OOS windows are stitched together to form a synthetic out-of-sample equity curve
that approximates what live trading would have produced, given the same re-optimisation
schedule.

### 1.2 Walk-Forward Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Training window | 3 months | Long enough for stable Sharpe estimates; short enough to adapt to regime changes |
| Test window | 1 month | Matches typical live re-optimisation cadence |
| Step size | 1 month | Every month of data generates one test period |
| IS Selection metric | Sharpe ratio | Penalises volatility; more robust than raw P&L |
| Top IS percentile forwarded to OOS | 40% | Wide enough to avoid lucky-single-best effects |

### 1.3 Efficiency Ratio

The **efficiency ratio (ER)** is the central robustness metric:

```
ER = OOS Sharpe / IS Sharpe
```

- ER = 1.0 → perfect preservation of IS performance OOS
- ER = 0.5 → OOS retains 50% of IS edge (acceptable)
- ER < 0.0 → strategy degrades to loss OOS (strong overfitting signal)

A healthy strategy should have median ER >= 0.50 across all walk-forward windows.
Strategies with median ER < 0.30 should be redesigned before live deployment.

---

## 2. Anti-Overfitting Rules

All five rules are enforced simultaneously. A parameter set that fails any rule
is rejected for that walk-forward window.

### Rule 1: Win-Rate Collapse Flag

**Condition:** IS win-rate > 80% AND OOS win-rate < 45%  
**What it catches:** Parameters that exploit noise in the IS window to achieve
near-perfect win-rates by cherry-picking entry conditions that happened to work
in that specific 3-month stretch. These same conditions produce a random or
losing sequence OOS.

**Threshold rationale:** 80%/45% creates a gap of 35 percentage points — large
enough that normal statistical variation between windows cannot explain the
collapse. Smaller gaps are expected and acceptable.

### Rule 2: Minimum OOS Sharpe

**Condition:** OOS Sharpe < 0.5 (annualised)  
**What it catches:** Parameter sets that look good IS but produce statistically
marginal or negative OOS performance. A Sharpe of 0.5 is the lower bound of
"investable" for an institutional quantitative strategy.

**Note:** This threshold applies to the *single-month OOS window*, which has higher
Sharpe variance than a full-year estimate. A 1-month Sharpe of 0.5 annualised
corresponds to roughly a 0.14 monthly Sharpe — a modest but non-trivial bar.

### Rule 3: Concentration Risk

**Condition:** Best OOS month contributes > 40% of total OOS profit  
**What it catches:** Strategies whose P&L is driven by one or two exceptional
events rather than consistent edge. Concentration risk means the strategy is
dependent on tail events recurring, which they often do not.

**Example:** If 3 months of OOS trading produces $1,000 profit but one month
accounts for $600, the strategy is not "working consistently" — it got lucky in
one month and broke even the rest.

### Rule 4: Minimum Trade Count

**Condition:** Fewer than 20 trades in any test window  
**What it catches:** Statistical insignificance. A Sharpe ratio computed on 5
trades is meaningless — it could easily arise from chance. 20 trades over 1 month
is the minimum for the metrics to carry any statistical weight.

**Note:** If your strategy regularly generates fewer than 20 trades per month,
consider extending the test window to 2 months or reducing the minimum to 10
with an explicit warning in reporting.

### Rule 5: Search Space Boundary Flag

**Condition:** Optimal parameter lies at the boundary of the search space  
**What it catches:** Optimization artifacts where the grid search is telling you
"go further" but you have not defined a wider range. If the optimal SL multiplier
is always 2.5 (the maximum in your grid), the real optimum may be 3.0 or 4.0 —
and you are constraining to a suboptimal value. Boundary results require expanding
the search space and re-running before trusting the result.

This rule **flags** rather than fails, because boundary results may be genuine
(e.g., "more TP is always better" is a reasonable finding) — but they always
require human review.

---

## 3. Parameter Stability Analysis

Parameter stability measures how sensitively the OOS Sharpe varies when a single
parameter is changed by one step while all others are held fixed.

**Stable parameters** show a broad plateau: the strategy performs well across a
range of values. This is the signature of genuine signal — the strategy works
because of structural market microstructure, not because one magic number was
found.

**Unstable parameters** show sharp spikes: the strategy performs well at exactly
one value and degrades rapidly on either side. This is a classic overfitting
signature, especially dangerous when the spike aligns with a boundary or with
the precise parameter value that maximises a particular IS period.

### Stability Metric

```
Plateau fraction = fraction of parameter grid where metric >= 80% of peak metric
```

A parameter is deemed **stable** if the plateau fraction >= 25% of the grid range.

---

## 4. Parameter Correlation Analysis

Pearson correlation between each parameter and the OOS Sharpe identifies
structural relationships vs spurious ones.

**Expected correlations:**
- A well-designed TP multiplier should have positive correlation with Sharpe
  (higher reward-to-risk → higher Sharpe), but only up to a point
- RSI threshold is expected to have low correlation unless the strategy is
  highly RSI-driven

**Red flag:** |r| > 0.70 between a parameter and OOS Sharpe suggests the
parameter is load-bearing for performance in a way that may be data-specific.
When this appears, run an additional stability test specifically for that
parameter across rolling sub-windows.

---

## 5. Monte Carlo Permutation Test

### Methodology

1. Record all OOS trades and their P&L values.
2. Shuffle the order of P&L values 1,000 times (keeping the magnitudes, changing only the sequence).
3. Compute the Sharpe ratio (or chosen metric) for each shuffled curve.
4. Check: does the real Sharpe rank above the 95th percentile of shuffled Sharpes?

### Interpretation

- **PASS (real Sharpe > 95th percentile of shuffled):** The P&L sequence has
  structural properties — it is not just a collection of random gains and losses.
  The ordering matters, which is consistent with a timing strategy capturing
  genuine intraday patterns.

- **FAIL (real Sharpe <= 95th percentile):** The P&L sequence is statistically
  indistinguishable from random. The strategy may be capturing noise, or the
  underlying alpha is too weak to measure with the available sample.

### Important caveat

The permutation test evaluates sequence dependency, not edge. A strategy with
genuine edge but low autocorrelation in returns (e.g., one that takes uncorrelated
daily trades) may fail this test even though it has positive expected value.
Interpret in conjunction with the walk-forward OOS consistency test.

---

## 6. Recommended Default Parameters

> **Note:** The values below are structural starting points derived from the
> parameter grid design. Fill in actual values after running walk-forward
> optimisation on your historical OHLCV data.

### LRB (London Range Breakout)

| Parameter | Grid Range | Step | Recommended Default | Stability Notes |
|-----------|-----------|------|---------------------|-----------------|
| pre_session_start | 5.0–7.0h UTC | 0.5h | _[fill after WFO]_ | Expected low sensitivity — London open is structural |
| pre_session_end | 7.5–8.5h UTC | 0.5h | _[fill after WFO]_ | Should converge near 8.0h (hard London open) |
| tp_multiplier | 1.0–3.0 | 0.25 | _[fill after WFO]_ | Expect positive Sharpe correlation; check for ceiling |
| sl_from_opposite | True/False | — | _[fill after WFO]_ | Test both; structural argument favours True |
| time_exit_hour | 12–15 UTC | 1h | _[fill after WFO]_ | Should show plateau 13–14h (pre-US open exit) |

**Structural priors for LRB:**
- `pre_session_end` near 8.0 UTC is structurally motivated by the Frankfurt/London
  crossover — this is where the range forms. Values away from 8.0 are suspicious.
- `time_exit_hour` of 13–14 UTC exits before the US open volatility regime shift.
  Values at 15 (boundary) should be flagged for Rule 5 review.

### EMP (Session Momentum)

| Parameter | Grid Range | Step | Recommended Default | Stability Notes |
|-----------|-----------|------|---------------------|-----------------|
| atr_period | 10–21 | 1 | _[fill after WFO]_ | Expect plateau 12–18 — ATR is robust in this range |
| atr_band_mult | 0.8–2.0 | 0.2 | _[fill after WFO]_ | High sensitivity expected; check plateau carefully |
| rsi_period | 10–21 | 1 | _[fill after WFO]_ | Similar to ATR — should show broad plateau |
| rsi_threshold | 45–55 | 1 | _[fill after WFO]_ | 50 is structural; tight range reduces noise |
| sl_atr_mult | 1.0–2.5 | 0.25 | _[fill after WFO]_ | Watch for Rule 5 ceiling at 2.5 |
| tp_atr_mult | 1.5–4.0 | 0.25 | _[fill after WFO]_ | Trade-off: high TP = low win-rate; check win-rate floor |

**Structural priors for EMP:**
- `rsi_threshold` near 50 is structurally neutral — the strategy shouldn't depend
  heavily on RSI filter direction. If the optimum is 45 or 55 (boundary), investigate.
- `sl_atr_mult` below 1.0 risks stop-hunting by market noise; above 2.5 makes
  the position size risk-per-trade too large for most risk frameworks.
- `tp/sl` ratio (tp_atr_mult / sl_atr_mult) should be >= 1.5 to maintain positive
  expectancy even at 40% win-rate.

---

## 7. Anti-Overfitting Test Results Template

Fill this section with actual values after running the optimizer.

### LRB Results

```
Test Period: [START] to [END]
Walk-Forward Windows: [N]
Total OOS Trades: [N]

WALK-FORWARD METRICS
--------------------
Average IS Sharpe:            [___]
Average OOS Sharpe:           [___]
Average Efficiency Ratio:     [___]
OOS Positive-Window Fraction: [___]%

ANTI-OVERFIT RULE RESULTS
--------------------------
Rule 1 (Win-Rate Collapse):     [PASS/FAIL] — IS:[___]%  OOS:[___]%
Rule 2 (Min OOS Sharpe 0.5):    [PASS/FAIL] — Avg OOS Sharpe: [___]
Rule 3 (Concentration Risk):    [PASS/FAIL] — Best month: [___]% of profit
Rule 4 (Min 20 OOS Trades):     [PASS/FAIL] — Min trades in window: [___]
Rule 5 (Boundary Params):       [PASS/FLAG] — Flagged params: [list]

OVERFITTING TEST SUITE
-----------------------
Monte Carlo Permutation (1000): [PASS/FAIL] — Percentile: [___]%
Parameter Stability:
  pre_session_start:  [PASS/FAIL] — Plateau: [___]%
  pre_session_end:    [PASS/FAIL] — Plateau: [___]%
  tp_multiplier:      [PASS/FAIL] — Plateau: [___]%
  sl_from_opposite:   [PASS/FAIL] — True fraction: [___]%
  time_exit_hour:     [PASS/FAIL] — Plateau: [___]%
Efficiency Ratio Distribution: [PASS/FAIL] — Median ER: [___]
OOS Consistency:               [PASS/FAIL] — Positive windows: [___]%
Drawdown Symmetry:             [PASS/FAIL] — OOS/IS DD ratio: [___]

RECOMMENDED PARAMS (post-WFO)
------------------------------
  pre_session_start: [___]
  pre_session_end:   [___]
  tp_multiplier:     [___]
  sl_from_opposite:  [___]
  time_exit_hour:    [___]
```

### EMP Results

```
Test Period: [START] to [END]
Walk-Forward Windows: [N]
Total OOS Trades: [N]

WALK-FORWARD METRICS
--------------------
Average IS Sharpe:            [___]
Average OOS Sharpe:           [___]
Average Efficiency Ratio:     [___]
OOS Positive-Window Fraction: [___]%

ANTI-OVERFIT RULE RESULTS
--------------------------
Rule 1 (Win-Rate Collapse):     [PASS/FAIL] — IS:[___]%  OOS:[___]%
Rule 2 (Min OOS Sharpe 0.5):    [PASS/FAIL] — Avg OOS Sharpe: [___]
Rule 3 (Concentration Risk):    [PASS/FAIL] — Best month: [___]% of profit
Rule 4 (Min 20 OOS Trades):     [PASS/FAIL] — Min trades in window: [___]
Rule 5 (Boundary Params):       [PASS/FLAG] — Flagged params: [list]

OVERFITTING TEST SUITE
-----------------------
Monte Carlo Permutation (1000): [PASS/FAIL] — Percentile: [___]%
Parameter Stability:
  atr_period:         [PASS/FAIL] — Plateau: [___]%
  atr_band_mult:      [PASS/FAIL] — Plateau: [___]%
  rsi_period:         [PASS/FAIL] — Plateau: [___]%
  rsi_threshold:      [PASS/FAIL] — Plateau: [___]%
  sl_atr_mult:        [PASS/FAIL] — Plateau: [___]%
  tp_atr_mult:        [PASS/FAIL] — Plateau: [___]%
Efficiency Ratio Distribution: [PASS/FAIL] — Median ER: [___]
OOS Consistency:               [PASS/FAIL] — Positive windows: [___]%
Drawdown Symmetry:             [PASS/FAIL] — OOS/IS DD ratio: [___]

RECOMMENDED PARAMS (post-WFO)
------------------------------
  atr_period:    [___]
  atr_band_mult: [___]
  rsi_period:    [___]
  rsi_threshold: [___]
  sl_atr_mult:   [___]
  tp_atr_mult:   [___]
```

---

## 8. Red Flags That Indicate Overfitting

The following patterns in walk-forward results should trigger a full strategy review
before live deployment. None is conclusive on its own, but two or more appearing
together is a strong indication of a data-mined strategy.

### Red Flag 1: IS/OOS Performance Cliff
The IS equity curve is smooth and rising. The OOS equity curve is flat or declining.
The gap is not one bad month — it is consistent across multiple windows.

**Diagnosis:** The optimizer is fitting to IS-period-specific patterns (news events,
seasonal volatility regimes) that do not repeat OOS.

**Action:** Increase training window to 6+ months, or add regime filters to prevent
optimization during anomalous IS periods.

### Red Flag 2: Parameter Instability Across Windows
The best parameter for January is tp_multiplier=2.0, for February it is 1.25, for
March it is 2.75. Parameters jump across the grid with no convergence.

**Diagnosis:** The strategy has no stable structural relationship between parameters
and performance. Each month's "best" parameter is exploiting that month's noise.

**Action:** The strategy may be fundamentally unoptimizable in this form. Consider
simplifying (fewer parameters) or using larger training windows.

### Red Flag 3: Sharpe Drops Sharply at Adjacent Parameter Values
The optimizer selects tp_multiplier=2.0, which has IS Sharpe=2.1. Adjacent values
(1.75 and 2.25) have IS Sharpe=0.8 and 0.9 respectively.

**Diagnosis:** This is a "lucky spike" — the optimizer found a narrow region that
fit the IS data perfectly but has no structural basis. OOS performance at the
selected value will likely revert to the adjacent-value level.

**Action:** Always check the stability plateau width. If it is < 25%, do not use
that parameter value regardless of IS performance.

### Red Flag 4: Rule 5 Boundaries Dominate
More than 30% of accepted window results have at least one boundary parameter.

**Diagnosis:** The optimizer consistently wants to push parameters beyond the
search space. Either the search space is too narrow (expand it and re-run), or
the strategy is chasing extreme values that will eventually produce outsized losses.

**Action:** Expand search space. If boundary results persist after expansion,
add a constraint that penalizes extreme values (e.g., regularization term in the
objective function).

### Red Flag 5: Concentration Risk Recurring
Rule 3 fails in more than 2 consecutive OOS windows.

**Diagnosis:** The strategy profits episodically — it waits for a specific market
condition and captures a large move, then flat-lines. This is not a systematic
intraday edge; it is an event-driven position that was accidentally discovered
through optimization.

**Action:** Check whether the profitable months cluster around specific macro
events (central bank meetings, earnings seasons). If so, this is a macro event
strategy, not an intraday momentum strategy, and should be treated as such.

### Red Flag 6: Monte Carlo Permutation Fail
The real equity curve does not beat 95% of randomly shuffled curves.

**Diagnosis:** The strategy's P&L sequence has no meaningful structure beyond
the distribution of individual trade returns. The timing edge is not statistically
detectable.

**Action:** This is not necessarily fatal — some valid intraday strategies have
low autocorrelation in returns. Check mean trade P&L directly. If mean P&L / std
of P&L (per-trade Sharpe) is positive and consistent, the strategy may still be
viable despite this test failing.

### Red Flag 7: Efficiency Ratio Trend Decline
Earlier walk-forward windows have ER=0.8, later windows have ER=0.3. The efficiency
ratio is declining over time.

**Diagnosis:** The market regime that the strategy was designed for is fading.
The more recent OOS periods are increasingly unlike the IS training periods.

**Action:** This may be a structural regime change (e.g., reduced intraday FX
volatility post-regulation). Consider adding a regime filter that suspends trading
when current market conditions differ significantly from training-period conditions.

---

## 9. Running the Optimizer

### Prerequisites
```
Python 3.10+
pip install pandas numpy
```
No scipy, sklearn, or other ML libraries required.

### Quick Start

```python
import pandas as pd
from quant_engine.optimizer.walk_forward_optimizer import run_optimization

# Load OHLCV data (DatetimeIndex, columns: open, high, low, close, volume)
df = pd.read_csv("data/EURUSD_H1.csv", index_col=0, parse_dates=True)

# Run LRB optimization
lrb_result = run_optimization(
    strategy="LRB",
    ohlcv_df=df,
    output_dir="./wfo_results/lrb",
    train_months=3,
    test_months=1,
    top_pct=0.40,
    verbose=True,
)

print(f"Recommended LRB params: {lrb_result.recommended_params}")
print(f"Avg OOS Sharpe: {lrb_result.avg_oos_sharpe:.3f}")
print(f"Avg Efficiency Ratio: {lrb_result.avg_efficiency_ratio:.3f}")
```

### Running Overfitting Tests

```python
import pandas as pd
from quant_engine.optimizer.overfitting_tests import run_full_overfit_suite

# Load WFO results CSV
wfo_df = pd.read_csv("./wfo_results/lrb/lrb_walk_forward_YYYYMMDD_HHMMSS.csv")

# Get trades from your best parameter set (replace with real trade list)
best_trades = [{"pnl": 0.003, "entry_dt": ..., "exit_dt": ...}, ...]

suite = run_full_overfit_suite(
    strategy="LRB",
    wfo_results_df=wfo_df,
    best_trades=best_trades,
    monte_carlo_n=1000,
    mc_confidence=0.95,
)

print(suite.summary())
```

### CLI Usage

```bash
# Walk-forward optimization
python walk_forward_optimizer.py \
  --strategy LRB \
  --data data/EURUSD_H1.csv \
  --output-dir ./wfo_results \
  --train-months 3 \
  --test-months 1 \
  --top-pct 0.40

# Overfitting tests
python overfitting_tests.py \
  --strategy LRB \
  --wfo-csv ./wfo_results/lrb_walk_forward_20240101_120000.csv \
  --output overfit_report.txt \
  --mc-n 1000
```

---

## 10. Output Files

### walk_forward_optimizer.py outputs

**CSV file** (`{strategy}_walk_forward_{timestamp}.csv`):
One row per parameter combination per walk-forward window. Columns include:
- `test_start`, `test_end`: window dates
- `is_sharpe`, `is_win_rate`, `is_profit_factor`, `is_max_drawdown`, `is_trade_count`
- `oos_sharpe`, `oos_win_rate`, `oos_profit_factor`, `oos_max_drawdown`, `oos_trade_count`
- `oos_total_return`: total OOS period return
- `efficiency_ratio`: OOS Sharpe / IS Sharpe
- `passed_anti_overfit`: bool
- `overfit_reasons`: pipe-separated list of failed rules
- `boundary_params`: comma-separated list of boundary-flagged params
- `rank_percentile_is`, `rank_percentile_oos`: percentile rank within window
- `param_{name}`: one column per parameter

**JSON file** (`{strategy}_walk_forward_{timestamp}.json`):
Compact summary with recommended params, avg OOS Sharpe, efficiency ratio, and
parameter stability summary.

### overfitting_tests.py outputs

**Console:** Full test suite summary with PASS/FAIL per test.  
**Text report** (optional): Same content written to file for archiving.

---

*Generated by EMPIREX-OS optimizer-agent | Walk-Forward Optimization Framework v1.0*
