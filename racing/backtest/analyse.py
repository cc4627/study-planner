"""Fit the ranking model on the training months, then test it once on the held-out month.

Usage: python analyse.py DATA_DIR TEST_START [--out RESULTS.md] [--model model.json]

Sporting Life rewrites a race's betting forecast with the starting prices once it has run, so the
"forecast" on results pages is the SP and is thrown away here: using it would be looking at the result.

1. Model: a conditional logit (one softmax per race) on the pre-race facts in racing/model.py (official
   rating, weight, age, form figures, days since last run), shrunk towards "no information", fitted on
   training races only.
2. Accuracy on the test month: the model against picking at random, with the SP shown for reference.
3. Betting: a fixed family of rules (model rank, race type, handicap, field size) is scored on training
   races. The single best is then run once on the test month. Bets are settled at the starting price
   (SP); selection never looks at it.
Paper points only; nothing here places a bet.
"""
import glob
import gzip
import itertools
import json
import math
import os
import random
import sys
from datetime import date, datetime, timezone

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from model import FEATURES, features  # noqa: E402

LAMBDA = 2.0        # shrinkage towards "no information"
MIN_TRAIN_BETS = 150
KINDS = ['all', 'flat', 'aw', 'hurdle', 'chase', 'nhf']
FIELDS = [('all', 0, 99), ('<=7', 0, 7), ('8-12', 8, 12), ('13+', 13, 99)]


def load(data_dir):
    races = {}
    for path in sorted(glob.glob(os.path.join(data_dir, '*.jsonl.gz'))):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                races[r['id']] = r
    out = []
    for r in races.values():
        rs = [x for x in r['runners'] if x.get('sp')]
        if len(rs) < 3 or len(rs) < len(r['runners']) - 1:
            continue  # need prices for (nearly) every runner
        for x in rs:
            x['fc'] = None  # on a results page this is the SP, not the morning forecast
        # Results pages list runners in finishing order. Shuffle (repeatably) so that no ranking can
        # pick up the winner just by breaking a tie in favour of whoever is listed first.
        random.Random(r['id']).shuffle(rs)
        r['runners'] = rs
        if not any(x.get('pos') == 1 for x in rs):
            continue  # abandoned, void or no result
        out.append(r)
    return sorted(out, key=lambda r: (r['date'], r['time']))


def winners(r):
    return [i for i, x in enumerate(r['runners']) if x.get('pos') == 1]


def fit(races):
    """Newton's method on the conditional-logit likelihood with an L2 pull towards zero."""
    Xs = [np.array(features(r)) for r in races]
    ws = [winners(r) for r in races]
    F = len(FEATURES)
    prior = np.zeros(F)
    b = prior.copy()
    for _ in range(25):
        g = -LAMBDA * (b - prior)
        H = -LAMBDA * np.eye(F)
        for X, w in zip(Xs, ws):
            s = X @ b; p = np.exp(s - s.max()); p /= p.sum()
            mean = p @ X
            g += X[w].mean(axis=0) - mean
            H -= (X * p[:, None]).T @ X - np.outer(mean, mean)
        step = np.linalg.solve(H, g)
        b -= step
        if np.abs(step).max() < 1e-6:
            break
    return dict(zip(FEATURES, (float(v) for v in b)))


def model_probs(r, coef):
    X = np.array(features(r)); s = X @ np.array([coef[f] for f in FEATURES])
    p = np.exp(s - s.max())
    return list(p / p.sum())


def accuracy(races, pfn):
    ll = top1 = top3 = 0.0
    for r in races:
        p, w = pfn(r), winners(r)
        ll -= sum(math.log(max(p[i], 1e-9)) for i in w) / len(w)
        order = sorted(range(len(p)), key=lambda i: -p[i])
        top1 += any(i in w for i in order[:1]); top3 += any(i in w for i in order[:3])
    n = len(races)
    return ll / n, top1 / n, top3 / n


