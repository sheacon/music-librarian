"""Album artwork embedding functionality."""

import io
from pathlib import Path

from mutagen.flac import FLAC, Picture
from PIL import Image

# Maximum embedded image size in bytes (2 MB)
MAX_IMAGE_SIZE = 2 * 1024 * 1024

# Minimum image dimension to preserve usability
MIN_DIMENSION = 500

# Cover image filenames to search for, in priority order
COVER_FILENAMES = [
    "cover.jpg",
    "cover.png",
    "folder.jpg",
    "folder.png",
    "front.jpg",
    "front.png",
    "album.jpg",
    "album.png",
]


def find_cover_image(album_path: Path) -> Path | None:
    """Find cover image in album directory.

    Searches for common cover image filenames in priority order,
    with case-insensitive fallback.

    Args:
        album_path: Path to album directory.

    Returns:
        Path to cover image, or None if not found.
    """
    # Try exact matches first (case-sensitive)
    for filename in COVER_FILENAMES:
        cover_path = album_path / filename
        if cover_path.exists():
            return cover_path

    # Case-insensitive fallback
    files_lower = {f.name.lower(): f for f in album_path.iterdir() if f.is_file()}
    for filename in COVER_FILENAMES:
        if filename.lower() in files_lower:
            return files_lower[filename.lower()]

    return None


def resize_image_to_target(image_path: Path, max_size: int = MAX_IMAGE_SIZE) -> bytes:
    """Resize image to fit under max_size bytes.

    Strategy:
    1. Convert PNG to RGB for JPEG output
    2. Binary search JPEG quality 95→50 to find largest quality under max_size
    3. If quality 50 still too large: reduce dimensions by 10% and retry
    4. Minimum dimensions: 500px to preserve usability

    Args:
        image_path: Path to source image.
        max_size: Maximum size in bytes.

    Returns:
        JPEG image data as bytes.
    """
    img = Image.open(image_path)

    # Convert to RGB if necessary (for PNG with transparency)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    current_img = img
    while True:
        # Binary search for optimal JPEG quality
        low, high = 50, 95
        best_data = None

        while low <= high:
            mid = (low + high) // 2
            buffer = io.BytesIO()
            current_img.save(buffer, format="JPEG", quality=mid)
            data = buffer.getvalue()

            if len(data) <= max_size:
                best_data = data
                low = mid + 1  # Try higher quality
            else:
                high = mid - 1  # Try lower quality

        if best_data is not None:
            return best_data

        # Quality 50 still too large, reduce dimensions by 10%
        width, height = current_img.size
        new_width = int(width * 0.9)
        new_height = int(height * 0.9)

        # Check minimum dimensions
        if new_width < MIN_DIMENSION or new_height < MIN_DIMENSION:
            # Force minimum size and return whatever we get
            if width > height:
                new_width = MIN_DIMENSION
                new_height = int(height * (MIN_DIMENSION / width))
            else:
                new_height = MIN_DIMENSION
                new_width = int(width * (MIN_DIMENSION / height))
            current_img = current_img.resize((new_width, new_height), Image.LANCZOS)
            buffer = io.BytesIO()
            current_img.save(buffer, format="JPEG", quality=50)
            return buffer.getvalue()

        current_img = current_img.resize((new_width, new_height), Image.LANCZOS)


def get_image_data(image_path: Path, max_size: int = MAX_IMAGE_SIZE) -> tuple[bytes, str]:
    """Read image data, resizing if necessary.

    Args:
        image_path: Path to image file.
        max_size: Maximum size in bytes.

    Returns:
        Tuple of (image_data, mime_type).
    """
    # Read original file
    original_data = image_path.read_bytes()

    if len(original_data) <= max_size:
        # Determine MIME type from extension
        suffix = image_path.suffix.lower()
        if suffix == ".png":
            mime_type = "image/png"
        else:
            mime_type = "image/jpeg"
        return original_data, mime_type

    # Need to resize - always outputs JPEG
    resized_data = resize_image_to_target(image_path, max_size)
    return resized_data, "image/jpeg"


def embed_artwork_in_track(track_path: Path, image_data: bytes, mime_type: str) -> None:
    """Embed artwork in a FLAC track.

    Args:
        track_path: Path to FLAC file.
        image_data: Image data as bytes.
        mime_type: MIME type of image (image/jpeg or image/png).
    """
    audio = FLAC(track_path)

    # Create picture object
    picture = Picture()
    picture.type = 3  # Front cover
    picture.mime = mime_type
    picture.data = image_data

    # Get image dimensions for metadata
    img = Image.open(io.BytesIO(image_data))
    picture.width, picture.height = img.size
    picture.depth = 24  # Assume 24-bit color

    # Clear existing pictures and add new one
    audio.clear_pictures()
    audio.add_picture(picture)
    audio.save()


def embed_artwork(album_path: Path) -> dict:
    """Embed cover artwork in all FLAC files in an album.

    Args:
        album_path: Path to album directory.

    Returns:
        Dict with results:
        - cover_found: bool
        - cover_path: Path or None
        - original_size: int (bytes)
        - embedded_size: int (bytes)
        - was_resized: bool
        - tracks_processed: int
    """
    result = {
        "cover_found": False,
        "cover_path": None,
        "original_size": 0,
        "embedded_size": 0,
        "was_resized": False,
        "tracks_processed": 0,
    }

    # Find cover image
    cover_path = find_cover_image(album_path)
    if cover_path is None:
        return result

    result["cover_found"] = True
    result["cover_path"] = cover_path
    result["original_size"] = cover_path.stat().st_size

    # Get image data (with resizing if needed)
    image_data, mime_type = get_image_data(cover_path)
    result["embedded_size"] = len(image_data)
    result["was_resized"] = len(image_data) != result["original_size"]

    # Find and process all FLAC files
    flac_files = sorted(album_path.glob("*.flac"))
    for track_path in flac_files:
        embed_artwork_in_track(track_path, image_data, mime_type)
        result["tracks_processed"] += 1

    return result
