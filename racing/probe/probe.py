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
    try:
        data = json.loads(nd.group(1)) if nd else (json.loads(h) if h and h[0] in '{[' else {})
    except ValueError:
        data = {}
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
day2 = str(datetime.now(ZoneInfo('Europe/London')).date() + timedelta(days=2))
report('two days ahead', f'{B}/racing/racecards/{day2}')
race = sorted(set(re.findall(rf'href="(/racing/racecards/{tom}/[^"]+/racecard/\d+/[^"]*)"', h)))
print('tomorrow race links on index:', race)
if race:
    s_, f_, h2 = get(B + race[0])
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h2, re.S)
    pp = json.loads(nd.group(1))['props']['pageProps'] if nd else {}
    ms = pp.get('meetings') or []
    print(f'race page {s_}: {len(ms)} meetings')
    for m in ms:
        if not isinstance(m, dict):
            continue
        sm = m.get('meeting_summary') or {}
        c = sm.get('course') or {}
        print('   ', sm.get('date'), c.get('name'), (c.get('country') or {}).get('long_name'), 'races:', len(m.get('races') or []))
    links = sorted(set(re.findall(rf'href="(/racing/racecards/{tom}/[^"]+/racecard/\d+/[^"]*)"', h2)))
    print('race page links to tomorrow:', len(links), links[:5])
