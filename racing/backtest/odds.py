"""Would backing the picks only within some price range have made money?

Usage: python odds.py DATA_DIR [--out ODDS.md]

Uses a year of UK & Irish results (Nov 2025 - Oct 2026). The picks are taken as the three shortest
prices in each race, the nearest a results page gets to the morning forecast the live picks use. Every
price rule (which pick, win or place, lowest and highest starting price) is tried on Nov - Jun and the
best is then run once on Jul - Oct, which it never saw. Place bets use standard each-way place terms.
Settled at SP; paper points only.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyse import load, stats  # noqa: E402

SPLIT = '2026-07-01'  # rules are chosen on the races before this date and tested once on the races after
MIN_BETS = 300  # a rule must have at least this many bets in the search months to be considered
PICKS = {'top pick': (1,), '2nd pick': (2,), '3rd pick': (3,), 'all three picks': (1, 2, 3)}
FLOORS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0]  # decimal odds (2.0 = evens)
CAPS = [None, 3.0, 4.0, 6.0, 10.0]
BANDS = [(1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 6.0), (6.0, 10.0), (10.0, None)]


def place_terms(runners, hcap):
    """(places paid, fraction of the odds) under standard UK & Irish each-way terms, or None (no place betting)."""
    if runners < 5:
        return None
    if runners <= 7:
        return 2, 1 / 4
    if hcap and runners >= 16:
        return 4, 1 / 4
    if hcap and runners >= 12:
        return 3, 1 / 4
    return 3, 1 / 5


def bets(races):
    """One row per race and pick (the three shortest prices): date, pick number, SP, win and place return."""
    out = []
    for r in races:
        terms = place_terms(len(r['runners']), r['hcap'])
        # sorted() is stable and load() shuffled the runners, so equal prices aren't ordered by result
        for k, x in enumerate(sorted(r['runners'], key=lambda x: x['sp'])[:3], 1):
            pos = x['pos'] if isinstance(x.get('pos'), int) and x['pos'] >= 1 else 99
            win = x['sp'] - 1 if pos == 1 else -1.0
            place = None if terms is None else (x['sp'] - 1) * terms[1] if pos <= terms[0] else -1.0
            out.append((r['date'], k, x['sp'], win, place))
    return out


def odds(d):
    """Decimal odds as the fractional price a bookmaker shows."""
    if d is None:
        return ''
    n = d - 1
    for num, den in ((1, 5), (1, 4), (2, 7), (1, 3), (2, 5), (4, 9), (1, 2), (8, 13), (4, 6), (4, 5), (5, 6),
                     (1, 1), (5, 4), (11, 8), (6, 4), (13, 8), (7, 4), (15, 8), (2, 1), (9, 4), (5, 2), (11, 4),
                     (3, 1), (7, 2), (4, 1), (9, 2), (5, 1), (6, 1), (7, 1), (9, 1), (10, 1), (12, 1), (14, 1)):
        if abs(num / den - n) < 1e-6:
            return 'evens' if num == den else f'{num}/{den}'
    return f'{n:g}/1'


def describe(rule):
    picks, kind, lo, hi = rule
    price = (f'{odds(lo)} to {odds(hi)}' if hi and lo > 1 else f'up to {odds(hi)}' if hi else
             f'{odds(lo)} or bigger' if lo > 1 else 'any price')
    return f"{picks}, to {kind}, {price}"


def returns(rows, rule):
    picks, kind, lo, hi = rule
    keep = [b for b in rows if b[1] in PICKS[picks] and b[2] >= lo and (hi is None or b[2] < hi)]
    if kind == 'each way':  # €1 each way is €2 staked: return per €1 is the average of the two halves
        return np.array([(b[3] + b[4]) / 2 for b in keep if b[4] is not None], dtype=float)
    col = 3 if kind == 'win' else 4
    return np.array([b[col] for b in keep if b[col] is not None], dtype=float)


def row(name, s):
    return f"| {name} | {s['n']} | {s['pl']:+.1f} | {s['roi']:+.1%} | {s['t']:.2f} |"


def main():
    args = sys.argv[1:]
    out_path = args[args.index('--out') + 1] if '--out' in args else None
    races = load(args[0])
    search = bets([r for r in races if r['date'] < SPLIT])
    test = bets([r for r in races if r['date'] >= SPLIT])
    every = bets(races)
    L = [f'# Backing the picks only within a price range: {races[0]["date"] if races else "?"} to '
         f'{races[-1]["date"] if races else "?"}', '',
         f'{len(races)} UK & Irish races. Each race\'s picks are its three shortest prices, the closest a results '
         'page gets to the morning forecast the live picks use. Bets settled at SP, paper points only, €1 stakes. '
         'Place bets use standard each-way place terms (1st-2nd at 1/4 odds with 5-7 runners; 1st-3rd at 1/5 with 8+, '
         'or 1/4 in handicaps of 12-15; 1st-4th at 1/4 in handicaps of 16+; no place betting under 5 runners).', '']
    if len(races) < 1000 or not search or not test:
        L.append('Not enough races to run this.')
        return finish(L, out_path)

    L += ['## Where the money goes, by price (whole year)', '',
          'Return per €1 staked (number of bets in brackets; – where under 30).', '',
          '| Starting price | Top pick, win | Top pick, place | All three, win | All three, place |', '|---|---|---|---|---|']
    for lo, hi in BANDS:
        cells = []
        for picks in ('top pick', 'all three picks'):
            for kind in ('win', 'place'):
                s = stats(returns(every, (picks, kind, lo, hi)))
                cells.append(f"{s['roi']:+.1%} ({s['n']})" if s['n'] >= 30 else '–')
        label = f'under {odds(hi)}' if lo <= 1 else f'{odds(lo)} to {odds(hi)}' if hi else f'{odds(lo)} or bigger'
        L.append(f'| {label} | ' + ' | '.join(cells) + ' |')

    L += ['', '## Each pick on its own, any price', '',
          'Return per €1 staked, chosen months and unseen months (number of bets in brackets).', '',
          '| Bet | Win, Nov-Jun | Win, Jul-Oct | Place, Nov-Jun | Place, Jul-Oct | Each way, Nov-Jun | Each way, Jul-Oct |',
          '|---|---|---|---|---|---|---|']
    for picks in PICKS:
        cells = []
        for kind in ('win', 'place', 'each way'):
            for rows_ in (search, test):
                s = stats(returns(rows_, (picks, kind, 1.0, None)))
                cells.append(f"{s['roi']:+.1%} ({s['n']})")
        L.append(f'| {picks} | ' + ' | '.join(cells) + ' |')

    L += ['', '## "Only back the picks at odds over x"', '',
          'All three picks, at or above each price. Chosen months (Nov - Jun) and unseen months (Jul - Oct) side by side.', '',
          '| Price at least | Win, Nov-Jun | Win, Jul-Oct | Place, Nov-Jun | Place, Jul-Oct |', '|---|---|---|---|---|']
    for lo in FLOORS:
        cells = []
        for kind in ('win', 'place'):
            for rows_ in (search, test):
                s = stats(returns(rows_, ('all three picks', kind, lo, None)))
                cells.append(f"{s['roi']:+.1%} ({s['n']})")
        L.append(f'| {odds(lo) if lo > 1 else "any"} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |')

    rules = [(p, k, lo, hi) for p in PICKS for k in ('win', 'place') for lo in FLOORS for hi in CAPS
             if hi is None or hi > lo]
    scored = []
    for rule in rules:
        s = stats(returns(search, rule))
        if s['n'] >= MIN_BETS:
            scored.append((s['roi'], rule, s))
    scored.sort(key=lambda x: -x[0])
    L += ['', '## Best price rules found on Nov - Jun, then run on Jul - Oct', '',
          f'{len(rules)} rules tried (which pick, win or place, lowest and highest price), {len(scored)} with at least '
          f'{MIN_BETS} bets. The best of that many will look better than it is by chance alone, so only the unseen '
          'months count.', '',
          '| Rule | Bets Nov-Jun | ROI Nov-Jun | Bets Jul-Oct | P/L Jul-Oct | ROI Jul-Oct | t Jul-Oct |',
          '|---|---|---|---|---|---|---|']
    for _, rule, s in scored[:8]:
        t = stats(returns(test, rule))
        L.append(f"| {describe(rule)} | {s['n']} | {s['roi']:+.1%} | {t['n']} | {t['pl']:+.1f} | {t['roi']:+.1%} | {t['t']:.2f} |")
    if not scored:
        L.append('| (no rule had enough bets) | | | | | | |')
        return finish(L, out_path)

    best = scored[0][1]
    t = stats(returns(test, best))
    luck = 0.5 * math.erfc(t['t'] / math.sqrt(2))
    edge = t['n'] >= 100 and t['roi'] > 0 and t['t'] >= 2
    L += ['', f"**Verdict:** the best rule on Nov - Jun was **{describe(best)}** ({scored[0][2]['roi']:+.1%} there). "
          + (f"On the unseen months it made {t['roi']:+.1%} on {t['n']} bets (t = {t['t']:.2f}, about a {luck:.1%} chance "
             "by luck): worth paper-tracking live, not yet worth money." if edge else
             f"On the unseen months it returned {t['roi']:+.1%} on {t['n']} bets (t = {t['t']:.2f}). "
             + ('No price rule beats the bookmakers here.' if t['roi'] <= 0 else
                f"That's short of the t >= 2 needed to call it an edge (about a {luck:.0%} chance by luck)."))]
    return finish(L, out_path)


def finish(lines, out_path):
    text = '\n'.join(lines) + '\n'
    print(text)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)


if __name__ == '__main__':
    main()
