"""Bookmaker odds for tennis matches from tennisexplorer.com (free, no account, read-only; its robots.txt allows
these pages). The day's match and result lists carry each match's two win prices; a match's own page carries
the over/under prices for each total-games line, averaged over the bookmakers it lists.
Requests are spaced out to keep the load light.
"""
import html
import re
import time
import unicodedata
import urllib.error
import urllib.request

BASE = 'https://www.tennisexplorer.com'
UA = {'User-Agent': 'study-planner/1.0 (+https://github.com/cc4627/study-planner)'}
PAUSE = 1.5
_last = [0.0]


def _get(path):
    wait = PAUSE - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(2):
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + path, headers=UA), timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410, 429):
                return None  # refused or gone: don't push
        except Exception:
            pass
        time.sleep(3)
    return None


def _num(s):
    try:
        v = float(s)
        return v if v > 1 else None
    except (TypeError, ValueError):
        return None


def list_path(day, kind, typ='all'):
    return f'/{kind}/?type={typ}&year={day.year}&month={day.month:02d}&day={day.day:02d}'


def day_list(day, kind, typ='all'):
    """Matches on tennisexplorer's 'matches' (kind='matches') or 'results' list for a date:
    [{'p1': 'Paul T.', 'p2': 'Halys Q.', 'o1': 1.30, 'o2': 3.50, 'id': '3370211'}]."""
    page = _get(list_path(day, kind, typ))
    return parse_list(page) if page else []


def parse_list(page):
    """The singles rows of a match or results list page, as day_list() returns them."""
    rows = {}
    for rid, b, body in re.findall(r'<tr id="r(\d+)(b?)"[^>]*>(.*?)</tr>', page, re.S):
        rows.setdefault(rid, {})['b' if b else 'a'] = body
    out = []
    for r in rows.values():
        if 'a' not in r or 'b' not in r:
            continue
        name = lambda body: (re.search(r'class="t-name"><a [^>]*>([^<]+)</a>', body) or [None, None])[1]
        n1, n2 = name(r['a']), name(r['b'])
        odds = re.findall(r'<td class="course\w*"[^>]*>([\d.]+)</td>', r['a'])
        mid = re.search(r'/match-detail/\?id=(\d+)', r['a'])
        if n1 and n2 and '/' not in n1 + n2:  # singles only
            out.append({'p1': html.unescape(n1), 'p2': html.unescape(n2), 'o1': _num(odds[0]) if len(odds) == 2 else None,
                        'o2': _num(odds[1]) if len(odds) == 2 else None, 'id': mid.group(1) if mid else None})
    return out


def games_prices(match_id):
    """{line: (average over price, average under price)} for each total-games line on a match's page."""
    page = _get(f'/match-detail/?id={match_id}')
    if not page:
        return {}
    out = {}
    for sec in page.split('<tr class="odds-type">')[1:]:
        head = re.search(r'Over/Under ([\d.]+) games', sec[:200])
        avg = re.search(r'<tr class="average">.*?<td class="value">([\d.]+)</td>\s*<td class="k1"><div class="odds-in">([\d.]+)</div>'
                        r'</td>\s*<td class="k2"><div class="odds-in">([\d.]+)</div>', sec, re.S)
        if head and avg and avg.group(1) == head.group(1):
            o, u = _num(avg.group(2)), _num(avg.group(3))
            if o and u:
                out[float(head.group(1))] = (o, u)
    return out


def _plain(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z ]', ' ', s.replace('-', ' ')).split()


def same_player(full, short):
    """Does ESPN's 'Tommy Paul' / 'Wang Xinyu' match tennisexplorer's 'Paul T.' / 'Wang X.'?"""
    toks = _plain(full)
    m = re.match(r'^(.*?)\s+([A-Za-z])\w*\.?$', (short or '').strip())
    if not m or not toks:
        return False
    sur, ini = ''.join(_plain(m.group(1))), m.group(2).lower()
    for i in range(len(toks)):
        for j in range(i + 1, len(toks) + 1):
            if ''.join(toks[i:j]) == sur:
                rest = toks[:i] + toks[j:]
                return any(t[0] == ini for t in rest) if rest else True
    return False


def find(entry, listing):
    """The listing row for a picks entry (either player order), as (row, swapped) or (None, False)."""
    for row in listing:
        if same_player(entry['p1'], row['p1']) and same_player(entry['p2'], row['p2']):
            return row, False
        if same_player(entry['p1'], row['p2']) and same_player(entry['p2'], row['p1']):
            return row, True
    return None, False
