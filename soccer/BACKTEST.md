# Soccer backtest

Football-data.co.uk has no corner or card odds, so these show how often each call came in and the price a bookmaker would need to pay for it to break even, not profit. Bookmakers usually price their main line near evens (about 1.83 each side), but they set that line per match, so a confident call at the league's usual line is normally offered shorter than that: compare the fair price on the page with your bookmaker's.

## Corners

20967 matches from 2021/22 to 2023/24 fitted the model; it was then run once over 16252 matches from 2024-07-26 to 2026-11-02 in 21 leagues, which it never saw. Each league's line is the .5 nearest its average total in the fitting seasons.

| | Average miss | Log loss on over/under the line |
|---|---|---|
| League average only | 2.71 | 0.6879 |
| Model | 2.67 | 0.6811 |

Lower is better.

### Corners: when the model is confident, how often is it right?

| Model said | Calls | Came in | Price needed to break even |
|---|---|---|---|
| 50%-55% | 7466 | 51.1% | 1.96 |
| 55%-60% | 5345 | 57.1% | 1.75 |
| 60%-65% | 2572 | 61.9% | 1.62 |
| 65%-70% | 766 | 67.5% | 1.48 |
| 70%-75% | 99 | 71.7% | 1.39 |

### Corners: the daily double (each day's two most confident calls)

| | Days | Model expected | Came in | Price needed to break even |
|---|---|---|---|---|
| Each leg on its own | 1076 | 63.6% | 65.1% | 1.54 |
| The double | 538 | 40.7% | 43.5% | 2.30 |

Fitted weights (home, away): const -0.04/+0.05, count for +0.25/+0.31, opp. count against +0.17/+0.20, related for +0.09/+0.01, opp. related against +0.16/+0.29, favourite +0.15/+0.15, one-sided +0.04/+0.02, open game +0.03/+0.02, referee +0.00/+0.00.

## Yellow cards

22544 matches from 2021/22 to 2023/24 fitted the model; it was then run once over 17546 matches from 2024-07-26 to 2026-11-02 in 22 leagues, which it never saw. Each league's line is the .5 nearest its average total in the fitting seasons.

| | Average miss | Log loss on over/under the line |
|---|---|---|
| League average only | 1.68 | 0.6915 |
| Model | 1.63 | 0.6691 |

Lower is better.

### Yellow cards: when the model is confident, how often is it right?

| Model said | Calls | Came in | Price needed to break even |
|---|---|---|---|
| 50%-55% | 6496 | 52.7% | 1.90 |
| 55%-60% | 5087 | 57.6% | 1.73 |
| 60%-65% | 3101 | 62.0% | 1.61 |
| 65%-70% | 1659 | 64.9% | 1.54 |
| 70%-75% | 759 | 72.7% | 1.38 |
| 75%-100% | 444 | 82.2% | 1.22 |

### Yellow cards: the daily double (each day's two most confident calls)

| | Days | Model expected | Came in | Price needed to break even |
|---|---|---|---|---|
| Each leg on its own | 1100 | 69.3% | 70.9% | 1.41 |
| The double | 550 | 48.5% | 50.7% | 1.97 |

Fitted weights (home, away): const +0.07/+0.02, count for +0.29/+0.23, opp. count against +0.34/+0.34, related for +0.39/+0.44, opp. related against +0.33/+0.43, favourite -0.07/-0.08, one-sided +0.07/+0.08, open game -0.02/-0.03, referee +0.50/+0.57.

## Goals over/under 2.5

From the match odds alone, over 17537 test matches: the call came in 56.6% of the time.

| Model said | Calls | Came in | Price needed to break even |
|---|---|---|---|
| 50%-55% | 8410 | 52.1% | 1.92 |
| 55%-60% | 5574 | 58.1% | 1.72 |
| 60%-65% | 2385 | 62.1% | 1.61 |
| 65%-70% | 821 | 67.8% | 1.47 |
| 70%-75% | 255 | 71.0% | 1.41 |
| 75%-100% | 92 | 89.1% | 1.12 |

## Both teams to score

From the match odds alone, over 17537 test matches: the call came in 54.9% of the time.

| Model said | Calls | Came in | Price needed to break even |
|---|---|---|---|
| 50%-55% | 10604 | 52.3% | 1.91 |
| 55%-60% | 5197 | 57.7% | 1.73 |
| 60%-65% | 1510 | 62.3% | 1.60 |
| 65%-70% | 206 | 63.6% | 1.57 |

## Match result picks

The bookmakers' favourite won 50.8% of 17537 test matches; backing it at the average odds returned -4.6%.

