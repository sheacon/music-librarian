"""Tests for library.py parsing and normalization."""

from pathlib import Path

import pytest

from music_librarian.library import (
    Album,
    Artist,
    get_artist_path,
    get_artist_search_variants,
    get_letter_for_artist,
    normalize_artist,
    parse_album_folder,
    scan_library,
)


# --- normalize_artist ---


class TestNormalizeArtist:
    def test_strips_the_prefix(self):
        assert normalize_artist("The Beatles") == "Beatles"

    def test_case_insensitive(self):
        assert normalize_artist("the rolling stones") == "rolling stones"

    def test_no_prefix_unchanged(self):
        assert normalize_artist("Radiohead") == "Radiohead"

    def test_the_the_strips_once(self):
        assert normalize_artist("The The") == "The"

    def test_empty_string(self):
        assert normalize_artist("") == ""

    def test_just_the(self):
        assert normalize_artist("The ") == ""

    def test_thee_not_stripped(self):
        assert normalize_artist("Thee Oh Sees") == "Thee Oh Sees"


# --- get_artist_search_variants ---


class TestGetArtistSearchVariants:
    def test_without_the_prefix(self):
        variants = get_artist_search_variants("Radiohead")
        assert "Radiohead" in variants
        assert "The Radiohead" in variants

    def test_with_the_prefix(self):
        variants = get_artist_search_variants("The Beatles")
        assert "Beatles" in variants
        assert "The Beatles" in variants

    def test_always_returns_two_variants(self):
        assert len(get_artist_search_variants("Radiohead")) == 2
        assert len(get_artist_search_variants("The Beatles")) == 2


# --- parse_album_folder ---


class TestParseAlbumFolder:
    def test_valid_format(self):
        result = parse_album_folder("[2020] Album Title")
        assert result == (2020, "Album Title")

    def test_old_year(self):
        result = parse_album_folder("[1969] Abbey Road")
        assert result == (1969, "Abbey Road")

    def test_no_space_after_bracket(self):
        result = parse_album_folder("[2020]Album Title")
        assert result == (2020, "Album Title")

    def test_invalid_no_brackets(self):
        assert parse_album_folder("2020 Album Title") is None

    def test_invalid_no_year(self):
        assert parse_album_folder("[abcd] Album Title") is None

    def test_invalid_short_year(self):
        assert parse_album_folder("[20] Album Title") is None

    def test_empty_string(self):
        assert parse_album_folder("") is None

    def test_title_with_special_chars(self):
        result = parse_album_folder("[2004] Franz Ferdinand")
        assert result == (2004, "Franz Ferdinand")


# --- get_letter_for_artist ---


class TestGetLetterForArtist:
    def test_regular_artist(self):
        assert get_letter_for_artist("Radiohead") == "R"

    def test_strips_the(self):
        assert get_letter_for_artist("The Beatles") == "B"

    def test_lowercase_input(self):
        assert get_letter_for_artist("radiohead") == "R"

    def test_the_prefix_lowercase(self):
        assert get_letter_for_artist("the beatles") == "B"

    def test_empty_string_fallback(self):
        # normalize_artist("") returns "", which is falsy, so fallback to "A"
        assert get_letter_for_artist("") == "A"


# --- scan_library ---


class TestScanLibrary:
    def test_scans_library_structure(self, tmp_library):
        artists = scan_library(tmp_library)
        assert "Beatles" in artists
        assert "Radiohead" in artists
        assert "Pink Floyd" in artists

    def test_artist_has_albums(self, tmp_library):
        artists = scan_library(tmp_library)
        beatles = artists["Beatles"]
        assert len(beatles.albums) == 2
        titles = {a.title for a in beatles.albums}
        assert "Abbey Road" in titles
        assert "Sgt. Peppers Lonely Hearts Club Band" in titles

    def test_album_year_parsed(self, tmp_library):
        artists = scan_library(tmp_library)
        radiohead = artists["Radiohead"]
        years = {a.year for a in radiohead.albums}
        assert 1997 in years
        assert 2000 in years

    def test_nonexistent_path_returns_empty(self, tmp_path):
        artists = scan_library(tmp_path / "nonexistent")
        assert artists == {}

    def test_empty_library_returns_empty(self, tmp_path):
        lib = tmp_path / "empty_lib"
        lib.mkdir()
        artists = scan_library(lib)
        assert artists == {}

    def test_skips_non_letter_folders(self, tmp_library):
        # Create a non-letter folder (should be ignored)
        (tmp_library / ".DS_Store").touch()
        (tmp_library / "misc").mkdir()
        artists = scan_library(tmp_library)
        assert len(artists) == 3  # Only Beatles, Radiohead, Pink Floyd

    def test_skips_non_album_folders(self, tmp_library):
        # Create a non-album folder inside an artist
        (tmp_library / "B" / "Beatles" / "extras").mkdir()
        artists = scan_library(tmp_library)
        # Should still only have 2 albums
        assert len(artists["Beatles"].albums) == 2

    def test_artist_canonical_name(self, tmp_library):
        artists = scan_library(tmp_library)
        assert artists["Beatles"].canonical_name == "Beatles"

    def test_artist_path(self, tmp_library):
        artists = scan_library(tmp_library)
        assert artists["Beatles"].path == tmp_library / "B" / "Beatles"


# --- get_artist_path ---


class TestGetArtistPath:
    def test_regular_artist(self, tmp_path):
        result = get_artist_path("Radiohead", tmp_path)
        assert result == tmp_path / "R" / "Radiohead"

    def test_the_prefix_stripped(self, tmp_path):
        result = get_artist_path("The Beatles", tmp_path)
        assert result == tmp_path / "B" / "Beatles"
