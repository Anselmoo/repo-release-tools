"""Tests for rrt docs api — API protocol index (Track 2)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_release_tools.docs.api_index import (
    ApiEntry,
    ArgInfo,
    build_api_index,
    load_hooks,
    render_api_json,
    render_api_md,
    render_api_txt,
)


# ---------------------------------------------------------------------------
# ArgInfo + ApiEntry dataclasses
# ---------------------------------------------------------------------------


class TestArgInfo:
    """Basic construction and dict serialisation."""

    def test_arginfo_fields(self) -> None:
        arg = ArgInfo(
            flags=["--verbose", "-v"],
            dest="verbose",
            help="Enable verbose output.",
            default=False,
            required=False,
            metavar=None,
            choices=None,
        )
        assert arg.flags == ["--verbose", "-v"]
        assert arg.dest == "verbose"
        assert arg.help == "Enable verbose output."
        assert arg.default is False
        assert not arg.required
        assert arg.metavar is None
        assert arg.choices is None


class TestApiEntry:
    """ApiEntry construction, to_dict, and hook_id."""

    def test_to_dict_minimal(self) -> None:
        entry = ApiEntry(name="rrt foo", description="Does foo.")
        d = entry.to_dict()
        assert d["name"] == "rrt foo"
        assert d["description"] == "Does foo."
        assert d["hook_id"] is None
        assert d["arguments"] == []

    def test_to_dict_with_hook_and_args(self) -> None:
        arg = ArgInfo(
            flags=["--bar"],
            dest="bar",
            help="Bar flag.",
            default=None,
            required=False,
            metavar="VAL",
            choices=["a", "b"],
        )
        entry = ApiEntry(name="rrt bar", description="Bar command.", arguments=[arg], hook_id="rrt-bar")
        d = entry.to_dict()
        assert d["hook_id"] == "rrt-bar"
        assert len(d["arguments"]) == 1
        assert d["arguments"][0]["flags"] == ["--bar"]
        assert d["arguments"][0]["choices"] == ["a", "b"]


# ---------------------------------------------------------------------------
# load_hooks
# ---------------------------------------------------------------------------


class TestLoadHooks:
    """load_hooks reads .pre-commit-hooks.yaml and builds entry → id map."""

    def test_load_hooks_from_real_repo(self) -> None:
        """Should load at least a few hook entries from the real .pre-commit-hooks.yaml."""
        repo_root = Path(__file__).resolve().parents[2]
        hooks = load_hooks(repo_root)
        # The real repo has at least rrt-branch-name and rrt-changelog
        assert len(hooks) >= 2
        # All values should be non-empty strings
        for entry, hook_id in hooks.items():
            assert isinstance(entry, str) and entry
            assert isinstance(hook_id, str) and hook_id

    def test_load_hooks_missing_file(self, tmp_path: Path) -> None:
        """Should return empty dict when .pre-commit-hooks.yaml does not exist."""
        hooks = load_hooks(tmp_path)
        assert hooks == {}

    def test_load_hooks_invalid_yaml(self, tmp_path: Path) -> None:
        """Should return empty dict when file is not a YAML list."""
        (tmp_path / ".pre-commit-hooks.yaml").write_text("not: a list\n", encoding="utf-8")
        hooks = load_hooks(tmp_path)
        assert hooks == {}

    def test_load_hooks_custom_file(self, tmp_path: Path) -> None:
        """Should parse a synthetic .pre-commit-hooks.yaml correctly."""
        content = (
            "- id: rrt-test\n"
            "  name: Test hook\n"
            "  entry: rrt-hooks test\n"
            "  language: python\n"
        )
        (tmp_path / ".pre-commit-hooks.yaml").write_text(content, encoding="utf-8")
        hooks = load_hooks(tmp_path)
        assert hooks.get("rrt-hooks test") == "rrt-test"

    def test_load_hooks_none_root_defaults_to_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_hooks(None) should look in CWD for .pre-commit-hooks.yaml."""
        # CWD in CI is the repo root which has the real file
        hooks = load_hooks(None)
        # Either finds hooks or empty dict — no exception
        assert isinstance(hooks, dict)

    def test_load_hooks_oserror(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return empty dict when the hook file cannot be read (OSError)."""
        hook_file = tmp_path / ".pre-commit-hooks.yaml"
        hook_file.write_text("- id: hook1\n  entry: rrt-hooks test\n", encoding="utf-8")
        # Simulate read failure
        monkeypatch.setattr(
            "pathlib.Path.read_text",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("permission denied")),
        )
        hooks = load_hooks(tmp_path)
        assert hooks == {}


# ---------------------------------------------------------------------------
# build_api_index
# ---------------------------------------------------------------------------


class TestBuildApiIndex:
    """build_api_index walks an ArgumentParser and returns ApiEntry list."""

    def _simple_parser(self) -> argparse.ArgumentParser:
        """Build a minimal two-level ArgumentParser for testing."""
        parser = argparse.ArgumentParser(prog="mytool", description="A test tool.")
        parser.add_argument("--verbose", action="store_true", help="Enable verbose.")
        subs = parser.add_subparsers(dest="command")
        sub_a = subs.add_parser("alpha", description="Alpha sub-command.")
        sub_a.add_argument("name", help="A positional name.")
        sub_a.add_argument("--count", type=int, default=1, help="Repeat count.")
        subs.add_parser("beta", description="Beta sub-command.")
        return parser

    def test_returns_list_of_api_entries(self) -> None:
        parser = self._simple_parser()
        entries = build_api_index(parser)
        assert isinstance(entries, list)
        assert all(isinstance(e, ApiEntry) for e in entries)

    def test_root_entry_present(self) -> None:
        parser = self._simple_parser()
        entries = build_api_index(parser)
        names = [e.name for e in entries]
        assert any("mytool" in n for n in names)

    def test_sub_entries_present(self) -> None:
        parser = self._simple_parser()
        entries = build_api_index(parser)
        names = [e.name for e in entries]
        assert any("alpha" in n for n in names)
        assert any("beta" in n for n in names)

    def test_arguments_collected(self) -> None:
        parser = self._simple_parser()
        entries = build_api_index(parser)
        alpha = next(e for e in entries if "alpha" in e.name)
        dests = [a.dest for a in alpha.arguments]
        assert "name" in dests
        assert "count" in dests

    def test_hook_id_cross_linked(self, tmp_path: Path) -> None:
        """When hook_map has a matching entry, hook_id should be populated."""
        parser = argparse.ArgumentParser(prog="rrt branch", description="Branch helper.")
        entries = build_api_index(
            parser,
            hook_map={"rrt-hooks pre-commit": "rrt-branch-name"},
        )
        assert len(entries) > 0
        # "rrt branch" → slug "rrt-branch" → prefix-matches "rrt-branch-name"
        assert entries[0].hook_id == "rrt-branch-name"

    def test_real_rrt_parser_produces_entries(self) -> None:
        """Smoke test: build_api_index on the real rrt parser should return >10 entries."""
        from repo_release_tools.cli import build_parser

        parser = build_parser()
        entries = build_api_index(parser)
        assert len(entries) > 10
        names = [e.name for e in entries]
        # At minimum rrt and rrt docs should be present
        assert any("rrt" in n for n in names)

    def test_collect_args_tuple_metavar(self) -> None:
        """_collect_args should join tuple metavar into a string (line 150)."""
        from repo_release_tools.docs.api_index import _collect_args

        parser = argparse.ArgumentParser(prog="test")
        parser.add_argument("pair", nargs=2, metavar=("FROM", "TO"), help="Source and dest.")
        args = _collect_args(parser)
        pair_arg = next(a for a in args if a.dest == "pair")
        assert pair_arg.metavar == "FROM TO"


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


class TestRenderApiMd:
    """render_api_md produces a Markdown document."""

    @pytest.fixture
    def sample_entries(self) -> list[ApiEntry]:
        return [
            ApiEntry(
                name="rrt foo",
                description="The foo command.",
                arguments=[
                    ArgInfo(
                        flags=["--bar", "-b"],
                        dest="bar",
                        help="Bar option.",
                        default="baz",
                        required=False,
                        metavar="VAL",
                        choices=None,
                    )
                ],
                hook_id="rrt-foo",
            ),
            ApiEntry(name="rrt foo sub", description="Sub command.", arguments=[]),
        ]

    def test_produces_markdown_heading(self, sample_entries: list[ApiEntry]) -> None:
        result = render_api_md(sample_entries)
        assert "# rrt API Index" in result

    def test_contains_entry_names(self, sample_entries: list[ApiEntry]) -> None:
        result = render_api_md(sample_entries)
        assert "rrt foo" in result
        assert "rrt foo sub" in result

    def test_contains_hook_id(self, sample_entries: list[ApiEntry]) -> None:
        result = render_api_md(sample_entries)
        assert "rrt-foo" in result

    def test_contains_argument_table(self, sample_entries: list[ApiEntry]) -> None:
        result = render_api_md(sample_entries)
        assert "--bar" in result
        assert "Bar option." in result

    def test_empty_entries_returns_heading_only(self) -> None:
        result = render_api_md([])
        assert "# rrt API Index" in result

    def test_no_hook_id_omits_hook_line(self) -> None:
        entries = [ApiEntry(name="rrt cmd", description="A command.", hook_id=None)]
        result = render_api_md(entries)
        assert "Pre-commit hook" not in result


class TestRenderApiTxt:
    """render_api_txt produces plain text."""

    def test_contains_entry_separator(self) -> None:
        entries = [ApiEntry(name="rrt baz", description="Baz.", arguments=[])]
        result = render_api_txt(entries)
        assert "=== rrt baz ===" in result

    def test_contains_description(self) -> None:
        entries = [ApiEntry(name="rrt qux", description="Qux desc.")]
        result = render_api_txt(entries)
        assert "Qux desc." in result

    def test_contains_hook_id(self) -> None:
        entries = [ApiEntry(name="rrt h", description="", hook_id="rrt-h")]
        result = render_api_txt(entries)
        assert "rrt-h" in result

    def test_contains_argument_flags(self) -> None:
        arg = ArgInfo(
            flags=["--flag"],
            dest="flag",
            help="A flag.",
            default=None,
            required=True,
            metavar=None,
            choices=None,
        )
        entries = [ApiEntry(name="rrt cmd", description="", arguments=[arg])]
        result = render_api_txt(entries)
        assert "--flag" in result
        assert "[required]" in result


class TestRenderApiJson:
    """render_api_json produces valid JSON."""

    def test_produces_valid_json(self) -> None:
        entries = [ApiEntry(name="rrt a", description="A.")]
        raw = render_api_json(entries)
        parsed = json.loads(raw)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "rrt a"

    def test_serialises_arguments(self) -> None:
        arg = ArgInfo(
            flags=["--x"],
            dest="x",
            help="X.",
            default=None,
            required=False,
            metavar=None,
            choices=["p", "q"],
        )
        entries = [ApiEntry(name="rrt x", description="", arguments=[arg])]
        raw = render_api_json(entries)
        parsed = json.loads(raw)
        assert parsed[0]["arguments"][0]["choices"] == ["p", "q"]


# ---------------------------------------------------------------------------
# _cmd_api integration (via cmd_docs dispatch)
# ---------------------------------------------------------------------------


def _extract_json_from_output(output: str) -> list[object]:
    """Extract and parse the JSON array from styled stdout output.

    DryRunPrinter writes a styled header/footer to the same stdout stream as
    the machine-readable JSON body.  This helper strips the surrounding noise
    by finding the outermost ``[…]`` span.
    """
    json_start = output.find("[")
    json_end = output.rfind("]") + 1
    assert json_start >= 0, "No '[' found in stdout; JSON not written"
    assert json_end > json_start, "No ']' found after '[' in stdout; JSON not complete"
    return json.loads(output[json_start:json_end])  # type: ignore[return-value]


class TestCmdApi:
    """Integration tests for the rrt docs api sub-action."""

    def _api_args(self, **overrides: object) -> SimpleNamespace:
        defaults: dict[str, object] = {
            "docs_action": "api",
            "format": "md",
            "output": None,
            "root": ".",
            "dry_run": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_cmd_api_stdout_md(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print Markdown API index to stdout."""
        from repo_release_tools.commands.docs_cmd import _cmd_api

        args = self._api_args(format="md")
        rc = _cmd_api(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "# rrt API Index" in out

    def test_cmd_api_stdout_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print JSON API index to stdout (may include styled header/footer)."""
        from repo_release_tools.commands.docs_cmd import _cmd_api

        args = self._api_args(format="json")
        rc = _cmd_api(args)
        assert rc == 0
        out = capsys.readouterr().out
        parsed = _extract_json_from_output(out)
        assert isinstance(parsed, list)
        assert len(parsed) > 0

    def test_cmd_api_stdout_txt(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print plain-text API index to stdout."""
        from repo_release_tools.commands.docs_cmd import _cmd_api

        args = self._api_args(format="txt")
        rc = _cmd_api(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "===" in out

    def test_cmd_api_write_to_file(self, tmp_path: Path) -> None:
        """Should write the API index to the specified output file."""
        from repo_release_tools.commands.docs_cmd import _cmd_api

        output_file = tmp_path / "api.md"
        args = self._api_args(format="md", output=str(output_file), root=str(tmp_path))
        rc = _cmd_api(args)
        assert rc == 0
        assert output_file.exists()
        assert "# rrt API Index" in output_file.read_text(encoding="utf-8")

    def test_cmd_api_dry_run_with_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dry-run mode should not write the file and should print a would_write line."""
        from repo_release_tools.commands.docs_cmd import _cmd_api

        output_file = tmp_path / "api.md"
        args = self._api_args(format="md", output=str(output_file), dry_run=True, root=str(tmp_path))
        rc = _cmd_api(args)
        assert rc == 0
        assert not output_file.exists()
        out = capsys.readouterr().out
        assert str(output_file) in out

    def test_cmd_api_dry_run_no_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Dry-run without --output should still print to stdout."""
        from repo_release_tools.commands.docs_cmd import _cmd_api

        args = self._api_args(format="md", dry_run=True)
        rc = _cmd_api(args)
        assert rc == 0

    def test_cmd_api_unsupported_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An unrecognised format should return exit code 1."""
        from repo_release_tools.commands.docs_cmd import _cmd_api

        args = self._api_args(format="xml")
        rc = _cmd_api(args)
        assert rc == 1

    def test_cmd_docs_dispatches_api(self, capsys: pytest.CaptureFixture[str]) -> None:
        """cmd_docs should dispatch to _cmd_api when docs_action == 'api'."""
        from repo_release_tools.commands.docs_cmd import cmd_docs

        args = self._api_args(docs_action="api", format="json")
        rc = cmd_docs(args)
        assert rc == 0
        out = capsys.readouterr().out
        parsed = _extract_json_from_output(out)
        assert isinstance(parsed, list)

    def test_cmd_api_relative_output_path(self, tmp_path: Path) -> None:
        """A relative --output path should be resolved against --root."""
        from repo_release_tools.commands.docs_cmd import _cmd_api

        args = self._api_args(
            format="md",
            output="out/api.md",
            root=str(tmp_path),
        )
        rc = _cmd_api(args)
        assert rc == 0
        expected = tmp_path / "out" / "api.md"
        assert expected.exists()
