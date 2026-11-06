"""Champions League, Europa League and Conference League matches from ESPN's free scores feed (no account,
read-only): fixtures, bookmaker odds where ESPN carries them, and results with corners and yellow cards.

football-data.co.uk covers domestic leagues only, so European nights come from here. Teams are matched to
the domestic files' names so the corners and cards models can use each side's league form.
"""
import difflib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = 'https://site.api.espn.com/apis/site/v2/sports/soccer'
UA = {'User-Agent': 'study-planner/1.0 (+https://github.com/cc4627/study-planner)'}
COMPS = {'uefa.champions': ('UCL', 'Champions League'), 'uefa.europa': ('UEL', 'Europa League'),
         'uefa.europa.conf': ('UECL', 'Conference League')}
# ESPN's slug for each football-data league, to fill in fixtures football-data hasn't listed yet.
DOMESTIC = {'E0': 'eng.1', 'E1': 'eng.2', 'E2': 'eng.3', 'E3': 'eng.4', 'EC': 'eng.5', 'SC0': 'sco.1', 'SC1': 'sco.2',
            'SC2': 'sco.3', 'SC3': 'sco.4', 'D1': 'ger.1', 'D2': 'ger.2', 'I1': 'ita.1', 'I2': 'ita.2', 'SP1': 'esp.1',
            'SP2': 'esp.2', 'F1': 'fra.1', 'F2': 'fra.2', 'N1': 'ned.1', 'B1': 'bel.1', 'P1': 'por.1', 'T1': 'tur.1', 'G1': 'gre.1'}
LONDON = ZoneInfo('Europe/London')
PAUSE = 1.0
_last = [0.0]

# ESPN name -> football-data name, where the two differ beyond spelling.
ALIASES = {
    'manchester city': 'Man City', 'manchester united': 'Man United', 'tottenham hotspur': 'Tottenham',
    'newcastle united': 'Newcastle', 'nottingham forest': "Nott'm Forest", 'wolverhampton wanderers': 'Wolves',
    'paris saint-germain': 'Paris SG', 'internazionale': 'Inter', 'inter milan': 'Inter', 'ac milan': 'Milan',
    'atletico madrid': 'Ath Madrid', 'athletic club': 'Ath Bilbao', 'real sociedad': 'Sociedad', 'real betis': 'Betis',
    'celta vigo': 'Celta', 'rayo vallecano': 'Vallecano', 'borussia dortmund': 'Dortmund', 'bayer leverkusen': 'Leverkusen',
    'eintracht frankfurt': 'Ein Frankfurt', 'borussia monchengladbach': "M'gladbach", 'rb leipzig': 'RB Leipzig',
    'vfb stuttgart': 'Stuttgart', 'sc freiburg': 'Freiburg', 'tsg hoffenheim': 'Hoffenheim', 'fc porto': 'Porto',
    'sporting cp': 'Sp Lisbon', 'sporting': 'Sp Lisbon', 'sl benfica': 'Benfica', 'sc braga': 'Sp Braga', 'braga': 'Sp Braga',
    'psv eindhoven': 'PSV Eindhoven', 'feyenoord rotterdam': 'Feyenoord', 'az alkmaar': 'AZ Alkmaar',
    'olympiacos': 'Olympiakos', 'paok salonika': 'PAOK', 'panathinaikos': 'Panathinaikos', 'aek athens': 'AEK',
    'union st.-gilloise': 'St. Gilloise', 'union saint-gilloise': 'St. Gilloise', 'club brugge': 'Club Brugge',
    'olympique lyonnais': 'Lyon', 'lyon': 'Lyon', 'olympique de marseille': 'Marseille', 'as monaco': 'Monaco',
    'lille osc': 'Lille', 'ogc nice': 'Nice', 'stade rennais': 'Rennes', 'rangers': 'Rangers', 'celtic': 'Celtic',
    'fenerbahce': 'Fenerbahce', 'besiktas': 'Besiktas', 'galatasaray': 'Galatasaray', 'as roma': 'Roma', 'ss lazio': 'Lazio',
    'queens park rangers': 'QPR', 'sheffield wednesday': 'Sheffield Weds', 'west bromwich albion': 'West Brom',
    'brighton & hove albion': 'Brighton', 'west ham united': 'West Ham', 'fc cologne': 'FC Koln', 'cologne': 'FC Koln',
    'hamburg sv': 'Hamburg', "queen's park": 'Queens Park', 'fortuna sittard': 'For Sittard',
}


def _get(url):
    wait = PAUSE - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
        except Exception:
            pass
        time.sleep(3 * (attempt + 1))
    return None


def _decimal(ml):
    """American odds (+150 / -120 / EVEN) -> decimal (2.5 / 1.83 / 2.0)."""
    if isinstance(ml, str) and ml.strip().upper() in ('EVEN', 'EV', 'EVS'):
        return 2.0
    try:
        v = float(str(ml).replace('+', '').strip())
    except (TypeError, ValueError):
        return None
    if v >= 100:
        return round(1 + v / 100, 3)
    if v <= -100:
        return round(1 + 100 / -v, 3)
    return None


def _price(node):
    """The closing (else opening) price from ESPN's newer {'close': {'odds': ..}, 'open': {..}} layout."""
    node = node or {}
    for when in ('close', 'current', 'open'):
        v = (node.get(when) or {}).get('odds')
        if v not in (None, ''):
            return v
    return node.get('odds')


def _line(node):
    for when in ('close', 'current', 'open'):
        v = (node or {}).get(when) or {}
        if v.get('line') not in (None, ''):
            try:
                return float(str(v['line']).lstrip('ouOU'))
            except ValueError:
                return None
    return None


