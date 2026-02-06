"""Tests for lastfm.py API integration."""

from unittest.mock import patch

import httpx
import pytest
import respx

from music_librarian.lastfm import (
    _call_lastfm_api,
    get_album_listeners,
    get_artist_top_tag,
    rank_albums_by_popularity,
)


class TestCallLastfmApi:
    def test_returns_none_without_api_key(self):
        with patch("music_librarian.lastfm.LASTFM_API_KEY", None):
            result = _call_lastfm_api("album.getinfo", api_key=None)
        assert result is None

    def test_returns_none_with_empty_api_key(self):
        result = _call_lastfm_api("album.getinfo", api_key="")
        assert result is None

    @respx.mock
    def test_returns_json_on_success(self):
        respx.get("https://ws.audioscrobbler.com/2.0/").mock(
            return_value=httpx.Response(200, json={"result": "ok"})
        )
        result = _call_lastfm_api("test.method", api_key="test_key")
        assert result == {"result": "ok"}

    @respx.mock
    def test_returns_none_on_http_error(self):
        respx.get("https://ws.audioscrobbler.com/2.0/").mock(
            return_value=httpx.Response(500)
        )
        result = _call_lastfm_api("test.method", api_key="test_key")
        assert result is None


class TestGetAlbumListeners:
    @respx.mock
    def test_returns_listener_count(self):
        respx.get("https://ws.audioscrobbler.com/2.0/").mock(
            return_value=httpx.Response(
                200,
                json={"album": {"listeners": "12345"}},
            )
        )
        result = get_album_listeners("Artist", "Album", api_key="test_key")
        assert result == 12345

    @respx.mock
    def test_returns_zero_on_failure(self):
        respx.get("https://ws.audioscrobbler.com/2.0/").mock(
            return_value=httpx.Response(404)
        )
        result = get_album_listeners("Artist", "Album", api_key="test_key")
        assert result == 0

    def test_returns_zero_without_api_key(self):
        with patch("music_librarian.lastfm.LASTFM_API_KEY", None):
            result = get_album_listeners("Artist", "Album", api_key=None)
        assert result == 0


class TestGetArtistTopTag:
    @respx.mock
    def test_returns_top_tag(self):
        respx.get("https://ws.audioscrobbler.com/2.0/").mock(
            return_value=httpx.Response(
                200,
                json={"toptags": {"tag": [{"name": "rock"}, {"name": "alternative"}]}},
            )
        )
        result = get_artist_top_tag("Radiohead", api_key="test_key")
        assert result == "rock"

    @respx.mock
    def test_returns_none_when_no_tags(self):
        respx.get("https://ws.audioscrobbler.com/2.0/").mock(
            return_value=httpx.Response(
                200,
                json={"toptags": {"tag": []}},
            )
        )
        result = get_artist_top_tag("Unknown Artist", api_key="test_key")
        assert result is None

    def test_returns_none_without_api_key(self):
        with patch("music_librarian.lastfm.LASTFM_API_KEY", None):
            result = get_artist_top_tag("Artist", api_key=None)
        assert result is None


class TestRankAlbumsByPopularity:
    @respx.mock
    def test_ranks_by_listeners_descending(self):
        call_count = 0

        def mock_response(request):
            nonlocal call_count
            call_count += 1
            album_param = dict(request.url.params).get("album", "")
            listeners = {"Album A": "100", "Album B": "500", "Album C": "200"}
            return httpx.Response(
                200,
                json={"album": {"listeners": listeners.get(album_param, "0")}},
            )

        respx.get("https://ws.audioscrobbler.com/2.0/").mock(side_effect=mock_response)

        from music_librarian.qobuz import QobuzAlbum

        albums = [
            QobuzAlbum(id="1", title="Album A", year=2020, artist="Artist", url=""),
            QobuzAlbum(id="2", title="Album B", year=2021, artist="Artist", url=""),
            QobuzAlbum(id="3", title="Album C", year=2022, artist="Artist", url=""),
        ]

        ranked = rank_albums_by_popularity(albums, "Artist", api_key="test_key")
        assert ranked[0][1] == 500  # Album B has most listeners
        assert ranked[1][1] == 200  # Album C second
        assert ranked[2][1] == 100  # Album A last
