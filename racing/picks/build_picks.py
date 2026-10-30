"""Write today's UK & Irish race picks (time, course, top 3) for the racing page.

Reads Sporting Life's free racecards (no account, read-only) and ranks each race with the model the
backtest chose (racing/backtest/model.json): the model if it beat the betting forecast on the test
month, otherwise the forecast order itself.

Writes racing/picks/YYYY-MM-DD.json and keeps racing/picks/index.json listing the dates available.
Also writes racing/track/YYYY-MM-DD.json for the paper-tracking: each race's page link, its top 3 and,
where the race qualifies, the frozen backtest rule's selection (racing/backtest/frozen.json). The
evening job (racing/track/settle.py) settles those at SP. Paper points only; no bets are placed.
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
FROZEN = os.path.join(HERE, '..', 'backtest', 'frozen.json')
TRACK = os.path.join(HERE, '..', 'track')
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


def rule_pick():
    """Return f(race) -> the frozen rule's selection (a runner name) or None if the race doesn't qualify."""
    try:
        with open(FROZEN, encoding='utf-8') as f:
            fz = json.load(f)
    except (OSError, ValueError):
        return lambda r: None
    rule, coef = fz['rule'], fz['coef']

    def pick(r):
        rs = r['runners']
        if rule['kind'] != 'all' and r['kind'] != rule['kind']:
            return None
        if rule['hcap'] != 'all' and bool(r['hcap']) != (rule['hcap'] == 'hcap'):
            return None
        if not rule['field'][1] <= len(rs) <= rule['field'][2] or len(rs) < rule['rank']:
            return None
        p = model.probs(r, coef)
        return rs[sorted(range(len(rs)), key=lambda i: -p[i])[rule['rank'] - 1]]['name']
    return pick


def merge_write(path, key, items, extra):
    """Write items to a day file, keeping entries from an earlier run today that this run couldn't read."""
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            seen = {key(r) for r in items}
            items += [r for r in json.load(f).get('races', []) if key(r) not in seen]
    items.sort(key=lambda r: (r['time'], r['course']))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dict(extra, races=items), f, indent=1, ensure_ascii=False)


def main():
    day = datetime.now(LONDON).date()
    rank, rule = ranker(), rule_pick()
    races, track = [], []
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
        picks = [rs[i]['name'] for i in order[:3]]
        races.append({'time': r['time'], 'course': r['course'], 'country': r['country'], 'picks': picks})
        track.append({'time': r['time'], 'course': r['course'], 'path': path, 'picks': picks, 'rule': rule(r)})

    if not races:
        print(f'{day}: no races found; nothing written.')
        return
    stamp = {'date': str(day), 'updated': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    key = lambda r: (r['time'], r['course'])
    merge_write(os.path.join(HERE, f'{day}.json'), key, races, stamp)
    os.makedirs(TRACK, exist_ok=True)
    merge_write(os.path.join(TRACK, f'{day}.json'), key, track, stamp)

    dates = sorted(n[:-5] for n in os.listdir(HERE) if n[:4].isdigit() and n.endswith('.json'))
    for old in dates[:-KEEP_DAYS]:
        os.remove(os.path.join(HERE, old + '.json'))
    with open(os.path.join(HERE, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'dates': dates[-KEEP_DAYS:]}, f)
    print(f'{day}: {len(races)} races')


if __name__ == '__main__':
    main()
