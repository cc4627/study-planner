# Corners backtest

20967 matches from 2021/22 to 2023/24 fitted the model; it was then run once over 16408 matches from 2024-07-26 to 2026-11-02 in 22 leagues, which it never saw. Each league's line is the .5 nearest its average total corners in the fitting seasons.

## How close the expected corners were

| | Average miss (corners) | Log loss on over/under the line |
|---|---|---|
| League average only | 2.71 | 0.6879 |
| Model | 2.68 | 0.6817 |

Lower is better. Corners are noisy: even a perfect model would miss by about 2.5 a match.

## When the model is confident, how often is it right?

| Model said | Calls | Came in | Price needed to break even |
|---|---|---|---|
| 50%-55% | 7290 | 51.6% | 1.94 |
| 55%-60% | 5504 | 57.2% | 1.75 |
| 60%-65% | 2711 | 61.0% | 1.64 |
| 65%-70% | 782 | 67.1% | 1.49 |
| 70%-75% | 119 | 70.6% | 1.42 |
| 75%-100% | 2 | 50.0% | 2.00 |

## The daily corner double

Each day, the two most confident calls across all leagues, doubled up. €1 a day.

| | Days | Model expected | Came in | Price needed to break even |
|---|---|---|---|---|
| Each leg on its own | 1080 | 63.8% | 64.4% | 1.55 |
| The double | 540 | 40.9% | 42.6% | 2.35 |

**What it means:** the double came in 43% of days, so it only made money where the bookmaker paid more than **2.35** for it (each leg more than about 1.55). Bookmakers usually price their main corners line near evens (about 1.83 each side), but they set that line per match, so a confident call at the league's usual line is normally offered shorter than that. Compare the fair price on the page with what your bookmaker offers: only a bigger price is worth taking.

## Match result picks (for reference)

The bookmakers' favourite won 50.8% of 16408 test matches; backing it at the average odds returned -4.6%.

## Fitted weights

| Feature | Home corners | Away corners |
|---|---|---|
| const | -0.058 | +0.042 |
| corners won | +0.252 | +0.309 |
| opp. corners conceded | +0.178 | +0.202 |
| shots | +0.088 | +0.006 |
| opp. shots conceded | +0.180 | +0.299 |
| favourite | +0.138 | +0.147 |
| open game | +0.001 | +0.008 |

Spread of totals: negative binomial size k = 68.4.
