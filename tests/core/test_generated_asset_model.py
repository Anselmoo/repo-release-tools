from pathlib import Path

import pytest

from repo_release_tools.config.model import GeneratedAsset


def test_generated_asset_validate_rejects_absolute_path() -> None:
    g = GeneratedAsset(path=Path("/abs/out.png"), command=["echo", "hi"])
    with pytest.raises(ValueError, match="relative path"):
        g.validate()


def test_generated_asset_validate_rejects_parent_escape() -> None:
    g = GeneratedAsset(path=Path("../escape.png"), command=["echo"])
    with pytest.raises(ValueError, match="must not escape"):
        g.validate()


def test_generated_asset_validate_rejects_bad_command() -> None:
    g = GeneratedAsset(path=Path("assets/out.png"), command=[])
    with pytest.raises(ValueError, match="non-empty list of strings"):
        g.validate()


def test_generated_asset_validate_allows_valid_entry() -> None:
    g = GeneratedAsset(path=Path("assets/out.png"), command=["make", "banner"])
    # Should not raise
    g.validate()
