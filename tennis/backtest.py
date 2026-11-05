"""How often the Elo pick wins: ratings built from ATP and WTA singles results since January 2024, with every
match from July 2025 on predicted before it was played and checked afterwards.

Usage: python backtest.py CACHE_DIR [--out BACKTEST.md]

No odds are in the free feed, so this measures hit rate and whether the stated chances are honest
(a 70% pick should win about 70% of the time); it can't measure profit. Paper only.
"""
import math
import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elo as E  # noqa: E402
import espn  # noqa: E402
import games as G  # noqa: E402

START = date(2024, 1, 1)
TEST_FROM = '2025-07-01'


def main():
    args = sys.argv[1:]
    cache = args[0]
    out_path = args[args.index('--out') + 1] if '--out' in args else None
    hist = espn.history(START, date.today(), cache)
    rating = E.Elo()
    res = []
    close = {'ATP': [], 'WTA': []}
    tuned = False
    for m in hist:
        a, b = m['p1']['id'], m['p2']['id']
        if m['start'] >= TEST_FROM:
            if not tuned:  # tune the games model on the months before the test, once
                for tour, gs in close.items():
                    if len(gs) >= 100:
                        G.calibrate(sum(gs) / len(gs), tour)
                tuned = True
            p1 = rating.p(a, b, E.bo5(m))
            pick, p = (1, p1) if p1 >= 0.5 else (2, 1 - p1)
            r = dict(m=m, p=p, hit=pick == m['winner'], known=min(rating.played(a), rating.played(b)) >= 10,
                     ll=E.logloss(p if pick == m['winner'] else 1 - p))
            bo = 5 if E.bo5(m) else 3
            full, first, games = G.summary(m, bo)
            if full:
                c = G.quick(p, m['tour'].upper(), bo)
                gl = c['games']
                r.update(first_p=c['first'], first_hit=first == pick, games_p=gl['p'],
                         games_hit=(games > gl['line']) == (gl['side'] == 'over'), acca_p=c['acca'])
                r['acca_hit'] = r['hit'] and r['first_hit'] and r['games_hit']
            res.append(r)
        elif not E.bo5(m):
            full, _, g = G.summary(m)
            if full and abs(rating.p(a, b) - 0.5) < 0.1:
                close[m['tour'].upper()].append(g)
        w, l = (a, b) if m['winner'] == 1 else (b, a)
        rating.update(w, l)

    L = ['# Tennis backtest', '']
    if len(res) < 500:
        L.append(f'Not enough matches to run it ({len(hist)} read, {len(res)} in the test period).')
        return finish(L, out_path)
    acc = lambda xs: sum(x['hit'] for x in xs) / len(xs)
    L += [f'{len(hist)} ATP and WTA singles results read from ESPN ({hist[0]["start"][:10]} to {hist[-1]["start"][:10]}). '
          f'Elo ratings were built match by match; each of the {len(res)} matches from {TEST_FROM} on was predicted '
          'before it was played. No odds are in the feed, so this shows hit rate and calibration, not profit.', '',
          '## How often the pick won', '', '| Matches | Picks | Won |', '|---|---|---|',
          f'| All | {len(res)} | {acc(res):.1%} |']
    for tour in ('atp', 'wta'):
        xs = [x for x in res if x['m']['tour'] == tour]
        if xs:
            L.append(f'| {tour.upper()} | {len(xs)} | {acc(xs):.1%} |')
    known = [x for x in res if x['known']]
    if known:
        L.append(f'| Both players with 10+ rated matches | {len(known)} | {acc(known):.1%} |')
    main_draw = [x for x in res if 'qualif' not in x['m']['round'].lower()]
    if main_draw:
        L.append(f'| Main draw only (no qualifying) | {len(main_draw)} | {acc(main_draw):.1%} |')
    ll = sum(x['ll'] for x in res) / len(res)
    L += ['', f'Log loss {ll:.4f} (a coin toss scores {math.log(2):.4f}; lower is better).', '',
          '## Are the chances honest?', '', '| Pick given | Picks | Won | Price needed to break even |', '|---|---|---|---|']
    for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
        xs = [x for x in res if lo <= x['p'] < hi]
        if xs:
            L.append(f'| {lo:.0%}-{min(hi, 1):.0%} | {len(xs)} | {acc(xs):.1%} | {1 / acc(xs):.2f} |')
    by_day = defaultdict(list)
    for x in res:
        by_day[x['m']['start'][:10]].append(x)
    doubles = []
    for d, xs in by_day.items():
        if len(xs) >= 2:
            a, b = sorted(xs, key=lambda x: -x['p'])[:2]
            doubles.append(a['hit'] and b['hit'])
    if doubles:
        dh = sum(doubles) / len(doubles)
        L += ['', f"**Each day's two most confident picks as a double:** came in on {dh:.1%} of {len(doubles)} days; "
              f'it pays only if the bookmaker offers more than {1 / dh:.2f} for it.']
    full = [x for x in res if 'acca_p' in x]
    if full:
        mean = lambda k: sum(x[k] for x in full) / len(full)
        L += ['', '## First set, total games and the match acca', '',
              f"From one game-by-game model per match (tennis/games.py), its hold rates tuned to the games in even "
              f"matches before {TEST_FROM} (ATP {G.HOLD['ATP']:.3f}, WTA {G.HOLD['WTA']:.3f}). {len(full)} test matches "
              "played out in full (no retirements or walkovers).", '',
              '| Call | Model expected | Came in | Price needed to break even |', '|---|---|---|---|']
        for name, pk, hk in (('Pick wins the first set', 'first_p', 'first_hit'), ('Total games over/under', 'games_p', 'games_hit'),
                             ('Match acca (all three)', 'acca_p', 'acca_hit')):
            hit = mean(hk)
            L.append(f'| {name} | {mean(pk):.1%} | {hit:.1%} | {1 / hit:.2f} |')
        L += ['', '| Games call given | Calls | Came in |', '|---|---|---|']
        for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 1.01)):
            xs = [x for x in full if lo <= x['games_p'] < hi]
            if len(xs) >= 30:
                L.append(f"| {lo:.0%}-{min(hi, 1):.0%} | {len(xs)} | {sum(x['games_hit'] for x in xs) / len(xs):.1%} |")
    return finish(L, out_path)


def finish(lines, out_path):
    text = '\n'.join(lines) + '\n'
    print(text)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)


if __name__ == '__main__':
    main()
