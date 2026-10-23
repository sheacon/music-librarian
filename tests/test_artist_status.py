"""Public profile parsing, weekly refresh, identity and delivery safeguards."""
import datetime as dt
import json
from unittest.mock import patch
import urllib.error

import pytest

from music_librarian import artist_status as status

NOW=dt.datetime(2026,10,23,12,tzinfo=dt.timezone.utc)
SEEDS={'artists':{}}


def page(name='Example',years='2000–present',died=None,born=None,extra=''):
    rows=[('Genres','Rock'),('Years active',years)]
    if died: rows.append(('Died',died))
    if born: rows.append(('Born',born))
    rows=''.join(f'<tr><th>{k}</th><td>{v}</td></tr>' for k,v in rows)
    parser=status.ArtistPage()
    parser.feed(f'<title>{name} - Wikipedia</title><h1>{name}</h1><table class="infobox vcard">{rows}</table>{extra}')
    return parser.result()


def fetched(**kwargs):
    return {'page':page(**kwargs)}


@pytest.mark.parametrize(('profile','expected'),[
    (page(born='1970-01-01'),'active'),
    (page(died='2026-10-20 (aged 56)'),'deceased'),
    (page(died='2026-12-20 (aged 56)'),'unknown'),
    (page(years='2000–2010'),'inactive'),
    (page(years='2000–2010, 2025–present'),'active'),
    (page(years='2000–present (on hiatus since 2018)'),'inactive'),
    (page(years='2000–2010 (hiatus), 2025–present'),'active'),
    (page(years='2000–present (hiatus 2012–2014)'),'active'),
    (page(years='2000–2026'),'unknown'),
    (page(years=''),'unknown'),
])
def test_public_fields_classify_status(profile,expected):
    assert status.assess_page(profile,'Example',NOW.date())['status']==expected


def test_member_death_in_article_does_not_retire_band():
    profile=page(extra='<p>The founder died. The band disbanded in 2012 and reunited.</p>')
    assert status.assess_page(profile,'Example',NOW.date())['status']=='active'


def test_namesakes_and_nonmusical_pages_are_unknown():
    assert status.assess_page(page('Other'),'Example',NOW.date())['status']=='unknown'
    profile={'heading':'Example','fields':{'died':'2000-01-01'}}
    assert status.assess_page(profile,'Example',NOW.date())['status']=='unknown'


def test_scripts_styles_and_citations_are_ignored():
    profile=page(years='2000–<style>.x{content:"2010"}</style><script>2010</script>present<sup>12</sup>')
    assert status.assess_page(profile,'Example',NOW.date())['status']=='active'


def test_weekly_refresh_and_new_artist_lookup(tmp_path):
    path=tmp_path/'status.json'
    calls=[]
    def fetch(url,cached):
        calls.append(url)
        return fetched()
    status.refresh({'1':'Example'},path,SEEDS,NOW,fetch)
    status.refresh({'1':'Example'},path,SEEDS,NOW+dt.timedelta(days=1),fetch)
    assert len(calls)==1
    status.refresh({'1':'Example'},path,SEEDS,NOW+dt.timedelta(days=7),fetch)
    assert len(calls)==2
    status.refresh({'1':'Example','2':'New band'},path,SEEDS,NOW+dt.timedelta(days=7),lambda u,c:fetched(name='New band'))
    assert json.loads(path.read_text())['artists']['2']['status']=='active'
    assert path.stat().st_mode & 0o777 == 0o600


def test_death_breakup_and_reunion_update_exclusions(tmp_path):
    path=tmp_path/'status.json'
    def refresh(day,**kwargs):
        return status.refresh({'1':'Example'},path,SEEDS,NOW+dt.timedelta(days=day),lambda u,c:fetched(**kwargs))
    assert not refresh(0,born='1970-01-01')['artists']
    dead=refresh(7,died='2026-10-24')
    assert dead['artists']['1']['status']=='deceased'
    def no_lookup(*args): pytest.fail('Confirmed deaths are retained')
    assert status.refresh({'1':'Example'},path,SEEDS,NOW+dt.timedelta(days=14),no_lookup)['artists']
    path.unlink()
    (tmp_path/'artist-pages.json').unlink()
    assert refresh(0,years='2000–2010')['artists']['1']['status']=='inactive'
    reunited=refresh(7,years='2000–2010, 2025–present')
    assert not reunited['artists']
    assert reunited['changes'][0]['before']=='inactive'
    assert refresh(14,years='2000–2010, 2025')['artists']['1']['status']=='inactive'


