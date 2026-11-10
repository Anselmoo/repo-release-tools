"""Tests for ``repo_release_tools.architecture.core`` (findings for ``rrt arch check``)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from repo_release_tools.architecture.core import (
    FINDING_KINDS,
    Finding,
    collect_findings,
    root_module_name,
)
from repo_release_tools.config.arch_config import _load_architecture_config
from repo_release_tools.config.model import ArchitectureConfig

PKG = "src/pkg"
ROLE_FILES = {"unit": ["__init__.py", "README.md"]}


def build(repo: Path, files: dict[str, str]) -> Path:
    """Create *files* (path -> text) under *repo* and return *repo*."""
    for rel, text in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return repo


def make_config(
    units: Sequence[str | Mapping[str, object]],
    *,
    layers: list[str] | None = None,
    layers_sync: str = "none",
    top_level_files: list[str] | None = None,
    required_files: dict[str, list[str]] | None = None,
    root: str = PKG,
) -> ArchitectureConfig:
    """Build a validated ArchitectureConfig; plain unit names become ``unit`` packages."""
    raw: dict[str, object] = {
        "root": root,
        "top_level_files": top_level_files if top_level_files is not None else ["__init__.py"],
        "layers": layers or [],
        "layers_sync": layers_sync,
        "required_files": required_files if required_files is not None else {},
        "units": [{"name": u} if isinstance(u, str) else u for u in units],
    }
    config = _load_architecture_config(raw)
    assert config is not None
    return config


def pkg_files(*units: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a minimal package tree: root init plus ``__init__.py`` for each unit."""
    files = {f"{PKG}/__init__.py": ""}
    files.update({f"{PKG}/{unit}/__init__.py": "" for unit in units})
    files.update(extra or {})
    return files


def ids(findings: list[Finding], kind: str | None = None) -> list[str]:
    """Return finding ids, optionally restricted to one kind."""
    return [f.id for f in findings if kind is None or f.kind == kind]


# ---------------------------------------------------------------------------
# Finding / root_module_name
# ---------------------------------------------------------------------------


def test_finding_id_order_and_equality_ignore_message() -> None:
    """Ids are ``kind:subject``; ordering and equality never look at the message."""
    first = Finding("missing-unit", "src/a", "one text")
    same = Finding("missing-unit", "src/a", "another text")
    later = Finding("undeclared", "src/a")
    assert first.id == "missing-unit:src/a"
    assert first == same
    assert first < later
    assert sorted([later, first]) == [first, later]
    assert FINDING_KINDS[0] == "missing-unit"
    assert len(set(FINDING_KINDS)) == len(FINDING_KINDS) == 7


def test_root_module_name_plain_and_nested(tmp_path: Path) -> None:
    """Walk up while the parent is a package: ``src/a/b`` below ``a/__init__.py`` is ``a.b``."""
    (tmp_path / "src" / "spectrafit").mkdir(parents=True)
    assert root_module_name(tmp_path / "src" / "spectrafit") == "spectrafit"

    (tmp_path / "src" / "a" / "b").mkdir(parents=True)
    (tmp_path / "src" / "a" / "__init__.py").write_text("")
    assert root_module_name(tmp_path / "src" / "a" / "b") == "a.b"


def test_root_module_name_relative_path_and_filesystem_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative directory is made absolute; the walk stops at the filesystem root."""
    (tmp_path / "pkg").mkdir()
    monkeypatch.chdir(tmp_path)
    assert root_module_name(Path("pkg")) == "pkg"
    assert root_module_name(Path("/")) == ""


# ---------------------------------------------------------------------------
# insider-shaped fixture (design section 1, verbatim)
# ---------------------------------------------------------------------------

INSIDER_RAW = {
    "root": "src/spectrafit",
    "top_level_files": ["__init__.py", "errors.py", "py.typed", "README.md"],
    "layers": ["mcp", "model | project", "steps | schema", "errors"],
    "layers_sync": "importlinter",
    "required_files": {
        "door": ["__init__.py", "README.md"],
        "unit": ["__init__.py", "README.md"],
        "foundation": ["__init__.py", "README.md"],
    },
    "units": [
        {"name": "mcp", "role": "door"},
        {"name": "model"},
        {"name": "project"},
        {"name": "prepare", "package": "prep", "prefix": "prep"},
        {"name": "read"},
        {"name": "fit"},
        {"name": "assess"},
        {"name": "show"},
        {"name": "report"},
        {"name": "steps"},
        {"name": "schema", "role": "foundation"},
        {"name": "errors", "module": "errors", "role": "foundation"},
    ],
}

INSIDER_PYPROJECT = """
[tool.importlinter]
root_package = "spectrafit"

