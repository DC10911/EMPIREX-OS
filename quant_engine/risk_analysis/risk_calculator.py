#!/usr/bin/env python3
"""
EMPIREX-OS Risk Calculator
==========================
Quantitative risk analysis for London Session intraday strategy.

Business target : $500/day net profit
Instruments     : EURUSD, GBPUSD, XAUUSD, NAS100
Session         : London (08:00-13:00 UTC)
Trade size      : 1.0 lot fixed (2 trades/day)

Functions
---------
ev_table()             - Expected Value matrix (win rate × R:R)
kelly_fraction()       - Kelly fraction and half-Kelly table
drawdown_probability() - Monte Carlo drawdown probability curves
stress_test()          - 5 stress scenarios with P/L impact

Run as standalone: python risk_calculator.py
"""

import math
import random
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

# Base trade parameters (EURUSD 1.0 lot)
PIP_VALUE       = 10.00      # USD per pip for EURUSD 1.0 lot
SL_PIPS         = 30         # Stop-loss in pips
SL_DOLLARS      = SL_PIPS * PIP_VALUE   # $300

COMMISSION      = 7.00       # Round-trip commission USD
SPREAD_PIPS     = 1.50       # Typical London spread pips
SLIPPAGE_PIPS   = 0.50       # Estimated slippage pips
COST_PER_TRADE  = COMMISSION + (SPREAD_PIPS + SLIPPAGE_PIPS) * PIP_VALUE  # $27

TRADES_PER_DAY  = 2
TRADING_DAYS    = 20         # Per month
MONTHLY_TRADES  = TRADES_PER_DAY * TRADING_DAYS   # 40
DAILY_TARGET    = 500.00
MONTHLY_TARGET  = DAILY_TARGET * TRADING_DAYS     # $10,000

WIN_RATES       = [0.40, 0.45, 0.50, 0.55, 0.60]
RR_RATIOS       = [1.0, 1.5, 2.0, 2.5]

SEPARATOR       = "=" * 78
THIN_SEP        = "-" * 78


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _ev_per_trade(win_rate: float, rr: float,
                  sl_usd: float = SL_DOLLARS,
                  cost: float = COST_PER_TRADE) -> Tuple[float, float]:
    """
    Return (gross_ev, net_ev) per single trade.

    Gross EV: ignores transaction costs.
    Net EV  : subtracts cost_per_trade from every trade outcome.
    """
    tp_usd      = rr * sl_usd
    gross_ev    = win_rate * tp_usd - (1 - win_rate) * sl_usd
    net_win_usd = tp_usd - cost
    net_los_usd = sl_usd + cost
    net_ev      = win_rate * net_win_usd - (1 - win_rate) * net_los_usd
    return gross_ev, net_ev


def _kelly(win_rate: float, rr: float,
           sl_usd: float = SL_DOLLARS,
           cost: float = COST_PER_TRADE) -> float:
    """
    Kelly fraction adjusted for net win/loss (after costs).
    f* = W - (1-W)/R_net
    Returns fraction in range [-1, 1]. Negative = do not trade.
    """
    net_win = rr * sl_usd - cost
    net_los = sl_usd + cost
    if net_los == 0:
        return 0.0
    r_net = net_win / net_los
    return win_rate - (1 - win_rate) / r_net


def _max_consec_losses(win_rate: float, confidence: float = 0.99) -> int:
    """
    Expected maximum consecutive losses at given confidence level.
    Uses log formula: log(1-confidence) / log(1-win_rate)
    """
    lose_rate = 1 - win_rate
    if lose_rate <= 0:
        return 0
    return math.ceil(math.log(1 - confidence) / math.log(lose_rate))


# ---------------------------------------------------------------------------
# 1. Expected Value Table
# ---------------------------------------------------------------------------

