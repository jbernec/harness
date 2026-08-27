"""Version pinning.

The point of a shared harness is that "green" means the same thing in every
project using it. That guarantee dissolves quietly if five repos end up on
five versions - the rules changed, the gate changed, and nobody noticed
because each repo still passes its own checks.

So a project records the version it was gated with, and the harness refuses
to run when the installed one is a different feature release. Upgrading is
then a deliberate act in each repo, which is exactly what it should be: you
are changing what your evidence means.

Patch releases are fixes, so 0.4.0 and 0.4.7 are interchangeable. 0.5.0 is
not, even though nothing may have broken - the point is that you looked.
"""

from __future__ import annotations

import re

__version__ = "0.8.1"

VERSION = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")


def feature_release(version: str) -> tuple[int, int]:
    """The part of a version that must match: major and minor."""
    m = VERSION.match(version.strip())
    if not m:
        raise ValueError(f"not a version: {version!r}")
    return int(m.group(1)), int(m.group(2))


def compatible(pinned: str, installed: str) -> bool:
    """Same feature release, patch level free.

    Deliberately symmetric. A newer harness is not automatically fine: it may
    add a gate condition, in which case older evidence was gathered under
    weaker rules. An older one obviously is not fine either.
    """
    try:
        return feature_release(pinned) == feature_release(installed)
    except ValueError:
        return False


def status(pinned: str, installed: str) -> dict:
    """Compare a project's pin against what is actually installed."""
    if not pinned:
        return {
            "ok": True,
            "pinned": "",
            "installed": installed,
            "reason": (
                f"harness {installed}, unpinned - add "
                f'harness_version = "{installed}" to checks.toml so this '
                "project keeps meaning the same thing"
            ),
        }

    try:
        feature_release(pinned)
    except ValueError:
        return {
            "ok": False,
            "pinned": pinned,
            "installed": installed,
            "reason": f"harness_version {pinned!r} is not a version number",
        }

    ok = compatible(pinned, installed)
    return {
        "ok": ok,
        "pinned": pinned,
        "installed": installed,
        "reason": (
            f"harness {installed} matches the pin ({pinned})"
            if ok
            else (
                f"this project was gated with harness {pinned}, but {installed} "
                f"is installed. Either install {pinned}, or read CHANGELOG.md "
                f"and set harness_version = \"{installed}\" in checks.toml."
            )
        ),
    }
