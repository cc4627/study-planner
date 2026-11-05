"""First-set winner, total games and the match acca for a tennis match, from one game-by-game model.

Each player holds serve with a fixed chance; the two chances sit either side of the tour's usual hold rate,
spread just enough that the model's match-win chance equals the Elo pick's. From that, exact sums over every
way a set and a match can go give the joint chance of (match winner, first-set winner, total games), so the
acca of all three calls on a match is priced as one bet rather than three independent ones.
Sets go to a tiebreak at 6-6; the player who received last serves first in the next set.
"""
from functools import lru_cache

HOLD = {'ATP': 0.79, 'WTA': 0.65}         # tour-wide service hold rates
LINES = {('ATP', 3): 22.5, ('WTA', 3): 21.5, ('ATP', 5): 38.5, ('WTA', 5): 38.5}


@lru_cache(maxsize=None)
def _set(ha, hb, a_serves):
    """{(a won the set, games in the set): chance} for a set from 0-0."""
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


def joint(ha, hb, best_of=3):
    """{(a won the match, a won the first set, total games): chance}, the first server chosen at random."""
    need = best_of // 2 + 1
    states = {}
    for a_first in (True, False):
        for (won, g), p in _set(ha, hb, a_first):
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
            for (won, g), q in _set(ha, hb, a_serves):
                next_a = (not a_serves) if g % 2 == 1 else a_serves
                k = (sa + won, sb + (not won), games + g, first, next_a)
                nxt[k] = nxt.get(k, 0.0) + p * q
        states = nxt
    return out


def fit(p_match, tour='ATP', best_of=3):
    """(hold A, hold B) about the tour's hold rate that give A the stated chance of winning the match."""
    base = HOLD.get(tour, 0.72)
    lo, hi = -0.35, 0.35
    for _ in range(30):
        d = (lo + hi) / 2
        ha, hb = min(max(base + d, 0.2), 0.98), min(max(base - d, 0.2), 0.98)
        pw = sum(p for (won, _, _), p in joint(round(ha, 4), round(hb, 4), best_of).items() if won)
        if pw < p_match:
            lo = d
        else:
            hi = d
    d = (lo + hi) / 2
    return round(min(max(base + d, 0.2), 0.98), 4), round(min(max(base - d, 0.2), 0.98), 4)


def calls(p_pick, tour='ATP', best_of=3):
    """For the picked player (match chance p_pick): first-set chance, the games call and the acca's chance."""
    ha, hb = fit(p_pick, tour, best_of)
    dist = joint(ha, hb, best_of)
    line = LINES.get((tour, best_of), 22.5)
    first = sum(p for (_, f, _), p in dist.items() if f)
    over = sum(p for (_, _, g), p in dist.items() if g > line)
    side = 'over' if over >= 0.5 else 'under'
    acca = sum(p for (w, f, g), p in dist.items() if w and f and ((g > line) == (side == 'over')))
    return {'first': first, 'games': {'line': line, 'side': side, 'p': over if side == 'over' else 1 - over}, 'acca': acca}


def expected_games(ha, hb, best_of=3):
    return sum(p * g for (_, _, g), p in joint(ha, hb, best_of).items())


def calibrate(avg_close, tour, best_of=3):
    """Set the tour's hold rate so an even match averages avg_close games, as close matches really do."""
    lo, hi = 0.5, 0.95
    for _ in range(25):
        mid = round((lo + hi) / 2, 4)
        if expected_games(mid, mid, best_of) < avg_close:
            lo = mid
        else:
            hi = mid
    HOLD[tour] = round((lo + hi) / 2, 4)
    return HOLD[tour]


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
def _calls_at(p_grid, tour, best_of, hold):
    return calls(p_grid, tour, best_of)


def quick(p_pick, tour='ATP', best_of=3):
    """calls() with the chance rounded to the nearest half percent, for scoring many matches."""
    return _calls_at(round(round(p_pick * 200) / 200, 3), tour, best_of, HOLD.get(tour))
