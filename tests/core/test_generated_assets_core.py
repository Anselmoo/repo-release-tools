from pathlib import Path

import pytest

from repo_release_tools.config.core import _load_generated_assets


def test_load_generated_assets_rejects_non_list() -> None:
    with pytest.raises(ValueError, match="generated_assets must be an array of tables"):
        _load_generated_assets(Path("."), "not-a-list")


def test_load_generated_assets_rejects_non_table_entry() -> None:
    with pytest.raises(ValueError, match="Each generated_assets entry must be a table"):
        _load_generated_assets(Path("."), [1])


def test_load_generated_assets_rejects_empty_path() -> None:
    with pytest.raises(
        ValueError, match="Each generated_assets entry must have a non-empty 'path' string"
    ):
        _load_generated_assets(Path("."), [{"path": "", "command": ["echo"]}])


def test_load_generated_assets_rejects_bad_command() -> None:
    with pytest.raises(
        ValueError,
        match="Each generated_assets entry must have a non-empty 'command' list of strings",
    ):
        _load_generated_assets(Path("."), [{"path": "a.png", "command": "bad"}])
