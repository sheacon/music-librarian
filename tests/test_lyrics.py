"""Tests for lyrics.py API integration."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from music_librarian.lyrics import (
    get_lyrics,
    get_lyrics_from_genius,
    get_lyrics_from_lrclib,
)


# --- get_lyrics_from_lrclib ---


class TestGetLyricsFromLrclib:
    @respx.mock
    def test_returns_plain_lyrics(self):
        respx.get("https://lrclib.net/api/get").mock(
            return_value=httpx.Response(
                200,
                json={
                    "plainLyrics": "Hello world\nSecond line",
                    "syncedLyrics": None,
                },
            )
        )
        result = get_lyrics_from_lrclib("Artist", "Song")
        assert result == "Hello world\nSecond line"

    @respx.mock
    def test_falls_back_to_synced_lyrics(self):
        respx.get("https://lrclib.net/api/get").mock(
            return_value=httpx.Response(
                200,
                json={
                    "plainLyrics": None,
                    "syncedLyrics": "[00:12.34] Hello world\n[00:15.67] Second line",
                },
            )
        )
        result = get_lyrics_from_lrclib("Artist", "Song")
        assert result is not None
        assert "Hello world" in result
        assert "[00:" not in result  # Timestamps stripped

    @respx.mock
    def test_returns_none_on_404(self):
        respx.get("https://lrclib.net/api/get").mock(
            return_value=httpx.Response(404)
        )
        result = get_lyrics_from_lrclib("Artist", "Song")
        assert result is None

    @respx.mock
    def test_returns_none_on_empty_response(self):
        respx.get("https://lrclib.net/api/get").mock(
            return_value=httpx.Response(
                200,
                json={"plainLyrics": None, "syncedLyrics": None},
            )
        )
        result = get_lyrics_from_lrclib("Artist", "Song")
        assert result is None

    @respx.mock
    def test_passes_album_param(self):
        route = respx.get("https://lrclib.net/api/get").mock(
            return_value=httpx.Response(
                200,
                json={"plainLyrics": "lyrics", "syncedLyrics": None},
            )
        )
        get_lyrics_from_lrclib("Artist", "Song", album="Album")
        assert route.called
        request = route.calls.last.request
        assert "album_name" in str(request.url)

    def test_handles_network_error(self):
        # The function has a broad except clause, so it should return None
        with patch("music_librarian.lyrics.httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = MagicMock(
                side_effect=httpx.ConnectError("fail")
            )
            result = get_lyrics_from_lrclib("Artist", "Song")
            assert result is None


# --- get_lyrics_from_genius ---


class TestGetLyricsFromGenius:
    def test_returns_none_without_api_key(self):
        with patch("music_librarian.lyrics.GENIUS_API_KEY", None):
            result = get_lyrics_from_genius("Artist", "Song", api_key=None)
        assert result is None

    def test_returns_none_with_empty_api_key(self):
        result = get_lyrics_from_genius("Artist", "Song", api_key="")
        assert result is None

    @respx.mock
    def test_returns_none_on_search_failure(self):
        respx.get("https://api.genius.com/search").mock(
            return_value=httpx.Response(500)
        )
        result = get_lyrics_from_genius("Artist", "Song", api_key="test_key")
        assert result is None

    @respx.mock
    def test_returns_none_on_no_hits(self):
        respx.get("https://api.genius.com/search").mock(
            return_value=httpx.Response(
                200,
                json={"response": {"hits": []}},
            )
        )
        result = get_lyrics_from_genius("Artist", "Song", api_key="test_key")
        assert result is None

    def test_matches_artist_in_results(self):
        search_response = httpx.Response(
            200,
            json={
                "response": {
                    "hits": [
                        {
                            "result": {
                                "primary_artist": {"name": "Completely Different Band"},
                                "url": "https://genius.com/wrong",
                            }
                        },
                        {
                            "result": {
                                "primary_artist": {"name": "Radiohead"},
                                "url": "https://genius.com/right",
                            }
                        },
                    ]
                }
            },
        )
        lyrics_response = httpx.Response(
            200,
            text='<div data-lyrics-container="true">Hello lyrics</div>',
        )

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(side_effect=[search_response, lyrics_response])

        with patch("music_librarian.lyrics.httpx.Client", return_value=mock_client):
            result = get_lyrics_from_genius("Radiohead", "Song", api_key="test_key")

        assert result == "Hello lyrics"
        # Verify first call was to search API
        assert "search" in str(mock_client.get.call_args_list[0])
        # Verify second call was to the matched artist URL
        assert mock_client.get.call_args_list[1][0][0] == "https://genius.com/right"


# --- get_lyrics ---


class TestGetLyrics:
    @respx.mock
    def test_prefers_lrclib(self):
        respx.get("https://lrclib.net/api/get").mock(
            return_value=httpx.Response(
                200,
                json={"plainLyrics": "LRCLIB lyrics", "syncedLyrics": None},
            )
        )
        lyrics, source = get_lyrics("Artist", "Song")
        assert lyrics == "LRCLIB lyrics"
        assert source == "lrclib"

    @respx.mock
    def test_falls_back_to_genius(self):
        respx.get("https://lrclib.net/api/get").mock(
            return_value=httpx.Response(404)
        )
        respx.get("https://api.genius.com/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "response": {
                        "hits": [
                            {
                                "result": {
                                    "primary_artist": {"name": "Artist"},
                                    "url": "https://genius.com/song",
                                }
                            }
                        ]
                    }
                },
            )
        )
        respx.get("https://genius.com/song").mock(
            return_value=httpx.Response(
                200,
                text='<div data-lyrics-container="true">Genius lyrics</div>',
            )
        )
        lyrics, source = get_lyrics("Artist", "Song", genius_api_key="test_key")
        assert lyrics == "Genius lyrics"
        assert source == "genius"

    @respx.mock
    def test_returns_none_when_both_fail(self):
        respx.get("https://lrclib.net/api/get").mock(
            return_value=httpx.Response(404)
        )
        lyrics, source = get_lyrics("Artist", "Song", genius_api_key=None)
        assert lyrics is None
        assert source == "none"
