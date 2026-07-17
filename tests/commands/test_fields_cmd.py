from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from repo_release_tools.commands.fields_cmd import (
    SOURCE_OWNED_TOPIC_DOCS,
    FieldComparison,
    FieldPathError,
    _add_fields_strict_argument,
    _compare_field_target,
    _compare_field_targets,
    _load_json_file,
    _print_field_list,
    _split_path,
    _write_json_file,
    cmd_fields,
    register,
    resolve_field,
    set_field,
)
from repo_release_tools.config.core import RrtConfig, VersionGroup
from repo_release_tools.config.model import FieldTarget, FieldTargetEntry

_DEFAULT_GROUP = VersionGroup(
    name="default",
    release_branch="release/v{version}",
    changelog_file=Path("CHANGELOG.md"),
    lock_command=[],
    generated_files=[],
    version_targets=[],
)


def _make_config(
    tmp_path: Path | None = None,
    field_targets: list[FieldTarget] | None = None,
) -> RrtConfig:
    root = tmp_path or Path(".")
    return RrtConfig(
        root=root,
        config_file=root / "pyproject.toml",
        version_groups=[_DEFAULT_GROUP],
        field_targets=field_targets or [],
    )


def _make_args(
    *,
    check: bool = False,
    sync: bool = False,
    list_: bool = False,
    dry_run: bool = False,
    strict: bool = False,
    verbose: int = 0,
) -> argparse.Namespace:
    return argparse.Namespace(
        check=check,
        sync=sync,
        list=list_,
        dry_run=dry_run,
        strict=strict,
        verbose=verbose,
    )


def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def _simple_field_target(
    *,
    source: str = "plugin.json",
    source_field: str = "description",
    target_path: str = "marketplace.json",
    target_field: str = "plugins[name=self-assess].description",
) -> FieldTarget:
    return FieldTarget(
        source=source,
        source_field=source_field,
        targets=[FieldTargetEntry(path=target_path, field=target_field)],
    )


# ---------------------------------------------------------------------------
# SOURCE_OWNED_TOPIC_DOCS
# ---------------------------------------------------------------------------


def test_source_owned_topic_docs_has_fields_entry() -> None:
    assert any(name == "fields" for name, _ in SOURCE_OWNED_TOPIC_DOCS)


# ---------------------------------------------------------------------------
# _split_path
# ---------------------------------------------------------------------------


def test_split_path_dotted() -> None:
    assert _split_path("author.name") == ["author", "name"]


def test_split_path_single_segment() -> None:
    assert _split_path("description") == ["description"]


def test_split_path_ignores_dots_inside_brackets() -> None:
    # A dot inside a bracket filter's match value must not split the segment.
    assert _split_path("plugins[name=self.assess].description") == [
        "plugins[name=self.assess]",
        "description",
    ]


def test_split_path_filter_then_dotted() -> None:
    assert _split_path("plugins[name=self-assess].description") == [
        "plugins[name=self-assess]",
        "description",
    ]


# ---------------------------------------------------------------------------
# resolve_field
# ---------------------------------------------------------------------------


def test_resolve_field_top_level_key() -> None:
    assert resolve_field({"description": "hi"}, "description") == "hi"


def test_resolve_field_nested_dotted() -> None:
    data = {"author": {"name": "Ada"}}
    assert resolve_field(data, "author.name") == "Ada"


def test_resolve_field_array_filter() -> None:
    data = {"plugins": [{"name": "a", "description": "A"}, {"name": "b", "description": "B"}]}
    assert resolve_field(data, "plugins[name=b].description") == "B"


def test_resolve_field_chained_filter_then_dotted_nested() -> None:
    data = {"items": [{"id": "x", "meta": {"label": "X label"}}]}
    assert resolve_field(data, "items[id=x].meta.label") == "X label"


def test_resolve_field_missing_key_raises() -> None:
    with pytest.raises(FieldPathError, match="not found"):
        resolve_field({"a": 1}, "b")


def test_resolve_field_missing_array_match_raises() -> None:
    data = {"plugins": [{"name": "a"}]}
    with pytest.raises(FieldPathError, match="no element"):
        resolve_field(data, "plugins[name=missing].description")


def test_resolve_field_filter_on_non_array_raises() -> None:
    data = {"plugins": {"not": "a list"}}
    with pytest.raises(FieldPathError, match="not an array"):
        resolve_field(data, "plugins[name=x].description")


