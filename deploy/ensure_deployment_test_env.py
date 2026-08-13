from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable


PINNED_PYTEST_VERSION = "8.4.1"
RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def venv_python_path(repository_root: Path) -> Path:
    return repository_root / ".venv" / "Scripts" / "python.exe"


def installed_pytest_version(python: Path, *, run: RunCommand = subprocess.run) -> str | None:
    if not python.is_file():
        return None
    result = run(
        [str(python), "-c", "import pytest; print(pytest.__version__)"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def ensure_deployment_test_python(
    repository_root: Path,
    *,
    bootstrap_python: str = sys.executable,
    run: RunCommand = subprocess.run,
) -> Path:
    repository_root = repository_root.resolve()
    python = venv_python_path(repository_root)
    if installed_pytest_version(python, run=run) == PINNED_PYTEST_VERSION:
        return python

    if not python.is_file():
        run([bootstrap_python, "-m", "venv", str(repository_root / ".venv")], check=True)
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--disable-pip-version-check",
            "--no-input",
            f"pytest=={PINNED_PYTEST_VERSION}",
        ],
        check=True,
    )
    if installed_pytest_version(python, run=run) != PINNED_PYTEST_VERSION:
        raise RuntimeError("deployment pytest environment did not reach the pinned version")
    return python


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository_root", type=Path)
    args = parser.parse_args()
    print(ensure_deployment_test_python(args.repository_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