[[tool.importlinter.contracts]]
name = "layers"
type = "layers"
containers = ["spectrafit"]
layers = ["mcp", "model | project", "steps | schema", "errors"]
"""


def insider_repo(repo: Path) -> Path:
    """Build the insider tree where only six of twelve declared units exist."""
    files = {
        "src/spectrafit/__init__.py": "",
        "src/spectrafit/py.typed": "",
        "src/spectrafit/README.md": "",
        "src/spectrafit/errors.py": "class SpectraError(Exception): ...\n",
        "pyproject.toml": INSIDER_PYPROJECT,
    }
    for unit in ("mcp", "model", "project", "steps", "schema"):
        files[f"src/spectrafit/{unit}/__init__.py"] = ""
        files[f"src/spectrafit/{unit}/README.md"] = ""
    files["src/spectrafit/mcp/tool.py"] = (
        "from spectrafit.model import data\nimport spectrafit.errors\n"
    )
    files["src/spectrafit/model/data.py"] = "from spectrafit.steps import run\n"
    files["src/spectrafit/steps/run.py"] = "from spectrafit.errors import SpectraError\n"
    (repo / "src").mkdir(parents=True, exist_ok=True)
    return build(repo, files)


def test_insider_fixture_reports_only_the_six_missing_units(tmp_path: Path) -> None:
    """Six declared-but-absent units are the only findings; layers-sync matches."""
    repo = insider_repo(tmp_path)
    config = _load_architecture_config(INSIDER_RAW)
    assert config is not None

    findings = collect_findings(config, repo)

    assert ids(findings) == [
        "missing-unit:src/spectrafit/assess",
        "missing-unit:src/spectrafit/fit",
        "missing-unit:src/spectrafit/prep",
        "missing-unit:src/spectrafit/read",
        "missing-unit:src/spectrafit/report",
        "missing-unit:src/spectrafit/show",
    ]
    assert "prepare" in findings[2].message


def test_insider_fixture_missing_module_unit(tmp_path: Path) -> None:
    """A module unit whose ``<module>.py`` is absent is a missing-unit with the file path."""
    repo = insider_repo(tmp_path)
    (repo / "src/spectrafit/errors.py").unlink()
    config = _load_architecture_config(INSIDER_RAW)
    assert config is not None

    findings = collect_findings(config, repo)

    assert "missing-unit:src/spectrafit/errors.py" in ids(findings)
    assert ids(findings, "missing-file") == []


# ---------------------------------------------------------------------------
# undeclared
# ---------------------------------------------------------------------------


def undeclared_repo(repo: Path) -> Path:
    """Root with one unit, noise that must be skipped, and real strays."""
    build(repo, pkg_files("alpha", extra={f"{PKG}/extra.py": "", f"{PKG}/scratch/x.txt": ""}))
    for noise in ("__pycache__", ".mypy_cache", "build", "node_modules"):
        (repo / PKG / noise).mkdir()
    (repo / PKG / ".DS_Store").write_text("")
    (repo / PKG / "__pycache__" / "x.pyc").write_bytes(b"")
    return repo


def test_undeclared_skips_noise_and_reports_strays(tmp_path: Path) -> None:
    """``__pycache__``, dot-entries and ignore_dir_names() are never undeclared."""
    repo = undeclared_repo(tmp_path)
    config = make_config(["alpha"], required_files={"unit": ["__init__.py"]})

    findings = collect_findings(config, repo)

    assert ids(findings) == [f"undeclared:{PKG}/extra.py", f"undeclared:{PKG}/scratch"]
    assert all(f.message for f in findings)


def test_undeclared_is_ignored_filter_gets_all_candidates_once(tmp_path: Path) -> None:
    """``is_ignored`` is called once with every candidate and its answer is dropped."""
    repo = undeclared_repo(tmp_path)
    config = make_config(["alpha"])
    calls: list[list[str]] = []

    def is_ignored(paths: list[str]) -> set[str]:
        """Record the call and ignore the scratch directory."""
        calls.append(list(paths))
        return {f"{PKG}/scratch"}

    findings = collect_findings(config, repo, is_ignored=is_ignored)

    assert calls == [[f"{PKG}/extra.py", f"{PKG}/scratch"]]
    assert ids(findings, "undeclared") == [f"undeclared:{PKG}/extra.py"]


def test_undeclared_is_ignored_not_called_without_candidates(tmp_path: Path) -> None:
    """With nothing to filter the callback (a git subprocess upstream) is skipped."""
    repo = build(tmp_path, pkg_files("alpha"))
    config = make_config(["alpha"])

    def is_ignored(paths: list[str]) -> set[str]:
        """Fail if called."""
        raise AssertionError("must not be called")

    assert collect_findings(config, repo, is_ignored=is_ignored) == []


def test_top_level_files_and_module_unit_entries_are_allowed(tmp_path: Path) -> None:
    """Files named in top_level_files and ``<module>.py`` unit entries are declared."""
    repo = build(tmp_path, pkg_files(extra={f"{PKG}/errors.py": "", f"{PKG}/py.typed": ""}))
    config = make_config(
        [{"name": "errors", "module": "errors"}], top_level_files=["__init__.py", "py.typed"]
    )

    assert collect_findings(config, repo) == []


# ---------------------------------------------------------------------------
# missing-unit / missing-file / unplaced
# ---------------------------------------------------------------------------


def test_missing_file_for_existing_packages_only(tmp_path: Path) -> None:
    """Role files plus unit files are required for existing package units, never modules."""
    repo = build(
        tmp_path,
        pkg_files(
            "has_all",
            "lacks_readme",
            extra={f"{PKG}/has_all/README.md": "", f"{PKG}/errors.py": ""},
        ),
    )
    config = make_config(
        [
            "has_all",
            "lacks_readme",
            {"name": "extra_need", "required_files": ["CHANGES.md"]},
            {"name": "errors", "module": "errors", "role": "foundation"},
            "gone",
        ],
        required_files={"unit": ["__init__.py", "README.md"], "foundation": ["__init__.py"]},
        top_level_files=["__init__.py"],
    )
    (repo / PKG / "extra_need").mkdir()

    findings = collect_findings(config, repo)

    assert ids(findings, "missing-file") == [
        f"missing-file:{PKG}/extra_need/CHANGES.md",
        f"missing-file:{PKG}/extra_need/README.md",
        f"missing-file:{PKG}/extra_need/__init__.py",
        f"missing-file:{PKG}/lacks_readme/README.md",
    ]
    assert ids(findings, "missing-unit") == [f"missing-unit:{PKG}/gone"]


def test_unplaced_only_for_existing_units_when_layers_set(tmp_path: Path) -> None:
    """An existing unit outside ``layers`` is unplaced; absent ones and empty layers are not."""
    repo = build(tmp_path, pkg_files("top", "stray"))
    placed = make_config(["top", "stray", "future"], layers=["top"])
    unplaced = collect_findings(placed, repo)
    assert ids(unplaced, "unplaced") == [f"unplaced:{PKG}/stray"]
    assert ids(unplaced, "missing-unit") == [f"missing-unit:{PKG}/future"]

    free = make_config(["top", "stray"])
    assert ids(collect_findings(free, repo), "unplaced") == []


# ---------------------------------------------------------------------------
# layer-import
# ---------------------------------------------------------------------------


def layered(
    repo: Path, files: dict[str, str], layers: list[str], units: list[str] | None = None
) -> list[Finding]:
    """Build ``pkg_files`` plus *files* and return only the layer-import findings."""
    names = units or sorted({n for spec in layers for n in spec.replace(":", "|").split("|")})
    names = [n.strip().strip("()") for n in names]
    build(repo, {**pkg_files(*names), **files})
    config = make_config(names, layers=layers, top_level_files=["__init__.py", "helpers.py"])
    return [f for f in collect_findings(config, repo) if f.kind == "layer-import"]


def test_lower_imports_higher_is_reported_with_line(tmp_path: Path) -> None:
    """Importing a higher layer is a violation; the message carries the first line."""
    findings = layered(
        tmp_path,
        {f"{PKG}/low/a.py": "import os\n\nfrom pkg.top import b\nfrom pkg.top import b\n"},
        ["top", "mid", "low"],
        units=["top", "mid", "low"],
    )
    assert ids(findings) == [f"layer-import:{PKG}/low/a.py -> {PKG}/top/__init__.py"]
    assert "line 3" in findings[0].message
    assert "'low'" in findings[0].message and "'top'" in findings[0].message


def test_downward_same_unit_and_unlayered_imports_are_fine(tmp_path: Path) -> None:
    """Higher importing lower, a unit importing itself, and third-party imports are allowed."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/top/a.py": "from pkg.low import b\nimport os.path\nfrom os import path\n",
            f"{PKG}/low/b.py": "from pkg.low import c\nfrom . import c\n",
            f"{PKG}/low/c.py": "",
            f"{PKG}/helpers.py": "from pkg.top import a\n",
        },
        ["top", "low"],
    )
    assert findings == []


