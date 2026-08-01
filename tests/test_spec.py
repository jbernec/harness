"""Tests for the spec layer: requirements, coverage, fingerprints, drift.

The point of this layer is that a spec change cannot pass unnoticed. These
tests exist to prove that claim, not to decorate it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.check import load_config  # noqa: E402
from harness.spec import amend, bless, coverage, history, parse, sync  # noqa: E402

SPEC = """\
# ARIA

Some prose that should be ignored entirely.

### R-001  Approved universe only
The agent may only trade instruments on the approved list.

check: universe

### R-002  Position limit
No single position may exceed 20% of book value.

check: position_limit

### R-003  The strategy is sound
No command settles this.

gate: human

### R-004  Retired rule  [REMOVED]
Kept so old traces still resolve.
"""


def write_spec(tmp_path: Path, text: str = SPEC) -> Path:
    p = tmp_path / "spec.md"
    p.write_text(text, encoding="utf-8")
    return p


# --- parsing ---------------------------------------------------------------


def test_parses_every_requirement(tmp_path):
    reqs = parse(write_spec(tmp_path))
    assert [r.id for r in reqs] == ["R-001", "R-002", "R-003", "R-004"]


def test_prose_outside_requirements_is_ignored(tmp_path):
    reqs = parse(write_spec(tmp_path))
    assert "should be ignored" not in reqs[0].body


def test_records_how_each_requirement_is_settled(tmp_path):
    reqs = {r.id: r for r in parse(write_spec(tmp_path))}
    assert reqs["R-002"].settled_by == "check"
    assert reqs["R-003"].settled_by == "human"
    assert reqs["R-004"].settled_by == "removed"


def test_removed_requirements_are_kept_not_dropped(tmp_path):
    """Old traces reference old ids. Deleting an id orphans its evidence."""
    reqs = parse(write_spec(tmp_path))
    assert any(r.id == "R-004" and r.removed for r in reqs)


def test_duplicate_ids_are_rejected(tmp_path):
    spec = SPEC + "\n### R-001  Sneaky duplicate\ncheck: other\n"
    with pytest.raises(ValueError, match="never reused"):
        parse(write_spec(tmp_path, spec))


def test_area_prefixed_ids_parse(tmp_path):
    spec = "### R-RISK-014  Drawdown\nHalt at 15%.\n\ncheck: kill_switch\n"
    assert parse(write_spec(tmp_path, spec))[0].id == "R-RISK-014"


# --- fingerprints ----------------------------------------------------------


def test_reformatting_does_not_change_the_fingerprint(tmp_path):
    """Re-wrapping a paragraph must not cry wolf."""
    a = parse(write_spec(tmp_path, "### R-001  T\nNo single position may\nexceed 20%.\n\ncheck: c\n"))[0]
    b = parse(write_spec(tmp_path, "### R-001  T\nNo single    position\n  may exceed 20%.\n\ncheck: c\n"))[0]
    assert a.fingerprint == b.fingerprint


def test_changing_the_words_changes_the_fingerprint(tmp_path):
    a = parse(write_spec(tmp_path, "### R-001  T\nMay not exceed 20%.\n\ncheck: c\n"))[0]
    b = parse(write_spec(tmp_path, "### R-001  T\nMay not exceed 25%.\n\ncheck: c\n"))[0]
    assert a.fingerprint != b.fingerprint


def test_changing_the_title_changes_the_fingerprint(tmp_path):
    a = parse(write_spec(tmp_path, "### R-001  Position limit\nBody.\n\ncheck: c\n"))[0]
    b = parse(write_spec(tmp_path, "### R-001  Exposure limit\nBody.\n\ncheck: c\n"))[0]
    assert a.fingerprint != b.fingerprint


# --- coverage --------------------------------------------------------------


def test_coverage_passes_when_everything_is_settled(tmp_path):
    reqs = parse(write_spec(tmp_path))
    result = coverage(reqs, {"universe", "position_limit"})
    assert result["ok"] is True
    assert result["by_check"] == 2
    assert result["by_human"] == 1


def test_coverage_fails_on_a_requirement_with_no_check_and_no_gate(tmp_path):
    spec = SPEC + "\n### R-005  Forgotten\nNobody decided how to settle this.\n"
    result = coverage(parse(write_spec(tmp_path, spec)), {"universe", "position_limit"})
    assert result["ok"] is False
    assert "R-005" in result["uncovered"]


def test_coverage_fails_when_a_requirement_points_at_a_missing_check(tmp_path):
    result = coverage(parse(write_spec(tmp_path)), {"universe"})
    assert result["ok"] is False
    assert any("position_limit" in d for d in result["dangling"])


def test_human_gate_counts_as_settled(tmp_path):
    """Marking something human-gated is honest, not a failure."""
    spec = "### R-003  Sound strategy\nJudgement call.\n\ngate: human\n"
    assert coverage(parse(write_spec(tmp_path, spec)), set())["ok"] is True


# --- sync / drift ----------------------------------------------------------


CONFIG = """\
project = "aria"

