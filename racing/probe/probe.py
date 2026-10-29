"""One-off: map the structure of Racing Post's free racecard and results pages from GitHub's runners."""
import re
import sys
import time
import urllib.request
from collections import Counter
from urllib.parse import urljoin

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
RP = 'https://www.racingpost.com'


def get(url):
    time.sleep(2)
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,*/*', 'Accept-Language': 'en-GB'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.geturl(), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, url, ''
    except Exception as e:
        return str(e)[:80], url, ''


def structure(html):
    print('  bytes', len(html), '| scripts with JSON:', len(re.findall(r'<script[^>]*type="application/(?:ld\+)?json"', html)),
          '| window.PRELOADED:', 'PRELOADED' in html, '| __NEXT_DATA__:', '__NEXT_DATA__' in html)
    sel = Counter(re.findall(r'data-test-selector="([^"]+)"', html))
    print('  data-test-selector:', ', '.join(f'{k}×{v}' for k, v in sel.most_common(70)))
    cls = Counter(c for cl in re.findall(r'class="([^"]+)"', html) for c in cl.split()
                  if re.match(r'(rp-|RC-|rc-|ui-)', c))
    print('  classes:', ', '.join(f'{k}×{v}' for k, v in cls.most_common(70)))
    ends = Counter(re.findall(r'data-ending="([^"]+)"', html))
    print('  data-ending:', dict(ends))


def show(html, marker, n=2, width=700):
    for m in list(re.finditer(re.escape(marker), html))[:n]:
        frag = html[m.start():m.start() + width]
        frag = re.sub(r'\s+', ' ', frag)
        print(f'  [{marker}] {frag}')


def links(base, html, pattern):
    out = []
    for h in re.findall(r'href="([^"#?]+)"', html):
        u = urljoin(base, h)
        if re.search(pattern, u) and u not in out:
            out.append(u)
    return out


s, f, h = get(RP + '/racecards/')
print('== racecards index', s, f)
if h:
    structure(h)
    rl = links(f, h, r'/racecards/\d+/[^/]+/\d{4}-\d{2}-\d{2}/\d+')
    print('  race links', len(rl), rl[:5])
    if rl:
        s, f, h = get(rl[0])
        print('== racecard', s, f)
        if h:
            structure(h)
            for mk in ['RC-runnerRow', 'RC-cardPage-runnerName', 'bettingForecast', 'Betting Forecast', 'RC-cardPage-runnerOr', 'RC-cardPage-runnerRpr', 'RC-header__raceInstanceTitle', 'RC-courseHeader']:
                show(h, mk, 1)

s, f, h = get(RP + '/results/2026-10-28')
print('== results day', s, f)
if h:
    structure(h)
    rl = links(f, h, r'/results/\d+/[^/]+/\d{4}-\d{2}-\d{2}/\d+')
    print('  result links', len(rl), rl[:5])
    if rl:
        s, f, h = get(rl[0])
        print('== result race', s, f)
        if h:
            structure(h)
            for mk in ['rp-horseTable__mainRow', 'rp-horseTable__pos__number', 'rp-horseTable__horse__price', 'data-ending="OR"', 'rp-raceTimeCourseName', 'rp-raceInfo']:
                show(h, mk, 1)
sys.stdout.flush()
