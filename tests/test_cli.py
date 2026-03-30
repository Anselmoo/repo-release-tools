from __future__ import annotations

import subprocess
import sys


def test_module_help_smoke() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "repo_release_tools", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "repo-release-tools" in result.stdout
    assert "branch" in result.stdout
    assert "bump" in result.stdout
