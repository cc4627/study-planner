"""Settle past soccer picks and write picks for the coming matches.

Usage: python daily.py [CACHE_DIR]   (CACHE_DIR keeps last season's files between runs)

For each match in football-data.co.uk's fixtures: the bookmakers' favourite and its chance (from the average
odds, margin removed); goals over/under 2.5 and both teams to score (from the odds); and the corners and
yellow-cards calls: the expected count and the likelier side of the league's usual line, with its chance.
Champions, Europa and Conference League ties come from ESPN's free feed (soccer/europe.py), each side's corners
and cards starting from its own league; so do the next few days' domestic fixtures in any league football-data
hasn't listed yet, and national-team matches (Nations League, friendlies), which get the odds-based calls only. Each day's two most confident corner calls make the corner double; the two most confident calls with real
odds (result or goals, from two matches) make the daily double; and each match's favourite with its goals
call makes a match double. Once a match is played, its score, total corners and total yellow cards are added
(from ESPN the same evening, until football-data's results are in). Writes soccer/picks/YYYY-MM-DD.json and picks/index.json.
Paper only; no bets are placed.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import europe  # noqa: E402
import fd  # noqa: E402
import goals as G  # noqa: E402
import stats as S  # noqa: E402

LONDON = ZoneInfo('Europe/London')
PICKS = os.path.join(HERE, 'picks')
MODEL = os.path.join(HERE, 'model.json')
KEEP_DAYS = 60
SETTLE_DAYS = 21
EURO_AHEAD = 3  # days of Champions, Europa and Conference League fixtures to pick ahead
ESPN_SETTLE_DAYS = 2  # days back to settle domestic matches from ESPN while football-data's results catch up
DOMESTIC_AHEAD = 3  # days ahead to fill in from ESPN when football-data hasn't listed a league's fixtures
INTL_AHEAD = 3      # days of national-team fixtures to pick ahead
INTL_DIVS = {code for code, _ in europe.INTERNATIONAL.values()}


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


def count_call(tr, m, model, cross=False):
    """Expected corners or cards, the league's usual line, and the likelier side with its chance. A European tie
    (cross=True) starts each side from its own league and uses the line nearest the two leagues' average."""
    f = tr.features_cross(m) if cross else tr.features(m)
    if not f or not model:
        return None
    mean = sum(S.expected(f, model))
    line = None if cross else model['lines'].get(m['div'])
    if cross:
        totals = [model['avg_total'][d] for d in (tr.div_of.get(m['home']), tr.div_of.get(m['away'])) if d in model.get('avg_total', {})]
        line = S.main_line(sum(totals) / len(totals) if totals else f[2] + f[3])
    elif line is None:
        avg = tr.league_avg(m['div'])
        line = S.main_line(avg['h'] + avg['a'])
    side, p = S.call(mean, line, model['k'])
    return {'exp': round(mean, 1), 'line': line, 'side': side, 'p': round(p, 3)}


def odds_calls(m, pick):
    """Goals over/under 2.5 and both-to-score calls, and the match double: the favourite with the goals call,
    its chance from the score grid (the two are linked) and the two average prices multiplied."""
    if not (m.get('over') and m.get('under')):
        return None, None, None  # without the goals market the goal rates would rest on a guess
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


def league_teams(div_of):
    """{league: set of team names} from each side's latest league in the season files."""
    teams = {}
    for t, d in div_of.items():
        teams.setdefault(d, set()).add(t)
    return teams


