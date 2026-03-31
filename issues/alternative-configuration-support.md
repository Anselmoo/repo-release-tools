## Problem
Currently, the configuration example for the tool uses `pyproject.toml` for release metadata, which is specific to Python projects. If `repo-release-tools` is to work effectively for JavaScript, Rust, or other non-Python projects, there needs to be support for alternative configuration files.

## Proposed Solution
Allow specifying or auto-detecting an alternative configuration file (e.g., `rrt.toml` or `repo-release-tools.toml`), which will follow the same `[tool.rrt]` structure for use with JavaScript and other ecosystems.

### Example:
```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"
lock_command = ["uv", "lock", "-U"]

[[tool.rrt.version_targets]]
path = "package.json"
kind = "npm"
```

## Motivation
This will provide a unified configuration experience across ecosystems and make `repo-release-tools` more flexible and widely usable.
