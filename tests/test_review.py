"""Review plumbing.

The harness assembles the bundle and records that a human ruled. It does not
review anything itself, and this file exists mostly to keep it that way.

The tempting version - hand the diff to a model, accept the answer - moves
judgement into the machine, which is the one thing the rest of this repo
argues cannot be automated. A reviewer the harness invokes and believes is
the agent grading itself with extra steps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.check import load_config  # noqa: E402
from harness.review import BUNDLE, extract_prompt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "HARNESS_HOME": str(cwd.parent / f"{cwd.name}-home")}
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=cwd, capture_output=True, text=True, env=env, timeout=180,
    )


def repo(tmp_path: Path, require_review: bool = False) -> Path:
    """A repo whose check passes or fails depending on a file, so tests can
    produce genuine red-then-green evidence rather than asserting around it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "checks.toml").write_text(
        'project = "r"\nspec = "spec.md"\nprotected = []\n'
        + ("require_review = true\n" if require_review else "")
        + '[[check]]\nname = "unit"\n'
        + 'cmd = "python -c \\"import pathlib,sys; sys.exit(0 if pathlib.Path(\'ok.txt\').exists() else 1)\\""\n',
        encoding="utf-8",
    )
    (tmp_path / "spec.md").write_text("# r\n\n### R-001  Thing\nIt works.\n\ncheck: unit\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def earn_green(cwd: Path) -> None:
    """Real red, then real green - the evidence the gate wants."""
    (cwd / "ok.txt").unlink(missing_ok=True)
    assert cli(cwd, "red", "unit").returncode == 0, "the check should have failed"
    (cwd / "ok.txt").write_text("", encoding="utf-8")
    assert cli(cwd, "run", "unit").returncode == 0, "the check should now pass"


def a_change(cwd: Path, text: str = "x = 2\n") -> None:
    (cwd / "app.py").write_text(text, encoding="utf-8")
    git(cwd, "add", "-A")
    git(cwd, "commit", "-qm", "change")


# --- assembling the bundle -------------------------------------------------


def test_the_bundle_carries_the_prompt_the_spec_and_the_diff(tmp_path):
    r = repo(tmp_path)
    git(r, "checkout", "-qb", "work")
    a_change(r)

    result = cli(r, "review", "--base", "main")
    assert result.returncode == 0, result.stderr

    text = (r / BUNDLE).read_text(encoding="utf-8")
    assert "WRONG" in text and "IRREVERSIBLE" in text, "prompt missing"
    assert "R-001" in text, "spec missing"
    assert "x = 2" in text, "diff missing"


def test_the_bundle_says_to_use_a_session_with_no_history(tmp_path):
    """The instruction is the load-bearing part. A reviewer given the
    author's reasoning stops noticing what the author should not have done."""
    r = repo(tmp_path)
    git(r, "checkout", "-qb", "work")
    a_change(r)
    cli(r, "review", "--base", "main")
    assert "no history" in (r / BUNDLE).read_text(encoding="utf-8")


def test_review_refuses_when_there_is_nothing_to_review(tmp_path):
    r = repo(tmp_path)
    result = cli(r, "review", "--base", "main")
    assert result.returncode == 2
    assert "nothing to review" in result.stderr


def test_the_prompt_is_extracted_without_its_prose():
    """The bundle should carry the instructions, not the essay around them."""
    md = "# Reviewer\n\nWhy separate: blah blah.\n\n## The prompt\n\n```\nDO THE THING\n```\n\n## Using it\n\nmore prose\n"
    assert extract_prompt(md) == "DO THE THING"


def test_prompt_extraction_refuses_a_file_with_no_fenced_block():
    """It used to fall back to the whole file, so a bundle would quietly
    carry an essay about reviewing instead of the instructions - looking
    fine and reviewing worse. Raised by a cold review of this very diff."""
    import pytest
    with pytest.raises(ValueError, match="no fenced prompt"):
        extract_prompt("no fenced block here, just prose")


def test_prompt_extraction_refuses_an_empty_block():
    import pytest
    with pytest.raises(ValueError):
        extract_prompt("## The prompt\n\n```\n\n```\n")


def test_review_refuses_to_write_a_bundle_from_a_malformed_prompt(tmp_path):
    r = repo(tmp_path)
    git(r, "checkout", "-qb", "work")
    a_change(r)
    (r / "reviewer").mkdir()
    (r / "reviewer" / "README.md").write_text("# Reviewer\n\nJust prose.\n", encoding="utf-8")

    result = cli(r, "review", "--base", "main")
    assert result.returncode == 2
    assert "malformed" in result.stderr
    assert not (r / BUNDLE).exists(), "a bad bundle must not be left behind"


# --- the trace must agree with what you were told --------------------------


def last_gate_evidence(cwd) -> str:
    """Read the reason recorded in the trace, not the one printed."""
    import json as _json
    home = cwd.parent / f"{cwd.name}-home"
    rows = [
        _json.loads(ln)
        for ln in (home / "r" / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    return next(r["evidence"] for r in reversed(rows) if r["phase"] == "gate")


def test_the_trace_records_the_same_reason_the_user_was_given(tmp_path):
    """The gate built one string for the trace and a different one for the
    terminal, so the evidence disagreed with what you were told - and the
    trace is the part that outlives the terminal. Found by a cold review."""
    r = repo(tmp_path, require_review=True)
    earn_green(r)
    result = cli(r, "gate", "unit")

    printed = result.stdout.strip().splitlines()[-1].replace("FAIL  ", "")
    assert "has not been reviewed" in printed
    assert "has not been reviewed" in last_gate_evidence(r)


def test_the_trace_records_a_hold_reason(tmp_path):
    r = repo(tmp_path, require_review=True)
    earn_green(r)
    cli(r, "review", "--record", "hold", "--note", "scope creep")
    cli(r, "gate", "unit")
    assert "scope creep" in last_gate_evidence(r)


def test_require_review_fails_closed_outside_a_repo(tmp_path):
    """It used to report 'reviewed and held: ' with an empty note, which is
    both wrong and confusing. Same rule as the guard: cannot verify, refuse -
    but say the true reason. Found by a cold review of this diff."""
    d = tmp_path / "loose"
    d.mkdir()
    (d / "checks.toml").write_text(
        'project = "r"\nprotected = []\nrequire_review = true\n'
        '[[check]]\nname = "unit"\n'
        'cmd = "python -c \\"import pathlib,sys; sys.exit(0 if pathlib.Path(\'ok.txt\').exists() else 1)\\""\n',
        encoding="utf-8",
    )
    assert cli(d, "red", "unit").returncode == 0
    (d / "ok.txt").write_text("", encoding="utf-8")
    assert cli(d, "run", "unit").returncode == 0

    result = cli(d, "gate", "unit")
    assert result.returncode == 1
    assert "not a git repository" in result.stdout
    assert "held" not in result.stdout


# --- recording a verdict ---------------------------------------------------


def test_recording_ship_is_traced(tmp_path):
    r = repo(tmp_path)
    assert cli(r, "review", "--record", "ship", "--note", "read it all").returncode == 0
    payload = json.loads(cli(r, "review", "--status", "--json").stdout)
    assert payload["reviewed"] and payload["verdict"] == "ship"


def test_a_hold_requires_a_reason(tmp_path):
    """A HOLD with no reason is not a review, it is a mood."""
    r = repo(tmp_path)
    result = cli(r, "review", "--record", "hold")
    assert result.returncode == 2
    assert "--note" in result.stderr


def test_a_hold_with_a_reason_is_recorded(tmp_path):
    r = repo(tmp_path)
    assert cli(r, "review", "--record", "hold", "--note", "scope is too wide").returncode == 0
    payload = json.loads(cli(r, "review", "--status", "--json").stdout)
    assert payload["verdict"] == "hold" and "scope is too wide" in payload["note"]


def test_status_reports_unreviewed_before_any_review(tmp_path):
    r = repo(tmp_path)
    result = cli(r, "review", "--status")
    assert result.returncode == 1
    assert "not been reviewed" in result.stdout


def test_a_review_does_not_carry_over_to_a_later_commit(tmp_path):
    """The failure this prevents: review once, then push three more commits
    under the same approval. Keyed on the revision, so it cannot."""
    r = repo(tmp_path)
    cli(r, "review", "--record", "ship", "--note", "fine")
    assert cli(r, "review", "--status").returncode == 0
    a_change(r)
    assert cli(r, "review", "--status").returncode == 1


def test_the_latest_verdict_wins(tmp_path):
    """Held, discussed, ruled again - the second ruling is the answer."""
    r = repo(tmp_path)
    cli(r, "review", "--record", "hold", "--note", "wait")
    cli(r, "review", "--record", "ship", "--note", "discussed, fine")
    assert json.loads(cli(r, "review", "--status", "--json").stdout)["verdict"] == "ship"


# --- require_review --------------------------------------------------------


def test_require_review_is_off_by_default(tmp_path):
    """A gate people route around is worse than no gate - it launders the
    habit into a green."""
    assert load_config(repo(tmp_path) / "checks.toml").require_review is False


def test_require_review_is_read_from_the_config(tmp_path):
    assert load_config(repo(tmp_path, require_review=True) / "checks.toml").require_review is True


def test_the_gate_shows_the_review_row_only_when_required(tmp_path):
    assert "reviewed" not in cli(repo(tmp_path / "off"), "gate", "unit").stdout
    assert "reviewed" in cli(repo(tmp_path / "on", require_review=True), "gate", "unit").stdout


def test_the_gate_refuses_an_unreviewed_revision(tmp_path):
    """Everything else green, so review is unambiguously what blocks it."""
    r = repo(tmp_path, require_review=True)
    earn_green(r)
    result = cli(r, "gate", "unit")
    assert result.returncode == 1
    assert "has not been reviewed" in result.stdout


def test_the_gate_refuses_a_held_revision(tmp_path):
    r = repo(tmp_path, require_review=True)
    earn_green(r)
    cli(r, "review", "--record", "hold", "--note", "the approach is wrong")
    result = cli(r, "gate", "unit")
    assert result.returncode == 1
    assert "the approach is wrong" in result.stdout


def test_the_gate_opens_once_the_evidence_and_the_ruling_are_both_there(tmp_path):
    """Proved in both directions: it must also open, or it is an obstacle
    rather than a gate."""
    r = repo(tmp_path, require_review=True)
    earn_green(r)
    cli(r, "review", "--record", "ship", "--note", "read it")
    result = cli(r, "gate", "unit")
    assert result.returncode == 0, result.stdout
    assert "reviewed         yes" in result.stdout


def test_a_recorded_ship_does_not_by_itself_open_the_gate(tmp_path):
    """Review is an extra condition, never a substitute for the evidence. A
    human saying 'looks fine' must not stand in for red-then-green."""
    r = repo(tmp_path, require_review=True)
    cli(r, "review", "--record", "ship", "--note", "looks fine")
    result = cli(r, "gate", "unit")
    assert result.returncode == 1
    assert "reviewed         yes" in result.stdout
    assert "saw red          no" in result.stdout


# --- what it must never do -------------------------------------------------


def test_the_harness_does_not_invoke_a_model():
    """The line this module exists to hold. If the harness ever calls out to
    a model and believes the answer, judgement has moved into the machine and
    require_review becomes satisfiable by something that read nothing."""
    source = (ROOT / "harness" / "review.py").read_text(encoding="utf-8")
    for banned in ("openai", "anthropic", "requests", "urllib", "http"):
        assert banned not in source.lower(), f"review.py reaches for {banned}"


def test_the_bundle_is_not_committable():
    """It contains a whole diff and gets regenerated constantly."""
    assert BUNDLE in (ROOT / ".gitignore").read_text(encoding="utf-8")
