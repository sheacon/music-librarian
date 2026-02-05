"""Shared test fixtures."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_library(tmp_path):
    """Create a temporary library directory structure."""
    lib = tmp_path / "library"
    # Create structure: Letter / Artist / [YYYY] Album Title
    (lib / "B" / "Beatles" / "[1969] Abbey Road").mkdir(parents=True)
    (lib / "B" / "Beatles" / "[1967] Sgt. Peppers Lonely Hearts Club Band").mkdir(parents=True)
    (lib / "R" / "Radiohead" / "[1997] OK Computer").mkdir(parents=True)
    (lib / "R" / "Radiohead" / "[2000] Kid A").mkdir(parents=True)
    (lib / "P" / "Pink Floyd" / "[1973] The Dark Side of the Moon").mkdir(parents=True)
    return lib


@pytest.fixture
def tmp_ignore_file(tmp_path):
    """Create a temporary ignore file."""
    ignore_path = tmp_path / "ignore.json"
    data = {"artists": [], "albums": []}
    ignore_path.write_text(json.dumps(data))
    return ignore_path


@pytest.fixture
def populated_ignore_file(tmp_path):
    """Create a temporary ignore file with some entries."""
    ignore_path = tmp_path / "ignore.json"
    data = {
        "artists": ["Nickelback", "Creed"],
        "albums": [
            {"artist": "Radiohead", "album": "Pablo Honey"},
            {"artist": "The Beatles", "album": "Yellow Submarine"},
        ],
    }
    ignore_path.write_text(json.dumps(data))
    return ignore_path