def test_from_package_import_submodule_targets_the_submodule(tmp_path: Path) -> None:
    """``from pkg.top import api`` edges to ``top/api.py``; a plain name edges to ``__init__``."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/top/api.py": "",
            f"{PKG}/low/a.py": "from pkg.top import api\n",
            f"{PKG}/low/b.py": "from pkg.top import not_a_module, other as o\nfrom pkg.top.api import X\n",
            f"{PKG}/low/c.py": "from pkg.top import *\n",
        },
        ["top", "low"],
    )
    assert ids(findings) == [
        f"layer-import:{PKG}/low/a.py -> {PKG}/top/api.py",
        f"layer-import:{PKG}/low/b.py -> {PKG}/top/__init__.py",
        f"layer-import:{PKG}/low/b.py -> {PKG}/top/api.py",
        f"layer-import:{PKG}/low/c.py -> {PKG}/top/__init__.py",
    ]


def test_import_statement_uses_longest_existing_prefix(tmp_path: Path) -> None:
    """``import pkg.top.api.Cls`` resolves to the longest known module prefix."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/top/api.py": "",
            f"{PKG}/low/a.py": "import pkg.top.api.Cls\n",
            f"{PKG}/low/b.py": "import pkg.top, pkg.low.b\n",
        },
        ["top", "low"],
    )
    assert ids(findings) == [
        f"layer-import:{PKG}/low/a.py -> {PKG}/top/api.py",
        f"layer-import:{PKG}/low/b.py -> {PKG}/top/__init__.py",
    ]


