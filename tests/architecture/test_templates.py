"""Tests for ``architecture/templates.py`` (rendering and self-test of template kinds)."""

from __future__ import annotations

from pathlib import Path

import pytest

from repo_release_tools.architecture import templates as t
from repo_release_tools.config import ArchitectureConfig, ArchUnit

ROOT_MODULE = "myapp"


def _config(*units: ArchUnit) -> ArchitectureConfig:
    """Return an architecture config with *units* under ``src/myapp``."""
    return ArchitectureConfig(root="src/myapp", units=units)


UNIT = ArchUnit(name="activities", package="acts", prefix="act")
CONFIG = _config(UNIT)


def make_kind(
    repo: Path,
    kind: str,
    files: dict[str, str | bytes],
    toml: str | None = "",
) -> Path:
    """Create ``.rrt/templates/<kind>/`` with *files* (relative to ``files/``)."""
    directory = repo / ".rrt" / "templates" / kind
    directory.mkdir(parents=True, exist_ok=True)
    if toml is not None:
        (directory / "kind.toml").write_text(toml, encoding="utf-8")
    for rel, content in files.items():
        path = directory / "files" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return directory


def render(
    repo: Path,
    kind: str,
    *,
    name: str = "prep_step",
    unit: ArchUnit | None = UNIT,
    force: bool = False,
) -> list[t.RenderedFile]:
    """Load, build variables for and render *kind*."""
    loaded = t.load_kind(repo, kind)
    variables = t.build_variables(
        config=CONFIG, root_module=ROOT_MODULE, name=name, unit=unit, kind=loaded
    )
    return t.render_kind(loaded, variables, repo, force=force)


def test_pascal_case() -> None:
    """Snake case becomes PascalCase."""
    assert t.pascal_case("prep_step") == "PrepStep"
    assert t.pascal_case("a__b2") == "AB2"


def test_list_kinds(tmp_path: Path) -> None:
    """Only directories with kind.toml count, sorted; absent dir gives []."""
    assert t.list_kinds(tmp_path) == []
    make_kind(tmp_path, "zeta", {"a.py.tmpl": ""})
    make_kind(tmp_path, "alpha", {"a.py.tmpl": ""})
    make_kind(tmp_path, "nokind", {"a.py.tmpl": ""}, toml=None)
    (tmp_path / ".rrt" / "templates" / "stray.txt").write_text("x", encoding="utf-8")
    assert t.list_kinds(tmp_path) == ["alpha", "zeta"]


def test_load_kind_full(tmp_path: Path) -> None:
    """A complete kind.toml is parsed into a TemplateKind."""
    make_kind(
        tmp_path,
        "step",
        {"a.py.tmpl": "x"},
        'description = "A step"\nrequires_unit = true\nnext_steps = ["one", "two"]\n'
        '[variables]\nflavour = "vanilla"\n',
    )
    kind = t.load_kind(tmp_path, "step")
    assert kind.name == "step"
    assert kind.description == "A step"
    assert kind.requires_unit is True
    assert kind.next_steps == ("one", "two")
    assert kind.variables == {"flavour": "vanilla"}


def test_load_kind_defaults(tmp_path: Path) -> None:
    """Every kind.toml key is optional."""
    make_kind(tmp_path, "bare", {"a.py.tmpl": "x"})
    kind = t.load_kind(tmp_path, "bare")
    assert (kind.description, kind.requires_unit, kind.next_steps, kind.variables) == (
        "",
        False,
        (),
        {},
    )


def test_unknown_kind_lists_available(tmp_path: Path) -> None:
    """An unknown kind names the available ones."""
    make_kind(tmp_path, "alpha", {"a.py.tmpl": ""})
    make_kind(tmp_path, "beta", {"a.py.tmpl": ""})
    with pytest.raises(t.TemplateError, match=r"Unknown template kind 'gamma'.*alpha, beta"):
        t.load_kind(tmp_path, "gamma")


def test_unknown_kind_without_any(tmp_path: Path) -> None:
    """With no templates at all the message says so."""
    with pytest.raises(t.TemplateError, match=r"\(none\)"):
        t.load_kind(tmp_path, "gamma")


