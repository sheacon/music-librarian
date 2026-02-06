"""CLI entry point using Typer."""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from .artwork import embed_artwork
from .config import DOWNLOADS_PATH, LASTFM_API_KEY, LIBRARY_PATH, MUSIC_VOLUME, NEW_PATH
from .convert import convert_album_to_aac
from .ignore import (
    add_ignored_album,
    add_ignored_artist,
    get_ignored_albums,
    get_ignored_artists,
    is_album_ignored_with_variants,
    remove_ignored_album,
    remove_ignored_artist,
)
from .lastfm import rank_albums_by_popularity
from .library import (
    check_volume_mounted,
    find_matching_artist,
    get_artist_path,
    normalize_artist,
    parse_album_folder,
    parse_new_folder,
    scan_library,
)
from .transfer import delete_source, move_album, rsync_album
from .normalize import normalize_album
from .qobuz import (
    QobuzAlbum,
    _normalize_album_title,
    discover_missing_albums,
    download_album,
    preview_album_processing,
    process_album,
)

app = typer.Typer(
    name="music-librarian",
    help="CLI tool to manage a music library with Qobuz integration.",
)
ignore_app = typer.Typer(help="Manage ignored artists and albums.")
app.add_typer(ignore_app, name="ignore")

console = Console()


def find_album_directories(path: Path) -> list[Path]:
    """Find all album directories under a path.

    An album directory is identified by the naming pattern '[YYYY] Album Title'.
    If the given path itself is an album directory, returns just that path.
    Otherwise, recursively searches for album directories.

    Args:
        path: Starting path to search from.

    Returns:
        List of album directory paths, sorted alphabetically.
    """
    # Check if path itself is an album directory
    if parse_album_folder(path.name):
        return [path]

    # Recursively find album directories
    albums = []
    for item in sorted(path.iterdir()):
        if item.is_dir():
            if parse_album_folder(item.name):
                albums.append(item)
            else:
                # Recurse into subdirectories (letter folders, artist folders)
                albums.extend(find_album_directories(item))

    return albums


@app.command()
def scan(
    library_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Path to music library"),
    ] = None,
) -> None:
    """List all artists and albums in the library."""
    path = library_path or LIBRARY_PATH

    if not path.exists():
        console.print(f"[red]Library path does not exist: {path}[/red]")
        raise typer.Exit(1)

    artists = scan_library(path)

    if not artists:
        console.print("[yellow]No artists found in library.[/yellow]")
        return

    table = Table(title="Music Library")
    table.add_column("Artist", style="cyan")
    table.add_column("Albums", style="green")

    for artist in sorted(artists.values(), key=lambda a: a.name.lower()):
        album_list = ", ".join(
            f"[{a.year}] {a.title}" for a in sorted(artist.albums, key=lambda x: x.year)
        )
        table.add_row(artist.canonical_name, album_list)

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] {len(artists)} artists")


def _open_in_qobuz(album_id: str) -> None:
    """Open an album in the Qobuz app."""
    import subprocess

    url = f"https://open.qobuz.com/album/{album_id}"
    subprocess.Popen(["open", url])


def _parse_interactive_input(choice: str, max_idx: int) -> list[tuple[int, str]]:
    """Parse interactive discover input.

    Supports:
    - Single index: "2" (select), "2d" (download), "2i" (ignore), "2o" (open), "2s" (skip)
    - Range: "1-3d" (download 1, 2, 3), "1-3i" (ignore 1, 2, 3)
    - Action only: "d", "i", "o", "s", "q"

    Returns list of (index, action) tuples. Index is 0 for action-only commands.
    """
    choice = choice.strip().lower()

    if not choice:
        return []

    if choice == "q":
        return [(0, "q")]

    # Parse range with action: "1-3d" or "1-3 d"
    import re
    range_match = re.match(r"(\d+)\s*-\s*(\d+)\s*([dios])?", choice)
    if range_match:
        start, end, action = range_match.groups()
        start_idx, end_idx = int(start), int(end)
        if start_idx < 1 or end_idx > max_idx or start_idx > end_idx:
            return []
        action = action or "s"  # Default to select/skip
        return [(i, action) for i in range(start_idx, end_idx + 1)]

    # Parse single index with optional action: "2", "2d", "2 d"
    single_match = re.match(r"(\d+)\s*([dios])?", choice)
    if single_match:
        idx, action = single_match.groups()
        idx = int(idx)
        if idx < 1 or idx > max_idx:
            return []
        action = action or "s"  # Default to select/skip
        return [(idx, action)]

    return []