def test_relative_imports_are_resolved(tmp_path: Path) -> None:
    """``from ..top import x``, ``from .. import top`` and ``from . import`` resolve properly."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/low/a.py": "from ..top import x\n",
            f"{PKG}/low/b.py": "from .. import top\n",
            f"{PKG}/low/sub/__init__.py": "from ...top import y\nfrom . import leaf\n",
            f"{PKG}/low/sub/leaf.py": "from .. import a\nfrom .... import nowhere\n",
            f"{PKG}/low/__init__.py": "from .sub import leaf\n",
            f"{PKG}/low/d.py": "from . import sub\nfrom .. import helpers\n",
        },
        ["top", "low"],
    )
    assert ids(findings) == [
        f"layer-import:{PKG}/low/a.py -> {PKG}/top/__init__.py",
        f"layer-import:{PKG}/low/b.py -> {PKG}/top/__init__.py",
        f"layer-import:{PKG}/low/sub/__init__.py -> {PKG}/top/__init__.py",
    ]


def test_type_checking_and_function_level_imports_count(tmp_path: Path) -> None:
    """Every import node counts, including ``TYPE_CHECKING`` blocks and function bodies."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/low/a.py": (
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from pkg.top import b\n"
            ),
            f"{PKG}/low/c.py": "def f():\n    import pkg.top\n",
        },
        ["top", "low"],
    )
    assert ids(findings) == [
        f"layer-import:{PKG}/low/a.py -> {PKG}/top/__init__.py",
        f"layer-import:{PKG}/low/c.py -> {PKG}/top/__init__.py",
    ]
    assert "line 3" in findings[0].message
    assert "line 2" in findings[1].message


