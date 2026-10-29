"""Write today's UK & Irish race picks (time, course, top 3) for the racing page.

Reads Sporting Life's free racecards (no account, read-only) and ranks each race with the model the
backtest chose (racing/backtest/model.json): the model if it beat the betting forecast on the test
month, otherwise the forecast order itself.

Writes racing/picks/YYYY-MM-DD.json and keeps racing/picks/index.json listing the dates available.
"""
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import model  # noqa: E402
import sl  # noqa: E402

LONDON = ZoneInfo('Europe/London')
MODEL = os.path.join(HERE, '..', 'backtest', 'model.json')
KEEP_DAYS = 60


def ranker():
    try:
        with open(MODEL, encoding='utf-8') as f:
            m = json.load(f)
        if m.get('use_model'):
            return lambda r: model.probs(r, m['coef'])
    except (OSError, ValueError):
        pass
    return model.forecast_probs


def main():
    day = datetime.now(LONDON).date()
    rank = ranker()
    races = []
    for _, path in sl.races_on(day, 'racecards'):
        try:
            r = sl.race(path)
        except Exception as e:
            print(f'  ! {path}: {e!r}')
            continue
        if not r or len(r['runners']) < 2:
            continue
        rs = r['runners']
        if any(x.get('fc') for x in rs):
            p = rank(r)
        elif any(x.get('sp') for x in rs):  # no forecast published: fall back to the current prices
            p = [1 / x['sp'] if x.get('sp') else 0 for x in rs]
        else:
            continue
        order = sorted(range(len(rs)), key=lambda i: -p[i])
        races.append({'time': r['time'], 'course': r['course'], 'country': r['country'],
                      'picks': [rs[i]['name'] for i in order[:3]]})

    path = os.path.join(HERE, f'{day}.json')
    if os.path.exists(path):  # a re-run later in the day keeps races it can no longer read
        with open(path, encoding='utf-8') as f:
            seen = {(r['time'], r['course']) for r in races}
            races += [r for r in json.load(f).get('races', []) if (r['time'], r['course']) not in seen]
    if not races:
        print(f'{day}: no races found; nothing written.')
        return
    races.sort(key=lambda r: (r['time'], r['course']))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'date': str(day), 'updated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   'races': races}, f, indent=1, ensure_ascii=False)

    dates = sorted(n[:-5] for n in os.listdir(HERE) if n[:4].isdigit() and n.endswith('.json'))
    for old in dates[:-KEEP_DAYS]:
        os.remove(os.path.join(HERE, old + '.json'))
    with open(os.path.join(HERE, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'dates': dates[-KEEP_DAYS:]}, f)
    print(f'{day}: {len(races)} races')


if __name__ == '__main__':
    main()
