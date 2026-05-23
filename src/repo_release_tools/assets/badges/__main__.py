"""Main entry point for badge asset generation."""

import sys
from pathlib import Path

from repo_release_tools.assets.badges import export_all_badges  # pragma: no cover

if __name__ == "__main__":  # pragma: no cover
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/assets/badges")
    sys.exit(export_all_badges(dest))
