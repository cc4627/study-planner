"""Do the tennis picks beat the bookmakers? The Elo pick for every ATP and WTA singles match of the last year,
predicted before it was played, settled at the prices tennisexplorer.com lists for it.

Usage: python odds_backtest.py CACHE_DIR [--te TE_CACHE_DIR] [--out ODDS.md]

Ratings are built exactly as for the daily picks (tennis/elo.py, every result since January 2024 from ESPN).
Prices come from tennisexplorer's daily results lists (its robots.txt allows them), one page per tour per day,
spaced out and cached, so a rerun reads nothing twice. Matches that ended in a retirement are left out
(bookmakers settle those differently); walkovers never reach the results. Paper only; no bets are placed.
"""
import math
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elo as E  # noqa: E402
import espn  # noqa: E402
import games as G  # noqa: E402
import odds as O  # noqa: E402

START = date(2024, 1, 1)
PAUSE = 2.0
TIME_BUDGET = 40 * 60  # seconds of tennisexplorer reading per run; a rerun carries on from the cache
_t0 = time.time()
_last = [0.0]
_stop = []


def te_page(cache, day, typ):
    """A results list page from tennisexplorer, from the cache folder when read before. None once refused or over budget."""
    fn = os.path.join(cache, f'results-{typ}-{day:%Y%m%d}.html')
    if os.path.exists(fn):
        with open(fn, encoding='utf-8') as f:
            return f.read()
    if not _stop and time.time() - _t0 > TIME_BUDGET:
        _stop.append('time budget used; a rerun carries on from the cache')
    if _stop:
        return None
    wait = PAUSE - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(O.BASE + O.list_path(day, 'results', typ), headers=O.UA), timeout=30) as r:
            page = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            _stop.append(f'HTTP {e.code}')  # refused or slow down: stop reading for this run
        return None
    except Exception:
        return None
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    with open(fn, 'w', encoding='utf-8') as f:
        f.write(page)
    return page


def lists_for(cache, days, busy):
    """{date: rows} from the ATP and WTA singles results lists; the 'all' list if the per-tour ones come back empty on
    a day ESPN has matches (busy)."""
    out, typed_empty = {}, 0
    for d in sorted(days):
        rows = []
        for typ in ('atp-single', 'wta-single'):
            page = te_page(cache, d, typ)
            rows += O.parse_list(page) if page else []
        if not rows and not _stop and d in busy:
            typed_empty += 1
            page = te_page(cache, d, 'all')
            rows = O.parse_list(page) if page else []
        out[d] = rows
    print(f'tennisexplorer: {len(out)} days, {sum(len(v) for v in out.values())} rows, {typed_empty} days needed the full list'
          + (f'; stopped early ({_stop[0]})' if _stop else ''))
    return out


def stat(bets):
    """(bets, won, staked, P/L, ROI, t) for a list of (odds, won)."""
    n = len(bets)
    if not n:
        return None
    pl = [o - 1 if w else -1.0 for o, w in bets]
    mean = sum(pl) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in pl) / (n - 1)) if n > 1 else 0
    return n, sum(1 for _, w in bets if w), n, sum(pl), mean, (mean / (sd / math.sqrt(n)) if sd else 0)


def row(name, bets):
    s = stat(bets)
    if not s or s[0] < 30:
        return f'| {name} | {s[0] if s else 0} | – | – | – |'
    n, w, _, pl, roi, t = s
    return f'| {name} | {n} | {w / n:.1%} | {pl:+.1f} | {roi:+.1%} (t {t:+.1f}) |'


