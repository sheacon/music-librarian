# Music Librarian

A CLI tool to manage a high-fidelity music library with Qobuz integration. Discover new albums by artists in your collection, download them in the best available quality, normalize volume levels, and create portable AAC versions.

## Features

- **Library scanning** - Index your music collection organized by artist and album
- **Album discovery** - Find missing albums by artists already in your library via Qobuz
- **Fuzzy matching** - Find artists even with typos, accents, or alternate spellings ("Radiohed" → "Radiohead", "Beyonce" → "Beyoncé")
- **Interactive mode** - Browse discovered albums and download, ignore, or open in Qobuz directly
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

# Check a specific artist (fuzzy matching handles typos/accents)
music-librarian discover --artist "Radiohed"    # matches "Radiohead"
music-librarian discover --artist "Beyonce"     # matches "Beyoncé"

# Show all albums (not just top 3)
music-librarian discover --artist "The Black Keys" --all

# Interactive mode - download, ignore, or open albums directly
music-librarian discover --artist "Radiohead" -I
```

```
Checking Black Keys...
  Found 7 new album(s):
    [2011] El Camino (24bit/44.1kHz) id:0075597947786
    [2014] Turn Blue (24bit/44.1kHz) id:0075597947946
    [2019] "Let's Rock" (24bit/48kHz) id:i2l0ljm2ti0rb
    ...and 4 more (use --all to see all)
```

The discover command:
- Only shows full albums (excludes singles and EPs)
- Deduplicates editions (standard, deluxe, remaster) keeping the best fidelity
- Shows bit depth and sample rate for each album
- Uses the original release year even for remastered editions
- When more than 3 albums found, shows top 3 by Qobuz popularity
- Use `--all` to see complete list
- Fuzzy matches artist names (typos, accents, word order, partial matches)
- Suggests similar artists if no match found ("Did you mean:")

#### Interactive Mode

Use `-I` / `--interactive` to browse and act on discovered albums:

```
Albums for Radiohead (5):
  1. [1995] The Bends (24bit/96kHz)
  2. [1997] OK Computer (24bit/96kHz)
  3. [2000] Kid A (24bit/44.1kHz)

Enter: number + action (e.g., '2d' download, '3i' ignore, '1o' open in Qobuz), or 'q' to quit
> 2d

Downloading: [1997] OK Computer...
```

Actions:
- `2d` - Download album 2
- `3i` - Ignore album 3 (won't show in future discovers)
- `1o` - Open album 1 in Qobuz app
- `1-3i` - Ignore albums 1, 2, and 3 (range)
- `q` - Quit interactive mode

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

# Preview changes without applying them
music-librarian process --dry-run "/Volumes/music/Alphabetical"
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

### Album Graduation Workflow

New albums go through a staging process before being added to the permanent library:

1. **Downloads** → Albums are downloaded to `~/Downloads/qobuz-dl/`
2. **[New]** → Albums are staged to a `[New]` folder on the NAS for review
3. **Library** → Albums are shelved to their permanent alphabetical location

#### Stage Albums

Move albums from local Downloads to `[New]` on the NAS:

```bash
# List albums in Downloads
music-librarian stage

# Interactive mode - stage, play, or delete albums
music-librarian stage -I

# Preview album in Cog player before staging
music-librarian stage -p 1

# Stage by index (shown in list)
music-librarian stage -i 1

# Stage by folder name
music-librarian stage "Radiohead - [1997] OK Computer"

# Dry run to preview the transfer
music-librarian stage -i 1 -n
```

#### Shelve Albums

Move albums from `[New]` to their permanent library location:

```bash
# List albums in [New] (shows destination paths)
music-librarian shelve

# Interactive mode - shelve, play, or delete albums
music-librarian shelve -I

# Preview album in Cog before shelving
music-librarian shelve -p 1

# Shelve by index
music-librarian shelve -i 1

# Shelve by folder name
music-librarian shelve "Radiohead - [1997] OK Computer"

# Dry run to preview the move
music-librarian shelve -i 1 -n
```

#### Interactive Mode

Both `stage` and `shelve` support interactive mode (`-I`):

```
Albums in Downloads (3):
  1. Radiohead - [1997] OK Computer
  2. The Beatles - [1966] Revolver
  3. Pink Floyd - [1973] The Dark Side of the Moon

Enter: number + action (e.g., '1s' stage, '2p' play, '3x' delete), or 'q' to quit
> 1s

Staging: Radiohead - [1997] OK Computer
Staged successfully!
```

Actions:
- `1s` - Stage/shelve album 1
- `2p` - Play album 2 in Cog
- `3x` - Delete album 3
- `q` - Quit interactive mode

The shelve command automatically determines the correct library location based on the folder name format `{Artist} - [{YYYY}] {Album Title}`.

## Configuration

Default paths are defined in `src/music_librarian/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `LIBRARY_PATH` | `/Volumes/music/Alphabetical` | Root of your music library |
| `AAC_OUTPUT_PATH` | `~/Downloads/qobuz-dl/transcoded` | Where AAC conversions are saved |
| `QOBUZ_CONFIG_PATH` | `~/.config/qobuz-dl/config.ini` | qobuz-dl credentials |

### API Keys (Optional)

Copy `.env.example` to `.env` and add your API keys:

```bash
cp .env.example .env
```

| Key | Purpose | Get one at |
|-----|---------|------------|
| `LASTFM_API_KEY` | Genre lookup during post-processing | [Last.fm](https://www.last.fm/api/account/create) |
| `GENIUS_API_KEY` | Lyrics fallback when LRCLIB fails | [Genius](https://genius.com/api-clients) |

Without these keys, the respective features will be skipped.

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

music-librarian discover [--artist NAME] [--path PATH] [--all] [--interactive]
    Find new albums by artists in the library.
    Shows top 3 by popularity; use --all for complete list.
    Use -I/--interactive to download, ignore, or open albums directly.
    Fuzzy matches artist names (typos, accents, partial matches).

music-librarian download ALBUM_ID
    Download an album from Qobuz and apply post-processing.

music-librarian process PATH [--dry-run]
    Apply post-processing to existing album(s).
    Accepts album folder, artist folder, letter folder, or library root.
    Use --dry-run (-n) to preview changes without applying them.

music-librarian stage [NAME] [--index N] [--play N] [--dry-run] [--interactive]
    Stage an album from Downloads to [New] on the NAS.
    Use -i/--index to select by list position.
    Use -p/--play to preview in Cog before staging.
    Use -I/--interactive for interactive mode (stage, play, delete).

music-librarian shelve [NAME] [--index N] [--play N] [--dry-run] [--interactive]
    Move an album from [New] to its permanent library location.
    Use -i/--index to select by list position.
    Use -p/--play to preview in Cog before shelving.
    Use -I/--interactive for interactive mode (shelve, play, delete).

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
- [rapidfuzz](https://github.com/rapidfuzz/RapidFuzz) - Fuzzy string matching

## License

MIT
