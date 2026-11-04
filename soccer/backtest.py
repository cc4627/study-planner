"""Fit the corners model on past seasons and test it on later ones it never saw.

Usage: python backtest.py CACHE_DIR [--out BACKTEST.md] [--model model.json]

Seasons 2021/22 to 2023/24 fit the model; 2024/25 to now test it. For every test match the model calls over or
under its league's usual corners line, and each day's two most confident calls make the "corner double".
Football-data.co.uk has no corner odds, so profit can't be measured directly: the report gives how often each
call came in and the price a bookmaker would need to pay for it to break even. Paper only; no bets are placed.
"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corners as C  # noqa: E402
import fd  # noqa: E402

TRAIN = ['2122', '2223', '2324']
TEST = ['2425', '2526', '2627']
WARMUP_DAYS = 42  # first six weeks only build up form


def collect(cache):
    """Every played match with corners, with its features (computed before the match) and season split."""
    hist = fd.history(TRAIN + TEST, cache)
    tr = C.Tracker()
    start = min(m['date'] for m, _ in hist) if hist else None
    rows = []
    for m, code in hist:
        if m['hc'] is None or m['ac'] is None:
            continue
        f = tr.features(m)
        if f and (m['date'] - start).days >= WARMUP_DAYS:
            rows.append(dict(m=m, f=f, split='train' if code in TRAIN else 'test'))
        tr.update(m, code)
    return rows


def fit(train):
    Xh = [r['f'][0] for r in train]
    Xa = [r['f'][1] for r in train]
    yh = [r['m']['hc'] for r in train]
    ya = [r['m']['ac'] for r in train]
    bh = C.fit_poisson(Xh, yh, [math.log(r['f'][2]) for r in train])
    ba = C.fit_poisson(Xa, ya, [math.log(r['f'][3]) for r in train])
    model = {'beta_home': bh.tolist(), 'beta_away': ba.tolist()}
    means = [sum(C.expected(r['f'], model)) for r in train]
    model['k'] = C.dispersion([r['m']['hc'] + r['m']['ac'] for r in train], means)
    totals = defaultdict(list)
    for r in train:
        totals[r['m']['div']].append(r['m']['hc'] + r['m']['ac'])
    model['lines'] = {d: C.main_line(float(np.mean(t))) for d, t in totals.items()}
    model['base_over'] = {d: float(np.mean([x > model['lines'][d] for x in t])) for d, t in totals.items()}
    return model


def logloss(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(math.log(p) if y else math.log(1 - p))


def main():
    args = sys.argv[1:]
    cache = args[0]
    out_path = args[args.index('--out') + 1] if '--out' in args else None
    model_path = args[args.index('--model') + 1] if '--model' in args else None
    rows = collect(cache)
    train = [r for r in rows if r['split'] == 'train']
    test = [r for r in rows if r['split'] == 'test']
    L = ['# Corners backtest', '']
    if len(train) < 2000 or len(test) < 1000:
        L.append(f'Not enough matches to run it ({len(train)} training, {len(test)} test).')
        return finish(L, out_path, model_path, None)
    model = fit(train)
    # Leagues new to the test seasons (e.g. the National League's first corner counts) use a line from their own
    # first matches; only for picking the line, never for scoring.
    for r in test:
        model['lines'].setdefault(r['m']['div'], 10.5)
        model['base_over'].setdefault(r['m']['div'], 0.5)

    res = []
    for r in test:
        m = r['m']
        line = model['lines'][m['div']]
        mean = sum(C.expected(r['f'], model))
        p = C.p_over(mean, line, model['k'])
        total = m['hc'] + m['ac']
        over = total > line
        side, pc = ('over', p) if p >= 0.5 else ('under', 1 - p)
        res.append(dict(m=m, line=line, mean=mean, p=p, total=total, over=over, side=side, pc=pc,
                        hit=(over if side == 'over' else not over), base=model['base_over'][m['div']]))

    mae = np.mean([abs(x['total'] - x['mean']) for x in res])
    lg_avg = defaultdict(list)
    for r in train:
        lg_avg[r['m']['div']].append(r['m']['hc'] + r['m']['ac'])
    mae0 = np.mean([abs(x['total'] - np.mean(lg_avg.get(x['m']['div'], [10.0]))) for x in res])
    ll = np.mean([logloss(x['p'], x['over']) for x in res])
    ll0 = np.mean([logloss(x['base'], x['over']) for x in res])
    first, last = res[0]['m']['date'], res[-1]['m']['date']
    L += [f'{len(train)} matches from 2021/22 to 2023/24 fitted the model; it was then run once over {len(res)} matches '
          f'from {first} to {last} in {len({x["m"]["div"] for x in res})} leagues, which it never saw. '
          "Each league's line is the .5 nearest its average total corners in the fitting seasons.", '',
          '## How close the expected corners were', '',
          '| | Average miss (corners) | Log loss on over/under the line |', '|---|---|---|',
          f'| League average only | {mae0:.2f} | {ll0:.4f} |',
          f'| Model | {mae:.2f} | {ll:.4f} |', '',
          'Lower is better. Corners are noisy: even a perfect model would miss by about 2.5 a match.', '',
          '## When the model is confident, how often is it right?', '',
          '| Model said | Calls | Came in | Price needed to break even |', '|---|---|---|---|']
    for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 0.75), (0.75, 1.01)):
        b = [x for x in res if lo <= x['pc'] < hi]
        if not b:
            continue
        hit = np.mean([x['hit'] for x in b])
        L.append(f'| {lo:.0%}-{min(hi, 1):.0%} | {len(b)} | {hit:.1%} | {1 / hit:.2f} |')

    by_day = defaultdict(list)
    for x in res:
        by_day[x['m']['date']].append(x)
    doubles = []
    for d, xs in sorted(by_day.items()):
        if len(xs) < 2:
            continue
        a, b = sorted(xs, key=lambda x: -x['pc'])[:2]
        doubles.append(dict(p=a['pc'] * b['pc'], hit=a['hit'] and b['hit'], legs=(a, b)))
    singles = [leg for dbl in doubles for leg in dbl['legs']]
    dh = np.mean([d['hit'] for d in doubles])
    sh = np.mean([x['hit'] for x in singles])
    L += ['', '## The daily corner double', '',
          "Each day, the two most confident calls across all leagues, doubled up. €1 a day.", '',
          '| | Days | Model expected | Came in | Price needed to break even |', '|---|---|---|---|---|',
          f"| Each leg on its own | {len(singles)} | {np.mean([x['pc'] for x in singles]):.1%} | {sh:.1%} | {1 / sh:.2f} |",
          f"| The double | {len(doubles)} | {np.mean([d['p'] for d in doubles]):.1%} | {dh:.1%} | {1 / dh:.2f} |", '',
          f"**What it means:** the double came in {dh:.0%} of days, so it only made money where the bookmaker paid more than "
          f"**{1 / dh:.2f}** for it (each leg more than about {1 / sh:.2f}). Bookmakers usually price their main corners line "
          "near evens (about 1.83 each side), but they set that line per match, so a confident call at the league's usual "
          "line is normally offered shorter than that. Compare the fair price on the page with what your bookmaker offers: "
          "only a bigger price is worth taking.",
          '', '## Match result picks (for reference)', '']
    fav = [x for x in res if x['m'].get('oh') and x['m'].get('oa')]
    won = [((x['m']['hg'] > x['m']['ag']) if x['m']['oh'] <= x['m']['oa'] else (x['m']['ag'] > x['m']['hg'])) for x in fav
           if x['m']['hg'] is not None]
    rets = [((x['m']['oh'] if x['m']['oh'] <= x['m']['oa'] else x['m']['oa']) - 1) if w else -1.0
            for x, w in zip([x for x in fav if x['m']['hg'] is not None], won)]
    if won:
        L += [f"The bookmakers' favourite won {np.mean(won):.1%} of {len(won)} test matches; backing it at the average odds "
              f"returned {np.mean(rets):+.1%}.", '']
    model.update(trained_on=TRAIN, tested_on=TEST, test_matches=len(res), double_hit=float(dh), leg_hit=float(sh),
                 features=C.FEATURES)
    L += ['## Fitted weights', '', '| Feature | Home corners | Away corners |', '|---|---|---|']
    for name, a, b in zip(C.FEATURES, model['beta_home'], model['beta_away']):
        L.append(f'| {name} | {a:+.3f} | {b:+.3f} |')
    L += ['', f"Spread of totals: negative binomial size k = {model['k']:.1f}." if model['k'] else
          'Spread of totals: no wider than Poisson.']
    return finish(L, out_path, model_path, model)


def finish(lines, out_path, model_path, model):
    text = '\n'.join(x for x in lines if x is not None) + '\n'
    print(text)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)
    if model_path and model:
        with open(model_path, 'w', encoding='utf-8') as f:
            json.dump(model, f, indent=1)


if __name__ == '__main__':
    main()
