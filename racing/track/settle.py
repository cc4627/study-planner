"""Settle the day's paper-tracked picks at SP and update the running totals.

Usage: python settle.py [YYYY-MM-DD]   (default: today, London time)

Reads racing/track/DATE.json (written by the morning picks job), re-reads each race page after racing
for finishing positions and starting prices, appends one row per race to results.csv and rewrites
SUMMARY.md. Paper points only; nothing here places a bet.
"""
import csv
import json
import math
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import sl  # noqa: E402

CSV = os.path.join(HERE, 'results.csv')
COLS = ['date', 'time', 'course', 'winner', 'top1', 'top1_sp', 'top1_ret', 'top3_hit', 'rule', 'rule_sp', 'rule_ret']


def ret(name, runners, winners):
    """(SP, return of a 1pt win bet) for a runner, or ('', '') if it didn't run (void)."""
    x = next((x for x in runners if sl.norm(x['name']) == sl.norm(name)), None) if name else None
    if not x or not x.get('sp'):
        return '', ''
    won = sl.norm(name) in {sl.norm(w) for w in winners}
    return round(x['sp'], 3), round(x['sp'] / len(winners) - 1 if won else -1.0, 3)


def settle(day):
    path = os.path.join(HERE, f'{day}.json')
    if not os.path.exists(path):
        print(f'{day}: nothing tracked')
        return
    with open(path, encoding='utf-8') as f:
        tracked = json.load(f)['races']
    rows = []
    if os.path.exists(CSV):
        with open(CSV, encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
    done = {(r['date'], r['time'], r['course']) for r in rows}
    added = 0
    for t in tracked:
        if (str(day), t['time'], t['course']) in done:
            continue
        try:
            r = sl.race(t['path'])
        except Exception as e:
            print(f"  ! {t['path']}: {e!r}")
            continue
        winners = [x['name'] for x in (r or {}).get('runners', []) if x.get('pos') == 1]
        if not winners:
            continue  # not run yet, abandoned or void
        sp1, r1 = ret(t['picks'][0] if t['picks'] else None, r['runners'], winners)
        spr, rr = ret(t.get('rule'), r['runners'], winners)
        rows.append(dict(date=str(day), time=t['time'], course=t['course'], winner=' / '.join(winners),
                         top1=t['picks'][0] if t['picks'] else '', top1_sp=sp1, top1_ret=r1,
                         top3_hit=int(any(sl.norm(p) in {sl.norm(w) for w in winners} for p in t['picks'][:3])),
                         rule=t.get('rule') or '', rule_sp=spr, rule_ret=rr))
        added += 1
    rows.sort(key=lambda r: (r['date'], r['time'], r['course']))
    with open(CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    summary(rows)
    print(f'{day}: settled {added} races ({len(rows)} in total)')


def line(label, rets):
    n = len(rets)
    if not n:
        return f'| {label} | 0 | | | | |'
    pl, mean = sum(rets), sum(rets) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rets) / (n - 1)) if n > 1 else 0
    t = mean / (sd / math.sqrt(n)) if sd else 0
    return f'| {label} | {n} | {sum(1 for x in rets if x > -1)} | {pl:+.1f} | {mean:+.1%} | {t:.2f} |'


def summary(rows):
    top1 = [float(r['top1_ret']) for r in rows if r['top1_ret'] != '']
    rule = [float(r['rule_ret']) for r in rows if r['rule_ret'] != '']
    hit3 = [int(r['top3_hit']) for r in rows]
    first = rows[0]['date'] if rows else '-'
    text = '\n'.join([
        '# Racing paper-tracking', '',
        f'Every UK & Irish race since {first}, settled at the starting price in paper points (1 pt a bet). '
        'No real bets are placed. Updated each evening by racing/track/settle.py.', '',
        f'- Races settled: {len(rows)}',
        f'- Winner in the page\'s top 3: {sum(hit3)} of {len(hit3)} ({(sum(hit3) / len(hit3) if hit3 else 0):.1%})', '',
        '| Strategy | Bets | Winners | P/L (pts) | ROI | t |', '|---|---|---|---|---|---|',
        line('Back the page\'s top pick in every race', top1),
        line('Frozen rule (back model #3 in handicap hurdles)', rule), '',
        'A strategy needs t >= 2 over a good number of bets before its profit means more than luck.', ''])
    with open(os.path.join(HERE, 'SUMMARY.md'), 'w', encoding='utf-8') as f:
        f.write(text)


if __name__ == '__main__':
    settle(date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(ZoneInfo('Europe/London')).date())
