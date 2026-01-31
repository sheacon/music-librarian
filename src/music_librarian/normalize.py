"""Volume normalization using rsgain."""

import subprocess
from pathlib import Path


def normalize_album(album_path: Path) -> bool:
    """Apply ReplayGain tags to an album using rsgain.

    Args:
        album_path: Path to album folder.

    Returns:
        True if successful, False otherwise.
    """
    if not album_path.exists():
        raise FileNotFoundError(f"Album path does not exist: {album_path}")

    if not album_path.is_dir():
        raise ValueError(f"Album path must be a directory: {album_path}")

    result = subprocess.run(["rsgain", "easy", str(album_path)])

    return result.returncode == 0
