"""Built-in folder templates."""

from __future__ import annotations

from repo_release_tools.config import FolderScaffoldFile, FolderTemplate


def _file(path: str, content: str = "") -> FolderScaffoldFile:
    """Create a scaffold file entry."""
    return FolderScaffoldFile(path=path, content=content)


BUILTIN_FOLDER_TEMPLATES: dict[str, FolderTemplate] = {
    "cargo-inspired": FolderTemplate(
        name="cargo-inspired",
        description="Strict Rust crate structure inspired by Cargo workspaces.",
        strictness="strict",
        required_files=("Cargo.toml", "README.md", "src/lib.rs"),
        required_dirs=("src",),
        allowed_files=("build.rs",),
        allowed_dirs=("tests", "benches", "examples"),
        scaffold_dirs=("src",),
        scaffold_files=(
            _file("Cargo.toml", '[package]\nname = "example"\nversion = "0.1.0"\n'),
            _file("README.md", "# Example\n"),
            _file("src/lib.rs", "pub fn placeholder() {}\n"),
        ),
    ),
    "python-package": FolderTemplate(
        name="python-package",
        description="Python package layout with src and tests.",
        strictness="strict",
        required_files=("pyproject.toml", "README.md", "src/package/__init__.py"),
        required_dirs=("src", "tests"),
        scaffold_dirs=("src/package", "tests"),
        scaffold_files=(
            _file("pyproject.toml", '[project]\nname = "example"\nversion = "0.1.0"\n'),
            _file("README.md", "# Example\n"),
            _file("src/package/__init__.py", '"""Example package."""\n'),
            _file("tests/test_smoke.py", "def test_smoke() -> None:\n    assert True\n"),
        ),
    ),
    "javascript-package": FolderTemplate(
        name="javascript-package",
        description="JavaScript or TypeScript package layout.",
        strictness="strict",
        required_files=("package.json", "README.md", "src/index.ts"),
        required_dirs=("src",),
        allowed_dirs=("test", "tests"),
        scaffold_dirs=("src",),
        scaffold_files=(
            _file("package.json", '{\n  "name": "example",\n  "version": "0.1.0"\n}\n'),
            _file("README.md", "# Example\n"),
            _file("src/index.ts", "export const placeholder = true;\n"),
        ),
    ),
    "go-module": FolderTemplate(
        name="go-module",
        description="Go module layout.",
        strictness="strict",
        required_files=("go.mod", "README.md", "cmd/main.go"),
        required_dirs=("cmd",),
        scaffold_dirs=("cmd",),
        scaffold_files=(
            _file("go.mod", "module example\n\ngo 1.24\n"),
            _file("README.md", "# Example\n"),
            _file("cmd/main.go", "package main\n\nfunc main() {}\n"),
        ),
    ),
    "docs-only": FolderTemplate(
        name="docs-only",
        description="Documentation-focused layout.",
        strictness="strict",
        required_files=("README.md", "docs/index.md"),
        required_dirs=("docs",),
        scaffold_dirs=("docs",),
        scaffold_files=(
            _file("README.md", "# Documentation\n"),
            _file("docs/index.md", "# Index\n"),
        ),
    ),
    "cli-tool": FolderTemplate(
        name="cli-tool",
        description="Command-line tool layout.",
        strictness="strict",
        required_files=("README.md", "src/main.py"),
        required_dirs=("src",),
        allowed_dirs=("tests",),
        scaffold_dirs=("src",),
        scaffold_files=(
            _file("README.md", "# CLI Tool\n"),
            _file("src/main.py", "def main() -> int:\n    return 0\n"),
        ),
    ),
    "library-module": FolderTemplate(
        name="library-module",
        description="Generic library/module layout.",
        strictness="strict",
        required_files=("README.md", "src/index.txt"),
        required_dirs=("src",),
        scaffold_dirs=("src",),
        scaffold_files=(
            _file("README.md", "# Library\n"),
            _file("src/index.txt", "library module placeholder\n"),
        ),
    ),
    "bash-powershell-project": FolderTemplate(
        name="bash-powershell-project",
        description="Script project with Bash and PowerShell entrypoints.",
        strictness="strict",
        required_files=("README.md", "scripts/main.sh", "scripts/main.ps1"),
        required_dirs=("scripts",),
        scaffold_dirs=("scripts",),
        scaffold_files=(
            _file("README.md", "# Script Project\n"),
            _file("scripts/main.sh", "#!/usr/bin/env bash\n"),
            _file("scripts/main.ps1", 'Write-Output "placeholder"\n'),
        ),
    ),
    "monorepo-workspace": FolderTemplate(
        name="monorepo-workspace",
        description="Monorepo workspace with packages and docs.",
        strictness="strict",
        required_files=("README.md", "packages/.gitkeep", "docs/index.md"),
        required_dirs=("packages", "docs"),
        scaffold_dirs=("packages", "docs"),
        scaffold_files=(
            _file("README.md", "# Workspace\n"),
            _file("packages/.gitkeep"),
            _file("docs/index.md", "# Workspace docs\n"),
        ),
    ),
    "plugin-extension": FolderTemplate(
        name="plugin-extension",
        description="Plugin or extension project skeleton.",
        strictness="strict",
        required_files=("README.md", "manifest.json", "src/extension.ts"),
        required_dirs=("src",),
        scaffold_dirs=("src",),
        scaffold_files=(
            _file("README.md", "# Plugin\n"),
            _file("manifest.json", '{"name": "example-plugin"}\n'),
            _file("src/extension.ts", "export function activate(): void {}\n"),
        ),
    ),
    "loose-starter": FolderTemplate(
        name="loose-starter",
        description="Very loose starter template with minimal constraints.",
        strictness="loose",
        scaffold_files=(_file("README.md", "# Starter\n"),),
        allow_patterns=("*", "**/*"),
    ),
    "loose-validate": FolderTemplate(
        name="loose-validate",
        description="Validation-only loose profile for gently supervising an existing tree.",
        strictness="loose",
        allow_patterns=("*", "**/*"),
    ),
}


def resolve_builtin_template(name: str) -> FolderTemplate | None:
    """Return one built-in template by *name*."""
    return BUILTIN_FOLDER_TEMPLATES.get(name)