def test_resolve_field_key_lookup_on_non_object_raises() -> None:
    data = {"description": "scalar"}
    with pytest.raises(FieldPathError, match="non-object"):
        resolve_field(data, "description.nested")


def test_resolve_field_empty_path_raises() -> None:
    with pytest.raises(FieldPathError):
        resolve_field({"a": 1}, "")


def test_resolve_field_invalid_segment_raises() -> None:
    with pytest.raises(FieldPathError, match="invalid field path segment"):
        resolve_field({"a": 1}, "a[")


def test_resolve_field_empty_middle_segment_raises() -> None:
    # "a..b" splits into ["a", "", "b"] — the empty middle segment must
    # raise once _step actually reaches it (not the same as an empty path).
    with pytest.raises(FieldPathError, match="empty segment"):
        resolve_field({"a": {"": {"b": 1}}}, "a..b")


# ---------------------------------------------------------------------------
# set_field
# ---------------------------------------------------------------------------


def test_set_field_top_level_key() -> None:
    data = {"description": "old"}
    set_field(data, "description", "new")
    assert data == {"description": "new"}


def test_set_field_preserves_key_order() -> None:
    data = {"z": 1, "description": "old", "a": 2}
    set_field(data, "description", "new")
    assert list(data.keys()) == ["z", "description", "a"]
    assert data["description"] == "new"


def test_set_field_array_filter_target() -> None:
    data = {"plugins": [{"name": "a", "description": "A"}, {"name": "b", "description": "B"}]}
    set_field(data, "plugins[name=b].description", "B2")
    assert data["plugins"][1]["description"] == "B2"
    assert data["plugins"][0]["description"] == "A"


def test_set_field_missing_key_raises() -> None:
    with pytest.raises(FieldPathError, match="not found"):
        set_field({"a": 1}, "b", "value")


def test_set_field_path_ending_in_filter_raises() -> None:
    data = {"plugins": [{"name": "a"}]}
    with pytest.raises(FieldPathError, match="must end in a plain key"):
        set_field(data, "plugins[name=a]", {"name": "a", "description": "x"})


def test_set_field_empty_path_raises() -> None:
    with pytest.raises(FieldPathError, match="non-empty string"):
        set_field({"a": 1}, "", "value")


def test_set_field_non_object_parent_raises() -> None:
    # "a.b": the parent segment "a" resolves to a scalar, not an object,
    # so the final key "b" cannot be set on it.
    data = {"a": "scalar"}
    with pytest.raises(FieldPathError, match="non-object"):
        set_field(data, "a.b", "value")


# ---------------------------------------------------------------------------
# _load_json_file / _write_json_file — round-trip formatting preservation
# ---------------------------------------------------------------------------


def test_json_round_trip_preserves_top_level_key_order(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "marketplace.json",
        {"z_last": 1, "plugins": [{"name": "x"}], "a_first": 2},
    )
    data = _load_json_file(path)
    # Untouched round trip: load, write back unchanged.
    _write_json_file(path, data)
    reloaded = _load_json_file(path)
    assert list(reloaded.keys()) == ["z_last", "plugins", "a_first"]
    assert reloaded == data


def test_json_round_trip_after_single_field_edit_preserves_order(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "marketplace.json",
        {"z_last": 1, "plugins": [{"name": "x", "description": "old"}], "a_first": 2},
    )
    data = _load_json_file(path)
    set_field(data, "plugins[name=x].description", "new")
    _write_json_file(path, data)
    reloaded = _load_json_file(path)
    assert list(reloaded.keys()) == ["z_last", "plugins", "a_first"]
    assert reloaded["plugins"][0]["description"] == "new"


def test_load_json_file_missing_raises_field_path_error(tmp_path: Path) -> None:
    with pytest.raises(FieldPathError, match="cannot read"):
        _load_json_file(tmp_path / "missing.json")


def test_load_json_file_invalid_json_raises_field_path_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not valid json")
    with pytest.raises(FieldPathError, match="invalid JSON"):
        _load_json_file(path)


# ---------------------------------------------------------------------------
# FieldTargetEntry / FieldTarget validation
# ---------------------------------------------------------------------------


def test_field_target_entry_validate_ok() -> None:
    FieldTargetEntry(path="a.json", field="description").validate()


def test_field_target_entry_validate_empty_path() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        FieldTargetEntry(path="", field="description").validate()


