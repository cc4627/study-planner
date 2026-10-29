"""Read UK & Irish race data from Sporting Life's free racecard and results pages.

Every page carries its data as JSON in Next.js's __NEXT_DATA__ script, so nothing is scraped from the
layout. Requests are spaced out (PAUSE) to keep the load on the site light. Read-only: no accounts.
"""
import json
import re
import time
import urllib.error
import urllib.request

BASE = 'https://www.sportinglife.com'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
PAUSE = 0.6
UK_IRE = ('england', 'scotland', 'wales', 'ireland', 'eire', 'great britain', 'united kingdom')
# Every GB & Irish track, as a second check in case a meeting's country label is missing or unexpected.
COURSES = {c.lower() for c in (
    'Aintree Ascot Ayr Bangor-on-Dee Bath Beverley Brighton Carlisle Cartmel Catterick Chelmsford Cheltenham Chepstow '
    'Chester Doncaster Epsom Exeter Fakenham Ffos-Las Fontwell Goodwood Hamilton Haydock Hereford Hexham Huntingdon Kelso '
    'Kempton Leicester Lingfield Ludlow Market-Rasen Musselburgh Newbury Newcastle Newmarket Newton-Abbot Nottingham Perth '
    'Plumpton Pontefract Redcar Ripon Salisbury Sandown Sedgefield Southwell Stratford Taunton Thirsk Uttoxeter Warwick '
    'Wetherby Wincanton Windsor Wolverhampton Worcester Yarmouth York '
    'Ballinrobe Bellewstown Clonmel Cork Curragh Down-Royal Downpatrick Dundalk Fairyhouse Galway Gowran-Park Kilbeggan '
    'Killarney Laytown Leopardstown Limerick Listowel Naas Navan Punchestown Roscommon Sligo Thurles Tipperary Tramore Wexford'
).replace('-', ' ').split()} | {'bangor on dee', 'ffos las', 'market rasen', 'newton abbot', 'down royal', 'gowran park'}
SEEN_OTHER = set()  # country labels skipped, printed by callers so a mislabelled meeting is visible


def is_uk_ire(country, course):
    c = (country or '').lower().strip()
    if c:  # trust the label when there is one (there's a Perth and a Newcastle in Australia too)
        return any(k in c for k in UK_IRE)
    return re.sub(r'\s*\(.*\)$', '', (course or '').lower()).replace('-', ' ').strip() in COURSES
_last = [0.0]


def page(path, with_html=False):
    """pageProps of a Sporting Life page (plus its HTML if asked), or None if it can't be fetched."""
    wait = PAUSE - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        _last[0] = time.time()
        try:
            req = urllib.request.Request(BASE + path, headers={'User-Agent': UA, 'Accept': 'text/html', 'Accept-Language': 'en-GB'})
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode('utf-8', 'replace')
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
            pp = json.loads(m.group(1)).get('props', {}).get('pageProps', {}) if m else None
            return (pp, html) if with_html else pp
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return (None, '') if with_html else None
        except Exception:
            pass
        time.sleep(3 * (attempt + 1))
    return (None, '') if with_html else None


def slugify(s):
    """Sporting Life's URL slugs: punctuation dropped, spaces to hyphens ('bettingsites.co.uk' -> 'bettingsitescouk')."""
    return re.sub(r'[\s-]+', '-', re.sub(r'[^a-z0-9\s-]', '', (s or '').lower())).strip('-')


