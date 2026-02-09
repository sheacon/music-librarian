"""Tests for normalize.py subprocess wrapper."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_librarian.normalize import has_replaygain_tags, normalize_album


class TestNormalizeAlbum:
    def test_raises_on_missing_path(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            normalize_album(tmp_path / "nonexistent")

    def test_raises_on_file_not_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        with pytest.raises(ValueError, match="must be a directory"):
            normalize_album(f)

    def test_returns_none_when_no_flac_files(self, tmp_path):
        album = tmp_path / "album"
        album.mkdir()
        assert normalize_album(album) is None

    @patch("music_librarian.normalize.subprocess.run")
    def test_parses_rsgain_output(self, mock_run, tmp_path):
        album = tmp_path / "album"
        album.mkdir()
        (album / "01.flac").touch()
        (album / "02.flac").touch()

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "Track 1:\n"
                "  Loudness:   -14.50 LUFS\n"
                "  Peak:     0.950000 (-0.45 dB)\n"
                "  Gain:       3.50 dB\n"
                "\n"
                "Album:\n"
                "  Loudness:   -15.20 LUFS\n"
                "  Peak:     0.980000 (-0.18 dB)\n"
                "  Gain:       2.80 dB\n"
            ),
            stderr="",
        )

        result = normalize_album(album)
        assert result is not None
        assert result["loudness"] == pytest.approx(-15.20)
        assert result["peak"] == pytest.approx(0.98)
        assert result["peak_db"] == pytest.approx(-0.18)
        assert result["gain"] == pytest.approx(2.80)

    @patch("music_librarian.normalize.subprocess.run")
    def test_returns_none_on_rsgain_failure(self, mock_run, tmp_path):
        album = tmp_path / "album"
        album.mkdir()
        (album / "01.flac").touch()

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        result = normalize_album(album)
        assert result is None

    @patch("music_librarian.normalize.subprocess.run")
    def test_returns_empty_dict_on_unparseable_output(self, mock_run, tmp_path):
        album = tmp_path / "album"
        album.mkdir()
        (album / "01.flac").touch()

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="some unrelated output",
            stderr="",
        )

        result = normalize_album(album)
        assert result == {}

    @patch("music_librarian.normalize.subprocess.run")
    def test_calls_rsgain_with_correct_args(self, mock_run, tmp_path):
        album = tmp_path / "album"
        album.mkdir()
        (album / "track.flac").touch()

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        normalize_album(album)
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "rsgain"
        assert "custom" in call_args
        assert "-a" in call_args
        assert "-s" in call_args
        assert "i" in call_args


class TestHasReplaygainTags:
    def _make_mock_flac(self, has_track=True, has_album=True):
        mock = MagicMock()
        tags = {}
        if has_track:
            tags["replaygain_track_gain"] = ["-3.5 dB"]
        if has_album:
            tags["replaygain_album_gain"] = ["-2.8 dB"]
        mock.get = lambda key, default=None: tags.get(key, default)
        return mock

    @patch("mutagen.flac.FLAC")
    def test_all_tagged_returns_true(self, mock_flac_cls, tmp_path):
        mock_flac_cls.return_value = self._make_mock_flac()
        (tmp_path / "01.flac").touch()
        (tmp_path / "02.flac").touch()
        assert has_replaygain_tags(tmp_path) is True

    @patch("mutagen.flac.FLAC")
    def test_missing_track_gain_returns_false(self, mock_flac_cls, tmp_path):
        mock_flac_cls.return_value = self._make_mock_flac(has_track=False)
        (tmp_path / "01.flac").touch()
        assert has_replaygain_tags(tmp_path) is False

    @patch("mutagen.flac.FLAC")
    def test_missing_album_gain_returns_false(self, mock_flac_cls, tmp_path):
        mock_flac_cls.return_value = self._make_mock_flac(has_album=False)
        (tmp_path / "01.flac").touch()
        assert has_replaygain_tags(tmp_path) is False

    def test_no_flac_files_returns_false(self, tmp_path):
        assert has_replaygain_tags(tmp_path) is False