def test_field_target_entry_validate_absolute_path() -> None:
    with pytest.raises(ValueError, match="relative path"):
        FieldTargetEntry(path="/a.json", field="description").validate()


def test_field_target_entry_validate_escapes_root() -> None:
    with pytest.raises(ValueError, match="escape"):
        FieldTargetEntry(path="../a.json", field="description").validate()


def test_field_target_entry_validate_empty_field() -> None:
    with pytest.raises(ValueError, match="exactly one of 'field' or 'anchor'"):
        FieldTargetEntry(path="a.json", field="").validate()


def test_field_target_entry_validate_neither_field_nor_anchor() -> None:
    with pytest.raises(ValueError, match="exactly one of 'field' or 'anchor'"):
        FieldTargetEntry(path="a.json").validate()


def test_field_target_entry_validate_both_field_and_anchor() -> None:
    with pytest.raises(ValueError, match="exactly one of 'field' or 'anchor'"):
        FieldTargetEntry(path="a.json", field="x", anchor="y").validate()


def test_field_target_entry_validate_anchor_only_ok() -> None:
    FieldTargetEntry(path="README.md", anchor="self-assess-description").validate()


def test_field_target_validate_ok() -> None:
    _simple_field_target().validate()


def test_field_target_validate_empty_source() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        FieldTarget(
            source="", source_field="d", targets=[FieldTargetEntry("a.json", "d")]
        ).validate()


def test_field_target_validate_absolute_source() -> None:
    with pytest.raises(ValueError, match="relative path"):
        FieldTarget(
            source="/a.json", source_field="d", targets=[FieldTargetEntry("a.json", "d")]
        ).validate()


def test_field_target_validate_source_escapes_root() -> None:
    with pytest.raises(ValueError, match="escape"):
        FieldTarget(
            source="../a.json", source_field="d", targets=[FieldTargetEntry("a.json", "d")]
        ).validate()


def test_field_target_validate_empty_source_field() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        FieldTarget(
            source="a.json", source_field="", targets=[FieldTargetEntry("a.json", "d")]
        ).validate()


def test_field_target_validate_no_targets() -> None:
    with pytest.raises(ValueError, match="at least one target"):
        FieldTarget(source="a.json", source_field="d", targets=[]).validate()


def test_field_target_validate_delegates_to_entries() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        FieldTarget(
            source="a.json", source_field="d", targets=[FieldTargetEntry("", "d")]
        ).validate()


# ---------------------------------------------------------------------------
# register / _add_fields_strict_argument
# ---------------------------------------------------------------------------


def test_register_creates_fields_subcommand() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register(subparsers)
    args = parser.parse_args(["fields"])
    assert hasattr(args, "handler")


def test_register_check_flag() -> None:
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["fields", "--check"])
    assert args.check is True
    assert args.sync is False


def test_register_sync_and_dry_run_flags() -> None:
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["fields", "--sync", "--dry-run"])
    assert args.sync is True
    assert args.dry_run is True


def test_register_list_flag() -> None:
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    args = parser.parse_args(["fields", "--list"])
    assert args.list is True


def test_register_check_and_sync_mutually_exclusive() -> None:
    parser = argparse.ArgumentParser()
    register(parser.add_subparsers())
    with pytest.raises(SystemExit):
        parser.parse_args(["fields", "--check", "--sync"])


def test_add_fields_strict_argument_default_false_uses_strict_flag() -> None:
    parser = argparse.ArgumentParser()
    _add_fields_strict_argument(parser, default=False)

    assert parser.parse_args([]).strict is False
    assert parser.parse_args(["--strict"]).strict is True
    with pytest.raises(SystemExit):
        parser.parse_args(["--no-strict"])


def test_add_fields_strict_argument_default_true_uses_no_strict_flag() -> None:
    parser = argparse.ArgumentParser()
    _add_fields_strict_argument(parser, default=True)

    assert parser.parse_args([]).strict is True
    assert parser.parse_args(["--no-strict"]).strict is False
    with pytest.raises(SystemExit):
        parser.parse_args(["--strict"])


# ---------------------------------------------------------------------------
# _compare_field_target / _compare_field_targets
# ---------------------------------------------------------------------------


def test_compare_field_target_match(tmp_path: Path) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "same"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "same"}]},
    )
    ft = _simple_field_target()
    results = _compare_field_target(ft, tmp_path)
    assert len(results) == 1
    assert results[0].matches
    assert results[0].error is None


