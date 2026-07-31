# harness

A small, reusable way to prove an AI coding agent actually did the work.

Zero dependencies. Python 3.11+. Drop it onto any project.

---

## The problem

You ask an agent to fix something. It says "Done! All tests pass." ✅

You have no idea if that's true. The agent graded its own homework. It may have:

- deleted the failing assertion instead of fixing the bug
- written a test that never could have failed
- simply reported success without running anything

**The rule this repo enforces: the one who does the work does not get to grade the work.**

---

## The four primitives

A harness is not one thing. It is four small things assembled.

| # | Primitive | What it is | Why it exists |
|---|-----------|-----------|---------------|
| 1 | **Check** | A command + the exit code that counts as passing | A fact, not an opinion |
| 2 | **Red first** | Run the check *before* the fix. It must fail | A check never seen failing proves nothing |
| 3 | **Trace** | An append-only, tamper-evident log of every result | Order is the evidence: red *then* green |
| 4 | **Gate** | Reads the trace and decides | Must not be the agent |

The four are the parts. **The harness is the assembly.**

### Why "red first" is the load-bearing one

`assert True` passes. So does a test for a feature you never wrote, if it's
wired up wrong. A green check on its own means nothing.

A check you *watched fail*, then watched pass, after a change you can point
to — that means something. The trace is what preserves the "then".

---

## Install

```bash
git clone <this-repo> && cd harness
pip install -e .
```

## Use

Create `checks.toml` in the project you want to verify:

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
harness list                    # what am I checking?
harness red position_limit      # 1. prove it fails first
#   ... now let the agent work ...
harness run position_limit      # 2. did it turn green?
harness gate position_limit     # 3. is it actually done?
```

`harness gate` exits 0 only when **all four** conditions hold:

```
check              position_limit
  chain intact     yes     <- trace was not tampered with
  saw red          yes     <- we watched it fail
  green after red  yes     <- and it passed afterwards, in that order
  green now        yes     <- and it still passes right now
  tests untouched  yes     <- the agent did not edit its own grader

PASS
```

Any `no` is a refusal. There is no partial credit and no override flag.

---

## Handing work to an agent

Paste this. Do not paste anything softer.

```
`python -m pytest tests/test_limit.py -q` currently fails.
Make it pass.

Do not edit anything under tests/.
Do not change the command.
When you are done, say only which files you changed.
```

Note what is *not* there: no "let me know if it works", no asking the agent
whether it's finished. You run `harness gate`. It answers.

**Anti-pattern:** do not ask the agent to write its own harness. You write
the checks. The agent writes the app. The moment those merge, you are back
to self-reported success.

---

## Trace integrity

The trace is an HMAC-SHA256 hash chain. Each row commits to the one before it,
so a row cannot be edited, reordered, or deleted without breaking every link
after it.

The important part is **where the key lives**:

```
~/.harness/key                      <- 32 random bytes, chmod 600
~/.harness/<project>/trace.jsonl    <- the log
```

Both sit **outside the project directory**. The agent can write to your repo;
it cannot write to these.

This is deliberate. An *unkeyed* SHA-256 chain stored inside the workspace —
the common design — is not tamper-evident at all: anyone who can write the
file can just recompute every hash and produce a perfectly valid chain saying
whatever they like. I verified this attack works against a shipped
implementation before writing this one. With a key the agent has never seen,
the same attack fails at row 0.

Verify at any time:

```bash
harness verify
harness log --json
```

Losing `~/.harness/key` invalidates existing traces. That is the intended
trade-off: evidence is worth exactly as much as the key is protected.

---

## The guard

`protected = ["tests/"]` means: if anything under `tests/` changed since
`HEAD`, the gate refuses — including **new untracked files**, so an agent
cannot drop in `test_easy.py` and call it a win.

Build artifacts (`__pycache__/`, `*.pyc`, `.pytest_cache/`) are ignored,
because running a check creates them itself. Override with `guard_ignore`.

Outside a git repo the guard **fails closed** — it cannot verify, so it
refuses rather than waving work through.

---

## Spec vs harness

They are not the same thing and mixing them is how projects drift.

| | Spec | Harness |
|---|---|---|
| Direction | Looking forward | Looking backward |
| Says | "here is what we intend to build" | "here is proof of what was built" |
| Lives | `docs/`, roadmap, objectives | `checks.toml` + trace |
| Can lie | Easily, and silently | Only if you leak the key |

Write the spec first. Derive checks from it. The harness proves the
machinery works — it cannot tell you the machinery was worth building.
That judgement stays with a human.

---

## What this cannot do

Be honest about the boundary. A check can verify:

- a command exits 0
- output is deterministic across runs
- an invariant holds on given inputs

A check **cannot** verify:

- whether the strategy is *wise*
- whether an interpretation is *sound*
- whether users will *want* it

For those, the gate is a person. Keep the two categories separate in your
`checks.toml` and don't pretend the second is automated.

---

## Layout

```
harness/
  check.py   Check = cmd + expected exit code. Timeout is a failure, never a hang.
  trace.py   HMAC-chained append-only log. Key lives outside the project.
  gate.py    The four-condition decision.
  guard.py   Agent must not edit its own tests. Fails closed.
  cli.py     list | red | run | gate | guard | verify | log
tests/       26 self-tests, including replays of the forgery attacks
examples/    starting checks.toml for real project shapes
```

## Design notes

- **Zero runtime dependencies** — stdlib `tomllib`, so `checks.toml` needs no parser.
- **Check identity is name + cmd.** Weaken the command and old red evidence stops
  applying to it — you cannot inherit a red from a harder version of the check.
- **An unparseable trace row counts as a break**, not as an absent row. Otherwise
  a row could be destroyed without breaking any link.
- **Timeouts are failures** (exit `-1`), enforced in-process. A hung check is a
  failed check.

MIT.