def _interactive_discover(
    artist_name: str,
    canonical_name: str,
    albums: list[QobuzAlbum],
    cons: Console,
) -> None:
    """Interactive album selection for discover command."""
    # Sort by year for display
    albums = sorted(albums, key=lambda x: x.year)

    while albums:
        # Display numbered list
        cons.print(f"\n[bold]Albums for {canonical_name} ({len(albums)}):[/bold]")
        for i, album in enumerate(albums, 1):
            fidelity = f"{album.bit_depth}bit/{album.sample_rate}kHz"
            if album.standard_id:
                cons.print(
                    f"  [bold]{i}.[/bold] [{album.year}] {album.title} "
                    f"[magenta]({fidelity}, {album.standard_track_count} tracks)[/magenta]"
                )
            else:
                cons.print(
                    f"  [bold]{i}.[/bold] [{album.year}] {album.title} [dim]({fidelity})[/dim]"
                )

        cons.print(
            "\n[dim]Enter: number + action (e.g., '2d' download, '3i' ignore, '1o' open in Qobuz), "
            "or 'q' to quit[/dim]"
        )

        # Get input
        try:
            choice = Prompt.ask(">")
        except (KeyboardInterrupt, EOFError):
            break

        parsed = _parse_interactive_input(choice, len(albums))
        if not parsed:
            cons.print("[yellow]Invalid input. Try again.[/yellow]")
            continue

        # Check for quit
        if parsed[0][1] == "q":
            break

        # Process actions in reverse order (so indices remain valid after removal)
        removed_indices = set()
        for idx, action in sorted(parsed, key=lambda x: -x[0]):
            album = albums[idx - 1]

            if action == "d":
                # Download
                cons.print(f"\n[cyan]Downloading: [{album.year}] {album.title}[/cyan]")
                try:
                    url = f"https://open.qobuz.com/album/{album.id}"
                    success, album_path = download_album(url)
                    if success:
                        cons.print("[green]Download complete![/green]")
                        if album_path:
                            cons.print(f"  Location: {album_path}")
                        removed_indices.add(idx - 1)
                    else:
                        cons.print("[red]Download failed.[/red]")
                except Exception as e:
                    cons.print(f"[red]Error: {e}[/red]")

            elif action == "i":
                # Ignore
                add_ignored_album(canonical_name, album.title)
                cons.print(f"[dim]Ignored: [{album.year}] {album.title}[/dim]")
                removed_indices.add(idx - 1)

            elif action == "o":
                # Open in Qobuz
                _open_in_qobuz(album.id)
                cons.print(f"[dim]Opened in Qobuz: [{album.year}] {album.title}[/dim]")

            # "s" (skip) does nothing

        # Remove processed albums
        albums = [a for i, a in enumerate(albums) if i not in removed_indices]