def test_compare_field_target_mismatch(tmp_path: Path) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "new"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "old"}]},
    )
    results = _compare_field_target(_simple_field_target(), tmp_path)
    assert not results[0].matches
    assert results[0].source_value == "new"
    assert results[0].target_value == "old"


def test_compare_field_target_source_error_propagates_to_all_targets(tmp_path: Path) -> None:
    # No plugin.json written at all.
    _write_json(tmp_path / "marketplace.json", {"plugins": []})
    results = _compare_field_target(_simple_field_target(), tmp_path)
    assert len(results) == 1
    assert results[0].error is not None
    assert "plugin.json" in results[0].error


def test_compare_field_target_target_error_only_affects_that_target(tmp_path: Path) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "new"})
    # marketplace.json missing entirely.
    results = _compare_field_target(_simple_field_target(), tmp_path)
    assert results[0].error is not None
    assert "marketplace.json" in results[0].error


def test_compare_field_targets_flattens_multiple_entries(tmp_path: Path) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "same"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "same"}]},
    )
    _write_json(tmp_path / "other.json", {"desc": "same"})
    ft1 = _simple_field_target()
    ft2 = FieldTarget(
        source="plugin.json",
        source_field="description",
        targets=[FieldTargetEntry(path="other.json", field="desc")],
    )
    results = _compare_field_targets([ft1, ft2], tmp_path)
    assert len(results) == 2


def test_field_comparison_matches_false_when_error_set() -> None:
    c = FieldComparison(
        source="a.json",
        source_field="d",
        target_path="b.json",
        target_field="d",
        source_value="x",
        target_value="x",
        error="boom",
    )
    assert c.matches is False


# ---------------------------------------------------------------------------
# cmd_fields — no targets / config errors / dry-run guard
# ---------------------------------------------------------------------------


def test_no_field_targets_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = _make_config()
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args())
    assert rc == 0


def test_config_load_error_returns_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config",
        side_effect=RuntimeError("no config"),
    ):
        rc = cmd_fields(_make_args())
    assert rc == 1


def test_dry_run_without_sync_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    ret = cmd_fields(_make_args(check=True, dry_run=True))
    assert ret == 1
    err = capsys.readouterr().err
    assert "--dry-run" in err
    assert "--sync" in err


# ---------------------------------------------------------------------------
# cmd_fields --check
# ---------------------------------------------------------------------------


def test_check_no_drift_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "same"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "same"}]},
    )
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(check=True))
    assert rc == 0


def test_check_advisory_exits_0_on_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "new"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "old"}]},
    )
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(check=True))
    assert rc == 0


def test_check_strict_exits_1_on_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "new"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "old"}]},
    )
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(check=True, strict=True))
    assert rc == 1


def test_check_strict_exits_1_on_resolution_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # Neither file exists.
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(check=True, strict=True))
    assert rc == 1


def test_default_no_flag_exits_0_even_on_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "new"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "old"}]},
    )
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(strict=True))  # strict ignored on bare invocation
    assert rc == 0


# ---------------------------------------------------------------------------
# cmd_fields --sync
# ---------------------------------------------------------------------------


def test_sync_writes_target_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "new value"})
    _write_json(
        tmp_path / "marketplace.json",
        {"z": 1, "plugins": [{"name": "self-assess", "description": "old value"}], "a": 2},
    )
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(sync=True))
    assert rc == 0
    data = json.loads((tmp_path / "marketplace.json").read_text())
    assert data["plugins"][0]["description"] == "new value"
    assert list(data.keys()) == ["z", "plugins", "a"]


def test_sync_already_in_sync_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "same"})
    marketplace = _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "same"}]},
    )
    original_mtime = marketplace.stat().st_mtime
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(sync=True))
    assert rc == 0
    assert marketplace.stat().st_mtime == original_mtime


def test_sync_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "new value"})
    marketplace = _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "old value"}]},
    )
    original_text = marketplace.read_text()
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(sync=True, dry_run=True))
    assert rc == 0
    assert marketplace.read_text() == original_text


def test_sync_returns_1_on_resolution_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "new value"})
    # marketplace.json missing -> target resolution error.
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(sync=True))
    assert rc == 1


