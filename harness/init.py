"""Init: drop a harness into a repository that already exists.

Retrofitting differs from starting clean in one important way: the code
already works, so you cannot observe a red for it. That evidence is gone and
no amount of tooling recovers it. What you get instead is red-first from the
next change onward, which is the part that was going to matter anyway.

So this writes a small, honest starting point rather than a full spec:
nothing is overwritten, requirements start empty, and the first checks are
whatever test command the project already has.
"""

from __future__ import annotations

from pathlib import Path

from .spec import bless, parse as parse_spec
from .version import __version__

CHECKS = '''\
project = "{project}"
spec = "spec.md"

# The harness release this project is gated with. `harness version` refuses
# to run under a different feature release, so "green" cannot quietly come to
# mean something else across your projects. Bumping this is deliberate.
harness_version = "{harness_version}"

# Paths the agent must not touch. If anything here changed since HEAD,
# the gate refuses - new untracked files included.
protected = ["tests/", "spec.md"]


[[check]]
name = "harness_version"
cmd = "harness version"
expect = 0
description = "the installed harness is the one this project was gated with"


[[check]]
name = "unit"
cmd = "{test_cmd}"
expect = 0
description = "the existing test suite passes"


# These two keep spec.md and checks.toml honest with each other.
# Without them, drift is something you have to remember to notice.

[[check]]
name = "spec_coverage"
cmd = "harness spec coverage"
expect = 0
description = "every requirement has a check, or is marked gate: human"

[[check]]
name = "spec_sync"
cmd = "harness spec sync"
expect = 0
description = "no requirement changed without its check being reviewed"

[[check]]
name = "spec_history"
cmd = "harness spec history"
expect = 0
description = "nothing was superseded or removed without saying why"
'''

SPEC = '''\
# {project} - specification

## Objective

<One sentence. Include a number if you can measure it.>

Everything below serves this. If a requirement doesn't, cut it.

## Requirements

Rules:
  - ids never change and are never reused
  - every requirement ends in `check:` or `gate: human` - no third option
  - retiring one means marking it `[REMOVED]`, not deleting it
  - changing or retiring a settled one needs an `amended:` line saying why

Optional per requirement:
  status: draft | agreed | implemented | superseded   (default: agreed)
  amended: 2026-01-31  what changed and why

Retrofitting? Do not sit down and write forty of these. Add a requirement
the next time something breaks, and write its check at the same time. A spec
grown from real failures beats an invented one, and you'll actually finish it.

### R-001  <first requirement>
<What must be true. Be specific enough that a command could settle it.>

check: unit
'''

DECISIONS = '''\
# Decisions

Append only. Never rewrite an entry once it is written.

Add one when you make a choice you would have to explain in six months.
Three lines: date, what you chose, why. Superseding means adding a new entry
and marking the old one, never editing it - the wrong turn is usually the
reason you don't take it twice.

## Active

## Superseded

---

### D-001  <date>  <decision>
<Why. Two lines is plenty.>
'''

AGENTS = '''\
# AGENTS.md

For any coding agent working in this repo.

1. **Do not edit anything under `protected` in `checks.toml`** - usually
   `tests/` and `spec.md`. If you think a test is wrong, say so and stop.

2. **Do not edit `checks.toml`.** Weakening a check is not progress.

3. **Do not write to `~/.harness/`.** That is the trace and the key.

4. **Do not report success.** `harness gate` decides when work is done.
   Report what you changed; stop there.

5. **Never hand-write a sequence that already has a runner.** If a procedure
   exists as a script or make target, invoke it. Do not retype it or write a
   temp script that does the same thing. A dropped step in an ordered
   procedure is not a typo, it is an unrecoverable state.

6. **Irreversible actions are on rails.** Production writes, orders, money,
   deploys, messages to real people: runner only. Improvise freely anywhere
   the cost of being wrong is `git checkout`.

7. **If a check will not pass, say why.** A clear "I could not do this
   because X" is worth more than a green you engineered by gutting the
   assertion.

8. **Do not edit the harness.** Not `harness/`, not `harness_version`.
   Changing the grader makes every green in this project meaningless,
   including the ones you did not touch.

9. **Be brief.** Answer first, then evidence, then stop. No preamble, no
   closing summary. Prefer a list over prose. Report results rather than
   narrating what you are about to do. Long output is not thoroughness.

## Task template

```
`<command>` currently fails.
Make it pass.

Do not edit anything under tests/.
Do not change the command.
When you are done, list only the files you changed.
```
'''

# A gate that only ever runs on one laptop is a gate one person can skip.
# This runs the same checks on every push, from a clean checkout.
#
# The trace and key live outside the repo, so CI starts with no history and
# therefore no red to point at. That is honest, not a gap: CI proves the
# checks pass, and the red-then-green ordering is proved locally where the
# work happened. Do not try to fake a red in CI to make the gate open.
WORKFLOW = '''\
name: harness

on:
  push:
  pull_request:

jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # the guard compares against HEAD

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install the pinned harness
        run: pip install "harness @ git+https://github.com/jbernec/harness@v{harness_version}"

      - name: Version pin
        run: harness version

      - name: Spec is honest
        run: |
          harness spec coverage
          harness spec sync
          harness spec history

      - name: Protected paths untouched
        run: harness guard

      - name: Every check
        run: harness run --all
'''

# Ordered: the first match wins, so put the more specific markers first.
TEST_COMMANDS = [
    ("pytest.ini", "python -m pytest -q"),
    ("tox.ini", "python -m pytest -q"),
    ("pyproject.toml", "python -m pytest -q"),
    ("setup.py", "python -m pytest -q"),
    ("Cargo.toml", "cargo test"),
    ("go.mod", "go test ./..."),
    ("package.json", "npm test"),
    ("Gemfile", "bundle exec rspec"),
    ("pom.xml", "mvn -q test"),
    ("build.gradle", "./gradlew test"),
]


def detect_test_command(cwd: Path) -> str:
    for marker, cmd in TEST_COMMANDS:
        if (cwd / marker).exists():
            return cmd
    return "echo 'set a real test command' && false"


def init(cwd: Path, project: str | None = None, ci: bool = True) -> dict:
    """Write starter files. Never overwrites - existing work is yours."""
    name = project or cwd.resolve().name
    test_cmd = detect_test_command(cwd)

    files = {
        "checks.toml": CHECKS.format(
            project=name, test_cmd=test_cmd, harness_version=__version__
        ),
        "spec.md": SPEC.format(project=name),
        "decisions.md": DECISIONS,
        "AGENTS.md": AGENTS,
    }
    if ci:
        files[".github/workflows/harness.yml"] = WORKFLOW.format(
            harness_version=__version__
        )

    written, skipped = [], []
    for filename, content in files.items():
        path = cwd / filename
        if path.exists():
            skipped.append(filename)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(filename)

    # Bless the placeholder requirement we just wrote. Both sides came from
    # here, so they match by construction and saying otherwise is noise - and
    # a scaffold that is red on day one for a reason nobody caused is how a
    # check earns a reputation for crying wolf. The first real edit to
    # spec.md then goes red correctly, which is the point.
    if {"checks.toml", "spec.md"} <= set(written):
        for req in parse_spec(cwd / "spec.md"):
            if req.check:
                bless(cwd / "checks.toml", req.check, req.fingerprint, req.id)

    return {
        "ok": True,
        "project": name,
        "test_cmd": test_cmd,
        "harness_version": __version__,
        "written": written,
        "skipped": skipped,
    }