def espn_settle(today, now, teams):
    """Scores, corners and yellow cards from ESPN for domestic matches that have kicked off in the last few days
    and that football-data hasn't posted a result for yet (it can take a day or two). Its own results, settled
    first, win whenever they're in."""
    settled = 0
    for k in range(ESPN_SETTLE_DAYS, -1, -1):
        day = today - timedelta(days=k)
        doc = read(day)
        if not doc:
            continue
        open_ = [e for e in doc['matches'] if e['div'] in europe.DOMESTIC and 'ft' not in e and started(day, e, now)]
        if not open_:
            continue
        comps = {europe.DOMESTIC[d]: (d, fd.LEAGUES[d]) for d in sorted({e['div'] for e in open_})}
        try:
            got = europe.matches(day, comps)
        except Exception as err:
            print(f'  ! ESPN domestic results for {day}: {err!r}')
            continue
        played_ = {}
        for m in got:
            if m['hg'] is None:
                continue
            known = teams.get(m['div'], set())
            h, a = europe.to_fd(m['home'], known), europe.to_fd(m['away'], known)
            if h and a:
                played_[(h, a)] = m
        changed = False
        for e in open_:
            m = played_.get((e['home'], e['away']))
            if not m:
                continue
            e['ft'] = [int(m['hg']), int(m['ag'])]
            if m['hc'] is not None and m['ac'] is not None:
                e['cn'] = int(m['hc'] + m['ac'])
            if m['hy'] is not None and m['ay'] is not None:
                e['yc'] = int(m['hy'] + m['ay'])
            settled += 1
            changed = True
        if changed:
            write(day, doc)
    print(f'ESPN settled {settled} domestic matches football-data has no result for yet')


