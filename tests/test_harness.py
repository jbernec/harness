"""The harness must pass its own standard.

The most important test in this file is test_forged_chain_is_rejected. It is
the exact attack that defeats a plain SHA-256 chain: rewrite the log, recompute
every hash, and present a clean red->green history for work that never
happened. Without a key held outside the project, that attack succeeds.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.check import DEFAULT_GUARD_IGNORE, Check, did_not_run, load_config, run  # noqa: E402
from harness.gate import evaluate  # noqa: E402
from harness.guard import check_protected  # noqa: E402
from harness.trace import Trace  # noqa: E402

PASSING = Check(name="passing", cmd=f'"{sys.executable}" -c "raise SystemExit(0)"', expect=0)
FAILING = Check(name="failing", cmd=f'"{sys.executable}" -c "raise SystemExit(1)"', expect=0)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_HOME", str(tmp_path / "home"))
    return tmp_path


# ── checks ────────────────────────────────────────────────────────

def test_check_reads_exit_code(tmp_path):
    assert run(PASSING, tmp_path).ok is True
    assert run(FAILING, tmp_path).ok is False


def test_nonzero_expect_inverts_the_verdict(tmp_path):
    inverted = Check(name="inverted", cmd=FAILING.cmd, expect=1)
    assert run(inverted, tmp_path).ok is True


def test_timeout_is_a_failure_not_a_hang(tmp_path):
    slow = Check(name="slow", cmd=f'"{sys.executable}" -c "import time; time.sleep(30)"', timeout=1)
    result = run(slow, tmp_path)
    assert result.ok is False
    assert "TIMEOUT" in result.output


# ── trace ─────────────────────────────────────────────────────────

def test_chain_verifies_when_untouched(home):
    tr = Trace("demo")
    tr.append("c", "cmd", "red", False, 1)
    tr.append("c", "cmd", "run", True, 0)
    assert tr.verify()["ok"] is True


def test_edited_row_breaks_the_chain(home):
    tr = Trace("demo")
    tr.append("c", "cmd", "red", False, 1)
    rows = [json.loads(x) for x in tr.path.read_text().splitlines()]
    rows[0]["ok"] = True  # flip the failure into a success
    tr.path.write_text(json.dumps(rows[0]) + "\n")
    assert tr.verify()["ok"] is False


def test_deleted_row_breaks_the_chain(home):
    tr = Trace("demo")
    tr.append("c", "cmd", "red", False, 1)
    tr.append("c", "cmd", "run", True, 0)
    lines = tr.path.read_text().splitlines()
    tr.path.write_text(lines[1] + "\n")  # drop the RED, keep the GREEN
    assert tr.verify()["ok"] is False


def test_unparseable_row_is_a_break_not_an_absence(home):
    """Destroying a row must not produce a shorter chain that still verifies."""
    tr = Trace("demo")
    tr.append("c", "cmd", "red", False, 1)
    tr.append("c", "cmd", "run", True, 0)
    lines = tr.path.read_text().splitlines()
    tr.path.write_text("{not json\n" + lines[1] + "\n")
    result = tr.verify()
    assert result["ok"] is False
    assert result["rows"] == 2


def test_forged_chain_is_rejected(home):
    """Recomputing every hash without the key must not produce a valid chain."""
    tr = Trace("demo")
    tr.append("c", "cmd", "red", False, 1)

    def unkeyed_hash(row):
        body = {k: row[k] for k in ("ts", "check", "cmd", "phase", "ok", "exit_code", "evidence")}
        h = sha256()
        h.update(row["prev"].encode())
        h.update(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
        return h.hexdigest()

    forged = []
    prev = "GENESIS"
    for ok, phase in [(False, "red"), (True, "run")]:
        row = {
            "ts": "2026-01-01T00:00:00", "check": "c", "cmd": "cmd", "phase": phase,
            "ok": ok, "exit_code": 0 if ok else 1,
            "evidence": "FABRICATED - never executed", "prev": prev, "mac": "",
        }
        row["mac"] = unkeyed_hash(row)
        prev = row["mac"]
        forged.append(json.dumps(row))
    tr.path.write_text("\n".join(forged) + "\n")

    assert tr.verify()["ok"] is False, "a forged chain must never verify"


def test_trace_lives_outside_the_project(home, tmp_path):
    tr = Trace("demo")
    project = (tmp_path / "project").resolve()
    project.mkdir()
    assert project not in tr.path.resolve().parents


# ── gate ──────────────────────────────────────────────────────────

def test_gate_rejects_a_check_never_seen_failing(home, tmp_path):
    """The vacuous-check guard: passing now proves nothing on its own."""
    tr = Trace("demo")
    tr.append(PASSING.name, PASSING.cmd, "run", True, 0)
    verdict = evaluate(tr, PASSING, tmp_path)
    assert verdict.ok is False
    assert verdict.saw_red is False


def test_gate_accepts_red_then_green(home, tmp_path):
    tr = Trace("demo")
    tr.append(PASSING.name, PASSING.cmd, "red", False, 1)
    tr.append(PASSING.name, PASSING.cmd, "run", True, 0)
    verdict = evaluate(tr, PASSING, tmp_path)
    assert verdict.ok is True


def test_gate_rejects_when_it_regressed(home, tmp_path):
    """Old red->green evidence cannot cover for a check that is red now."""
    tr = Trace("demo")
    tr.append(FAILING.name, FAILING.cmd, "red", False, 1)
    tr.append(FAILING.name, FAILING.cmd, "run", True, 0)
    verdict = evaluate(tr, FAILING, tmp_path)
    assert verdict.currently_green is False
    assert verdict.ok is False


def test_gate_rejects_green_before_red(home, tmp_path):
    tr = Trace("demo")
    tr.append(PASSING.name, PASSING.cmd, "run", True, 0)
    tr.append(PASSING.name, PASSING.cmd, "run", False, 1)
    assert evaluate(tr, PASSING, tmp_path).ok is False


def test_weakening_the_command_discards_old_red_evidence(home, tmp_path):
    """Swapping in an easier command makes it a different check."""
    tr = Trace("demo")
    tr.append("same-name", "the-original-strict-command", "red", False, 1)
    tr.append("same-name", "the-original-strict-command", "run", True, 0)
    weakened = Check(name="same-name", cmd=PASSING.cmd, expect=0)
    assert evaluate(tr, weakened, tmp_path).saw_red is False


def test_gate_rejects_when_chain_is_broken(home, tmp_path):
    tr = Trace("demo")
    tr.append(PASSING.name, PASSING.cmd, "red", False, 1)
    tr.append(PASSING.name, PASSING.cmd, "run", True, 0)

    rows = [json.loads(x) for x in tr.path.read_text().splitlines() if x.strip()]
    assert rows[0]["ok"] is False
    rows[0]["ok"] = True  # rewrite history: pretend it never failed
    tr.path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    assert tr.verify()["ok"] is False
    assert evaluate(tr, PASSING, tmp_path).ok is False


# ── guard ─────────────────────────────────────────────────────────

def _git_repo(path: Path) -> None:
    for args in (["init", "-q"], ["config", "user.email", "h@h"], ["config", "user.name", "h"]):
        subprocess.run(["git", *args], cwd=path, capture_output=True)
    (path / "tests").mkdir(exist_ok=True)
    (path / "tests" / "test_x.py").write_text("def test_x(): assert True\n")
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, capture_output=True)


def test_guard_passes_when_tests_untouched(tmp_path):
    _git_repo(tmp_path)
    assert check_protected(tmp_path, ["tests/"])["ok"] is True


def test_guard_catches_an_edited_test(tmp_path):
    _git_repo(tmp_path)
    (tmp_path / "tests" / "test_x.py").write_text("def test_x(): pass  # weakened\n")
    result = check_protected(tmp_path, ["tests/"])
    assert result["ok"] is False
    assert "tests/test_x.py" in result["changed"]


def test_guard_catches_a_new_untracked_test(tmp_path):
    _git_repo(tmp_path)
    (tmp_path / "tests" / "test_sneaky.py").write_text("def test_easy(): assert True\n")
    assert check_protected(tmp_path, ["tests/"])["ok"] is False


def test_guard_fails_closed_outside_a_repo(tmp_path):
    assert check_protected(tmp_path, ["tests/"])["ok"] is False


def test_guard_ignores_build_artifacts(tmp_path):
    """Running a check writes __pycache__ into tests/. That is not an edit."""
    _git_repo(tmp_path)
    cache = tmp_path / "tests" / "__pycache__"
    cache.mkdir()
    (cache / "test_x.cpython-311-pytest-9.1.1.pyc").write_bytes(b"\x00binary")

    assert check_protected(tmp_path, ["tests/"])["ok"] is False, "no ignore list means no filtering"
    assert check_protected(tmp_path, ["tests/"], ignore=DEFAULT_GUARD_IGNORE)["ok"] is True


def test_guard_still_catches_real_edits_alongside_artifacts(tmp_path):
    """Ignoring artifacts must not let a real test edit slip through with them."""
    _git_repo(tmp_path)
    cache = tmp_path / "tests" / "__pycache__"
    cache.mkdir()
    (cache / "test_x.cpython-311.pyc").write_bytes(b"\x00")
    (tmp_path / "tests" / "test_x.py").write_text("def test_x(): pass  # weakened\n")

    result = check_protected(tmp_path, ["tests/"], ignore=DEFAULT_GUARD_IGNORE)
    assert result["ok"] is False
    assert result["changed"] == ["tests/test_x.py"]


def test_guard_ignore_does_not_match_a_test_named_like_a_pattern(tmp_path):
    """'*.pyc' must not be stretched to hide a real .py test file."""
    _git_repo(tmp_path)
    (tmp_path / "tests" / "test_pycache.py").write_text("def test_a(): assert True\n")
    result = check_protected(tmp_path, ["tests/"], ignore=DEFAULT_GUARD_IGNORE)
    assert result["ok"] is False
    assert "tests/test_pycache.py" in result["changed"]


# ── config ────────────────────────────────────────────────────────

def test_config_round_trips(tmp_path):
    (tmp_path / "checks.toml").write_text(
        'project = "demo"\n\n[[check]]\nname = "unit"\ncmd = "pytest -q"\nexpect = 0\n'
    )
    cfg = load_config(tmp_path / "checks.toml")
    assert cfg.project == "demo"
    assert cfg.checks["unit"].cmd == "pytest -q"
    assert cfg.protected == ["tests/"]


def test_config_rejects_duplicate_names(tmp_path):
    (tmp_path / "checks.toml").write_text(
        'project = "d"\n[[check]]\nname = "a"\ncmd = "x"\n[[check]]\nname = "a"\ncmd = "y"\n'
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_config(tmp_path / "checks.toml")


def test_config_requires_a_project_name(tmp_path):
    (tmp_path / "checks.toml").write_text('[[check]]\nname = "a"\ncmd = "x"\n')
    with pytest.raises(ValueError, match="project"):
        load_config(tmp_path / "checks.toml")


# ── cli ───────────────────────────────────────────────────────────

def test_red_step_fails_when_the_check_already_passes(home, tmp_path):
    """The single most useful error message in the tool."""
    from harness.cli import main
    (tmp_path / "checks.toml").write_text(
        f'project = "cli"\n\n[[check]]\nname = "vacuous"\ncmd = {json.dumps(PASSING.cmd)}\nexpect = 0\n'
    )
    code = main(["--cwd", str(tmp_path), "--config", str(tmp_path / "checks.toml"), "--json", "red", "vacuous"])
    assert code == 1


# ── a red the check never earned ──────────────────────────────────
#
# A test file that does not exist yet fails exactly like a test that fails.
# Without this, you bank a red against a file you never wrote, then write
# anything at all and the gate accepts it. Found while building selah: the
# workaround was to hand-write a stub so the red was an AssertionError, which
# is discipline, not enforcement.

def test_did_not_run_distinguishes_pytest_failure_from_pytest_never_running():
    real = Check(name="t", cmd="python -m pytest tests/test_x.py -q")
    assert did_not_run(real, 1) is None          # tests ran, one failed
    assert did_not_run(real, 2) is not None      # ImportError while collecting
    assert did_not_run(real, 4) is not None      # test path does not exist
    assert did_not_run(real, 5) is not None      # nothing collected


def test_command_not_found_is_never_a_red():
    for cmd in ("python -m pytest x.py", "cargo test", "go test ./...", "npm test"):
        assert did_not_run(Check(name="t", cmd=cmd), 127) is not None
        assert did_not_run(Check(name="t", cmd=cmd), 126) is not None


def test_non_pytest_runners_keep_their_own_exit_codes():
    """Only pytest's codes are known. Guessing for other runners would reject
    legitimate reds, which is worse than the hole it closes."""
    assert did_not_run(Check(name="t", cmd="cargo test"), 2) is None
    assert did_not_run(Check(name="t", cmd="go test ./..."), 5) is None


def test_a_check_may_declare_its_own_inconclusive_codes():
    declared = Check(name="t", cmd="make verify", inconclusive=(3,))
    assert did_not_run(declared, 3) is not None
    assert did_not_run(declared, 1) is None
    # An explicit empty list opts out of inference entirely.
    optout = Check(name="t", cmd="python -m pytest x.py", inconclusive=())
    assert did_not_run(optout, 5) is None


def test_red_refuses_a_check_that_never_ran(home, tmp_path):
    from harness.cli import main
    missing = f'"{sys.executable}" -m pytest {tmp_path / "no_such_test.py"} -q'
    (tmp_path / "checks.toml").write_text(
        f'project = "void"\n\n[[check]]\nname = "phantom"\ncmd = {json.dumps(missing)}\nexpect = 0\n'
    )
    argv = ["--cwd", str(tmp_path), "--config", str(tmp_path / "checks.toml"), "--json"]
    assert main(argv + ["red", "phantom"]) == 1

    # and it must not have left red evidence behind
    rows = Trace("void").rows()
    assert rows, "the attempt should still be recorded"
    assert all(r["phase"] == "void" for r in rows)
    assert all(r["phase"] != "red" for r in rows)


def test_a_void_row_cannot_satisfy_the_gate(home, tmp_path):
    """The hole this closes: void evidence must not reach saw_red."""
    trace = Trace("voidgate")
    trace.append(FAILING.name, FAILING.cmd, "void", False, 5, "no tests ran")
    trace.append(FAILING.name, FAILING.cmd, "run", True, 0, "")
    passing_under_same_name = Check(name=FAILING.name, cmd=FAILING.cmd, expect=1)
    verdict = evaluate(trace, passing_under_same_name, tmp_path)
    assert verdict.saw_red is False
    assert verdict.ok is False


def test_a_real_red_still_satisfies_the_gate(home, tmp_path):
    """The guard must pass on legitimate work, not only block the bad case."""
    trace = Trace("realred")
    trace.append(FAILING.name, FAILING.cmd, "red", False, 1, "assert 1 == 2")
    trace.append(FAILING.name, FAILING.cmd, "run", True, 1, "")
    inverted = Check(name=FAILING.name, cmd=FAILING.cmd, expect=1)
    verdict = evaluate(trace, inverted, tmp_path)
    assert verdict.saw_red is True
    assert verdict.ok is True
