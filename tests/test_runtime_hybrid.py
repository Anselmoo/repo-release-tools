from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


@dataclass(frozen=True)
class RuntimeCase:
    name: str
    required_bins: tuple[str, ...]
    expected_before: str
    expected_after: str
    app_command: tuple[str, ...]
    setup: Callable[[Path, dict[str, str]], None]
    version_file: str
    lock_file: str | None = None
    command_env: Callable[[Path], dict[str, str]] | None = None


def _run(
    cmd: list[str] | tuple[str, ...],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(cmd),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(cmd)}\n"
            f"cwd={cwd}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def _init_git_repo(repo: Path) -> None:
    _run(["git", "init", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.name", "Repo Release Tools"], cwd=repo)
    _run(["git", "config", "user.email", "rrt@example.invalid"], cwd=repo)
    _run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "feat: initial hello world"], cwd=repo)


def _rrt_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else f"{SRC}{os.pathsep}{existing}"
    return env


def _repo_command_env(repo: Path, *, include_python_src: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    cache_root = repo.parent / f".{repo.name}-runtime-cache"
    env["UV_CACHE_DIR"] = str(cache_root / "uv")
    env["NPM_CONFIG_CACHE"] = str(cache_root / "npm")
    env["GOCACHE"] = str(cache_root / "go-build")
    env["GOMODCACHE"] = str(cache_root / "go-mod")
    env["CARGO_HOME"] = str(cache_root / "cargo")
    if include_python_src:
        package_src = str(repo / "src")
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = package_src if not existing else f"{package_src}{os.pathsep}{existing}"
    return env


def _default_command_env(repo: Path) -> dict[str, str]:
    return _repo_command_env(repo)


def _python_command_env(repo: Path) -> dict[str, str]:
    env = _repo_command_env(repo, include_python_src=True)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_rrt_bump(repo: Path, env: dict[str, str]) -> None:
    command_env = _rrt_env()
    command_env.update(env)
    _run(
        [sys.executable, "-m", "repo_release_tools", "bump", "patch", "--no-commit"],
        cwd=repo,
        env=command_env,
    )


def _assert_runtime_flow(case: RuntimeCase, tmp_path: Path) -> None:
    missing = [binary for binary in case.required_bins if shutil.which(binary) is None]
    if missing:
        pytest.skip(f"Missing runtime toolchain(s) for {case.name}: {', '.join(missing)}")

    repo = tmp_path / case.name
    repo.mkdir()
    command_env = (
        case.command_env(repo) if case.command_env is not None else _default_command_env(repo)
    )

    case.setup(repo, command_env)
    _init_git_repo(repo)

    before = _run(case.app_command, cwd=repo, env=command_env).stdout.strip()
    assert before == case.expected_before

    _run_rrt_bump(repo, command_env)

    after = _run(case.app_command, cwd=repo, env=command_env).stdout.strip()
    assert after == case.expected_after
    assert case.expected_after in (repo / case.version_file).read_text(encoding="utf-8")
    assert f"## [{case.expected_after}]" in (repo / "CHANGELOG.md").read_text(encoding="utf-8")

    if case.lock_file is not None:
        assert (repo / case.lock_file).exists()


def _setup_python_repo(repo: Path, env: dict[str, str]) -> None:
    package_dir = repo / "src" / "hello_python"
    package_dir.mkdir(parents=True)
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"

[[tool.rrt.version_targets]]
path = "src/hello_python/__init__.py"
pattern = '^(\\s*__version__\\s*=\\s*")([^"]+)(")'

[project]
name = "hello-python"
version = "0.1.0"
requires-python = ">=3.12"
""",
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    (package_dir / "__main__.py").write_text(
        """\
from hello_python import __version__

print(__version__)
""",
        encoding="utf-8",
    )
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n", encoding="utf-8")
    _run(["uv", "lock", "-U"], cwd=repo, env=env)


def _setup_node_repo(repo: Path, env: dict[str, str]) -> None:
    (repo / "package.json").write_text(
        """\
{
  "name": "hello-node",
  "version": "0.1.0",
  "private": true,
  "main": "index.js",
  "rrt": {
    "changelog_file": "CHANGELOG.md",
    "version_targets": [
      {
        "path": "package.json",
        "kind": "package_json"
      }
    ]
  }
}
""",
        encoding="utf-8",
    )
    (repo / "index.js").write_text(
        """\
const pkg = require("./package.json");
console.log(pkg.version);
""",
        encoding="utf-8",
    )
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n", encoding="utf-8")
    _run(["npm", "install", "--package-lock-only"], cwd=repo, env=env)


def _setup_rust_repo(repo: Path, env: dict[str, str]) -> None:
    src_dir = repo / "src"
    src_dir.mkdir()
    (repo / ".gitignore").write_text("target/\n", encoding="utf-8")
    (repo / "Cargo.toml").write_text(
        """\
[package]
name = "hello-rust"
version = "0.1.0"
edition = "2021"

[package.metadata.rrt]
changelog_file = "CHANGELOG.md"

[[package.metadata.rrt.version_targets]]
path = "Cargo.toml"
section = "package"
field = "version"
""",
        encoding="utf-8",
    )
    (src_dir / "main.rs").write_text(
        """\
fn main() {
    println!("{}", env!("CARGO_PKG_VERSION"));
}
""",
        encoding="utf-8",
    )
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n", encoding="utf-8")
    _run(["cargo", "generate-lockfile"], cwd=repo, env=env)


def _setup_go_repo(repo: Path, env: dict[str, str]) -> None:
    internal_dir = repo / "internal" / "version"
    internal_dir.mkdir(parents=True)
    (repo / ".rrt.toml").write_text(
        """\
[tool.rrt]
changelog_file = "CHANGELOG.md"

[[tool.rrt.version_targets]]
path = "internal/version/version.go"
pattern = '^(const Value = ")([^"]+)(")$'
""",
        encoding="utf-8",
    )
    (repo / "go.mod").write_text(
        """\
module example.com/hello-go

go 1.22
""",
        encoding="utf-8",
    )
    (internal_dir / "version.go").write_text(
        """\
package version

const Value = "0.1.0"
""",
        encoding="utf-8",
    )
    (repo / "main.go").write_text(
        """\
package main

import (
    "fmt"

    "example.com/hello-go/internal/version"
)

func main() {
    fmt.Println(version.Value)
}
""",
        encoding="utf-8",
    )
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n", encoding="utf-8")
    _run(["go", "mod", "tidy"], cwd=repo, env=env)


RUNTIME_CASES = [
    RuntimeCase(
        name="python",
        required_bins=("uv",),
        expected_before="0.1.0",
        expected_after="0.1.1",
        app_command=(sys.executable, "-m", "hello_python"),
        setup=_setup_python_repo,
        version_file="src/hello_python/__init__.py",
        lock_file="uv.lock",
        command_env=_python_command_env,
    ),
    RuntimeCase(
        name="node",
        required_bins=("node", "npm"),
        expected_before="0.1.0",
        expected_after="0.1.1",
        app_command=("node", "index.js"),
        setup=_setup_node_repo,
        version_file="package.json",
        lock_file="package-lock.json",
    ),
    RuntimeCase(
        name="rust",
        required_bins=("cargo", "rustc"),
        expected_before="0.1.0",
        expected_after="0.1.1",
        app_command=("cargo", "run", "--quiet"),
        setup=_setup_rust_repo,
        version_file="Cargo.toml",
        lock_file="Cargo.lock",
    ),
    RuntimeCase(
        name="go",
        required_bins=("go",),
        expected_before="0.1.0",
        expected_after="0.1.1",
        app_command=("go", "run", "."),
        setup=_setup_go_repo,
        version_file="internal/version/version.go",
    ),
]


@pytest.mark.runtime
@pytest.mark.parametrize("case", RUNTIME_CASES, ids=lambda case: case.name)
def test_hybrid_runtime_bump_updates_running_examples(case: RuntimeCase, tmp_path: Path) -> None:
    _assert_runtime_flow(case, tmp_path)
