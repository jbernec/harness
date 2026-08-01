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

CHECKS = '''\
project = "{project}"
spec = "spec.md"

# Paths the agent must not touch. If anything here changed since HEAD,
# the gate refuses - new untracked files included.
protected = ["tests/", "spec.md"]


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
   temp script that does the same thing. A dropped step in a database
   procedure is not a typo, it is a corrupted table.

6. **Irreversible actions are on rails.** Production writes, orders, money,
   deploys, messages to real people: runner only. Improvise freely anywhere
   the cost of being wrong is `git checkout`.

7. **If a check will not pass, say why.** A clear "I could not do this
   because X" is worth more than a green you engineered by gutting the
   assertion.

## Task template

```
`<command>` currently fails.
Make it pass.

Do not edit anything under tests/.
Do not change the command.
When you are done, list only the files you changed.
```
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


def init(cwd: Path, project: str | None = None) -> dict:
    """Write starter files. Never overwrites - existing work is yours."""
    name = project or cwd.resolve().name
    test_cmd = detect_test_command(cwd)

    files = {
        "checks.toml": CHECKS.format(project=name, test_cmd=test_cmd),
        "spec.md": SPEC.format(project=name),
        "decisions.md": DECISIONS,
        "AGENTS.md": AGENTS,
    }

    written, skipped = [], []
    for filename, content in files.items():
        path = cwd / filename
        if path.exists():
            skipped.append(filename)
            continue
        path.write_text(content, encoding="utf-8")
        written.append(filename)

    return {
        "ok": True,
        "project": name,
        "test_cmd": test_cmd,
        "written": written,
        "skipped": skipped,
    }
