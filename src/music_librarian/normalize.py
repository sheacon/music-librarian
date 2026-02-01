"""Volume normalization using rsgain."""

import re
import subprocess
from pathlib import Path


def normalize_album(album_path: Path) -> dict | None:
    """Apply ReplayGain tags to an album using rsgain.

    Args:
        album_path: Path to album folder.

    Returns:
        Dict with album gain info, or None if failed.
    """
    if not album_path.exists():
        raise FileNotFoundError(f"Album path does not exist: {album_path}")

    if not album_path.is_dir():
        raise ValueError(f"Album path must be a directory: {album_path}")

    # Get all FLAC files in the album folder
    flac_files = list(album_path.glob("*.flac"))
    if not flac_files:
        return None

    # Use custom mode with album gain (-a) and write tags (-s i)
    cmd = ["rsgain", "custom", "-a", "-s", "i"] + [str(f) for f in flac_files]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return None

    # Parse album gain info from output
    output = result.stdout + result.stderr
    album_info = {}

    # Look for album section and extract values
    album_match = re.search(
        r"Album:\s*\n"
        r"\s*Loudness:\s*([-\d.]+)\s*LUFS\s*\n"
        r"\s*Peak:\s*([-\d.]+)\s*\(([-\d.]+)\s*dB\)\s*\n"
        r"\s*Gain:\s*([-\d.]+)\s*dB",
        output,
    )

    if album_match:
        album_info = {
            "loudness": float(album_match.group(1)),
            "peak": float(album_match.group(2)),
            "peak_db": float(album_match.group(3)),
            "gain": float(album_match.group(4)),
        }

    return album_info
