# Tennis backtest

29188 ATP and WTA singles results read from ESPN (2023-12-29 to 2026-11-09). Elo ratings were built match by match; each of the 14477 matches from 2025-07-01 on was predicted before it was played. No odds are in the feed, so this shows hit rate and calibration, not profit.

## How often the pick won

| Matches | Picks | Won |
|---|---|---|
| All | 14477 | 63.0% |
| ATP | 2563 | 63.1% |
| WTA | 11914 | 62.9% |
| Both players with 10+ rated matches | 11614 | 63.0% |
| Main draw only (no qualifying) | 10138 | 64.0% |

Log loss 0.6403 (a coin toss scores 0.6931; lower is better).

## Are the chances honest?

| Pick given | Picks | Won | Price needed to break even |
|---|---|---|---|
| 50%-60% | 5196 | 53.8% | 1.86 |
| 60%-70% | 4381 | 61.2% | 1.63 |
| 70%-80% | 3061 | 69.6% | 1.44 |
| 80%-90% | 1483 | 79.9% | 1.25 |
| 90%-100% | 356 | 91.0% | 1.10 |

**Each day's two most confident picks as a double:** came in on 65.1% of 479 days; it pays only if the bookmaker offers more than 1.54 for it.

## First set, total games and the match acca

From one game-by-game model per match (tennis/games.py), its set-to-set swing tuned to the games in even matches before 2025-07-01 (ATP 0.136, WTA 0.142). 13490 test matches played out in full (no retirements or walkovers).

| Call | Model expected | Came in | Price needed to break even |
|---|---|---|---|
| Pick wins the first set | 61.1% | 59.9% | 1.67 |
| Total games over/under | 54.1% | 50.6% | 1.98 |
| Match acca (all three) | 26.7% | 25.6% | 3.91 |

| Games call given | Calls | Came in |
|---|---|---|
| 50%-55% | 10898 | 49.2% |
| 55%-60% | 1788 | 53.5% |
| 60%-65% | 445 | 62.7% |
| 65%-70% | 224 | 56.7% |
| 70%-100% | 135 | 74.8% |
