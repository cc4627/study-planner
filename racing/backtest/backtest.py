"""Backtest market-rank selection rules on UK & Irish win markets using Betfair SP files.

Data: Betfair's free daily BSP files (promo.betfair.com/betfairsp/prices), one CSV per country per day.
Selection uses only the morning traded price (morningwap), which is known before the race; every bet
is settled at Betfair SP (bsp) less commission, so there is no look-ahead.

Method: a fixed family of rules is scored on the training window, the best one (by ROI, with a minimum
number of bets) is picked, and that single rule is then run once on the untouched test window. The test
result is the honest estimate; the training result is inflated by having picked the best of many rules.

Usage: python backtest.py START END TEST_START [--out RESULTS.md]
  dates as YYYY-MM-DD; training = START..TEST_START-1, test = TEST_START..END
"""
import csv
import io
import itertools
import math
import os
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

BASE = 'https://promo.betfair.com/betfairsp/prices/dwbfprices{country}win{d:%d%m%Y}.csv'
COUNTRIES = {'GB': 'uk', 'IE': 'ire'}
COMMISSION = 0.05  # Betfair's standard rate on net winnings; the conservative case
MIN_TRAIN_BETS = 200
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')


def fetch(url):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, url.rsplit('/', 1)[1])
    if os.path.exists(path):
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (racing backtest)'})
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read().decode('utf-8', errors='replace')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            return text
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # no racing that day (e.g. Christmas) or file not published
            err = e
        except Exception as e:  # network hiccup: back off and retry
            err = e
        time.sleep(2 ** (attempt + 1))
    print(f'  ! failed {url}: {err}', file=sys.stderr)
    return None


def num(s):
    try:
        v = float(s)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def race_type(name):
    n = ' ' + name.upper() + ' '
    if 'NHF' in n or 'NH FLAT' in n or 'INHF' in n:
        return 'nhf'
    if 'CHS' in n or 'CHASE' in n:
        return 'chase'
    if 'HRD' in n or 'HURDLE' in n:
        return 'hurdle'
    return 'flat'


def load(start, end):
    """Return a list of races: dict(date, country, kind, hcap, runners=[(morning, bsp, won)])."""
    races = {}
    d = start
    while d <= end:
        for country, slug in COUNTRIES.items():
            text = fetch(BASE.format(country=slug, d=d))
            if not text:
                continue
            for row in csv.DictReader(io.StringIO(text)):
                row = {k.strip().lower(): (v or '').strip() for k, v in row.items() if k}
                bsp = num(row.get('bsp'))
                if bsp is None:
                    continue
                key = (country, row.get('event_id'))
                r = races.setdefault(key, {
                    'date': d, 'country': country, 'name': row.get('event_name', ''),
                    'course': row.get('menu_hint', ''), 'runners': []})
                r['runners'].append((num(row.get('morningwap')), bsp, row.get('win_lose') == '1'))
        d += timedelta(days=1)
    out = []
    for r in races.values():
        runners = r['runners']
        priced = [x for x in runners if x[0]]
        # Need a winner, a real field, and morning prices for most of it to rank by.
        if len(runners) < 3 or sum(x[2] for x in runners) != 1 or len(priced) < 0.8 * len(runners):
            continue
        r['kind'] = race_type(r['name'])
        r['hcap'] = 'HCAP' in r['name'].upper()
        r['field'] = len(runners)
        r['ranked'] = sorted(priced, key=lambda x: x[0])
        out.append(r)
    return out


# ---- the rule family, fixed before looking at any results ----
RANKS = [1, 2, 3]
SIDES = ['back', 'lay']
KINDS = ['all', 'flat', 'hurdle', 'chase', 'nhf']
HCAP = ['all', 'hcap', 'non-hcap']
FIELDS = [('all', 0, 99), ('<=7', 0, 7), ('8-12', 8, 12), ('13+', 13, 99)]
COUNTRY = ['all', 'GB', 'IE']
PRICES = [('all', 0, 1e9), ('<3', 0, 3), ('3-6', 3, 6), ('6+', 6, 1e9)]


def rules():
    for rank, side, kind, hc, fb, ct, pb in itertools.product(RANKS, SIDES, KINDS, HCAP, FIELDS, COUNTRY, PRICES):
        yield dict(rank=rank, side=side, kind=kind, hcap=hc, field=fb, country=ct, price=pb)


def describe(rule):
    parts = [f"{rule['side']} morning #{rule['rank']}"]
    if rule['kind'] != 'all': parts.append(rule['kind'])
    if rule['hcap'] != 'all': parts.append(rule['hcap'])
    if rule['field'][0] != 'all': parts.append(f"field {rule['field'][0]}")
    if rule['country'] != 'all': parts.append(rule['country'])
    if rule['price'][0] != 'all': parts.append(f"morning price {rule['price'][0]}")
    return ', '.join(parts)


