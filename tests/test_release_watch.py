"""Behavior checks for release dates, edition duplicates, and uncertain delivery."""
import datetime as dt
import json
from unittest.mock import patch

import pytest

from music_librarian import release_watch as watch
from music_librarian.qobuz_auth import atomic_json


def album(id='1', title='New record', date='2026-09-25', **kwargs):
    return dict(id=id, title=title, release_date_original=date,
                artist={'id': 42, 'name': 'Artist'}, **({'release_type':'album'} | kwargs))


def test_releases_exclude_live_singles_future_old_unavailable():
    items = [album(), album('2', 'New single', release_type='single'),
             album('3', 'Live in Richmond'), album('4', 'Future record', date='2026-10-02'),
             album('5', 'Old record', date='1999-01-01'), album('6', date=None),
             album('7', streamable=False)]
    found = watch.select_releases(items, dt.date(2026, 9, 23), dt.date(2026, 9, 30), set())
    assert {a['id'] for a in found} == {'1'}


def test_best_fidelity_edition_once_and_delivered_not_repeated():
    items = [album(maximum_bit_depth=16), album('2', 'New record (Deluxe Edition)', maximum_bit_depth=24)]
    found = watch.select_releases(items, dt.date(2026, 9, 23), dt.date(2026, 9, 30), set())
    assert [a['id'] for a in found] == ['2']
    assert not watch.select_releases(items, dt.date(2026, 9, 23), dt.date(2026, 9, 30), {watch.release_key(found[0])})


def pending():
    return {'message_id':'qobuz-example@index.local', 'subject':'Test', 'body':'Test'}


def test_uncertain_delivery_is_not_resent(tmp_path):
    item = pending()
    with patch.object(watch, 'gmail', side_effect=[{}, RuntimeError('timeout')]):
        with pytest.raises(RuntimeError):
            watch.deliver(tmp_path, item)
    saved = json.loads((tmp_path/'pending.json').read_text())
    assert saved['attempted'] is True
    with patch.object(watch, 'gmail', return_value={}) as gmail:
        with pytest.raises(RuntimeError, match='uncertain'):
            watch.deliver(tmp_path, saved)
        assert gmail.call_count == 1


def test_uncertain_delivery_reconciled_even_if_trashed(tmp_path):
    item = dict(pending(), attempted=True)
    with patch.object(watch, 'gmail', return_value={'messages':[{'id':'sent-id'}]}) as gmail:
        assert watch.deliver(tmp_path, item) == 'sent-id'
        assert gmail.call_args.args[1]['includeSpamTrash'] is True
        assert gmail.call_count == 1


def test_confirmed_send(tmp_path):
    with patch.object(watch, 'gmail', side_effect=[{}, {'id':'ok'}]) as gmail:
        assert watch.deliver(tmp_path, pending()) == 'ok'
        assert gmail.call_args.args[0] == 'send'


def test_failed_search_never_attempts_send(tmp_path):
    with patch.object(watch, 'gmail', side_effect=RuntimeError('offline')):
        with pytest.raises(RuntimeError):
            watch.deliver(tmp_path, pending())
    assert not (tmp_path/'pending.json').exists()


def test_auth_file_permissions(tmp_path):
    path = tmp_path / 'auth.json'
    atomic_json(path, {'token':'test'})
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == {'token':'test'}


def test_reissue_incorrectly_dated_new_is_excluded_when_older_edition_exists():
    items = [album(date='1996-09-23'), album('2', 'New record (Deluxe Edition)', date='2026-09-25')]
    assert not watch.select_releases(items, dt.date(2026,9,23), dt.date(2026,9,30), set())


def test_classification_overrules_track_count_and_unknown_is_excluded():
    items = [album(tracks_count=3), album('2', 'Long EP', release_type='ep', tracks_count=10),
             album('3', 'Unknown', release_type=None, tracks_count=12)]
    assert [a['id'] for a in watch.select_releases(items, dt.date(2026,9,23), dt.date(2026,9,30), set())] == ['1']


def test_earlier_single_does_not_suppress_same_named_album():
    items = [album('single',date='2026-08-01',release_type='single'), album()]
    assert [a['id'] for a in watch.select_releases(items,dt.date(2026,9,23),dt.date(2026,9,30),set())] == ['1']


