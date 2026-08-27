# harness

**Prove work was done, instead of believing someone who says it was.**

Zero dependencies. Python 3.11+. Drop it onto any project.

```bash
harness red mycheck     # 1. it must FAIL before the work starts
#   ... agent works ...
harness gate mycheck    # 2. the harness decides. not the agent.
```

The rule underneath all of it: **whoever does the work does not grade the
work.** The cheapest way to satisfy a grader you control is to lower it.

### In four words

| Component | Plainly |
|---|---|
| **Check** | the measurement |
| **Red first** | proof the measurement works |
| **Trace** | evidence, sealed |
| **Gate** | go / no-go |

> Measure it, prove the measurement works, seal the result, then let
> something else say go or no-go.

**None of these is a test** — a test is one *kind* of check. Any three of
them is a habit; all four is a harness. → [Concepts](docs/concepts.md)

---

## Which problem do you have?

| Symptom | Fix | Read |
|---|---|---|
| Agent says "done" and it isn't | red first + gate | below |
| Agent dropped a step in a procedure | a runner | [runners](docs/runners.md) |
| Spec says one thing, code does another | numbered requirements | [requirements](docs/requirements.md) |
| Change passes, but nobody read it | `harness review` | [reviewer/](reviewer/) |

These are independent. **Take only what your problem needs.** Adopting all of
them at once is how this ends up unused.

---

## Install

```bash
pip install "harness @ git+https://github.com/jbernec/harness@v0.7.0"
```

Pin the tag, not `main`. `main` moves; a tag is a decision.

Then in the project you want to verify:

```bash
cd your-project
harness init          # checks.toml, spec.md, decisions.md, AGENTS.md,
                      # and a CI workflow. Never overwrites anything.
```

Using it across several projects? → [Standardizing](docs/standardizing.md)

---

## Use

`checks.toml` — a check is a command plus the exit code that counts as passing:

```toml
project = "aria"
protected = ["tests/"]

[[check]]
name = "position_limit"
cmd = "python -m pytest tests/test_limit.py -q"
expect = 0
description = "no single position may exceed 20% of the book"
```

Then:

```bash
harness list                  # what am I checking?
harness red position_limit    # 1. prove it fails first
#   ... agent works ...
harness run position_limit    # 2. did it turn green?
harness gate position_limit   # 3. is it actually done?
```

`harness gate` exits 0 only when **all five** conditions hold:

```
check              position_limit
  chain intact     yes     <- trace was not tampered with
  saw red          yes     <- we watched it fail
  green after red  yes     <- and it passed afterwards, in that order
  green now        yes     <- and it still passes right now
  tests untouched  yes     <- the agent did not edit its own grader
  reviewed         yes     <- only with require_review = true

PASS
```

Any `no` is a refusal. No partial credit, no override flag.

### Iterating on a big suite

Scope a check to the paths it is about, then shortlist with `harness select`:

```toml
files = ["src/api/", "schema/*.json"]
```

A check with no `files` always runs, and **the gate never selects** —
otherwise the easy way to pass is to touch nothing the suite watches.

### In CI

`harness init` writes a workflow that installs the pinned harness, then runs
`harness version`, `harness guard` and `harness run --all`. CI proves the
checks pass from a clean checkout; it does **not** gate, because a fresh
runner has no trace and so no red to point at.
→ [Standardizing](docs/standardizing.md)

---

## Handing work to an agent

Copy [`AGENTS.md`](AGENTS.md) into your project. Point `CLAUDE.md` and
`.github/copilot-instructions.md` at it with one line each — never duplicate
the rules, or they drift. Then the task itself:

```
`<command>` currently fails.
Make it pass.

Do not edit anything under tests/.
Do not change the command.
When you are done, list only the files you changed.
```

You run `red` and `gate`. The agent only occupies the middle.

---

## What this cannot do

A check verifies that a command exits 0, that output is deterministic, that
an invariant holds. It **cannot** tell you whether the idea is any good.

For that, mark the requirement `gate: human` and judge it yourself:

```bash
harness review                              # bundles prompt + spec + diff
harness review --record ship --note "..."   # your ruling, traced
```

Paste the bundle into a session with no history of the work. The harness
assembles and records; **it does not review** — a reviewer it invokes and
believes is the agent grading itself with extra steps. Set
`require_review = true` for a sixth gate condition. Scored 5/5 on a planted
fixture → [`reviewer/`](reviewer/)

---

## Docs

| | |
|---|---|
| [Concepts](docs/concepts.md) | the four primitives, and why red-first is load-bearing |
| [Requirements](docs/requirements.md) | numbered requirements, drift fingerprints, amendments |
| [Runners](docs/runners.md) | when to improvise, when the steps must live in a file |
| [How checks fail](docs/failures.md) | four ways a check quietly stops working |
| [Retrofitting](docs/retrofit.md) | putting this on a project that already exists |
| [Standardizing](docs/standardizing.md) | one harness across many projects: pinning, CI, rollout |
| [Trace and guard](docs/security.md) | why the evidence cannot be forged |

---

## Layout

```
harness/
  check.py   Check = cmd + expected exit code. Timeout is a failure, never a hang.
  trace.py   HMAC-chained append-only log. Key lives outside the project.
  gate.py    Four conditions on the trace. The guard adds the fifth.
  guard.py   Agent must not edit its own tests. Fails closed.
  spec.py    Numbered requirements, coverage, drift fingerprints, amendments.
  init.py    Retrofit starter files onto an existing repo. Never overwrites.
  version.py The pin. Same feature release, or refuse.
  review.py  Assemble the bundle, record the ruling. Judges nothing.
  cli.py     init list select red run gate guard verify version review log spec
tests/       self-tests, including replays of the forgery attacks
checks.toml  + spec.md: the harness under its own verification
examples/    starting checks.toml for aria, selah, ifetch, and pipelines
reviewer/    the prompt, plus a fixture proving it finds planted defects
```
Design notes: [concepts](docs/concepts.md#design-notes). MIT.
