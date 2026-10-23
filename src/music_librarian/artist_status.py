"""Assess current Qobuz artists from public Wikipedia musical-artist profiles.

Artist-name lookups are authorized by the user. Credentials, library files and
personal notes are never sent. Compact page fields and HTTP validators stay local.
"""
import argparse
import datetime as dt
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from .qobuz_auth import atomic_json

SEEDS = Path(__file__).with_name('release_exclusions.json')
CACHE_DAYS = 6  # Each weekly run refreshes, even if it starts earlier this Friday.
USER_AGENT = 'MusicLibrarian/0.1 (personal music metadata reader)'


def normalized(name):
    name = re.sub(r'\s*\((?:band|musician|rapper|singer|group|duo)\)$', '', name, flags=re.I)
    name = unicodedata.normalize('NFKD', name.strip().casefold()).replace('&', 'and')
    return re.sub(r'[^a-z0-9]', '', re.sub(r'^the\s+', '', name))


class ArtistPage(HTMLParser):
    """Read visible infobox cells; ignore scripts, styles and footnote citations."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.heading, self.title = {}, '', ''
        self.canonical = None
        self.table_depth, self.infobox_depth = 0, None
        self.done, self.cell = False, None
        self.parts, self.row = [], []
        self.skip, self.heading_tag = 0, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and attrs.get('rel') == 'canonical':
            url = attrs.get('href','')
            if url.startswith('https://en.wikipedia.org/wiki/'):
                self.canonical = url
        if tag in ('script','style','sup'):
            self.skip += 1
        if tag in ('h1','title'):
            self.heading_tag = tag
        if tag == 'table':
            self.table_depth += 1
            if self.infobox_depth is None and not self.done and 'infobox' in attrs.get('class','').split():
                self.infobox_depth = self.table_depth
        if self.infobox_depth is None or self.infobox_depth != self.table_depth:
            return
        if tag == 'tr':
            self.row = []
        elif tag in ('td','th'):
            self.cell, self.parts = tag, []
        elif tag in ('br','li','div') and self.cell:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script','style','sup'):
            self.skip = max(0, self.skip-1)
        if tag == self.heading_tag:
            self.heading_tag = None
        if self.infobox_depth is not None and self.infobox_depth == self.table_depth:
            if tag in ('td','th') and self.cell:
                self.row.append(re.sub(r'\s+', ' ', ''.join(self.parts)).strip())
                self.cell = None
            elif tag == 'tr' and len(self.row) >= 2:
                self.rows[self.row[0].casefold()] = self.row[1]
        if tag == 'table':
            if self.infobox_depth == self.table_depth:
                self.infobox_depth, self.done = None, True
            self.table_depth -= 1

    def handle_data(self, text):
        if self.skip:
            return
        if self.heading_tag == 'h1':
            self.heading += text
        elif self.heading_tag == 'title':
            self.title += text
        if self.cell:
            self.parts.append(text)

    def result(self):
        return {'heading':(self.heading or self.title.removesuffix(' - Wikipedia')).strip(), 'fields':self.rows}


class WikipediaRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != 'https' or parsed.hostname != 'en.wikipedia.org':
            raise RuntimeError('Unexpected artist reference redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fresh(timestamp, now):
    return timestamp and dt.timedelta(0) <= now-dt.datetime.fromisoformat(timestamp) < dt.timedelta(days=CACHE_DAYS)


def fetch_page(url, cached=None):
    """Conditional public-page GETs; never transmit account metadata or contacts."""
    if not url.startswith('https://en.wikipedia.org/wiki/'):
        raise ValueError('Unsupported artist reference URL')
    cached = cached or {}
    headers = {'User-Agent':USER_AGENT}
    for field, header in (('etag','If-None-Match'),('last_modified','If-Modified-Since')):
        if cached.get(field):
            headers[header] = cached[field]
    opener = urllib.request.build_opener(WikipediaRedirects())
    for attempt in range(3):
        try:
            with opener.open(urllib.request.Request(url,headers=headers),timeout=30) as response:
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise RuntimeError('Artist reference page exceeds size limit')
                parser = ArtistPage()
                parser.feed(raw.decode('utf-8'))
                return {'page':parser.result(), 'canonical':parser.canonical or response.url,
                        'etag':response.headers.get('ETag'), 'last_modified':response.headers.get('Last-Modified')}
        except urllib.error.HTTPError as error:
            if error.code == 304 and 'page' in cached:
                return dict(cached)
            if error.code == 404:
                return {'page':None}
            if error.code not in (429,500,502,503,504) or attempt == 2:
                raise RuntimeError(f'Artist reference service failed (HTTP {error.code})') from None
        except (urllib.error.URLError,TimeoutError):
            if attempt == 2:
                raise RuntimeError('Artist reference service unavailable') from None
        time.sleep(2 ** (attempt+1))
    raise RuntimeError('Artist reference service unavailable')


def assess_page(page, name, today, pinned=False, redirected=False):
    aliases = page['fields'].get('also known as','')
    named_alias = bool(re.search(r'(?<!\w)'+re.escape(name.strip())+r'(?!\w)',aliases,re.I))
    if not pinned and not redirected and not named_alias and normalized(page['heading']) != normalized(name):
        return {'status':'unknown', 'evidence':'Article identity does not match the Qobuz name'}
    fields = page['fields']
    if not any(k in fields for k in ('genres','genre','instruments','instrument','labels','musical career')):
        return {'status':'unknown', 'evidence':'No identifiable musical artist infobox'}
    if fields.get('died'):
        years = re.findall(r'\b(?:1[0-9]{3}|20[0-9]{2})\b',fields['died'])
        iso_date = re.search(r'\b(\d{4}-\d{2}-\d{2})\b',fields['died'])
        try:
            future = iso_date and dt.date.fromisoformat(iso_date[1]) > today
        except ValueError:
            return {'status':'unknown', 'evidence':'Unusable death date'}
        if years and int(years[0]) <= today.year and not future:
            return {'status':'deceased', 'evidence':'Died: '+fields['died'][:200]}
        return {'status':'unknown', 'evidence':'Unusable death date'}
    if fields.get('born') or fields.get('birth name'):
        return {'status':'active', 'evidence':'Living musical artist; no death field'}
    years = fields.get('years active','')
    current = list(re.finditer(r'\b(?:present|ongoing|current)\b',years,re.I))
    if current:
        tail = years[current[-1].end():]
        hiatus = re.search(r'\bhiatus(?: since)?\s+\d{4}|\b(?:indefinite hiatus|on hiatus)\b|\(hiatus\)',tail,re.I)
        historical = re.search(r'\d{4}\s*[–-]\s*\d{4}',tail)
        return {'status':'inactive' if hiatus and not historical else 'active', 'evidence':'Years active: '+years[:200]}
    dates = re.findall(r'\b(?:1[0-9]{3}|20[0-9]{2})\b',years)
    if re.search(r'\bhiatus\b',years,re.I) or (dates and max(map(int,dates)) < today.year):
        return {'status':'inactive', 'evidence':'Years active: '+years[:200]}
    return {'status':'unknown', 'evidence':'No unambiguous current activity field: '+years[:160]}


def assess_artist(name, today, prior, seed, get):
    old_status = prior.get('status',seed.get('reason','unknown'))
    # Confirmed deaths cannot be reversed by missing fields or a namesake page.
    if old_status == 'deceased':
        record = prior or seed
        return {'status':'deceased', 'source':record['source'],
                'evidence':record.get('evidence','Previously reviewed death record')}
    pinned = prior.get('source') or seed.get('source','')
    urls = [(pinned,True)] if pinned.startswith('https://en.wikipedia.org/wiki/') else []
    for suffix in ('',' (band)',' (musician)',' (rapper)',' (singer)',' (group)'):
        url = 'https://en.wikipedia.org/wiki/'+urllib.parse.quote((name.strip()+suffix).replace(' ','_'))
        if all(url != previous for previous,_ in urls):
            urls.append((url,False))
    for url,is_pinned in urls:
        reference = get(url)
        if not reference.get('page'):
            if is_pinned:
                return {'status':'unknown', 'evidence':'Pinned reference page no longer exists'}
            continue
        redirected = reference.get('canonical',url) != url
        result = assess_page(reference['page'],name,today,pinned=is_pinned,redirected=redirected)
        if result['status'] != 'unknown':
            if result['status'] == 'deceased' and seed.get('reason') == 'inactive':
                result['status'] = 'inactive'  # Reviewed group credit points to a deceased leader.
            return dict(result,source=reference.get('canonical',url))
        if is_pinned:
            return result  # Do not silently change a known identity to a namesake.
    return {'status':'unknown', 'evidence':'No unambiguous musical artist reference found'}


def refresh(artists, cache_path, seeds, now=None, fetch=fetch_page):
    now = now or dt.datetime.now(dt.timezone.utc)
    previous = json.loads(cache_path.read_text()) if cache_path.exists() else {'artists':{}}
    if previous.get('version',1) != 1 or not isinstance(previous.get('artists'),dict):
        raise RuntimeError('Invalid artist status cache')
    page_path = cache_path.with_name('artist-pages.json')
    pages = json.loads(page_path.read_text()) if page_path.exists() else {}
    requested = 0
    def get(url):
        nonlocal requested
        cached = pages.get(url,{})
        if fresh(cached.get('checked_at'),now):
            return cached
        record = dict(fetch(url,cached),checked_at=now.isoformat())
        pages[url] = record
        requested += 1
        # Save completed public lookups for retry after a partial scan; the artist
        # assessment is published only when all current lookups succeed.
        if requested % 25 == 0:
            atomic_json(page_path,pages)
            print(f'Artist reference: {requested} page checks completed',file=sys.stderr,flush=True)
        return record
    records,changes = dict(previous['artists']),[]
    for ident,name in artists.items():
        old,seed = records.get(ident,{}),seeds['artists'].get(ident,{})
        result = assess_artist(name,now.date(),old,seed,get)
        old_status = old.get('status',seed.get('reason','unknown'))
        if result['status'] == 'unknown':
            record = dict(old or seed,name=name,status=old_status,attempted_at=now.isoformat(),
                          assessment='unknown',assessment_note=result['evidence'])
        else:
            record = dict(result,name=name,checked_at=now.isoformat(),assessment='resolved')
            if result['status'] != old_status:
                changes.append({'id':ident,'name':name,'before':old_status,'after':result['status']})
        records[ident] = record
    atomic_json(page_path,pages)
    atomic_json(cache_path,{'version':1,'updated_at':now.isoformat(),'changes':changes,'artists':records})
    current = {ident:records[ident] for ident in artists}
    return {'artists':{ident:r for ident,r in current.items() if r['status'] in ('deceased','inactive')},
            'assessed':len(current),'unresolved':[ident for ident,r in current.items() if r['assessment']=='unknown'],
            'changes':changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    args = parser.parse_args()
    try:
        artists = json.load(sys.stdin)
        if not isinstance(artists,dict) or not artists or not all(isinstance(v,str) and v.strip() for v in artists.values()):
            raise RuntimeError('Invalid Qobuz artist list')
        print(json.dumps(refresh(artists,args.cache,json.loads(SEEDS.read_text()))))
    except Exception as error:
        print(f'Artist assessment failed: {error if isinstance(error,RuntimeError) else type(error).__name__}',file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
