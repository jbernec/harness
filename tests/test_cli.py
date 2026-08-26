"""The CLI surface.

Two things here were bugs I shipped into a generated CI workflow before
noticing: `harness list --json` was rejected because the flag belonged to the
parent parser, and CI needed a shell loop with an embedded python one-liner to
run every check. Both are the same failure - the recipe in the docs was never
executed by anything.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.init import init  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def cli(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "HARNESS_HOME": str(cwd / ".hh")}
    return subprocess.run(
        [sys.executable, "-m", "harness.cli", *args],
        cwd=cwd, capture_output=True, text=True, env=env, timeout=180,
    )


def project(tmp_path: Path) -> Path:
    """A project whose checks do not shell out to `harness`.

    The generated checks call the `harness` console script, which is only on
    PATH after an install. Tests must not depend on that.
    """
    init(tmp_path, project="t", ci=False)
    (tmp_path / "checks.toml").write_text(
        'project = "t"\nspec = "spec.md"\nprotected = []\n'
        '[[check]]\nname = "passes"\ncmd = "python -c \\"raise SystemExit(0)\\""\n'
        '[[check]]\nname = "fails"\ncmd = "python -c \\"raise SystemExit(1)\\""\nexpect = 0\n',
        encoding="utf-8",
    )
    return tmp_path


# --- global flags after the subcommand -------------------------------------


def test_json_works_after_the_subcommand(tmp_path):
    """What everybody actually types, and what my own CI recipe typed."""
    result = cli(project(tmp_path), "list", "--json")
    assert result.returncode == 0, result.stderr
    assert [c["name"] for c in json.loads(result.stdout)] == ["passes", "fails"]


def test_json_still_works_before_the_subcommand(tmp_path):
    result = cli(project(tmp_path), "--json", "list")
    assert result.returncode == 0
    assert json.loads(result.stdout)


def test_a_subcommand_flag_does_not_clobber_the_parent(tmp_path):
    """SUPPRESS is the load-bearing part. Without it the subparser's default
    would overwrite a flag the parent already set, silently."""
    result = cli(project(tmp_path), "--json", "run", "passes")
    assert json.loads(result.stdout)["ok"] is True


def test_cwd_works_after_the_subcommand(tmp_path):
    p = project(tmp_path)
    outside = tmp_path.parent
    result = subprocess.run(
        [sys.executable, "-m", "harness.cli", "list", "--cwd", str(p)],
        cwd=outside, capture_output=True, text=True, timeout=180,
        env={**os.environ, "PYTHONPATH": str(ROOT), "HARNESS_HOME": str(p / ".hh")},
    )
    assert result.returncode == 0, result.stderr


# --- run --all --------------------------------------------------------------


def test_run_all_runs_every_check(tmp_path):
    result = cli(project(tmp_path), "run", "--all", "--json")
    assert json.loads(result.stdout)["total"] == 2


def test_run_all_does_not_stop_at_the_first_failure(tmp_path):
    """CI wants the whole picture. Stopping early means fix, push, wait,
    discover the next one."""
    p = project(tmp_path)
    (p / "checks.toml").write_text(
        (p / "checks.toml").read_text(encoding="utf-8").replace(
            'name = "passes"', 'name = "aaa_fails_first"'
        ).replace('raise SystemExit(0)', 'raise SystemExit(1)', 1),
        encoding="utf-8",
    )
    payload = json.loads(cli(p, "run", "--all", "--json").stdout)
    assert len(payload["checks"]) == 2


def test_run_all_exits_nonzero_when_any_check_fails(tmp_path):
    assert cli(project(tmp_path), "run", "--all").returncode == 1


def test_run_all_exits_zero_when_all_pass(tmp_path):
    p = project(tmp_path)
    (p / "checks.toml").write_text(
        'project = "t"\nprotected = []\n'
        '[[check]]\nname = "passes"\ncmd = "python -c \\"raise SystemExit(0)\\""\n',
        encoding="utf-8",
    )
    assert cli(p, "run", "--all").returncode == 0


def test_run_all_names_what_failed(tmp_path):
    result = cli(project(tmp_path), "run", "--all")
    assert "fails" in result.stdout


def test_run_needs_a_name_or_all(tmp_path):
    """An empty `run` must not quietly become `run --all`. One runs a check;
    the other is a full suite."""
    result = cli(project(tmp_path), "run")
    assert result.returncode == 2
    assert "--all" in result.stderr


# --- the generated workflow is executable, not decorative -------------------


def test_the_generated_workflow_only_uses_real_commands(tmp_path):
    """A CI recipe naming a flag the CLI rejects fails on someone else's
    machine, days later. That was this file's reason for existing."""
    import re
    import yaml

    init(tmp_path, project="t")
    doc = yaml.safe_load((tmp_path / ".github/workflows/harness.yml").read_text(encoding="utf-8"))
    runs = "\n".join(s.get("run", "") for s in doc["jobs"]["checks"]["steps"])

    for line in runs.splitlines():
        line = line.strip()
        if not line.startswith("harness "):
            continue
        # Every `harness ...` line must parse. Exit 2 is argparse rejecting
        # it; anything else means the CLI at least understood the request.
        result = cli(tmp_path, *line.split()[1:], "--cwd", str(tmp_path))
        assert result.returncode != 2, f"workflow line is not valid CLI: {line}\n{result.stderr}"

    assert re.search(r"harness run --all", runs), "the workflow must run every check"
