"""Attacks that succeeded once, replayed so they cannot succeed again.

Every test here corresponds to a real bypass found by a security review of
v0.6.1, with the gate observed exiting 0 when it should not have. A fix
without a replay is a fix that gets undone by the next refactor and nobody
notices, because the thing it broke is invisible until someone attacks it.

The threat model: an agent with full write access to the project directory,
and no access to HARNESS_HOME. It wants `harness gate` to exit 0 without
having done the work.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.check import DEFAULT_PROTECTED, load_config  # noqa: E402
from harness.trace import Trace, safe_project  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "HARNESS_HOME": str(cwd.parent / f"{cwd.name}-home")}
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=cwd, capture_output=True, text=True, env=env, timeout=180,
    )


def victim(tmp_path: Path, expect: int = 0, protected: str | None = None) -> Path:
    """A project with one check that fails, so a red can be earned honestly."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_it.py").write_text("def test_it(): assert False\n", encoding="utf-8")
    (tmp_path / "checks.toml").write_text(
        'project = "v"\n'
        + (f"protected = {protected}\n" if protected else "")
        + f'[[check]]\nname = "unit"\ncmd = "python -m pytest tests -q"\nexpect = {expect}\n',
        encoding="utf-8",
    )
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    return tmp_path


# --- Attack 1: flip `expect` so failing means passing ----------------------


def test_changing_expect_does_not_inherit_the_old_red(tmp_path):
    """FOUND LIVE, gate exited 0.

    Earn a red with expect=0, then set expect=1. The command never changes,
    so the old red matched, and the still-failing test now counted as green.
    `expect` decides what passing means, so it is part of the check's
    identity - not metadata about it.
    """
    v = victim(tmp_path)
    assert cli(v, "red", "unit").returncode == 0, "the check should fail honestly first"

    cfg = v / "checks.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("expect = 0", "expect = 1"), encoding="utf-8")

    cli(v, "run", "unit")
    result = cli(v, "gate", "unit")
    assert result.returncode == 1, f"gate opened on a still-failing test:\n{result.stdout}"
    assert "saw red          no" in result.stdout, result.stdout


def test_expect_is_committed_to_by_the_mac(tmp_path):
    """Editing `expect` in a recorded row must break the chain, or the value
    could be changed after the fact and the row would silently mean something
    different."""
    home = tmp_path / "home"
    os.environ["HARNESS_HOME"] = str(home)
    try:
        t = Trace("p")
        t.append("unit", "cmd", "red", False, 1, "", 0)
        assert t.verify()["ok"]

        rows = [json.loads(ln) for ln in t.path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        rows[0]["expect"] = 1
        t.path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

        assert not t.verify()["ok"], "expect was edited and the chain still verified"
    finally:
        os.environ.pop("HARNESS_HOME", None)


# --- Attack 2: configure the tests out of existence ------------------------


def test_a_root_conftest_is_protected_by_default(tmp_path):
    """FOUND LIVE, gate exited 0.

    A conftest.py at the project root that skips every test. Pytest exits 0
    for skipped tests, so the check went green, and the guard said nothing
    because conftest.py was outside `tests/`.
    """
    v = victim(tmp_path)
    assert cli(v, "red", "unit").returncode == 0

    (v / "conftest.py").write_text(
        "import pytest\n"
        "def pytest_collection_modifyitems(items):\n"
        "    for i in items: i.add_marker(pytest.mark.skip('bypass'))\n",
        encoding="utf-8",
    )
    cli(v, "run", "unit")
    result = cli(v, "gate", "unit")
    assert result.returncode == 1, f"gate opened with the tests skipped:\n{result.stdout}"
    assert "conftest.py" in result.stdout, result.stdout


def test_a_nested_conftest_is_protected_too(tmp_path):
    """The same trick one directory down."""
    v = victim(tmp_path)
    (v / "src").mkdir()
    (v / "src" / "conftest.py").write_text("# added\n", encoding="utf-8")

    from harness.guard import check_protected
    result = check_protected(v, DEFAULT_PROTECTED)
    assert not result["ok"], "a nested conftest.py slipped past the guard"


def test_the_default_does_not_protect_files_edited_for_ordinary_reasons():
    """Both directions. pyproject.toml configures the grader AND holds your
    dependencies - protecting it by default would fire on normal work, and a
    guard that cries wolf gets switched off, which catches nothing."""
    assert "pyproject.toml" not in DEFAULT_PROTECTED
    assert "setup.cfg" not in DEFAULT_PROTECTED


def test_the_default_still_protects_the_tests_themselves():
    assert "tests/" in DEFAULT_PROTECTED


# --- Attack 5: escape HARNESS_HOME via the project name --------------------


def test_a_project_name_cannot_be_a_path():
    """FOUND LIVE.

    `project = "../../elsewhere"` in checks.toml put the trace outside
    HARNESS_HOME - overwriting another project's evidence, or landing
    somewhere the agent can reach. The name comes from a file the agent
    writes, so it does not get to be a path.
    """
    for bad in ("../../evil", "..\\..\\evil", "a/b", "a\\b", "..", ".", "", "/abs"):
        with pytest.raises(ValueError):
            safe_project(bad)


def test_an_ordinary_project_name_still_works():
    """Both directions - the fix must not reject normal names."""
    for good in ("aria", "my-project", "my_project", "proj.2", "Selah"):
        assert safe_project(good) == good


def test_a_traversing_project_name_is_refused_end_to_end(tmp_path):
    os.environ["HARNESS_HOME"] = str(tmp_path / "home")
    try:
        with pytest.raises(ValueError):
            Trace("../../escaped")
    finally:
        os.environ.pop("HARNESS_HOME", None)


def test_the_trace_lands_under_harness_home(tmp_path):
    home = tmp_path / "home"
    os.environ["HARNESS_HOME"] = str(home)
    try:
        assert home.resolve() in Trace("p").path.parents
    finally:
        os.environ.pop("HARNESS_HOME", None)


# --- Attacks 3 and 4: the limits, stated rather than hidden ----------------


def test_the_documented_limits_are_written_down():
    """Two attacks cannot be closed by code, and pretending otherwise would
    be worse than the hole:

      3. HARNESS_HOME is an environment variable. Whoever sets the
         environment of the gate chooses which key is used.
      4. `harness review --record ship` is a command. Whoever can run
         commands can record a ruling.

    Both reduce to the same thing: the gate has to be run by the person doing
    the trusting. That is stated in the README and AGENTS.md already, but it
    has to be stated as a LIMIT, not as a habit - so this asserts the words
    are there.
    """
    docs = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    assert "HARNESS_HOME" in docs
    assert "What this cannot stop" in docs