def test_sync_multiple_targets_same_file_both_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "D", "summary": "S"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "old-d", "summary": "old-s"}]},
    )
    ft = FieldTarget(
        source="plugin.json",
        source_field="description",
        targets=[
            FieldTargetEntry(path="marketplace.json", field="plugins[name=self-assess].description")
        ],
    )
    ft2 = FieldTarget(
        source="plugin.json",
        source_field="summary",
        targets=[
            FieldTargetEntry(path="marketplace.json", field="plugins[name=self-assess].summary")
        ],
    )
    config = _make_config(tmp_path, field_targets=[ft, ft2])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(sync=True))
    assert rc == 0
    data = json.loads((tmp_path / "marketplace.json").read_text())
    assert data["plugins"][0]["description"] == "D"
    assert data["plugins"][0]["summary"] == "S"


# ---------------------------------------------------------------------------
# cmd_fields --list
# ---------------------------------------------------------------------------


def test_list_exits_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "same"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "same"}]},
    )
    config = _make_config(tmp_path, field_targets=[_simple_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(list_=True))
    assert rc == 0


def test_print_field_list_shows_match(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "same"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "same"}]},
    )
    _print_field_list([_simple_field_target()], tmp_path)
    captured = capsys.readouterr()
    assert "✓" in captured.out


def test_print_field_list_shows_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "new"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "old"}]},
    )
    _print_field_list([_simple_field_target()], tmp_path)
    captured = capsys.readouterr()
    assert "MISMATCH" in captured.out


def test_print_field_list_shows_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # No files at all -> resolution error.
    _print_field_list([_simple_field_target()], tmp_path)
    captured = capsys.readouterr()
    assert "cannot read" in captured.out


# ---------------------------------------------------------------------------
# anchor targets (#180)
# ---------------------------------------------------------------------------

_MD_ANCHOR_DOC = (
    "# werkstoff\n"
    "\n"
    "<!-- rrt:auto:start:self-assess-description -->\n"
    "old description\n"
    "<!-- rrt:auto:end:self-assess-description -->\n"
    "\n"
    "trailing text\n"
)

_MDX_ANCHOR_DOC = (
    "# werkstoff\n"
    "\n"
    "{/* rrt:auto:start:self-assess-description */}\n"
    "old description\n"
    "{/* rrt:auto:end:self-assess-description */}\n"
    "\n"
    "trailing text\n"
)

_RST_ANCHOR_DOC = (
    "werkstoff\n"
    "=========\n"
    "\n"
    ".. rrt:auto:start:self-assess-description\n"
    "\n"
    "old description\n"
    "\n"
    ".. rrt:auto:end:self-assess-description\n"
    "\n"
    "trailing text\n"
)


def _anchor_field_target(
    *,
    source: str = "plugin.json",
    source_field: str = "description",
    target_path: str = "README.md",
    anchor: str = "self-assess-description",
) -> FieldTarget:
    return FieldTarget(
        source=source,
        source_field=source_field,
        targets=[FieldTargetEntry(path=target_path, anchor=anchor)],
    )


@pytest.mark.parametrize(
    ("doc", "filename"),
    [
        (_MD_ANCHOR_DOC, "README.md"),
        (_MDX_ANCHOR_DOC, "README.mdx"),
        (_RST_ANCHOR_DOC, "README.rst"),
    ],
)
def test_compare_field_target_anchor_match(tmp_path: Path, doc: str, filename: str) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "old description"})
    (tmp_path / filename).write_text(doc)
    ft = _anchor_field_target(target_path=filename)
    comparisons = _compare_field_target(ft, tmp_path)
    assert len(comparisons) == 1
    assert comparisons[0].matches
    assert comparisons[0].target_label == "anchor:self-assess-description"


def test_compare_field_target_anchor_mismatch(tmp_path: Path) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "new description"})
    (tmp_path / "README.md").write_text(_MD_ANCHOR_DOC)
    comparisons = _compare_field_target(_anchor_field_target(), tmp_path)
    assert len(comparisons) == 1
    assert not comparisons[0].matches
    assert comparisons[0].error is None


def test_compare_field_target_anchor_missing_markers_errors(tmp_path: Path) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "d"})
    (tmp_path / "README.md").write_text("# no anchors here\n")
    comparisons = _compare_field_target(_anchor_field_target(), tmp_path)
    assert len(comparisons) == 1
    assert comparisons[0].error is not None
    assert "missing anchor markers" in comparisons[0].error


