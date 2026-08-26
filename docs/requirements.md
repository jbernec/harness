# Requirements

Numbered requirements, drift fingerprints, and amendments.

This is documentation *about* the spec layer. Your project's own spec lives
at `spec.md` in its root.

[README](../README.md) · [Concepts](concepts.md) · [Requirements](requirements.md) · [Runners](runners.md) · [How checks fail](failures.md) · [Retrofitting](retrofit.md) · [Standardizing](standardizing.md) · [Trace and guard](security.md)

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
harness spec history     # did anything change without saying why?
```

`bless` writes a fingerprint of each requirement's text into `checks.toml`.
You never type it. Now change 20% to 25% in the spec:

```
FAIL  changed since last reviewed -> R-002: spec is a0c325, check recorded 7fe6cd
```

The gate will not open until you look at the check and either update it or
re-bless it. **Drift stops being something you have to notice and becomes
something that goes red.**

### Re-blessing costs you a sentence

Accepting a change requires a reason:

```
$ harness spec bless R-002
FAIL  R-002 changed since it was last blessed (7fe6cd -> a0c325).
      Re-blessing needs a reason: harness spec bless R-002 --reason "..."

$ harness spec bless R-002 --reason "raised to 25% after the March review"
blessed  R-002  a0c325  -> check position_limit  (amendment recorded)
```

Which writes into `spec.md`:

```markdown
### R-002  Position limit
amended: 2026-08-01  raised to 25% after the March review
No single position may exceed 25% of book value.

status: implemented
check: position_limit
```

The old wording is already in git. What git cannot tell you is **why**, and
the moment you re-bless is the only moment you still remember. A month later
the question is never "what did this used to say" — it's "who decided this
and what did they know."

`status:` is one of `draft`, `agreed`, `implemented`, `superseded`. Neither
`status:` nor `amended:` is part of the fingerprint: recording that something
changed must not itself count as a change, or blessing would re-drift what it
just blessed.

`harness spec history` fails when a requirement is marked `superseded` or
`[REMOVED]` with no `amended:` line. A tombstone with no cause reads as an
oversight, and someone eventually re-adds the rule you deliberately dropped.

Add these to `checks.toml` and they run like any other check:

```toml
[[check]]
name = "spec_coverage"
cmd = "harness spec coverage"
description = "every requirement has a check, or is marked gate: human"

[[check]]
name = "spec_sync"
cmd = "harness spec sync"
description = "no requirement changed without its check being reviewed"

[[check]]
name = "spec_history"
cmd = "harness spec history"
description = "nothing was superseded or removed without saying why"
```

### Three rules for IDs

1. **Never change an ID.** Traces point at them.
2. **Never reuse one.** `harness spec list` rejects duplicates.
3. **Retire, don't delete** — mark `[REMOVED]`, leave it in place, and add an
   `amended:` line saying what replaced it.

### Every requirement ends one of two ways

`check:` or `gate: human`. There is no third option, and that's the point.
Marking something human-gated isn't an admission of failure — it's the spec
being honest that no command can settle it. What must never happen is a
requirement nobody has decided how to settle. That's what `spec coverage`
catches.

---
