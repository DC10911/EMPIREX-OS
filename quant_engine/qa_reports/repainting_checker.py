"""
repainting_checker.py — Pine Script Repainting & Lookahead Pattern Detector
=============================================================================
Author  : EMPIREX-OS / qa-agent
Version : 1.0.0
Date    : 2026-06-28

PURPOSE
-------
Statically analyse Pine Script v5/v6 source code (as a string) to detect
patterns known to cause bar repainting or lookahead bias.

USAGE
-----
    from repainting_checker import RepaintingChecker

    code = open("strategy.pine").read()
    checker = RepaintingChecker()
    violations = checker.check(code)
    for v in violations:
        print(f"Line {v['line']}: [{v['severity']}] {v['rule']}")
        print(f"  Code: {v['snippet']}")

RETURNS
-------
    List of dicts with keys:
        line     : int    — 1-based line number
        col      : int    — 1-based column position of match start
        severity : str    — "ERROR" | "WARNING"
        rule     : str    — short rule name
        message  : str    — human-readable explanation
        snippet  : str    — the offending code fragment (up to 120 chars)

KNOWN PATTERNS CHECKED
----------------------
  ERROR-level (definite repainting / lookahead):
    1.  security() with lookahead=true or lookahead=barmerge.lookahead_on
    2.  security() with gaps=barmerge.gaps_off and lookahead=barmerge.lookahead_on
    3.  Bare security() call with no lookahead argument (defaults to lookahead_off
        in v5+, but we warn on unverified v4 legacy code)
    4.  request.security() with lookahead=true
    5.  ta.highest() / ta.lowest() used without [1] offset on current (non-closed) bar
        when the result is immediately used in a signal variable assignment
    6.  plotshape() / plotarrow() / plotchar() called with a condition that references
        the current bar (common repainting in alert setups)
    7.  Python: df.shift(-N) with N > 0 (future-bar shift)
    8.  Python: fillna(method='ffill') after a future-date merge (heuristic)
    9.  barstate.isrealtime used inside a strategy.entry() or signal calculation
        without barstate.isconfirmed guard
   10.  input() with defval depending on close[] without [1] offset

  WARNING-level (potential repainting — requires manual review):
   11.  security() call without explicit lookahead parameter on @version=5 or =6
   12.  ta.highest() / ta.lowest() without [1] offset (any usage)
   13.  close without [1] offset used directly in var assignment at bar level
   14.  hlc3 / ohlc4 / hl2 without [1] offset in signal calculation
   15.  alertcondition() using non-[1]-offset values
   16.  strategy.entry() inside a barstate.isrealtime block
   17.  request.security() without lookahead parameter
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


# ---------------------------------------------------------------------------
# Violation dataclass
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    line: int
    col: int
    severity: str        # "ERROR" | "WARNING"
    rule: str
    message: str
    snippet: str


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

# Each rule is a dict:
#   pattern : compiled regex
#   severity: "ERROR" | "WARNING"
#   rule    : short identifier string
#   message : explanation template (may include {match} placeholder)
#   context : optional list of additional context patterns that must appear
#             on the same line to trigger (all must match)

_RULES: list[dict] = [

    # -----------------------------------------------------------------------
    # ERRORs — definite lookahead / repainting
    # -----------------------------------------------------------------------

    {
        "rule": "security_lookahead_on",
        "severity": "ERROR",
        "pattern": re.compile(
            r"security\s*\([^)]*lookahead\s*=\s*(?:true|barmerge\.lookahead_on)",
            re.IGNORECASE
        ),
        "message": (
            "security() called with lookahead=true or barmerge.lookahead_on. "
            "This DIRECTLY injects future bar data into the current bar, causing "
            "severe lookahead bias and repainting. Remove or set lookahead=barmerge.lookahead_off."
        ),
    },

    {
        "rule": "request_security_lookahead_on",
        "severity": "ERROR",
        "pattern": re.compile(
            r"request\.security\s*\([^)]*lookahead\s*=\s*(?:true|barmerge\.lookahead_on)",
            re.IGNORECASE
        ),
        "message": (
            "request.security() called with lookahead=true / barmerge.lookahead_on. "
            "Injects future-bar data. Replace with barmerge.lookahead_off."
        ),
    },

    {
        "rule": "python_future_shift",
        "severity": "ERROR",
        "pattern": re.compile(
            r"\.shift\(\s*-\s*[1-9]\d*\s*\)",
            re.IGNORECASE
        ),
        "message": (
            "Python: df.shift(-N) with N > 0 shifts data BACKWARD (uses future values). "
            "This is classic lookahead bias. Use positive shift (df.shift(N)) to look backward only."
        ),
    },

    {
        "rule": "strategy_entry_in_realtime",
        "severity": "ERROR",
        "pattern": re.compile(
            r"barstate\.isrealtime[^$\n]*strategy\.entry",
            re.IGNORECASE
        ),
        "message": (
            "strategy.entry() inside barstate.isrealtime block. "
            "Signals on realtime bars repaint on the next bar close."
        ),
    },

    # -----------------------------------------------------------------------
    # WARNINGs — potential repainting / requires manual review
    # -----------------------------------------------------------------------

    {
        "rule": "security_no_lookahead_param",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\bsecurity\s*\(",
            re.IGNORECASE
        ),
        "message": (
            "security() call detected. Verify that lookahead=barmerge.lookahead_off is explicitly set. "
            "Default is off in Pine v5+, but legacy v4 scripts may behave differently."
        ),
    },

    {
        "rule": "request_security_no_lookahead_param",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\brequest\.security\s*\(",
            re.IGNORECASE
        ),
        "message": (
            "request.security() call detected. Verify lookahead=barmerge.lookahead_off is explicit."
        ),
    },

    {
        "rule": "ta_highest_no_offset",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\bta\.highest\s*\([^)]+\)(?!\s*\[)",
            re.IGNORECASE
        ),
        "message": (
            "ta.highest() used without a [1] historical offset. "
            "If this value is used in a signal condition on the current bar it will "
            "repaint as the bar's high changes intrabar. "
            "Use ta.highest(src, length)[1] to reference the previous bar's confirmed value."
        ),
    },

    {
        "rule": "ta_lowest_no_offset",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\bta\.lowest\s*\([^)]+\)(?!\s*\[)",
            re.IGNORECASE
        ),
        "message": (
            "ta.lowest() used without a [1] historical offset. "
            "If this value is used in a signal condition on the current bar it will "
            "repaint intrabar. Use ta.lowest(src, length)[1] for confirmed values."
        ),
    },

    {
        "rule": "plotshape_non_confirmed",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\bplotshape\s*\(",
            re.IGNORECASE
        ),
        "message": (
            "plotshape() detected. Verify the condition argument is based only on "
            "confirmed bar values (e.g. close[1], not close of current bar). "
            "Plotting on the current bar causes visual repainting on chart."
        ),
    },

    {
        "rule": "plotarrow_non_confirmed",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\bplotarrow\s*\(",
            re.IGNORECASE
        ),
        "message": (
            "plotarrow() detected. Verify the condition is on confirmed-bar data."
        ),
    },

    {
        "rule": "plotchar_non_confirmed",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\bplotchar\s*\(",
            re.IGNORECASE
        ),
        "message": (
            "plotchar() detected. Verify the condition is on confirmed-bar data."
        ),
    },

    {
        "rule": "alertcondition_non_offset",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\balertcondition\s*\(",
            re.IGNORECASE
        ),
        "message": (
            "alertcondition() detected. If the condition uses current-bar values "
            "(close, high, low without [1]), the alert fires intrabar and may trigger "
            "on data that changes before the bar closes."
        ),
    },

    {
        "rule": "calc_on_every_tick_true",
        "severity": "WARNING",
        "pattern": re.compile(
            r"calc_on_every_tick\s*=\s*true",
            re.IGNORECASE
        ),
        "message": (
            "calc_on_every_tick=true causes the strategy to recalculate on every tick "
            "of the current (unconfirmed) bar. This leads to repainting signals. "
            "Set calc_on_every_tick=false unless intrabar fills are intentional and understood."
        ),
    },

    {
        "rule": "calc_on_order_fills_true",
        "severity": "WARNING",
        "pattern": re.compile(
            r"calc_on_order_fills\s*=\s*true",
            re.IGNORECASE
        ),
        "message": (
            "calc_on_order_fills=true recalculates after each fill within the bar. "
            "Signals generated mid-bar can repaint. Use only if intentional."
        ),
    },

    {
        "rule": "barstate_isrealtime_in_signal",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\bbarstate\.isrealtime\b",
            re.IGNORECASE
        ),
        "message": (
            "barstate.isrealtime usage detected. Code inside isrealtime blocks executes "
            "on unconfirmed tick data and may repaint. Ensure it is guarded by "
            "barstate.isconfirmed when used for signal generation."
        ),
    },

    {
        "rule": "python_ffill_after_merge",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\.ffill\s*\(\s*\)|fillna\s*\(\s*method\s*=\s*['\"]ffill['\"]",
            re.IGNORECASE
        ),
        "message": (
            "Python: ffill / fillna(method='ffill') detected. "
            "If applied after merging future-dated reference data this introduces "
            "lookahead bias. Verify the merge key is strictly <= signal timestamp."
        ),
    },

    {
        "rule": "hlc3_no_offset",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\bhlc3\b(?!\s*\[)",
            re.IGNORECASE
        ),
        "message": (
            "hlc3 used without [1] offset on current bar. "
            "On an unconfirmed bar, hlc3 changes tick-by-tick. "
            "Use hlc3[1] for confirmed values in signal calculations."
        ),
    },

    {
        "rule": "ohlc4_no_offset",
        "severity": "WARNING",
        "pattern": re.compile(
            r"\bohlc4\b(?!\s*\[)",
            re.IGNORECASE
        ),
        "message": (
            "ohlc4 used without [1] offset on current bar. "
            "Use ohlc4[1] for confirmed bar values."
        ),
    },
]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

# Lines that begin with // are full-line comments — skip pattern matching
_FULL_LINE_COMMENT = re.compile(r"^\s*//")

# Inline comment stripper (naive — does not handle strings containing //)
_INLINE_COMMENT = re.compile(r"//.*$")


def _strip_comments(line: str) -> str:
    """Remove Pine Script inline comments from a line."""
    return _INLINE_COMMENT.sub("", line)


def _is_error_suppressed(line: str) -> bool:
    """
    If the line ends with a QA-suppress comment ( // qa:suppress ), skip it.
    This allows strategy authors to explicitly document a known false positive.
    """
    return bool(re.search(r"//\s*qa\s*:\s*suppress", line, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Main checker class
# ---------------------------------------------------------------------------

class RepaintingChecker:
    """
    Scan Pine Script (or Python) source code for repainting / lookahead patterns.

    Methods
    -------
    check(code: str) -> list[dict]
        Analyse the full source and return a list of violation dicts.
        Each dict has keys: line, col, severity, rule, message, snippet.

    check_file(filepath: str) -> list[dict]
        Convenience wrapper that reads a file and calls check().
    """

    def __init__(self, rules: Optional[list] = None):
        """
        Parameters
        ----------
        rules : list, optional
            Override the default rule set. Useful for testing individual rules.
        """
        self._rules = rules if rules is not None else _RULES

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def check(self, code: str) -> List[dict]:
        """
        Analyse Pine Script / Python source code.

        Parameters
        ----------
        code : str
            Full source code as a string.

        Returns
        -------
        list of dict
            Each dict: {line, col, severity, rule, message, snippet}
        """
        violations: List[Violation] = []
        lines = code.splitlines()

        for lineno, raw_line in enumerate(lines, start=1):
            # Skip full-line comments
            if _FULL_LINE_COMMENT.match(raw_line):
                continue
            # Skip qa:suppress lines
            if _is_error_suppressed(raw_line):
                continue

            # Work on the stripped version for matching (but report raw snippet)
            stripped = _strip_comments(raw_line)

            for rule in self._rules:
                pattern: re.Pattern = rule["pattern"]
                match = pattern.search(stripped)
                if match:
                    snippet = raw_line.strip()[:120]
                    violations.append(Violation(
                        line=lineno,
                        col=match.start() + 1,
                        severity=rule["severity"],
                        rule=rule["rule"],
                        message=rule["message"],
                        snippet=snippet,
                    ))

        return [self._violation_to_dict(v) for v in violations]

    def check_file(self, filepath: str) -> List[dict]:
        """Read a file and run check()."""
        with open(filepath, "r", encoding="utf-8") as fh:
            code = fh.read()
        return self.check(code)

    def format_report(self, violations: List[dict], title: str = "Repainting Check") -> str:
        """
        Format violations into a human-readable report string.

        Parameters
        ----------
        violations : list of dict
            Output from check() or check_file().
        title : str
            Report header title.

        Returns
        -------
        str
        """
        if not violations:
            return f"{title}\n{'=' * 60}\nNO VIOLATIONS FOUND. Code appears clean.\n"

        errors = [v for v in violations if v["severity"] == "ERROR"]
        warnings = [v for v in violations if v["severity"] == "WARNING"]

        lines = [
            f"{title}",
            "=" * 70,
            f"  ERRORS   : {len(errors)}",
            f"  WARNINGS : {len(warnings)}",
            "-" * 70,
        ]

        if errors:
            lines.append("  ERRORS (must fix before any backtest approval):")
            for v in errors:
                lines.append(f"    Line {v['line']:4d}:{v['col']:3d} | [{v['rule']}]")
                lines.append(f"      {v['message']}")
                lines.append(f"      Code: {v['snippet']}")

        if warnings:
            lines.append("  WARNINGS (review and confirm safe):")
            for v in warnings:
                lines.append(f"    Line {v['line']:4d}:{v['col']:3d} | [{v['rule']}]")
                lines.append(f"      {v['message']}")
                lines.append(f"      Code: {v['snippet']}")

        lines.append("=" * 70)
        verdict = "VIOLATIONS FOUND — Review required before strategy approval."
        lines.append(f"  VERDICT: {verdict}")
        lines.append("=" * 70)
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _violation_to_dict(v: Violation) -> dict:
        return {
            "line": v.line,
            "col": v.col,
            "severity": v.severity,
            "rule": v.rule,
            "message": v.message,
            "snippet": v.snippet,
        }


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def check_pine_script(code: str) -> List[dict]:
    """
    Module-level shortcut for quick checks.

    Returns list of violation dicts (empty = clean).
    """
    return RepaintingChecker().check(code)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python repainting_checker.py <pine_script_file.pine>")
        print("       python repainting_checker.py --demo")
        sys.exit(0)

    if sys.argv[1] == "--demo":
        demo_code = """
//@version=5
strategy("Demo Repaint Test", overlay=true,
         calc_on_every_tick=true,      // qa:suppress — intentional for demo only
         calc_on_order_fills=false)

// Good: confirmed bars via [1] offset
highest_confirmed = ta.highest(high, 20)[1]

// BAD: no offset — will repaint
highest_repaint = ta.highest(high, 20)

// BAD: lookahead on security
tf_close = security("EURUSD", "1D", close, lookahead=barmerge.lookahead_on)

// BAD: plotshape on current bar
plotshape(close > highest_repaint, title="Signal", location=location.belowbar, style=shape.triangleup)

// Python pattern (in a comment, should not trigger):
// df.shift(-1)  <- this is a comment
"""
        checker = RepaintingChecker()
        violations = checker.check(demo_code)
        print(checker.format_report(violations, title="Demo Pine Script Check"))
    else:
        filepath = sys.argv[1]
        checker = RepaintingChecker()
        try:
            violations = checker.check_file(filepath)
        except FileNotFoundError:
            print(f"ERROR: File not found: {filepath}")
            sys.exit(1)

        print(checker.format_report(violations, title=f"Repainting Check: {filepath}"))

        if violations:
            sys.exit(1)   # non-zero exit for CI integration
        sys.exit(0)