def test_compare_field_target_anchor_missing_file_errors(tmp_path: Path) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "d"})
    comparisons = _compare_field_target(_anchor_field_target(), tmp_path)
    assert len(comparisons) == 1
    assert comparisons[0].error is not None
    assert "cannot read" in comparisons[0].error


def test_compare_field_target_mixed_field_and_anchor_targets(tmp_path: Path) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "shared value"})
    _write_json(
        tmp_path / "marketplace.json",
        {"plugins": [{"name": "self-assess", "description": "shared value"}]},
    )
    (tmp_path / "README.md").write_text(_MD_ANCHOR_DOC.replace("old description", "shared value"))
    ft = FieldTarget(
        source="plugin.json",
        source_field="description",
        targets=[
            FieldTargetEntry(
                path="marketplace.json", field="plugins[name=self-assess].description"
            ),
            FieldTargetEntry(path="README.md", anchor="self-assess-description"),
        ],
    )
    comparisons = _compare_field_target(ft, tmp_path)
    assert len(comparisons) == 2
    assert all(c.matches for c in comparisons)


def test_compare_field_target_mixed_source_error_propagates_to_both(tmp_path: Path) -> None:
    # plugin.json missing entirely -> source_error should apply to every target.
    ft = FieldTarget(
        source="plugin.json",
        source_field="description",
        targets=[
            FieldTargetEntry(
                path="marketplace.json", field="plugins[name=self-assess].description"
            ),
            FieldTargetEntry(path="README.md", anchor="self-assess-description"),
        ],
    )
    comparisons = _compare_field_target(ft, tmp_path)
    assert len(comparisons) == 2
    assert all(c.error is not None for c in comparisons)
    assert comparisons[0].error == comparisons[1].error


def test_check_anchor_advisory_warns_on_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "new description"})
    (tmp_path / "README.md").write_text(_MD_ANCHOR_DOC)
    config = _make_config(tmp_path, field_targets=[_anchor_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(check=True))
    assert rc == 0
    captured = capsys.readouterr()
    assert "mismatch" in captured.err.lower() or "advisory" in captured.out.lower()


def test_check_anchor_strict_missing_markers_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "d"})
    (tmp_path / "README.md").write_text("# no anchors here\n")
    config = _make_config(tmp_path, field_targets=[_anchor_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(check=True, strict=True))
    assert rc == 1


def test_sync_writes_anchor_block_preserving_surrounding_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "brand new description"})
    (tmp_path / "README.md").write_text(_MD_ANCHOR_DOC)
    config = _make_config(tmp_path, field_targets=[_anchor_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(sync=True))
    assert rc == 0
    updated = (tmp_path / "README.md").read_text()
    assert "brand new description" in updated
    assert "old description" not in updated
    assert "# werkstoff" in updated
    assert "trailing text" in updated


def test_sync_anchor_dry_run_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "brand new description"})
    (tmp_path / "README.md").write_text(_MD_ANCHOR_DOC)
    original_text = (tmp_path / "README.md").read_text()
    config = _make_config(tmp_path, field_targets=[_anchor_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(sync=True, dry_run=True))
    assert rc == 0
    assert (tmp_path / "README.md").read_text() == original_text


def test_sync_anchor_missing_markers_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "d"})
    (tmp_path / "README.md").write_text("# no anchors here\n")
    config = _make_config(tmp_path, field_targets=[_anchor_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(sync=True))
    assert rc == 1


def test_sync_anchor_missing_file_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_json(tmp_path / "plugin.json", {"description": "d"})
    config = _make_config(tmp_path, field_targets=[_anchor_field_target()])
    with patch(
        "repo_release_tools.commands.fields_cmd.load_or_autodetect_config", return_value=config
    ):
        rc = cmd_fields(_make_args(sync=True))
    assert rc == 1


def test_list_anchor_shows_match(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "same"})
    (tmp_path / "README.md").write_text(_MD_ANCHOR_DOC.replace("old description", "same"))
    _print_field_list([_anchor_field_target()], tmp_path)
    captured = capsys.readouterr()
    assert "✓" in captured.out
    assert "anchor:self-assess-description" in captured.out


def test_list_anchor_shows_mismatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_json(tmp_path / "plugin.json", {"description": "new"})
    (tmp_path / "README.md").write_text(_MD_ANCHOR_DOC)
    _print_field_list([_anchor_field_target()], tmp_path)
    captured = capsys.readouterr()
    assert "MISMATCH" in captured.out