[[check]]
name = "position_limit"
cmd = "pytest tests/test_risk.py -q"
requirement = "R-002"
requirement_hash = "{h}"
"""

ONE_REQ = "### R-002  Position limit\nNo single position may exceed 20%.\n\ncheck: position_limit\n"


def _setup(tmp_path, spec_text=ONE_REQ, recorded=None):
    spec_path = write_spec(tmp_path, spec_text)
    req = parse(spec_path)[0]
    h = req.fingerprint if recorded is None else recorded
    cfg_path = tmp_path / "checks.toml"
    cfg_path.write_text(CONFIG.format(h=h), encoding="utf-8")
    return spec_path, cfg_path, req


def test_sync_passes_when_spec_matches_the_recorded_fingerprint(tmp_path):
    spec_path, cfg_path, _ = _setup(tmp_path)
    assert sync(parse(spec_path), load_config(cfg_path).checks)["ok"] is True


def test_sync_fails_when_the_spec_changed_after_review(tmp_path):
    """The whole point: edit 20% to 25% and the gate must not open."""
    _, cfg_path, _ = _setup(tmp_path)
    changed = write_spec(tmp_path, ONE_REQ.replace("20%", "25%"))
    result = sync(parse(changed), load_config(cfg_path).checks)
    assert result["ok"] is False
    assert "R-002" in result["reason"]


def test_sync_fails_when_a_check_was_never_reviewed(tmp_path):
    spec_path, cfg_path, _ = _setup(tmp_path, recorded="")
    result = sync(parse(spec_path), load_config(cfg_path).checks)
    assert result["ok"] is False
    assert "never reviewed" in result["reason"]


def test_sync_ignores_removed_requirements(tmp_path):
    spec = "### R-002  Position limit  [REMOVED]\nGone.\n\ncheck: position_limit\n"
    spec_path, cfg_path, _ = _setup(tmp_path, spec, recorded="deadbe")
    assert sync(parse(spec_path), load_config(cfg_path).checks)["ok"] is True


# --- bless -----------------------------------------------------------------


def test_bless_records_the_current_fingerprint(tmp_path):
    _, cfg_path, _ = _setup(tmp_path, recorded="staleh")
    changed = write_spec(tmp_path, ONE_REQ.replace("20%", "25%"))
    req = parse(changed)[0]

    assert sync([req], load_config(cfg_path).checks)["ok"] is False
    assert bless(cfg_path, "position_limit", req.fingerprint) is True
    assert sync([req], load_config(cfg_path).checks)["ok"] is True


def test_bless_adds_the_field_when_it_is_absent(tmp_path):
    spec_path = write_spec(tmp_path, ONE_REQ)
    req = parse(spec_path)[0]
    cfg_path = tmp_path / "checks.toml"
    cfg_path.write_text(
        'project = "aria"\n\n[[check]]\nname = "position_limit"\n'
        'cmd = "pytest -q"\nrequirement = "R-002"\n',
        encoding="utf-8",
    )
    assert bless(cfg_path, "position_limit", req.fingerprint) is True
    assert load_config(cfg_path).checks["position_limit"].requirement_hash == req.fingerprint


def test_bless_leaves_other_checks_alone(tmp_path):
    cfg_path = tmp_path / "checks.toml"
    cfg_path.write_text(
        'project = "aria"\n\n'
        '[[check]]\nname = "first"\ncmd = "a"\nrequirement_hash = "aaaaaa"\n\n'
        '[[check]]\nname = "second"\ncmd = "b"\nrequirement_hash = "bbbbbb"\n',
        encoding="utf-8",
    )
    bless(cfg_path, "second", "cccccc")
    checks = load_config(cfg_path).checks
    assert checks["first"].requirement_hash == "aaaaaa"
    assert checks["second"].requirement_hash == "cccccc"


def test_bless_preserves_comments_and_formatting(tmp_path):
    cfg_path = tmp_path / "checks.toml"
    cfg_path.write_text(
        "# keep me\nproject = \"aria\"\n\n[[check]]\nname = \"first\"\n"
        "cmd = \"a\"\n# and me\nrequirement_hash = \"aaaaaa\"\n",
        encoding="utf-8",
    )
    bless(cfg_path, "first", "cccccc")
    text = cfg_path.read_text(encoding="utf-8")
    assert "# keep me" in text and "# and me" in text


def test_bless_reports_an_unknown_check(tmp_path):
    _, cfg_path, _ = _setup(tmp_path)
    assert bless(cfg_path, "nonexistent", "abc123") is False


# --- status and amendments -------------------------------------------------

AMENDED_SPEC = """\
# ARIA

