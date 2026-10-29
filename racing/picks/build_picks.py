"""Write today's UK & Irish race picks (time, course, top 3) for the racing page.

Read-only: it calls only Betfair's login, listMarketCatalogue and listMarketBook. There is no code
here that places, changes or cancels a bet, and the account needs no funds for any of these calls.

Picks are the three shortest-priced runners on the Betfair Exchange win market when the job runs
(mid-morning), the same "morning price" ranking the backtest in racing/backtest scores.

Env: BETFAIR_APP_KEY, BETFAIR_USERNAME, BETFAIR_PASSWORD (GitHub secrets). Missing secrets = no-op.
Writes racing/picks/YYYY-MM-DD.json and keeps racing/picks/index.json listing the dates available.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LONDON = ZoneInfo('Europe/London')
HERE = os.path.dirname(os.path.abspath(__file__))
LOGIN = 'https://identitysso.betfair.com/api/login'
API = 'https://api.betfair.com/exchange/betting/rest/v1.0/'
KEEP_DAYS = 60


def post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def login(app_key, user, password):
    res = post(LOGIN, urllib.parse.urlencode({'username': user, 'password': password}).encode(),
               {'X-Application': app_key, 'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded'})
    if res.get('status') != 'SUCCESS':
        sys.exit(f"Betfair login failed: {res.get('error') or res.get('status')}")
    return res['token']


def call(method, body, app_key, token):
    return post(API + method + '/', json.dumps(body).encode(),
                {'X-Application': app_key, 'X-Authentication': token,
                 'Content-Type': 'application/json', 'Accept': 'application/json'})


def price(runner):
    """Best guess at the current price: mid of best back/lay, else last traded, else best back."""
    ex = runner.get('ex') or {}
    back = (ex.get('availableToBack') or [{}])[0].get('price')
    lay = (ex.get('availableToLay') or [{}])[0].get('price')
    if back and lay and lay <= back * 1.25:
        return (back + lay) / 2
    return runner.get('lastPriceTraded') or back or lay


def build(app_key, token, day):
    start = datetime.combine(day, datetime.min.time(), LONDON)
    cat = call('listMarketCatalogue', {
        'filter': {'eventTypeIds': ['7'], 'marketCountries': ['GB', 'IE'], 'marketTypeCodes': ['WIN'],
                   'marketStartTime': {'from': start.astimezone(timezone.utc).isoformat(),
                                       'to': (start + timedelta(days=1)).astimezone(timezone.utc).isoformat()}},
        'marketProjection': ['EVENT', 'MARKET_START_TIME', 'RUNNER_DESCRIPTION'],
        'sort': 'FIRST_TO_START', 'maxResults': '1000'}, app_key, token)
    books = {}
    ids = [m['marketId'] for m in cat]
    for i in range(0, len(ids), 25):  # EX_BEST_OFFERS costs 5 of the 200-point request limit per market
        for b in call('listMarketBook', {'marketIds': ids[i:i + 25],
                                         'priceProjection': {'priceData': ['EX_BEST_OFFERS']}}, app_key, token):
            books[b['marketId']] = b
    races = []
    for m in cat:
        book = books.get(m['marketId'])
        if not book:
            continue
        names = {r['selectionId']: r['runnerName'] for r in m.get('runners', [])}
        priced = [(price(r), names.get(r['selectionId'])) for r in book.get('runners', [])
                  if r.get('status') == 'ACTIVE' and names.get(r['selectionId'])]
        priced = sorted((p, n) for p, n in priced if p)
        if len(priced) < 2:
            continue
        ev = m.get('event') or {}
        off = datetime.fromisoformat(m['marketStartTime'].replace('Z', '+00:00')).astimezone(LONDON)
        races.append({'time': off.strftime('%H:%M'), 'course': ev.get('venue') or ev.get('name', ''),
                      'country': ev.get('countryCode', ''), 'picks': [n for _, n in priced[:3]]})
    return races


def main():
    keys = [os.environ.get(k, '').strip() for k in ('BETFAIR_APP_KEY', 'BETFAIR_USERNAME', 'BETFAIR_PASSWORD')]
    if not all(keys):
        print('Betfair secrets not set; nothing to do.')
        return
    app_key, user, password = keys
    day = datetime.now(LONDON).date()
    races = build(app_key, login(app_key, user, password), day)

    path = os.path.join(HERE, f'{day}.json')
    if os.path.exists(path):  # a re-run later in the day keeps races whose markets have since closed
        with open(path, encoding='utf-8') as f:
            seen = {(r['time'], r['course']) for r in races}
            races += [r for r in json.load(f).get('races', []) if (r['time'], r['course']) not in seen]
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