def test_named_module_import_does_not_pull_in_the_root_init(tmp_path: Path) -> None:
    """``from pkg.helpers import X`` edges to helpers only, not through the root ``__init__``."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/__init__.py": "from pkg.top import a\n",
            f"{PKG}/helpers.py": "",
            f"{PKG}/low/a.py": "from pkg.helpers import X\nfrom pkg import helpers\n",
        },
        ["top", "low"],
    )
    assert findings == []


def test_indirect_chain_through_root_init_is_reported_with_path(tmp_path: Path) -> None:
    """low -> root __init__ (unlayered) -> top is reported once with the shortest path."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/__init__.py": "from pkg.top import a\nfrom pkg.helpers import h\n",
            f"{PKG}/helpers.py": "from pkg.top import a\n",
            f"{PKG}/low/a.py": "x = 1\nimport pkg\n",
            f"{PKG}/low/b.py": "from pkg import VERSION\n",
        },
        ["top", "low"],
    )
    assert ids(findings) == [
        f"layer-import:{PKG}/low/a.py -> {PKG}/top/__init__.py",
        f"layer-import:{PKG}/low/b.py -> {PKG}/top/__init__.py",
    ]
    assert "via pkg" in findings[0].message
    assert "line 2" in findings[0].message
    assert findings[0].message.startswith("pkg.low.a imports pkg.top via pkg ")


def test_longest_chain_lists_every_hop_and_stops_at_layers(tmp_path: Path) -> None:
    """A chain walks only through unlayered modules; a layered hop ends the search."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/h1.py": "import pkg.h2\n",
            f"{PKG}/h2.py": "import pkg.top\n",
            f"{PKG}/low/a.py": "import pkg.h1\n",
            f"{PKG}/mid/m.py": "import pkg.top\n",
            f"{PKG}/low/b.py": "import pkg.mid.m\n",
        },
        ["top", "mid", "low"],
        units=["top", "mid", "low"],
    )
    assert ids(findings) == [
        f"layer-import:{PKG}/low/a.py -> {PKG}/top/__init__.py",
        f"layer-import:{PKG}/low/b.py -> {PKG}/mid/m.py",
        f"layer-import:{PKG}/mid/m.py -> {PKG}/top/__init__.py",
    ]
    assert "via pkg.h1 -> pkg.h2" in findings[0].message


def test_direct_edge_takes_precedence_over_a_chain(tmp_path: Path) -> None:
    """When a direct edge and a chain connect the same pair only the direct one is reported."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/__init__.py": "from pkg.top import a\n",
            f"{PKG}/low/a.py": "import pkg\nimport pkg.top\n",
        },
        ["top", "low"],
    )
    assert len(findings) == 1
    assert "via" not in findings[0].message


def test_independent_siblings_violate_in_both_directions(tmp_path: Path) -> None:
    """``a | b``: a->b and b->a are both findings; same-unit and downward imports are not."""
    findings = layered(
        tmp_path,
        {
            f"{PKG}/a/x.py": "from pkg.b import y\nfrom pkg.a import z\nfrom pkg.low import q\n",
            f"{PKG}/b/y.py": "from pkg.a import x\n",
            f"{PKG}/a/z.py": "",
            f"{PKG}/low/q.py": "",
        },
        ["a | b", "low"],
        units=["a", "b", "low"],
    )
    assert ids(findings) == [
        f"layer-import:{PKG}/a/x.py -> {PKG}/b/y.py",
        f"layer-import:{PKG}/b/y.py -> {PKG}/a/x.py",
    ]
    assert "independent siblings" in findings[0].message


def test_colon_siblings_may_import_each_other(tmp_path: Path) -> None:
    """``a : b`` siblings are allowed to import each other."""
    findings = layered(
        tmp_path,
        {f"{PKG}/a/x.py": "from pkg.b import y\n", f"{PKG}/b/y.py": "from pkg.a import x\n"},
        ["a : b"],
        units=["a", "b"],
    )
    assert findings == []


