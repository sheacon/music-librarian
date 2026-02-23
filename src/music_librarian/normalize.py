"""Volume normalization using rsgain."""

import re
import subprocess
from pathlib import Path


def has_replaygain_tags(album_path: Path) -> bool:
    """Check if all tracks in an album already have ReplayGain tags.

    Returns True if every FLAC file has both track and album gain tags.
    """
    from mutagen.flac import FLAC

    flac_files = list(album_path.glob("*.flac"))
    if not flac_files:
        return False

    for f in flac_files:
        audio = FLAC(f)
        if not audio.get("replaygain_track_gain") or not audio.get("replaygain_album_gain"):
            return False

    return True


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

    # Parse gain info from output
    output = result.stdout + result.stderr
    gain_info = {}

    # Count track-level gains
    track_matches = re.findall(
        r"Track:\s*.+\n"
        r"\s*Loudness:\s*[-\d.]+\s*LUFS\s*\n"
        r"\s*Peak:\s*[-\d.]+\s*\([-\d.]+\s*dB\)\s*\n"
        r"\s*Gain:\s*[-\d.]+\s*dB",
        output,
    )
    gain_info["tracks_count"] = len(track_matches)

    # Look for album section and extract values
    album_match = re.search(
        r"Album:\s*\n"
        r"\s*Loudness:\s*([-\d.]+)\s*LUFS\s*\n"
        r"\s*Peak:\s*([-\d.]+)\s*\(([-\d.]+)\s*dB\)\s*\n"
        r"\s*Gain:\s*([-\d.]+)\s*dB",
        output,
    )

    if album_match:
        gain_info["loudness"] = float(album_match.group(1))
        gain_info["peak"] = float(album_match.group(2))
        gain_info["peak_db"] = float(album_match.group(3))
        gain_info["gain"] = float(album_match.group(4))

    return gain_info