def test_kind_traversal_is_unknown(tmp_path: Path) -> None:
    """A kind name cannot escape the templates directory."""
    make_kind(tmp_path, "alpha", {"a.py.tmpl": ""})
    with pytest.raises(t.TemplateError, match="Unknown template kind"):
        t.load_kind(tmp_path, "../templates/alpha")


@pytest.mark.parametrize(
    ("toml", "fragment"),
    [
        ("bogus = 1\nother = 2\n", "bogus, other"),
        ("description = 3\n", "'description' must be a string"),
        ('requires_unit = "yes"\n', "'requires_unit' must be a boolean"),
        ('next_steps = "one"\n', "'next_steps' must be a list of strings"),
        ("next_steps = [1]\n", "'next_steps' must be a list of strings"),
        ('variables = "x"\n', "'variables' must be a table"),
        ("[variables]\nn = 1\n", "'variables' must be a table"),
        ('[variables]\nname = "x"\nroot = "y"\n', "cannot override built-ins: name, root"),
        ("description = \n", "cannot read kind.toml"),
    ],
)
def test_invalid_kind_toml(tmp_path: Path, toml: str, fragment: str) -> None:
    """Bad keys, types, built-in overrides and TOML syntax errors are rejected."""
    make_kind(tmp_path, "bad", {"a.py.tmpl": "x"}, toml)
    with pytest.raises(t.TemplateError, match=fragment):
        t.load_kind(tmp_path, "bad")


def test_unreadable_kind_toml(tmp_path: Path) -> None:
    """A kind.toml that cannot be opened is a TemplateError."""
    directory = make_kind(tmp_path, "bad", {"a.py.tmpl": "x"})
    (directory / "kind.toml").unlink()
    (directory / "kind.toml").mkdir()  # is_file() is false, so reach the reader directly
    with pytest.raises(t.TemplateError, match="cannot read kind.toml"):
        t._read_kind_toml("bad", directory / "kind.toml")


def test_non_tmpl_file_rejected(tmp_path: Path) -> None:
    """Every non-ignored file under files/ must end in .tmpl."""
    make_kind(tmp_path, "bad", {"a.py.tmpl": "x", "sub/b.py": "y"})
    with pytest.raises(t.TemplateError, match=r"'sub/b.py' must end in '.tmpl'"):
        t.load_kind(tmp_path, "bad")


def test_kind_without_files_rejected(tmp_path: Path) -> None:
    """No files/ dir, or only ignored files, is an invalid kind."""
    make_kind(tmp_path, "empty", {})
    with pytest.raises(t.TemplateError, match="no template files"):
        t.load_kind(tmp_path, "empty")
    make_kind(tmp_path, "ignored", {".DS_Store": "x", "__pycache__/a.pyc": "x"})
    with pytest.raises(t.TemplateError, match="no template files"):
        t.load_kind(tmp_path, "ignored")


def test_ignored_files_skipped_dot_tmpl_kept(tmp_path: Path) -> None:
    """Dot-files and __pycache__ are skipped; a dot-named .tmpl is a template."""
    make_kind(
        tmp_path,
        "mix",
        {
            "a.py.tmpl": "x = 1\n",
            ".DS_Store": "junk",
            "__pycache__/a.cpython.pyc": "junk",
            ".gitignore.tmpl": "*.log\n",
        },
    )
    assert [f.target for f in render(tmp_path, "mix")] == [".gitignore", "a.py"]


def test_build_variables_with_unit(tmp_path: Path) -> None:
    """Built-ins, unit variables and kind constants are merged."""
    make_kind(tmp_path, "step", {"a.py.tmpl": "x"}, '[variables]\nflavour = "vanilla"\n')
    kind = t.load_kind(tmp_path, "step")
    variables = t.build_variables(
        config=CONFIG, root_module=ROOT_MODULE, name="prep_step", unit=UNIT, kind=kind
    )
    assert variables == {
        "name": "prep_step",
        "Name": "PrepStep",
        "root": "src/myapp",
        "root_module": "myapp",
        "unit": "activities",
        "unit_package": "acts",
        "unit_prefix": "act",
        "unit_module": "myapp.acts",
        "flavour": "vanilla",
    }


