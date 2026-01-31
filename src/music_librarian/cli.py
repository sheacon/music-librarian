"""CLI entry point using Typer."""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import LASTFM_API_KEY, LIBRARY_PATH
from .convert import convert_album_to_aac
from .lastfm import rank_albums_by_popularity
from .library import scan_library
from .normalize import normalize_album
from .qobuz import discover_missing_albums, download_album

app = typer.Typer(
    name="music-librarian",
    help="CLI tool to manage a music library with Qobuz integration.",
)
console = Console()


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
        from .library import normalize_artist

        normalized = normalize_artist(artist)
        if normalized not in artists:
            console.print(f"[yellow]Artist '{artist}' not found in library.[/yellow]")
            return
        artists = {normalized: artists[normalized]}

    # Check if Last.fm API key is configured for ranking
    has_lastfm = bool(LASTFM_API_KEY)
    if not has_lastfm and not all_albums:
        console.print(
            "[dim]Tip: Set LASTFM_API_KEY env var to rank albums by popularity[/dim]"
        )

    for artist_data in sorted(artists.values(), key=lambda a: a.name.lower()):
        console.print(f"\n[cyan]Checking {artist_data.canonical_name}...[/cyan]")

        existing = [(a.year, a.title) for a in artist_data.albums]

        try:
            missing = discover_missing_albums(artist_data.canonical_name, existing)

            if missing:
                total_count = len(missing)
                display_albums = missing
                remaining_count = 0

                # Rank and limit if more than 3 albums and not showing all
                if total_count > 3 and not all_albums:
                    if has_lastfm:
                        # Rank by Last.fm popularity
                        ranked = rank_albums_by_popularity(
                            missing, artist_data.canonical_name
                        )
                        display_albums = [album for album, _ in ranked[:3]]
                    else:
                        # Fall back to showing first 3 by year
                        display_albums = sorted(missing, key=lambda x: x.year)[:3]
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
                            f"[magenta]({fidelity}, {album.standard_track_count} tracks)[/magenta]"
                        )
                    else:
                        console.print(
                            f"    [{album.year}] {album.title} [dim]({fidelity})[/dim]"
                        )
                    console.print(f"      [dim]{album.url}[/dim]")

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
    url: Annotated[str, typer.Argument(help="Qobuz album or artist URL")],
    artist: Annotated[
        Optional[str],
        typer.Option("--artist", "-a", help="Artist name for folder structure"),
    ] = None,
    library_path: Annotated[
        Optional[Path],
        typer.Option("--path", "-p", help="Path to music library"),
    ] = None,
) -> None:
    """Download an album or artist discography from Qobuz."""
    console.print(f"[cyan]Downloading: {url}[/cyan]")

    try:
        success, album_path = download_album(url, artist_name=artist, library_path=library_path)

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


if __name__ == "__main__":
    app()
