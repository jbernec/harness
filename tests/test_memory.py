"""Memory audit.

Every check here is proved in both directions. A memory rule nobody has
watched fail is a preference with a command attached.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.memory import (  # noqa: E402
    append_only, audit, decisions, duplicates, one_copy_of_the_rules,
)
from harness.spec import parse as parse_spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

GOOD = """\
# decisions

## D-001  The key lives outside the project
2026-07-31

Because an unkeyed chain inside the workspace is not tamper-evident.

## D-002  Red first carries the weight
2026-08-01

A green check on its own means nothing.
"""


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def repo(tmp_path: Path, body: str = GOOD) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "decisions.md").write_text(body, encoding="utf-8")
    (tmp_path / "spec.md").write_text("# s\n\n### R-001  A\nx\n\ncheck: unit\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n\n1. **Rule.**\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


# --- decisions -------------------------------------------------------------


def test_a_well_kept_file_passes(tmp_path):
    (tmp_path / "d.md").write_text(GOOD, encoding="utf-8")
    result = decisions(tmp_path / "d.md")
    assert result["ok"] and result["count"] == 2


def test_a_missing_file_fails(tmp_path):
    assert not decisions(tmp_path / "nope.md")["ok"]


def test_a_file_with_no_decisions_fails(tmp_path):
    (tmp_path / "d.md").write_text("# decisions\n\nNothing yet.\n", encoding="utf-8")
    assert not decisions(tmp_path / "d.md")["ok"]


def test_duplicate_ids_fail(tmp_path):
    (tmp_path / "d.md").write_text(GOOD.replace("D-002", "D-001"), encoding="utf-8")
    result = decisions(tmp_path / "d.md")
    assert not result["ok"] and "duplicate" in result["reason"]


def test_ids_out_of_order_fail(tmp_path):
    """Inserting between existing entries instead of appending."""
    (tmp_path / "d.md").write_text(GOOD.replace("D-002", "D-000"), encoding="utf-8")
    result = decisions(tmp_path / "d.md")
    assert not result["ok"] and "out of order" in result["reason"]


def test_an_undated_decision_fails(tmp_path):
    (tmp_path / "d.md").write_text(GOOD.replace("2026-08-01\n", ""), encoding="utf-8")
    result = decisions(tmp_path / "d.md")
    assert not result["ok"] and "D-002" in result["reason"]


# --- append-only -----------------------------------------------------------


def test_adding_a_decision_is_allowed(tmp_path):
    r = repo(tmp_path)
    (r / "decisions.md").write_text(
        GOOD + "\n## D-003  Something new\n2026-08-27\n\nBecause.\n", encoding="utf-8"
    )
    assert append_only(r, r / "decisions.md")["ok"]


def test_editing_an_old_decision_fails(tmp_path):
    """The rule people break, and the one that matters. Rewriting the wrong
    turn is how you take it a second time."""
    r = repo(tmp_path)
    (r / "decisions.md").write_text(
        GOOD.replace("Because an unkeyed chain inside the workspace is not tamper-evident.",
                     "Because it seemed neater."),
        encoding="utf-8",
    )
    result = append_only(r, r / "decisions.md")
    assert not result["ok"]
    assert "append-only" in result["reason"]


def test_deleting_a_decision_fails(tmp_path):
    r = repo(tmp_path)
    (r / "decisions.md").write_text(GOOD.split("## D-002")[0], encoding="utf-8")
    assert not append_only(r, r / "decisions.md")["ok"]


def test_reflowing_whitespace_is_not_a_rewrite(tmp_path):
    """Cries wolf otherwise, and a guard that cries wolf gets switched off."""
    r = repo(tmp_path)
    (r / "decisions.md").write_text(GOOD.replace("\n\n", "\n\n\n"), encoding="utf-8")
    assert append_only(r, r / "decisions.md")["ok"]


def test_append_only_is_quiet_when_git_cannot_answer(tmp_path):
    """Refusing outside a repository would make this useless in exactly the
    places it is easiest to adopt. It says it did not verify."""
    (tmp_path / "decisions.md").write_text(GOOD, encoding="utf-8")
    result = append_only(tmp_path, tmp_path / "decisions.md")
    assert result["ok"] and "not verified" in result["reason"]


# --- one copy of the rules -------------------------------------------------


def test_agents_md_alone_passes(tmp_path):
    assert one_copy_of_the_rules(repo(tmp_path))["ok"]


def test_a_one_line_pointer_passes(tmp_path):
    r = repo(tmp_path)
    (r / "CLAUDE.md").write_text("See AGENTS.md.\n", encoding="utf-8")
    assert one_copy_of_the_rules(r)["ok"]


def test_a_second_copy_of_the_rules_fails(tmp_path):
    """Three files with the same rules is three files that drift."""
    r = repo(tmp_path)
    (r / "CLAUDE.md").write_text("# Rules\n\n" + "\n".join(f"{i}. Do a thing." for i in range(20)), encoding="utf-8")
    result = one_copy_of_the_rules(r)
    assert not result["ok"] and "CLAUDE.md" in result["reason"]


def test_a_long_file_that_points_at_agents_is_allowed(tmp_path):
    """Scoped by 'does it name AGENTS.md', not by length alone - some tools
    need a little front matter."""
    r = repo(tmp_path)
    (r / "CLAUDE.md").write_text("See AGENTS.md.\n" + "\n" * 40, encoding="utf-8")
    assert one_copy_of_the_rules(r)["ok"]


def test_no_agents_file_fails(tmp_path):
    r = repo(tmp_path)
    (r / "AGENTS.md").unlink()
    assert not one_copy_of_the_rules(r)["ok"]


# --- the whole audit -------------------------------------------------------


def test_a_complete_project_passes(tmp_path):
    assert audit(repo(tmp_path))["ok"]


def test_a_missing_spec_fails(tmp_path):
    r = repo(tmp_path)
    (r / "spec.md").unlink()
    result = audit(r)
    assert not result["ok"] and "spec" in result["failed"]


def test_the_audit_names_every_part_that_failed(tmp_path):
    r = repo(tmp_path)
    (r / "spec.md").unlink()
    (r / "decisions.md").unlink()
    assert set(audit(r)["failed"]) >= {"spec", "decisions"}


def test_this_repo_keeps_its_own_memory():
    """The same dogfooding gap as shipping checks.toml.example and never
    running a check on itself."""
    assert audit(ROOT)["ok"], audit(ROOT)["reason"]


def test_a_fresh_scaffold_passes_the_memory_audit(tmp_path):
    """Same rule as everywhere else: a scaffold that is red on day one for a
    reason nobody caused is how a check earns a reputation for crying wolf.
    `init` writes a real first decision, dated, rather than a placeholder."""
    from harness.init import init

    init(tmp_path, project="fresh", ci=False)
    result = audit(tmp_path)
    assert result["ok"], result["reason"]


def test_the_scaffolded_decision_is_real_not_a_placeholder(tmp_path):
    from harness.init import init

    init(tmp_path, project="fresh", ci=False)
    text = (tmp_path / "decisions.md").read_text(encoding="utf-8")
    assert "<date>" not in text and "<decision>" not in text
    assert decisions(tmp_path / "decisions.md")["count"] == 1


# --- superseding: retiring a decision without losing it --------------------

SUPERSEDED = """\
# decisions