def test_build_variables_without_unit(tmp_path: Path) -> None:
    """Unit variables are absent when no unit is given."""
    make_kind(tmp_path, "plain", {"a.py.tmpl": "x"})
    kind = t.load_kind(tmp_path, "plain")
    variables = t.build_variables(
        config=CONFIG, root_module=ROOT_MODULE, name="x1", unit=None, kind=kind
    )
    assert set(variables) == {"name", "Name", "root", "root_module"}


def test_requires_unit_without_unit(tmp_path: Path) -> None:
    """A kind that requires a unit refuses unit=None."""
    make_kind(tmp_path, "step", {"a.py.tmpl": "x"}, "requires_unit = true\n")
    with pytest.raises(t.TemplateError, match="requires a unit"):
        render(tmp_path, "step", unit=None)


@pytest.mark.parametrize("name", ["", "Bad", "1abc", "has-dash", "a b", "../x"])
def test_bad_name(tmp_path: Path, name: str) -> None:
    """Names must match NAME_RE."""
    make_kind(tmp_path, "plain", {"a.py.tmpl": "x"})
    with pytest.raises(t.TemplateError, match="Invalid name"):
        render(tmp_path, "plain", name=name)


def test_build_variables_rejects_shadowing_constant(tmp_path: Path) -> None:
    """A hand-built kind whose constants shadow a built-in is refused."""
    kind = t.TemplateKind(name="k", directory=tmp_path, variables={"unit": "x"})
    with pytest.raises(t.TemplateError, match="cannot override built-ins: unit"):
        t.build_variables(config=CONFIG, root_module=ROOT_MODULE, name="ok", unit=None, kind=kind)


def test_render_python_body_with_braces_and_escape(tmp_path: Path) -> None:
    """Braces and f-strings need no escaping; $$ gives a literal dollar."""
    body = (
        "def ${name}(x):\n"
        "    cost = '$$5'\n"
        "    return f'{x} {x!r}' + str({'k': x})\n"
        "\n\nclass ${Name}Step: ...\n"
    )
    make_kind(tmp_path, "fn", {"${root}/${unit_package}/${name}.py.tmpl": body})
    (rendered,) = render(tmp_path, "fn")
    assert rendered.target == "src/myapp/acts/prep_step.py"
    assert rendered.body == (
        "def prep_step(x):\n"
        "    cost = '$5'\n"
        "    return f'{x} {x!r}' + str({'k': x})\n"
        "\n\nclass PrepStepStep: ...\n"
    )
    assert rendered.path == tmp_path.resolve() / "src/myapp/acts/prep_step.py"
    assert rendered.exists is False


def test_render_multiple_sorted_with_unit_vars(tmp_path: Path) -> None:
    """Several files render, sorted by target, with unit placeholders."""
    make_kind(
        tmp_path,
        "pair",
        {
            "tests/test_${name}.py.tmpl": "from ${unit_module} import ${unit_prefix}\n",
            "${root}/${name}.py.tmpl": "UNIT = '${unit}'\n",
        },
    )
    files = render(tmp_path, "pair")
    assert [f.target for f in files] == ["src/myapp/prep_step.py", "tests/test_prep_step.py"]
    assert files[1].body == "from myapp.acts import act\n"
    assert files[0].body == "UNIT = 'activities'\n"


def test_render_never_writes(tmp_path: Path) -> None:
    """render_kind has no side effects on the target tree."""
    make_kind(tmp_path, "fn", {"out/${name}.py.tmpl": "x = 1\n"})
    render(tmp_path, "fn")
    assert not (tmp_path / "out").exists()


def test_missing_placeholder_in_body(tmp_path: Path) -> None:
    """An unknown placeholder in a body names kind, file and placeholder."""
    make_kind(tmp_path, "fn", {"out/a.py.tmpl": "x = '${nope}'\n"})
    with pytest.raises(t.TemplateError) as info:
        render(tmp_path, "fn")
    message = str(info.value)
    assert "'fn'" in message
    assert "out/a.py.tmpl" in message
    assert "${nope}" in message


