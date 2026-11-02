"""One-off: find where Sporting Life serves tomorrow's racecards (temporary; removed after use)."""
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
B = 'https://www.sportinglife.com'
tom = str(datetime.now(ZoneInfo('Europe/London')).date() + timedelta(days=1))


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/json,*/*', 'Accept-Language': 'en-GB'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.geturl(), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, url, ''
    except Exception as e:
        return str(e)[:60], url, ''


def report(label, url):
    s, f, h = get(url)
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    data = json.loads(nd.group(1)) if nd else (json.loads(h) if h[:1] in '{[' else {})
    pp = data.get('props', {}).get('pageProps', data.get('pageProps', data)) if isinstance(data, dict) else {}
    dates = sorted({((m.get('meeting_summary') or {}).get('date')) for m in (pp.get('meetings') or []) if isinstance(m, dict)}) if isinstance(pp, dict) else []
    links = sorted(set(re.findall(rf'href="(/racing/racecards/{tom}/[^"]+)"', h)))
    print(f'== {label}: {s} -> {f} | bytes {len(h)} | meeting dates {dates} | links to {tom}: {len(links)}')
    for l in links[:6]:
        print('     ', l)
    if isinstance(pp, dict):
        print('     pageProps keys:', sorted(pp)[:15])
    sys.stdout.flush()
    return h, data


h, data = report('index', B + '/racing/racecards')
build = data.get('buildId') if isinstance(data, dict) else None
print('buildId', build, '| query of index:', data.get('query') if isinstance(data, dict) else None, '| page:', data.get('page') if isinstance(data, dict) else None)
for label, path in [('dated', f'/racing/racecards/{tom}'), ('tomorrow', '/racing/racecards/tomorrow'),
                    ('query', f'/racing/racecards?date={tom}'), ('fixtures', '/racing/fixtures'),
                    ('dated-racecards', f'/racing/racecards/{tom}/racecards')]:
    report(label, B + path)
if build:
    report('next-data dated', f'{B}/_next/data/{build}/racing/racecards/{tom}.json')
    report('next-data dated+query', f'{B}/_next/data/{build}/racing/racecards/{tom}.json?date={tom}')
# any other date-looking links on the index
print('index links with dates:', sorted(set(re.findall(r'href="(/racing/racecards/\d{4}-\d{2}-\d{2}[^"]*)"', h)))[:12])
