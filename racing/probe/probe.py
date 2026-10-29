"""One-off: see which public UK/IRE racecard sites answer from GitHub's runners and how their pages are built."""
import json
import re
import sys
import urllib.request
from urllib.parse import urljoin

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
SITES = [
    'https://www.sportinglife.com/racing/racecards',
    'https://www.skysports.com/racing/racecards',
    'https://www.attheraces.com/racecards',
    'https://www.racingpost.com/racecards/',
    'https://www.timeform.com/horse-racing/racecards',
    'https://www.racingtv.com/racecards',
    'https://www.horseracing.net/racecards',
    'https://www.bbc.co.uk/sport/horse-racing',
]


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,*/*', 'Accept-Language': 'en-GB'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.geturl(), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, url, ''
    except Exception as e:
        return str(e)[:80], url, ''


def describe(url, html):
    title = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
    print('  title:', (title.group(1).strip()[:90] if title else '-'))
    print('  bytes:', len(html), '| __NEXT_DATA__:', '__NEXT_DATA__' in html, '| ld+json:', html.count('ld+json'),
          '| "forecast":', len(re.findall('forecast', html, re.I)))
    for m in list(re.finditer(r'forecast', html, re.I))[:2]:
        text = re.sub(r'<[^>]+>', ' ', html[max(0, m.start() - 150):m.start() + 450])
        print('  ctx:', re.sub(r'\s+', ' ', text)[:400])
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if nd:
        try:
            data = json.loads(nd.group(1))
            pp = data.get('props', {}).get('pageProps', {})
            print('  pageProps keys:', list(pp)[:20])
        except Exception as e:
            print('  next data parse error', e)


def race_links(base, html):
    hrefs = re.findall(r'href="([^"#?]+)"', html)
    out = []
    for h in hrefs:
        u = urljoin(base, h)
        if re.search(r'racecard', u, re.I) and re.search(r'\d{3,}', u) and u not in out:
            out.append(u)
    return out


for site in SITES:
    status, final, html = get(site)
    print(f'== {site} -> {status} ({final})')
    if not html:
        continue
    describe(final, html)
    links = race_links(final, html)
    print('  race-like links:', len(links))
    for l in links[:6]:
        print('   ', l)
    if links:
        s2, f2, h2 = get(links[0])
        print(f'  -- first race page {s2} {f2}')
        if h2:
            describe(f2, h2)
    sys.stdout.flush()
