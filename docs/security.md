# Trace and guard

Why the evidence cannot be forged or self-graded.

[README](../README.md) · [Concepts](concepts.md) · [Requirements](requirements.md) · [Runners](runners.md) · [How checks fail](failures.md) · [Retrofitting](retrofit.md) · [Standardizing](standardizing.md) · [Trace and guard](security.md)

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

`protected` means: if anything listed changed since `HEAD`, the gate refuses
— including **new untracked files**, so an agent cannot drop in
`test_easy.py` and call it a win.

The default is not just `tests/`. A test runner reads configuration from
outside its test directory, and that configuration can make every test
disappear while still exiting 0 — a root `conftest.py` that skips everything
was demonstrated doing exactly that, with the guard reporting no change. So
the default also covers `conftest.py` (at any depth), `pytest.ini`,
`tox.ini`, `.rspec` and the common JS runner configs.

**Not** covered by default: `pyproject.toml` and `setup.cfg`. They configure
the grader too, but they are also where dependencies live, so protecting
them would fire on ordinary work — and a guard that cries wolf gets switched
off, which catches nothing. If your pytest config lives in `pyproject.toml`,
add it yourself. That is a decision worth making on purpose.

The list cannot be exhaustive. Anything the check command reads can
influence it.

Build artifacts (`__pycache__/`, `*.pyc`, `.pytest_cache/`) are ignored,
because running a check creates them itself. Override with `guard_ignore`.

Outside a git repo the guard **fails closed** — it cannot verify, so it
refuses rather than waving work through. An explicitly empty `protected = []`
is different: that is a stated intention, not a failed verification, and it
protects nothing, which is what it says.

---

## What this cannot stop

An adversarial review of v0.6.1 found five bypasses. Three are fixed and
replayed as tests in `tests/test_attacks.py`. **Two cannot be fixed in
code**, and stating them plainly is worth more than a fix that sounds
reassuring and is not.

### Whoever sets the environment chooses the key

`HARNESS_HOME` is an environment variable. Point it at a directory you
control and the harness creates a fresh key there, then happily verifies a
chain you wrote yourself:

```
$env:HARNESS_HOME = ".\my-own-home"
#   ... write a forged red-then-green chain with the new key ...
harness verify     # PASS - chain intact
harness gate unit  # exit 0
```

That is not a flaw in the chain. The chain is exactly as trustworthy as the
key, and the key is wherever the environment says it is.

### Whoever can run commands can record a ruling

`harness review --record ship` is a command. There is no way for the tool to
tell a person typing it from an agent shelling out. `require_review` records
*that a ruling was made*; it cannot prove *who made it*.

### Both reduce to one rule

> **The gate is not something the agent runs.**

You run `harness red` and `harness gate`. The agent occupies the middle and
nothing else. If the agent runs the gate — in a script, a hook, a CI job it
wrote, or a shell you handed it — it controls the environment of the thing
judging it, and everything above is available to it.

This is a property of the situation, not a bug to be fixed. Any verifier the
graded party invokes can be pointed at a different judge. What the harness
buys you is that **cheating requires deliberately reaching outside the
project directory**, which is a visible, describable act rather than a
silently weakened assertion.

Two habits that keep the guarantee real:

- Run `red` and `gate` yourself, in your own shell.
- Do not put `harness gate` in a script the agent can edit.

---
