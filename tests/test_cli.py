"""Tests for cli.py helpers and commands."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from music_librarian.cli import app, find_album_directories

runner = CliRunner()


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


# --- stage command ---


class TestStage:
    def _make_album(self, tmp_path):
        """Create a fake album folder in a downloads dir."""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        album = downloads / "Radiohead - [1997] OK Computer"
        album.mkdir()
        (album / "01 - Airbag.flac").touch()
        return downloads, album

    def _make_volume(self, tmp_path):
        """Create a fake mounted volume with [New] dir."""
        volume = tmp_path / "volume"
        volume.mkdir()
        new = volume / "[New]"
        new.mkdir()
        return volume, new

    def test_list(self, tmp_path):
        downloads, album = self._make_album(tmp_path)
        # Add another album
        (downloads / "The Beatles - [1966] Revolver").mkdir()

        with patch("music_librarian.cli.DOWNLOADS_PATH", downloads):
            result = runner.invoke(app, ["stage"])

        assert result.exit_code == 0
        assert "Albums in Downloads (2)" in result.output
        assert "Radiohead - [1997] OK Computer" in result.output
        assert "The Beatles - [1966] Revolver" in result.output

    def test_list_empty(self, tmp_path):
        downloads = tmp_path / "downloads"
        downloads.mkdir()

        with patch("music_librarian.cli.DOWNLOADS_PATH", downloads):
            result = runner.invoke(app, ["stage"])

        assert result.exit_code == 0
        assert "No albums" in result.output

    def test_list_skips_non_album_dirs(self, tmp_path):
        downloads, album = self._make_album(tmp_path)
        (downloads / "random_folder").mkdir()

        with patch("music_librarian.cli.DOWNLOADS_PATH", downloads):
            result = runner.invoke(app, ["stage"])

        assert result.exit_code == 0
        assert "Albums in Downloads (1)" in result.output
        assert "random_folder" not in result.output

    @patch("music_librarian.cli.rsync_album")
    def test_dry_run(self, mock_rsync, tmp_path):
        downloads, album = self._make_album(tmp_path)
        volume, new = self._make_volume(tmp_path)
        mock_rsync.return_value = True

        with patch("music_librarian.cli.DOWNLOADS_PATH", downloads), \
             patch("music_librarian.cli.MUSIC_VOLUME", volume), \
             patch("music_librarian.cli.NEW_PATH", new):
            result = runner.invoke(app, ["stage", "-n", "Radiohead - [1997] OK Computer"])

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert album.exists()  # Source not deleted

    @patch("music_librarian.cli.rsync_album")
    def test_success(self, mock_rsync, tmp_path):
        downloads, album = self._make_album(tmp_path)
        volume, new = self._make_volume(tmp_path)

        # Simulate rsync creating the destination as a side effect
        def fake_rsync(source, dest, dry_run=False):
            dest_album = dest / source.name
            dest_album.mkdir(parents=True, exist_ok=True)
            (dest_album / "01 - Airbag.flac").touch()
            return True

        mock_rsync.side_effect = fake_rsync

        with patch("music_librarian.cli.DOWNLOADS_PATH", downloads), \
             patch("music_librarian.cli.MUSIC_VOLUME", volume), \
             patch("music_librarian.cli.NEW_PATH", new), \
             patch("music_librarian.cli.delete_source") as mock_delete:
            result = runner.invoke(app, ["stage", "Radiohead - [1997] OK Computer"])

        assert result.exit_code == 0
        assert "Staged successfully" in result.output
        mock_delete.assert_called_once_with(album)

    def test_folder_not_found(self, tmp_path):
        downloads = tmp_path / "downloads"
        downloads.mkdir()

        with patch("music_librarian.cli.DOWNLOADS_PATH", downloads):
            result = runner.invoke(app, ["stage", "Nonexistent - [2024] Album"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_bad_folder_name(self, tmp_path):
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        (downloads / "bad_name").mkdir()

        with patch("music_librarian.cli.DOWNLOADS_PATH", downloads):
            result = runner.invoke(app, ["stage", "bad_name"])

        assert result.exit_code == 1
        assert "doesn't match" in result.output

    def test_volume_not_mounted(self, tmp_path):
        downloads, album = self._make_album(tmp_path)
        # Empty volume dir simulates unmounted
        volume = tmp_path / "volume"
        volume.mkdir()

        with patch("music_librarian.cli.DOWNLOADS_PATH", downloads), \
             patch("music_librarian.cli.MUSIC_VOLUME", volume):
            result = runner.invoke(app, ["stage", "Radiohead - [1997] OK Computer"])

        assert result.exit_code == 1
        assert "not mounted" in result.output

    def test_destination_exists(self, tmp_path):
        downloads, album = self._make_album(tmp_path)
        volume, new = self._make_volume(tmp_path)
        # Pre-create destination
        (new / album.name).mkdir()

        with patch("music_librarian.cli.DOWNLOADS_PATH", downloads), \
             patch("music_librarian.cli.MUSIC_VOLUME", volume), \
             patch("music_librarian.cli.NEW_PATH", new):
            result = runner.invoke(app, ["stage", "Radiohead - [1997] OK Computer"])

        assert result.exit_code == 1
        assert "Already exists" in result.output


# --- shelve command ---


class TestShelve:
    def _make_new_dir(self, tmp_path):
        """Create a fake [New] dir with an album."""
        volume = tmp_path / "volume"
        volume.mkdir()
        new = volume / "[New]"
        new.mkdir()
        album = new / "Radiohead - [1997] OK Computer"
        album.mkdir()
        (album / "01 - Airbag.flac").touch()
        lib = volume / "Alphabetical"
        lib.mkdir()
        return volume, new, album, lib

    def test_list(self, tmp_path):
        volume, new, album, lib = self._make_new_dir(tmp_path)

        with patch("music_librarian.cli.MUSIC_VOLUME", volume), \
             patch("music_librarian.cli.NEW_PATH", new), \
             patch("music_librarian.cli.LIBRARY_PATH", lib):
            result = runner.invoke(app, ["shelve"])

        assert result.exit_code == 0
        assert "Radiohead - [1997] OK Computer" in result.output
        assert "Albums in [New]" in result.output

    def test_dry_run(self, tmp_path):
        volume, new, album, lib = self._make_new_dir(tmp_path)

        with patch("music_librarian.cli.MUSIC_VOLUME", volume), \
             patch("music_librarian.cli.NEW_PATH", new), \
             patch("music_librarian.cli.LIBRARY_PATH", lib):
            result = runner.invoke(app, ["shelve", "-n", "Radiohead - [1997] OK Computer"])

        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert album.exists()  # Source not moved

    @patch("music_librarian.cli.move_album")
    def test_success(self, mock_move, tmp_path):
        volume, new, album, lib = self._make_new_dir(tmp_path)
        (lib / "R" / "Radiohead").mkdir(parents=True)

        with patch("music_librarian.cli.MUSIC_VOLUME", volume), \
             patch("music_librarian.cli.NEW_PATH", new), \
             patch("music_librarian.cli.LIBRARY_PATH", lib):
            result = runner.invoke(app, ["shelve", "Radiohead - [1997] OK Computer"])

        assert result.exit_code == 0
        assert "Shelved successfully" in result.output
        expected_dest = lib / "R" / "Radiohead" / "[1997] OK Computer"
        mock_move.assert_called_once_with(album, expected_dest)

    @patch("music_librarian.cli.move_album")
    def test_the_prefix(self, mock_move, tmp_path):
        volume = tmp_path / "volume"
        volume.mkdir()
        new = volume / "[New]"
        new.mkdir()
        album = new / "The Beatles - [1966] Revolver"
        album.mkdir()
        (album / "01 - Taxman.flac").touch()
        lib = volume / "Alphabetical"
        lib.mkdir()
        (lib / "B" / "Beatles").mkdir(parents=True)

        with patch("music_librarian.cli.MUSIC_VOLUME", volume), \
             patch("music_librarian.cli.NEW_PATH", new), \
             patch("music_librarian.cli.LIBRARY_PATH", lib):
            result = runner.invoke(app, ["shelve", "The Beatles - [1966] Revolver"])

        assert result.exit_code == 0
        expected_dest = lib / "B" / "Beatles" / "[1966] Revolver"
        mock_move.assert_called_once_with(album, expected_dest)

    @patch("music_librarian.cli.move_album")
    def test_new_artist_folder_created(self, mock_move, tmp_path):
        volume, new, album, lib = self._make_new_dir(tmp_path)
        # Don't pre-create artist folder — shelve should create it

        with patch("music_librarian.cli.MUSIC_VOLUME", volume), \
             patch("music_librarian.cli.NEW_PATH", new), \
             patch("music_librarian.cli.LIBRARY_PATH", lib):
            result = runner.invoke(app, ["shelve", "Radiohead - [1997] OK Computer"])

        assert result.exit_code == 0
        assert (lib / "R" / "Radiohead").exists()
        assert "Created" in result.output

    def test_volume_not_mounted(self, tmp_path):
        volume = tmp_path / "volume"
        volume.mkdir()

        with patch("music_librarian.cli.MUSIC_VOLUME", volume):
            result = runner.invoke(app, ["shelve"])

        assert result.exit_code == 1
        assert "not mounted" in result.output