def rows(races, coef):
    """One row per runner: what a rule can see before the race, plus the SP return of a 1pt win bet."""
    cols = {k: [] for k in ('m_rank', 'kind', 'hcap', 'field', 'ret')}
    for r in races:
        pm, w = model_probs(r, coef), winners(r)
        rs = r['runners']
        m_order = sorted(range(len(rs)), key=lambda i: -pm[i])
        for i, x in enumerate(rs):
            cols['m_rank'].append(m_order.index(i) + 1)
            cols['kind'].append(r['kind']); cols['hcap'].append(bool(r['hcap'])); cols['field'].append(len(rs))
            cols['ret'].append(x['sp'] / len(w) - 1 if i in w else -1.0)  # dead heats split the stake
    return {k: np.array(v) for k, v in cols.items()}


def rules():
    for rank, kind, hc, fb in itertools.product([1, 2, 3, 'any'], KINDS, ['all', 'hcap', 'non-hcap'], FIELDS):
        yield dict(rank=rank, kind=kind, hcap=hc, field=fb)


def mask(rule, d):
    m = np.ones(len(d['ret']), bool)
    if rule['rank'] != 'any':
        m &= d['m_rank'] == rule['rank']
    if rule['kind'] != 'all': m &= d['kind'] == rule['kind']
    if rule['hcap'] == 'hcap': m &= d['hcap']
    if rule['hcap'] == 'non-hcap': m &= ~d['hcap']
    m &= (d['field'] >= rule['field'][1]) & (d['field'] <= rule['field'][2])
    return m


def stats(ret):
    n = len(ret)
    if n < 2:
        return dict(n=n, pl=float(ret.sum()) if n else 0.0, roi=float(ret.mean()) if n else 0.0, t=0.0)
    sd = ret.std(ddof=1)
    return dict(n=n, pl=float(ret.sum()), roi=float(ret.mean()), t=float(ret.mean() / (sd / math.sqrt(n))) if sd else 0.0)


def describe(rule):
    parts = ['back every runner' if rule['rank'] == 'any' else f"back model #{rule['rank']}"]
    if rule['kind'] != 'all': parts.append(rule['kind'])
    if rule['hcap'] != 'all': parts.append(rule['hcap'])
    if rule['field'][0] != 'all': parts.append('field ' + rule['field'][0])
    return ', '.join(parts)


