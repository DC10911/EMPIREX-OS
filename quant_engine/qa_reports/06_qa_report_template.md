# QA REPORT TEMPLATE — EMPIREX-OS Quantitative Strategy
## VERSION: 1.0 | Date: [FILL DATE]

---

> **THIS IS A TEMPLATE. Results must be filled with REAL backtest data.**
> Do not submit this document with empty or placeholder values.
> Every checkbox and table cell must be completed before review.

---

## STRATEGY METADATA

| Field | Value |
|---|---|
| Strategy Name | [FILL] |
| Strategy ID | [FILL e.g. EMP-LRB-001] |
| Version | [FILL] |
| Author / Agent | [FILL] |
| QA Reviewer | [FILL] |
| QA Date | [FILL YYYY-MM-DD] |
| Instrument(s) | [FILL e.g. EURUSD, GBPUSD] |
| Timeframe | [FILL e.g. 1H, 15M] |
| Backtest Start | [FILL YYYY-MM-DD] |
| Backtest End | [FILL YYYY-MM-DD] |
| Backtest Duration (months) | [FILL] |
| Platform | [FILL e.g. TradingView Pine v6 / Python BacktestEngine v1] |
| Broker Model | [FILL e.g. ECN / Market Maker] |
| Initial Capital | $[FILL] |
| Lot Size | [FILL e.g. 0.1 lots fixed] |
| Data Source | [FILL e.g. OANDA v20 API / Interactive Brokers] |

---

## SECTION 1: TECHNICAL QUALITY CHECKS

| # | Check | Status | Notes |
|---|---|---|---|
| 1.1 | No repainting (signals do not change on historical bars) | [ ] PASS / [ ] FAIL | [FILL] |
| 1.2 | No lookahead bias (no future data in signal calculation) | [ ] PASS / [ ] FAIL | [FILL] |
| 1.3 | All signals based on confirmed (closed) bars only | [ ] PASS / [ ] FAIL | [FILL] |
| 1.4 | Pine Script: no security() with lookahead=true | [ ] PASS / [ ] FAIL / [ ] N/A | [FILL] |
| 1.5 | Python: no df.shift(-N), no future-date forward-fill | [ ] PASS / [ ] FAIL / [ ] N/A | [FILL] |

**Repainting Checker Output:**
```
[PASTE OUTPUT OF repainting_checker.py HERE]
```

**Technical Quality Verdict:** [ ] ALL PASS  [ ] FAILURES PRESENT

---

## SECTION 2: COST REALISM

### Cost Model Documentation

| Cost Component | Backtest Value | Broker Spec | Match? |
|---|---|---|---|
| Spread (pips) | [FILL] | [FILL] | [ ] YES / [ ] NO |
| Commission (RT, USD) | [FILL] | [FILL] | [ ] YES / [ ] NO |
| Slippage (pips) | [FILL] | [FILL] | [ ] YES / [ ] NO |
| **Total Cost per Trade (USD)** | **$[FILL]** | **$[FILL]** | **[ ] YES / [ ] NO** |

| # | Check | Status | Notes |
|---|---|---|---|
| 2.1 | Spread included in backtest | [ ] PASS / [ ] FAIL | [FILL] |
| 2.2 | Commission included in backtest | [ ] PASS / [ ] FAIL | [FILL] |
| 2.3 | Slippage included in backtest | [ ] PASS / [ ] FAIL | [FILL] |
| 2.4 | Total cost documented and matches broker specs | [ ] PASS / [ ] WARN / [ ] FAIL | [FILL] |

**Cost Realism Verdict:** [ ] ALL PASS  [ ] FAILURES PRESENT

---

## SECTION 3: STATISTICAL VALIDITY

### Core Statistics

