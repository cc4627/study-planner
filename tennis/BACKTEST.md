# Tennis backtest

29123 ATP and WTA singles results read from ESPN (2023-12-29 to 2026-11-04). Elo ratings were built match by match; each of the 14412 matches from 2025-07-01 on was predicted before it was played. No odds are in the feed, so this shows hit rate and calibration, not profit.

## How often the pick won

| Matches | Picks | Won |
|---|---|---|
| All | 14412 | 62.9% |
| ATP | 2545 | 62.9% |
| WTA | 11867 | 63.0% |
| Both players with 10+ rated matches | 11553 | 63.0% |
| Main draw only (no qualifying) | 10073 | 64.0% |

Log loss 0.6404 (a coin toss scores 0.6931; lower is better).

## Are the chances honest?

| Pick given | Picks | Won | Price needed to break even |
|---|---|---|---|
| 50%-60% | 5170 | 53.8% | 1.86 |
| 60%-70% | 4366 | 61.1% | 1.64 |
| 70%-80% | 3046 | 69.6% | 1.44 |
| 80%-90% | 1475 | 79.9% | 1.25 |
| 90%-100% | 355 | 91.0% | 1.10 |

**Each day's two most confident picks as a double:** came in on 65.1% of 475 days; it pays only if the bookmaker offers more than 1.54 for it.
