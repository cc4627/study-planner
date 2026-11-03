"""Turn a race's pre-race facts into per-runner features and win chances.

Shared by the backtest (racing/backtest/analyse.py) and the daily picks (racing/picks/build_picks.py)
so both rank runners the same way. Uses only what is known before the off: the betting forecast,
official rating, weight, age, form figures and days since the last run. Never the starting price.
"""
import math

FEATURES = ['lfc', 'fc_missing', 'or_rel', 'or_rel_h', 'or_missing', 'wt_rel', 'wt_rel_h',
            'form_last', 'form_avg', 'form_missing', 'nf_last',
            'd_short', 'd_mid', 'd_long', 'd_vlong', 'debut', 'age_young', 'age_old']

# Form figures: 1-9 = finishing position, 0 = 10th or worse, letters = did not complete.
POS_PTS = {'1': 1.0, '2': .7, '3': .5, '4': .35, '5': .25, '6': .18, '7': .13, '8': .1, '9': .07, '0': .03}
NON_FINISH = set('PFURBSCO')


def form_runs(form):
    runs = []
    for ch in str(form or '').upper():
        if ch in POS_PTS:
            runs.append((POS_PTS[ch], False))
        elif ch in NON_FINISH:
            runs.append((0.1 if ch == 'F' else 0.0, True))
    return runs[-6:]


def features(race):
    """One feature vector (list, in FEATURES order) per runner in race['runners']."""
    rs = race['runners']
    hcap = 1.0 if race.get('hcap') else 0.0
    fc = [1 / r['fc'] if r.get('fc') else None for r in rs]
    known = [p for p in fc if p]
    floor = min(known) / 2 if known else 1.0
    fc = [p if p else floor for p in fc]
    tot = sum(fc)
    ors = [r['or'] for r in rs if isinstance(r.get('or'), (int, float))]
    wts = [r['wt'] for r in rs if r.get('wt')]
    mor = sum(ors) / len(ors) if ors else 0
    mwt = sum(wts) / len(wts) if wts else 0
    out = []
    for r, p in zip(rs, fc):
        has_or = isinstance(r.get('or'), (int, float))
        or_rel = (r['or'] - mor) / 10 if has_or else 0.0
        wt_rel = (r['wt'] - mwt) / 10 if r.get('wt') and wts else 0.0
        runs = form_runs(r.get('form'))
        if runs:
            w, s, t = 1.0, 0.0, 0.0
            for pts, _ in reversed(runs):
                s += pts * w; t += w; w *= .75
            form_last, form_avg, nf_last = runs[-1][0], s / t, float(runs[-1][1])
        else:
            form_last = form_avg = nf_last = 0.0
        d = r.get('days')
        debut = 1.0 if d is None and not runs else 0.0
        age = r.get('age') or 0
        out.append([
            math.log(p / tot), 0.0 if r.get('fc') else 1.0,
            or_rel, or_rel * hcap, 0.0 if has_or else 1.0, wt_rel, wt_rel * hcap,
            form_last, form_avg, 0.0 if runs else 1.0, nf_last,
            float(d is not None and d <= 7), float(d is not None and 31 <= d <= 90),
            float(d is not None and 91 <= d <= 180), float(d is not None and d > 180), debut,
            float(0 < age <= 3), float(age >= 10),
        ])
    return out


def probs(race, coef):
    """Win chance per runner: softmax of features . coef (coef maps feature name -> weight)."""
    w = [coef.get(f, 0.0) for f in FEATURES]
    s = [sum(a * b for a, b in zip(x, w)) for x in features(race)]
    m = max(s)
    e = [math.exp(v - m) for v in s]
    z = sum(e)
    return [v / z for v in e]


def forecast_probs(race):
    """The betting forecast alone, as win chances (the baseline the model has to beat)."""
    return probs(race, {'lfc': 1.0})
