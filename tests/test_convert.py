"""Tests for convert.py subprocess wrapper."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from music_librarian.convert import convert_album_to_aac


class TestConvertAlbumToAac:
    def test_raises_on_missing_path(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            convert_album_to_aac(tmp_path / "nonexistent", output_base=tmp_path)

    def test_raises_on_file_not_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        with pytest.raises(ValueError, match="must be a directory"):
            convert_album_to_aac(f, output_base=tmp_path)

    def test_raises_on_no_flac_files(self, tmp_path):
        album = tmp_path / "album"
        album.mkdir()
        with pytest.raises(ValueError, match="No FLAC files"):
            convert_album_to_aac(album, output_base=tmp_path)

    @patch("music_librarian.convert.subprocess.run")
    def test_converts_flac_to_m4a(self, mock_run, tmp_path):
        album = tmp_path / "input" / "[2020] Album"
        album.mkdir(parents=True)
        (album / "01 - Track.flac").touch()
        (album / "02 - Track.flac").touch()

        mock_run.return_value = MagicMock(returncode=0)

        output = convert_album_to_aac(album, output_base=tmp_path / "output", artist_name="Artist")

        assert mock_run.call_count == 2
        assert output == tmp_path / "output" / "Artist" / "[2020] Album"

    @patch("music_librarian.convert.subprocess.run")
    def test_uses_parent_as_artist_name(self, mock_run, tmp_path):
        artist_dir = tmp_path / "input" / "Beatles"
        album = artist_dir / "[1969] Abbey Road"
        album.mkdir(parents=True)
        (album / "01.flac").touch()

        mock_run.return_value = MagicMock(returncode=0)

        output = convert_album_to_aac(album, output_base=tmp_path / "output")
        assert output.parent.name == "Beatles"

    @patch("music_librarian.convert.subprocess.run")
    def test_ffmpeg_args_correct(self, mock_run, tmp_path):
        album = tmp_path / "album"
        album.mkdir()
        (album / "track.flac").touch()

        mock_run.return_value = MagicMock(returncode=0)

        convert_album_to_aac(album, output_base=tmp_path / "output", artist_name="A")

        args = mock_run.call_args[0][0]
        assert args[0] == "ffmpeg"
        assert "-c:a" in args
        assert "aac_at" in args
        assert "-q:a" in args
        assert "2" in args

    @patch("music_librarian.convert.subprocess.run")
    @patch("music_librarian.convert.shutil.copy2")
    def test_copies_cover_art(self, mock_copy, mock_run, tmp_path):
        album = tmp_path / "album"
        album.mkdir()
        (album / "track.flac").touch()
        (album / "cover.jpg").touch()

        mock_run.return_value = MagicMock(returncode=0)

        output = convert_album_to_aac(album, output_base=tmp_path / "output", artist_name="A")

        mock_copy.assert_called_once()
        src = mock_copy.call_args[0][0]
        assert src.name == "cover.jpg"

    @patch("music_librarian.convert.subprocess.run")
    def test_creates_output_dirs(self, mock_run, tmp_path):
        album = tmp_path / "album"
        album.mkdir()
        (album / "track.flac").touch()

        mock_run.return_value = MagicMock(returncode=0)

        output = convert_album_to_aac(
            album, output_base=tmp_path / "out" / "deep", artist_name="A"
        )
        assert output.parent.exists()
