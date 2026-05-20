import re
try:
    s = open('home-live.html', encoding='utf-8').read()
    m = re.search(r'<script type="text/babel">(.*?)</script>', s, re.S)
    if m:
        js = m.group(1)
        print(f"len {len(js)}")
        print(f"lines {js.count('\n')}")
    else:
        print("Script tag not found")
except Exception as e:
    print(f"Error: {e}")
