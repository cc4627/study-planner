"""Expected corners or yellow cards in a match, and the chance of going over or under a line.

Each side's expected count = the league's average for that venue x a fitted mix of:
  - how many the side has been getting, and the opponent conceding (relative to the league),
  - a related count: shots for corners (shots lead to corners), fouls for cards (fouls lead to bookings),
  - the match odds: who's favourite, how one-sided it is, and how open the bookmakers expect it to be,
  - for cards, the referee's record (where the league's files name the referee).
Form is an exponentially weighted average, so recent matches count most, pulled towards the league average
until a side has played a few games. Home and away counts are fitted as two Poisson regressions; the total
is spread as a negative binomial whose extra spread is fitted on the same training matches.
"""
import math

import numpy as np

DECAY = 0.92          # each older match counts 0.92x the next one (half-life about 8 matches)
PRIOR = 4.0           # every side starts with 4 matches' worth of league-average form
SEASON_CARRY = 0.5    # last season's form is halved at the start of a new one
LEAGUE_DECAY = 0.995
STATS = {
    'corners': dict(h='hc', a='ac', xh='hs', xa='as', ref=False, related='shots'),
    'cards': dict(h='hy', a='ay', xh='hf', xa='af', ref=True, related='fouls'),
}
FEATURES = ['const', 'count for', 'opp. count against', 'related for', 'opp. related against', 'favourite', 'one-sided',
            'open game', 'referee']


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
    """League averages, each side's form and each referee's record for one stat, updated match by match."""

    def __init__(self, stat):
        self.k = STATS[stat]
        self.league = {}
        self.team = {}
        self.refs = {}
        self.div_of = {}  # each side's league, for European matches between leagues

    def league_avg(self, div):
        L = self.league.get(div)
        if not L or L['w'] < 30:
            return None
        return {'h': L['h'] / L['w'], 'a': L['a'] / L['w'],
                'xh': L['xh'] / L['wx'] if L['wx'] > 30 else None, 'xa': L['xa'] / L['wx'] if L['wx'] > 30 else None}

    def _ratio(self, team, key, wkey='w'):
        t = self.team.get(team)
        if not t:
            return 1.0
        return (t[key] + PRIOR) / (t[wkey] + PRIOR)

    def _ref(self, m):
        r = self.refs.get((m['div'], m.get('ref'))) if self.k['ref'] and m.get('ref') else None
        return (r['x'] + PRIOR) / (r['w'] + PRIOR) if r else 1.0

    def features(self, m):
        """(home-side features, away-side features, league home average, league away average), or None early on."""
        L = self.league_avg(m['div'])
        if L is None:
            return None
        h, a = m['home'], m['away']
        sup, goals = market(m)
        r, ref = self._ratio, math.log(self._ref(m))
        fh = [1.0, math.log(r(h, 'f')), math.log(r(a, 'a')), math.log(r(h, 'xf', 'wx')), math.log(r(a, 'xa', 'wx')), sup, -abs(sup), goals, ref]
        fa = [1.0, math.log(r(a, 'f')), math.log(r(h, 'a')), math.log(r(a, 'xf', 'wx')), math.log(r(h, 'xa', 'wx')), -sup, -abs(sup), goals, ref]
        return fh, fa, L['h'], L['a']

    def features_cross(self, m):
        """Features for a match between sides from different leagues (a European tie): each side's expected count
        starts from its own league's average for that venue. A side not in the domestic files gets the average
        of all the leagues."""
        avgs = [a for a in (self.league_avg(d) for d in self.league) if a]
        if not avgs:
            return None
        mean = lambda key: sum(a[key] for a in avgs) / len(avgs)
        lh = self.league_avg(self.div_of.get(m['home'], ''))
        la = self.league_avg(self.div_of.get(m['away'], ''))
        h, a = m['home'], m['away']
        sup, goals = market(m)
        r = self._ratio
        fh = [1.0, math.log(r(h, 'f')), math.log(r(a, 'a')), math.log(r(h, 'xf', 'wx')), math.log(r(a, 'xa', 'wx')), sup, -abs(sup), goals, 0.0]
        fa = [1.0, math.log(r(a, 'f')), math.log(r(h, 'a')), math.log(r(a, 'xf', 'wx')), math.log(r(h, 'xa', 'wx')), -sup, -abs(sup), goals, 0.0]
        return fh, fa, (lh or {}).get('h') or mean('h'), (la or {}).get('a') or mean('a')

    def _side(self, team, season):
        t = self.team.get(team)
        if t is None:
            t = self.team[team] = dict(w=0.0, f=0.0, a=0.0, wx=0.0, xf=0.0, xa=0.0, season=season)
        elif t['season'] != season:
            for key in ('w', 'f', 'a', 'wx', 'xf', 'xa'):
                t[key] *= SEASON_CARRY
            t['season'] = season
        return t

    def update(self, m, season):
        """Fold a played match into the league average, both sides' form and the referee's record."""
        k = self.k
        hv, av = m.get(k['h']), m.get(k['a'])
        if hv is None or av is None:
            return
        self.div_of[m['home']] = self.div_of[m['away']] = m['div']
        hx, ax = m.get(k['xh']), m.get(k['xa'])
        L = self.league.setdefault(m['div'], dict(w=0.0, h=0.0, a=0.0, wx=0.0, xh=0.0, xa=0.0))
        avg = self.league_avg(m['div'])
        related = hx is not None and ax is not None
        if avg and avg['h'] and avg['a']:
            hs, as_ = self._side(m['home'], season), self._side(m['away'], season)
            for t, f, a in ((hs, hv / avg['h'], av / avg['a']), (as_, av / avg['a'], hv / avg['h'])):
                t['w'] = DECAY * t['w'] + 1
                t['f'] = DECAY * t['f'] + f
                t['a'] = DECAY * t['a'] + a
            if related and avg['xh'] and avg['xa']:
                for t, f, a in ((hs, hx / avg['xh'], ax / avg['xa']), (as_, ax / avg['xa'], hx / avg['xh'])):
                    t['wx'] = DECAY * t['wx'] + 1
                    t['xf'] = DECAY * t['xf'] + f
                    t['xa'] = DECAY * t['xa'] + a
            if k['ref'] and m.get('ref'):
                rr = self.refs.setdefault((m['div'], m['ref']), dict(w=0.0, x=0.0))
                rr['w'] = DECAY * rr['w'] + 1
                rr['x'] = DECAY * rr['x'] + (hv + av) / (avg['h'] + avg['a'])
        for key in ('w', 'h', 'a'):
            L[key] *= LEAGUE_DECAY
        L['w'] += 1
        L['h'] += hv
        L['a'] += av
        if related:
            for key in ('wx', 'xh', 'xa'):
                L[key] *= LEAGUE_DECAY
            L['wx'] += 1
            L['xh'] += hx
            L['xa'] += ax


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
    """(home, away) counts expected for a match, from Tracker.features() and a fitted model."""
    fh, fa, lh, la = f
    return (lh * math.exp(float(np.dot(model['beta_home'], fh))),
            la * math.exp(float(np.dot(model['beta_away'], fa))))


def dispersion(totals, means):
    """Negative binomial size k from the extra spread of totals around their means (None: plain Poisson)."""
    t, m = np.asarray(totals, float), np.asarray(means, float)
    extra = ((t - m) ** 2 - m).sum()
    return float((m ** 2).sum() / extra) if extra > 0 else None


def p_over(mean, line, k):
    """Chance the total goes over a .5 line (k None: plain Poisson)."""
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