def main():
    args = [a for a in sys.argv[1:]]
    opt = lambda k: args[args.index(k) + 1] if k in args else None
    out_path, model_path = opt('--out'), opt('--model')
    data_dir, test_start = args[0], args[1]
    races = load(data_dir)
    train = [r for r in races if r['date'] < test_start]
    test = [r for r in races if r['date'] >= test_start]
    L = [f'# Racing backtest: {races[0]["date"] if races else "?"} to {races[-1]["date"] if races else "?"}', '',
         'UK & Irish races from Sporting Life results pages. Runners are ranked using only facts known before the race '
         '(official rating, weight, age, form figures, days since last run); every bet is settled at the starting price (SP). '
         'Paper points only.', '',
         'The morning betting forecast is not used: once a race has run, Sporting Life replaces it with the SPs, so on '
         'past races it would be looking at the result. The forecast-based daily picks can only be checked going forward.', '',
         f'Training: {len(train)} races before {test_start}. Test: {len(test)} races from {test_start}, used once.', '']
    if len(train) < 500 or len(test) < 200:
        L.append('Not enough races collected to run the backtest.')
        return finish(L, out_path, model_path, None)

    coef = fit(train)
    un_acc = accuracy(test, lambda r: [1 / len(r['runners'])] * len(r['runners']))
    m_acc = accuracy(test, lambda r: model_probs(r, coef))
    sp_acc = accuracy(test, lambda r: [1 / x['sp'] / sum(1 / y['sp'] for y in r['runners']) for x in r['runners']])
    L += ['## 1. Who wins: accuracy on the test month', '',
          '| Ranking | Log loss (lower is better) | Top pick won | Winner in top 3 |', '|---|---|---|---|',
          f'| Random pick | {un_acc[0]:.4f} | {un_acc[1]:.1%} | {un_acc[2]:.1%} |',
          f'| Model (rating, weight, age, form, days off) | {m_acc[0]:.4f} | {m_acc[1]:.1%} | {m_acc[2]:.1%} |',
          f'| Starting price (known only at the off, for reference) | {sp_acc[0]:.4f} | {sp_acc[1]:.1%} | {sp_acc[2]:.1%} |', '',
          'Model weights: ' + ', '.join(f'{k} {v:+.2f}' for k, v in coef.items() if k not in ('lfc', 'fc_missing')), '']

    dtr, dte = rows(train, coef), rows(test, coef)
    base = [('Back every runner (the bookmakers\' margin)', dict(rank='any', kind='all', hcap='all', field=FIELDS[0])),
            ('Back the model top pick', dict(rank=1, kind='all', hcap='all', field=FIELDS[0]))]
    L += ['## 2. Betting at SP: simple strategies', '', '| Strategy | Train bets | Train ROI | Test bets | Test P/L | Test ROI |', '|---|---|---|---|---|---|']
    for label, rule in base:
        a, b = stats(dtr['ret'][mask(rule, dtr)]), stats(dte['ret'][mask(rule, dte)])
        L.append(f"| {label} | {a['n']} | {a['roi']:+.1%} | {b['n']} | {b['pl']:+.1f} | {b['roi']:+.1%} |")
    L.append('')

    scored = []
    for rule in rules():
        s = stats(dtr['ret'][mask(rule, dtr)])
        if s['n'] >= MIN_TRAIN_BETS:
            scored.append((s['roi'], rule, s))
    scored.sort(key=lambda x: -x[0])
    L += [f'## 3. Searching for an edge: best of {len(scored)} rules on training, then tested', '',
          '| Rule | Train bets | Train ROI | Train t | Test bets | Test ROI | Test t |', '|---|---|---|---|---|---|---|']
    for _, rule, s in scored[:10]:
        t = stats(dte['ret'][mask(rule, dte)])
        L.append(f"| {describe(rule)} | {s['n']} | {s['roi']:+.1%} | {s['t']:.2f} | {t['n']} | {t['roi']:+.1%} | {t['t']:.2f} |")
    _, best, s = scored[0]
    t = stats(dte['ret'][mask(best, dte)])
    passed = t['n'] >= 50 and t['roi'] > 0 and t['t'] >= 2
    L += ['', f'**Chosen on training: {describe(best)}**', '',
          f"- Training: {s['n']} bets, {s['pl']:+.1f} pts, ROI {s['roi']:+.1%} (t = {s['t']:.2f})",
          f"- Test, run once: {t['n']} bets, {t['pl']:+.1f} pts, ROI {t['roi']:+.1%} (t = {t['t']:.2f})", '',
          '**Verdict:** ' + verdict(t, passed), '',
          'Only the chosen rule counts as the test. The other rows show how training winners usually fade on new races.']
    # The live page ranks by the morning forecast, which this backtest can't check (see above), so the
    # model is recorded here but not switched on for the daily picks.
    return finish(L, out_path, model_path, dict(
        coef=coef, use_model=False, rule=describe(best), rule_passed=passed,
        train_races=len(train), test_races=len(test), test_start=test_start,
        generated=datetime.now(timezone.utc).isoformat(timespec='seconds')))


def verdict(t, passed):
    # One-sided chance of a test result at least this good if the rule really broke even (normal approx.).
    luck = 0.5 * math.erfc(t['t'] / math.sqrt(2))
    if passed:
        return ('this rule kept a profit on unseen races with t >= 2. Promising but not proven after one month; '
                'paper-trade it live before trusting it.')
    if t['roi'] > 0:
        return (f"no proven edge yet. The rule also made a profit on the test month, but over {t['n']} bets that is "
                f"not enough to tell skill from luck (t = {t['t']:.2f}: about a {luck:.0%} chance of doing this well by luck "
                'with no edge at all). A pass needs t >= 2 over at least 50 bets.')
    return ('no edge. The training profit came from picking the best of many rules and did not hold up on unseen '
            'races.')


def finish(lines, out_path, model_path, model):
    text = '\n'.join(lines) + '\n'
    print(text)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)
    if model_path and model:
        with open(model_path, 'w', encoding='utf-8') as f:
            json.dump(model, f, indent=1)


if __name__ == '__main__':
    main()
