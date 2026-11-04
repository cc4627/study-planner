"""Settle past soccer picks and write picks for the coming matches.

Usage: python daily.py [CACHE_DIR]   (CACHE_DIR keeps last season's files between runs)

For each match in football-data.co.uk's fixtures: the bookmakers' favourite and its chance (from the average
odds, margin removed); goals over/under 2.5 and both teams to score (from the odds); and the corners and
yellow-cards calls: the expected count and the likelier side of the league's usual line, with its chance.
Each day's two most confident corner calls make the corner double; the two most confident calls with real
odds (result or goals, from two matches) make the daily double; and each match's favourite with its goals
call makes a match double. Once a match is played, its score, total corners and total yellow cards are added. Writes soccer/picks/YYYY-MM-DD.json and picks/index.json.
Paper only; no bets are placed.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fd  # noqa: E402
import goals as G  # noqa: E402
import stats as S  # noqa: E402

LONDON = ZoneInfo('Europe/London')
PICKS = os.path.join(HERE, 'picks')
MODEL = os.path.join(HERE, 'model.json')
KEEP_DAYS = 60
SETTLE_DAYS = 21


def load_model():
    try:
        with open(MODEL, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def result_pick(m):
    """The favourite ('H', 'D' or 'A') and its chance, from the average odds with the margin taken out."""
    if not (m['oh'] and m['od'] and m['oa']):
        return None
    inv = [1 / m['oh'], 1 / m['od'], 1 / m['oa']]
    p = [x / sum(inv) for x in inv]
    i = max(range(3), key=lambda k: p[k])
    return {'side': 'HDA'[i], 'p': round(p[i], 3), 'odds': (m['oh'], m['od'], m['oa'])[i]}


def count_call(tr, m, model):
    """Expected corners or cards, the league's usual line, and the likelier side with its chance."""
    f = tr.features(m)
    if not f or not model:
        return None
    mean = sum(S.expected(f, model))
    line = model['lines'].get(m['div'])
    if line is None:
        avg = tr.league_avg(m['div'])
        line = S.main_line(avg['h'] + avg['a'])
    side, p = S.call(mean, line, model['k'])
    return {'exp': round(mean, 1), 'line': line, 'side': side, 'p': round(p, 3)}


def odds_calls(m, pick):
    """Goals over/under 2.5 and both-to-score calls, and the match double: the favourite with the goals call,
    its chance from the score grid (the two are linked) and the two average prices multiplied."""
    c = G.calls(m)
    if not c:
        return None, None, None
    side = c['goals'][0]
    goals = {'side': side, 'p': round(c['goals'][1], 3), 'odds': m['over'] if side == 'over' else m['under']}
    btts = {'side': c['btts'][0], 'p': round(c['btts'][1], 3)}
    combo = None
    if pick and pick.get('odds') and goals['odds']:
        combo = {'p': round(G.joint(c['rates'], pick['side'], side), 3), 'odds': round(pick['odds'] * goals['odds'], 2)}
    return goals, btts, combo


def started(day, entry, now):
    return day < now.date() or (day == now.date() and (entry.get('time') or '00:00') <= now.strftime('%H:%M'))


