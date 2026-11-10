"""CLI tests for `rrt arch check`, `rrt arch baseline` and `rrt arch new`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_release_tools.cli import build_parser
from repo_release_tools.commands import arch_cmd
from repo_release_tools.state import arch_baseline_path, read_arch_baseline

_HEADER = (
    '[project]\nname = "demo"\nversion = "0.1.0"\n\n'
    "[tool.rrt]\n\n"
    '[[tool.rrt.version_targets]]\npath = "pyproject.toml"\nkind = "pep621"\n'
)

_ARCH = """
[tool.rrt.architecture]
root = "src/pkg"
top_level_files = ["__init__.py"]
layers = ["api", "core", "errors"]

[tool.rrt.architecture.required_files]
unit = ["__init__.py", "README.md"]

[[tool.rrt.architecture.units]]
name = "api"
role = "door"

[[tool.rrt.architecture.units]]
name = "core"

[[tool.rrt.architecture.units]]
name = "errors"
module = "errors"
role = "foundation"
"""


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(tmp_path: Path, *, arch: str | None = _ARCH, clean: bool = True) -> Path:
    """Build a repo; *clean* makes `arch check` find nothing."""
    repo = tmp_path / "repo"
    _write(repo / "pyproject.toml", _HEADER + (arch or ""))
    pkg = repo / "src" / "pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "api" / "__init__.py", "from pkg import core\n")
    _write(pkg / "core" / "__init__.py", "from pkg import errors\n")
    _write(pkg / "core" / "README.md", "# core\n")
    _write(pkg / "errors.py")
    if not clean:
        _write(pkg / "stray.py")  # undeclared
    return repo


def _run(*argv: str) -> int:
    args = build_parser().parse_args(["arch", *argv])
    return args.handler(args)


def _templates(repo: Path, *, body: str = "X = '$name'\n", next_steps: str = '["wire it"]') -> None:
    kind = repo / ".rrt" / "templates" / "step"
    _write(
        kind / "kind.toml",
        f'description = "A step"\nrequires_unit = true\nnext_steps = {next_steps}\n',
    )
    _write(kind / "files" / "${root}" / "${unit_package}" / "${name}.py.tmpl", body)


# --- rrt arch (no subcommand) -------------------------------------------------


def test_arch_without_subcommand_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    """`rrt arch` alone prints help and exits 1."""
    assert _run() == 1
    assert "check" in capsys.readouterr().out


# --- rrt arch check -----------------------------------------------------------


def test_check_clean_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A tree that matches the declaration has no findings."""
    repo = _repo(tmp_path)
    assert _run("check", "--root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "No findings." in out
    assert "Baseline: none" in out


def test_check_with_default_relative_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default root ``.`` is resolved, so ids are repo-relative (the B1 lesson)."""
    repo = _repo(tmp_path, clean=False)
    monkeypatch.chdir(repo)
    assert _run("check") == 0
    assert "undeclared:src/pkg/stray.py" in capsys.readouterr().out


def test_check_is_advisory_without_strict(tmp_path: Path) -> None:
    """Findings alone never fail a non-strict check."""
    assert _run("check", "--root", str(_repo(tmp_path, clean=False))) == 0


def test_check_strict_fails_on_new_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--strict`` exits 1 on a finding not in the baseline."""
    repo = _repo(tmp_path, clean=False)
    assert _run("check", "--strict", "--root", str(repo)) == 1
    captured = capsys.readouterr()
    assert "[new] undeclared:src/pkg/stray.py" in captured.out
    assert "Architecture drift: 1 finding(s): 1 new, 0 baselined, 0 stale" in captured.err


def test_check_strict_passes_with_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Baselined findings are listed but do not fail ``--strict``."""
    repo = _repo(tmp_path, clean=False)
    assert _run("baseline", "--root", str(repo)) == 0
    capsys.readouterr()
    assert _run("check", "--strict", "--root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "Baseline: .rrt/architecture.baseline.toml" in out
    assert "[new]" not in out
    assert "1 baselined" in out


def test_check_strict_fails_on_stale_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A baseline entry that is no longer found must be removed: stale fails ``--strict``."""
    repo = _repo(tmp_path, clean=False)
    assert _run("baseline", "--root", str(repo)) == 0
    (repo / "src" / "pkg" / "stray.py").unlink()
    capsys.readouterr()
    assert _run("check", "--root", str(repo)) == 0
    assert "[stale] undeclared:src/pkg/stray.py" in capsys.readouterr().out
    assert _run("check", "--strict", "--root", str(repo)) == 1


def test_check_not_configured(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Without the table, the command explains and exits 1."""
    repo = _repo(tmp_path, arch=None)
    assert _run("check", "--root", str(repo)) == 1
    assert "[tool.rrt.architecture] is not configured." in capsys.readouterr().err


def test_check_without_config_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """No config file at all exits 1 with the loader's reason."""
    assert _run("check", "--root", str(tmp_path)) == 1
    assert "Could not load [tool.rrt] config" in capsys.readouterr().err


def test_check_invalid_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A config error is reported, not raised."""
    repo = _repo(tmp_path, arch='\n[tool.rrt.architecture]\nroot = "src/pkg"\nlayers = ["x"]\n')
    assert _run("check", "--root", str(repo)) == 1
    assert "no declared unit" in capsys.readouterr().err


def test_check_missing_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A root directory that does not exist exits 1."""
    repo = _repo(tmp_path, arch=_ARCH.replace('root = "src/pkg"', 'root = "src/nope"'))
    assert _run("check", "--root", str(repo)) == 1
    assert "Architecture root 'src/nope' does not exist." in capsys.readouterr().err


def test_check_skips_gitignored_entries(tmp_path: Path) -> None:
    """A gitignored entry under the root is never `undeclared`."""
    repo = _repo(tmp_path)
    _write(repo / "src" / "pkg" / "generated.py")
    _write(repo / ".gitignore", "src/pkg/generated.py\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    assert _run("check", "--strict", "--root", str(repo)) == 0


# --- rrt arch baseline --------------------------------------------------------


def test_baseline_seed_then_up_to_date(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The first run writes today's findings; an unchanged list is not rewritten."""
    repo = _repo(tmp_path, clean=False)
    assert _run("baseline", "--root", str(repo)) == 0
    path = arch_baseline_path(repo)
    assert read_arch_baseline(path) == ["undeclared:src/pkg/stray.py"]
    out = capsys.readouterr().out
    assert "+ undeclared:src/pkg/stray.py" in out
    assert "Wrote .rrt/architecture.baseline.toml" in out
    before = path.read_text(encoding="utf-8")
    assert _run("baseline", "--root", str(repo)) == 0
    assert "Baseline is up to date." in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == before


def test_baseline_dry_run_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--dry-run`` previews the write."""
    repo = _repo(tmp_path, clean=False)
    assert _run("baseline", "--dry-run", "--root", str(repo)) == 0
    assert not arch_baseline_path(repo).exists()
    out = capsys.readouterr().out
    assert "Would update" in out
    assert "no changes made" in out


def test_baseline_shrinks_and_refuses_additions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Resolved entries are removed; a new finding is not added and exits 1."""
    repo = _repo(tmp_path, clean=False)
    assert _run("baseline", "--root", str(repo)) == 0
    (repo / "src" / "pkg" / "stray.py").unlink()
    _write(repo / "src" / "pkg" / "other.py")
    capsys.readouterr()
    assert _run("baseline", "--root", str(repo)) == 1
    captured = capsys.readouterr()
    assert "- undeclared:src/pkg/stray.py" in captured.out
    assert "[new] undeclared:src/pkg/other.py" in captured.err
    assert "1 new finding(s) not added" in captured.err
    assert read_arch_baseline(arch_baseline_path(repo)) == []


def test_baseline_force_adds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``--force`` rewrites the baseline including new findings."""
    repo = _repo(tmp_path)
    assert _run("baseline", "--root", str(repo)) == 0
    _write(repo / "src" / "pkg" / "other.py")
    capsys.readouterr()
    assert _run("baseline", "--force", "--root", str(repo)) == 0
    assert "+ undeclared:src/pkg/other.py" in capsys.readouterr().out
    assert read_arch_baseline(arch_baseline_path(repo)) == ["undeclared:src/pkg/other.py"]


def test_baseline_not_configured(tmp_path: Path) -> None:
    """Without the table, baseline exits 1."""
    assert _run("baseline", "--root", str(_repo(tmp_path, arch=None))) == 1


# --- rrt arch new -------------------------------------------------------------


def test_new_dry_run_prints_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A dry run lists each target and body, and writes nothing."""
    repo = _repo(tmp_path)
    _templates(repo, body="X = '${name}'")  # no trailing newline
    assert _run("new", "step", "normalize", "--unit", "core", "--dry-run", "--root", str(repo)) == 0
    out = capsys.readouterr().out
    assert "src/pkg/core/normalize.py" in out
    assert "X = 'normalize'\n" in out
    assert not (repo / "src" / "pkg" / "core" / "normalize.py").exists()


def test_new_writes_and_prints_next_steps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A write renders the files and prints the kind's next steps."""
    repo = _repo(tmp_path)
    _templates(repo)
    assert _run("new", "step", "normalize", "--unit", "core", "--root", str(repo)) == 0
    target = repo / "src" / "pkg" / "core" / "normalize.py"
    assert target.read_text(encoding="utf-8") == "X = 'normalize'\n"
    out = capsys.readouterr().out
    assert "create: src/pkg/core/normalize.py" in out
    assert "wire it" in out


def test_new_reports_a_failed_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An OSError during the write is an error message and exit 1, not a traceback."""
    repo = _repo(tmp_path)
    _templates(repo)

    def fail(_files: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(arch_cmd, "write_rendered", fail)
    assert _run("new", "step", "normalize", "--unit", "core", "--root", str(repo)) == 1
    assert "Writing the rendered files failed: denied" in capsys.readouterr().err


def test_new_refuses_existing_target_even_in_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An existing target is refused before the dry-run branch; ``--force`` overwrites."""
    repo = _repo(tmp_path)
    _templates(repo)
    target = repo / "src" / "pkg" / "core" / "normalize.py"
    _write(target, "old\n")
    argv = ("new", "step", "normalize", "--unit", "core", "--root", str(repo))
    assert _run(*argv, "--dry-run") == 1
    assert "already exists" in capsys.readouterr().err
    assert _run(*argv, "--force") == 0
    assert "overwrite: src/pkg/core/normalize.py" in capsys.readouterr().out
    assert target.read_text(encoding="utf-8") == "X = 'normalize'\n"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (("new", "step"), "Usage: rrt arch new <kind> <name>"),
        (("new", "step", "x", "--unit", "ghost"), "Unknown unit 'ghost'. Declared units: api"),
        (("new", "nope", "x"), "Unknown template kind 'nope'"),
        (("new", "step", "Bad"), "Invalid name 'Bad'"),
        (("new", "step", "--check-templates"), "--check-templates takes no kind or name."),
    ],
)
def test_new_refusals(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: tuple[str, ...],
    message: str,
) -> None:
    """Every refusal exits 1 with a reason on stderr."""
    repo = _repo(tmp_path)
    _templates(repo)
    assert _run(*argv, "--root", str(repo)) == 1
    assert message in capsys.readouterr().err


def test_new_not_configured(tmp_path: Path) -> None:
    """Without the table, new exits 1."""
    assert _run("new", "step", "x", "--root", str(_repo(tmp_path, arch=None))) == 1


def test_check_templates_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A valid kind passes the self-test."""
    repo = _repo(tmp_path)
    _templates(repo)
    assert _run("new", "--check-templates", "--root", str(repo)) == 0
    assert "1 kind(s) ok" in capsys.readouterr().out


def test_check_templates_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A kind whose rendered Python does not compile fails the self-test."""
    repo = _repo(tmp_path)
    _templates(repo, body="def (:\n")
    assert _run("new", "--check-templates", "--root", str(repo)) == 1
    err = capsys.readouterr().err
    assert "step" in err
    assert "1 of 1 kind(s) failed the self-test." in err


def test_check_templates_without_kinds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """No kinds is a warning, not a failure."""
    repo = _repo(tmp_path)
    assert _run("new", "--check-templates", "--root", str(repo)) == 0
    assert "No kinds under .rrt/templates/." in capsys.readouterr().out