| Metric | Value | Threshold | Pass? |
|---|---|---|---|
| Total trades | [FILL] | n/a | — |
| Win rate | [FILL]% | 30%–70% plausible | [ ] PASS / [ ] WARN |
| Profit factor | [FILL] | > 1.2 (reject ≤ 1.0) | [ ] PASS / [ ] WARN / [ ] FAIL |
| Net profit | $[FILL] | > 0 | [ ] PASS / [ ] FAIL |
| Avg trade net P/L | $[FILL] | > total cost | [ ] PASS / [ ] FAIL |
| Backtest duration | [FILL] months | ≥ 6 months | [ ] PASS / [ ] FAIL |
| Min trades per month | [FILL] | ≥ 20 | [ ] PASS / [ ] FAIL |
| Max single month profit share | [FILL]% | ≤ 40% | [ ] PASS / [ ] FAIL |

| # | Check | Status | Notes |
|---|---|---|---|
| 3.1 | Minimum 20 trades per month in every month | [ ] PASS / [ ] FAIL | Worst month: [FILL] trades in [FILL-MM] |
| 3.2 | No single month contributes > 40% of total profit | [ ] PASS / [ ] FAIL | Best month share: [FILL]% |
| 3.3 | Minimum 6 months of data tested | [ ] PASS / [ ] FAIL | [FILL] months tested |
| 3.4 | Win rate documented and plausible (30%–70%) | [ ] PASS / [ ] WARN | Win rate: [FILL]% |
| 3.5 | Profit factor > 1.2 | [ ] PASS / [ ] WARN / [ ] FAIL | PF: [FILL] |

**Statistical Validity Verdict:** [ ] ALL PASS  [ ] FAILURES PRESENT

---

## SECTION 4: MONTHLY BREAKDOWN

### Monthly P/L Table

| Year | Month | Gross P/L | Costs | Net P/L | % of Total |
|---|---|---|---|---|---|
| [FILL] | Jan | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Feb | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Mar | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Apr | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | May | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Jun | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Jul | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Aug | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Sep | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Oct | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Nov | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| [FILL] | Dec | $[FILL] | $[FILL] | $[FILL] | [FILL]% |
| **TOTAL** | | **$[FILL]** | **$[FILL]** | **$[FILL]** | **100%** |

### Monthly Trade Count Table

| Year | Month | Total Trades | Winners | Losers | Win Rate |
|---|---|---|---|---|---|
| [FILL] | Jan | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Feb | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Mar | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Apr | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | May | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Jun | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Jul | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Aug | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Sep | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Oct | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Nov | [FILL] | [FILL] | [FILL] | [FILL]% |
| [FILL] | Dec | [FILL] | [FILL] | [FILL] | [FILL]% |
| **TOTAL** | | **[FILL]** | **[FILL]** | **[FILL]** | **[FILL]%** |

### Monthly Breakdown Summary

| # | Check | Status | Notes |
|---|---|---|---|
| 4.1 | Monthly P/L table exists (above) | [ ] PASS / [ ] FAIL | — |
| 4.2 | Monthly trade count table exists (above) | [ ] PASS / [ ] FAIL | — |
| 4.3 | No months with 0 trades (unless holiday) | [ ] PASS / [ ] WARN | Zero-trade months: [FILL or NONE] |
| 4.4 | Best month identified | [ ] PASS / [ ] FAIL | [FILL YYYY-MM]: $[FILL] |
| 4.5 | Worst month identified | [ ] PASS / [ ] FAIL | [FILL YYYY-MM]: $[FILL] |

**Monthly Breakdown Verdict:** [ ] ALL PASS  [ ] FAILURES PRESENT

---

## SECTION 5: BENCHMARK COMPARISON

### Benchmark Results Table

| Benchmark | Net Return % | Profit Factor | Max Drawdown % | Notes |
|---|---|---|---|---|
| **This Strategy** | [FILL]% | [FILL] | [FILL]% | — |
| Buy-and-Hold (same instrument) | [FILL]% | n/a | [FILL]% | Passive hold over same period |
| LRB Benchmark (LRB_Benchmark_v6.pine) | [FILL]% | [FILL] | [FILL]% | Run on same data range |