@pytest.mark.parametrize('genre', [
    {'id': 10, 'name': 'Classical'},
    {'id': 27, 'name': 'Chamber Music', 'path': [10, 27]},
    {'id': 11, 'name': 'Symphonic Music', 'path': ['10', '11']},
    {'name': 'Classical'},
    {'slug': 'classique'},
])
def test_classical_and_subgenres_excluded_regardless_of_artist(genre):
    items = [album('classical', genre=genre), album('rock', title='Rock record', genre={'id': 119, 'path': [112, 119]}),
             album('jazz', title='Jazz record', genre={'id': 80, 'path': [80]}), album('unknown', title='Unknown genre record', genre=None)]
    found = watch.select_releases(items, dt.date(2026, 9, 23), dt.date(2026, 9, 30), set())
    assert {a['id'] for a in found} == {'rock', 'jazz', 'unknown'}


def test_email_explains_classical_exclusion():
    body = watch.render([], 1, dt.date(2026, 9, 23), dt.date(2026, 9, 30))
    assert 'classical music (including its subgenres)' in body


@pytest.mark.parametrize('fields', [
    {'release_tags': ['live']}, {'release_tags': ['compilation']},
    {'release_tags': ['remaster']}, {'release_tags': ['reissue']},
    {'version': 'Live'}, {'version': '2010 Remaster'},
    {'title': 'Greatest Hits'}, {'title': 'The Best of Artist'},
    {'title': 'New Record (25th Anniversary Edition)'},
    {'title': 'New Record [Remastered]'}, {'is_compilation': True},
    {'title': 'Live at the Hall'}, {'title': 'Hidden in Pieces: Live'},
    {'title': 'New Record', 'recording_information': 'Live recording'},
])
def test_archival_release_markers_excluded(fields):
    item = album()
    item.update(fields)
    assert not watch.select_releases([item], dt.date(2026,9,23), dt.date(2026,9,30), set())


def test_artist_exclusion_uses_ids_and_main_credits_not_guests():
    def credited(ident, **kwargs):
        item = album(**kwargs)
        item['artist'] = {'id': ident, 'name': 'Same name'}
        return item
    items = [credited(1, id='inactive'), credited(2, id='active'),
             credited(2, id='guest', title='Guest album', artists=[{'id':1,'roles':['featured-artist']}]),
             credited(2, id='collaboration', title='Joint album', artists=[{'id':1,'roles':['main-artist']}])]
    found = watch.select_releases(items, dt.date(2026,9,23), dt.date(2026,9,30), set(), excluded={'1'})
    assert {a['id'] for a in found} == {'active', 'guest'}


def test_reviewed_exclusions_and_active_members_are_separate():
    excluded = watch.excluded_artist_ids()
    assert {'41736', '135918', '35028', '6760', '38326'} <= excluded
    # Jack White the musician is alive; his defunct band is a separate credit.
    assert '384484' in excluded
    assert '40569' not in excluded
    assert '118681' not in excluded  # Reunited Oasis.
    assert '50891' not in excluded  # Tangerine Dream continues after its founder.


@pytest.mark.parametrize('title', ['Live Through This', 'Alive', 'New record (Deluxe Edition)'])
def test_studio_titles_and_current_deluxe_editions_not_overfiltered(title):
    assert not watch.is_archival_release(album(title=title))


def test_runtime_assessment_can_restore_previously_excluded_artist():
    item=album()
    item['artist']={'id':135918,'name':'Reunited band'}
    found=watch.select_releases([item],dt.date(2026,9,23),dt.date(2026,9,30),set(),excluded=set())
    assert found == [item]


def test_digest_discloses_unresolved_assessments():
    body=watch.render([],10,dt.date(2026,9,23),dt.date(2026,9,30),{'artists':{'1':{}},'unresolved':['2']})
    assert '1 excluded, 1 unresolved' in body
    assert 'new unknown artists remain eligible' in body


def test_assessment_failure_never_sends_or_advances_checkpoint(tmp_path):
    import subprocess
    original={'through':'2026-09-30','delivered':['old']}
    atomic_json(tmp_path/'state.json',original)
    with patch.object(watch.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'collector')), patch.object(watch,'deliver') as deliver:
        with pytest.raises(subprocess.CalledProcessError):
            watch.run(tmp_path,preview=True)
    deliver.assert_not_called()
    assert json.loads((tmp_path/'state.json').read_text()) == original
    assert not (tmp_path/'pending.json').exists()
