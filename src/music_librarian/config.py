"""Configuration settings for music-librarian."""

import os
from pathlib import Path

# Library paths
LIBRARY_PATH = Path("/Volumes/music/Alphabetical")
AAC_OUTPUT_PATH = Path.home() / "Downloads" / "qobuz-dl" / "transcoded"

# qobuz-dl config location
QOBUZ_CONFIG_PATH = Path.home() / ".config" / "qobuz-dl" / "config.ini"

# Last.fm API key (get one free at https://www.last.fm/api/account/create)
LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY", "")
