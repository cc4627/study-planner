"""Write UK & Irish race picks (time, course, top 3) for the racing page.

Usage: python build_picks.py

Sporting Life's racecards page shows today's cards only, so this builds today's races still to run.
It runs just after midnight (the day's first picks) and again mid-morning (late changes).

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
    """Write items to a day file, keeping entries from an earlier run today that this run couldn't read (and the
    day's double)."""
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            prev = json.load(f)
        seen = {key(r) for r in items}
        items += [r for r in prev.get('races', []) if key(r) not in seen]
        if prev.get('double'):
            extra = dict(extra, double=prev['double'])
    items.sort(key=lambda r: (r['time'], r['course']))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dict(extra, races=items), f, indent=1, ensure_ascii=False)


def main():
    now = datetime.now(LONDON)
    build(now.date(), now)
    write_index()


def build(day, now):
    rank, rule = ranker(), rule_pick()
    races, track = [], []
    listed = sl.races_on(day, 'racecards')
    unread = off = small = 0
    for _, path in listed:
        try:
            r = sl.race(path)
        except Exception as e:
            print(f'  ! {path}: {e!r}')
            unread += 1
            continue
        if not r or len(r['runners']) < 2:
            unread += not r; small += bool(r)
            continue
        if day < now.date() or (day == now.date() and r['time'] <= now.strftime('%H:%M')):
            off += 1
            continue  # already off: a "prediction" now could see the result, and earlier picks stay as they were
        rs = r['runners']
        if any(x.get('fc') for x in rs):
            p = rank(r)
        elif any(x.get('sp') for x in rs):  # no forecast published: fall back to the current prices
            p = [1 / x['sp'] if x.get('sp') else 0 for x in rs]
        else:
            continue
        order = sorted(range(len(rs)), key=lambda i: -p[i])
        picks = [rs[i]['name'] for i in order[:3]]
        chance = p[order[0]] / sum(p) if sum(p) else None  # the top pick's win chance, for choosing the day's double
        races.append({'time': r['time'], 'course': r['course'], 'country': r['country'], 'picks': picks,
                      'p': round(chance, 3) if chance else None})
        track.append({'time': r['time'], 'course': r['course'], 'path': path, 'picks': picks, 'rule': rule(r)})

    if sl.SEEN_OTHER:
        print(f'{day}: skipped meetings:', '; '.join(sorted(sl.SEEN_OTHER)))
        sl.SEEN_OTHER.clear()
    print(f'{day}: {len(listed)} races listed, {off} already off, {unread} unreadable, {small} with under 2 runners')
    if not races:
        print(f'{day}: no races still to run; nothing written.')
        return
    stamp = {'date': str(day), 'updated': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    key = lambda r: (r['time'], r['course'])
    merge_write(os.path.join(HERE, f'{day}.json'), key, races, stamp)
    set_double(os.path.join(HERE, f'{day}.json'), now)
    os.makedirs(TRACK, exist_ok=True)
    merge_write(os.path.join(TRACK, f'{day}.json'), key, track, stamp)
    print(f'{day}: {len(races)} races')


def set_double(path, now):
    """The day's double: the two top picks with the best win chances, kept as they were once either race is off."""
    with open(path, encoding='utf-8') as f:
        doc = json.load(f)
    clock = now.strftime('%H:%M')
    old = doc.get('double')
    if not (old and any(t <= clock for t, _ in old['legs'])):
        cand = [r for r in doc['races'] if r.get('p') and r['time'] > clock]
        if len(cand) >= 2:
            a, b = sorted(cand, key=lambda r: -r['p'])[:2]
            doc['double'] = {'legs': [[a['time'], a['course']], [b['time'], b['course']]], 'p': round(a['p'] * b['p'], 3)}
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(doc, f, indent=1, ensure_ascii=False)


def write_index():
    dates = sorted(n[:-5] for n in os.listdir(HERE) if n[:4].isdigit() and n.endswith('.json'))
    for old in dates[:-KEEP_DAYS]:
        os.remove(os.path.join(HERE, old + '.json'))
    with open(os.path.join(HERE, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'dates': dates[-KEEP_DAYS:]}, f)


if __name__ == '__main__':
    main()
