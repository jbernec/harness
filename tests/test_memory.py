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
    append_only, audit, decisions, one_copy_of_the_rules,
)

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