## D-001  Store one hash per check
2026-07-31

It seemed enough at the time.

## D-002  Store one hash per requirement
2026-08-27
supersedes: D-001  it assumed a check settles exactly one requirement

Several requirements legitimately share a check.
"""


def write(tmp_path, body):
    p = tmp_path / "d.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_a_valid_supersession_passes(tmp_path):
    result = decisions(write(tmp_path, SUPERSEDED))
    assert result["ok"]
    assert result["superseded"] == {"D-001": "D-002"}
    assert result["live"] == ["D-002"]


def test_superseding_something_that_does_not_exist_fails(tmp_path):
    result = decisions(write(tmp_path, SUPERSEDED.replace("supersedes: D-001", "supersedes: D-099")))
    assert not result["ok"] and "does not exist" in result["reason"]


def test_superseding_itself_fails(tmp_path):
    result = decisions(write(tmp_path, SUPERSEDED.replace("supersedes: D-001", "supersedes: D-002")))
    assert not result["ok"] and "supersedes itself" in result["reason"]


def test_superseding_a_newer_decision_fails(tmp_path):
    """A sign the ids were shuffled, which append-only exists to prevent."""
    body = SUPERSEDED.replace("supersedes: D-001  it assumed", "supersedes: D-003  it assumed")
    body += "\n## D-003  Later\n2026-08-28\n\nSomething.\n"
    result = decisions(write(tmp_path, body))
    assert not result["ok"] and "is newer" in result["reason"]


def test_superseding_with_no_reason_fails(tmp_path):
    """'Superseded by D-002' with no why is a deletion with extra steps."""
    result = decisions(write(tmp_path, SUPERSEDED.replace(
        "supersedes: D-001  it assumed a check settles exactly one requirement",
        "supersedes: D-001")))
    assert not result["ok"] and "no reason" in result["reason"]


def test_a_file_with_no_supersessions_is_still_fine(tmp_path):
    """Both directions - the feature must not become mandatory."""
    assert decisions(write(tmp_path, GOOD))["ok"]


def test_this_repo_records_a_supersession():
    """Dogfooding: D-012 replaced an earlier design and said nothing."""
    result = decisions(ROOT / "decisions.md")
    assert result["superseded"], "no decision here has ever been retired properly"


# --- duplicates ------------------------------------------------------------

TWICE = """\
# s

