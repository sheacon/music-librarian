"""Tests for library.py parsing and normalization."""

from pathlib import Path

import pytest

from music_librarian.library import (
    Album,
    Artist,
    check_volume_mounted,
    find_matching_artist,
    get_artist_path,
    get_artist_search_variants,
    get_letter_for_artist,
    normalize_artist,
    parse_album_folder,
    parse_new_folder,
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


# --- parse_new_folder ---


class TestParseNewFolder:
    def test_valid(self):
        result = parse_new_folder("Radiohead - [1997] OK Computer")
        assert result == ("Radiohead", 1997, "OK Computer")

    def test_the_prefix(self):
        result = parse_new_folder("The Beatles - [1966] Revolver")
        assert result == ("The Beatles", 1966, "Revolver")

    def test_hyphen_in_artist(self):
        result = parse_new_folder("Jay-Z - [2001] The Blueprint")
        assert result == ("Jay-Z", 2001, "The Blueprint")

    def test_extra_spaces(self):
        result = parse_new_folder("Artist  -  [2020]  Album")
        assert result == ("Artist", 2020, "Album")

    def test_invalid_no_separator(self):
        assert parse_new_folder("[2020] Album Title") is None

    def test_invalid_no_year(self):
        assert parse_new_folder("Artist - Album Title") is None

    def test_invalid_empty(self):
        assert parse_new_folder("") is None

    def test_invalid_bad_year(self):
        assert parse_new_folder("Artist - [abcd] Album") is None


# --- check_volume_mounted ---


class TestCheckVolumeMounted:
    def test_mounted(self, tmp_path):
        (tmp_path / "some_content").mkdir()
        assert check_volume_mounted(tmp_path) is True

    def test_empty_stub(self, tmp_path):
        empty = tmp_path / "empty_mount"
        empty.mkdir()
        assert check_volume_mounted(empty) is False

    def test_missing(self, tmp_path):
        assert check_volume_mounted(tmp_path / "nonexistent") is False


# --- find_matching_artist ---


class TestFindMatchingArtist:
    def test_exact_match(self):
        artists = ["Radiohead", "The Beatles", "Pink Floyd"]
        assert find_matching_artist("Radiohead", artists) == "Radiohead"

    def test_accent_mismatch(self):
        artists = ["Beyoncé", "Radiohead"]
        assert find_matching_artist("Beyonce", artists) == "Beyoncé"

    def test_typo_tolerance(self):
        artists = ["Radiohead", "The Beatles"]
        assert find_matching_artist("Radiohed", artists) == "Radiohead"

    def test_word_reordering(self):
        artists = ["The Black Keys", "Radiohead"]
        assert find_matching_artist("Black Keys The", artists) == "The Black Keys"

    def test_partial_match(self):
        artists = ["The Beatles", "Radiohead"]
        assert find_matching_artist("Beatles", artists) == "The Beatles"

    def test_case_insensitive(self):
        artists = ["Radiohead"]
        assert find_matching_artist("RADIOHEAD", artists) == "Radiohead"

    def test_no_match_below_threshold(self):
        artists = ["Radiohead", "The Beatles"]
        assert find_matching_artist("Completely Different", artists) is None

    def test_empty_list(self):
        assert find_matching_artist("Radiohead", []) is None

    def test_custom_threshold(self):
        artists = ["Radiohead", "The Beatles"]
        # Very high threshold should reject close but not exact matches
        assert find_matching_artist("Radiohea", artists, threshold=99) is None
        # Lower threshold should accept
        assert find_matching_artist("Radiohea", artists, threshold=80) == "Radiohead"
