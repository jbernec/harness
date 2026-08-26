"""Version pinning across projects.

A shared harness only means something if "green" means the same thing
everywhere it is used. Five repos on five versions is five different
definitions of done, and nothing surfaces it - each repo still passes its
own checks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.check import load_config  # noqa: E402
from harness.init import init  # noqa: E402
from harness.version import __version__, compatible, feature_release, status  # noqa: E402


# --- comparison ------------------------------------------------------------


def test_patch_releases_are_interchangeable():
    """Patches are fixes. Forcing five repos to move together for a bug fix
    makes upgrading painful enough that nobody does it."""
    assert compatible("0.4.0", "0.4.7")
    assert compatible("0.4.7", "0.4.0")


def test_a_different_feature_release_is_not_compatible():
    assert not compatible("0.4.0", "0.5.0")
    assert not compatible("1.0.0", "2.0.0")


def test_a_newer_harness_is_not_automatically_fine():
    """It may add a gate condition, in which case older evidence was gathered
    under weaker rules. Symmetric on purpose."""
    assert not compatible("0.4.0", "0.9.0")


def test_a_two_part_version_is_accepted():
    assert feature_release("1.2") == (1, 2)
    assert compatible("1.2", "1.2.9")


def test_garbage_is_not_a_version():
    with pytest.raises(ValueError):
        feature_release("latest")


# --- status ----------------------------------------------------------------


def test_unpinned_passes_but_says_what_to_add():
    result = status("", "0.5.0")
    assert result["ok"]
    assert 'harness_version = "0.5.0"' in result["reason"]


def test_a_match_passes():
    assert status("0.5.0", "0.5.1")["ok"]


def test_a_mismatch_fails_and_names_both_versions():
    result = status("0.4.0", "0.5.0")
    assert not result["ok"]
    assert "0.4.0" in result["reason"] and "0.5.0" in result["reason"]


def test_an_unparseable_pin_fails_rather_than_being_ignored():
    """Silently ignoring a broken pin is the same as having no pin, except it
    looks like you have one."""
    assert not status("main", "0.5.0")["ok"]


# --- config ----------------------------------------------------------------


def test_the_pin_is_read_from_the_config(tmp_path):
    p = tmp_path / "checks.toml"
    p.write_text(
        'project = "p"\nharness_version = "0.4.0"\n[[check]]\nname = "u"\ncmd = "true"\n',
        encoding="utf-8",
    )
    assert load_config(p).harness_version == "0.4.0"


def test_an_absent_pin_reads_as_empty(tmp_path):
    p = tmp_path / "checks.toml"
    p.write_text('project = "p"\n[[check]]\nname = "u"\ncmd = "true"\n', encoding="utf-8")
    assert load_config(p).harness_version == ""


# --- init ------------------------------------------------------------------


def test_init_pins_the_version_it_wrote_with(tmp_path):
    init(tmp_path, project="demo")
    assert load_config(tmp_path / "checks.toml").harness_version == __version__


def test_init_writes_a_version_check(tmp_path):
    init(tmp_path, project="demo")
    assert "harness_version" in load_config(tmp_path / "checks.toml").checks


def test_a_fresh_init_passes_its_own_version_check(tmp_path):
    """The starting point must be green, or the first thing a new project
    sees is a failure it did not cause."""
    init(tmp_path, project="demo")
    cfg = load_config(tmp_path / "checks.toml")
    assert status(cfg.harness_version, __version__)["ok"]


def test_a_fresh_init_is_green_on_every_scaffolded_check(tmp_path):
    """Same reason, wider: a scaffold that is red on day one for a reason
    nobody caused is how a check earns a reputation for crying wolf, and a
    check people learn to ignore catches nothing."""
    from harness.spec import coverage, history, parse, sync

    init(tmp_path, project="demo")
    cfg = load_config(tmp_path / "checks.toml")
    reqs = parse(tmp_path / "spec.md")

    assert coverage(reqs, set(cfg.checks))["ok"]
    assert sync(reqs, cfg.checks)["ok"], "the scaffold must not be born drifted"
    assert history(reqs)["ok"]


def test_editing_the_scaffolded_spec_then_goes_red(tmp_path):
    """Blessing at init must not disarm the drift check - it must arm it."""
    from harness.spec import parse, sync

    init(tmp_path, project="demo")
    p = tmp_path / "spec.md"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "<What must be true.", "<Something completely different."
        ),
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "checks.toml")
    assert not sync(parse(p), cfg.checks)["ok"]


# --- CI --------------------------------------------------------------------


def test_init_writes_a_workflow(tmp_path):
    result = init(tmp_path, project="demo")
    assert ".github/workflows/harness.yml" in result["written"]
    assert (tmp_path / ".github/workflows/harness.yml").exists()


def test_the_workflow_installs_the_pinned_version(tmp_path):
    """A workflow that installs whatever is on main defeats the pin."""
    init(tmp_path, project="demo")
    text = (tmp_path / ".github/workflows/harness.yml").read_text(encoding="utf-8")
    assert f"@v{__version__}" in text


def test_the_workflow_is_valid_yaml(tmp_path):
    yaml = pytest.importorskip("yaml")
    init(tmp_path, project="demo")
    doc = yaml.safe_load((tmp_path / ".github/workflows/harness.yml").read_text(encoding="utf-8"))
    assert "checks" in doc["jobs"]


def test_ci_can_be_declined(tmp_path):
    result = init(tmp_path, project="demo", ci=False)
    assert not (tmp_path / ".github").exists()
    assert ".github/workflows/harness.yml" not in result["written"]


def test_init_does_not_overwrite_an_existing_workflow(tmp_path):
    wf = tmp_path / ".github/workflows/harness.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("mine", encoding="utf-8")
    result = init(tmp_path, project="demo")
    assert wf.read_text(encoding="utf-8") == "mine"
    assert ".github/workflows/harness.yml" in result["skipped"]


# --- the CLI actually refuses ----------------------------------------------


def cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    root = Path(__file__).resolve().parents[1]
    env = {
        **__import__("os").environ,
        "PYTHONPATH": str(root),
        "HARNESS_HOME": str(cwd / ".harness-home"),
    }
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=cwd, capture_output=True, text=True, env=env, timeout=120,
    )


def test_cli_version_exits_zero_when_pinned_correctly(tmp_path):
    init(tmp_path, project="demo")
    assert cli(tmp_path, "version").returncode == 0


def test_cli_version_exits_nonzero_on_a_mismatch(tmp_path):
    """The whole point. If this exits 0, the pin is decoration."""
    init(tmp_path, project="demo")
    p = tmp_path / "checks.toml"
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            f'harness_version = "{__version__}"', 'harness_version = "0.1.0"'
        ),
        encoding="utf-8",
    )
    result = cli(tmp_path, "version")
    assert result.returncode == 1
    assert "0.1.0" in result.stdout


# --- the harness pins itself -----------------------------------------------


def test_the_packaged_version_matches_the_module():
    """Two places holding the same number is two places to get it wrong."""
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in pyproject