| # | Check | Status | Notes |
|---|---|---|---|
| 5.1 | Strategy compared to Buy-and-Hold benchmark | [ ] PASS / [ ] FAIL | Strategy [FILL]% vs B&H [FILL]% |
| 5.2 | Strategy compared to LRB benchmark | [ ] PASS / [ ] FAIL / [ ] WARN | PF vs LRB: [FILL] > [FILL]? |
| 5.3 | Strategy beats BOTH benchmarks net of costs | [ ] PASS / [ ] FAIL | [FILL] |

**Benchmark Comparison Verdict:** [ ] ALL PASS  [ ] FAILURES PRESENT

---

## SECTION 6: RISK CHECKS

### Risk Metrics

| Metric | Value | Threshold | Pass? |
|---|---|---|---|
| Maximum Drawdown | [FILL]% | Document; warn if > 30% | [ ] PASS / [ ] WARN |
| Max Consecutive Losses | [FILL] | Document; warn if > 10 | [ ] PASS / [ ] WARN |
| Average R-Multiple per trade | [FILL] | > 0 | [ ] PASS / [ ] FAIL |
| Sharpe Ratio (annualized, if computed) | [FILL] | > 1.0 preferred | [ ] PASS / [ ] WARN / [ ] N/A |
| Calmar Ratio (return / max DD) | [FILL] | > 1.0 preferred | [ ] PASS / [ ] WARN / [ ] N/A |

| # | Check | Status | Notes |
|---|---|---|---|
| 6.1 | Max drawdown documented | [ ] PASS / [ ] FAIL | DD: [FILL]% |
| 6.2 | Max consecutive losses documented | [ ] PASS / [ ] FAIL | MCL: [FILL] |
| 6.3 | Kill switch defined | [ ] PASS / [ ] FAIL | Trigger: [FILL e.g. 10% daily DD halt] |
| 6.4 | No martingale / grid / averaging down in code | [ ] PASS / [ ] FAIL | Evidence: [FILL or NONE] |
| 6.5 | Fixed lot size enforced | [ ] PASS / [ ] WARN | [FILL lot size] |

**Risk Checks Verdict:** [ ] ALL PASS  [ ] FAILURES PRESENT

---

## SECTION 7: EXECUTION FEASIBILITY

| # | Check | Status | Notes |
|---|---|---|---|
| 7.1 | Entry conditions achievable with market orders (no phantom fills) | [ ] PASS / [ ] WARN / [ ] FAIL | [FILL] |
| 7.2 | Stop loss always set at order time | [ ] PASS / [ ] FAIL | [FILL] |
| 7.3 | Slippage model matches broker type (ECN vs Market Maker) | [ ] PASS / [ ] WARN | Model: [FILL] / Broker: [FILL] |
| 7.4 | London session filter present (08:00–13:00 UTC) | [ ] PASS / [ ] WARN | [FILL] |

**Execution Feasibility Verdict:** [ ] ALL PASS  [ ] FAILURES PRESENT

---

## SECTION 8: ANTI-OVERFITTING TEST RESULTS

### Walk-Forward Analysis (if performed)

| Period | In-Sample | Out-of-Sample | IS Profit Factor | OOS Profit Factor | Degradation % |
|---|---|---|---|---|---|
| Period 1 | [FILL] to [FILL] | [FILL] to [FILL] | [FILL] | [FILL] | [FILL]% |
| Period 2 | [FILL] to [FILL] | [FILL] to [FILL] | [FILL] | [FILL] | [FILL]% |
| Period 3 | [FILL] to [FILL] | [FILL] to [FILL] | [FILL] | [FILL] | [FILL]% |
| **Average** | — | — | **[FILL]** | **[FILL]** | **[FILL]%** |

> Acceptable degradation: OOS PF >= 70% of IS PF. If OOS PF < 70% of IS PF, the
> strategy is likely overfit to the in-sample period.

### Parameter Sensitivity Test

| Parameter | Baseline | -20% | +20% | PF Change | Robust? |
|---|---|---|---|---|---|
| [FILL param] | [FILL] | [FILL] | [FILL] | [FILL] | [ ] YES / [ ] NO |
| [FILL param] | [FILL] | [FILL] | [FILL] | [FILL] | [ ] YES / [ ] NO |
| [FILL param] | [FILL] | [FILL] | [FILL] | [FILL] | [ ] YES / [ ] NO |