def test_failed_refresh_keeps_previous_status_cache(tmp_path):
    path=tmp_path/'status.json'
    status.refresh({'1':'Example'},path,SEEDS,NOW,lambda u,c:fetched())
    original=path.read_bytes()
    def fetch(url,cached):
        if url.endswith('/New'): raise RuntimeError('Unavailable')
        return fetched(years='2000–2010')
    with pytest.raises(RuntimeError):
        status.refresh({'1':'Example','2':'New'},path,SEEDS,NOW+dt.timedelta(days=7),fetch)
    assert path.read_bytes()==original


def test_missing_identity_retains_known_exclusion_and_discloses_unknowns(tmp_path):
    seeds={'artists':{'1':{'name':'Example','reason':'inactive','source':'https://en.wikipedia.org/wiki/Example'}}}
    result=status.refresh({'1':'Example','2':'New'},tmp_path/'status.json',seeds,NOW,lambda u,c:{'page':None})
    assert result['artists']['1']['status']=='inactive'
    assert set(result['unresolved'])=={'1','2'}
    assert '2' not in result['artists']


def test_pinned_identity_is_not_replaced_by_a_namesake():
    calls=[]
    def get(url):
        calls.append(url)
        return {'page':{'heading':'Removed artist','fields':{}}}
    old={'source':'https://en.wikipedia.org/wiki/Example_(band)'}
    assert status.assess_artist('Example',NOW.date(),old,{},get)['status']=='unknown'
    assert len(calls)==1


def test_wikipedia_redirect_resolves_a_stage_name_alias():
    get=lambda url:{'page':page(name='Full stage name',born='1970-01-01'),'canonical':'https://en.wikipedia.org/wiki/Full_stage_name'}
    assert status.assess_artist('Alias',NOW.date(),{},{},get)['status']=='active'


def test_removed_artists_not_in_current_exclusions(tmp_path):
    path=tmp_path/'status.json'
    status.refresh({'1':'Example'},path,SEEDS,NOW,lambda u,c:fetched(years='2000–2010'))
    result=status.refresh({'2':'New'},path,SEEDS,NOW+dt.timedelta(days=7),lambda u,c:fetched(name='New'))
    assert result['assessed']==1 and not result['artists']


def test_http_304_reuses_fields_and_sends_only_validators():
    cached={'page':page(),'etag':'public-tag','last_modified':'date'}
    with patch.object(status.urllib.request,'build_opener') as opener:
        opener.return_value.open.side_effect=urllib.error.HTTPError('https://en.wikipedia.org/wiki/Example',304,'unchanged',{},None)
        assert status.fetch_page('https://en.wikipedia.org/wiki/Example',cached)==cached
        request=opener.return_value.open.call_args.args[0]
        assert request.get_header('If-none-match')=='public-tag'
        assert '@' not in request.get_header('User-agent')


def test_nonwikipedia_targets_and_external_redirects_are_rejected():
    with pytest.raises(ValueError): status.fetch_page('https://example.org/private')
    with pytest.raises(RuntimeError,match='redirect'):
        status.WikipediaRedirects().redirect_request(None,None,302,'',{},'https://example.org/')


def test_explicit_stage_alias_and_html_canonical_metadata():
    profile=page(name='Legal name',born='1970-01-01')
    profile['fields']['also known as']='Other name Stage Name'
    assert status.assess_page(profile,'Stage Name',NOW.date())['status']=='active'
    parser=status.ArtistPage()
    parser.feed('<link rel="canonical" href="https://en.wikipedia.org/wiki/Legal_name">')
    assert parser.canonical=='https://en.wikipedia.org/wiki/Legal_name'
    parser.feed('<link rel="canonical" href="https://example.org/">')
    assert parser.canonical=='https://en.wikipedia.org/wiki/Legal_name'
