"""Assets for badges."""

from __future__ import annotations

import sys
from pathlib import Path

from repo_release_tools.tools.platform import PLATFORM_LABELS, make_badge_svg

__all__ = ["export_all_badges"]


def export_all_badges(out_dir: Path, *, check: bool = False) -> int:
    """Export all platform/variant badge combinations to out_dir."""
    from repo_release_tools.tools.inject import apply_generated_docs

    out_dir.mkdir(parents=True, exist_ok=True)
    platforms = list(PLATFORM_LABELS.keys())
    variants = ["color", "dark", "light", "reto-dark", "reto-light"]

    exit_code = 0
    for plat in platforms:
        for variant in variants:
            svg = make_badge_svg(plat, variant=variant)
            suffix = f"-{variant}" if variant != "color" else ""
            dest = out_dir / f"{plat}{suffix}.svg"

            exit_code = max(
                exit_code,
                apply_generated_docs(
                    svg,
                    output_path=dest,
                    check=check,
                    write=not check,
                    fail_on_change=False,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    stale_hint="export_all_badges",
                ),
            )
    return exit_code


def _main() -> None:
    """Export all badges to the directory provided as the first argument."""
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/assets/badges")
    sys.exit(export_all_badges(dest))


if __name__ == "__main__":  # pragma: no cover
    _main()
