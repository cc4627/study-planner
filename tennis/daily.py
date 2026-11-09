"""Settle past tennis picks and write picks for the ATP and WTA singles matches of today and the next three days
(as far as the draws already name both players).

Usage: python daily.py [CACHE_DIR]

Elo ratings are rebuilt from every result since January 2024 (ESPN's free scoreboard feed). Each scheduled
match gets the higher-rated player as the pick, with their chance of winning, plus the first-set and total-games
calls and the chance of all three together (tennis/games.py), and bookmaker prices from tennisexplorer.com
(tennis/odds.py). Once played, the winner and
score are added. Writes tennis/picks/YYYY-MM-DD.json (UK dates) and picks/index.json. Paper only.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import elo as E  # noqa: E402
import espn  # noqa: E402
import games as G  # noqa: E402
import odds as O  # noqa: E402

LONDON = ZoneInfo('Europe/London')
PICKS = os.path.join(HERE, 'picks')
START = date(2024, 1, 1)
KEEP_DAYS = 60
SETTLE_DAYS = 7
AHEAD = 3  # days ahead to pick: later rounds join as their players are decided


def read(day):
    try:
        with open(os.path.join(PICKS, f'{day}.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write(day, doc):
    os.makedirs(PICKS, exist_ok=True)
    doc['matches'].sort(key=lambda e: (e['time'], e['event'], e['id']))
    with open(os.path.join(PICKS, f'{day}.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)


def score(m):
    return ' '.join(f'{a}-{b}' for a, b in m['sets'])


def choose_double(doc, day, now):
    """The day's two most confident picks from two matches, kept as they were once either has started."""
    by_id = {e['id']: e for e in doc['matches']}
    begun = lambda e: 'winner' in e or day < now.date() or (day == now.date() and e['time'] <= now.strftime('%H:%M'))
    old = doc.get('double')
    if old and any(begun(by_id[i]) for i in old['legs'] if i in by_id):
        return old
    cand = [e for e in doc['matches'] if not begun(e) and not e.get('new')]
    if len(cand) < 2:
        return old
    a, b = sorted(cand, key=lambda e: -e['p'])[:2]
    return {'legs': [a['id'], b['id']], 'p': round(a['p'] * b['p'], 3)}


MAX_DETAIL = 40  # match pages read per run for total-games prices


