#!/usr/bin/env python3
"""Run backend lint, format and SQLite tests in a disposable Python environment."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def python_in(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def executable_in(environment: Path, name: str) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / f"{name}.exe"
    return environment / "bin" / name


def run(command: list[str], *, label: str, cwd: Path = ROOT) -> None:
    print(label, flush=True)
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise SystemExit(result.returncode)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--suite", choices=("sqlite",), required=True)
    return result


def main() -> int:
    arguments = parser().parse_args()
    with tempfile.TemporaryDirectory(prefix="podobank-backend-check-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        source = temporary_root / "source"
        source.mkdir()
        shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
        shutil.copy2(ROOT / "README.md", source / "README.md")
        shutil.copytree(
            ROOT / "backend",
            source / "backend",
            ignore=shutil.ignore_patterns("__pycache__", "*.py[cod]", "*.egg-info"),
        )

        environment = temporary_root / "venv"
        print("Creating a temporary backend validation environment.", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
        interpreter = python_in(environment)
        run(
            [
                str(interpreter),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--quiet",
                ".[dev]",
            ],
            label="Installing project-declared validation dependencies.",
            cwd=source,
        )

        ruff = str(executable_in(environment, "ruff"))
        run(
            [ruff, "check", "backend", "scripts/verify_backend.py"],
            label="Running Ruff lint checks.",
        )
        run(
            [ruff, "format", "--check", "backend", "scripts/verify_backend.py"],
            label="Checking Ruff formatting.",
        )
        run(
            [
                str(interpreter),
                "-m",
                "unittest",
                "discover",
                "-s",
                "backend/tests",
                "-t",
                "backend",
                "-v",
            ],
            label=f"Running the {arguments.suite} backend suite.",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
