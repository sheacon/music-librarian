# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Music Librarian is a CLI tool for managing a high-fidelity music library with Qobuz integration. It discovers missing albums, downloads them via qobuz-dl, normalizes volume levels, fetches lyrics, and creates portable AAC versions.

## Commands

```bash
# Install for development
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Run the CLI
music-librarian scan                    # List library contents
music-librarian discover --artist "X"   # Find missing albums
music-librarian download <album_id>     # Download from Qobuz
music-librarian process <path>          # Post-process album(s) - supports bulk
music-librarian process -n <path>       # Dry run - preview changes
music-librarian normalize <path>        # Apply ReplayGain tags
music-librarian convert <path>          # Convert to AAC

# External tools required
# qobuz-dl - downloading (pip install qobuz-dl)
# rsgain - ReplayGain normalization (brew install rsgain)
# ffmpeg with AudioToolbox - AAC conversion (brew install ffmpeg)
```

## Architecture

### Module Structure (`src/music_librarian/`)

- **cli.py** - Typer-based CLI entry point, defines all commands
- **qobuz.py** - Core Qobuz integration: API calls, album deduplication, download orchestration, post-processing pipeline
- **library.py** - Local library scanning, parses folder structure `[Letter]/[Artist]/[Year] Album Title/`
- **config.py** - Default paths and environment variable handling (LASTFM_API_KEY, GENIUS_API_KEY)

### Supporting Modules

- **normalize.py** - Wraps rsgain for ReplayGain tagging
- **convert.py** - FFmpeg wrapper for FLAC→AAC conversion using macOS AudioToolbox
- **artwork.py** - Cover image embedding with automatic resizing (max 2MB)
- **lyrics.py** - Fetches from LRCLIB (primary) and Genius (fallback)
- **lastfm.py** - Album popularity ranking and genre lookup for discovery results
- **ignore.py** - Manages ignore lists for artists/albums (persisted to ~/.config/music-librarian/ignore.json)

### Key Data Flow

1. **Discovery**: `library.scan_library()` → `qobuz.search_artist()` → `qobuz.get_artist_albums()` → `qobuz._deduplicate_albums()`
2. **Download**: `qobuz.download_album()` calls qobuz-dl subprocess, then `qobuz.process_album()` for post-processing
3. **Post-processing** (`process_album`): metadata normalization → genre lookup → lyrics fetch → artwork embed → ReplayGain

### Album Deduplication Logic (`qobuz._deduplicate_albums`)

When multiple editions exist (standard, deluxe, remaster), the tool:
- Groups by normalized title (strips edition markers)
- Finds standard edition (earliest year, fewest tracks)
- Finds hi-fi edition (highest bit depth, then sample rate)
- Merges: uses hi-fi audio with standard's year, removes bonus tracks after download

### Library Structure Expectations

```
/Volumes/music/Alphabetical/[Letter]/[Artist]/[Year] Album Title/
```

Artists with "The" prefix are stored without it (e.g., "The Beatles" → `B/Beatles/`). The `normalize_artist()` function handles this mapping.

## Environment Variables

- `LASTFM_API_KEY` - Enables popularity ranking in discovery (optional)
- `GENIUS_API_KEY` - Enables Genius lyrics fallback (optional)
