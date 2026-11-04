"""Fit the corners and cards models on past seasons and test them, with the goals and both-to-score calls, on
later seasons they never saw.

Usage: python backtest.py CACHE_DIR [--out BACKTEST.md] [--model model.json]

Seasons 2021/22 to 2023/24 fit the models; 2024/25 to now test them. For every test match each model calls
over or under its league's usual line; each day's two most confident corner calls make the "corner double".
Football-data.co.uk has no corner or card odds, so profit can't be measured directly: the report gives how
often each call came in and the price a bookmaker would need to pay for it to break even. Paper only.
"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fd  # noqa: E402
import goals as G  # noqa: E402
import stats as S  # noqa: E402

TRAIN = ['2122', '2223', '2324']
TEST = ['2425', '2526', '2627']
WARMUP_DAYS = 42  # first six weeks only build up form
NAMES = {'corners': 'Corners', 'cards': 'Yellow cards'}


def collect(cache):
    """Per stat: every played match with that stat, its features (computed before the match) and split."""
    hist = fd.history(TRAIN + TEST, cache)
    trackers = {s: S.Tracker(s) for s in S.STATS}
    start = min(m['date'] for m, _ in hist) if hist else None
    rows = {s: [] for s in S.STATS}
    matches = []
    for m, code in hist:
        warm = start and (m['date'] - start).days >= WARMUP_DAYS
        split = 'train' if code in TRAIN else 'test'
        for s, tr in trackers.items():
            k = S.STATS[s]
            if m.get(k['h']) is None or m.get(k['a']) is None:
                continue
            f = tr.features(m)
            if f and warm:
                rows[s].append(dict(m=m, f=f, split=split))
            tr.update(m, code)
        if warm and split == 'test' and m['hg'] is not None:
            matches.append(m)
    return rows, matches


def fit(train, stat):
    k = S.STATS[stat]
    bh = S.fit_poisson([r['f'][0] for r in train], [r['m'][k['h']] for r in train], [math.log(r['f'][2]) for r in train])
    ba = S.fit_poisson([r['f'][1] for r in train], [r['m'][k['a']] for r in train], [math.log(r['f'][3]) for r in train])
    model = {'beta_home': bh.tolist(), 'beta_away': ba.tolist()}
    means = [sum(S.expected(r['f'], model)) for r in train]
    model['k'] = S.dispersion([r['m'][k['h']] + r['m'][k['a']] for r in train], means)
    totals = defaultdict(list)
    for r in train:
        totals[r['m']['div']].append(r['m'][k['h']] + r['m'][k['a']])
    model['lines'] = {d: S.main_line(float(np.mean(t))) for d, t in totals.items()}
    model['base_over'] = {d: float(np.mean([x > model['lines'][d] for x in t])) for d, t in totals.items()}
    model['avg_total'] = {d: float(np.mean(t)) for d, t in totals.items()}
    return model


def logloss(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(math.log(p) if y else math.log(1 - p))


def calibration(res, L):
    L += ['| Model said | Calls | Came in | Price needed to break even |', '|---|---|---|---|']
    for lo, hi in ((0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.7), (0.7, 0.75), (0.75, 1.01)):
        b = [x for x in res if lo <= x['pc'] < hi]
        if len(b) >= 20:
            hit = np.mean([x['hit'] for x in b])
            L.append(f'| {lo:.0%}-{min(hi, 1):.0%} | {len(b)} | {hit:.1%} | {1 / hit:.2f} |')


def evaluate(stat, train, test, model, L):
    k = S.STATS[stat]
    res = []
    for r in test:
        m = r['m']
        line = model['lines'].get(m['div'])
        if line is None:
            continue  # a league with no counts in the fitting seasons
        mean = sum(S.expected(r['f'], model))
        p = S.p_over(mean, line, model['k'])
        total = m[k['h']] + m[k['a']]
        over = total > line
        side, pc = ('over', p) if p >= 0.5 else ('under', 1 - p)
        res.append(dict(m=m, mean=mean, p=p, total=total, over=over, pc=pc, hit=(over if side == 'over' else not over),
                        base=model['base_over'][m['div']], avg=model['avg_total'][m['div']]))
    mae = np.mean([abs(x['total'] - x['mean']) for x in res])
    mae0 = np.mean([abs(x['total'] - x['avg']) for x in res])
    ll = np.mean([logloss(x['p'], x['over']) for x in res])
    ll0 = np.mean([logloss(x['base'], x['over']) for x in res])
    name = NAMES[stat]
    L += [f'## {name}', '',
          f"{len(train)} matches from 2021/22 to 2023/24 fitted the model; it was then run once over {len(res)} matches "
          f"from {res[0]['m']['date']} to {res[-1]['m']['date']} in {len({x['m']['div'] for x in res})} leagues, which it "
          f"never saw. Each league's line is the .5 nearest its average total in the fitting seasons.", '',
          '| | Average miss | Log loss on over/under the line |', '|---|---|---|',
          f'| League average only | {mae0:.2f} | {ll0:.4f} |', f'| Model | {mae:.2f} | {ll:.4f} |', '',
          'Lower is better.', '', f'### {name}: when the model is confident, how often is it right?', '']
    calibration(res, L)
    by_day = defaultdict(list)
    for x in res:
        by_day[x['m']['date']].append(x)
    doubles = []
    for d, xs in sorted(by_day.items()):
        if len(xs) >= 2:
            a, b = sorted(xs, key=lambda x: -x['pc'])[:2]
            doubles.append(dict(p=a['pc'] * b['pc'], hit=a['hit'] and b['hit'], legs=(a, b)))
    legs = [leg for d in doubles for leg in d['legs']]
    dh, sh = np.mean([d['hit'] for d in doubles]), np.mean([x['hit'] for x in legs])
    L += ['', f"### {name}: the daily double (each day's two most confident calls)", '',
          '| | Days | Model expected | Came in | Price needed to break even |', '|---|---|---|---|---|',
          f"| Each leg on its own | {len(legs)} | {np.mean([x['pc'] for x in legs]):.1%} | {sh:.1%} | {1 / sh:.2f} |",
          f"| The double | {len(doubles)} | {np.mean([d['p'] for d in doubles]):.1%} | {dh:.1%} | {1 / dh:.2f} |", '']
    model.update(test_matches=len(res), double_hit=float(dh), leg_hit=float(sh), features=S.FEATURES)
    L += [f'Fitted weights (home, away): ' + ', '.join(f'{n} {a:+.2f}/{b:+.2f}' for n, a, b in
                                                     zip(S.FEATURES, model['beta_home'], model['beta_away'])) + '.', '']
    return dh


def main():
    args = sys.argv[1:]
    cache = args[0]
    out_path = args[args.index('--out') + 1] if '--out' in args else None
    model_path = args[args.index('--model') + 1] if '--model' in args else None
    rows, matches = collect(cache)
    L = ['# Soccer backtest', '',
         'Football-data.co.uk has no corner or card odds, so these show how often each call came in and the price a '
         'bookmaker would need to pay for it to break even, not profit. Bookmakers usually price their main line near '
         'evens (about 1.83 each side), but they set that line per match, so a confident call at the league\'s usual line '
         'is normally offered shorter than that: compare the fair price on the page with your bookmaker\'s.', '']
    models = {}
    for stat in S.STATS:
        train = [r for r in rows[stat] if r['split'] == 'train']
        test = [r for r in rows[stat] if r['split'] == 'test']
        if len(train) < 2000 or len(test) < 1000:
            L += [f'## {NAMES[stat]}', '', f'Not enough matches ({len(train)} fitting, {len(test)} testing).', '']
            continue
        models[stat] = fit(train, stat)
        evaluate(stat, train, test, models[stat], L)

    for key, name in (('goals', 'Goals over/under 2.5'), ('btts', 'Both teams to score')):
        res = []
        for m in matches:
            c = G.calls(m)
            if not c:
                continue
            side, pc = c[key]
            happened = (m['hg'] + m['ag'] > 2.5) if key == 'goals' else (m['hg'] > 0 and m['ag'] > 0)
            res.append(dict(pc=pc, hit=happened == (side in ('over', 'yes'))))
        if res:
            L += [f'## {name}', '', f"From the match odds alone, over {len(res)} test matches: the call came in "
                  f"{np.mean([x['hit'] for x in res]):.1%} of the time.", '']
            calibration(res, L)
            L.append('')
    fav = [m for m in matches if m.get('oh') and m.get('oa')]
    if fav:
        won = [(m['hg'] > m['ag']) if m['oh'] <= m['oa'] else (m['ag'] > m['hg']) for m in fav]
        rets = [((m['oh'] if m['oh'] <= m['oa'] else m['oa']) - 1) if w else -1.0 for m, w in zip(fav, won)]
        L += ['## Match result picks', '', f"The bookmakers' favourite won {np.mean(won):.1%} of {len(won)} test matches; "
              f"backing it at the average odds returned {np.mean(rets):+.1%}.", '']
    return finish(L, out_path, model_path, models)


def finish(lines, out_path, model_path, models):
    text = '\n'.join(lines) + '\n'
    print(text)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)
    if model_path and models:
        with open(model_path, 'w', encoding='utf-8') as f:
            json.dump(models, f, indent=1)


if __name__ == '__main__':
    main()