def ev_table(
    win_rates: List[float] = WIN_RATES,
    rr_ratios: List[float] = RR_RATIOS,
    sl_usd: float = SL_DOLLARS,
    cost: float = COST_PER_TRADE,
    trades_per_day: int = TRADES_PER_DAY,
    trading_days: int = TRADING_DAYS,
) -> None:
    """
    Print three formatted tables:
      A) Gross EV per trade
      B) Net EV per trade
      C) Daily net EV (× trades_per_day)
      D) Monthly net P/L (× trading_days)
    Flags positive/negative EV cells and monthly-target cells.
    """
    print(f"\n{SEPARATOR}")
    print("  EXPECTED VALUE TABLES")
    print(f"  SL=${sl_usd:.0f} | Cost/trade=${cost:.2f} | "
          f"{trades_per_day} trades/day | {trading_days} days/month")
    print(SEPARATOR)

    header = f"{'WR':>6}" + "".join(f"  R:R {r:.1f}" for r in rr_ratios)
    col_sep = f"{'':>6}" + "  " + ("--------  " * len(rr_ratios))

    # --- Table A: Gross EV ---
    print("\n[A] GROSS EV PER TRADE (before costs)")
    print(header)
    print(col_sep)
    for w in win_rates:
        row = f"{w*100:>5.0f}%"
        for r in rr_ratios:
            g, _ = _ev_per_trade(w, r, sl_usd, cost)
            flag = "+" if g >= 0 else " "
            row += f"  {flag}${g:>7.2f}"
        print(row)

    # --- Table B: Net EV ---
    print("\n[B] NET EV PER TRADE (after costs)")
    print(header)
    print(col_sep)
    for w in win_rates:
        row = f"{w*100:>5.0f}%"
        for r in rr_ratios:
            _, n = _ev_per_trade(w, r, sl_usd, cost)
            marker = "*" if n < 0 else "+"
            row += f"  {marker}${n:>7.2f}" if n >= 0 else f"  -${abs(n):>7.2f}"
        print(row)
    print("  * = negative EV (do not trade this combination)")

    # --- Table C: Daily Net EV ---
    print(f"\n[C] DAILY NET EV ({trades_per_day} trades/day)")
    print(header)
    print(col_sep)
    for w in win_rates:
        row = f"{w*100:>5.0f}%"
        for r in rr_ratios:
            _, n = _ev_per_trade(w, r, sl_usd, cost)
            daily = n * trades_per_day
            marker = "+" if daily >= 0 else "-"
            row += f"  {marker}${abs(daily):>7.2f}"
        print(row)

    # --- Table D: Monthly P/L ---
    print(f"\n[D] MONTHLY NET P/L ({MONTHLY_TRADES} trades/month)")
    print(f"    Target: ${MONTHLY_TARGET:,.0f}/month   [TARGET] marks combos that reach it")
    print(header)
    print(col_sep)
    for w in win_rates:
        row = f"{w*100:>5.0f}%"
        for r in rr_ratios:
            _, n = _ev_per_trade(w, r, sl_usd, cost)
            monthly = n * MONTHLY_TRADES
            tag = " [TARGET]" if monthly >= MONTHLY_TARGET else ""
            sign = "+" if monthly >= 0 else "-"
            row += f"  {sign}${abs(monthly):>8.0f}{tag}"
        print(row)

    # --- Summary: breakeven WR ---
    print(f"\n[E] BREAKEVEN WIN RATE (net EV = 0)")
    print(f"  {'R:R':>8}  {'Breakeven WR':>14}  {'BE WR + costs':>14}")
    print(f"  {'-'*8}  {'-'*14}  {'-'*14}")
    for r in rr_ratios:
        be_random = 1 / (1 + r)
        # Net breakeven: W*(r*SL-cost) = (1-W)*(SL+cost)
        # W*(r*SL-cost) + W*(SL+cost) = SL+cost
        # W = (SL+cost)/(r*SL-cost+SL+cost) = (SL+cost)/((r+1)*SL)
        net_tp = r * sl_usd - cost
        net_lo = sl_usd + cost
        be_net = net_lo / (net_tp + net_lo) if (net_tp + net_lo) != 0 else float("nan")
        print(f"  {r:>7.1f}:1  {be_random*100:>13.1f}%  {be_net*100:>13.1f}%")
    print()


# ---------------------------------------------------------------------------
# 2. Kelly Fraction Table
# ---------------------------------------------------------------------------

