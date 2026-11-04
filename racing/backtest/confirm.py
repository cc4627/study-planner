"""Confirm (or refute) the pre-registered model and rule on months the backtest never saw.

Usage: python confirm.py DATA_DIR [--out CONFIRM.md]

frozen.json holds the model weights and the single rule chosen on 29 Jul - 28 Sep 2026. Nothing is
fitted or chosen here: the frozen rule is run once over the new data, settled at SP, and reported
whole and month by month. Paper points only.
"""
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyse import FIELDS, accuracy, load, mask, model_probs, rows, stats  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    import json
    args = sys.argv[1:]
    out_path = args[args.index('--out') + 1] if '--out' in args else None
    with open(os.path.join(HERE, 'frozen.json'), encoding='utf-8') as f:
        frozen = json.load(f)
    coef = defaultdict(float, frozen['coef'])
    rule = dict(frozen['rule'], field=tuple(frozen['rule']['field']))
    races = load(args[0])
    L = [f'# Confirmation test: {races[0]["date"] if races else "?"} to {races[-1]["date"] if races else "?"}', '',
         f'The rule **{frozen["rule_text"]}** and the model weights were chosen on 29 Jul - 28 Sep 2026 and frozen in '
         f'`frozen.json` before this run. None of these {len(races)} races were used to build or choose them. '
         'Bets settled at SP; paper points only.', '']
    if len(races) < 1000:
        L.append('Not enough races collected to run the confirmation.')
        return finish(L, out_path)

    m_acc = accuracy(races, lambda r: model_probs(r, coef))
    sp_acc = accuracy(races, lambda r: [1 / x['sp'] / sum(1 / y['sp'] for y in r['runners']) for x in r['runners']])
    d = rows(races, coef)
    month = [r['date'][:7] for r in races for _ in r['runners']]
    every = stats(d['ret'][mask(dict(rank='any', kind='all', hcap='all', field=FIELDS[0]), d)])
    top = stats(d['ret'][mask(dict(rank=1, kind='all', hcap='all', field=FIELDS[0]), d)])
    m = mask(rule, d)
    s = stats(d['ret'][m])
    luck = 0.5 * math.erfc(s['t'] / math.sqrt(2))
    L += ['## Model accuracy on the new months', '',
          '| Ranking | Top pick won | Winner in top 3 |', '|---|---|---|',
          f'| Model | {m_acc[1]:.1%} | {m_acc[2]:.1%} |',
          f'| Starting price (reference) | {sp_acc[1]:.1%} | {sp_acc[2]:.1%} |', '',
          '## Betting at SP', '', '| Strategy | Bets | P/L (pts) | ROI | t |', '|---|---|---|---|---|',
          f"| Back every runner (the bookmakers' margin) | {every['n']} | {every['pl']:+.1f} | {every['roi']:+.1%} | |",
          f"| Back the model top pick | {top['n']} | {top['pl']:+.1f} | {top['roi']:+.1%} | {top['t']:.2f} |",
          f"| **{frozen['rule_text']}** | {s['n']} | {s['pl']:+.1f} | {s['roi']:+.1%} | {s['t']:.2f} |", '',
          '### The frozen rule month by month', '', '| Month | Bets | Winners | P/L (pts) | ROI |', '|---|---|---|---|---|']
    mon = [x for x, keep in zip(month, m) if keep]
    rets = d['ret'][m]
    for mo in sorted(set(mon)):
        r = rets[[x == mo for x in mon]]
        L.append(f'| {mo} | {len(r)} | {int((r > -1).sum())} | {r.sum():+.1f} | {r.mean():+.1%} |')
    passed = s['n'] >= 100 and s['roi'] > 0 and s['t'] >= 2
    L += ['', '**Verdict:** ' + (
        f"confirmed on unseen data: {s['n']} bets, ROI {s['roi']:+.1%}, t = {s['t']:.2f} (about a {luck:.1%} chance by luck). "
        'Still paper-track it live before trusting it: past edges can fade.' if passed else
        f"not confirmed. On {s['n']} unseen bets the rule returned {s['roi']:+.1%} (t = {s['t']:.2f}); the October profit "
        'looks like luck rather than an edge.' if s['roi'] <= 0 else
        f"not confirmed. The rule made {s['roi']:+.1%} on {s['n']} unseen bets, but t = {s['t']:.2f} (about a {luck:.0%} "
        'chance by luck) is short of the t >= 2 needed to call it an edge.')]
    return finish(L, out_path)


def finish(lines, out_path):
    text = '\n'.join(lines) + '\n'
    print(text)
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(text)


if __name__ == '__main__':
    main()
