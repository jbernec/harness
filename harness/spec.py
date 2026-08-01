"""Spec: numbered requirements, and the link from each one to its check.

A spec says what you intend. A check proves what you built. They drift apart
silently unless something forces them together. That something is here:

  - every requirement has an ID that never changes and is never reused
  - every requirement is either settled by a check, or gated by a human
  - a requirement's text has a fingerprint; edit the text and the fingerprint
    changes, which breaks the link and turns the check red
  - changing a settled requirement leaves a dated record of why

You never type a fingerprint. The tool computes it. `harness spec bless`
writes it down, and that is the deliberate act of saying "yes, I looked."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from pathlib import Path

# ### R-014  Position limit
HEADING = re.compile(r"^#{1,6}\s+(R-[A-Z0-9]+(?:-[A-Z0-9]+)*)\s*(.*)$")

# check: position_limit   |   gate: human   |   status: agreed
DIRECTIVE = re.compile(r"^\s*(check|gate|status)\s*:\s*(.+?)\s*$", re.IGNORECASE)

# amended: 2026-08-01  limit raised from 10% to 20% after the March drawdown
AMENDED = re.compile(r"^\s*amended\s*:\s*(\d{4}-\d{2}-\d{2})\s+(.+?)\s*$", re.IGNORECASE)

REMOVED = "[REMOVED]"
HASH_LEN = 6

# Where a requirement is in its life. `draft` is not yet binding; `agreed` is
# binding but unbuilt; `implemented` is built and checked; `superseded` has
# been replaced and must say by what.
STATUSES = ("draft", "agreed", "implemented", "superseded")
DEFAULT_STATUS = "agreed"


@dataclass(frozen=True)
class Amendment:
    on: str
    reason: str

    def __str__(self) -> str:
        return f"{self.on}  {self.reason}"


@dataclass(frozen=True)
class Requirement:
    id: str
    title: str
    body: str
    check: str | None
    gate: str | None
    removed: bool
    line: int
    status: str = DEFAULT_STATUS
    amendments: tuple[Amendment, ...] = field(default_factory=tuple)

    @property
    def fingerprint(self) -> str:
        """Hash of the requirement's meaning, not its formatting.

        Whitespace is normalised so re-wrapping a paragraph doesn't cry wolf,
        but any change to the actual words does. Directives - check, gate,
        status, amended - are excluded: recording that you reviewed a change
        must not itself count as a change.
        """
        text = f"{self.title}\n{self.body}"
        normalised = " ".join(text.split())
        return sha256(normalised.encode("utf-8")).hexdigest()[:HASH_LEN]

    @property
    def settled_by(self) -> str:
        if self.removed:
            return "removed"
        if self.check:
            return "check"
        if self.gate:
            return "human"
        return "nothing"


def parse(path: Path) -> list[Requirement]:
    """Read a spec file into requirements.

    Anything outside a requirement heading is prose and is ignored, so you can
    write whatever context you like around them.
    """
    if not path.exists():
        raise FileNotFoundError(f"no spec at {path}")

    reqs: list[Requirement] = []
    current: dict | None = None

    def flush() -> None:
        if current is None:
            return
        reqs.append(
            Requirement(
                id=current["id"],
                title=current["title"],
                body="\n".join(current["body"]).strip(),
                check=current["check"],
                gate=current["gate"],
                removed=current["removed"],
                line=current["line"],
                status=current["status"],
                amendments=tuple(current["amendments"]),
            )
        )

    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        head = HEADING.match(raw)
        if head:
            flush()
            title = head.group(2).strip()
            current = {
                "id": head.group(1),
                "title": title.replace(REMOVED, "").strip(),
                "body": [],
                "check": None,
                "gate": None,
                "removed": REMOVED in title,
                "line": n,
                "status": DEFAULT_STATUS,
                "amendments": [],
            }
            continue

        if current is None:
            continue

        amended = AMENDED.match(raw)
        if amended:
            current["amendments"].append(Amendment(on=amended.group(1), reason=amended.group(2)))
            continue

        directive = DIRECTIVE.match(raw)
        if directive:
            kind, value = directive.group(1).lower(), directive.group(2).strip()
            current[kind] = value.lower() if kind == "status" else value
            continue

        current["body"].append(raw)

    flush()

    seen: set[str] = set()
    for r in reqs:
        if r.id in seen:
            raise ValueError(f"duplicate requirement id {r.id} at line {r.line} - ids are never reused")
        seen.add(r.id)
    return reqs


def coverage(reqs: list[Requirement], check_names: set[str]) -> dict:
    """Every live requirement must be settled by something, and say so.

    An unchecked requirement is not a failure of effort, it is a failure of
    honesty - mark it `gate: human` and it passes. What must never pass is a
    requirement nobody has decided how to settle.
    """
    uncovered = [r.id for r in reqs if r.settled_by == "nothing"]
    dangling = [
        f"{r.id} -> {r.check}"
        for r in reqs
        if r.check and r.check not in check_names
    ]

    problems = []
    if uncovered:
        problems.append(f"no check and no gate: {', '.join(uncovered)}")
    if dangling:
        problems.append(f"points at a check that does not exist: {', '.join(dangling)}")

    live = [r for r in reqs if not r.removed]
    return {
        "ok": not problems,
        "total": len(live),
        "by_check": sum(1 for r in live if r.settled_by == "check"),
        "by_human": sum(1 for r in live if r.settled_by == "human"),
        "uncovered": uncovered,
        "dangling": dangling,
        "reason": "; ".join(problems) if problems else f"all {len(live)} requirements are settled",
    }


def sync(reqs: list[Requirement], checks: dict) -> dict:
    """Compare each requirement's fingerprint against the one its check recorded.

    A mismatch means the spec changed after the check was last agreed. It is
    not necessarily wrong - it is unreviewed, which is the thing worth
    catching.
    """
    drifted: list[str] = []
    unblessed: list[str] = []

    by_req = {r.id: r for r in reqs if r.check and not r.removed}

    for req_id, r in by_req.items():
        check = checks.get(r.check)
        if check is None:
            continue
        recorded = getattr(check, "requirement_hash", "")
        if not recorded:
            unblessed.append(f"{req_id} ({r.check})")
        elif recorded != r.fingerprint:
            drifted.append(f"{req_id}: spec is {r.fingerprint}, check recorded {recorded}")

    problems = []
    if drifted:
        problems.append("changed since last reviewed -> " + "; ".join(drifted))
    if unblessed:
        problems.append("never reviewed -> " + ", ".join(unblessed))

    return {
        "ok": not problems,
        "drifted": drifted,
        "unblessed": unblessed,
        "reason": (
            "; ".join(problems) + "  (run: harness spec bless <ID>)"
            if problems
            else f"all {len(by_req)} linked requirements match their checks"
        ),
    }


def history(reqs: list[Requirement]) -> dict:
    """Rules about a requirement's life, not its content.

    Deleting the old wording and typing new wording loses the one thing worth
    keeping: that it changed, when, and why. These rules make that record
    mandatory where it matters and cheap everywhere else.
    """
    bad_status = [
        f"{r.id}: status '{r.status}' (use {', '.join(STATUSES)})"
        for r in reqs
        if r.status not in STATUSES
    ]
    # Superseded means something replaced it. Say what, or it reads as deleted.
    unexplained = [
        r.id for r in reqs if r.status == "superseded" and not r.amendments
    ]
    # Same for removal: a tombstone with no cause invites someone to re-add it.
    silent_removal = [r.id for r in reqs if r.removed and not r.amendments]

    problems = []
    if bad_status:
        problems.append("unknown status: " + "; ".join(bad_status))
    if unexplained:
        problems.append(
            "superseded with no `amended:` line: " + ", ".join(unexplained)
        )
    if silent_removal:
        problems.append("removed with no `amended:` line: " + ", ".join(silent_removal))

    return {
        "ok": not problems,
        "bad_status": bad_status,
        "unexplained": unexplained,
        "silent_removal": silent_removal,
        "amended": sum(len(r.amendments) for r in reqs),
        "reason": "; ".join(problems) if problems else "every status is valid and every change is explained",
    }


def amend(spec_path: Path, req_id: str, reason: str, on: str | None = None) -> bool:
    """Write a dated amendment line under a requirement.

    Inserted directly beneath the heading, newest first, so the reason for the
    current wording is the first thing read. Returns False if the ID isn't
    found.
    """
    lines = spec_path.read_text(encoding="utf-8").splitlines()
    stamp = on or date.today().isoformat()

    for i, raw in enumerate(lines):
        head = HEADING.match(raw)
        if head and head.group(1) == req_id:
            lines.insert(i + 1, f"amended: {stamp}  {reason}")
            spec_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    return False


def bless(config_path: Path, check_name: str, fingerprint: str) -> bool:
    """Record a fingerprint against a check in checks.toml.

    Deliberately a line edit rather than a rewrite: your comments, ordering and
    formatting survive untouched. Returns False if the check isn't found.
    """
    lines = config_path.read_text(encoding="utf-8").splitlines()
    name_pat = re.compile(rf"^\s*name\s*=\s*[\"']{re.escape(check_name)}[\"']\s*$")
    hash_pat = re.compile(r"^(\s*)requirement_hash\s*=.*$")

    start = next((i for i, ln in enumerate(lines) if name_pat.match(ln)), None)
    if start is None:
        return False

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("[["):
            end = i
            break

    for i in range(start, end):
        if hash_pat.match(lines[i]):
            indent = hash_pat.match(lines[i]).group(1)
            lines[i] = f'{indent}requirement_hash = "{fingerprint}"'
            break
    else:
        lines.insert(start + 1, f'requirement_hash = "{fingerprint}"')

    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


# Exported under a clearer name at package level, where `parse` alone is vague.
parse_spec = parse