@app.command()
def discover(
    artist: Annotated[
        Optional[str],
        typer.Option("--artist", "-a", help="Specific artist to check"),
    ] = None,
    library_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Path to music library"),
    ] = None,
    all_albums: Annotated[
        bool,
        typer.Option("--all", help="Show all albums instead of top 3"),
    ] = False,
    interactive: Annotated[
        bool,
        typer.Option("--interactive", "-I", help="Interactive mode to download or ignore albums"),
    ] = False,
) -> None:
    """Find new albums by artists in the library."""
    path = library_path or LIBRARY_PATH

    if not path.exists():
        console.print(f"[red]Library path does not exist: {path}[/red]")
        raise typer.Exit(1)

    artists = scan_library(path)

    if not artists:
        console.print("[yellow]No artists found in library.[/yellow]")
        return

    # Filter to specific artist if provided
    if artist:
        normalized = normalize_artist(artist)
        if normalized not in artists:
            # Try fuzzy match
            match = find_matching_artist(artist, list(artists.keys()))
            if match:
                console.print(f"[dim]Matched '{artist}' to '{match}'[/dim]")
                normalized = match
            else:
                console.print(f"[yellow]Artist '{artist}' not found in library.[/yellow]")
                # Suggest closest matches
                from rapidfuzz import process as rfprocess
                suggestions = rfprocess.extract(artist, list(artists.keys()), limit=3)
                if suggestions:
                    console.print("[dim]Did you mean:[/dim]")
                    for name, score, _ in suggestions:
                        console.print(f"  [dim]- {name}[/dim]")
                return
        artists = {normalized: artists[normalized]}

    from .ignore import is_artist_ignored

    for artist_data in sorted(artists.values(), key=lambda a: a.name.lower()):
        # Skip ignored artists
        if is_artist_ignored(artist_data.canonical_name) or is_artist_ignored(artist_data.name):
            continue

        console.print(f"\n[cyan]Checking {artist_data.canonical_name}...[/cyan]")

        existing = [(a.year, a.title) for a in artist_data.albums]

        try:
            missing = discover_missing_albums(artist_data.canonical_name, existing)

            # Filter out ignored albums
            missing = [
                album for album in missing
                if not is_album_ignored_with_variants(
                    artist_data.name,
                    artist_data.canonical_name,
                    album.title,
                    _normalize_album_title(album.title),
                )
            ]

            if missing:
                if interactive:
                    _interactive_discover(
                        artist_data.name,
                        artist_data.canonical_name,
                        missing,
                        console,
                    )
                else:
                    total_count = len(missing)
                    display_albums = missing
                    remaining_count = 0

                    # Rank and limit if more than 3 albums and not showing all
                    if total_count > 3 and not all_albums:
                        # Sort by Qobuz popularity (descending), then by year (ascending)
                        display_albums = sorted(
                            missing, key=lambda x: (-x.popularity, x.year)
                        )[:3]
                        remaining_count = total_count - 3

                    console.print(f"  [green]Found {total_count} new album(s):[/green]")

                    # When showing all, sort by year; when showing top 3, keep popularity order
                    if all_albums:
                        display_albums = sorted(display_albums, key=lambda x: x.year)

                    for album in display_albums:
                        fidelity = f"{album.bit_depth}bit/{album.sample_rate}kHz"
                        if album.standard_id:
                            # This is a hi-fi version that will have bonus tracks removed
                            console.print(
                                f"    [{album.year}] {album.title} "
                                f"[magenta]({fidelity}, {album.standard_track_count} tracks)[/magenta] "
                                f"[dim]id:{album.id}[/dim]"
                            )
                        else:
                            console.print(
                                f"    [{album.year}] {album.title} [dim]({fidelity})[/dim] "
                                f"[dim]id:{album.id}[/dim]"
                            )

                    if remaining_count > 0:
                        console.print(
                            f"    [dim]...and {remaining_count} more (use --all to see all)[/dim]"
                        )
            else:
                console.print("  [dim]No new albums found.[/dim]")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")


