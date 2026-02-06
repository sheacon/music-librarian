"""Album transfer utilities using rsync and filesystem moves."""

import shutil
import subprocess
from pathlib import Path


def rsync_album(source: Path, dest: Path, dry_run: bool = False) -> bool:
    """Transfer an album directory using rsync.

    Uses archive mode with progress output. Suitable for cross-filesystem
    transfers (e.g., local SSD to network drive).

    Args:
        source: Source album directory.
        dest: Destination parent directory (rsync will place source into it).
        dry_run: If True, only simulate the transfer.

    Returns:
        True if rsync succeeded.
    """
    cmd = [
        "rsync",
        "-avh",
        "--progress",
        "--whole-file",
    ]

    if dry_run:
        cmd.append("--dry-run")

    # No trailing slash on source: transfers the directory itself
    cmd.append(str(source))
    cmd.append(str(dest) + "/")

    result = subprocess.run(cmd)
    return result.returncode == 0


def delete_source(source: Path) -> None:
    """Delete a source directory after confirmed transfer."""
    shutil.rmtree(source)


def move_album(source: Path, dest: Path) -> None:
    """Move an album directory to a new location.

    Uses shutil.move for same-filesystem moves (e.g., within a NAS volume).

    Args:
        source: Source album directory.
        dest: Full destination path for the album.
    """
    shutil.move(str(source), str(dest))