def returns(rule, races):
    """Per-bet returns for 1 unit (back stake, or lay at backer's stake of 1)."""
    out = []
    for r in races:
        if rule['kind'] != 'all' and r['kind'] != rule['kind']: continue
        if rule['hcap'] == 'hcap' and not r['hcap']: continue
        if rule['hcap'] == 'non-hcap' and r['hcap']: continue
        _, lo, hi = rule['field']
        if not lo <= r['field'] <= hi: continue
        if rule['country'] != 'all' and r['country'] != rule['country']: continue
        if len(r['ranked']) < rule['rank']: continue
        morning, bsp, won = r['ranked'][rule['rank'] - 1]
        _, plo, phi = rule['price']
        if not plo <= morning < phi: continue
        if rule['side'] == 'back':
            out.append((bsp - 1) * (1 - COMMISSION) if won else -1.0)
        else:
            out.append(-(bsp - 1) if won else 1 - COMMISSION)
    return out


def stats(rets):
    n = len(rets)
    if not n:
        return dict(n=0, pl=0.0, roi=0.0, t=0.0)
    pl = sum(rets)
    mean = pl / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rets) / (n - 1)) if n > 1 else 0
    return dict(n=n, pl=pl, roi=mean, t=mean / (sd / math.sqrt(n)) if sd else 0.0)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    out_path = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else None
    if out_path in args: args.remove(out_path)
    start, end, test_start = (datetime.strptime(a, '%Y-%m-%d').date() for a in args)

    print(f'Loading {start}..{end}', file=sys.stderr)
    races = load(start, end)
    train = [r for r in races if r['date'] < test_start]
    test = [r for r in races if r['date'] >= test_start]
    lines = [f'# Racing backtest: {start} to {end}', '',
             f'Betfair SP files, UK & Ireland win markets. Selection on morning price only, settled at BSP less {COMMISSION:.0%} commission.',
             f'Training: {start} to {test_start - timedelta(days=1)} ({len(train)} races). Test: {test_start} to {end} ({len(test)} races).', '']
    if not train or not test:
        lines.append('Not enough data loaded to run the backtest (files missing or unreachable).')
        report(lines, out_path)
        return

    base = dict(rank=1, side='back', kind='all', hcap='all', field=FIELDS[0], country='all', price=PRICES[0])
    bt, bs = stats(returns(base, train)), stats(returns(base, test))
    lines += ['## Baseline: back every morning favourite', '',
              '| Window | Bets | P/L (pts) | ROI |', '|---|---|---|---|',
              f"| Training | {bt['n']} | {bt['pl']:+.1f} | {bt['roi']:+.1%} |",
              f"| Test | {bs['n']} | {bs['pl']:+.1f} | {bs['roi']:+.1%} |", '']

    scored = []
    for rule in rules():
        s = stats(returns(rule, train))
        if s['n'] >= MIN_TRAIN_BETS:
            scored.append((s['roi'], rule, s))
    scored.sort(key=lambda x: -x[0])
    lines += [f'## Top 10 rules on training ({len(scored)} rules with at least {MIN_TRAIN_BETS} bets)', '',
              '| Rule | Train bets | Train ROI | Train t | Test bets | Test ROI | Test t |', '|---|---|---|---|---|---|---|']
    for roi, rule, s in scored[:10]:
        t = stats(returns(rule, test))
        lines.append(f"| {describe(rule)} | {s['n']} | {s['roi']:+.1%} | {s['t']:.2f} | {t['n']} | {t['roi']:+.1%} | {t['t']:.2f} |")
    lines.append('')

    _, best, s = scored[0]
    t = stats(returns(best, test))
    lines += ['## Chosen rule (best on training), run once on test', '',
              f'**{describe(best)}**', '',
              f"- Training: {s['n']} bets, P/L {s['pl']:+.1f} pts, ROI {s['roi']:+.1%}, t = {s['t']:.2f}",
              f"- Test: {t['n']} bets, P/L {t['pl']:+.1f} pts, ROI {t['roi']:+.1%}, t = {t['t']:.2f}", '']
    edge = t['n'] >= 50 and t['roi'] > 0 and t['t'] >= 2
    lines.append('Verdict: ' + ('the rule held up out of sample (t >= 2). Treat it as promising, not proven: '
                               'a month is a short test, so keep tracking it live.' if edge else
                               'no reliable edge. The training profit came from picking the best of many rules and did not '
                               'survive on unseen races (needs a positive test ROI with t >= 2).'))
    report(lines, out_path)


def report(lines, out_path):
    text = '\n'.join(lines) + '\n'
    print(text)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)


if __name__ == '__main__':
    main()
