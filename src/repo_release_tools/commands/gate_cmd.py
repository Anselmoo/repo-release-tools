"""Run a declared list of check lines, each against the exit code it is designed to produce.

## Overview

`rrt gate run` executes every `[[tool.rrt.gates]]` line and compares its exit
code with the line's `expect` value. A list joined with `&&` stops at the first
non-zero exit. That silently skips every later check, even when the red line
was red on purpose. Here every line runs regardless of earlier results.

The report is a table of expected exit, actual exit, and verdict. The command
exits 0 only when every verdict matches. A deliberately failing check, such as a
seeded defect whose test must fail, therefore passes when it fails as designed.

## Configuration

```toml
[[tool.rrt.gates]]
name = "unit"
run = "uv run pytest -q | tail -3"

[[tool.rrt.gates]]
name = "seeded-defect"
run = ["uv", "run", "pytest", "tests/test_seeded.py"]
expect = 1
timeout = 600
```

- `run` as a string executes through `bash -o pipefail -c`. The caller's shell
  is never assumed, and a pipeline reports its first failing element.
- `run` as a list executes as argv with no shell at all.
- `expect` defaults to `0`. `timeout` is optional, in seconds.

## Examples

- `rrt gate run`
- `rrt gate run seeded-defect unit`
- `rrt gate run --dry-run`

## Caveats

- String-form lines need `bash` on `PATH`. Use the list form where no shell exists.
- A missing executable or a timeout fails its line with an error, never a crash.
- Lines run sequentially from the repository root, with stdin closed.
- Output is captured. The tail of each mismatched line is shown so a failure stays explainable.
- The MCP `rrt_gate_run` tool defaults to a dry run because it executes repository commands.

## Related docs

- [CI & Automation commands](/repo-release-tools/commands/ci-automation/)
- [Generated CLI reference](/repo-release-tools/commands/rrt-cli/)
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.commands._cli_shared import add_dry_run_flag
from repo_release_tools.commands._registry import CommandCategory, CommandGroup, register_command
from repo_release_tools.config import GateSpec, load_gates
from repo_release_tools.ui import GLYPHS, DryRunPrinter

GATE_RUN_EXAMPLES = """\
  $ rrt gate run
  $ rrt gate run seeded-defect unit
  $ rrt gate run --dry-run"""

OUTPUT_TAIL_LINES = 15


@dataclass(frozen=True)
class GateResult:
    """The verdict for one gate line.

    *exit* is ``None`` when the line did not produce an exit code: a dry run,
    a missing executable, or a timeout. *ok* is true only when *exit* equals
    *expected_exit*.
    """

    name: str
    command: str
    expected_exit: int
    exit: int | None = None
    ok: bool = False
    error: str | None = None
    output_tail: str = ""


def gate_argv(spec: GateSpec) -> list[str]:
    """Return the argv for *spec*: explicit bash for strings, verbatim for lists."""
    if isinstance(spec.run, str):
        return ["bash", "-o", "pipefail", "-c", spec.run]
    return list(spec.run)


def _command_text(spec: GateSpec) -> str:
    return spec.run if isinstance(spec.run, str) else shlex.join(spec.run)


def select_gates(specs: tuple[GateSpec, ...], names: list[str]) -> tuple[GateSpec, ...]:
    """Return the gates named in *names* (all when empty), in config order.

    Raises ``ValueError`` naming every unknown gate.
    """
    if not names:
        return specs
    known = {spec.name for spec in specs}
    unknown = [name for name in names if name not in known]
    if unknown:
        available = ", ".join(sorted(known)) or "none configured"
        raise ValueError(f"Unknown gate(s): {', '.join(unknown)}. Available: {available}")
    wanted = set(names)
    return tuple(spec for spec in specs if spec.name in wanted)


def _tail(stdout: str, stderr: str) -> str:
    lines = (stdout + stderr).strip().splitlines()
    return "\n".join(lines[-OUTPUT_TAIL_LINES:])


def run_gate(root: Path, spec: GateSpec) -> GateResult:
    """Run one gate line and judge its exit code against ``spec.expect``."""
    command = _command_text(spec)
    try:
        result = subprocess.run(
            gate_argv(spec),
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=spec.timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return GateResult(
            spec.name, command, spec.expect, error=f"command not found: {exc.filename}"
        )
    except subprocess.TimeoutExpired:
        return GateResult(spec.name, command, spec.expect, error=f"timed out after {spec.timeout}s")
    ok = result.returncode == spec.expect
    return GateResult(
        name=spec.name,
        command=command,
        expected_exit=spec.expect,
        exit=result.returncode,
        ok=ok,
        output_tail="" if ok else _tail(result.stdout, result.stderr),
    )


def run_gates(
    root: Path, specs: tuple[GateSpec, ...], *, dry_run: bool = False
) -> list[GateResult]:
    """Run every gate in *specs*, never stopping early.

    In dry-run mode nothing executes and each result has ``exit=None``.
    """
    if dry_run:
        return [GateResult(spec.name, _command_text(spec), spec.expect) for spec in specs]
    return [run_gate(root, spec) for spec in specs]


def _verdict(result: GateResult) -> str:
    if result.ok:
        return f"{GLYPHS.bullet.ok} as expected"
    if result.error is not None:
        return f"{GLYPHS.bullet.error} error"
    return f"{GLYPHS.bullet.error} mismatch"


def cmd_gate_run(args: argparse.Namespace) -> int:
    """Run the configured gate lines and report expected / actual / verdict."""
    dry_run = bool(args.dry_run)
    p = DryRunPrinter(dry_run, verbose=getattr(args, "verbose", 0) or 0)
    root = Path.cwd()
    try:
        specs = select_gates(load_gates(root), list(args.names))
    except ValueError as exc:
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    if not specs:
        p.warn("No [[tool.rrt.gates]] lines are configured.", stream=sys.stderr)
        return 1

    results = run_gates(root, specs, dry_run=dry_run)
    p.blank_line()
    p.header("Gate run", Lines=str(len(results)))
    if dry_run:
        p.section("Lines")
        for spec, result in zip(specs, results, strict=True):
            p.would_run(f"{result.command}  # expect exit {result.expected_exit}")
            if spec.description:
                p.list_item(spec.description)
        p.footer("Done.")
        return 0

    rows = [
        [
            result.name,
            str(result.expected_exit),
            "-" if result.exit is None else str(result.exit),
            _verdict(result),
        ]
        for result in results
    ]
    sys.stdout.write(GLYPHS.box.table(["gate", "expected", "actual", "verdict"], rows) + "\n")
    failed = [result for result in results if not result.ok]
    for result in failed:
        p.blank_line(stream=sys.stderr)
        p.warn(f"{result.name}: {result.error or 'unexpected exit'}", stream=sys.stderr)
        p.action(f"$ {result.command}", stream=sys.stderr)
        for line in result.output_tail.splitlines():
            p.list_item(line, stream=sys.stderr)
    p.blank_line()
    if failed:
        p.line(f"{len(failed)} of {len(results)} gate line(s) did not match.", ok=False)
        return 1
    p.footer(f"All {len(results)} gate line(s) matched their expected exit.")
    return 0


@register_command(name="gate", category=CommandCategory.WRITE, group=CommandGroup.CI_AUTOMATION)
def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``rrt gate``."""
    parser = subparsers.add_parser(
        "gate",
        help="Run declared check lines, each against its expected exit code",
        description=(
            "Run [[tool.rrt.gates]] check lines. Every line runs regardless of earlier "
            "results, and each is judged against the exit code it is designed to produce."
        ),
    )
    gate_sub = parser.add_subparsers(
        dest="gate_command", metavar="<gate_command>", parser_class=type(parser), required=True
    )
    run_parser = gate_sub.add_parser(
        "run",
        help="Run every gate line (or the named ones) and report expected / actual / verdict.",
        description="Run gate lines and exit 0 only when every line matched its expected exit.",
        epilog=GATE_RUN_EXAMPLES,
    )
    run_parser.add_argument("names", nargs="*", metavar="NAME", help="Gate names to run.")
    add_dry_run_flag(run_parser, verb="running gate commands")
    run_parser.set_defaults(handler=cmd_gate_run)