def races_on(day, kind):
    """[(race_id, path)] for UK & Irish races on a date. kind = 'results' (past) or 'racecards' (today)."""
    pp, html = page(f'/racing/{kind}/{day}' if kind == 'results' else '/racing/racecards', with_html=True)
    if not pp:
        return []
    # Prefer the page's own links; build one from the names only if a race isn't linked.
    links = {int(rid): href for href, rid in re.findall(rf'href="(/racing/{kind}/{day}/[^/"]+(?:/racecard)?/(\d+)/[^"]*)"', html)}
    out = []
    for m in pp.get('meetings') or []:
        ms = m.get('meeting_summary') or {}
        country = ((ms.get('course') or {}).get('country') or {}).get('long_name')
        if ms.get('date') != str(day):
            continue
        if not is_uk_ire(country, (ms.get('course') or {}).get('name')):
            SEEN_OTHER.add(f"{country} ({(ms.get('course') or {}).get('name')})")
            continue
        course_slug = slugify((ms.get('course') or {}).get('name'))
        for r in m.get('races') or []:
            rid = (r.get('race_summary_reference') or {}).get('id')
            if not rid:
                continue
            mid = '/racecard' if kind == 'racecards' else ''
            out.append((rid, links.get(int(rid)) or f'/racing/{kind}/{day}/{course_slug}{mid}/{rid}/{slugify(r.get("name"))}'))
    return out


def obj(x):
    """The dict itself, or the first dict of a list (some page fields come either way), else {}."""
    if isinstance(x, list):
        x = x[0] if x else {}
    return x if isinstance(x, dict) else {}


def dec(odds):
    """Fractional or 'Evs' odds string -> decimal odds, or None."""
    s = str(odds or '').strip().lower()
    if s in ('evs', 'evens', 'ev'):
        return 2.0
    m = re.match(r'^(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)$', s)
    return 1 + float(m.group(1)) / float(m.group(2)) if m and float(m.group(2)) else None


def lbs(w):
    m = re.match(r'^(\d+)-(\d+)$', str(w or ''))
    return int(m.group(1)) * 14 + int(m.group(2)) if m else None


def norm(name):
    return re.sub(r'[^a-z0-9]', '', re.sub(r'\([A-Z]{2,3}\)', '', name or '').lower())


def forecast(text):
    """'Horse A (5/2), Horse B (9/2)' -> {normalised name: decimal odds}."""
    out = {}
    for name, odds in re.findall(r'\s*([^,]+?)\s*\(([^()]+)\)\s*(?:,|$)', text or ''):
        d = dec(odds)
        if d:
            out[norm(name)] = d
    return out


def kind_of(name, surface):
    n = (name or '').lower()
    if 'chase' in n:
        return 'chase'
    if 'hurdle' in n:
        return 'hurdle'
    if 'national hunt flat' in n or 'nh flat' in n or 'bumper' in n or 'inh flat' in n:
        return 'nhf'
    return 'aw' if (surface or '').upper() in ('POLYTRACK', 'TAPETA', 'FIBRESAND', 'ALL_WEATHER', 'AW') else 'flat'


def race(path):
    """Compact record of one race: details, the betting forecast and every runner's pre-race facts and result."""
    pp = page(path)
    if not pp or not pp.get('race'):
        return None
    rc = obj(pp['race'])
    rs = obj(rc.get('race_summary'))
    fc = forecast(rc.get('betting_forecast'))
    runners = []
    for ride in rc.get('rides') or []:
        horse = obj(ride.get('horse'))
        status = ride.get('ride_status') or ''
        if 'NON' in status.upper():
            continue
        name = horse.get('name') or ''
        runners.append({
            'name': name,
            'fc': fc.get(norm(name)),
            'sp': dec(obj(ride.get('betting')).get('current_odds')),
            'pos': ride.get('finish_position'),
            'or': ride.get('official_rating'),
            'wt': lbs(ride.get('handicap')),
            'age': horse.get('age'),
            'days': horse.get('last_ran_days'),
            'form': obj(horse.get('formsummary')).get('display_text') or '',
        })
    meeting = obj(obj(pp.get('meeting')).get('meeting_summary'))
    return {
        'id': obj(rs.get('race_summary_reference')).get('id'),
        'date': rs.get('date'), 'time': (rs.get('time') or '')[:5], 'course': rs.get('course_name'),
        'country': obj(obj(meeting.get('course')).get('country')).get('long_name'),
        'name': rs.get('name'), 'kind': kind_of(rs.get('name'), obj(rs.get('course_surface')).get('surface')),
        'hcap': bool(rs.get('has_handicap')), 'going': rs.get('going'), 'cls': rs.get('race_class'),
        'stage': rs.get('race_stage'), 'runners': runners,
    }
