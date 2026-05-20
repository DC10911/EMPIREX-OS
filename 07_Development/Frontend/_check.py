import re
src = open('home-live.html', encoding='utf-8').read()
m = re.search(r'<script type="text/babel">(.*?)</script>', src, re.S)
if not m:
    print("NO BABEL BLOCK"); raise SystemExit(1)
js = m.group(1)
print("babel js len:", len(js))
# count balanced braces & parens at top-level (rough)
opens = js.count('{'); closes = js.count('}')
print("braces  open=%d close=%d delta=%d" % (opens, closes, opens-closes))
opens = js.count('('); closes = js.count(')')
print("parens  open=%d close=%d delta=%d" % (opens, closes, opens-closes))
opens = js.count('['); closes = js.count(']')
print("bracks  open=%d close=%d delta=%d" % (opens, closes, opens-closes))
# find newly added function defs
for name in ["MarketTape","MarketHeatmap","MarketPulse","WatchlistPanel","RiskEnginePanel","NewsPanel","StatusDot","Hero","SetupCards","AiInsight"]:
    n = len(re.findall(r"function "+name+r"\b", js))
    print("def %-18s count=%d" % (name, n))