> A robust strategy shows < 20% PF change when parameters vary ±20%.

### Monte Carlo Simulation Results (if performed)

| Metric | 5th Percentile | 50th Percentile | 95th Percentile |
|---|---|---|---|
| Net return after [FILL] months | [FILL]% | [FILL]% | [FILL]% |
| Max drawdown | [FILL]% | [FILL]% | [FILL]% |
| Profit factor | [FILL] | [FILL] | [FILL] |

---

## SECTION 9: STRESS TEST RESULTS

| Scenario | Normal PF | Stressed PF | Passes? |
|---|---|---|---|
| Spread doubled (2× normal) | [FILL] | [FILL] | [ ] YES / [ ] NO |
| Slippage tripled (3× normal) | [FILL] | [FILL] | [ ] YES / [ ] NO |
| Worst historical volatility period only | [FILL] | [FILL] | [ ] YES / [ ] NO |
| London session extended by 1H each side | [FILL] | [FILL] | [ ] YES / [ ] NO |
| 2020 COVID volatility re-test | [FILL] | [FILL] | [ ] YES / [ ] NO |

> Strategy must remain profitable (PF > 1.0) under ALL stress scenarios.

---

## SECTION 10: OUT-OF-SAMPLE VALIDATION

| OOS Period | Duration (months) | Net Return | Profit Factor | Trades | Verdict |
|---|---|---|---|---|---|
| [FILL] to [FILL] | [FILL] | [FILL]% | [FILL] | [FILL] | [ ] PASS / [ ] FAIL |
| [FILL] to [FILL] | [FILL] | [FILL]% | [FILL] | [FILL] | [ ] PASS / [ ] FAIL |
| [FILL] to [FILL] | [FILL] | [FILL]% | [FILL] | [FILL] | [ ] PASS / [ ] FAIL |
| **Total OOS** | **[FILL]** | **[FILL]%** | **[FILL]** | **[FILL]** | **[ ] PASS / [ ] FAIL** |

> Minimum 3 months of positive OOS results required for LIVE-READY status.

---

## SECTION 11: QA VALIDATOR OUTPUT

Paste the complete output of `QAValidator().run_all_checks(strategy_results).summary()` here:

```
[PASTE QAValidator OUTPUT HERE]
```

Verdict from automated validator: [FILL: REJECTED / RESEARCH-VALID / FORWARD-TEST READY / LIVE-READY]

---

## SECTION 12: FINAL VERDICT

### Verdict Criteria Reference

| Verdict | Criteria |
|---|---|
| **REJECTED** | Any mandatory check fails |
| **RESEARCH-VALID** | All mandatory checks pass; warnings present |
| **FORWARD-TEST READY** | All checks pass, no warnings, profit factor > 1.5 |
| **LIVE-READY** | FORWARD-TEST READY + minimum 3 months of positive OOS |

### Final Decision

**Automated Validator Verdict:** [FILL]

**Human Reviewer Override:** [ ] AGREE with automated verdict  [ ] OVERRIDE to [FILL]

**Override Justification (required if overriding):**
> [FILL or N/A]

**Conditions for Upgrade (if RESEARCH-VALID or lower):**
- [ ] [FILL condition 1]
- [ ] [FILL condition 2]
- [ ] [FILL condition 3]

---

**FINAL VERDICT: [FILL: REJECTED / RESEARCH-VALID / FORWARD-TEST READY / LIVE-READY]**

---

## SIGN-OFF

| Role | Name | Date | Signature |
|---|---|---|---|
| QA Reviewer | [FILL] | [FILL] | [FILL] |
| Strategy Author | [FILL] | [FILL] | [FILL] |
| Risk Manager | [FILL] | [FILL] | [FILL] |

---

*THIS IS A TEMPLATE. Results must be filled with REAL backtest data.*
*Document version: 1.0 | EMPIREX-OS quant_engine/qa_reports/*