def main():
    args = sys.argv[1:]
    cache = args[0]
    out_path = args[args.index('--out') + 1] if '--out' in args else None
    te_cache = args[args.index('--te') + 1] if '--te' in args else os.path.join(cache, 'te')
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    test_from = end - timedelta(days=365)
    mid = test_from + timedelta(days=183)
    hist = espn.history(START, end, cache)
    rating = E.Elo()
    test = []
    for m in hist:
        a, b = m['p1']['id'], m['p2']['id']
        day = espn.start_time(m).date()
        if day >= test_from:
            full, _, _ = G.summary(m, 5 if E.bo5(m) else 3)
            if full:
                p1 = rating.p(a, b, E.bo5(m))
                test.append({'m': m, 'day': day, 'p1': p1, 'known': min(rating.played(a), rating.played(b)) >= 10})
        w, l = (a, b) if m['winner'] == 1 else (b, a)
        rating.update(w, l)
    print(f'{len(hist)} ESPN results read; {len(test)} completed matches from {test_from} to {end}')

    days = set()
    for x in test:
        days.update(x['day'] + timedelta(days=k) for k in (-1, 0, 1))
    lists = lists_for(te_cache, {d for d in days if d <= end}, {x['day'] for x in test})

    recs = []
    for x in test:
        m = x['m']
        pool = []
        for k in (0, 1, -1):  # tennisexplorer dates its lists in Central European time
            pool += lists.get(x['day'] + timedelta(days=k), [])
        r, swapped = O.find({'p1': m['p1']['name'], 'p2': m['p2']['name']}, pool)
        if not r or not r['o1'] or not r['o2']:
            continue
        o1, o2 = (r['o2'], r['o1']) if swapped else (r['o1'], r['o2'])
        if 1 / o1 + 1 / o2 < 0.98 or 1 / o1 + 1 / o2 > 1.25:
            continue  # not a sensible two-way price: a misread or a mismatch
        recs.append({'day': x['day'], 'tour': m['tour'].upper(), 'q1': x['p1'], 'o': (o1, o2), 'w': m['winner'], 'known': x['known'],
                     'qual': 'qualif' in m['round'].lower()})
    print(f'{len(recs)} matched to prices')

    L = ['# Tennis picks against the bookmakers', '']
    if len(recs) < 300:
        L.append(f'Not enough matches with prices yet ({len(recs)} of {len(test)}).' + (f' Reading stopped early ({_stop[0]}); a rerun carries on.' if _stop else ''))
        return finish(L, out_path)

    def pick(r):  # (odds, won, chance) for the Elo pick
        s = 1 if r['q1'] >= 0.5 else 2
        return r['o'][s - 1], r['w'] == s, r['q1'] if s == 1 else 1 - r['q1']

    def fav(r):
        if r['o'][0] == r['o'][1]:
            return None
        s = 1 if r['o'][0] < r['o'][1] else 2
        return s

    def value(r, x):
        """The side whose Elo chance x its price is at least 1 + x (the bigger edge if both), as (odds, won)."""
        best = None
        for s in (1, 2):
            q = r['q1'] if s == 1 else 1 - r['q1']
            edge = q * r['o'][s - 1] - 1
            if edge >= x and (best is None or edge > best[0]):
                best = (edge, r['o'][s - 1], r['w'] == s)
        return best and best[1:]

    def market_q(r):
        a, b = 1 / r['o'][0], 1 / r['o'][1]
        return a / (a + b)

    first = [r for r in recs if r['day'] < mid]
    second = [r for r in recs if r['day'] >= mid]
    margin = sum(1 / r['o'][0] + 1 / r['o'][1] - 1 for r in recs) / len(recs)
    acc = lambda xs, f: sum(1 for r in xs if f(r)) / len(xs)
    ll = lambda q, w: -math.log(q if w == 1 else 1 - q)
    L += [f'{len(recs)} ATP and WTA singles matches from {test_from} to {end}, each predicted from ratings built only on '
          f'earlier results (every ESPN result since {START:%B %Y}), matched to the prices on tennisexplorer.com\'s results lists '
          f'({len(test)} completed matches in all; retirements left out). The bookmaker margin averages {margin:.1%}. '
          '€1 per bet; P/L in euros; t is how many standard errors the return is from zero (beyond about ±2 is unlikely to be luck).'
          + (f' Reading stopped early ({_stop[0]}), so some days have no prices yet.' if _stop else ''), '',
          '## Who predicts better: the ratings or the market?', '',
          '| | Picked the winner | Log loss (lower is better) |', '|---|---|---|',
          f"| Elo ratings (the site's pick) | {acc(recs, lambda r: (r['q1'] >= 0.5) == (r['w'] == 1)):.1%} | {sum(ll(r['q1'], r['w']) for r in recs) / len(recs):.4f} |",
          f"| Bookmakers' prices, margin removed | {acc(recs, lambda r: fav(r) == r['w']):.1%} | {sum(ll(market_q(r), r['w']) for r in recs) / len(recs):.4f} |",
          '', '## What €1 a match would have returned', '',
          '| Bet | Bets | Won | P/L | Return per €1 |', '|---|---|---|---|---|']
    L.append(row('The Elo pick, every match', [pick(r)[:2] for r in recs]))
    L.append(row("The bookmakers' favourite", [(min(r['o']), fav(r) == r['w']) for r in recs if fav(r)]))
    L.append(row("The bookmakers' underdog", [(max(r['o']), fav(r) != r['w']) for r in recs if fav(r)]))
    L.append(row('The Elo pick when it is also the favourite', [pick(r)[:2] for r in recs if fav(r) and pick(r)[0] == min(r['o'])]))
    L.append(row('The Elo pick when the bookmakers make it the underdog', [pick(r)[:2] for r in recs if fav(r) and pick(r)[0] == max(r['o'])]))
    for tour in ('ATP', 'WTA'):
        L.append(row(f'The Elo pick, {tour} only', [pick(r)[:2] for r in recs if r['tour'] == tour]))
    L.append(row('The Elo pick, both players with 10+ rated matches', [pick(r)[:2] for r in recs if r['known']]))
    L.append(row('The Elo pick, main draw only', [pick(r)[:2] for r in recs if not r['qual']]))

    L += ['', '## The Elo pick by its price', '', '| Pick priced | Bets | Won | P/L | Return per €1 |', '|---|---|---|---|---|']
    for lo, hi in ((1.0, 1.3), (1.3, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 100)):
        L.append(row(f'{lo:.2f} to {hi:.2f}' if hi < 100 else f'{lo:.2f} or more', [pick(r)[:2] for r in recs if lo <= pick(r)[0] < hi]))
    L += ['', '## The Elo pick by the chance it was given', '', '| Chance given | Bets | Won | P/L | Return per €1 |', '|---|---|---|---|---|']
    for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)):
        L.append(row(f'{lo:.0%}-{min(hi, 1):.0%}', [pick(r)[:2] for r in recs if lo <= pick(r)[2] < hi]))

    L += ['', '## Value bets: back whichever player the ratings rate above the price', '',
          "Bet only when the Elo chance × the price is at least 1 + the edge, on either player. Run separately on the "
          f"two halves of the year ({test_from} to {mid - timedelta(days=1)} and {mid} to {end}): a rule worth anything "
          'should make money in both.', '',
          '| Edge at least | Bets, 1st half | Return, 1st half | Bets, 2nd half | Return, 2nd half |', '|---|---|---|---|---|']
    for x in (0.0, 0.05, 0.1, 0.2, 0.3):
        cells = []
        for part in (first, second):
            s = stat([b for b in (value(r, x) for r in part) if b])
            cells += [str(s[0]), f'{s[4]:+.1%} (t {s[5]:+.1f})'] if s and s[0] >= 30 else [str(s[0]) if s else '0', '–']
        L.append(f'| {x:.0%} | ' + ' | '.join(cells) + ' |')

    L += ['', '## Month by month', '', '| Month | Matches | Elo pick P/L | Favourite P/L | Value 10%+ bets | Value 10%+ P/L |', '|---|---|---|---|---|---|']
    by_month = defaultdict(list)
    for r in recs:
        by_month[f'{r["day"]:%Y-%m}'].append(r)
    up = {'pick': 0, 'fav': 0, 'val': 0}
    for mo, xs in sorted(by_month.items()):
        sp = stat([pick(r)[:2] for r in xs])
        sf = stat([(min(r['o']), fav(r) == r['w']) for r in xs if fav(r)])
        sv = stat([b for b in (value(r, 0.1) for r in xs) if b])
        up['pick'] += sp[3] > 0
        up['fav'] += bool(sf) and sf[3] > 0
        up['val'] += bool(sv) and sv[3] > 0
        L.append(f'| {mo} | {len(xs)} | {sp[3]:+.1f} | {sf[3] if sf else 0:+.1f} | {sv[0] if sv else 0} | {sv[3] if sv else 0:+.1f} |')
    n = len(by_month)
    L += ['', f"Months in profit: the Elo pick {up['pick']} of {n}, the favourite {up['fav']} of {n}, value 10%+ {up['val']} of {n}."]
    return finish(L, out_path)


def finish(lines, out_path):
    text = '\n'.join(lines) + '\n'
    print(text)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)


if __name__ == '__main__':
    main()
