"""Checks: a command plus the exit code that counts as passing.

A check is the only thing in this system that decides pass or fail. It is a
command, not an opinion, and nobody's judgement is involved.
"""

from __future__ import annotations

import fnmatch
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TIMEOUT = 900

# Exit codes that mean the shell could not run the command at all. A red from
# one of these says nothing about the code under test.
CANNOT_RUN = {
    126: "command found but not executable",
    127: "command not found",
}

# Runners that distinguish "tests ran and failed" from "tests never ran".
# Only pytest is listed because only pytest's codes have been verified:
#   1  tests ran, something failed   <- the only legitimate red
#   2  interrupted, e.g. ImportError while collecting
#   3  internal error
#   4  usage error, e.g. the named test file does not exist
#   5  no tests were collected
# Exits 2-5 look identical to a real failure if you only read the exit code,
# which is how a red gets banked against a test that was never written.
# Other runners: set `inconclusive` on the check rather than guessing here.
RUNNER_DID_NOT_RUN: dict[str, dict[int, str]] = {
    "pytest": {
        2: "collection was interrupted - no test ran (often an ImportError)",
        3: "pytest internal error - no test ran",
        4: "usage error - the test path probably does not exist",
        5: "no tests were collected",
    },
}

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
    # Paths this check is about. Empty means "everything" - it always runs.
    files: tuple[str, ...] = field(default_factory=tuple)
    # Exit codes that mean the check never ran. None means "infer from cmd";
    # an explicit list (including an empty one) overrides the inference.
    inconclusive: tuple[int, ...] | None = None

    def concerns(self, paths: list[str]) -> bool:
        """Does this check care about any of these changed files?

        A check with no `files` always concerns you. That default is
        deliberate: forgetting to declare paths must widen the net, never
        narrow it. A scoping mistake that skips a check is invisible.
        """
        if not self.files:
            return True
        return any(_matches(p, f) for p in self.files for f in paths)


def did_not_run(check: Check, exit_code: int) -> str | None:
    """Why this exit code means the check never ran, or None if it really ran.

    `harness red` refuses a failure it cannot attribute to the code. A test
    file that does not exist yet fails exactly like a test that fails, so
    without this you can bank a red against a file you never wrote, then write
    anything at all and the gate will accept it.
    """
    if exit_code in CANNOT_RUN:
        return CANNOT_RUN[exit_code]

    if check.inconclusive is not None:
        return "declared inconclusive by the check" if exit_code in check.inconclusive else None

    for runner, codes in RUNNER_DID_NOT_RUN.items():
        if runner in check.cmd and exit_code in codes:
            return codes[exit_code]
    return None



def _matches(pattern: str, path: str) -> bool:
    """Match a changed file against a check's path pattern.

    `*` spans directories here, unlike shell globbing, so `src/*` and `src/**`
    both cover `src/a/b.py`. A pattern ending in `/` is a directory prefix.
    """
    path = path.replace("\\", "/").lstrip("./")
    pattern = pattern.replace("\\", "/").lstrip("./")
    if pattern.endswith("/"):
        return path.startswith(pattern)
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern.rstrip("/") + "/*")


def changed_files(cwd: Path, base: str | None = None) -> list[str] | None:
    """Files that differ from `base`, plus anything uncommitted or untracked.

    Returns None when git can't answer - no repo, bad ref, git missing. The
    caller must treat that as "run everything", because a selector that fails
    open is a nuisance and one that fails closed is a hole.
    """
    cmds = [["git", "status", "--porcelain"]]
    if base:
        cmds.insert(0, ["git", "diff", "--name-only", f"{base}...HEAD"])

    found: list[str] = []
    for cmd in cmds:
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            line = line.rstrip()
            if not line:
                continue
            # `git status --porcelain` prefixes two status columns.
            if cmd[1] == "status":
                line = line[3:]
                # Renames appear as `old -> new`; the new path is what changed.
                if " -> " in line:
                    line = line.split(" -> ", 1)[1]
            found.append(line.strip().strip('"'))
    return sorted(set(found))


def select(checks: dict[str, Check], paths: list[str]) -> list[Check]:
    """The checks that concern a set of changed files, in config order."""
    return [c for c in checks.values() if c.concerns(paths)]


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
            files=tuple(entry.get("files", [])),
            inconclusive=(
                tuple(int(c) for c in entry["inconclusive"])
                if "inconclusive" in entry
                else None
            ),
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
