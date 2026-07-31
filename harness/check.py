"""Checks: a command plus the exit code that counts as passing.

A check is the only thing in this system that decides pass or fail. It is a
command, not an opinion, and nobody's judgement is involved.
"""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT = 900

# Running a check inside a protected directory creates build artifacts there
# (pytest writes __pycache__ into tests/). Those are not check edits, so the
# guard ignores them by default. Override with `guard_ignore` in checks.toml.
DEFAULT_GUARD_IGNORE = [
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
]


@dataclass(frozen=True)
class Check:
    name: str
    cmd: str
    expect: int = 0
    description: str = ""
    timeout: int = DEFAULT_TIMEOUT
    requirement: str = ""
    requirement_hash: str = ""


@dataclass(frozen=True)
class CheckResult:
    check: Check
    ok: bool
    exit_code: int
    output: str


@dataclass(frozen=True)
class Config:
    project: str
    checks: dict[str, Check]
    protected: list[str]
    guard_ignore: list[str]
    spec: str


def load_config(path: Path) -> Config:
    """Read checks.toml."""
    if not path.exists():
        raise FileNotFoundError(f"no config at {path}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    project = data.get("project")
    if not project:
        raise ValueError("config must set a top-level `project` name")

    checks: dict[str, Check] = {}
    for entry in data.get("check", []):
        name = entry.get("name")
        cmd = entry.get("cmd")
        if not name or not cmd:
            raise ValueError("every [[check]] needs a `name` and a `cmd`")
        if name in checks:
            raise ValueError(f"duplicate check name: {name}")
        checks[name] = Check(
            name=name,
            cmd=cmd,
            expect=int(entry.get("expect", 0)),
            description=entry.get("description", ""),
            timeout=int(entry.get("timeout", DEFAULT_TIMEOUT)),
            requirement=entry.get("requirement", ""),
            requirement_hash=entry.get("requirement_hash", ""),
        )
    if not checks:
        raise ValueError("config defines no checks")

    return Config(
        project=project,
        checks=checks,
        protected=list(data.get("protected", ["tests/"])),
        guard_ignore=list(data.get("guard_ignore", DEFAULT_GUARD_IGNORE)),
        spec=data.get("spec", "spec.md"),
    )


def run(check: Check, cwd: Path) -> CheckResult:
    """Execute a check. A timeout is a failure, never a hang."""
    try:
        proc = subprocess.run(
            check.cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=check.timeout,
        )
        code = proc.returncode
        output = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        code = -1
        output = f"TIMEOUT after {check.timeout}s"
    return CheckResult(check=check, ok=code == check.expect, exit_code=code, output=output.strip()[-2000:])