def test_missing_placeholder_in_path(tmp_path: Path) -> None:
    """An unknown placeholder in a target path is reported too."""
    make_kind(tmp_path, "fn", {"out/${nope}.py.tmpl": "x = 1\n"})
    with pytest.raises(t.TemplateError, match=r"\$\{nope\}"):
        render(tmp_path, "fn")


def test_bad_dollar_in_body(tmp_path: Path) -> None:
    """A stray $ is an error that points at $$."""
    make_kind(tmp_path, "fn", {"out/a.py.tmpl": "price = $ 5\n"})
    with pytest.raises(t.TemplateError, match=r"invalid placeholder.*\$\$"):
        render(tmp_path, "fn")


def test_unreadable_template_body(tmp_path: Path) -> None:
    """A template that is not UTF-8 is a TemplateError."""
    make_kind(tmp_path, "fn", {"out/a.py.tmpl": b"\xff\xfe\x00bad"})
    with pytest.raises(t.TemplateError, match="cannot read template"):
        render(tmp_path, "fn")


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("/etc", "relative to the repo root"),
        ("../up", r"must not contain '\.\.'"),
        ("a/../b", r"must not contain '\.\.'"),
    ],
)
def test_unsafe_targets(tmp_path: Path, value: str, fragment: str) -> None:
    """Absolute and parent-traversing targets are refused."""
    make_kind(tmp_path, "fn", {"${bad}/x.py.tmpl": "x = 1\n"}, f'[variables]\nbad = "{value}"\n')
    with pytest.raises(t.TemplateError, match=fragment):
        render(tmp_path, "fn")


@pytest.mark.parametrize("value", ["", "."])
def test_empty_targets(tmp_path: Path, value: str) -> None:
    """A target that renders to nothing (or '.') names no file."""
    make_kind(tmp_path, "fn", {"${bad}.tmpl": "x"}, f'[variables]\nbad = "{value}"\n')
    with pytest.raises(t.TemplateError, match="is empty"):
        render(tmp_path, "fn")


def test_target_resolving_outside_via_symlink(tmp_path: Path) -> None:
    """A symlink inside the repo that leaves it is caught after resolving."""
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    repo.mkdir()
    try:
        (repo / "link").symlink_to(outside, target_is_directory=True)
    except OSError:  # pragma: no cover - platform without symlinks
        pytest.skip("symlinks unavailable")
    make_kind(repo, "fn", {"link/x.py.tmpl": "x = 1\n"})
    with pytest.raises(t.TemplateError, match="resolves outside the repo root"):
        render(repo, "fn")


def test_target_is_directory(tmp_path: Path) -> None:
    """A target that is an existing directory is refused even with force."""
    make_kind(tmp_path, "fn", {"out.tmpl": "x"})
    (tmp_path / "out").mkdir()
    with pytest.raises(t.TemplateError, match="is a directory"):
        render(tmp_path, "fn", force=True)


def test_existing_target_refused_unless_force(tmp_path: Path) -> None:
    """An existing target needs force; the rendered file records exists=True."""
    make_kind(tmp_path, "fn", {"out/${name}.py.tmpl": "x = 1\n"})
    existing = tmp_path / "out" / "prep_step.py"
    existing.parent.mkdir()
    existing.write_text("old\n", encoding="utf-8")
    with pytest.raises(t.TemplateError, match="already exists; use --force"):
        render(tmp_path, "fn")
    (rendered,) = render(tmp_path, "fn", force=True)
    assert rendered.exists is True
    assert existing.read_text(encoding="utf-8") == "old\n"


def test_duplicate_targets(tmp_path: Path) -> None:
    """Two templates rendering to the same target are refused."""
    make_kind(
        tmp_path,
        "dup",
        {"out/${a}.py.tmpl": "x = 1\n", "out/${b}.py.tmpl": "x = 2\n"},
        '[variables]\na = "same"\nb = "same"\n',
    )
    with pytest.raises(t.TemplateError, match="also produced by"):
        render(tmp_path, "dup")


def test_render_is_all_or_nothing(tmp_path: Path) -> None:
    """One bad file means no list is returned at all."""
    make_kind(tmp_path, "fn", {"a/good.py.tmpl": "x = 1\n", "b/bad.py.tmpl": "${nope}\n"})
    with pytest.raises(t.TemplateError):
        render(tmp_path, "fn")
    assert not (tmp_path / "a").exists()


