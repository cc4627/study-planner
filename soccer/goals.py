"""Goals over/under 2.5 and both teams to score, from the match odds.

The home and away goal rates (independent Poisson) are solved so that they reproduce the bookmakers'
average 1X2 and over/under 2.5 odds with the margin taken out. Over 2.5 is then the market's own view, and
both-to-score is the chance each side scores at least once: (1 - e^-home rate) x (1 - e^-away rate).
"""
import math

MAX = 11


def _pois(l):
    out, p = [], math.exp(-l)
    for k in range(MAX):
        out.append(p)
        p *= l / (k + 1)
    return out


def _probs(lh, la):
    ph, pa = _pois(lh), _pois(la)
    home = sum(ph[i] * pa[j] for i in range(MAX) for j in range(i))
    away = sum(ph[i] * pa[j] for j in range(MAX) for i in range(j))
    under = sum(ph[i] * pa[j] for i in range(3) for j in range(3 - i))
    return home, away, 1 - under


def rates(m, base_total=2.7):
    """(home rate, away rate) matching the odds, or None without 1X2 odds."""
    if not (m.get('oh') and m.get('od') and m.get('oa')):
        return None
    inv = [1 / m['oh'], 1 / m['od'], 1 / m['oa']]
    ph, _, pa = (x / sum(inv) for x in inv)
    po = None
    if m.get('over') and m.get('under'):
        po = (1 / m['over']) / (1 / m['over'] + 1 / m['under'])
    total, sup = base_total, 0.0
    split = lambda t, s: (max((t + s) / 2, 0.02), max((t - s) / 2, 0.02))
    for _ in range(6):
        if po is not None:
            lo, hi = 0.3, 7.0
            for _ in range(40):
                mid = (lo + hi) / 2
                if _probs(*split(mid, sup))[2] < po:
                    lo = mid
                else:
                    hi = mid
            total = (lo + hi) / 2
        lo, hi = -total + 0.04, total - 0.04
        for _ in range(40):
            mid = (lo + hi) / 2
            h, a, _ = _probs(*split(total, mid))
            if h - a < ph - pa:
                lo = mid
            else:
                hi = mid
        sup = (lo + hi) / 2
    return split(total, sup)


def calls(m):
    """{'goals': ('over'/'under', chance), 'btts': ('yes'/'no', chance)} from the odds, or None."""
    r = rates(m)
    if not r:
        return None
    lh, la = r
    po = _probs(lh, la)[2]
    if m.get('over') and m.get('under'):
        po = (1 / m['over']) / (1 / m['over'] + 1 / m['under'])
    pb = (1 - math.exp(-lh)) * (1 - math.exp(-la))
    return {'goals': ('over', po) if po >= 0.5 else ('under', 1 - po),
            'btts': ('yes', pb) if pb >= 0.5 else ('no', 1 - pb), 'rates': (lh, la)}
