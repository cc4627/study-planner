# Tennis backtest

29133 ATP and WTA singles results read from ESPN (2023-12-29 to 2026-11-04). Elo ratings were built match by match; each of the 14422 matches from 2025-07-01 on was predicted before it was played. No odds are in the feed, so this shows hit rate and calibration, not profit.

## How often the pick won

| Matches | Picks | Won |
|---|---|---|
| All | 14422 | 63.0% |
| ATP | 2549 | 63.0% |
| WTA | 11873 | 62.9% |
| Both players with 10+ rated matches | 11563 | 63.0% |
| Main draw only (no qualifying) | 10083 | 64.0% |

Log loss 0.6404 (a coin toss scores 0.6931; lower is better).

## Are the chances honest?

| Pick given | Picks | Won | Price needed to break even |
|---|---|---|---|
| 50%-60% | 5174 | 53.8% | 1.86 |
| 60%-70% | 4369 | 61.1% | 1.64 |
| 70%-80% | 3047 | 69.6% | 1.44 |
| 80%-90% | 1476 | 79.9% | 1.25 |
| 90%-100% | 356 | 91.0% | 1.10 |

**Each day's two most confident picks as a double:** came in on 65.3% of 475 days; it pays only if the bookmaker offers more than 1.53 for it.

## First set, total games and the match acca

From one game-by-game model per match (tennis/games.py), its hold rates tuned to the games in even matches before 2025-07-01 (ATP 0.500, WTA 0.500). 13436 test matches played out in full (no retirements or walkovers).

| Call | Model expected | Came in | Price needed to break even |
|---|---|---|---|
| Pick wins the first set | 61.1% | 60.0% | 1.67 |
| Total games over/under | 57.7% | 48.3% | 2.07 |
| Match acca (all three) | 24.5% | 20.4% | 4.90 |

| Games call given | Calls | Came in |
|---|---|---|
| 50%-55% | 3701 | 48.9% |
| 55%-60% | 4674 | 48.1% |
| 60%-65% | 4895 | 47.3% |
| 65%-70% | 89 | 64.0% |
| 70%-100% | 77 | 74.0% |
