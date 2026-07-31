"""Tests for retrofitting a harness onto an existing repository.

The risk with an init command is that it quietly destroys work someone
already did. These tests mostly exist to prove it doesn't.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.check import load_config  # noqa: E402
from harness.init import detect_test_command, init  # noqa: E402
from harness.spec import coverage, parse  # noqa: E402


def test_writes_the_four_starter_files(tmp_path):
    result = init(tmp_path)
    assert set(result["written"]) == {"checks.toml", "spec.md", "decisions.md", "AGENTS.md"}
    for f in ("checks.toml", "spec.md", "decisions.md", "AGENTS.md"):
        assert (tmp_path / f).exists()


def test_never_overwrites_existing_files(tmp_path):
    """The single most important property here."""
    (tmp_path / "spec.md").write_text("# my hard-won spec\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("my rules\n", encoding="utf-8")

    result = init(tmp_path)

    assert (tmp_path / "spec.md").read_text(encoding="utf-8") == "# my hard-won spec\n"
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "my rules\n"
    assert set(result["skipped"]) == {"spec.md", "AGENTS.md"}


def test_running_twice_changes_nothing(tmp_path):
    init(tmp_path)
    before = {f: (tmp_path / f).read_text(encoding="utf-8") for f in
              ("checks.toml", "spec.md", "decisions.md", "AGENTS.md")}

    second = init(tmp_path)

    assert second["written"] == []
    assert len(second["skipped"]) == 4
    for f, text in before.items():
        assert (tmp_path / f).read_text(encoding="utf-8") == text


def test_project_name_defaults_to_the_directory(tmp_path):
    project = tmp_path / "aria"
    project.mkdir()
    init(project)
    assert load_config(project / "checks.toml").project == "aria"


def test_project_name_can_be_given(tmp_path):
    init(tmp_path, project="selah")
    assert load_config(tmp_path / "checks.toml").project == "selah"


def test_generated_config_is_valid(tmp_path):
    init(tmp_path)
    cfg = load_config(tmp_path / "checks.toml")
    assert {"unit", "spec_coverage", "spec_sync"} <= set(cfg.checks)
    assert "tests/" in cfg.protected


def test_generated_spec_parses_and_is_covered(tmp_path):
    """Whatever init writes must satisfy its own checks out of the box."""
    init(tmp_path)
    reqs = parse(tmp_path / "spec.md")
    cfg = load_config(tmp_path / "checks.toml")
    assert coverage(reqs, set(cfg.checks))["ok"] is True


def test_detects_python(tmp_path):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    assert detect_test_command(tmp_path) == "python -m pytest -q"


def test_detects_node(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert detect_test_command(tmp_path) == "npm test"


def test_detects_rust(tmp_path):
    (tmp_path / "Cargo.toml").write_text("", encoding="utf-8")
    assert detect_test_command(tmp_path) == "cargo test"


def test_detects_go(tmp_path):
    (tmp_path / "go.mod").write_text("", encoding="utf-8")
    assert detect_test_command(tmp_path) == "go test ./..."


def test_unknown_project_gets_a_failing_placeholder(tmp_path):
    """A placeholder must fail loudly, never pass silently."""
    cmd = detect_test_command(tmp_path)
    assert "false" in cmd

    init(tmp_path)
    from harness.check import run
    result = run(load_config(tmp_path / "checks.toml").checks["unit"], tmp_path)
    assert result.ok is False
