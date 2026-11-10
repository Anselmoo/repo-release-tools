"""Tests for `rrt-hooks arch-check` and its `.pre-commit-hooks.yaml` entry."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_release_tools.docs.api_index import load_hooks
from repo_release_tools.workflow import hooks

_REPO_ROOT = Path(__file__).resolve().parents[2]

_PYPROJECT = """\
[project]
name = "demo"
version = "0.1.0"

[tool.rrt]

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[tool.rrt.architecture]
root = "src/pkg"
top_level_files = ["__init__.py"]
layers = ["api", "core"]

[[tool.rrt.architecture.units]]
name = "api"
role = "door"

[[tool.rrt.architecture.units]]
name = "core"
"""


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(tmp_path: Path, *, planted: bool = False) -> Path:
    """Build a git repo whose skeleton is clean, or carries one planted finding."""
    repo = tmp_path / "repo"
    _write(repo / "pyproject.toml", _PYPROJECT)
    pkg = repo / "src" / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "api" / "__init__.py", "from pkg import core\n")
    _write(pkg / "core" / "__init__.py")
    if planted:
        # core sits below api, so this import breaks the layer order.
        _write(pkg / "core" / "__init__.py", "from pkg import api\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def _template(repo: Path, body: str) -> None:
    kind = repo / ".rrt" / "templates" / "step"
    _write(kind / "kind.toml", 'description = "A step"\n')
    _write(kind / "files" / "${root}" / "${name}.py.tmpl", body)


def test_clean_repo_passes_with_the_default_relative_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_repo(tmp_path))
    assert hooks.main(["arch-check"]) == 0


def test_planted_finding_fails_with_the_default_relative_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(_repo(tmp_path, planted=True))
    assert hooks.main(["arch-check"]) == 1
    captured = capsys.readouterr()
    assert "[new] layer-import:" in captured.out
    assert "Architecture drift" in captured.err


def test_explicit_root_is_honoured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, planted=True)
    monkeypatch.chdir(tmp_path)
    assert hooks.main(["arch-check", "--root", "repo"]) == 1
    assert hooks.main(["arch-check", "--root", str(_repo(tmp_path / "clean"))]) == 0
    assert repo.is_dir()


def test_baselined_finding_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from repo_release_tools.cli import build_parser

    monkeypatch.chdir(_repo(tmp_path, planted=True))
    args = build_parser().parse_args(["arch", "baseline"])
    assert args.handler(args) == 0
    assert hooks.main(["arch-check"]) == 0


def test_missing_config_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / "pyproject.toml", _PYPROJECT.split("[tool.rrt.architecture]")[0])
    monkeypatch.chdir(tmp_path)
    assert hooks.main(["arch-check"]) == 1
    assert "[tool.rrt.architecture] is not configured." in capsys.readouterr().err


def test_check_templates_runs_the_self_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    _template(repo, "X = '$name'\n")
    monkeypatch.chdir(repo)
    assert hooks.main(["arch-check", "--check-templates"]) == 0


def test_check_templates_failure_fails_a_clean_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    _template(repo, "def broken(:\n")
    monkeypatch.chdir(repo)
    assert hooks.main(["arch-check"]) == 0  # templates only run on request
    assert hooks.main(["arch-check", "--check-templates"]) == 1
    assert "1 of 1 kind(s) failed the self-test." in capsys.readouterr().err


def test_check_templates_still_runs_after_a_failed_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, planted=True)
    _template(repo, "X = '$name'\n")
    monkeypatch.chdir(repo)
    assert hooks.main(["arch-check", "--check-templates"]) == 1
    assert "Template self-test" in capsys.readouterr().out


def test_pre_commit_hook_entry_is_published() -> None:
    assert load_hooks(_REPO_ROOT)["rrt-hooks arch-check"] == "rrt-arch-check"
    text = (_REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    block = text.split("- id: rrt-arch-check\n", 1)[1].split("\n\n", 1)[0]
    assert "pass_filenames: false" in block
    assert "always_run: true" in block
