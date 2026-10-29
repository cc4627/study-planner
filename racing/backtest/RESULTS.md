# Racing backtest: 2026-07-29 to 2026-10-28

UK & Irish races from Sporting Life results pages. Runners are ranked using only what was published before the race (betting forecast, official rating, weight, age, form, days since last run); every bet is settled at the starting price. Paper points only.

Training: 1800 races before 2026-09-29. Test: 884 races from 2026-09-29, used once.

## 1. Who wins: accuracy on the test month

| Ranking | Log loss (lower is better) | Top pick won | Winner in top 3 |
|---|---|---|---|
| Betting forecast | 1.7394 | 37.7% | 71.9% |
| Model (forecast + form, ratings, fitness) | 1.7438 | 35.7% | 70.2% |
| Starting price (known only at the off, for reference) | 1.7394 | 37.7% | 71.9% |

The model does not beat the forecast out of sample, so the daily top 3 use the forecast order.

Model weights: lfc +1.08, fc_missing +0.00, or_rel +0.13, or_rel_h +0.22, or_missing -0.06, wt_rel -0.04, wt_rel_h -0.21, form_last +0.17, form_avg -0.40, form_missing -0.34, nf_last +0.03, d_short +0.10, d_mid +0.01, d_long +0.30, d_vlong +0.00, debut +0.04, age_young +0.07, age_old -0.05

## 2. Betting at SP: simple strategies

| Strategy | Train bets | Train ROI | Test bets | Test P/L | Test ROI |
|---|---|---|---|---|---|
| Back the forecast favourite | 1800 | -6.7% | 884 | +0.2 | +0.0% |
| Back the model top pick | 1800 | -13.0% | 884 | -65.2 | -7.4% |

## 3. Searching for an edge: best of 292 rules on training, then tested

| Rule | Train bets | Train ROI | Train t | Test bets | Test ROI | Test t |
|---|---|---|---|---|---|---|
| back model #2, flat, field 13+ | 167 | +18.0% | 1.03 | 88 | -45.9% | -2.75 |
| back forecast #2, flat, forecast price 6-12 | 155 | +14.2% | 0.70 | 76 | +17.1% | 0.60 |
| back forecast #2, flat, field 13+ | 167 | +11.6% | 0.68 | 88 | -37.6% | -2.02 |
| back model #2, field 13+ | 191 | +11.0% | 0.69 | 115 | -36.0% | -2.27 |
| back model #1 where model chance x forecast odds >= 1.0 | 246 | +10.9% | 1.18 | 124 | -5.2% | -0.43 |
| back model #2, hcap, field 13+ | 151 | +10.5% | 0.57 | 100 | -33.7% | -1.91 |
| back model #1 where model chance x forecast odds >= 1.0, flat | 177 | +8.9% | 0.80 | 52 | -3.7% | -0.19 |
| back forecast #3, non-hcap, forecast price 6-12 | 247 | +7.9% | 0.46 | 125 | -2.4% | -0.11 |
| back any runner where model chance x forecast odds >= 1.0 | 613 | +7.3% | 0.78 | 376 | -37.3% | -4.07 |
| back model #2, flat, forecast price 6-12 | 173 | +5.8% | 0.30 | 85 | -11.8% | -0.49 |

**Chosen on training: back model #2, flat, field 13+**

- Training: 167 bets, +30.1 pts, ROI +18.0% (t = 1.03)
- Test, run once: 88 bets, -40.4 pts, ROI -45.9% (t = -2.75)

**Verdict:** no reliable edge. The training profit came from picking the best of many rules and did not hold up on unseen races (a pass needs a positive test ROI with t >= 2 over at least 50 bets).

Only the chosen rule counts as the test. The other rows show how training winners usually fade on new races.
