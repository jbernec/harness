"""The examples, and the memory files.

`examples/*.toml` are the first thing anyone copies, and until now nothing
checked them. A starting point that does not parse teaches people the tool is
broken before they reach anything real - and it fails on their machine, not
in this repo, which is the worst place to find out.

These cannot assert the example commands actually run: they name tools that
do not exist here, deliberately. What they can assert is that every example
is structurally valid, internally consistent, and does not contradict the
rules the docs state.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.check import Check, load_config  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "examples").glob("*.toml"))
ALL_CONFIGS = EXAMPLES + [ROOT / "checks.toml.example", ROOT / "checks.toml"]


def test_there_are_examples_to_check():
    assert EXAMPLES, "no examples found - this file is guarding nothing"


def test_every_config_parses():
    for path in ALL_CONFIGS:
        tomllib.loads(path.read_text(encoding="utf-8"))


def test_every_config_loads_as_a_real_config():
    """Parsing as TOML is not enough - it has to survive load_config, which
    is what the CLI actually does."""
    for path in ALL_CONFIGS:
        cfg = load_config(path)
        assert cfg.project, f"{path.name} has no project name"
        assert cfg.checks, f"{path.name} defines no checks"


def test_no_config_has_duplicate_check_names():
    """load_config raises on duplicates, so this is really asserting that the
    examples do not lean on that error path."""
    for path in ALL_CONFIGS:
        names = [c["name"] for c in tomllib.loads(path.read_text(encoding="utf-8")).get("check", [])]
        assert len(names) == len(set(names)), f"{path.name} repeats a check name"


def test_every_check_describes_itself():
    """A check whose failure means nothing to the reader gets deleted rather
    than fixed. The examples are where the habit is set."""
    thin = []
    for path in ALL_CONFIGS:
        for check in load_config(path).checks.values():
            if not check.description and path.name != "checks.toml.example":
                thin.append(f"{path.name}:{check.name}")
    assert not thin, f"checks with no description: {thin}"


def test_expect_is_always_a_plausible_exit_code():
    for path in ALL_CONFIGS:
        for check in load_config(path).checks.values():
            assert 0 <= check.expect <= 255, f"{path.name}:{check.name} expects {check.expect}"


def test_scoped_checks_use_paths_not_globs_of_nothing():
    """A `files` pattern that can never match makes the check invisible to
    `select` while looking scoped."""
    for path in ALL_CONFIGS:
        for check in load_config(path).checks.values():
            for pattern in check.files:
                assert pattern.strip(), f"{path.name}:{check.name} has an empty files pattern"
                assert not pattern.startswith("/"), (
                    f"{path.name}:{check.name} pattern {pattern!r} is absolute - "
                    "patterns are relative to the project"
                )


def test_a_scoped_check_actually_concerns_its_own_paths():
    """Derived, not typed: take the check's own first pattern, build a path
    that should match it, and assert it does. A scoping rule nobody exercises
    is a check that silently never runs."""
    for path in ALL_CONFIGS:
        for check in load_config(path).checks.values():
            if not check.files:
                continue
            pattern = check.files[0]
            sample = pattern.rstrip("/") + "/f.py" if pattern.endswith("/") else pattern.replace("*", "x")
            assert check.concerns([sample]), (
                f"{path.name}:{check.name} does not match {sample!r}, "
                f"built from its own pattern {pattern!r}"
            )


def test_unscoped_checks_always_run():
    """The safe default, stated in the docs. Worth asserting rather than
    trusting, because getting it backwards silently skips checks."""
    assert Check(name="x", cmd="true").concerns(["anything.py"])
    assert Check(name="x", cmd="true").concerns([])


def test_every_example_declares_what_it_protects():
    """Reads the raw TOML, not the loaded config.

    Checking `load_config(...).protected` could never fail here, because the
    loader defaults to ["tests/"] when the key is absent - so the test would
    pass for an example that never mentions protection at all. A check that
    can only ever pass is decoration. What matters is that each example says
    so explicitly, since examples set the habit.
    """
    silent = []
    for path in EXAMPLES:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if "protected" not in data or not data["protected"]:
            silent.append(path.name)
    assert not silent, f"examples that never declare `protected`: {silent}"


def test_examples_that_mention_a_runner_do_not_also_invite_improvisation():
    """The rule is: irreversible actions go through a runner. An example that
    says both things teaches nothing."""
    for path in EXAMPLES:
        text = path.read_text(encoding="utf-8").lower()
        if "runner" in text:
            assert "improvise" not in text or "reversible" in text, (
                f"{path.name} mentions a runner and improvising without saying "
                "which side of the line applies"
            )


# --- the memory files the repo tells everyone else to keep -----------------


def test_the_repo_keeps_its_own_decisions():
    """It shipped decisions.template.md for six releases and kept no
    decisions. Same gap as shipping checks.toml.example and never running a
    check on itself."""
    assert (ROOT / "decisions.md").exists()


def test_decision_ids_are_unique_and_sequential():
    ids = re.findall(r"^## (D-\d+)", (ROOT / "decisions.md").read_text(encoding="utf-8"), re.M)
    assert ids, "no decisions recorded"
    assert len(ids) == len(set(ids)), "duplicate decision id"
    numbers = [int(i.split("-")[1]) for i in ids]
    assert numbers == sorted(numbers), "decision ids are out of order - append, do not insert"


def test_every_decision_is_dated():
    body = (ROOT / "decisions.md").read_text(encoding="utf-8")
    entries = re.split(r"^## D-\d+", body, flags=re.M)[1:]
    undated = [i for i, e in enumerate(entries, 1) if not re.search(r"\d{4}-\d{2}-\d{2}", e)]
    assert not undated, f"undated decisions at position {undated}"


def test_there_is_something_to_read_when_the_pin_refuses():
    """`harness version` tells you to read CHANGELOG.md. Sending someone to a
    file that does not exist is worse than saying nothing."""
    from harness.version import status

    reason = status("0.1.0", "9.9.9")["reason"]
    named = re.findall(r"\b([A-Z]+\.md)\b", reason)
    assert named, "the refusal names no document"
    for doc in named:
        assert (ROOT / doc).exists(), f"the refusal points at {doc}, which does not exist"


def test_the_changelog_covers_the_current_release():
    """Derived from the module, so the changelog cannot silently fall behind
    a release."""
    from harness.version import __version__

    assert f"## {__version__}" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), (
        f"CHANGELOG.md has no entry for {__version__}"
    )


def test_the_changelog_says_which_releases_change_the_gate():
    """The only line that matters when deciding whether to bump a pin: did
    what 'green' means change?"""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Gate conditions" in text
