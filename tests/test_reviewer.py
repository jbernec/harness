"""The reviewer fixture.

`reviewer/README.md` is a prompt, and a prompt is a claim about behaviour.
You cannot assert on a model's wording - ask twice, get two answers - but you
can keep the fixture and its answer key from drifting apart, which is the way
this particular thing rots: someone edits the diff, the answers now describe
code that is no longer there, and the next run scores itself against fiction.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWER = ROOT / "reviewer"
DIFF = REVIEWER / "fixture.diff"
ANSWERS = REVIEWER / "fixture.md"
PROMPT = REVIEWER / "README.md"

CATEGORIES = ["WRONG", "UNPROVEN", "WIDER", "SILENT FAILURE", "IRREVERSIBLE"]


def test_the_fixture_exists():
    assert DIFF.exists() and ANSWERS.exists() and PROMPT.exists()


def test_the_prompt_asks_for_every_category():
    text = PROMPT.read_text(encoding="utf-8")
    missing = [c for c in CATEGORIES if c not in text]
    assert not missing, f"prompt no longer asks for: {missing}"


def test_the_answer_key_covers_every_category():
    """One planted defect per category. A category with no planted defect is
    a category the fixture cannot tell you anything about."""
    text = ANSWERS.read_text(encoding="utf-8")
    missing = [c for c in CATEGORIES if c not in text]
    assert not missing, f"no planted defect for: {missing}"


def test_every_symbol_in_the_answer_key_is_in_the_diff():
    """The way this rots: the diff is edited and the answers now describe
    code that is not there. Derived from the files, never typed.

    Exception names are excluded because the answer key discusses them as
    prose - "the NameError is swallowed" - rather than claiming they appear
    in the diff. A first version flagged that, which is the cry-wolf failure
    in docs/failures.md.
    """
    diff = DIFF.read_text(encoding="utf-8")
    answers = ANSWERS.read_text(encoding="utf-8")

    symbols = {
        s for s in re.findall(r"`([A-Za-z_][A-Za-z0-9_]{3,})`", answers)
        if not s.startswith("R-") and not s.endswith(("Error", "Exception", "Warning"))
    }
    absent = sorted(s for s in symbols if s not in diff)
    assert not absent, f"answer key names things the diff does not contain: {absent}"


def test_that_symbol_check_would_catch_a_renamed_function():
    """Proved in both directions. A guard only ever seen passing is
    decoration."""
    diff = DIFF.read_text(encoding="utf-8")
    assert "issue_refund" in diff
    assert "issue_refund_v2" not in diff, "pick a name that is genuinely absent"


def test_the_diff_still_contains_each_planted_defect():
    """Spot-check the defects by their signature rather than by description.
    If someone 'fixes' the fixture, the fixture stops being a test."""
    diff = DIFF.read_text(encoding="utf-8")
    signatures = {
        "off-by-one window": "REFUND_WINDOW_DAYS + 1",
        "silent success": 'return {"ok": True, "reason": "refund submitted"}',
        "unguarded delete": "DELETE FROM charges",
        "unrelated helper": "def retry_with_backoff",
        "unchecked currency": "def issue_refund",
    }
    gone = [name for name, sig in signatures.items() if sig not in diff]
    assert not gone, f"planted defects no longer in the fixture: {gone}"


def test_the_requirement_the_defects_violate_is_in_the_diff():
    """The reviewer is given the diff and nothing else, so the spec hunk has
    to travel with it or half the findings are unreachable."""
    diff = DIFF.read_text(encoding="utf-8")
    assert "R-015" in diff and "90 days" in diff
    assert "original currency" in diff


def test_a_run_is_recorded():
    """An unrun fixture is a fixture that proves nothing. This does not check
    the score - it checks that somebody actually ran it and wrote down what
    happened."""
    text = ANSWERS.read_text(encoding="utf-8")
    assert "## Recorded runs" in text
    assert re.search(r"\|\s*\d{4}-\d{2}-\d{2}\s*\|", text), "no dated run recorded"