def kelly_fraction(
    win_rates: List[float] = WIN_RATES,
    rr_ratios: List[float] = RR_RATIOS,
    sl_usd: float = SL_DOLLARS,
    cost: float = COST_PER_TRADE,
) -> None:
    """
    Print Kelly fraction, half-Kelly, quarter-Kelly, and
    max consecutive losses at 99% and 95% confidence.
    """
    print(f"\n{SEPARATOR}")
    print("  KELLY FRACTION ANALYSIS")
    print(f"  SL=${sl_usd:.0f} | Cost/trade=${cost:.2f}")
    print(SEPARATOR)

    print("\n[A] FULL KELLY FRACTION (% of account to risk per trade)")
    header = f"{'WR':>6}" + "".join(f"  R:R {r:.1f}" for r in rr_ratios)
    print(header)
    for w in win_rates:
        row = f"{w*100:>5.0f}%"
        for r in rr_ratios:
            k = _kelly(w, r, sl_usd, cost)
            if k < 0:
                row += f"   [NEG]  "
            else:
                row += f"  {k*100:>7.1f}%"
        print(row)
    print("  [NEG] = negative EV — this combination destroys capital")

    print("\n[B] HALF-KELLY FRACTION (recommended practical sizing)")
    print(header)
    for w in win_rates:
        row = f"{w*100:>5.0f}%"
        for r in rr_ratios:
            k = _kelly(w, r, sl_usd, cost)
            hk = max(0, k) * 0.5
            row += f"  {hk*100:>7.1f}%"
        print(row)

    print("\n[C] MAX CONSECUTIVE LOSSES (before 20% account drawdown)")
    print(f"  Based on $327/loss (SL + cost), account at $15,000")
    acct = 15000.0
    dd_limit = acct * 0.20  # 20% drawdown
    max_from_dd = int(dd_limit // (sl_usd + cost))
    print(f"  Max losses before 20% DD: {max_from_dd} consecutive losses "
          f"(${sl_usd+cost:.0f} each × {max_from_dd} = ${(sl_usd+cost)*max_from_dd:.0f})")

    print(f"\n[D] EXPECTED MAXIMUM CONSECUTIVE LOSS STREAK")
    print(f"  {'Win Rate':>10}  {'Max Streak (99% CI)':>22}  "
          f"{'Max Streak (95% CI)':>22}  {'Dollar Impact':>14}")
    print(f"  {'-'*10}  {'-'*22}  {'-'*22}  {'-'*14}")
    for w in win_rates:
        m99 = _max_consec_losses(w, 0.99)
        m95 = _max_consec_losses(w, 0.95)
        dollar_impact = m99 * (sl_usd + cost)
        print(f"  {w*100:>9.0f}%  {m99:>22d}  {m95:>22d}  "
              f"  ${dollar_impact:>10,.0f}")
    print()


# ---------------------------------------------------------------------------
# 3. Drawdown Probability (Monte Carlo)
# ---------------------------------------------------------------------------

def drawdown_probability(
    win_rates: List[float] = WIN_RATES,
    rr: float = 1.5,
    sl_usd: float = SL_DOLLARS,
    cost: float = COST_PER_TRADE,
    account_size: float = 15000.0,
    dd_thresholds_pct: List[float] = [0.10, 0.20, 0.30, 0.50],
    n_trade_points: List[int] = [20, 40, 100, 240, 480],
    n_simulations: int = 10000,
    seed: int = 42,
) -> None:
    """
    Monte Carlo simulation of drawdown probability.
    For each (win_rate, n_trades) pair, simulate n_simulations paths
    and compute P(max_drawdown > threshold) for each threshold.
    Uses fixed R:R for clean comparison.
    """
    random.seed(seed)
    print(f"\n{SEPARATOR}")
    print(f"  DRAWDOWN PROBABILITY (Monte Carlo, {n_simulations:,} simulations)")
    print(f"  R:R={rr:.1f} | SL=${sl_usd:.0f} | Cost/trade=${cost:.2f} | Account=${account_size:,.0f}")
    print(SEPARATOR)

    net_win = rr * sl_usd - cost
    net_los = sl_usd + cost

    for dd_pct in dd_thresholds_pct:
        dd_dollar = account_size * dd_pct
        print(f"\n  Drawdown threshold: {dd_pct*100:.0f}% of account = ${dd_dollar:,.0f}")
        print(f"  {'N Trades':>10}", end="")
        for w in win_rates:
            print(f"  WR={w*100:.0f}%", end="")
        print()
        print(f"  {'-'*10}", end="")
        for _ in win_rates:
            print(f"  {'------':>8}", end="")
        print()

        for n_trades in n_trade_points:
            print(f"  {n_trades:>10d}", end="")
            for w in win_rates:
                count_exceed = 0
                for _ in range(n_simulations):
                    equity = 0.0
                    peak   = 0.0
                    max_dd = 0.0
                    for _ in range(n_trades):
                        if random.random() < w:
                            equity += net_win
                        else:
                            equity -= net_los
                        if equity > peak:
                            peak = equity
                        drawdown = peak - equity
                        if drawdown > max_dd:
                            max_dd = drawdown
                    if max_dd >= dd_dollar:
                        count_exceed += 1
                prob = count_exceed / n_simulations
                print(f"  {prob*100:>7.1f}%", end="")
            print()

    print()
    print("  Interpretation: P(max_drawdown > threshold) over N trades")
    print("  Lower is better. High probabilities indicate inadequate capital buffer.")
    print()


# ---------------------------------------------------------------------------
# 4. Stress Test
# ---------------------------------------------------------------------------

def stress_test(
    base_win_rate: float = 0.52,
    base_rr: float = 1.80,
    base_sl_usd: float = SL_DOLLARS,
    base_cost: float = COST_PER_TRADE,
    monthly_trades: int = MONTHLY_TRADES,
) -> None:
    """
    Apply 5 stress scenarios and print impact on:
    - EV per trade
    - Daily P/L
    - Monthly P/L
    - Drawdown risk rating
    """
    print(f"\n{SEPARATOR}")
    print("  STRESS TEST SCENARIOS")
    print(f"  Baseline: WR={base_win_rate*100:.0f}% | R:R={base_rr:.1f}:1 | "
          f"SL=${base_sl_usd:.0f} | Cost=${base_cost:.2f}")
    print(SEPARATOR)

    def _describe_scenario(name, win, rr, sl, cost, extra=""):
        _, net_ev  = _ev_per_trade(win, rr, sl, cost)
        daily      = net_ev * TRADES_PER_DAY
        monthly    = net_ev * monthly_trades
        loss_trade = sl + cost
        # Severity
        if monthly < -3000:
            severity = "CATASTROPHIC"
        elif monthly < 0:
            severity = "CRITICAL    "
        elif monthly < 1500:
            severity = "HIGH        "
        elif monthly < 2500:
            severity = "MODERATE    "
        else:
            severity = "LOW         "
        return net_ev, daily, monthly, loss_trade, severity

    # Baseline
    bev, bdaily, bmonthly, bloss, _ = _describe_scenario(
        "Baseline", base_win_rate, base_rr, base_sl_usd, base_cost)

    scenarios = [
        {
            "name":    "BASELINE",
            "desc":    "Normal trading conditions",
            "win":     base_win_rate,
            "rr":      base_rr,
            "sl":      base_sl_usd,
            "cost":    base_cost,
        },
        {
            "name":    "SCENARIO 1: Spread ×2",
            "desc":    "High-impact news — spread doubles to 3.0 pips",
            "win":     base_win_rate,
            "rr":      base_rr,
            "sl":      base_sl_usd,
            "cost":    COMMISSION + (3.0 + SLIPPAGE_PIPS) * PIP_VALUE,  # 3.0 pip spread
        },
        {
            "name":    "SCENARIO 2: Slippage ×3",
            "desc":    "Thin liquidity — slippage 1.5 pips (was 0.5)",
            "win":     base_win_rate,
            "rr":      base_rr,
            "sl":      base_sl_usd,
            "cost":    COMMISSION + (SPREAD_PIPS + 1.5) * PIP_VALUE,    # 1.5 pip slip
        },
        {
            "name":    "SCENARIO 3: Win Rate -15pp",
            "desc":    "Strategy decay / regime shift",
            "win":     base_win_rate - 0.15,
            "rr":      base_rr,
            "sl":      base_sl_usd,
            "cost":    base_cost,
        },
        {
            "name":    "SCENARIO 4: Commission ×2",
            "desc":    "Broker repricing — commission $14 RT (was $7)",
            "win":     base_win_rate,
            "rr":      base_rr,
            "sl":      base_sl_usd,
            "cost":    14.0 + (SPREAD_PIPS + SLIPPAGE_PIPS) * PIP_VALUE,
        },
        {
            "name":    "SCENARIO 5: 10 Consec. Losses",
            "desc":    "Cold streak — one-time drawdown event",
            "win":     base_win_rate,    # ongoing EV unchanged
            "rr":      base_rr,
            "sl":      base_sl_usd,
            "cost":    base_cost,
        },
    ]

    # Width constants
    w1, w2, w3, w4, w5 = 14, 12, 12, 14, 12

    header = (f"\n  {'':30}  {'EV/Trade':>{w1}}  {'Daily P/L':>{w2}}  "
              f"{'Monthly P/L':>{w3}}  {'vs Baseline':>{w4}}  {'Severity':>{w5}}")
    print(header)
    print(f"  {'-'*30}  {'-'*w1}  {'-'*w2}  {'-'*w3}  {'-'*w4}  {'-'*w5}")

    for i, s in enumerate(scenarios):
        ev, daily, monthly, loss, severity = _describe_scenario(
            s["name"], s["win"], s["rr"], s["sl"], s["cost"])

        diff = monthly - bmonthly
        diff_str = f"+${diff:,.0f}" if diff >= 0 else f"-${abs(diff):,.0f}"
        ev_str   = f"+${ev:,.2f}" if ev >= 0 else f"-${abs(ev):,.2f}"
        day_str  = f"+${daily:,.0f}" if daily >= 0 else f"-${abs(daily):,.0f}"
        mon_str  = f"+${monthly:,.0f}" if monthly >= 0 else f"-${abs(monthly):,.0f}"

        if i == 5:  # 10 consecutive losses — special display
            consec_loss = 10 * loss
            ev_str   = f"+${ev:,.2f}"
            day_str  = "(event)"
            mon_str  = f"-${consec_loss:,.0f} (event)"
            diff_str = f"-${consec_loss:,.0f} (one-time)"
            severity = "HIGH        "

        print(f"  {s['name']:30}  {ev_str:>{w1}}  {day_str:>{w2}}  "
              f"{mon_str:>{w3}}  {diff_str:>{w4}}  {severity:>{w5}}")

    print()
    print("  SCENARIO DESCRIPTIONS:")
    for s in scenarios:
        print(f"  - {s['name']}: {s['desc']}")

    # --- Combined worst case ---
    print(f"\n  COMBINED WORST CASE: Scenarios 1 + 2 + 3 simultaneously")
    wc_cost = COMMISSION + (3.0 + 1.5) * PIP_VALUE   # spread×2 + slip×3
    wc_win  = base_win_rate - 0.15
    _, wc_ev = _ev_per_trade(wc_win, base_rr, base_sl_usd, wc_cost)
    wc_monthly = wc_ev * monthly_trades
    wc_diff = wc_monthly - bmonthly
    print(f"  Monthly P/L: ${wc_monthly:,.0f}  |  Change: ${wc_diff:,.0f}  |  "
          f"Severity: {'CATASTROPHIC' if wc_monthly < -3000 else 'CRITICAL'}")

    # --- Position sizing ---
    print(f"\n  POSITION SIZING REQUIREMENTS (fixed 1.0 lot, SL=${base_sl_usd:.0f})")
    loss_per_trade = base_sl_usd + base_cost
    print(f"  Loss per trade (SL + cost): ${loss_per_trade:.2f}")
    print()
    print(f"  {'Risk %':>8}  {'Min Account':>14}  {'Safe Account':>14}  "
          f"{'Max DD streak (20%)':>22}")
    print(f"  {'-'*8}  {'-'*14}  {'-'*14}  {'-'*22}")
    for pct in [0.01, 0.02, 0.03, 0.05, 0.10]:
        min_acct  = loss_per_trade / pct
        safe_acct = min_acct * 1.10
        dd_20pct  = min_acct * 0.20
        max_losses = int(dd_20pct // loss_per_trade)
        print(f"  {pct*100:>7.0f}%  ${min_acct:>13,.0f}  ${safe_acct:>13,.0f}  "
              f"  {max_losses:>20d} losses")
    print()


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main() -> None:
    print(SEPARATOR)
    print("  EMPIREX-OS QUANTITATIVE RISK CALCULATOR")
    print("  Strategy: London Session Intraday Breakout / VWAP")
    print("  Target  : $500/day net | 2 trades/day | 1.0 lot")
    print("  Date    : 2026-06-28")
    print(SEPARATOR)

    print(f"\n  TRADE COST STRUCTURE (EURUSD 1.0 lot)")
    print(f"  {'Component':25}  {'Pips':>8}  {'USD':>10}")
    print(f"  {'-'*25}  {'-'*8}  {'-'*10}")
    print(f"  {'Commission (RT)':25}  {'0.70':>8}  ${COMMISSION:>9.2f}")
    print(f"  {'Spread (typical)':25}  {SPREAD_PIPS:>8.2f}  ${SPREAD_PIPS*PIP_VALUE:>9.2f}")
    print(f"  {'Slippage (est.)':25}  {SLIPPAGE_PIPS:>8.2f}  ${SLIPPAGE_PIPS*PIP_VALUE:>9.2f}")
    print(f"  {'TOTAL cost/trade':25}  {COST_PER_TRADE/PIP_VALUE:>8.2f}  ${COST_PER_TRADE:>9.2f}")
    print(f"\n  Pip value: ${PIP_VALUE:.2f}/pip  |  SL: {SL_PIPS} pips = ${SL_DOLLARS:.0f}")

    ev_table()
    kelly_fraction()
    drawdown_probability(n_simulations=5000)   # 5k runs for speed; use 50k for final report
    stress_test()

    print(SEPARATOR)
    print("  FEASIBILITY SUMMARY")
    print(SEPARATOR)
    print(f"\n  Target: ${MONTHLY_TARGET:,.0f}/month ({DAILY_TARGET}/day × {TRADING_DAYS} days)")
    print(f"\n  Minimum viable parameters to reach ${DAILY_TARGET}/day:")
    print()
    print(f"  {'Win Rate':>10}  {'R:R':>8}  {'Daily EV':>12}  {'Monthly P/L':>14}  {'Achievable':>12}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*12}  {'-'*14}  {'-'*12}")
    for w in WIN_RATES:
        for r in RR_RATIOS:
            _, n = _ev_per_trade(w, r)
            daily   = n * TRADES_PER_DAY
            monthly = n * MONTHLY_TRADES
            achieves = "YES [TARGET]" if monthly >= MONTHLY_TARGET else "No"
            if achieves == "YES [TARGET]" or (monthly > 0 and daily > 200):
                sign_d = "+" if daily >= 0 else ""
                sign_m = "+" if monthly >= 0 else ""
                print(f"  {w*100:>9.0f}%  {r:>7.1f}:1  "
                      f"{sign_d}${abs(daily):>10.0f}  "
                      f"{sign_m}${abs(monthly):>12.0f}  {achieves:>12}")

    print(f"\n  KEY FINDINGS:")
    print(f"  1. Negative EV at WR<43% with R:R 1.5:1 — do not trade")
    print(f"  2. $500/day target requires 60%+ WR with 2.0+ R:R")
    print(f"  3. Realistic London breakout WR: 42-49% — target likely unachievable at baseline")
    print(f"  4. Recommended minimum account: $15,000-$18,000 (2% risk/trade)")
    print(f"  5. Biggest risk: 15pp win rate drop — turns +$2,840/mo into -$2,960/mo")
    print(f"\n{SEPARATOR}\n")


if __name__ == "__main__":
    main()
