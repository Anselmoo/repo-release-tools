---
name: tox-uv multi-Python testing
description: >
  How to run the test suite against all supported Python versions (3.12, 3.13, 3.14)
  locally using tox with the tox-uv plugin. Use this whenever you need to reproduce
  a version-specific test failure, verify a fix across all supported interpreters, or
  add a new Python version to the test matrix.
applyTo: "pyproject.toml"
---

# tox-uv — Multi-Python Local Testing

`tox-uv` replaces tox's default virtualenv + pip with `uv`, making per-interpreter
environment creation fast. The test matrix mirrors the CI matrix in
`.github/workflows/cicd.yml`.

## Installation (once per machine)

tox is installed as a standalone tool — **not** in the project's dev dependencies:

```bash
uv tool install tox --with tox-uv
```

Verify:

```bash
tox --version   # should show tox-uv listed as a plugin
```

## Running the matrix

```bash
# All three Python versions in parallel
tox -p auto

# Single version
tox -e py314

# Pass extra pytest arguments (posargs)
tox -e py314 -- tests/test_cli.py -xvs

# Only unit tests, verbose
tox -e py312 -- -v -m "not runtime"
```

## Configuration (in pyproject.toml)

The matrix is defined under `[tool.tox]`:

- **`runner = "uv-venv-runner"`** — uses uv instead of virtualenv/pip for environment
  creation and package installs; significantly faster cold starts.
- **`dependency_groups = ["dev"]`** — installs the `[dependency-groups] dev` group from
  `pyproject.toml` (pytest, pytest-cov, ruff, ty) into each tox environment.
- **`skip_missing_interpreters = true`** — silently skips environments whose Python
  interpreter is not installed locally rather than hard-failing the whole run.
- **`{posargs}`** in commands — forwards any arguments after `--` directly to pytest.

## Adding a new Python version

1. Add the interpreter to `env_list` and add a `[tool.tox.env.pyXYZ]` section with
   `base_python = "python3.XY"` in `pyproject.toml`.
2. Add the version to the `matrix.python-version` list in `.github/workflows/cicd.yml`.
3. Add the classifier `"Programming Language :: Python :: 3.XY"` under `[project]`.

## Debugging version-specific failures

```bash
# Run only the failing test file on the affected version
tox -e py314 -- tests/test_cli.py -xvs

# Check which interpreter tox resolved
tox -e py314 --listenvs-all -v

# Recreate the environment from scratch
tox -e py314 --recreate
```

## Key design choices

| Choice | Reason |
|---|---|
| `uv-venv-runner` | Consistent with the rest of the project's uv-first toolchain |
| dev group only | Mirrors `uv sync --all-groups` — no separate tox-specific requirements file |
| Tool install, not dev dep | tox itself doesn't need to be a project dependency; `uv tool` keeps it isolated |
| `skip_missing_interpreters` | Prevents CI-like hard failures on developer machines missing one version |
