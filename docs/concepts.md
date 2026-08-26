# Concepts

Why the harness is shaped the way it is. Read once.

[README](../README.md) · [Concepts](concepts.md) · [Requirements](requirements.md) · [Runners](runners.md) · [How checks fail](failures.md) · [Retrofitting](retrofit.md) · [Standardizing](standardizing.md) · [Trace and guard](security.md)

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

But only if the check actually ran. A test file that does not exist yet fails
with a non-zero exit code, exactly like a test that fails. Bank that as your
red and you have evidence about nothing: write anything at all afterwards and
the gate accepts it.

So `red` refuses a failure it cannot attribute to the code:

```
FAIL  'parser' failed (exit 4), but it never ran: usage error - the test
      path probably does not exist.
```

For pytest, only exit 1 is a real red — 2 is an ImportError while collecting,
4 is a missing path, 5 is nothing collected. Exit 126 and 127 are refused for
every runner: the shell could not start the command. Other runners' codes are
not guessed; declare them per check with `inconclusive = [...]` if you need
them, or `inconclusive = []` to opt out.

The refused attempt is still written to the trace, under a phase the gate
ignores. Evidence of what happened, without counting as proof.

One hole this does not close: a runner that is missing entirely often exits 1.
`python -m pytest` with pytest uninstalled prints "No module named pytest" and
exits 1, which is indistinguishable from a genuine failure by exit code alone.
Run your suite once before trusting the first red.

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

Templates: [`spec.template.md`](../spec.template.md),
[`decisions.template.md`](../decisions.template.md).

---

---

## Design notes

- **Zero runtime dependencies** — stdlib `tomllib`, so `checks.toml` needs no parser.
- **A red must be earned.** A test file that does not exist yet fails exactly
  like a test that fails, so `red` refuses exit codes it can attribute to the
  check never running — 2/3/4/5 for pytest, 126/127 for any runner. Set
  `inconclusive = [...]` on a check for other runners, or `[]` to opt out.
  The refused attempt is still traced, under a phase the gate ignores.
- **Check identity is name + cmd.** Weaken the command and old red evidence stops
  applying — you cannot inherit a red from a harder version of the check.
- **An unparseable trace row counts as a break**, not an absent row. Otherwise a
  row could be destroyed without breaking any link.
- **Timeouts are failures** (exit `-1`). A hung check is a failed check.
- **Selection can only widen.** Unscoped checks always run; the gate ignores
  selection. A skipped check and a passing check leave the same trace.
