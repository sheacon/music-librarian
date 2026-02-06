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
music-librarian discover --artist "X"   # Find missing albums (fuzzy matching)
music-librarian discover --artist "X" -I # Interactive mode - download/ignore albums
music-librarian download <album_id>     # Download from Qobuz
music-librarian process <path>          # Post-process album(s) - supports bulk
music-librarian process -n <path>       # Dry run - preview changes
music-librarian stage                   # List/stage albums from Downloads to [New]
music-librarian stage -i 1              # Stage album by index
music-librarian stage -I                # Interactive mode - stage, play, or delete
music-librarian shelve                  # List/shelve albums from [New] to library
music-librarian shelve -i 1             # Shelve album by index
music-librarian shelve -I               # Interactive mode - shelve, play, or delete
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
- **library.py** - Local library scanning, parses folder structure `[Letter]/[Artist]/[Year] Album Title/`, fuzzy artist matching
- **config.py** - Default paths and environment variable handling (LASTFM_API_KEY, GENIUS_API_KEY)

### Supporting Modules

- **normalize.py** - Wraps rsgain for ReplayGain tagging
- **convert.py** - FFmpeg wrapper for FLAC→AAC conversion using macOS AudioToolbox
- **artwork.py** - Cover image embedding with automatic resizing (max 2MB)
- **lyrics.py** - Fetches from LRCLIB (primary) and Genius (fallback)
- **lastfm.py** - Genre lookup via Last.fm API for post-processing
- **ignore.py** - Manages ignore lists for artists/albums (persisted to ~/.config/music-librarian/ignore.json)
- **transfer.py** - Handles rsync transfers and file moves for staging/shelving workflow

### Key Data Flow

1. **Discovery**: `library.scan_library()` → `qobuz.search_artist()` → `qobuz.get_artist_albums()` → `qobuz._deduplicate_albums()`
2. **Download**: `qobuz.download_album()` calls qobuz-dl subprocess, then `qobuz.process_album()` for post-processing
3. **Post-processing** (`process_album`): metadata normalization → genre lookup → lyrics fetch → artwork embed → ReplayGain
4. **Graduation**: `stage` (Downloads → [New] via rsync) → `shelve` ([New] → library via move)

### Album Deduplication Logic (`qobuz._deduplicate_albums`)

When multiple editions exist (standard, deluxe, remaster), the tool:
- Groups by normalized title (strips edition markers)
- Finds standard edition (earliest year, fewest tracks)
- Finds hi-fi edition (highest bit depth, then sample rate)
- Merges: uses hi-fi audio with standard's year, removes bonus tracks after download

### Fuzzy Artist Matching (`library.find_matching_artist`)

The discover command uses fuzzy matching (via `rapidfuzz`) to find artists even with:
- Typos: "Radiohed" → "Radiohead"
- Accents: "Beyonce" → "Beyoncé"
- Word reordering: "Black Keys The" → "The Black Keys"
- Partial matches: "Beatles" → "The Beatles"
- Case differences: "RADIOHEAD" → "Radiohead"

If no match is found, suggests closest matches with "Did you mean:" prompt.

### Interactive Discover Mode

The `-I` / `--interactive` flag enables interactive album selection:
- Displays all albums with numbered indices
- Supports shorthand input: `2d` (download), `3i` (ignore), `1o` (open in Qobuz), `1-3i` (range)
- Downloads call `download_album()`, ignores call `add_ignored_album()`
- Open action launches album in Qobuz.app via URL
- Type `q` to quit

### Library Structure Expectations

```
/Volumes/music/Alphabetical/[Letter]/[Artist]/[Year] Album Title/
```

Artists with "The" prefix are stored without it (e.g., "The Beatles" → `B/Beatles/`). The `normalize_artist()` function handles this mapping.

## Environment Variables

API keys can be set in a `.env` file (copy from `.env.example`):

- `LASTFM_API_KEY` - Enables genre lookup during post-processing (optional)
- `GENIUS_API_KEY` - Enables Genius lyrics fallback (optional)

## Testing

All new features must include tests. After making changes, run the full test suite to verify both new and existing functionality:

```bash
pytest
```

Tests live in `tests/` and use pytest with class-based grouping, `tmp_path` fixtures, and `unittest.mock.patch` for isolating dependencies. Follow the patterns in existing test files when adding new tests.