def test_write_rendered(tmp_path: Path) -> None:
    """write_rendered creates parents and writes utf-8."""
    make_kind(
        tmp_path,
        "fn",
        {"deep/er/${name}.py.tmpl": "s = 'ü'\n", "top.txt.tmpl": "hi\n"},
    )
    files = render(tmp_path, "fn")
    t.write_rendered(files)
    assert (tmp_path / "deep/er/prep_step.py").read_text(encoding="utf-8") == "s = 'ü'\n"
    assert (tmp_path / "top.txt").read_text(encoding="utf-8") == "hi\n"


def test_check_templates_ok(tmp_path: Path) -> None:
    """A valid kind (python and non-python targets) has no problems."""
    make_kind(
        tmp_path,
        "good",
        {
            "${root}/${unit_package}/${name}.py.tmpl": "def ${name}() -> str:\n    return '${Name}'\n",
            "docs/${name}.md.tmpl": "def not python (never compiled)\n",
        },
        "requires_unit = true\n",
    )
    assert t.check_templates(CONFIG, tmp_path, ROOT_MODULE) == {"good": []}
    assert not (tmp_path / "src").exists()


def test_check_templates_syntax_error(tmp_path: Path) -> None:
    """A rendered .py that does not compile is reported with file and line."""
    make_kind(tmp_path, "broken", {"${name}.py.tmpl": "x = 1\ndef (:\n"})
    result = t.check_templates(CONFIG, tmp_path, ROOT_MODULE)
    (problem,) = result["broken"]
    assert problem.startswith("example.py: line 2:")


def test_check_templates_no_role_unit(tmp_path: Path) -> None:
    """requires_unit without a role='unit' unit is a problem; others still run."""
    make_kind(tmp_path, "needs", {"${name}.py.tmpl": "x = 1\n"}, "requires_unit = true\n")
    make_kind(tmp_path, "free", {"${name}.py.tmpl": "x = 1\n"})
    config = _config(ArchUnit(name="core", role="infra"))
    assert t.check_templates(config, tmp_path, ROOT_MODULE) == {
        "free": [],
        "needs": ["requires a unit but no unit with role 'unit' is declared"],
    }


def test_check_templates_picks_first_role_unit(tmp_path: Path) -> None:
    """The first unit with role 'unit' supplies the sample unit variables."""
    make_kind(
        tmp_path,
        "pick",
        {"${name}.py.tmpl": "UNIT = '${unit}'\nassert UNIT == 'second'\n"},
        "requires_unit = true\n",
    )
    config = _config(ArchUnit(name="core", role="infra"), ArchUnit(name="second"))
    assert t.check_templates(config, tmp_path, ROOT_MODULE) == {"pick": []}


def test_check_templates_reports_load_and_render_problems(tmp_path: Path) -> None:
    """Invalid kinds, bad placeholders and unsafe targets become problems."""
    make_kind(tmp_path, "badtoml", {"a.py.tmpl": "x"}, "bogus = 1\n")
    make_kind(tmp_path, "badvar", {"${name}.py.tmpl": "${nope}\n"})
    make_kind(tmp_path, "escape", {"${up}/x.py.tmpl": "x = 1\n"}, '[variables]\nup = ".."\n')
    result = t.check_templates(CONFIG, tmp_path, ROOT_MODULE)
    assert "unknown key(s)" in result["badtoml"][0]
    assert "${nope}" in result["badvar"][0]
    assert "'..'" in result["escape"][0]


def test_check_templates_reports_write_failure(tmp_path: Path) -> None:
    """Targets that cannot coexist on disk are reported, not raised."""
    make_kind(tmp_path, "clash", {"pkg.tmpl": "x", "pkg/mod.py.tmpl": "x = 1\n"})
    result = t.check_templates(CONFIG, tmp_path, ROOT_MODULE)
    assert len(result["clash"]) == 1


def test_check_templates_no_kinds(tmp_path: Path) -> None:
    """No templates directory means an empty result."""
    assert t.check_templates(CONFIG, tmp_path, ROOT_MODULE) == {}