def _stat(team, *names):
    for x in team.get('statistics') or []:
        if x.get('name') in names:
            try:
                return float(x.get('displayValue') if x.get('displayValue') not in (None, '') else x.get('value'))
            except (TypeError, ValueError):
                return None
    return None


def _odds(comp):
    """Decimal 1X2 and over/under 2.5 prices from the first odds provider ESPN lists, in either of its layouts."""
    out = {}
    odds = comp.get('odds')
    for o in (odds if isinstance(odds, list) else [odds]):
        if not isinstance(o, dict):
            continue  # ESPN sometimes lists an empty slot
        ml = o.get('moneyline') or {}
        out['oh'] = _decimal((o.get('homeTeamOdds') or {}).get('moneyLine')) or _decimal(_price(ml.get('home')))
        out['oa'] = _decimal((o.get('awayTeamOdds') or {}).get('moneyLine')) or _decimal(_price(ml.get('away')))
        out['od'] = _decimal((o.get('drawOdds') or {}).get('moneyLine')) or _decimal(_price(ml.get('draw')))
        tot = o.get('total') or {}
        line = o.get('overUnder')
        if line in (None, ''):
            line = _line(tot.get('over'))
        try:
            line = float(line)
        except (TypeError, ValueError):
            line = None
        if line == 2.5:
            out['over'] = _decimal(o.get('overOdds')) or _decimal(_price(tot.get('over')))
            out['under'] = _decimal(o.get('underOdds')) or _decimal(_price(tot.get('under')))
        if not out.get('oh'):  # log the layout once, so a change on ESPN's side shows in the job output
            if not getattr(_odds, 'logged', False):
                _odds.logged = True
                slim = {k: v for k, v in o.items() if k not in ('link', 'links', 'provider')}
                print('  ESPN odds layout:', json.dumps(slim, default=str)[:1500])
        break
    return out


def matches(day, comps=None, cards=True):
    """Every match on a UK date in the given competitions ({slug: (code, name)}, the European ones by default), in
    the same shape as fd.row(), plus state and ESPN's team names. cards=False skips the match reports that
    played matches need for their yellow cards."""
    out = []
    for slug, (code, name) in (COMPS if comps is None else comps).items():
        j = _get(f'{BASE}/{slug}/scoreboard?dates={day:%Y%m%d}') or {}
        for e in j.get('events', []):
            try:
                m = _match(slug, code, name, e, day, cards)
            except Exception as err:  # one odd event shouldn't lose the night
                print(f'  ! {slug} {e.get("id")}: {err!r}')
                continue
            if m:
                out.append(m)
    return out


def _match(slug, code, name, e, day, cards=True):
    """One ESPN event as a match dict, or None if it isn't a complete fixture on this UK date."""
    comp = (e.get('competitions') or [{}])[0]
    teams = {t.get('homeAway'): t for t in comp.get('competitors') or []}
    if 'home' not in teams or 'away' not in teams or not e.get('date'):
        return None
    ko = datetime.strptime(e['date'].replace('Z', '+0000'), '%Y-%m-%dT%H:%M%z').astimezone(LONDON)
    if ko.date() != day:
        return None
    st = ((comp.get('status') or e.get('status') or {}).get('type') or {})
    h, a = teams['home'], teams['away']
    post = st.get('state') == 'post' and st.get('completed')
    num = lambda x: float(x) if x not in (None, '') else None
    m = {'div': code, 'league': name, 'date': day, 'time': ko.strftime('%H:%M'), 'state': st.get('state'),
         'home': (h.get('team') or {}).get('displayName') or '', 'away': (a.get('team') or {}).get('displayName') or '',
         'hg': num(h.get('score')) if post else None, 'ag': num(a.get('score')) if post else None,
         'hc': _stat(h, 'wonCorners', 'cornerKicks') if post else None, 'ac': _stat(a, 'wonCorners', 'cornerKicks') if post else None,
         'hy': _stat(h, 'yellowCards') if post else None, 'ay': _stat(a, 'yellowCards') if post else None,
         'hs': None, 'as': None, 'hf': None, 'af': None, 'ref': None,
         'oh': None, 'od': None, 'oa': None, 'over': None, 'under': None}
    m.update({k: v for k, v in _odds(comp).items() if v})
    if cards and post and (m['hy'] is None or m['ay'] is None) and e.get('id'):
        m['hy'], m['ay'] = _yellows(slug, e['id'], m['home'], m['away'])
    return m if m['home'] and m['away'] else None


def _yellows(slug, event_id, home, away):
    """Yellow cards per side from the match report (the scoreboard doesn't carry them)."""
    s = _get(f'{BASE}/{slug}/summary?event={event_id}') or {}
    got = {}
    for t in (s.get('boxscore') or {}).get('teams') or []:
        got[(t.get('team') or {}).get('displayName')] = _stat(t, 'yellowCards')
    return got.get(home), got.get(away)


def _norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return ' '.join(w for w in s.split() if w not in ('fc', 'cf', 'afc', 'sc', 'ac', 'club', 'de', 'the', 'fk', 'sk'))


def to_fd(name, known):
    """The football-data name for an ESPN team name, or None when the team isn't in the domestic files."""
    key = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower().strip()
    if key in ALIASES and ALIASES[key] in known:
        return ALIASES[key]
    by_norm = {_norm(k): k for k in known}
    n = _norm(name)
    if n in by_norm:
        return by_norm[n]
    for kn, k in by_norm.items():
        if kn and (kn in n.split() or n in kn.split() or (len(kn) > 4 and (kn in n or n in kn))):
            return k
    close = difflib.get_close_matches(n, list(by_norm), n=1, cutoff=0.82)
    return by_norm[close[0]] if close else None
