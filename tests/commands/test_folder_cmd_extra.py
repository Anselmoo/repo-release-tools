import argparse
import stat
from typing import Any

import pytest

from repo_release_tools.commands import folder as folder_mod
from repo_release_tools.config import FolderScaffoldFile
from repo_release_tools.folders import core as folder_core


class DummyReport:
    def __init__(
        self,
        ok: bool = True,
        actions: list[Any] | None = None,
        targets: list[Any] | None = None,
    ) -> None:
        self._ok = ok
        self.actions = actions or []
        self.targets = targets or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self._ok,
            "actions": [{"kind": a.kind, "path": a.path, "detail": a.detail} for a in self.actions],
        }

    @property
    def ok(self) -> bool:
        return self._ok


class DummyAction:
    def __init__(self, kind: str, path: str, detail: str) -> None:
        self.kind = kind
        self.path = path
        self.detail = detail


def test_cmd_folder_check_json_ok_and_not_ok(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(folder_mod, "_load_folder_policy_config", lambda root: None)

    # report.ok == True -> return 0
    monkeypatch.setattr(
        folder_mod,
        "check_folders",
        lambda root, policy, template_names, mode_override: DummyReport(ok=True),
    )
    args = argparse.Namespace(root=".", template=[], report_only=False, format="json")
    rc = folder_mod.cmd_folder_check(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert '"ok": true' in captured.out.lower() or '"ok": true' in captured.out

    # report.ok == False -> return 1
    monkeypatch.setattr(
        folder_mod,
        "check_folders",
        lambda root, policy, template_names, mode_override: DummyReport(ok=False),
    )
    args = argparse.Namespace(root=".", template=[], report_only=False, format="json")
    rc = folder_mod.cmd_folder_check(args)
    assert rc == 1


def test_cmd_folder_scaffold_json_and_dry_run(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(folder_mod, "_load_folder_policy_config", lambda root: None)
    actions = [DummyAction("create", "a.txt", "detail")]
    monkeypatch.setattr(
        folder_mod,
        "scaffold_folders",
        lambda root, policy, template_names, force, dry_run: DummyReport(ok=True, actions=actions),
    )

    # JSON output path
    args = argparse.Namespace(root=".", template=[], force=False, dry_run=False, format="json")
    rc = folder_mod.cmd_folder_scaffold(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert '"actions"' in captured.out

    # dry-run action path
    args = argparse.Namespace(root=".", template=[], force=False, dry_run=True)
    rc = folder_mod.cmd_folder_scaffold(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert "[dry-run] create a.txt" in captured.out


def test_cmd_folder_design_nonexistent_root(capsys: Any, tmp_path: Any) -> None:
    root = tmp_path / "nope"
    args = argparse.Namespace(root=str(root), name="captured", loose=False, selector=".")
    rc = folder_mod.cmd_folder_design(args)
    captured = capsys.readouterr()
    assert rc == 1
    assert "Design root must be an existing directory" in captured.err


def test_cmd_folder_check_human_readable(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(folder_mod, "_load_folder_policy_config", lambda root: None)

    class V:
        def __init__(self, severity: str, path: str, message: str) -> None:
            self.severity = severity
            self.path = path
            self.message = message

    class T:
        def __init__(self, rule_name: str, base_path: str, ok: bool, violations: list[Any]) -> None:
            self.rule_name = rule_name
            self.base_path = base_path
            self.ok = ok
            self.violations = violations

    t1 = T("rule_ok", "/tmp", True, [])
    t2 = T("rule_warn", "/tmp2", False, [V("warning", "p1", "m1")])
    t3 = T("rule_err", "/tmp3", False, [V("error", "p2", "m2")])

    report = DummyReport(ok=False, actions=None, targets=[t1, t2, t3])
    monkeypatch.setattr(
        folder_mod,
        "check_folders",
        lambda root, policy, template_names, mode_override: report,
    )

    args = argparse.Namespace(root=".", template=[], report_only=False)
    rc = folder_mod.cmd_folder_check(args)
    captured = capsys.readouterr()
    assert rc == 1
    assert "rule_ok" in captured.out
    assert "rule_warn" in captured.out
    assert "p1: m1" in captured.out
    assert "p2: m2" in captured.err


def test__load_folder_policy_config_handles_missing_tool(monkeypatch: Any, tmp_path: Any) -> None:
    # Simulate load_or_autodetect_config raising ValueError and the helper
    # recognizing it as the "missing rrt tool" case so the loader returns None.
    monkeypatch.setattr(
        folder_mod,
        "load_or_autodetect_config",
        lambda root: (_ for _ in ()).throw(ValueError("no rrt")),
    )
    monkeypatch.setattr(folder_mod, "is_missing_tool_rrt_error", lambda exc: True)
    result = folder_mod._load_folder_policy_config(tmp_path)
    assert result is None


def test__load_folder_policy_config_raises_on_other_valueerror(
    monkeypatch: Any, tmp_path: Any
) -> None:
    monkeypatch.setattr(
        folder_mod,
        "load_or_autodetect_config",
        lambda root: (_ for _ in ()).throw(ValueError("other")),
    )
    monkeypatch.setattr(folder_mod, "is_missing_tool_rrt_error", lambda exc: False)
    with pytest.raises(ValueError):
        folder_mod._load_folder_policy_config(tmp_path)


def test_scaffold_sets_executable(tmp_path: Any) -> None:
    """Scaffold should set the executable bit for files marked executable."""
    rule = folder_core._EffectiveRule(
        name="exec-test",
        selector=".",
        mode="strict",
        exact=False,
        required_files=(),
        required_dirs=(),
        allowed_files=(),
        allowed_dirs=(),
        allow_patterns=(),
        scaffold_dirs=(),
        scaffold_files=(
            FolderScaffoldFile(path="bin/script.sh", content="#/bin/sh\necho hi", executable=True),
        ),
    )

    base = tmp_path / "repo"
    base.mkdir()
    # Call internal scaffold implementation directly for focused testing.
    folder_core._scaffold_one_target(
        base_path=base,
        root=tmp_path,
        rule=rule,
        force=False,
        dry_run=False,
    )
    created = base / "bin" / "script.sh"
    assert created.exists()
    mode = created.stat().st_mode
    assert mode & stat.S_IXUSR != 0
