"""One-off: map Sporting Life's racecard and results data (Next.js __NEXT_DATA__) from GitHub's runners."""
import json
import re
import sys
import time
import urllib.request

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
SL = 'https://www.sportinglife.com/racing'


def get(url):
    time.sleep(2)
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,*/*', 'Accept-Language': 'en-GB'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.geturl(), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, url, ''
    except Exception as e:
        return str(e)[:80], url, ''


def nextdata(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def schema(x, path='', depth=0, maxdepth=6):
    """Print a compact key tree with one example value per leaf; lists show their first element only."""
    pad = '  ' * depth
    if depth > maxdepth:
        return
    if isinstance(x, dict):
        for k, v in list(x.items())[:45]:
            if isinstance(v, (dict, list)):
                n = f'[{len(v)}]' if isinstance(v, list) else ''
                print(f'{pad}{k}{n}:')
                schema(v, path + '.' + k, depth + 1, maxdepth)
            else:
                print(f'{pad}{k} = {json.dumps(v)[:90]}')
    elif isinstance(x, list) and x:
        schema(x[0], path + '[0]', depth, maxdepth)


def probe(label, url, pick, maxdepth=6):
    s, f, h = get(url)
    print(f'===== {label}: {s} {f}')
    d = nextdata(h) if h else None
    if not d:
        print('  no __NEXT_DATA__')
        return None
    pp = d.get('props', {}).get('pageProps', {})
    print('pageProps keys:', list(pp))
    node = pick(pp)
    schema(node, maxdepth=maxdepth)
    sys.stdout.flush()
    return pp


first = lambda key: (lambda pp: (pp.get(key) or [None])[0] if isinstance(pp.get(key), list) else pp.get(key))

# Today's cards: one meeting in full (races, forecast, runners?)
today = probe('racecards today', SL + '/racecards', first('meetings'), 5)
# A past date's cards: is the betting forecast still there?
past = probe('racecards past date', SL + '/racecards/2026-10-28', first('meetings'), 4)
if past:
    ms = past.get('meetings') or []
    races = [r for m in ms for r in (m.get('races') or [])]
    print('past meetings', len(ms), 'races', len(races), 'with forecast', sum(1 for r in races if r.get('betting_forecast')))
# Results for a past date
res = probe('results past date', SL + '/results/2026-10-28', lambda pp: pp, 5)
sys.stdout.flush()
