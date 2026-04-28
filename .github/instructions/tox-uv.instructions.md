---
name: tox-uv multi-Python testing
description: >
  How to run the test suite against all supported Python versions (3.12, 3.13, 3.14)
  locally using tox with the tox-uv plugin. Use this whenever you need to reproduce
  a version-specific test failure, verify a fix across all supported interpreters,
  compare behaviour between Python versions, or add a new Python version to the matrix.
applyTo: "pyproject.toml"
---

# tox-uv — Multi-Python Local Testing

`tox-uv` replaces tox's default virtualenv + pip with `uv`, making per-interpreter
environment creation fast. The test matrix (3.12, 3.13, 3.14) mirrors the CI matrix in
`.github/workflows/cicd.yml`.

## Preferred invocation — zero install with `uvx`

No machine-wide installation needed:

```bash
# All three Python versions in parallel (recommended)
uvx --with tox-uv tox -p auto

# Single version
uvx --with tox-uv tox -e 3.14

# Compare two versions side by side
uvx --with tox-uv tox -e 3.13,3.14

# Pass extra pytest arguments (posargs)
uvx --with tox-uv tox -e 3.14 -- tests/test_cli.py -xvs
```

## Optional persistent install (once per machine)

```bash
uv tool install tox --with tox-uv
tox --version   # should list tox-uv as a registered plugin
```

After installing, the `uvx --with tox-uv` prefix can be dropped:

```bash
tox -p auto
tox -e 3.14
```

## Configuration (in pyproject.toml)

The matrix lives under `[tool.tox]`:

- **`requires = ["tox>=4", "tox-uv>=1"]`** — declares the tox-uv plugin as a tox
  requirement; `uvx --with tox-uv` satisfies this automatically.
- **`env_list = ["3.12", "3.13", "3.14"]`** — bare version numbers; tox-uv resolves
  these to the matching `uv`-managed Python interpreters.
- **`dependency_groups = ["dev"]`** — installs the `[dependency-groups] dev` group
  (pytest, pytest-cov, ruff, ty) into each tox environment via `uv sync`.
- **`skip_missing_interpreters = true`** — silently skips any version not installed
  locally instead of hard-failing the whole run.
- **`{posargs}`** — forwards any arguments after `--` directly to pytest.

## Comparing behaviour across Python versions

When a test fails on one version but passes on another, run the two versions together
to see both outputs in one session:

```bash
# Compare 3.13 vs 3.14 for a specific test
uvx --with tox-uv tox -e 3.13,3.14 -- tests/test_cli.py::test_decolor_returns_plain_text -xvs

# Run all three and diff the results
uvx --with tox-uv tox -p auto -- tests/test_cli.py -v
```

## Debugging a version-specific failure

```bash
# Full output for the failing version
uvx --with tox-uv tox -e 3.14 -- -xvs

# Recreate the environment from scratch (clears cached venv)
uvx --with tox-uv tox -e 3.14 --recreate

# Inspect which interpreter was resolved
uvx --with tox-uv tox -e 3.14 --listenvs-all -v
```

## Adding a new Python version

1. Add the version string to `env_list` in `[tool.tox]` in `pyproject.toml`.
2. Add it to `matrix.python-version` in `.github/workflows/cicd.yml`.
3. Add the classifier `"Programming Language :: Python :: 3.XY"` under `[project]`.

## Key design choices

| Choice | Reason |
|---|---|
| `uvx --with tox-uv tox` | Zero install; always uses the latest tox-uv — no local tool management |
| Bare version numbers (`"3.14"`) | tox-uv resolves these via uv's Python management — no `base_python` needed |
| `requires` in `[tool.tox]` | Self-documenting; ensures tox-uv is always active for this project |
| `dependency_groups` only | Mirrors `uv sync --all-groups` — no separate requirements file to maintain |
| `skip_missing_interpreters` | Prevents CI-like hard failures on machines missing one interpreter |
