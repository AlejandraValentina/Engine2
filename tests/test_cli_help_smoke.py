from __future__ import annotations

import shutil
import subprocess
import sys


def test_cli_help_smoke() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pywavedyn.cli", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_console_script_help_smoke() -> None:
    exe = shutil.which("pywavedyn")
    if exe is None:
        return
    result = subprocess.run(
        [exe, "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
