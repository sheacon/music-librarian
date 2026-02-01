# Music Librarian

A CLI tool to manage a high-fidelity music library with Qobuz integration. Discover new albums by artists in your collection, download them in the best available quality, normalize volume levels, and create portable AAC versions.

## Features

- **Library scanning** - Index your music collection organized by artist and album
- **Album discovery** - Find missing albums by artists already in your library via Qobuz
- **Popularity ranking** - Shows top 3 most popular missing albums (via Last.fm) when many exist
- **Smart deduplication** - Automatically selects the best version when multiple editions exist:
  - Prefers higher fidelity (bit depth, then sample rate)
  - Uses the original release year (not reissue year)
  - Downloads hi-fi deluxe editions but removes bonus tracks to match standard track listing
- **Downloading** - Download albums from Qobuz using qobuz-dl
- **Post-processing** - Normalize metadata, fetch genres/lyrics, embed artwork, apply ReplayGain
- **Bulk processing** - Process existing albums in bulk at any directory level
- **Volume normalization** - Apply ReplayGain tags using rsgain
- **Format conversion** - Create AAC 256kbps versions for portable devices

## Library Structure

The tool expects your music library to be organized as:

```
/Volumes/music/Alphabetical/[Letter]/[Artist]/[Year] Album Title/
```

Examples:
```
/Volumes/music/Alphabetical/B/Beatles/[1966] Revolver/
/Volumes/music/Alphabetical/P/Pink Floyd/[1973] The Dark Side of the Moon/
/Volumes/music/Alphabetical/T/Talking Heads/[1980] Remain in Light/
```

**Note:** Artists with "The" prefix are stored without it (e.g., "The Beatles" → `B/Beatles/`)

## Installation

### Prerequisites