### R-001  Position limit
No single position may exceed 20% of book value.

amended: 2026-08-01  raised from 10% after the March drawdown
status: implemented
check: position_limit

### R-002  Old rule
Replaced by R-001.

amended: 2026-07-04  folded into R-001
status: superseded
gate: human
"""


def test_status_defaults_to_agreed_when_unstated(tmp_path):
    reqs = parse(write_spec(tmp_path))
    assert all(r.status == "agreed" for r in reqs)


def test_status_is_read_and_lowercased(tmp_path):
    reqs = parse(write_spec(tmp_path, AMENDED_SPEC.replace("implemented", "IMPLEMENTED")))
    assert reqs[0].status == "implemented"


def test_amendments_are_parsed_with_date_and_reason(tmp_path):
    reqs = parse(write_spec(tmp_path, AMENDED_SPEC))
    assert reqs[0].amendments[0].on == "2026-08-01"
    assert "March drawdown" in reqs[0].amendments[0].reason


def test_an_amendment_does_not_change_the_fingerprint(tmp_path):
    """Recording that something changed must not itself register as a change.

    Otherwise blessing a drifted requirement re-drifts it and you loop.
    """
    before = parse(write_spec(tmp_path, AMENDED_SPEC))[0].fingerprint
    after = parse(
        write_spec(
            tmp_path,
            AMENDED_SPEC.replace(
                "amended: 2026-08-01  raised from 10% after the March drawdown",
                "amended: 2026-08-01  raised from 10% after the March drawdown\n"
                "amended: 2026-08-02  confirmed with the risk desk",
            ),
        )
    )[0].fingerprint
    assert before == after


def test_status_does_not_change_the_fingerprint(tmp_path):
    a = parse(write_spec(tmp_path, AMENDED_SPEC))[0].fingerprint
    b = parse(write_spec(tmp_path, AMENDED_SPEC.replace("status: implemented", "status: draft")))[0].fingerprint
    assert a == b


def test_history_passes_when_every_change_is_explained(tmp_path):
    assert history(parse(write_spec(tmp_path, AMENDED_SPEC)))["ok"]


def test_history_rejects_an_unknown_status(tmp_path):
    reqs = parse(write_spec(tmp_path, AMENDED_SPEC.replace("status: draft", "status: maybe")
                            .replace("status: implemented", "status: shipped")))
    result = history(reqs)
    assert not result["ok"]
    assert "R-001" in result["reason"]


def test_history_rejects_superseded_with_no_reason(tmp_path):
    reqs = parse(write_spec(tmp_path, AMENDED_SPEC.replace("amended: 2026-07-04  folded into R-001\n", "")))
    result = history(reqs)
    assert not result["ok"]
    assert "R-002" in result["unexplained"]


def test_history_rejects_a_removal_with_no_reason(tmp_path):
    """A tombstone with no cause invites someone to re-add the rule."""
    result = history(parse(write_spec(tmp_path)))
    assert not result["ok"]
    assert "R-004" in result["silent_removal"]


def test_amend_writes_a_dated_line_under_the_requirement(tmp_path):
    p = write_spec(tmp_path)
    assert amend(p, "R-002", "limit raised to 20%", on="2026-08-01")
    reqs = parse(p)
    by_id = {r.id: r for r in reqs}
    assert str(by_id["R-002"].amendments[0]) == "2026-08-01  limit raised to 20%"
    assert by_id["R-001"].amendments == ()


def test_amend_returns_false_for_an_unknown_id(tmp_path):
    assert not amend(write_spec(tmp_path), "R-999", "nope")


def test_amend_leaves_every_other_requirement_untouched(tmp_path):
    p = write_spec(tmp_path)
    before = {r.id: r.fingerprint for r in parse(p)}
    amend(p, "R-002", "limit raised to 20%")
    assert {r.id: r.fingerprint for r in parse(p)} == before
