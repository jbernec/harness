"""Guard: the agent must not edit the checks that grade it.

If the tests are writable by the thing being tested, the harness proves
nothing. This compares protected paths against a git baseline.
"""

from __future__ import annotations

import subprocess
from fnmatch import fnmatch
from pathlib import Path


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def is_repo(cwd: Path) -> bool:
    return _git(["rev-parse", "--git-dir"], cwd).returncode == 0


def _ignored(path: str, patterns: list[str]) -> bool:
    """True if any path segment matches an ignore pattern.

    Directory patterns end in '/' and match a whole segment; the rest are
    globbed against the basename.
    """
    parts = path.split("/")
    for pat in patterns:
        if pat.endswith("/"):
            if pat.rstrip("/") in parts:
                return True
        elif fnmatch(parts[-1], pat):
            return True
    return False


def check_protected(
    cwd: Path,
    protected: list[str],
    baseline: str = "HEAD",
    ignore: list[str] | None = None,
) -> dict:
    """Return which protected paths changed relative to `baseline`.

    Covers tracked edits and untracked additions, so a new test file dropped
    into a protected directory is caught too. Build artifacts listed in
    `ignore` are skipped, since running a check produces them itself.
    """
    if not is_repo(cwd):
        return {"ok": False, "changed": [], "reason": "not a git repository - cannot verify protected paths"}

    patterns = ignore or []
    changed: set[str] = set()

    diff = _git(["diff", "--name-only", baseline, "--", *protected], cwd)
    if diff.returncode != 0:
        return {"ok": False, "changed": [], "reason": f"git diff failed: {diff.stderr.strip()}"}
    changed.update(ln.strip() for ln in diff.stdout.splitlines() if ln.strip())

    untracked = _git(["ls-files", "--others", "--exclude-standard", "--", *protected], cwd)
    changed.update(ln.strip() for ln in untracked.stdout.splitlines() if ln.strip())

    ordered = sorted(p for p in changed if not _ignored(p, patterns))
    if ordered:
        return {
            "ok": False,
            "changed": ordered,
            "reason": f"protected paths were modified: {', '.join(ordered)}",
        }
    return {"ok": True, "changed": [], "reason": "protected paths unchanged"}
