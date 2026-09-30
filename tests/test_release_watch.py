"""Behavior checks for release dates, edition duplicates, and uncertain delivery."""
import datetime as dt
import json
from unittest.mock import patch

import pytest

from music_librarian import release_watch as watch
from music_librarian.qobuz_auth import atomic_json


def album(id='1', title='New record', date='2026-09-25', **kwargs):
    return dict(id=id, title=title, release_date_original=date,
                artist={'id': 42, 'name': 'Artist'}, **kwargs)


def test_releases_include_singles_and_live_exclude_future_old_unavailable():
    items = [album(), album('2', 'New single', release_type='single'),
             album('3', 'Live in Richmond'), album('4', 'Future record', date='2026-10-02'),
             album('5', 'Old record', date='1999-01-01'), album('6', date=None),
             album('7', streamable=False)]
    found = watch.select_releases(items, dt.date(2026, 9, 23), dt.date(2026, 9, 30), set())
    assert {a['id'] for a in found} == {'1', '2', '3'}


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