def test_module_unit_and_unplaced_units_in_layers(tmp_path: Path) -> None:
    """A module unit takes part in layering; units outside ``layers`` are unlayered."""
    build(
        tmp_path,
        {
            **pkg_files("top", "free"),
            f"{PKG}/errors.py": "from pkg.top import a\n",
            f"{PKG}/free/f.py": "from pkg.top import a\nimport pkg.errors\n",
            f"{PKG}/top/a.py": "import pkg.errors\n",
        },
    )
    config = make_config(
        ["top", "free", {"name": "errors", "module": "errors", "role": "foundation"}],
        layers=["top", "errors"],
    )
    findings = [f for f in collect_findings(config, tmp_path) if f.kind == "layer-import"]
    assert ids(findings) == [f"layer-import:{PKG}/errors.py -> {PKG}/top/a.py"]


def test_unparsable_unreadable_and_skipped_files(tmp_path: Path) -> None:
    """Unparsable files are findings; non-py, dot and cache entries never count."""
    build(
        tmp_path,
        {
            **pkg_files("top", "low"),
            f"{PKG}/low/bad.py": "def (:\n",
            f"{PKG}/low/data.txt": "from pkg.top import a\n",
            f"{PKG}/low/.hidden.py": "from pkg.top import a\n",
            f"{PKG}/low/__pycache__/c.py": "from pkg.top import a\n",
            f"{PKG}/low/.venv/c.py": "from pkg.top import a\n",
            f"{PKG}/low/nul.py": "x = 1\x00\n",
        },
    )
    (tmp_path / PKG / "low" / "dangling.py").symlink_to(tmp_path / "nowhere.py")
    config = make_config(["top", "low"], layers=["top", "low"])

    findings = collect_findings(config, tmp_path)

    assert [f for f in findings if f.kind == "layer-import"] == []
    unparsable = [f for f in findings if f.kind == "unparsable"]
    assert ids(unparsable) == [
        f"unparsable:{PKG}/low/bad.py",
        f"unparsable:{PKG}/low/dangling.py",
        f"unparsable:{PKG}/low/nul.py",
    ]
    assert "imports are unchecked" in unparsable[0].message


def test_subpackage_named_like_tool_output_is_scanned(tmp_path: Path) -> None:
    """``build``/``env``/``dist`` inside a unit are real subpackages, not ignored output."""
    build(
        tmp_path,
        {
            **pkg_files("top", "low"),
            f"{PKG}/low/build/__init__.py": "",
            f"{PKG}/low/build/c.py": "from pkg.top import a\n",
            f"{PKG}/low/env/d.py": "import pkg.top\n",
        },
    )
    config = make_config(["top", "low"], layers=["top", "low"])

    findings = [f for f in collect_findings(config, tmp_path) if f.kind == "layer-import"]

    assert ids(findings) == [
        f"layer-import:{PKG}/low/build/c.py -> {PKG}/top/__init__.py",
        f"layer-import:{PKG}/low/env/d.py -> {PKG}/top/__init__.py",
    ]


def test_root_module_name_stops_at_the_repo_root(tmp_path: Path) -> None:
    """A stray ``__init__.py`` at or above the repo root never leaks into the module name."""
    repo = tmp_path / "repo"
    build(tmp_path, {"__init__.py": "", "repo/__init__.py": "", "repo/src/__init__.py": ""})
    (repo / "src" / "pkg").mkdir()

    root_dir = repo / "src" / "pkg"

    assert root_module_name(root_dir) == f"{tmp_path.name}.repo.src.pkg"
    assert root_module_name(root_dir, repo) == "src.pkg"
    assert root_module_name(root_dir, repo / "src") == "pkg"
    assert root_module_name(root_dir, tmp_path / "elsewhere") == "pkg"


