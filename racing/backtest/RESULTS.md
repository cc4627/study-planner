# Racing backtest: 2026-07-29 to 2026-10-28

UK & Irish races from Sporting Life results pages. Runners are ranked using only facts known before the race (official rating, weight, age, form figures, days since last run); every bet is settled at the starting price (SP). Paper points only.

The morning betting forecast is not used: once a race has run, Sporting Life replaces it with the SPs, so on past races it would be looking at the result. The forecast-based daily picks can only be checked going forward.

Training: 2327 races before 2026-09-29. Test: 1183 races from 2026-09-29, used once.

## 1. Who wins: accuracy on the test month

| Ranking | Log loss (lower is better) | Top pick won | Winner in top 3 |
|---|---|---|---|
| Random pick | 2.1843 | 11.6% | 33.6% |
| Model (rating, weight, age, form, days off) | 2.0738 | 23.5% | 53.8% |
| Starting price (known only at the off, for reference) | 1.7691 | 35.8% | 70.4% |

Model weights: or_rel +0.83, or_rel_h -0.31, or_missing -0.46, wt_rel +0.12, wt_rel_h -0.36, form_last +0.52, form_avg +1.69, form_missing +0.29, nf_last +0.08, d_short +0.33, d_mid -0.09, d_long +0.05, d_vlong -0.31, debut -0.25, age_young +0.03, age_old -0.31

## 2. Betting at SP: simple strategies

| Strategy | Train bets | Train ROI | Test bets | Test P/L | Test ROI |
|---|---|---|---|---|---|
| Back every runner (the bookmakers' margin) | 22176 | -27.4% | 11326 | -3049.0 | -26.9% |
| Back the model top pick | 2327 | -17.6% | 1183 | -237.5 | -20.1% |

## 3. Searching for an edge: best of 130 rules on training, then tested

| Rule | Train bets | Train ROI | Train t | Test bets | Test ROI | Test t |
|---|---|---|---|---|---|---|
| back model #3, hurdle, hcap | 179 | +26.0% | 1.10 | 145 | +47.0% | 1.38 |
| back every runner, aw, hcap, field <=7 | 214 | +24.5% | 0.80 | 50 | +6.4% | 0.14 |
| back every runner, hurdle, non-hcap, field 8-12 | 408 | +22.0% | 0.46 | 487 | -34.0% | -2.35 |
| back model #1, aw | 204 | +18.8% | 1.12 | 118 | -11.3% | -0.64 |
| back every runner, aw, field <=7 | 317 | +12.4% | 0.52 | 75 | -15.5% | -0.47 |
| back model #3, hurdle | 293 | +10.9% | 0.57 | 260 | +16.8% | 0.70 |
| back model #2, flat, hcap, field <=7 | 316 | +9.3% | 0.68 | 57 | +12.2% | 0.30 |
| back model #3, hcap, field <=7 | 455 | +8.7% | 0.69 | 189 | -9.9% | -0.70 |
| back model #2, hcap, field <=7 | 455 | +8.2% | 0.63 | 189 | -11.6% | -0.69 |
| back model #1, non-hcap, field <=7 | 306 | +0.7% | 0.07 | 181 | -17.0% | -1.50 |

**Chosen on training: back model #3, hurdle, hcap**

- Training: 179 bets, +46.5 pts, ROI +26.0% (t = 1.10)
- Test, run once: 145 bets, +68.1 pts, ROI +47.0% (t = 1.38)

**Verdict:** no proven edge yet. The rule also made a profit on the test month, but over 145 bets that is not enough to tell skill from luck (t = 1.38: about a 8% chance of doing this well by luck with no edge at all). A pass needs t >= 2 over at least 50 bets.

Only the chosen rule counts as the test. The other rows show how training winners usually fade on new races.
