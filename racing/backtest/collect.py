"""Collect UK & Irish results (forecast, pre-race facts, finishing positions, SPs) from Sporting Life.

Usage: python collect.py START END OUT.jsonl.gz   (dates YYYY-MM-DD, inclusive)
One JSON line per race. The data stays in the GitHub Actions cache; it isn't committed to the repo.
"""
import gzip
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import sl  # noqa: E402

sl.PAUSE = 1.0  # one request a second for the bulk download


def main():
    start, end = (date.fromisoformat(a) for a in sys.argv[1:3])
    out = sys.argv[3]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    got = missed = 0
    with gzip.open(out, 'wt', encoding='utf-8') as f:
        d = start
        while d <= end:
            listed = sl.races_on(d, 'results')
            day_got = 0
            for _, path in listed:
                r = sl.race(path)
                if r and r['runners']:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
                    day_got += 1
                else:
                    missed += 1
                if got + day_got == 0 and missed >= 10:
                    sys.exit('Nothing could be read from Sporting Life (first 10 races failed); stopping.')
            got += day_got
            print(f'{d}: {day_got}/{len(listed)} races', flush=True)
            d += timedelta(days=1)
    print(f'done: {got} races, {missed} unreadable')


if __name__ == '__main__':
    main()