def test_nested_root_module_and_namespace_root(tmp_path: Path) -> None:
    """Root below a parent package is dotted; a root without ``__init__`` still works."""
    build(
        tmp_path,
        {
            "src/outer/__init__.py": "",
            "src/outer/pkg/top/__init__.py": "",
            "src/outer/pkg/low/__init__.py": "",
            "src/outer/pkg/low/a.py": (
                "from outer.pkg.top import b\nfrom .. import q\nfrom ... import r\nimport outer\n"
            ),
        },
    )
    config = make_config(
        ["top", "low"], layers=["top", "low"], root="src/outer/pkg", top_level_files=[]
    )
    findings = [f for f in collect_findings(config, tmp_path) if f.kind == "layer-import"]
    assert ids(findings) == ["layer-import:src/outer/pkg/low/a.py -> src/outer/pkg/top/__init__.py"]

    ns = tmp_path / "ns"
    build(
        ns,
        {
            f"{PKG}/top/__init__.py": "",
            f"{PKG}/low/__init__.py": "import pkg\nfrom pkg import top\n",
        },
    )
    ns_findings = collect_findings(config_for_ns(), ns)
    assert ids(ns_findings, "layer-import") == [
        f"layer-import:{PKG}/low/__init__.py -> {PKG}/top/__init__.py"
    ]


def config_for_ns() -> ArchitectureConfig:
    """Config for the namespace-root tree (no root ``__init__.py``)."""
    return make_config(["top", "low"], layers=["top", "low"], top_level_files=[])


# ---------------------------------------------------------------------------
# layers-sync
# ---------------------------------------------------------------------------


