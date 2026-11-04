"""Elo ratings for tennis players, the standard way: everyone starts at 1500, and each result moves both
players by K x (result - expected), with K shrinking as a player's record grows (new players move fast,
established ones slowly). Men's Grand Slam matches are best of five, which favours the stronger player, so
their chance is converted from a per-set strength."""
import math

START = 1500.0


def k(n):
    return 250.0 / (n + 5) ** 0.4


def best_of_five(p3):
    """Chance of winning a best-of-five match, given the chance of winning a best-of-three one."""
    lo, hi = 0.0, 1.0
    for _ in range(60):  # per-set chance s with s^2 (3 - 2s) = p3
        s = (lo + hi) / 2
        if s * s * (3 - 2 * s) < p3:
            lo = s
        else:
            hi = s
    s = (lo + hi) / 2
    return s ** 3 * (10 - 15 * s + 6 * s * s)


class Elo:
    def __init__(self):
        self.r = {}
        self.n = {}

    def rating(self, pid):
        return self.r.get(pid, START)

    def p(self, a, b, bo5=False):
        """Chance a beats b."""
        p = 1 / (1 + 10 ** ((self.rating(b) - self.rating(a)) / 400))
        return best_of_five(p) if bo5 else p

    def update(self, winner, loser):
        p = self.p(winner, loser)
        nw, nl = self.n.get(winner, 0), self.n.get(loser, 0)
        self.r[winner] = self.rating(winner) + k(nw) * (1 - p)
        self.r[loser] = self.rating(loser) - k(nl) * (1 - p)
        self.n[winner], self.n[loser] = nw + 1, nl + 1

    def played(self, pid):
        return self.n.get(pid, 0)


def bo5(m):
    return m['tour'] == 'atp' and m.get('major') and 'qualif' not in (m.get('round') or '').lower()


def logloss(p):
    return -math.log(min(max(p, 1e-9), 1 - 1e-9))
