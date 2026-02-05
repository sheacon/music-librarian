"""Tests for cli.py helpers."""

from pathlib import Path

import pytest

from music_librarian.cli import find_album_directories


class TestFindAlbumDirectories:
    def test_single_album_dir(self, tmp_path):
        album = tmp_path / "[2020] Album Title"
        album.mkdir()
        result = find_album_directories(album)
        assert result == [album]

    def test_finds_albums_recursively(self, tmp_library):
        result = find_album_directories(tmp_library)
        assert len(result) == 5  # 2 Beatles + 2 Radiohead + 1 Pink Floyd
        names = [p.name for p in result]
        assert "[1969] Abbey Road" in names
        assert "[1997] OK Computer" in names

    def test_empty_dir_returns_empty(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = find_album_directories(empty)
        assert result == []

    def test_skips_non_album_dirs(self, tmp_path):
        (tmp_path / "not_an_album").mkdir()
        (tmp_path / "[2020] Real Album").mkdir()
        result = find_album_directories(tmp_path)
        assert len(result) == 1
        assert result[0].name == "[2020] Real Album"

    def test_finds_in_artist_folder(self, tmp_path):
        artist = tmp_path / "Beatles"
        (artist / "[1969] Abbey Road").mkdir(parents=True)
        (artist / "[1967] Sgt Pepper").mkdir(parents=True)
        result = find_album_directories(artist)
        assert len(result) == 2

    def test_sorted_alphabetically(self, tmp_path):
        (tmp_path / "[2020] Zebra").mkdir()
        (tmp_path / "[2020] Alpha").mkdir()
        (tmp_path / "[2020] Middle").mkdir()
        result = find_album_directories(tmp_path)
        names = [p.name for p in result]
        assert names == sorted(names)
