"""Configuration settings for music-librarian."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root if it exists
load_dotenv()

# Library paths
MUSIC_VOLUME = Path("/Volumes/music")
LIBRARY_PATH = Path("/Volumes/music/Alphabetical")
NEW_PATH = MUSIC_VOLUME / "[New]"
DOWNLOADS_PATH = Path.home() / "Downloads" / "music-downloads"
AAC_OUTPUT_PATH = DOWNLOADS_PATH / "transcoded"

# qobuz-dl config location
QOBUZ_CONFIG_PATH = Path.home() / ".config" / "qobuz-dl" / "config.ini"

# Last.fm API key (get one free at https://www.last.fm/api/account/create)
LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY", "")

# Genius API key (get one at https://genius.com/api-clients)
GENIUS_API_KEY = os.environ.get("GENIUS_API_KEY", "")
