"""Tests for artwork.py image processing."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from music_librarian.artwork import (
    COVER_FILENAMES,
    MAX_IMAGE_SIZE,
    MIN_DIMENSION,
    find_cover_image,
    get_image_data,
    resize_image_to_target,
)


def _create_test_image(path: Path, width=100, height=100, fmt="JPEG", size_bytes=None):
    """Create a test image at the given path."""
    img = Image.new("RGB", (width, height), color="red")
    if size_bytes and fmt == "JPEG":
        # Create a larger image by adding noise-like data
        import random
        pixels = img.load()
        for x in range(width):
            for y in range(height):
                pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    img.save(path, format=fmt)
    return path


def _create_large_image(path: Path, target_size: int):
    """Create an image file that exceeds target_size bytes."""
    # Create a large noisy image to ensure file size exceeds target
    width = 4000
    height = 4000
    img = Image.new("RGB", (width, height))
    import random
    pixels = img.load()
    for x in range(width):
        for y in range(height):
            pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    img.save(path, format="JPEG", quality=100)
    # If still not large enough, try PNG
    if path.stat().st_size < target_size:
        img.save(path, format="PNG")
    return path


# --- find_cover_image ---


class TestFindCoverImage:
    def test_finds_cover_jpg(self, tmp_path):
        cover = tmp_path / "cover.jpg"
        cover.touch()
        assert find_cover_image(tmp_path) == cover

    def test_finds_cover_png(self, tmp_path):
        cover = tmp_path / "cover.png"
        cover.touch()
        assert find_cover_image(tmp_path) == cover

    def test_priority_order(self, tmp_path):
        # cover.jpg should take priority over folder.jpg
        (tmp_path / "folder.jpg").touch()
        (tmp_path / "cover.jpg").touch()
        assert find_cover_image(tmp_path).name == "cover.jpg"

    def test_case_insensitive_fallback(self, tmp_path):
        cover = tmp_path / "Cover.JPG"
        cover.touch()
        result = find_cover_image(tmp_path)
        assert result is not None
        # On case-insensitive filesystems (macOS), exact match may find it first
        assert result.name.lower() == "cover.jpg"

    def test_no_cover_returns_none(self, tmp_path):
        (tmp_path / "track.flac").touch()
        assert find_cover_image(tmp_path) is None

    def test_all_supported_filenames(self, tmp_path):
        for filename in COVER_FILENAMES:
            cover = tmp_path / filename
            cover.touch()
            result = find_cover_image(tmp_path)
            assert result is not None
            cover.unlink()


# --- get_image_data ---


class TestGetImageData:
    def test_small_image_returned_as_is(self, tmp_path):
        cover = tmp_path / "cover.jpg"
        _create_test_image(cover, 100, 100)
        data, mime = get_image_data(cover)
        assert mime == "image/jpeg"
        assert len(data) == cover.stat().st_size

    def test_png_returns_png_mime(self, tmp_path):
        cover = tmp_path / "cover.png"
        _create_test_image(cover, 100, 100, fmt="PNG")
        data, mime = get_image_data(cover)
        assert mime == "image/png"

    def test_large_image_resized(self, tmp_path):
        cover = tmp_path / "cover.jpg"
        _create_large_image(cover, MAX_IMAGE_SIZE + 1)
        if cover.stat().st_size <= MAX_IMAGE_SIZE:
            pytest.skip("Could not create large enough test image")
        data, mime = get_image_data(cover)
        assert len(data) <= MAX_IMAGE_SIZE
        assert mime == "image/jpeg"


# --- resize_image_to_target ---


class TestResizeImageToTarget:
    def test_output_under_target_size(self, tmp_path):
        cover = tmp_path / "cover.jpg"
        _create_large_image(cover, MAX_IMAGE_SIZE + 1)
        if cover.stat().st_size <= MAX_IMAGE_SIZE:
            pytest.skip("Could not create large enough test image")
        data = resize_image_to_target(cover, MAX_IMAGE_SIZE)
        assert len(data) <= MAX_IMAGE_SIZE

    def test_output_is_valid_jpeg(self, tmp_path):
        cover = tmp_path / "cover.jpg"
        _create_test_image(cover, 1000, 1000)
        data = resize_image_to_target(cover, 50_000)  # Small target
        img = Image.open(io.BytesIO(data))
        assert img.format == "JPEG"

    def test_rgba_converted_to_rgb(self, tmp_path):
        cover = tmp_path / "cover.png"
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        img.save(cover, format="PNG")
        data = resize_image_to_target(cover, MAX_IMAGE_SIZE)
        result = Image.open(io.BytesIO(data))
        assert result.mode == "RGB"

    def test_respects_min_dimension(self, tmp_path):
        cover = tmp_path / "cover.jpg"
        # Create a moderately sized image and request very small output
        _create_test_image(cover, 600, 600)
        data = resize_image_to_target(cover, 100)  # Very small target
        result = Image.open(io.BytesIO(data))
        # Should respect MIN_DIMENSION (500px)
        assert result.width >= MIN_DIMENSION or result.height >= MIN_DIMENSION
