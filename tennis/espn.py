"""Read ATP and WTA singles matches from ESPN's free public scoreboard feed (no account, read-only).

A day's scoreboard carries every tournament running around that day, with all of its matches: results
(winner, set scores) and scheduled ones. Requests are spaced out to keep the load light, and days more than
ten days back are cached, since their results no longer change.
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE = 'https://site.api.espn.com/apis/site/v2/sports/tennis'
UA = {'User-Agent': 'study-planner/1.0 (+https://github.com/cc4627/study-planner)'}
TOURS = ('atp', 'wta')
PAUSE = 1.0
_last = [0.0]
EASTERN = ZoneInfo('America/New_York')


def unscheduled(c):
    """Has the tournament still to give this match a day and time? ESPN says so with timeValid; where it doesn't
    carry that, its stand-in start of midnight US Eastern time gives it away."""
    tv = c.get('timeValid')
    if tv is not None:
        return tv is False
    try:
        t = datetime.strptime(c['date'].replace('Z', '+0000'), '%Y-%m-%dT%H:%M%z')
    except (KeyError, ValueError):
        return False
    return t.astimezone(EASTERN).strftime('%H:%M') == '00:00'


def scoreboard(tour, day, cache=None):
    fn = os.path.join(cache, f'{tour}-{day:%Y%m%d}.json') if cache else None
    old = day < datetime.now(timezone.utc).date() - timedelta(days=10)
    if fn and old and os.path.exists(fn):
        with open(fn, encoding='utf-8') as f:
            return json.load(f)
    wait = PAUSE - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    board = None
    for attempt in range(3):
        _last[0] = time.time()
        try:
            req = urllib.request.Request(f'{BASE}/{tour}/scoreboard?dates={day:%Y%m%d}', headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                board = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
        except Exception:
            pass
        time.sleep(3 * (attempt + 1))
    if board is not None and fn and old:
        os.makedirs(cache, exist_ok=True)
        with open(fn, 'w', encoding='utf-8') as f:
            json.dump(board, f)
    return board


def _player(x):
    a = x.get('athlete') if isinstance(x.get('athlete'), dict) else {}
    pid, name = a.get('id') or x.get('id'), a.get('displayName') or a.get('fullName')
    if not pid or not name or name.strip().upper() in ('TBD', 'TBA', 'BYE', 'QUALIFIER'):
        return None  # a draw slot still to be decided
    return {'id': str(pid), 'name': name}


def matches(board, tour):
    """Singles matches on a scoreboard: id, tournament, start (UTC), round, state, players, winner (1/2), sets."""
    for ev in (board or {}).get('events', []):
        for g in ev.get('groupings', []):
            if not (g.get('grouping') or {}).get('slug', '').endswith('singles'):
                continue
            for c in g.get('competitions', []):
                comps = c.get('competitors') or []
                if len(comps) != 2:
                    continue
                a, b = sorted(comps, key=lambda x: x.get('order') or 0)
                pa, pb = _player(a), _player(b)
                if not pa or not pb or not c.get('id') or not c.get('date'):
                    continue
                st = (c.get('status') or {}).get('type') or {}
                sets = [(int(x.get('value') or 0), int(y.get('value') or 0))
                        for x, y in zip(a.get('linescores') or [], b.get('linescores') or [])]
                yield {
                    'id': str(c['id']), 'tour': tour, 'event': ev.get('shortName') or ev.get('name') or '',
                    'major': bool(ev.get('major')), 'start': c['date'], 'round': (c.get('round') or {}).get('displayName') or '',
                    'state': st.get('state'), 'p1': pa, 'p2': pb, 'tbc': unscheduled(c), 'time_valid': c.get('timeValid'),
                    'winner': 1 if a.get('winner') else 2 if b.get('winner') else None, 'sets': sets,
                }


def start_time(m):
    return datetime.strptime(m['start'].replace('Z', '+0000'), '%Y-%m-%dT%H:%M%z')


def history(start, end, cache=None, step=4):
    """Every finished singles match (with set scores, so no walkovers) from start to end, oldest first."""
    seen = {}
    d = start
    while d <= end:
        for tour in TOURS:
            for m in matches(scoreboard(tour, d, cache), tour):
                if m['state'] == 'post' and m['winner'] and m['sets']:
                    seen[m['id']] = m
        d += timedelta(days=step)
    return sorted(seen.values(), key=lambda m: (m['start'], m['id']))


def around(days):
    """Every singles match on the scoreboards for the given days, fetched fresh, keyed by match id."""
    out = {}
    for d in days:
        for tour in TOURS:
            for m in matches(scoreboard(tour, d), tour):
                out[m['id']] = m
    return out


__all__ = ['history', 'around', 'start_time', 'date']
