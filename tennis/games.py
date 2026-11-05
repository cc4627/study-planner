"""First-set winner, total games and the match acca for a tennis match, from one game-by-game model.

Each player holds serve with a set chance, either side of the tour's usual hold rate and spread just enough
that the model's match-win chance equals the Elo pick's. Real sets are more one-sided than steady chances
would make them (form and momentum swing), so in each set the gap between the two players shifts one way
or the other by a "swing", tuned so that even matches average as many games as they really do. Exact sums
over every way a set and a match can go then give the joint chance of (match winner, first-set winner,
total games), so the acca of all three calls on a match is priced as one bet rather than three.
Sets go to a tiebreak at 6-6; the player who received last serves first in the next set.
"""
from functools import lru_cache

HOLD = {'ATP': 0.79, 'WTA': 0.65}   # tour-wide service hold rates
SWING = {'ATP': 0.0, 'WTA': 0.0}    # set-to-set shift in the hold gap, set by calibrate()
LINES = {('ATP', 3): 22.5, ('WTA', 3): 21.5, ('ATP', 5): 38.5, ('WTA', 5): 38.5}


def _clip(h):
    return round(min(max(h, 0.05), 0.98), 4)


@lru_cache(maxsize=None)
def _set(ha, hb, a_serves):
    """((a won the set, games in the set), chance) pairs for a set from 0-0 with steady hold chances."""
    out = {}

    def go(ga, gb, server_a, p):
        if p < 1e-12:
            return
        if (ga >= 6 or gb >= 6) and abs(ga - gb) >= 2 or ga == 7 or gb == 7:
            key = (ga > gb, ga + gb)
            out[key] = out.get(key, 0.0) + p
            return
        if ga == 6 and gb == 6:  # tiebreak, counted as one game
            t = (ha + 1 - hb) / 2
            out[(True, 13)] = out.get((True, 13), 0.0) + p * t
            out[(False, 13)] = out.get((False, 13), 0.0) + p * (1 - t)
            return
        win = ha if server_a else 1 - hb  # chance A wins this game
        go(ga + 1, gb, not server_a, p * win)
        go(ga, gb + 1, not server_a, p * (1 - win))

    go(0, 0, a_serves, 1.0)
    return tuple(out.items())


@lru_cache(maxsize=None)
def _set_mix(base, d, swing, a_serves):
    """A set where the hold gap d swings by +/- swing (half the time each way)."""
    if swing <= 0:
        return _set(_clip(base + d), _clip(base - d), a_serves)
    out = {}
    for s in (swing, -swing):
        for k, p in _set(_clip(base + d + s), _clip(base - d - s), a_serves):
            out[k] = out.get(k, 0.0) + 0.5 * p
    return tuple(out.items())


def joint(base, d, swing=0.0, best_of=3):
    """{(a won the match, a won the first set, total games): chance}, the first server chosen at random."""
    base, d, swing = round(base, 4), round(d, 4), round(swing, 4)
    need = best_of // 2 + 1
    states = {}
    for a_first in (True, False):
        for (won, g), p in _set_mix(base, d, swing, a_first):
            next_a = (not a_first) if g % 2 == 1 else a_first
            key = (1 if won else 0, 0 if won else 1, g, won, next_a)
            states[key] = states.get(key, 0.0) + 0.5 * p
    out = {}
    while states:
        nxt = {}
        for (sa, sb, games, first, a_serves), p in states.items():
            if sa == need or sb == need:
                k = (sa == need, first, games)
                out[k] = out.get(k, 0.0) + p
                continue
            for (won, g), q in _set_mix(base, d, swing, a_serves):
                next_a = (not a_serves) if g % 2 == 1 else a_serves
                k = (sa + won, sb + (not won), games + g, first, next_a)
                nxt[k] = nxt.get(k, 0.0) + p * q
        states = nxt
    return out


def fit(p_match, tour='ATP', best_of=3):
    """The hold gap d that gives A the stated chance of winning the match."""
    base, swing = HOLD.get(tour, 0.72), SWING.get(tour, 0.0)
    lo, hi = -0.45, 0.45
    for _ in range(28):
        d = (lo + hi) / 2
        pw = sum(p for (won, _, _), p in joint(base, d, swing, best_of).items() if won)
        if pw < p_match:
            lo = d
        else:
            hi = d
    return (lo + hi) / 2


def calls(p_pick, tour='ATP', best_of=3):
    """For the picked player (match chance p_pick): first-set chance, the games call and the acca's chance."""
    d = fit(p_pick, tour, best_of)
    dist = joint(HOLD.get(tour, 0.72), d, SWING.get(tour, 0.0), best_of)
    line = LINES.get((tour, best_of), 22.5)
    first = sum(p for (_, f, _), p in dist.items() if f)
    over = sum(p for (_, _, g), p in dist.items() if g > line)
    side = 'over' if over >= 0.5 else 'under'
    acca = sum(p for (w, f, g), p in dist.items() if w and f and ((g > line) == (side == 'over')))
    return {'first': first, 'games': {'line': line, 'side': side, 'p': over if side == 'over' else 1 - over}, 'acca': acca}


def expected_games(base, d=0.0, swing=0.0, best_of=3):
    return sum(p * g for (_, _, g), p in joint(base, d, swing, best_of).items())


def calibrate(avg_close, tour, best_of=3):
    """Set the tour's swing so an even match averages avg_close games, as close matches really do."""
    base = HOLD.get(tour, 0.72)
    lo, hi = 0.0, 0.45
    if expected_games(base, 0.0, 0.0, best_of) <= avg_close:
        SWING[tour] = 0.0
        return 0.0
    for _ in range(22):
        mid = (lo + hi) / 2
        if expected_games(base, 0.0, mid, best_of) > avg_close:
            lo = mid
        else:
            hi = mid
    SWING[tour] = round((lo + hi) / 2, 4)
    return SWING[tour]


def summary(m, best_of=3):
    """(finished in full, first-set winner 1/2, total games) from a result's set scores; tiebreak sets count 13."""
    sets = m.get('sets') or []
    need = best_of // 2 + 1
    won1 = sum(1 for a, b in sets if a > b)
    won2 = sum(1 for a, b in sets if b > a)
    full = (won1 == need or won2 == need) and all(max(a, b) >= 6 for a, b in sets)
    first = (1 if sets[0][0] > sets[0][1] else 2) if sets else None
    return full, first, sum(a + b for a, b in sets)


@lru_cache(maxsize=None)
def _calls_at(p_grid, tour, best_of, hold, swing):
    return calls(p_grid, tour, best_of)


def quick(p_pick, tour='ATP', best_of=3):
    """calls() with the chance rounded to the nearest half percent, for scoring many matches."""
    return _calls_at(round(round(p_pick * 200) / 200, 3), tour, best_of, HOLD.get(tour), SWING.get(tour))
