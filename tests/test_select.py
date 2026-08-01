"""Pattern-scoped check selection.

Running everything on every keystroke is slow enough that people stop running
anything. Running a subset is only safe if getting the subset wrong makes it
bigger, never smaller - a skipped check looks identical to a passing one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.check import Check, changed_files, load_config, select  # noqa: E402


def make(name: str, files: tuple[str, ...] = ()) -> Check:
    return Check(name=name, cmd="true", files=files)


# --- matching --------------------------------------------------------------


def test_a_check_with_no_paths_always_runs():
    """Forgetting to scope must widen the net, never narrow it."""
    assert make("unit").concerns(["anything/at/all.py"])
    assert make("unit").concerns([])


def test_a_directory_prefix_matches_everything_beneath_it():
    c = make("api", ("src/api/",))
    assert c.concerns(["src/api/routes.py"])
    assert not c.concerns(["src/web/routes.py"])


def test_a_star_spans_directories():
    c = make("py", ("src/*",))
    assert c.concerns(["src/deep/nested/file.py"])


def test_an_extension_pattern_matches_at_any_depth():
    c = make("sql", ("*.sql",))
    assert c.concerns(["db/migrations/001_init.sql"])
    assert not c.concerns(["db/migrations/001_init.py"])


def test_windows_separators_match_posix_patterns():
    assert make("api", ("src/api/",)).concerns(["src\\api\\routes.py"])


def test_a_leading_dot_slash_is_ignored():
    assert make("api", ("./src/api/",)).concerns(["./src/api/routes.py"])


def test_it_matches_if_any_one_pattern_matches():
    c = make("data", ("db/", "*.sql"))
    assert c.concerns(["schema.sql"])
    assert c.concerns(["db/seed.py"])


def test_it_matches_if_any_one_changed_file_matches():
    c = make("api", ("src/api/",))
    assert c.concerns(["README.md", "src/api/routes.py"])


# --- selection -------------------------------------------------------------


def test_select_returns_only_concerned_checks_in_config_order():
    checks = {
        "unit": make("unit"),
        "api": make("api", ("src/api/",)),
        "web": make("web", ("src/web/",)),
    }
    assert [c.name for c in select(checks, ["src/api/routes.py"])] == ["unit", "api"]


def test_select_returns_nothing_when_no_scoped_check_matches():
    checks = {"api": make("api", ("src/api/",))}
    assert select(checks, ["README.md"]) == []


# --- reading git -----------------------------------------------------------


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "seed.txt").write_text("seed", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "seed")
    return tmp_path


def test_changed_files_sees_an_untracked_file(tmp_path):
    r = repo(tmp_path)
    (r / "new.py").write_text("x", encoding="utf-8")
    assert "new.py" in changed_files(r)


def test_changed_files_sees_an_uncommitted_edit(tmp_path):
    r = repo(tmp_path)
    (r / "seed.txt").write_text("changed", encoding="utf-8")
    assert "seed.txt" in changed_files(r)


def test_changed_files_is_empty_in_a_clean_tree(tmp_path):
    assert changed_files(repo(tmp_path)) == []


def test_changed_files_returns_none_outside_a_repo(tmp_path):
    """None means 'git could not answer', which the caller turns into
    'run everything'. Failing open here is a nuisance; failing closed is a
    hole."""
    assert changed_files(tmp_path) is None


def test_changed_files_returns_none_for_an_unknown_base(tmp_path):
    assert changed_files(repo(tmp_path), base="no-such-branch") is None


# --- config ----------------------------------------------------------------


def test_files_are_read_from_the_config(tmp_path):
    cfg_path = tmp_path / "checks.toml"
    cfg_path.write_text(
        'project = "p"\n'
        "[[check]]\n"
        'name = "api"\n'
        'cmd = "true"\n'
        'files = ["src/api/", "*.sql"]\n',
        encoding="utf-8",
    )
    assert load_config(cfg_path).checks["api"].files == ("src/api/", "*.sql")


def test_files_default_to_empty_meaning_always_run(tmp_path):
    cfg_path = tmp_path / "checks.toml"
    cfg_path.write_text('project = "p"\n[[check]]\nname = "u"\ncmd = "true"\n', encoding="utf-8")
    check = load_config(cfg_path).checks["u"]
    assert check.files == ()
    assert check.concerns(["whatever.py"])
