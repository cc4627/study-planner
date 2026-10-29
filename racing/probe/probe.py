"""One-off: map Sporting Life's per-race racecard and result pages from GitHub's runners."""
import json
import re
import sys
import time
import urllib.request
from urllib.parse import urljoin

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
SL = 'https://www.sportinglife.com'


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


def pageprops(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)).get('props', {}).get('pageProps', {}) if m else {}


def schema(x, depth=0, maxdepth=3):
    pad = '  ' * depth
    if depth > maxdepth:
        return
    if isinstance(x, dict):
        for k, v in x.items():
            if isinstance(v, (dict, list)):
                print(f'{pad}{k}{f"[{len(v)}]" if isinstance(v, list) else ""}:')
                schema(v, depth + 1, maxdepth)
            else:
                print(f'{pad}{k} = {json.dumps(v)[:80]}')
    elif isinstance(x, list) and x:
        schema(x[0], depth, maxdepth)


def first_link(base, html, pattern):
    for h in re.findall(r'href="([^"#?]+)"', html):
        if re.search(pattern, h):
            return urljoin(base, h)


def race_page(label, url):
    s, f, h = get(url)
    print(f'===== {label}: {s} {f}')
    pp = pageprops(h) if h else {}
    print('pageProps keys:', list(pp))
    race = pp.get('race') or next((v for v in pp.values() if isinstance(v, dict) and 'rides' in v), None)
    if not race:
        print('no race object; top-level schema:')
        schema(pp, maxdepth=2)
        return
    rides = race.get('rides') or []
    print('race keys:', [k for k in race if k != 'rides'])
    for k in ('betting_forecast', 'going', 'distance', 'has_handicap', 'race_stage'):
        print(f'  {k} = {json.dumps(race.get(k))[:200]}')
    if race.get('race_summary'):
        print('race_summary keys:', list(race['race_summary']))
    print(f'rides: {len(rides)}; first ride schema:')
    if rides:
        schema(rides[0], 1, 3)
    for r in rides[:4]:
        horse = (r.get('horse') or {}).get('name')
        print('  ride:', horse, '| pos', r.get('finish_position'), '| status', r.get('ride_status'),
              '| sp', json.dumps(r.get('starting_price') or r.get('betting'))[:120])
    sys.stdout.flush()


s, f, h = get(SL + '/racing/racecards')
print('== today index', s, 'nextTenRaces:', len(pageprops(h).get('nextTenRaces') or []))
card = first_link(f, h, r'^/racing/racecards/\d{4}-\d{2}-\d{2}/[^/]+/racecard/\d+')
race_page('todays racecard', card)

for day in ('2026-10-28', '2026-08-01'):
    s, f, h = get(f'{SL}/racing/results/{day}')
    ms = pageprops(h).get('meetings') or []
    print(f'== results {day}: {s}, meetings {len(ms)}, races {sum(len(m.get("races") or []) for m in ms)}')
    link = first_link(f, h, r'^/racing/results/\d{4}-\d{2}-\d{2}/[^/]+/\d+')
    print('   first result link:', link)
    if link:
        race_page(f'result race {day}', link)