def read(day):
    try:
        with open(os.path.join(PICKS, f'{day}.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write(day, doc):
    os.makedirs(PICKS, exist_ok=True)
    doc['matches'].sort(key=lambda e: (e.get('time') or '', e['league'], e['home']))
    with open(os.path.join(PICKS, f'{day}.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)


def choose_double(doc, day, now):
    """The day's two most confident corner calls, kept as they were once either match has kicked off."""
    by_key = {(e['home'], e['away']): e for e in doc['matches']}
    old = doc.get('double')
    if old and any(started(day, by_key.get(tuple(k), {}), now) for k in old['legs'] if tuple(k) in by_key):
        return old
    cand = [e for e in doc['matches'] if e.get('corners') and not started(day, e, now)]
    if len(cand) < 2:
        return old if old else None
    a, b = sorted(cand, key=lambda e: -e['corners']['p'])[:2]
    return {'legs': [[a['home'], a['away']], [b['home'], b['away']]], 'p': round(a['corners']['p'] * b['corners']['p'], 3)}


def best_leg(e):
    """A match's most confident call that has real odds: the result pick or the goals call."""
    legs = [(k, e[k]) for k in ('pick', 'goals') if e.get(k) and e[k].get('odds')]
    return max(legs, key=lambda kv: kv[1]['p']) if legs else None


def choose_daily(doc, day, now):
    """The day's double: the two most confident real-odds calls from two different matches, kept as they were
    once either match has kicked off."""
    by_key = {(e['home'], e['away']): e for e in doc['matches']}
    old = doc.get('daily')
    if old and any(started(day, by_key.get((l['home'], l['away']), {}), now) for l in old['legs']
                   if (l['home'], l['away']) in by_key):
        return old
    cand = [(e, best_leg(e)) for e in doc['matches'] if not started(day, e, now)]
    cand = [(e, leg) for e, leg in cand if leg]
    if len(cand) < 2:
        return old if old else None
    (a, la), (b, lb) = sorted(cand, key=lambda x: -x[1][1]['p'])[:2]
    return {'legs': [{'home': a['home'], 'away': a['away'], 'kind': la[0]}, {'home': b['home'], 'away': b['away'], 'kind': lb[0]}],
            'p': round(la[1]['p'] * lb[1]['p'], 3), 'odds': round(la[1]['odds'] * lb[1]['odds'], 2)}


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else None
    now = datetime.now(LONDON)
    today = now.date()
    cur = fd.season_code(today)
    prev = fd.season_code(date(today.year - 1 if today.month >= 7 else today.year - 2, 9, 1))
    models = load_model() or {}
    if 'beta_home' in models:  # an older corners-only model file
        models = {'corners': models}
    print('models:', ', '.join(models) or 'none (corners and cards left out)')

    hist = []
    for code, c in ((prev, cache), (cur, None)):
        for div in fd.LEAGUES:
            hist += [(m, code) for m in fd.season(div, code, c)]
    hist.sort(key=lambda x: (x[0]['date'], x[0]['time'], x[0]['div']))
    trackers = {s: S.Tracker(s) for s in S.STATS}
    results = {}
    for m, code in hist:
        for tr in trackers.values():
            tr.update(m, code)
        if fd.played(m):
            results[(m['date'], m['home'], m['away'])] = m
    print(f'{len(results)} played matches read ({prev} and {cur})')

    # Settle: scores and corners for matches already picked
    settled = 0
    for k in range(SETTLE_DAYS, -1, -1):
        day = today - timedelta(days=k)
        doc = read(day)
        if not doc:
            continue
        changed = False
        for e in doc['matches']:
            m = results.get((day, e['home'], e['away']))
            if m and 'ft' not in e:
                e['ft'] = [int(m['hg']), int(m['ag'])]
                e['cn'] = int(m['hc'] + m['ac'])
                if m.get('hy') is not None and m.get('ay') is not None:
                    e['yc'] = int(m['hy'] + m['ay'])
                changed = True
                settled += 1
        if changed:
            write(day, doc)
    print(f'settled {settled} matches')

    # Picks for the coming matches
    fx = [m for m in fd.fixtures() if m['date'] >= today]
    by_day = {}
    for m in fx:
        by_day.setdefault(m['date'], []).append(m)
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for day, ms in sorted(by_day.items()):
        doc = read(day) or {'date': str(day), 'matches': []}
        keep = {(e['home'], e['away']): e for e in doc['matches']}
        for m in ms:
            key = (m['home'], m['away'])
            if key in keep and started(day, keep[key], now):
                continue  # kicked off: the pick stays as it was
            pick = result_pick(m)
            goals, btts, combo = odds_calls(m, pick)
            keep[key] = {'time': m['time'], 'div': m['div'], 'league': fd.LEAGUES[m['div']], 'home': m['home'],
                         'away': m['away'], 'pick': pick, 'goals': goals, 'btts': btts, 'combo': combo,
                         'corners': count_call(trackers['corners'], m, models.get('corners')),
                         'cards': count_call(trackers['cards'], m, models.get('cards'))}
        doc['matches'] = list(keep.values())
        doc['updated'] = stamp
        doc['double'] = choose_double(doc, day, now)
        doc['daily'] = choose_daily(doc, day, now)
        write(day, doc)
        print(f'{day}: {len(ms)} fixtures, {len(doc["matches"])} matches on the page')

    dates = sorted(n[:-5] for n in os.listdir(PICKS) if n[:4].isdigit() and n.endswith('.json')) if os.path.isdir(PICKS) else []
    for old in dates[:-KEEP_DAYS]:
        os.remove(os.path.join(PICKS, old + '.json'))
    if dates:
        with open(os.path.join(PICKS, 'index.json'), 'w', encoding='utf-8') as f:
            json.dump({'dates': dates[-KEEP_DAYS:]}, f)


if __name__ == '__main__':
    main()