- Python 3.10+
- [qobuz-dl](https://github.com/vitiko98/qobuz-dl) - for downloading from Qobuz
- [rsgain](https://github.com/complexlogic/rsgain) - for ReplayGain normalization
- [ffmpeg](https://ffmpeg.org/) with AudioToolbox (macOS) - for AAC conversion

```bash
# Install external dependencies (macOS)
brew install rsgain ffmpeg
pip install qobuz-dl

# Set up qobuz-dl credentials (run once)
qobuz-dl
```

### Install music-librarian

```bash
cd music-librarian
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

Always activate the virtual environment first:

```bash
source .venv/bin/activate
```

### Scan Library

List all artists and albums in your library:

```bash
music-librarian scan
```

```
                                 Music Library
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Artist        ┃ Albums                                                       ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Beatles       │ [1966] Revolver, [1967] Sgt. Pepper's Lonely Hearts Club Band│
│ Pink Floyd    │ [1973] The Dark Side of the Moon, [1979] The Wall            │
│ Talking Heads │ [1980] Remain in Light                                       │
└───────────────┴──────────────────────────────────────────────────────────────┘

Total: 3 artists
```

Use a custom library path:

```bash
music-librarian scan --path /path/to/music
```

### Discover New Albums

Find albums on Qobuz that aren't in your library:

```bash
# Check all artists
music-librarian discover

# Check a specific artist
music-librarian discover --artist "The Black Keys"

# Show all albums (not just top 3)
music-librarian discover --artist "The Black Keys" --all
```

```
Checking Black Keys...
  Found 7 new album(s):
    [2011] El Camino (24bit/44.1kHz)
      https://www.qobuz.com/album/0075597947786
    [2014] Turn Blue (24bit/44.1kHz)
      https://www.qobuz.com/album/0075597947946
    [2019] "Let's Rock" (24bit/48kHz)
      https://www.qobuz.com/album/i2l0ljm2ti0rb
    ...and 4 more (use --all to see all)
```

The discover command:
- Only shows full albums (excludes singles and EPs)
- Deduplicates editions (standard, deluxe, remaster) keeping the best fidelity
- Shows bit depth and sample rate for each album
- Uses the original release year even for remastered editions
- When more than 3 albums found, shows top 3 by popularity (requires Last.fm API key)
- Use `--all` to see complete list

### Download Albums

Download an album from Qobuz using the album ID (shown by `discover`):

```bash
music-librarian download 0075597947786
```

The download command automatically applies post-processing: metadata normalization, genre lookup, lyrics fetching, artwork embedding, and ReplayGain.

### Process Existing Albums

Apply post-processing to albums already in your library. Supports bulk processing at any directory level:

```bash
# Process a single album
music-librarian process "/Volumes/music/Alphabetical/B/Beatles/[1966] Revolver"

# Process all albums by an artist
music-librarian process "/Volumes/music/Alphabetical/B/Beatles"

# Process all albums for artists starting with B
music-librarian process "/Volumes/music/Alphabetical/B"

# Process entire library
music-librarian process "/Volumes/music/Alphabetical"
```

Post-processing includes:
- Metadata normalization (artist, album/track titles, edition markers)
- Genre lookup from Last.fm
- Lyrics fetching from LRCLIB and Genius
- Artwork embedding (with automatic resizing if needed)
- ReplayGain normalization

### Normalize Volume

Apply ReplayGain tags to an album for consistent playback volume:

```bash
music-librarian normalize "/Volumes/music/Alphabetical/B/Black Keys/[2011] El Camino"
```

### Convert to AAC

Create a portable AAC 256kbps version of an album:

```bash
# Default output location
music-librarian convert "/Volumes/music/Alphabetical/B/Black Keys/[2011] El Camino"

# Custom output directory
music-librarian convert "/Volumes/music/Alphabetical/B/Black Keys/[2011] El Camino" \
    --out ~/Music/Portable
```

Output is saved to `~/Downloads/qobuz-dl/transcoded/[Artist]/[Album]/` by default.

## Configuration

Default paths are defined in `src/music_librarian/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `LIBRARY_PATH` | `/Volumes/music/Alphabetical` | Root of your music library |
| `AAC_OUTPUT_PATH` | `~/Downloads/qobuz-dl/transcoded` | Where AAC conversions are saved |
| `QOBUZ_CONFIG_PATH` | `~/.config/qobuz-dl/config.ini` | qobuz-dl credentials |

### Last.fm API Key (Optional)

To rank albums by popularity, get a free API key from [Last.fm](https://www.last.fm/api/account/create) and set it:

```bash
export LASTFM_API_KEY="your_api_key_here"
```

Without an API key, albums are shown in chronological order.

## How Deduplication Works

When multiple editions of an album exist on Qobuz (standard, deluxe, remaster, etc.), the tool intelligently selects the best version:

1. **Groups by normalized title** - "Brothers", "Brothers (Deluxe)", and "Brothers (Remastered)" are treated as the same album
2. **Finds the standard edition** - The version with the earliest year and fewest tracks
3. **Finds the hi-fi edition** - The version with highest bit depth, then sample rate
4. **Merges if needed** - If the hi-fi version is a deluxe edition with bonus tracks:
   - Uses the hi-fi version's audio files
   - Uses the standard edition's release year for the folder name
   - After download, removes bonus tracks not present in the standard edition

### Example

For The Black Keys' "Brothers":
- Standard: 15 tracks, 24bit/44.1kHz (2010)
- Deluxe: 18 tracks, 24bit/48kHz (2010)

The tool will:
1. Download the 48kHz deluxe version (better sample rate)
2. Name the folder `[2010] Brothers`
3. Remove the 3 bonus tracks, leaving the original 15

## Command Reference

```
music-librarian scan [--path PATH]
    List all artists and albums in the library.

music-librarian discover [--artist NAME] [--path PATH] [--all]
    Find new albums by artists in the library.
    Shows top 3 by popularity; use --all for complete list.

music-librarian download ALBUM_ID
    Download an album from Qobuz and apply post-processing.

music-librarian process PATH
    Apply post-processing to existing album(s).
    Accepts album folder, artist folder, letter folder, or library root.

music-librarian normalize PATH
    Apply ReplayGain normalization to an album.

music-librarian convert PATH [--out PATH] [--artist NAME]
    Convert FLAC album to AAC 256kbps.

music-librarian embed-art PATH
    Embed cover artwork into FLAC files.

music-librarian ignore add ARTIST [ALBUM]
    Add artist or album to ignore list.

music-librarian ignore remove ARTIST [ALBUM]
    Remove artist or album from ignore list.

music-librarian ignore list
    Show all ignored artists and albums.
```

## Dependencies

- [typer](https://typer.tiangolo.com/) - CLI framework
- [httpx](https://www.python-httpx.org/) - HTTP client for Qobuz API
- [mutagen](https://mutagen.readthedocs.io/) - Audio metadata handling
- [rich](https://rich.readthedocs.io/) - Terminal formatting

## License

MIT