def espn_fill(fx, today, div_of):
    """Domestic fixtures football-data hasn't listed yet (its fixture list can lag, often by a day before the weekend),
    from ESPN's free feed: each side matched to its name in the league's season file, with DraftKings odds where
    ESPN has them. Only for a league and day with no football-data fixtures, so its own average odds win when listed."""
    have = {(m['date'], m['div']) for m in fx}
    teams = league_teams(div_of)
    out, missed, used = [], set(), set()
    for k in range(DOMESTIC_AHEAD + 1):
        day = today + timedelta(days=k)
        comps = {europe.DOMESTIC[d]: (d, fd.LEAGUES[d]) for d in fd.LEAGUES if d in europe.DOMESTIC and (day, d) not in have}
        if not comps:
            continue
        try:
            got = europe.matches(day, comps, cards=False)
        except Exception as err:
            print(f'  ! ESPN domestic fixtures for {day}: {err!r}')
            continue
        for m in got:
            if m['state'] != 'pre':
                continue
            known = teams.get(m['div'], set())
            h, a = europe.to_fd(m['home'], known), europe.to_fd(m['away'], known)
            if not h or not a or h == a:
                missed.update(f"{t} ({m['div']})" for t, f in ((m['home'], h), (m['away'], a)) if not f)
                continue
            out.append(dict(m, home=h, away=a))
            used.update((h, a))
    by = {}
    for m in out:
        by[str(m['date'])] = by.get(str(m['date']), 0) + 1
    print(f'ESPN filled in {len(out)} domestic fixtures {by or ""}; names not matched: {", ".join(sorted(missed)) or "none"}')
    for d in sorted({x.rsplit('(', 1)[1].rstrip(')') for x in missed}):  # the league's names left over, to add an alias
        print(f'  {d} names with no ESPN match: {", ".join(sorted(teams.get(d, set()) - used))}')
    return out


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
    div_of = {**trackers['corners'].div_of, **trackers['cards'].div_of}
    espn_settle(today, now, league_teams(div_of))

    # European ties: settle from ESPN, then pick the coming ones
    known = set(trackers['corners'].div_of) | set(trackers['cards'].div_of)
    euro_settled = 0
    for k in range(3, -1, -1):
        day = today - timedelta(days=k)
        doc = read(day)
        open_divs = {e['div'] for e in (doc or {}).get('matches', []) if 'ft' not in e}
        played_ = {}
        try:
            if open_divs & {'UCL', 'UEL', 'UECL'}:
                played_.update({(m['home'], m['away']): m for m in europe.matches(day) if m['hg'] is not None})
            if open_divs & INTL_DIVS:
                played_.update({(m['home'], m['away']): m for m in europe.matches(day, europe.INTERNATIONAL, cards=False)
                                if m['hg'] is not None})
        except Exception as err:
            print(f'  ! European results for {day}: {err!r}')
            continue
        if not played_:
            continue
        for e in doc['matches']:
            m = played_.get((e['home'], e['away']))
            if m and 'ft' not in e:
                e['ft'] = [int(m['hg']), int(m['ag'])]
                if m['hc'] is not None and m['ac'] is not None:
                    e['cn'] = int(m['hc'] + m['ac'])
                if m['hy'] is not None and m['ay'] is not None:
                    e['yc'] = int(m['hy'] + m['ay'])
                euro_settled += 1
        write(day, doc)
    euro = []
    for k in range(EURO_AHEAD + 1):
        try:
            coming = europe.matches(today + timedelta(days=k))
        except Exception as err:
            print(f'  ! European fixtures for {today + timedelta(days=k)}: {err!r}')
            coming = []
        for m in coming:
            if m['state'] != 'pre':
                continue
            look = dict(m, home=europe.to_fd(m['home'], known) or m['home'], away=europe.to_fd(m['away'], known) or m['away'])
            m['_look'] = look
            euro.append(m)
    unmatched = sorted({t for m in euro for t, f in ((m['home'], m['_look']['home']), (m['away'], m['_look']['away'])) if t == f and t not in known})
    print(f'European: {euro_settled} settled, {len(euro)} coming; not in the domestic files: {", ".join(unmatched) or "none"}')
    intl, listed = [], {}
    for k in range(INTL_AHEAD + 1):
        day = today + timedelta(days=k)
        try:
            coming = europe.matches(day, europe.INTERNATIONAL, cards=False)
        except Exception as err:
            print(f'  ! international fixtures for {day}: {err!r}')
            coming = []
        for m in coming:
            if m['state'] != 'pre':
                continue
            listed[str(day)] = listed.get(str(day), 0) + 1
            if result_pick(m):  # nothing to call without prices; it joins once ESPN has them
                intl.append(dict(m, _intl=True))
    print(f'International: {listed or "none"} listed, {len(intl)} with prices')

    # Picks for the coming matches
    fx = [m for m in fd.fixtures() if m['date'] >= today]
    days = {}
    for m in fx:
        days[str(m['date'])] = days.get(str(m['date']), 0) + 1
    print(f'football-data fixtures: {days or "none"}')
    fx += espn_fill(fx, today, div_of) + euro + intl
    by_day = {}
    for m in fx:
        by_day.setdefault(m['date'], []).append(m)
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    where = {(m['home'], m['away']): m['date'] for m in fx}
    for day, ms in sorted(by_day.items()):
        doc = read(day) or {'date': str(day), 'matches': []}
        keep = {(e['home'], e['away']): e for e in doc['matches']}
        for m in ms:
            key = (m['home'], m['away'])
            if key in keep and started(day, keep[key], now):
                continue  # kicked off: the pick stays as it was
            pick = result_pick(m)
            goals, btts, combo = odds_calls(m, pick)
            cross = '_look' in m
            look = m.get('_look', m)
            counts = not m.get('_intl')  # the corners and cards models know clubs, not national teams
            keep[key] = {'time': m['time'], 'div': m['div'], 'league': m.get('league') or fd.LEAGUES[m['div']], 'home': m['home'],
                         'away': m['away'], 'pick': pick, 'goals': goals, 'btts': btts, 'combo': combo,
                         'corners': count_call(trackers['corners'], look, models.get('corners'), cross) if counts else None,
                         'cards': count_call(trackers['cards'], look, models.get('cards'), cross) if counts else None}
        # An older, not yet started entry sharing a side with one of this run's fixtures in the same league was
        # superseded (a side matched to the wrong team before, or a fixture moved): drop it.
        fresh = {(m['home'], m['away']): m['div'] for m in ms}
        for key, e in list(keep.items()):
            if key in fresh or started(day, e, now):
                continue
            if any(div == e['div'] and (e['home'] in k or e['away'] in k) for k, div in fresh.items()):
                print(f"  {day}: dropped {e['home']} v {e['away']}, superseded")
                del keep[key]
            elif where.get(key, day) != day:  # the same fixture is now listed on another day
                print(f"  {day}: dropped {e['home']} v {e['away']}, moved to {where[key]}")
                del keep[key]
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
