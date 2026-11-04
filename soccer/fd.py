"""Read football-data.co.uk's free CSVs: past results with corners and odds, and upcoming fixtures with odds.

Season files: https://www.football-data.co.uk/mmz4281/SSSS/DIV.csv (e.g. 2526/E0.csv), updated twice a week.
Fixtures: https://www.football-data.co.uk/fixtures.csv, the coming days' matches with pre-match odds.
Read-only, no account. Requests are spaced out to keep the load on the site light.
"""
import csv
import io
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime

BASE = 'https://www.football-data.co.uk'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) study-planner/1.0'}
PAUSE = 1.0
_last = [0.0]

# Every division football-data.co.uk covers with corner counts (all of them, from 2026/27; the National
# League's files had none before that).
LEAGUES = {
    'E0': 'Premier League', 'E1': 'Championship', 'E2': 'League One', 'E3': 'League Two', 'EC': 'National League',
    'SC0': 'Scottish Prem', 'SC1': 'Scottish Champ', 'SC2': 'Scottish League 1', 'SC3': 'Scottish League 2',
    'D1': 'Bundesliga', 'D2': '2. Bundesliga', 'I1': 'Serie A', 'I2': 'Serie B', 'SP1': 'La Liga', 'SP2': 'La Liga 2',
    'F1': 'Ligue 1', 'F2': 'Ligue 2', 'N1': 'Eredivisie', 'B1': 'Belgian Pro League', 'P1': 'Primeira Liga',
    'T1': 'Super Lig', 'G1': 'Greek Super League',
}


def fetch(path, cache=None):
    """Bytes of BASE + path, or None if it isn't there. With cache (a folder), reuse a saved copy."""
    if cache:
        fn = os.path.join(cache, path.strip('/').replace('/', '_'))
        if os.path.exists(fn):
            with open(fn, 'rb') as f:
                return f.read()
    wait = PAUSE - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    body = None
    for attempt in range(3):
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + path, headers=UA), timeout=60) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
        except Exception:
            pass
        time.sleep(3 * (attempt + 1))
    if body is not None and cache:
        os.makedirs(cache, exist_ok=True)
        with open(fn, 'wb') as f:
            f.write(body)
    return body


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def day(s):
    s = (s or '').strip()
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def season_code(d):
    """'2526' for a date in the 2025/26 season (seasons start in July)."""
    y = d.year if d.month >= 7 else d.year - 1
    return f'{y % 100:02d}{(y + 1) % 100:02d}'


def row(r, div=None):
    """One match as a dict; scores, corners and shots are None for a fixture not yet played."""
    d = day(r.get('Date'))
    if not d or not r.get('HomeTeam') or not r.get('AwayTeam'):
        return None
    def odds(*keys):
        for k in keys:
            v = num(r.get(k))
            if v and v > 1:
                return v
        return None
    return {
        'div': div or r.get('Div'), 'date': d, 'time': (r.get('Time') or '').strip()[:5],
        'home': r['HomeTeam'].strip(), 'away': r['AwayTeam'].strip(),
        'hg': num(r.get('FTHG')), 'ag': num(r.get('FTAG')),
        'hc': num(r.get('HC')), 'ac': num(r.get('AC')), 'hs': num(r.get('HS')), 'as': num(r.get('AS')),
        'hy': num(r.get('HY')), 'ay': num(r.get('AY')), 'hf': num(r.get('HF')), 'af': num(r.get('AF')),
        'ref': (r.get('Referee') or '').strip() or None,
        'oh': odds('AvgH', 'BbAvH', 'B365H'), 'od': odds('AvgD', 'BbAvD', 'B365D'), 'oa': odds('AvgA', 'BbAvA', 'B365A'),
        'over': odds('Avg>2.5', 'BbAv>2.5', 'B365>2.5'), 'under': odds('Avg<2.5', 'BbAv<2.5', 'B365<2.5'),
    }


def season(div, code, cache=None):
    """Every match in a season file, in date order (played ones carry scores and corners)."""
    b = fetch(f'/mmz4281/{code}/{div}.csv', cache)
    if not b:
        return []
    out = [m for m in (row(r, div) for r in csv.DictReader(io.StringIO(b.decode('latin-1')))) if m]
    return sorted(out, key=lambda m: (m['date'], m['time']))


def history(codes, cache=None):
    """[(match, season code)] for every league and season listed, in date order."""
    out = []
    for code in codes:
        for div in LEAGUES:
            out += [(m, code) for m in season(div, code, cache)]
    return sorted(out, key=lambda x: (x[0]['date'], x[0]['time'], x[0]['div']))


def fixtures():
    """Upcoming matches in the leagues above, with pre-match odds."""
    b = fetch('/fixtures.csv')
    if not b:
        return []
    rows = csv.DictReader(io.StringIO(b.decode('utf-8-sig', 'replace')))
    return [m for m in (row(r) for r in rows) if m and m['div'] in LEAGUES]


def played(m):
    return None not in (m['hg'], m['ag'], m['hc'], m['ac'])


def today_uk():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Europe/London')).date()
