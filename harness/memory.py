"""Memory: the files that outlive the session.

Agents forget. Sessions end. Models get swapped. Everything a future session
needs has to be in the repository, because a chat log is already gone.

Four files, and they have deliberately different rules:

    spec.md        what we are building     edit freely - it is the present
    checks.toml    how we prove it          edit freely
    decisions.md   why we chose X over Y    APPEND only - it is the past
    AGENTS.md      rules for agents         one copy, others point at it

The append-only rule on decisions.md is the one that gets broken, and it is
the one that matters. Superseding D-004 means writing D-011 and marking D-004
superseded - not editing D-004. The wrong turn is usually the most useful
entry in the file, because it is the reason you do not take it twice. Rewrite
it and you will take it twice.

Nothing here judges whether your decisions were good. It checks that the
record was kept in a way a future session can trust.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

DECISION = re.compile(r"^#{1,3}\s+(D-\d+)", re.M)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# supersedes: D-004  the constraint it assumed no longer holds
#
# `[ \t]*` and not `\s*`: \s matches newlines, so the reason group would run
# on and grab the next paragraph - a supersession with no reason would
# silently borrow one, and record the wrong text as its justification.
SUPERSEDES = re.compile(r"^[ \t]*supersedes[ \t]*:[ \t]*(D-\d+)[ \t]*([^\r\n]*)$", re.IGNORECASE | re.M)

# CLAUDE.md and .github/copilot-instructions.md must point at AGENTS.md, not
# repeat it. Three files with the same rules is three files that drift, and
# when they disagree nobody knows which one is current.
POINTERS = ("CLAUDE.md", ".github/copilot-instructions.md", "GEMINI.md", ".cursorrules")
POINTER_MAX_LINES = 12


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None


def decisions(path: Path) -> dict:
    """Ids unique, in order, every entry dated, and supersessions resolvable.

    Retiring a decision is the operation people get wrong. Deleting it loses
    the reason you did not take that turn, and editing it in place loses that
    you ever changed your mind. So the only way to retire one is to write a
    new entry that names it:

        ## D-011  Store fingerprints per requirement
        2026-08-27
        supersedes: D-006  it assumed one requirement per check

    which leaves both the old reasoning and the moment it stopped applying.
    """
    if not path.exists():
        return {"ok": False, "count": 0, "reason": f"no {path.name} - decisions live in the repo, not in a chat log"}

    text = path.read_text(encoding="utf-8")
    ids = DECISION.findall(text)
    if not ids:
        return {"ok": False, "count": 0, "reason": f"{path.name} records no decisions"}

    problems = []
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        problems.append(f"duplicate ids: {', '.join(dupes)}")

    numbers = [int(i.split("-")[1]) for i in ids]
    if numbers != sorted(numbers):
        problems.append("ids are out of order - append, do not insert")

    entries = re.split(r"^#{1,3}\s+D-\d+", text, flags=re.M)[1:]
    undated = [ids[i] for i, e in enumerate(entries) if not DATE.search(e)]
    if undated:
        problems.append(f"undated: {', '.join(undated)}")

    # Supersession: the target must exist, must not be the entry itself, and
    # must be older. A decision superseding a newer one is a sign the ids
    # were shuffled, which is the thing append-only exists to prevent.
    known = set(ids)
    retired: dict[str, str] = {}
    for i, entry in enumerate(entries):
        for target, why in SUPERSEDES.findall(entry):
            here = ids[i]
            if target not in known:
                problems.append(f"{here} supersedes {target}, which does not exist")
            elif target == here:
                problems.append(f"{here} supersedes itself")
            elif int(target.split("-")[1]) > int(here.split("-")[1]):
                problems.append(f"{here} supersedes {target}, which is newer")
            elif not why.strip():
                problems.append(f"{here} supersedes {target} with no reason given")
            else:
                retired[target] = here

    live = [i for i in ids if i not in retired]
    summary = f"{len(ids)} decisions, all dated and in order"
    if retired:
        summary += f" ({len(retired)} superseded, {len(live)} live)"

    return {
        "ok": not problems,
        "count": len(ids),
        "live": live,
        "superseded": retired,
        "reason": "; ".join(problems) if problems else summary,
    }


def append_only(cwd: Path, path: Path, baseline: str = "HEAD") -> dict:
    """Did this change only add lines?

    The rule people break. Editing an old entry is not a correction, it is
    losing the reason you did not take that turn twice. Superseding means
    adding a new entry that says so.

    Returns ok when git cannot answer, and says so - refusing to run outside
    a repository would make this useless in exactly the places it is easiest
    to adopt.
    """
    if not path.exists():
        return {"ok": True, "reason": f"no {path.name} to check"}

    rel = path.relative_to(cwd).as_posix()
    proc = _git(cwd, "diff", "--unified=0", baseline, "--", rel)
    if proc is None or proc.returncode != 0:
        return {"ok": True, "reason": "git could not answer - append-only not verified"}

    removed = [
        ln for ln in proc.stdout.splitlines()
        if ln.startswith("-") and not ln.startswith("---")
    ]
    # Trailing-whitespace-only and blank removals are formatting, not history.
    real = [ln for ln in removed if ln[1:].strip()]
    if real:
        preview = "; ".join(ln[1:].strip()[:60] for ln in real[:3])
        return {
            "ok": False,
            "removed": len(real),
            "reason": (
                f"{rel} lost {len(real)} line(s) - it is append-only. "
                f"Supersede with a new entry instead of editing an old one. "
                f"Removed: {preview}"
            ),
        }
    return {"ok": True, "removed": 0, "reason": f"{rel} only gained lines"}


def duplicates(reqs: list) -> dict:
    """Two requirements that say the same thing.

    Only exact duplication is reported - identical fingerprints, meaning the
    normalised words match. Nothing here tries to judge whether two
    differently-worded requirements *mean* the same thing, because that is a
    judgement, and a guard that guesses at judgement produces false positives
    until someone switches it off.

    What this does catch is the real mechanism: copy a requirement to amend
    it, forget to delete the original, and now two ids point at the same
    words. Whichever one you later edit, the other silently disagrees.
    """
    by_print: dict[str, list[str]] = {}
    for r in reqs:
        if getattr(r, "removed", False):
            continue
        by_print.setdefault(r.fingerprint, []).append(r.id)

    dupes = {fp: ids for fp, ids in by_print.items() if len(ids) > 1}
    if dupes:
        listed = "; ".join(" = ".join(ids) for ids in dupes.values())
        return {
            "ok": False,
            "groups": list(dupes.values()),
            "reason": f"requirements with identical text: {listed} - retire one with [REMOVED]",
        }
    return {"ok": True, "groups": [], "reason": "no requirement is written twice"}


def one_copy_of_the_rules(cwd: Path) -> dict:
    """AGENTS.md holds the rules; the others are pointers.

    A pointer is short and mentions AGENTS.md. Anything longer is a second
    copy waiting to disagree with the first.
    """
    agents = cwd / "AGENTS.md"
    if not agents.exists():
        return {"ok": False, "reason": "no AGENTS.md - the agent has no rules to follow"}

    duplicates = []
    for name in POINTERS:
        p = cwd / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if "AGENTS.md" in text and len(lines) <= POINTER_MAX_LINES:
            continue
        duplicates.append(name)

    if duplicates:
        return {
            "ok": False,
            "duplicates": duplicates,
            "reason": (
                f"{', '.join(duplicates)} repeats the rules instead of pointing at "
                "AGENTS.md - when they disagree, nobody knows which is current"
            ),
        }
    return {"ok": True, "duplicates": [], "reason": "AGENTS.md is the only copy of the rules"}


def audit(cwd: Path, spec: str = "spec.md", baseline: str = "HEAD") -> dict:
    """Everything a fresh session would need, and whether it is trustworthy."""
    parts = {
        "decisions": decisions(cwd / "decisions.md"),
        "append_only": append_only(cwd, cwd / "decisions.md", baseline),
        "rules": one_copy_of_the_rules(cwd),
    }

    spec_path = cwd / spec
    if spec_path.exists():
        parts["spec"] = {"ok": True, "reason": f"{spec} is present"}
        try:
            from .spec import parse as parse_spec

            parts["duplicates"] = duplicates(parse_spec(spec_path))
        except (ValueError, OSError) as exc:
            parts["duplicates"] = {"ok": False, "reason": f"{spec} would not parse: {exc}"}
    else:
        parts["spec"] = {
            "ok": False,
            "reason": f"no {spec} - a fresh session cannot tell what this is for",
        }

    failed = [k for k, v in parts.items() if not v["ok"]]
    return {
        "ok": not failed,
        "parts": parts,
        "failed": failed,
        "reason": (
            "; ".join(parts[k]["reason"] for k in failed)
            if failed
            else "a fresh session could pick this up from the repository alone"
        ),
    }
