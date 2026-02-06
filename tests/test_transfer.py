"""Tests for transfer.py rsync and move utilities."""

from pathlib import Path
from unittest.mock import patch, call

import pytest

from music_librarian.transfer import delete_source, move_album, rsync_album


class TestRsyncAlbum:
    @patch("music_librarian.transfer.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value.returncode = 0
        source = Path("/tmp/src/Artist - [2024] Album")
        dest = Path("/tmp/dest")

        result = rsync_album(source, dest)

        assert result is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "rsync" in cmd
        assert str(source) in cmd
        assert str(dest) + "/" in cmd

    @patch("music_librarian.transfer.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value.returncode = 1
        result = rsync_album(Path("/tmp/src"), Path("/tmp/dest"))
        assert result is False

    @patch("music_librarian.transfer.subprocess.run")
    def test_dry_run_flag(self, mock_run):
        mock_run.return_value.returncode = 0
        rsync_album(Path("/tmp/src"), Path("/tmp/dest"), dry_run=True)

        cmd = mock_run.call_args[0][0]
        assert "--dry-run" in cmd

    @patch("music_librarian.transfer.subprocess.run")
    def test_no_dry_run_flag_by_default(self, mock_run):
        mock_run.return_value.returncode = 0
        rsync_album(Path("/tmp/src"), Path("/tmp/dest"))

        cmd = mock_run.call_args[0][0]
        assert "--dry-run" not in cmd


class TestDeleteSource:
    @patch("music_librarian.transfer.shutil.rmtree")
    def test_calls_rmtree(self, mock_rmtree):
        source = Path("/tmp/src/album")
        delete_source(source)
        mock_rmtree.assert_called_once_with(source)


class TestMoveAlbum:
    @patch("music_librarian.transfer.shutil.move")
    def test_calls_shutil_move(self, mock_move):
        source = Path("/vol/new/Artist - [2024] Album")
        dest = Path("/vol/lib/A/Artist/[2024] Album")
        move_album(source, dest)
        mock_move.assert_called_once_with(str(source), str(dest))
