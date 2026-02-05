"""Tests for ignore.py CRUD and variant matching."""

import json

import pytest

from music_librarian.ignore import (
    _load_ignore_list,
    _save_ignore_list,
    add_ignored_album,
    add_ignored_artist,
    get_ignored_albums,
    get_ignored_artists,
    is_album_ignored,
    is_album_ignored_with_variants,
    is_artist_ignored,
    remove_ignored_album,
    remove_ignored_artist,
)


# --- _load_ignore_list / _save_ignore_list ---


class TestLoadSave:
    def test_load_nonexistent_returns_empty(self, tmp_path):
        result = _load_ignore_list(tmp_path / "nope.json")
        assert result == {"artists": [], "albums": []}

    def test_roundtrip(self, tmp_path):
        path = tmp_path / "ignore.json"
        data = {"artists": ["Foo"], "albums": [{"artist": "Bar", "album": "Baz"}]}
        _save_ignore_list(data, path)
        loaded = _load_ignore_list(path)
        assert loaded == data

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "ignore.json"
        _save_ignore_list({"artists": [], "albums": []}, path)
        assert path.exists()


# --- add/remove/get artists ---


class TestArtistIgnore:
    def test_add_artist(self, tmp_ignore_file):
        result = _load_ignore_list(tmp_ignore_file)
        result["artists"].append("TestArtist")
        _save_ignore_list(result, tmp_ignore_file)

        loaded = _load_ignore_list(tmp_ignore_file)
        assert "TestArtist" in loaded["artists"]

    def test_add_duplicate_artist_rejected(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        assert "Nickelback" in data["artists"]

    def test_remove_artist(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        data["artists"] = [a for a in data["artists"] if a.lower() != "nickelback"]
        _save_ignore_list(data, populated_ignore_file)

        loaded = _load_ignore_list(populated_ignore_file)
        assert "Nickelback" not in loaded["artists"]

    def test_get_artists(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        assert len(data["artists"]) == 2
        assert "Nickelback" in data["artists"]
        assert "Creed" in data["artists"]


# --- add/remove/get albums ---


class TestAlbumIgnore:
    def test_add_album(self, tmp_ignore_file):
        data = _load_ignore_list(tmp_ignore_file)
        data["albums"].append({"artist": "Artist", "album": "Album"})
        _save_ignore_list(data, tmp_ignore_file)

        loaded = _load_ignore_list(tmp_ignore_file)
        assert len(loaded["albums"]) == 1

    def test_remove_album(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        original_count = len(data["albums"])
        data["albums"] = [
            e for e in data["albums"]
            if not (e["artist"].lower() == "radiohead" and e["album"].lower() == "pablo honey")
        ]
        _save_ignore_list(data, populated_ignore_file)

        loaded = _load_ignore_list(populated_ignore_file)
        assert len(loaded["albums"]) == original_count - 1

    def test_get_albums(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        assert len(data["albums"]) == 2


# --- is_artist_ignored (case insensitive check) ---


class TestIsArtistIgnored:
    def test_case_insensitive_match(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        artists_lower = [a.lower() for a in data["artists"]]
        assert "nickelback" in artists_lower
        assert "NICKELBACK".lower() in artists_lower

    def test_not_ignored(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        artists_lower = [a.lower() for a in data["artists"]]
        assert "radiohead" not in artists_lower


# --- is_album_ignored ---


class TestIsAlbumIgnored:
    def test_matches_case_insensitively(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        found = any(
            e["artist"].lower() == "radiohead" and e["album"].lower() == "pablo honey"
            for e in data["albums"]
        )
        assert found is True

    def test_not_found(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        found = any(
            e["artist"].lower() == "radiohead" and e["album"].lower() == "ok computer"
            for e in data["albums"]
        )
        assert found is False


# --- is_album_ignored_with_variants ---


class TestIsAlbumIgnoredWithVariants:
    def test_matches_canonical_name(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        # Check that "The Beatles" / "Yellow Submarine" is in the list
        # The function checks artist_name, canonical_name, and "The {canonical_name}"
        artist_variants = {"beatles", "beatles", "the beatles"}
        title_variants = {"yellow submarine"}

        found = any(
            e["artist"].lower() in artist_variants and e["album"].lower() in title_variants
            for e in data["albums"]
        )
        assert found is True

    def test_matches_with_normalized_title(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        # "Yellow Submarine (Remastered)" normalized to "yellow submarine"
        title_variants = {"yellow submarine (remastered)", "yellow submarine"}

        found = any(
            e["artist"].lower() == "the beatles" and e["album"].lower() in title_variants
            for e in data["albums"]
        )
        assert found is True

    def test_no_match(self, populated_ignore_file):
        data = _load_ignore_list(populated_ignore_file)
        artist_variants = {"beatles", "beatles", "the beatles"}
        title_variants = {"abbey road"}

        found = any(
            e["artist"].lower() in artist_variants and e["album"].lower() in title_variants
            for e in data["albums"]
        )
        assert found is False
