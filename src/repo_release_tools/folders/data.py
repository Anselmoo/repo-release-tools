"""Folder supervision result models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FolderViolation:
    """A single folder supervision violation."""

    code: str
    path: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-ready representation."""
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class FolderTargetReport:
    """Folder check result for one matched target path."""

    rule_name: str
    selector: str
    base_path: str
    violations: tuple[FolderViolation, ...] = ()

    @property
    def ok(self) -> bool:
        """Return whether the target is violation-free."""
        return not self.violations

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation."""
        return {
            "rule_name": self.rule_name,
            "selector": self.selector,
            "base_path": self.base_path,
            "ok": self.ok,
            "violations": [violation.to_dict() for violation in self.violations],
        }


@dataclass(frozen=True)
class FolderCheckReport:
    """Aggregated report for folder supervision."""

    mode: str
    targets: tuple[FolderTargetReport, ...] = ()

    @property
    def violation_count(self) -> int:
        """Return total violation count."""
        return sum(len(target.violations) for target in self.targets)

    @property
    def ok(self) -> bool:
        """Return whether all target checks passed."""
        return self.violation_count == 0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation."""
        return {
            "mode": self.mode,
            "ok": self.ok,
            "violation_count": self.violation_count,
            "targets": [target.to_dict() for target in self.targets],
        }


@dataclass(frozen=True)
class FolderScaffoldAction:
    """One emitted scaffold action."""

    kind: str
    path: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-ready representation."""
        return {"kind": self.kind, "path": self.path, "detail": self.detail}


@dataclass(frozen=True)
class FolderScaffoldReport:
    """Aggregated scaffold result."""

    actions: tuple[FolderScaffoldAction, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation."""
        return {"actions": [action.to_dict() for action in self.actions]}
