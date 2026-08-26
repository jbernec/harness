# Runners

When to improvise, and when the steps must live in a file.

[README](../README.md) · [Concepts](concepts.md) · [Requirements](requirements.md) · [Runners](runners.md) · [How checks fail](failures.md) · [Retrofitting](retrofit.md) · [Standardizing](standardizing.md) · [Trace and guard](security.md)

---

## The fix, first

If a procedure has steps that must run in order, put them in a file:

```bash
# pipeline/run.sh
set -euo pipefail
python -m app.migrate
python -m app.load
python -m app.reconcile
```

Then delete the steps from your spec and write one line:

> Run `pipeline/run.sh`.

Done. Nothing is retyped, so nothing can be dropped. `set -e` means a failed
step stops the chain instead of continuing into a corrupted state.

**Leaving the written-out steps in the spec defeats it** — someone will
follow them by hand. Delete them.

## Why this comes up

The pattern is always the same. An agent is told to follow an ordered
procedure that is documented correctly. It reconstructs the sequence from
memory instead of executing it, drops a step, and the step it drops is the
one that was protecting something.

The tell is when the postmortem says *"I improvised the sequence rather than
executing the spec."* That sounds like a discipline problem. It's a design
problem:

> **A sequence that must be followed exactly should not exist as prose.**

If the only thing between you and an unrecoverable state is someone retyping
several steps in the right order, that fails eventually.

## But doesn't this stifle ideation?

No, because these operate on different questions:

- **Ideation** — *what should we do?* → keep free
- **Improvisation** — *how do I execute something already known?* → remove

You only remove the second, and only where a correct sequence already
exists. Nobody has a creative breakthrough retyping a migration sequence.

## The line: is the action reversible?

| | Reversible | Irreversible |
|---|---|---|
| **Examples** | edit a file, run tests, prototype, draft a query | write to prod, submit an order, send money, deploy, email users |
| **How** | improvise freely | runner only |
| **Why** | mistake costs `git checkout` | mistake is permanent |

An agent that can't experiment is useless. An agent that can improvise a
payout script is dangerous. Same agent, different blast radius.

## When to write one

Don't design runners up front — you'd be guessing. Promote them:

```
1st time doing it   improvise, it's exploration
2nd time, same way  it's a procedure now -> write the runner
                    delete the prose version
```

Corollary, and the one that matters: **the same failure twice means a check
is missing.** "Be more careful" is not a mechanism. First occurrence, fix
and log it. Second occurrence, stop and write the check.

## Per project

| Project | Improvise | Runner only |
|---|---|---|
| ETL | query shapes, schema design, transformation logic | migrations, load sequence, backfills |
| Trading | strategy ideas, indicators, backtests | order submission, position sizing, live release |
| Content/AI | ranking heuristics, prompts, UI | index rebuilds, publishing |
| Marketplace | matching logic, pricing models | payouts, refunds, SMS sends |

Same shape: **thinking is free, side effects are on rails.**

## Cheap preflight beats expensive rollback

A precondition check that fails in two seconds is worth more than a
transaction that rolls back after forty minutes. Both save your data; only
one saves your afternoon.

```toml
[[check]]
name = "preconditions"
cmd = "python -m etl.preflight"
description = "assert the world is as expected before doing anything expensive"
```

Keep the transaction too. It's the last line, not the first.

See [`examples/pipeline.toml`](../examples/pipeline.toml).

---