def sync_findings(
    repo: Path,
    pyproject: str | None,
    layers: list[str],
    *,
    units: list[str] | list[dict[str, object]] | None = None,
    layers_sync: str = "importlinter",
) -> list[Finding]:
    """Return layers-sync findings for a tree whose units all exist."""
    names = units or ["a", "b", "c"]
    plain = [u if isinstance(u, str) else str(u["name"]) for u in names]
    package_dirs = {
        (u["package"] if isinstance(u, dict) and "package" in u else n)
        for u, n in zip(names, plain)
    }
    build(repo, pkg_files(*(str(d) for d in package_dirs)))
    if pyproject is not None:
        (repo / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    config = make_config(names, layers=layers, layers_sync=layers_sync)
    return [f for f in collect_findings(config, repo) if f.kind == "layers-sync"]


def contract(*layers: str, containers: str = '["pkg"]', kind: str = "layers") -> str:
    """Return a ``[[tool.importlinter.contracts]]`` TOML block."""
    quoted = ", ".join(f'"{layer}"' for layer in layers)
    return (
        "[[tool.importlinter.contracts]]\n"
        f'name = "c"\ntype = "{kind}"\ncontainers = {containers}\nlayers = [{quoted}]\n'
    )


def test_layers_sync_equal_contract_gives_no_finding(tmp_path: Path) -> None:
    """An exactly equal contract (names, separators, order) is in sync."""
    assert sync_findings(tmp_path, contract("a", "b | c"), ["a", "b | c"]) == []


def test_layers_sync_ignored_when_not_requested_or_no_layers(tmp_path: Path) -> None:
    """``layers_sync = "none"`` and an empty ``layers`` never produce a finding."""
    assert sync_findings(tmp_path, None, ["a"], layers_sync="none") == []
    other = tmp_path / "other"
    assert sync_findings(other, None, []) == []


def test_layers_sync_missing_pyproject_or_contract(tmp_path: Path) -> None:
    """No pyproject, invalid TOML, no contracts, wrong type or wrong containers: one finding."""
    missing = sync_findings(tmp_path / "m", None, ["a", "b"])
    assert ids(missing) == ["layers-sync:pyproject.toml"]
    assert 'containers = ["pkg"]' in missing[0].message
    assert "'a', 'b'" in missing[0].message

    for index, text in enumerate(
        [
            "not = valid = toml",
            "[tool]\nimportlinter = 3\n",
            "tool = 1\n",
            "[tool.importlinter]\ncontracts = 5\n",
            contract("a", "b", kind="forbidden"),
            contract("a", "b", containers='["other"]'),
            contract("a", "b", containers='["pkg", "other"]'),
            "[[tool.importlinter.contracts]]\ntype = 'layers'\ncontainers = ['pkg']\nlayers = 3\n",
            "[[tool.importlinter.contracts]]\ntype = 'layers'\ncontainers = ['pkg']\nlayers = [1]\n",
            "tool.importlinter.contracts = [1, 2]\n",
        ]
    ):
        found = sync_findings(tmp_path / f"v{index}", text, ["a", "b"])
        assert ids(found) == ["layers-sync:pyproject.toml"], text
        assert "no [[tool.importlinter.contracts]]" in found[0].message


def test_layers_sync_mismatch_shows_expected_and_found(tmp_path: Path) -> None:
    """Different order, separator, optional mark or an invalid layer string all differ."""
    cases = [
        (["b", "a"], "order"),
        (["a | b"], "separator"),
        (["a : b"], "separator colon"),
        (["(a)", "b"], "optional"),
        (["a", "b", "c"], "extra layer"),
        (["a | b : c", "b"], "invalid"),
    ]
    for index, (specs, label) in enumerate(cases):
        found = sync_findings(tmp_path / f"c{index}", contract(*specs), ["a", "b"])
        assert ids(found) == ["layers-sync:pyproject.toml"], label
        assert "expected: 'a', 'b'" in found[0].message, label
        assert "found: " + ", ".join(repr(s) for s in specs) in found[0].message, label


def test_layers_sync_sibling_order_within_a_layer_is_ignored(tmp_path: Path) -> None:
    """``b | c`` equals ``c | b``; the separator and the layer order still count."""
    assert sync_findings(tmp_path / "same", contract("a", "c | b"), ["a", "b | c"]) == []
    colon = sync_findings(tmp_path / "colon", contract("a", "c : b"), ["a", "b | c"])
    assert ids(colon) == ["layers-sync:pyproject.toml"]


def test_layers_sync_second_contract_may_match(tmp_path: Path) -> None:
    """Any layers contract for the root container that equals the declaration is enough."""
    text = contract("b", "a") + contract("a", "b")
    assert sync_findings(tmp_path, text, ["a", "b"]) == []


def test_layers_sync_translates_unit_names_and_keeps_optional_marks(tmp_path: Path) -> None:
    """Unit names map to import names (``prepare`` -> ``prep``); ``(x)`` marks must match."""
    units: list[dict[str, object]] = [
        {"name": "prepare", "package": "prep"},
        {"name": "a"},
        {"name": "b"},
    ]
    layers = ["prepare | a", "(b)"]
    ok = sync_findings(tmp_path / "ok", contract("prep | a", "(b)"), layers, units=units)
    assert ok == []

    bad = sync_findings(tmp_path / "bad", contract("prepare | a", "(b)"), layers, units=units)
    assert ids(bad) == ["layers-sync:pyproject.toml"]
    assert "expected: 'prep | a', '(b)'" in bad[0].message


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_findings_are_sorted_by_id_and_deduplicated(tmp_path: Path) -> None:
    """The result is sorted by id with each id at most once."""
    repo = build(
        tmp_path,
        pkg_files("top", "low", extra={f"{PKG}/zz.py": "", f"{PKG}/aa.py": ""}),
    )
    config = make_config(["top", "low", "gone", "other"], layers=["top"])

    findings = collect_findings(config, repo)

    assert ids(findings) == sorted(ids(findings))
    assert len(set(ids(findings))) == len(findings)
    assert {f.kind for f in findings} == {"missing-unit", "undeclared", "unplaced"}


def test_relative_cwd_root_yields_same_ids_as_absolute_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolving ``.`` after ``chdir`` gives byte-identical ids to the absolute tmp root."""
    repo = insider_repo(tmp_path / "repo")
    (repo / "src/spectrafit/stray.py").write_text("from spectrafit.steps import run\n")
    (repo / "src/spectrafit/steps/bad.py").write_text("from spectrafit.mcp import tool\n")
    config = _load_architecture_config(INSIDER_RAW)
    assert config is not None

    absolute = collect_findings(config, repo.resolve())
    monkeypatch.chdir(repo)
    relative = collect_findings(config, Path(".").resolve())

    assert ids(relative) == ids(absolute)
    assert "layer-import:src/spectrafit/steps/bad.py -> src/spectrafit/mcp/tool.py" in ids(absolute)
    assert "undeclared:src/spectrafit/stray.py" in ids(absolute)
