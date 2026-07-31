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

## Spec drift

A spec says what you intend. A check proves what you built. They come apart
quietly unless something forces them together.

Number every requirement in `spec.md`:

```markdown
### R-002  Position limit
No single position may exceed 20% of book value.

check: position_limit

### R-007  The strategy is sound
No command settles this.

gate: human
```

Point the check back at it:

```toml
[[check]]
name = "position_limit"
requirement = "R-002"
cmd = "python -m pytest tests/test_risk.py -q"
```

Then:

```bash
harness spec list        # what have I got, and how is each one settled?
harness spec coverage    # is anything unaccounted for?
harness spec bless       # I have read these; record their fingerprints
harness spec sync        # has anything changed since I read it?
```

`bless` writes a fingerprint of each requirement's text into `checks.toml`.
You never type it. Now change 20% to 25% in the spec:

```
FAIL  changed since last reviewed -> R-002: spec is a0c325, check recorded 7fe6cd
```

The gate will not open until you look at the check and either update it or
re-bless it. **Drift stops being something you have to notice and becomes
something that goes red.**

Add these two to `checks.toml` and they run like any other check:

```toml
[[check]]
name = "spec_coverage"
cmd = "harness spec coverage"
description = "every requirement has a check, or is marked gate: human"

[[check]]
name = "spec_sync"
cmd = "harness spec sync"
description = "no requirement changed without its check being reviewed"
```

### Three rules for IDs

1. **Never change an ID.** Traces point at them.
2. **Never reuse one.** `harness spec list` rejects duplicates.
3. **Retire, don't delete** — mark `[REMOVED]` and leave it in place, so old
   evidence still resolves.

### Every requirement ends one of two ways

`check:` or `gate: human`. There is no third option, and that's the point.
Marking something human-gated isn't an admission of failure — it's the spec
being honest that no command can settle it. What must never happen is a
requirement nobody has decided how to settle. That's what `spec coverage`
catches.

---

## Memory

Agents forget. Sessions end. Models get swapped. Put durable memory in files,
not in a model:

```
spec.md          what we're building, R-xxx numbered
checks.toml      how we prove it
decisions.md     why we chose X over Y, dated
AGENTS.md        rules for agents
~/.harness/      the trace: what actually happened
```

The three that hold history have **opposite rules**, and mixing them up is
the common mistake:

| File | You may | You may never |
|---|---|---|
| `spec.md` | edit it — it's the present | — |
| `decisions.md` | append to the bottom | rewrite an old entry |
| trace | nothing; the tool writes it | touch it |

You can change the present. You cannot change the past. Superseding a
decision means adding `D-021` and marking `D-008` as superseded — not
editing D-008. The wrong turn is usually the most useful entry in the file;
it's the reason you don't take it twice.

**The test for whether your memory is in the right place:** a fresh session
with zero context should be able to pick up the work by reading the repo. If
it can't, the memory is in a chat log and it's already gone.

`decisions.md` is the one people skip. Its trigger is human and it's one
line: *you made a choice you'd have to explain in six months.* Three lines,
then move on.

Templates: [`spec.template.md`](spec.template.md),
[`decisions.template.md`](decisions.template.md).

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
  spec.py    Numbered requirements, coverage, and drift fingerprints.
  cli.py     list | red | run | gate | guard | verify | log | spec
tests/       48 self-tests, including replays of the forgery attacks
examples/    starting checks.toml for real project shapes
spec.template.md, decisions.template.md
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
