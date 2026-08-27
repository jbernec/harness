# decisions

Append-only. You may add to the bottom; you may not rewrite an entry.
Superseding D-004 means writing D-011 and marking D-004 superseded - not
editing D-004. The wrong turn is usually the most useful entry in the file,
because it is the reason you do not take it twice.

Trigger: you made a choice you would have to explain in six months.

---

## D-001  The key lives outside the project
2026-07-31

An unkeyed hash chain stored inside the workspace is not tamper-evident at
all: anyone who can write the file recomputes every hash and produces a
perfectly valid chain saying whatever they like. I verified that attack works
against a shipped implementation before writing this one.

HMAC with a key at `~/.harness/key`, and the trace beside it. The agent can
write anywhere in your repo; it cannot write there.

Cost: losing the key invalidates existing traces. Accepted - evidence is
worth exactly what the key is worth.

## D-002  Red first is the load-bearing link, not the gate
2026-07-31

The obvious design is "gate reads the test results". But a green check on its
own means nothing: `assert True` passes, and so does a test for a feature
that was never wired up. What carries the weight is having *watched it fail*,
then watched it pass, in that order.

So the trace stores order, and the gate reads order. The gate is the cheap
part; red-first is the part that makes it mean anything.

## D-003  A check is identified by name AND command
2026-07-31

Otherwise: earn a red on a hard check, weaken the command, and inherit the
red. Changing the command makes it a different check, and old evidence stops
applying.

## D-004  The guard fails closed outside a repository
2026-07-31

It cannot verify, so it refuses. The alternative - waving work through when
verification is unavailable - makes the guard worthless precisely when
someone has arranged for it to be unavailable.

Later qualified by D-010.

## D-005  Every requirement ends in `check:` or `gate: human`
2026-07-31

No third option, and `gate: human` is not an admission of failure. It is the
spec being honest that no command settles this one. What must never exist is
a requirement nobody has decided how to settle, because that is the state
that looks like coverage and is not.

## D-006  Improvise freely where the cost is `git checkout`
2026-08-01

The runner rules could easily become a rule against thinking. They are scoped
by reversibility, not importance: anywhere being wrong costs a `git
checkout`, improvise. Where it costs data or money, runner only.

Promotion rule: first time improvise, second time the same way, write the
runner and delete the prose version.

## D-007  One reviewer, generic, not a library of personas
2026-08-01

Splitting it into a security reviewer, a performance reviewer and a
correctness reviewer sounds thorough and produces three shallow passes plus
three files to keep in sync. Add a second only when you can name a finding
the first demonstrably missed twice.

Evidence since: the single prompt scored 5/5 on planted defects and then
found three real bugs in this repo's own diff.

## D-008  The harness never produces a review verdict
2026-08-27

Considered: `harness review` calls a model, parses SHIP/HOLD, records it.
Rejected. That moves judgement into the machine, and a reviewer the harness
invokes and believes is the agent grading itself with extra steps -
`require_review` would become satisfiable by something that read nothing.

The harness assembles the bundle and records what a human decided. There is a
test asserting `review.py` never reaches for an HTTP client, because a line
that is only written down gets crossed.

## D-009  `require_review` is off by default
2026-08-27

Requiring a human ruling on every check makes the gate something people route
around, and a gate people route around is worse than no gate: it launders the
habit into a green. Opt in per project.

## D-010  An empty `protected` list is a statement, not a failure
2026-08-27

`protected = []` used to protect everything, because `git diff -- ` with an
empty pathspec means every path. Fixed to protect nothing, which is what it
says.

This is not a retreat from D-004. Being outside a repository is a *failed
verification* and still refuses. An empty list is a *stated intention*, and
the default is `["tests/"]`, so you have to mean it.

## D-011  Patch releases are interchangeable, feature releases are not
2026-08-26

Strict equality on the full version would force five repos to move together
for a bug fix, which makes upgrading painful enough that nobody does it.
Ignoring the version entirely means five definitions of done.

Same major.minor, patch free. Refused in *both* directions - a newer harness
may add a gate condition, so evidence gathered under the older one was
gathered under weaker rules.

## D-012  Fingerprints are per requirement, not per check
2026-08-27

Originally one `requirement_hash` per check. Several requirements
legitimately share one check, and each blessing erased the last, so
`spec sync` was permanently red with no way to satisfy it - and a check that
can never go green gets deleted.

Considered forcing one requirement per check. Rejected as too rigid: a suite
honestly settles several requirements at once.

## D-013  The harness is under its own verification
2026-08-27

It shipped a `checks.toml.example` and no `checks.toml` for six releases. A
verification tool that is not itself verified is asking you to take its word
for it, which is the one thing it exists to stop.

Writing its spec exposed D-012 within minutes. That is the argument for
dogfooding in one line.
