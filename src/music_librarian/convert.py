"""Format conversion to AAC using ffmpeg."""

import shutil
import subprocess
from pathlib import Path

from .config import AAC_OUTPUT_PATH


def convert_album_to_aac(
    album_path: Path,
    output_base: Path | None = None,
    artist_name: str | None = None,
) -> Path:
    """Convert FLAC album to AAC 256kbps.

    Uses macOS AudioToolbox encoder (aac_at) with VBR quality 2.

    Args:
        album_path: Path to album folder containing FLAC files.
        output_base: Base output directory. Defaults to AAC_OUTPUT_PATH.
        artist_name: Artist name for output folder. If None, uses parent folder name.

    Returns:
        Path to output folder.
    """
    if not album_path.exists():
        raise FileNotFoundError(f"Album path does not exist: {album_path}")

    if not album_path.is_dir():
        raise ValueError(f"Album path must be a directory: {album_path}")

    if output_base is None:
        output_base = AAC_OUTPUT_PATH

    # Determine artist name from path if not provided
    if artist_name is None:
        artist_name = album_path.parent.name

    album_name = album_path.name
    output_path = output_base / artist_name / album_name
    output_path.mkdir(parents=True, exist_ok=True)

    # Find all FLAC files
    flac_files = list(album_path.glob("*.flac"))
    if not flac_files:
        raise ValueError(f"No FLAC files found in {album_path}")

    # Convert each FLAC file
    for flac_file in flac_files:
        output_file = output_path / (flac_file.stem + ".m4a")

        subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(flac_file),
                "-c:a",
                "aac_at",
                "-q:a",
                "2",
                "-movflags",
                "+faststart",
                "-y",  # Overwrite output
                str(output_file),
            ],
            capture_output=True,
            check=True,
        )

    # Copy cover art if present
    for cover_name in ["cover.jpg", "cover.png", "folder.jpg", "folder.png"]:
        cover_file = album_path / cover_name
        if cover_file.exists():
            shutil.copy2(cover_file, output_path / cover_name)
            break

    return output_path