def attach_odds(today):
    """Bookmaker prices from tennisexplorer.com: both players' win prices on every picked match (kept as they
    were once the match is played), and the over/under price at the pick's games line, read once per match."""
    lists = {}
    for day, kinds in [(today - timedelta(days=1), ('results',)), (today, ('results', 'matches'))] + \
            [(today + timedelta(days=k), ('matches',)) for k in range(1, AHEAD + 2)]:
        rows = []
        for kind in kinds:
            try:
                rows += O.day_list(day, kind)
            except Exception as err:
                print(f'  ! odds list {kind} {day}: {err!r}')
        lists[day] = rows
    details = matched = 0
    for k in range(-1, AHEAD + 1):
        day = today + timedelta(days=k)
        doc = read(day)
        if not doc:
            continue
        pool = lists.get(day, []) + lists.get(day + timedelta(days=1), [])  # the site's dates are Central European
        changed = False
        for e in doc['matches']:
            row, swapped = O.find(e, pool)
            if not row:
                continue
            matched += 1
            if row['o1'] and row['o2'] and ('winner' not in e or not e.get('odds')):
                o = [row['o2'], row['o1']] if swapped else [row['o1'], row['o2']]
                if e.get('odds') != o:
                    e['odds'], changed = o, True
            if row['id'] and e.get('games') and 'gp' not in e and details < MAX_DETAIL:
                details += 1
                try:
                    prices = O.games_prices(row['id'])
                except Exception as err:
                    print(f'  ! games prices {row["id"]}: {err!r}')
                    prices = {}
                pr = prices.get(float(e['games']['line']))
                if pr:
                    e['gp'], changed = {'over': pr[0], 'under': pr[1]}, True
        if changed:
            write(day, doc)
    print(f'odds: {sum(len(v) for v in lists.values())} listed, {matched} picks matched, {details} match pages read')


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else None
    now = datetime.now(LONDON)
    today = now.date()
    seen = {m['id']: m for m in espn.history(START, today - timedelta(days=1), cache)}
    fresh = espn.around([today + timedelta(days=k) for k in range(AHEAD + 1)])
    seen.update({k: m for k, m in fresh.items() if m['state'] == 'post' and m['winner'] and m['sets']})
    rating = E.Elo()
    close = {'ATP': [], 'WTA': []}  # games in even best-of-3 matches over the last year, to tune the games model
    year_ago = (today - timedelta(days=365)).isoformat()
    for m in sorted(seen.values(), key=lambda m: (m['start'], m['id'])):
        if m['state'] == 'post' and m['winner'] and m['sets']:
            if m['start'] >= year_ago and not E.bo5(m):
                full, _, g = G.summary(m)
                if full and abs(rating.p(m['p1']['id'], m['p2']['id']) - 0.5) < 0.1:
                    close[m['tour'].upper()].append(g)
            w, l = (m['p1']['id'], m['p2']['id']) if m['winner'] == 1 else (m['p2']['id'], m['p1']['id'])
            rating.update(w, l)
    for tour, gs in close.items():
        if len(gs) >= 100:
            print(f'{tour}: even matches average {sum(gs) / len(gs):.1f} games; hold rate set to {G.calibrate(sum(gs) / len(gs), tour)}')
    print(f'{len(seen)} results rated; {len(fresh)} matches on the boards for today to {today + timedelta(days=AHEAD)}')
    known = {**seen, **fresh}

    # Settle
    settled = 0
    for k in range(SETTLE_DAYS, -1, -1):
        day = today - timedelta(days=k)
        doc = read(day)
        if not doc:
            continue
        changed = False
        for e in doc['matches']:
            m = known.get(e['id'])
            if m and m['state'] == 'post' and m['winner'] and 'winner' not in e:
                e['winner'] = m['winner']
                e['score'] = score(m) if m['sets'] else 'w/o'
                if m['sets']:
                    e['sets'] = [list(x) for x in m['sets']]
                changed = True
                settled += 1
        if changed:
            write(day, doc)
    print(f'settled {settled} matches')

    # Picks for scheduled matches
    stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
    by_day, where = {}, {}
    for m in fresh.values():
        if m['state'] != 'pre':
            continue
        t = espn.start_time(m).astimezone(LONDON)
        where[m['id']] = t.date()
        if not today <= t.date() <= today + timedelta(days=AHEAD):
            continue
        p1 = rating.p(m['p1']['id'], m['p2']['id'], E.bo5(m))
        pick, p = (1, p1) if p1 >= 0.5 else (2, 1 - p1)
        bo = 5 if E.bo5(m) else 3
        c = G.calls(p, m['tour'].upper(), bo)
        by_day.setdefault(t.date(), []).append({
            'id': m['id'], 'time': t.strftime('%H:%M'), 'tour': m['tour'].upper(), 'event': m['event'], 'round': m['round'],
            'p1': m['p1']['name'], 'p2': m['p2']['name'], 'pick': pick, 'p': round(p, 3), 'bo': bo,
            'new': min(rating.played(m['p1']['id']), rating.played(m['p2']['id'])) < 5,
            'first': round(c['first'], 3), 'games': {k: (round(v, 3) if k == 'p' else v) for k, v in c['games'].items()},
            'acca': round(c['acca'], 4),
        })
    for day in (today + timedelta(days=k) for k in range(AHEAD + 1)):
        entries, doc = by_day.get(day, []), read(day)
        if not entries and not doc:
            continue
        doc = doc or {'date': str(day), 'matches': []}
        keep = {e['id']: e for e in doc['matches']}
        for e in entries:
            old = keep.get(e['id'])
            if old and ('winner' in old or (day == today and old['time'] <= now.strftime('%H:%M'))):
                continue  # started or played: the pick stays as it was
            keep[e['id']] = e
        # drop draw slots picked before both players were known (older runs listed them as TBD), and matches
        # since rescheduled to another day
        doc['matches'] = [e for e in keep.values() if 'winner' in e or
                          ('TBD' not in (e['p1'], e['p2']) and where.get(e['id'], day) == day)]
        doc['updated'] = stamp
        doc['double'] = choose_double(doc, day, now)
        write(day, doc)
        print(f'{day}: {len(entries)} scheduled matches picked, {len(doc["matches"])} on the page')

    try:
        attach_odds(today)
    except Exception as err:  # odds are extra: never lose the picks over them
        print(f'  ! odds: {err!r}')

    dates = sorted(n[:-5] for n in os.listdir(PICKS) if n[:4].isdigit() and n.endswith('.json')) if os.path.isdir(PICKS) else []
    for old in dates[:-KEEP_DAYS]:
        os.remove(os.path.join(PICKS, old + '.json'))
    if dates:
        with open(os.path.join(PICKS, 'index.json'), 'w', encoding='utf-8') as f:
            json.dump({'dates': dates[-KEEP_DAYS:]}, f)


if __name__ == '__main__':
    main()
