"""Expected corners in a match, and the chance of going over or under a line.

Each side's expected corners = the league's average for that venue x a fitted mix of:
  - how many corners the side has been winning, and the opponent conceding (relative to the league),
  - the same for shots, which lead to corners,
  - the match odds: who's favourite (favourites win more corners) and how open the bookmakers expect it to be.
Form is an exponentially weighted average, so recent matches count most, pulled towards the league average
until a side has played a few games. Home and away corners are fitted as two Poisson regressions; the total
is spread as a negative binomial whose extra spread is fitted on the same training matches.
"""
import math

import numpy as np

DECAY = 0.92          # each older match counts 0.92x the next one (half-life about 8 matches)
PRIOR = 4.0           # every side starts with 4 matches' worth of league-average form
SEASON_CARRY = 0.5    # last season's form is halved at the start of a new one
LEAGUE_DECAY = 0.995
FEATURES = ['const', 'corners won', 'opp. corners conceded', 'shots', 'opp. shots conceded', 'favourite', 'open game']


def market(m):
    """(log home/away win-chance ratio, log-odds of over 2.5 goals) from the match odds; 0 when missing."""
    sup = goals = 0.0
    if m.get('oh') and m.get('oa') and m.get('od'):
        ph, pd, pa = 1 / m['oh'], 1 / m['od'], 1 / m['oa']
        sup = math.log(ph / pa)
    if m.get('over') and m.get('under'):
        po, pu = 1 / m['over'], 1 / m['under']
        goals = math.log(po / pu)
    return sup, goals


class Tracker:
    """League averages and each side's form, updated match by match in date order."""

    def __init__(self):
        self.league = {}
        self.team = {}

    def league_avg(self, div):
        L = self.league.get(div)
        if not L or L['w'] < 30:
            return None
        return {'hc': L['hc'] / L['w'], 'ac': L['ac'] / L['w'],
                'hs': L['hs'] / L['ws'] if L['ws'] > 30 else None, 'as': L['as'] / L['ws'] if L['ws'] > 30 else None}

    def _ratio(self, team, key, wkey='w'):
        t = self.team.get(team)
        if not t:
            return 1.0
        return (t[key] + PRIOR) / (t[wkey] + PRIOR)

    def features(self, m):
        """(home-side features, away-side features, league home corners, league away corners), or None early on."""
        L = self.league_avg(m['div'])
        if L is None:
            return None
        h, a = m['home'], m['away']
        sup, goals = market(m)
        r = self._ratio
        fh = [1.0, math.log(r(h, 'cf')), math.log(r(a, 'ca')), math.log(r(h, 'sf', 'ws')), math.log(r(a, 'sa', 'ws')), sup, goals]
        fa = [1.0, math.log(r(a, 'cf')), math.log(r(h, 'ca')), math.log(r(a, 'sf', 'ws')), math.log(r(h, 'sa', 'ws')), -sup, goals]
        return fh, fa, L['hc'], L['ac']

    def _side(self, team, season):
        t = self.team.get(team)
        if t is None:
            t = self.team[team] = dict(w=0.0, cf=0.0, ca=0.0, ws=0.0, sf=0.0, sa=0.0, season=season)
        elif t['season'] != season:
            for k in ('w', 'cf', 'ca', 'ws', 'sf', 'sa'):
                t[k] *= SEASON_CARRY
            t['season'] = season
        return t

    def update(self, m, season):
        """Fold a played match into the league average and both sides' form."""
        if m['hc'] is None or m['ac'] is None:
            return
        L = self.league.setdefault(m['div'], dict(w=0.0, hc=0.0, ac=0.0, ws=0.0, hs=0.0, **{'as': 0.0}))
        avg = self.league_avg(m['div'])
        shots = m['hs'] is not None and m['as'] is not None
        if avg:
            h, a = self._side(m['home'], season), self._side(m['away'], season)
            for t, cf, ca in ((h, m['hc'] / avg['hc'], m['ac'] / avg['ac']), (a, m['ac'] / avg['ac'], m['hc'] / avg['hc'])):
                t['w'] = DECAY * t['w'] + 1
                t['cf'] = DECAY * t['cf'] + cf
                t['ca'] = DECAY * t['ca'] + ca
            if shots and avg['hs'] and avg['as']:
                for t, sf, sa in ((h, m['hs'] / avg['hs'], m['as'] / avg['as']), (a, m['as'] / avg['as'], m['hs'] / avg['hs'])):
                    t['ws'] = DECAY * t['ws'] + 1
                    t['sf'] = DECAY * t['sf'] + sf
                    t['sa'] = DECAY * t['sa'] + sa
        for k in ('w', 'hc', 'ac'):
            L[k] *= LEAGUE_DECAY
        L['w'] += 1
        L['hc'] += m['hc']
        L['ac'] += m['ac']
        if shots:
            for k in ('ws', 'hs', 'as'):
                L[k] *= LEAGUE_DECAY
            L['ws'] += 1
            L['hs'] += m['hs']
            L['as'] += m['as']


def fit_poisson(X, y, offset, ridge=1.0, iters=25):
    """Poisson regression (log link, with an offset) by Newton's method, lightly pulled towards zero."""
    X, y, offset = np.asarray(X, float), np.asarray(y, float), np.asarray(offset, float)
    beta = np.zeros(X.shape[1])
    pen = np.full(X.shape[1], ridge)
    pen[0] = 0.0
    for _ in range(iters):
        mu = np.exp(X @ beta + offset)
        grad = X.T @ (y - mu) - pen * beta
        hess = (X * mu[:, None]).T @ X + np.diag(pen)
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    return beta


def expected(f, model):
    """(home corners, away corners) expected for a match, from Tracker.features() and a fitted model."""
    fh, fa, lh, la = f
    return (lh * math.exp(float(np.dot(model['beta_home'], fh))),
            la * math.exp(float(np.dot(model['beta_away'], fa))))


def dispersion(totals, means):
    """Negative binomial size k from the extra spread of totals around their means (None: plain Poisson)."""
    t, m = np.asarray(totals, float), np.asarray(means, float)
    extra = ((t - m) ** 2 - m).sum()
    return float((m ** 2).sum() / extra) if extra > 0 else None


def p_over(mean, line, k):
    """Chance the total goes over a .5 line."""
    n = int(math.floor(line))
    if k is None:
        cdf = sum(math.exp(-mean + t * math.log(mean) - math.lgamma(t + 1)) for t in range(n + 1))
    else:
        lp = k / (k + mean)
        cdf = sum(math.exp(math.lgamma(t + k) - math.lgamma(k) - math.lgamma(t + 1) + k * math.log(lp) + t * math.log(1 - lp))
                  for t in range(n + 1))
    return max(0.0, min(1.0, 1 - cdf))


def call(mean, line, k):
    """('over' or 'under', chance) for the likelier side of the line."""
    p = p_over(mean, line, k)
    return ('over', p) if p >= 0.5 else ('under', 1 - p)


def main_line(avg_total):
    """The .5 line nearest a league's average total (e.g. 10.2 -> 10.5, 9.8 -> 9.5)."""
    return math.floor(avg_total) + 0.5