@app.command()
def download(
    album_id: Annotated[str, typer.Argument(help="Qobuz album ID")],
) -> None:
    """Download an album from Qobuz."""
    url = f"https://open.qobuz.com/album/{album_id}"
    console.print(f"[cyan]Downloading: {album_id}[/cyan]")

    try:
        success, album_path = download_album(url)

        if success:
            console.print("[green]Download complete![/green]")
            if album_path:
                console.print(f"  Location: {album_path}")
        else:
            console.print("[red]Download failed. Check qobuz-dl output for details.[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def _print_preview(album_path: Path, preview: dict) -> bool:
    """Print preview of changes for an album.

    Returns True if any changes would be made.
    """
    has_changes = False

    # Metadata changes
    if preview["metadata_changes"]:
        has_changes = True
        console.print("  [yellow]Metadata:[/yellow]")
        for item in preview["metadata_changes"]:
            console.print(f"    {item['file']}:")
            for change in item["changes"]:
                console.print(f"      {change}")

    # Genre
    if preview["genre"]["would_fetch"]:
        has_changes = True
        console.print("  [yellow]Genre:[/yellow] would fetch from Last.fm")
    elif preview["genre"]["current"]:
        console.print(f"  [dim]Genre:[/dim] {preview['genre']['current']} (already set)")

    # Lyrics
    if preview["lyrics"]["missing"] > 0:
        has_changes = True
        console.print(
            f"  [yellow]Lyrics:[/yellow] {preview['lyrics']['missing']} tracks missing, "
            f"{preview['lyrics']['have']} already have"
        )
    elif preview["lyrics"]["have"] > 0:
        console.print(f"  [dim]Lyrics:[/dim] all {preview['lyrics']['have']} tracks have lyrics")

    # Artwork
    if preview["artwork"]["found"]:
        if not preview["artwork"]["embedded"]:
            has_changes = True
            msg = f"  [yellow]Artwork:[/yellow] would embed {preview['artwork']['path']}"
            if preview["artwork"]["needs_resize"]:
                size_kb = preview["artwork"]["current_size"] / 1024
                msg += f" (resize from {size_kb:.0f}KB)"
            console.print(msg)
        else:
            console.print(f"  [dim]Artwork:[/dim] already embedded")
    else:
        console.print("  [dim]Artwork:[/dim] no cover image found")

    # ReplayGain
    if not preview["replaygain"]["has_tags"]:
        has_changes = True
        console.print("  [yellow]ReplayGain:[/yellow] would apply normalization")
    else:
        console.print("  [dim]ReplayGain:[/dim] already has tags")

    return has_changes


@app.command()
def process(
    path: Annotated[Path, typer.Argument(help="Path to album or parent directory")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview changes without applying them"),
    ] = False,
) -> None:
    """Apply post-processing to album(s).

    Can process a single album folder or traverse a directory tree to find
    and process all albums. Album folders are identified by the naming
    pattern '[YYYY] Album Title'.

    Examples:
        music-librarian process "/path/to/[2020] Album Name"
        music-librarian process "/path/to/Artist"
        music-librarian process --dry-run "/path/to/Alphabetical"
    """
    if not path.exists():
        console.print(f"[red]Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    if not path.is_dir():
        console.print(f"[red]Path must be a directory: {path}[/red]")
        raise typer.Exit(1)

    albums = find_album_directories(path)

    if not albums:
        console.print(f"[yellow]No album folders found under: {path}[/yellow]")
        raise typer.Exit(1)

    if dry_run:
        console.print(f"[cyan]Previewing {len(albums)} album(s)...[/cyan]\n")
        albums_with_changes = 0

        for album_path in albums:
            console.print(f"[bold]{album_path.parent.name} / {album_path.name}[/bold]")
            try:
                preview = preview_album_processing(album_path)
                if _print_preview(album_path, preview):
                    albums_with_changes += 1
                else:
                    console.print("  [green]No changes needed[/green]")
            except Exception as e:
                console.print(f"  [red]Error: {e}[/red]")
            console.print()

        console.print(f"[cyan]Summary: {albums_with_changes} of {len(albums)} album(s) have pending changes[/cyan]")
    else:
        console.print(f"[cyan]Found {len(albums)} album(s) to process[/cyan]\n")

        succeeded = 0
        failed = 0

        for album_path in albums:
            console.print(f"[bold]{album_path.parent.name} / {album_path.name}[/bold]")
            try:
                process_album(album_path)
                console.print("[green]  Done[/green]\n")
                succeeded += 1
            except Exception as e:
                console.print(f"[red]  Error: {e}[/red]\n")
                failed += 1

        console.print(f"[cyan]Processed {succeeded} album(s)[/cyan]", end="")
        if failed:
            console.print(f"[red], {failed} failed[/red]")
        else:
            console.print()


@app.command()
def normalize(
    path: Annotated[Path, typer.Argument(help="Path to album folder")],
) -> None:
    """Apply ReplayGain normalization to an album."""
    if not path.exists():
        console.print(f"[red]Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    if not path.is_dir():
        console.print(f"[red]Path must be a directory: {path}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Normalizing: {path}[/cyan]")

    try:
        success = normalize_album(path)

        if success:
            console.print("[green]ReplayGain tags applied successfully![/green]")
        else:
            console.print("[red]Normalization failed. Is rsgain installed?[/red]")
            raise typer.Exit(1)
    except FileNotFoundError:
        console.print("[red]rsgain not found. Install with: brew install rsgain[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def convert(
    path: Annotated[Path, typer.Argument(help="Path to album folder")],
    output: Annotated[
        Optional[Path],
        typer.Option("--out", "-o", help="Output directory"),
    ] = None,
    artist: Annotated[
        Optional[str],
        typer.Option("--artist", "-a", help="Artist name for output folder"),
    ] = None,
) -> None:
    """Convert FLAC album to AAC 256kbps."""
    if not path.exists():
        console.print(f"[red]Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    if not path.is_dir():
        console.print(f"[red]Path must be a directory: {path}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Converting: {path}[/cyan]")

    try:
        output_path = convert_album_to_aac(path, output_base=output, artist_name=artist)
        console.print(f"[green]Conversion complete![/green]")
        console.print(f"Output: {output_path}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("embed-art")
def embed_art(
    path: Annotated[Path, typer.Argument(help="Path to album folder")],
) -> None:
    """Embed cover artwork into FLAC files."""
    if not path.exists():
        console.print(f"[red]Path does not exist: {path}[/red]")
        raise typer.Exit(1)

    if not path.is_dir():
        console.print(f"[red]Path must be a directory: {path}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Embedding artwork: {path}[/cyan]")

    result = embed_artwork(path)

    if not result["cover_found"]:
        console.print("[yellow]No cover image found in album folder.[/yellow]")
        raise typer.Exit(1)

    console.print(f"  Cover: {result['cover_path'].name}")
    console.print(f"  Tracks processed: {result['tracks_processed']}")

    original_kb = result["original_size"] / 1024
    embedded_kb = result["embedded_size"] / 1024

    if result["was_resized"]:
        console.print(
            f"  [yellow]Resized:[/yellow] {original_kb:.1f} KB → {embedded_kb:.1f} KB"
        )
    else:
        console.print(f"  Size: {embedded_kb:.1f} KB")

    console.print("[green]Artwork embedded successfully![/green]")


def _open_in_cog(album_path: Path) -> None:
    """Open an album folder in the Cog music player."""
    import subprocess

    subprocess.Popen(["open", "-a", "Cog", str(album_path)])
    console.print(f"[green]Opened in Cog:[/green] {album_path.name}")


def _list_albums_in(directory: Path, label: str, show_dest: bool = False) -> list[Path]:
    """List albums in a directory with index numbers.

    Args:
        directory: Directory to scan for album folders.
        label: Display label for the directory (e.g., "Downloads", "[New]").
        show_dest: If True, show the destination path for each album.

    Returns:
        Sorted list of album directory paths.
    """
    albums = sorted(
        [d for d in directory.iterdir() if d.is_dir() and parse_new_folder(d.name)],
        key=lambda d: d.name.lower(),
    )
    if not albums:
        console.print(f"[dim]No albums in {label}.[/dim]")
        return albums

    console.print(f"[bold]Albums in {label} ({len(albums)}):[/bold]")
    for i, album_dir in enumerate(albums, 1):
        parsed = parse_new_folder(album_dir.name)
        if parsed and show_dest:
            artist, year, title = parsed
            dest = get_artist_path(artist, LIBRARY_PATH)
            console.print(f"  [bold]{i}.[/bold] {album_dir.name}")
            console.print(f"     [dim]→ {dest}/[{year}] {title}[/dim]")
        else:
            console.print(f"  [bold]{i}.[/bold] {album_dir.name}")

    return albums


@app.command()
def stage(
    name: Annotated[
        Optional[str],
        typer.Argument(help="Album folder name in Downloads (omit to list all)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview transfer without executing"),
    ] = False,
    play: Annotated[
        Optional[int],
        typer.Option("--play", "-p", help="Open album at index in Cog"),
    ] = None,
    index: Annotated[
        Optional[int],
        typer.Option("--index", "-i", help="Stage album at index (1-based)"),
    ] = None,
) -> None:
    """Stage an album from Downloads to [New] on the NAS.

    Transfers using rsync for integrity, then deletes the local copy.
    The folder name should match the format '{Artist} - [{YYYY}] {Album Title}'.

    If no name is given, lists all albums currently in Downloads.

    Examples:
        music-librarian stage
        music-librarian stage -p 1
        music-librarian stage -i 1
        music-librarian stage -i 1 -n
        music-librarian stage "Radiohead - [1997] OK Computer"
    """
    if name is None and index is None:
        if not DOWNLOADS_PATH.exists():
            console.print(f"[dim]Downloads folder not found: {DOWNLOADS_PATH}[/dim]")
            return

        albums = _list_albums_in(DOWNLOADS_PATH, "Downloads")
        if albums and play is not None:
            if 1 <= play <= len(albums):
                _open_in_cog(albums[play - 1])
            else:
                console.print(f"[red]Invalid index: {play} (1-{len(albums)})[/red]")
                raise typer.Exit(1)
        return

    if index is not None:
        if not DOWNLOADS_PATH.exists():
            console.print(f"[dim]Downloads folder not found: {DOWNLOADS_PATH}[/dim]")
            raise typer.Exit(1)

        albums = sorted(
            [d for d in DOWNLOADS_PATH.iterdir() if d.is_dir() and parse_new_folder(d.name)],
            key=lambda d: d.name.lower(),
        )
        if not albums:
            console.print("[dim]No albums in Downloads.[/dim]")
            raise typer.Exit(1)
        if not 1 <= index <= len(albums):
            console.print(f"[red]Invalid index: {index} (1-{len(albums)})[/red]")
            raise typer.Exit(1)
        path = albums[index - 1]
    else:
        path = DOWNLOADS_PATH / name

    if not path.exists():
        console.print(f"[red]Folder not found: {path}[/red]")
        raise typer.Exit(1)

    if not path.is_dir():
        console.print(f"[red]Not a directory: {path}[/red]")
        raise typer.Exit(1)

    parsed = parse_new_folder(path.name)
    if not parsed:
        console.print(
            "[red]Folder name doesn't match expected format:[/red] "
            "{Artist} - [{YYYY}] {Album Title}"
        )
        console.print(f"  Got: {path.name}")
        raise typer.Exit(1)

    artist, year, title = parsed

    if not check_volume_mounted(MUSIC_VOLUME):
        console.print(f"[red]Network drive not mounted: {MUSIC_VOLUME}[/red]")
        console.print("  Mount the drive and try again.")
        raise typer.Exit(1)

    if not NEW_PATH.exists():
        if not dry_run:
            NEW_PATH.mkdir(parents=True, exist_ok=True)

    dest_album = NEW_PATH / path.name
    if dest_album.exists():
        console.print(f"[red]Already exists in [New]: {dest_album}[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Staging: {artist} - [{year}] {title}[/cyan]")
    console.print(f"  From: {path}")
    console.print(f"  To:   {dest_album}")

    if dry_run:
        console.print("\n[yellow]Dry run — no changes made.[/yellow]")
        rsync_album(path, NEW_PATH, dry_run=True)
        return

    console.print()
    success = rsync_album(path, NEW_PATH)

    if success:
        if dest_album.exists() and any(dest_album.iterdir()):
            delete_source(path)
            console.print(f"\n[green]Staged successfully![/green]")
            console.print(f"  Location: {dest_album}")
        else:
            console.print(
                "\n[red]rsync reported success but destination appears empty. "
                "Source NOT deleted.[/red]"
            )
            raise typer.Exit(1)
    else:
        console.print("\n[red]Transfer failed. Source NOT deleted.[/red]")
        raise typer.Exit(1)


@app.command()
def shelve(
    name: Annotated[
        Optional[str],
        typer.Argument(help="Album folder name in [New] (omit to list all)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview move without executing"),
    ] = False,
    play: Annotated[
        Optional[int],
        typer.Option("--play", "-p", help="Open album at index in Cog"),
    ] = None,
    index: Annotated[
        Optional[int],
        typer.Option("--index", "-i", help="Shelve album at index (1-based)"),
    ] = None,
) -> None:
    """Shelve an album from [New] into the permanent library.

    Parses the '{Artist} - [{YYYY}] {Album Title}' folder name to determine
    the correct alphabetical location, then moves it.

    If no name is given, lists all albums currently in [New].

    Examples:
        music-librarian shelve
        music-librarian shelve -p 2
        music-librarian shelve -i 1
        music-librarian shelve -i 1 -n
        music-librarian shelve "Radiohead - [1997] OK Computer"
    """
    if not check_volume_mounted(MUSIC_VOLUME):
        console.print(f"[red]Network drive not mounted: {MUSIC_VOLUME}[/red]")
        console.print("  Mount the drive and try again.")
        raise typer.Exit(1)

    if not NEW_PATH.exists():
        console.print(f"[red][New] folder not found: {NEW_PATH}[/red]")
        raise typer.Exit(1)

    if name is None and index is None:
        albums = _list_albums_in(NEW_PATH, "[New]", show_dest=True)
        if albums and play is not None:
            if 1 <= play <= len(albums):
                _open_in_cog(albums[play - 1])
            else:
                console.print(f"[red]Invalid index: {play} (1-{len(albums)})[/red]")
                raise typer.Exit(1)
        return

    if index is not None:
        albums = sorted(
            [d for d in NEW_PATH.iterdir() if d.is_dir() and parse_new_folder(d.name)],
            key=lambda d: d.name.lower(),
        )
        if not albums:
            console.print("[dim]No albums in [New].[/dim]")
            raise typer.Exit(1)
        if not 1 <= index <= len(albums):
            console.print(f"[red]Invalid index: {index} (1-{len(albums)})[/red]")
            raise typer.Exit(1)
        path = albums[index - 1]
    else:
        path = NEW_PATH / name

    if not path.exists():
        console.print(f"[red]Folder not found: {path}[/red]")
        raise typer.Exit(1)

    if not path.is_dir():
        console.print(f"[red]Not a directory: {path}[/red]")
        raise typer.Exit(1)

    parsed = parse_new_folder(path.name)
    if not parsed:
        console.print(
            "[red]Folder name doesn't match expected format:[/red] "
            "{Artist} - [{YYYY}] {Album Title}"
        )
        console.print(f"  Got: {path.name}")
        raise typer.Exit(1)

    artist, year, title = parsed
    artist_path = get_artist_path(artist, LIBRARY_PATH)
    album_folder_name = f"[{year}] {title}"
    dest_album = artist_path / album_folder_name

    console.print(f"[cyan]Shelving: {artist} - [{year}] {title}[/cyan]")
    console.print(f"  From: {path}")
    console.print(f"  To:   {dest_album}")

    if dest_album.exists():
        console.print(f"\n[red]Destination already exists: {dest_album}[/red]")
        raise typer.Exit(1)

    if dry_run:
        if not artist_path.exists():
            console.print(f"\n[yellow]Would create artist folder: {artist_path}[/yellow]")
        console.print("[yellow]Dry run — no changes made.[/yellow]")
        return

    if not artist_path.exists():
        artist_path.mkdir(parents=True, exist_ok=True)
        console.print(f"  Created: {artist_path}")

    move_album(path, dest_album)
    console.print(f"\n[green]Shelved successfully![/green]")
    console.print(f"  Location: {dest_album}")


@ignore_app.command("add")
def ignore_add(
    artist: Annotated[str, typer.Argument(help="Artist name")],
    album: Annotated[
        Optional[str],
        typer.Argument(help="Album title (if omitting, ignores entire artist)"),
    ] = None,
) -> None:
    """Add an artist or album to the ignore list."""
    if album:
        if add_ignored_album(artist, album):
            console.print(f"[green]Ignored album:[/green] {artist} - {album}")
        else:
            console.print(f"[yellow]Already ignored:[/yellow] {artist} - {album}")
    else:
        if add_ignored_artist(artist):
            console.print(f"[green]Ignored artist:[/green] {artist}")
        else:
            console.print(f"[yellow]Already ignored:[/yellow] {artist}")


@ignore_app.command("remove")
def ignore_remove(
    artist: Annotated[str, typer.Argument(help="Artist name")],
    album: Annotated[
        Optional[str],
        typer.Argument(help="Album title (if omitting, removes artist from ignore list)"),
    ] = None,
) -> None:
    """Remove an artist or album from the ignore list."""
    if album:
        if remove_ignored_album(artist, album):
            console.print(f"[green]Removed from ignore list:[/green] {artist} - {album}")
        else:
            console.print(f"[yellow]Not in ignore list:[/yellow] {artist} - {album}")
    else:
        if remove_ignored_artist(artist):
            console.print(f"[green]Removed from ignore list:[/green] {artist}")
        else:
            console.print(f"[yellow]Not in ignore list:[/yellow] {artist}")


@ignore_app.command("list")
def ignore_list() -> None:
    """Show all ignored artists and albums."""
    artists = get_ignored_artists()
    albums = get_ignored_albums()

    if not artists and not albums:
        console.print("[dim]No ignored artists or albums.[/dim]")
        return

    if artists:
        console.print("[bold]Ignored Artists:[/bold]")
        for artist in sorted(artists, key=str.lower):
            console.print(f"  {artist}")

    if albums:
        console.print("\n[bold]Ignored Albums:[/bold]")
        for entry in sorted(albums, key=lambda x: (x["artist"].lower(), x["album"].lower())):
            console.print(f"  {entry['artist']} - {entry['album']}")


if __name__ == "__main__":
    app()
