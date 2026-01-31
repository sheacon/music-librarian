"""Configuration settings for music-librarian."""

from pathlib import Path

# Library paths
LIBRARY_PATH = Path("/Volumes/music/Alphabetical")
AAC_OUTPUT_PATH = Path.home() / "Downloads" / "qobuz-dl" / "transcoded"

# qobuz-dl config location
QOBUZ_CONFIG_PATH = Path.home() / ".config" / "qobuz-dl" / "config.ini"