### R-001  Position limit
No single position may exceed 20% of book value.

check: a

### R-002  Position limit
No single position may exceed 20% of book value.

check: b
"""


def test_identical_requirements_are_reported(tmp_path):
    """The real mechanism: copy one to amend it, forget to delete the
    original, and whichever you later edit, the other silently disagrees."""
    p = tmp_path / "spec.md"
    p.write_text(TWICE, encoding="utf-8")
    result = duplicates(parse_spec(p))
    assert not result["ok"]
    assert "R-001" in result["reason"] and "R-002" in result["reason"]


def test_differently_worded_requirements_are_not_reported(tmp_path):
    """Only exact duplication. Judging whether two wordings MEAN the same
    thing is a judgement, and a guard that guesses produces false positives
    until someone switches it off."""
    p = tmp_path / "spec.md"
    p.write_text(TWICE.replace("may exceed 20% of book value.\n\ncheck: b",
                               "may exceed a fifth of the book.\n\ncheck: b"), encoding="utf-8")
    assert duplicates(parse_spec(p))["ok"]


def test_a_retired_duplicate_is_not_reported(tmp_path):
    """Retiring one is the fix, so it must not still be flagged afterwards."""
    p = tmp_path / "spec.md"
    p.write_text(TWICE.replace("### R-002  Position limit", "### R-002  Position limit  [REMOVED]"),
                 encoding="utf-8")
    assert duplicates(parse_spec(p))["ok"]


def test_reformatting_does_not_create_a_duplicate(tmp_path):
    p = tmp_path / "spec.md"
    p.write_text(TWICE.replace("No single position may exceed 20% of book value.\n\ncheck: b",
                               "No single position\nmay exceed 20% of book value.\n\ncheck: b"),
                 encoding="utf-8")
    result = duplicates(parse_spec(p))
    assert not result["ok"], "whitespace is normalised, so this is still the same requirement"


def test_the_audit_includes_duplicates(tmp_path):
    r = repo(tmp_path)
    (r / "spec.md").write_text(TWICE, encoding="utf-8")
    result = audit(r)
    assert not result["ok"] and "duplicates" in result["failed"]


def test_a_reasonless_supersession_does_not_borrow_the_next_paragraph():
    """Found by the test above failing.

    `\\s*` matches newlines, so the reason group ran on and picked up the
    following paragraph - a supersession with no reason silently borrowed
    one, and recorded the wrong text as its justification.
    """
    from harness.memory import SUPERSEDES

    body = "supersedes: D-001\n\nAn unrelated paragraph.\n"
    assert SUPERSEDES.findall(body) == [("D-001", "")]


def test_a_reason_on_the_same_line_is_still_captured():
    from harness.memory import SUPERSEDES

    body = "supersedes: D-001  because the constraint moved\n\nOther text.\n"
    assert SUPERSEDES.findall(body) == [("D-001", "because the constraint moved")]
