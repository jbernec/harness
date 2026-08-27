# harness - specification

## Objective

A coding agent's claim that work is done can be checked without believing the
agent, and without the person checking having to remember anything.

One sentence. Everything below serves it. If a requirement doesn't, cut it.

## Requirements

Rules:
  - ids never change and are never reused
  - every requirement ends in `check:` or `gate: human` - no third option
  - retiring one means marking it `[REMOVED]`, not deleting it
  - changing or retiring a settled one needs an `amended:` line saying why

### R-001  A check is a command and an expected exit code
amended: 2026-08-27  restored original wording
Nothing about a check is a matter of opinion. It runs, it exits, and the
exit code is the whole result.

status: implemented
check: unit

### R-002  A check that has never failed proves nothing
The harness refuses to treat a check as passed-after-failed unless it
watched it fail first, for that exact name and command.

status: implemented
check: unit

### R-003  A failure the check did not earn is not a red
A test file that does not exist yet fails with a non-zero exit code exactly
like a test that fails. Exit codes attributable to the check never running
are refused rather than banked as evidence.

status: implemented
check: unit

### R-004  The trace cannot be edited without detection
Rows are HMAC-chained. Editing, reordering or deleting any row breaks every
link after it. An unparseable row counts as a break, not as an absent row.

status: implemented
check: security

### R-005  The key is not reachable by the thing being graded
The key and the trace live outside the project directory. An agent with full
write access to the repository cannot forge a chain.

status: implemented
check: security

### R-006  The graded may not edit the grader
Protected paths that changed since HEAD - including new untracked files -
make the gate refuse. Outside a git repository the guard fails closed,
because it cannot verify.

status: implemented
check: security

### R-007  The gate decides, and states why
Four conditions on the trace, plus the guard. Any failure is a refusal with
a reason naming the missing condition. No partial credit, no override flag.

status: implemented
check: security

### R-008  A requirement that changed since review goes red
Requirement text is fingerprinted. Editing it breaks the link to its check
until a human re-blesses, and re-blessing a changed requirement demands a
reason that is written into the spec.

status: implemented
check: spec_sync

### R-009  Every requirement is settled, or says it is not
A requirement with no check and no `gate: human` fails coverage. Being
human-gated is honest; being unaccounted for is not.

status: implemented
check: spec_coverage

### R-010  Nothing is retired without a reason
A requirement marked superseded or [REMOVED] with no dated `amended:` line
fails. A tombstone with no cause invites someone to re-add the rule.

status: implemented
check: spec_history

### R-011  Green means the same thing in every project using this
A project records the harness release it was gated with, and the harness
refuses to run under a different feature release in either direction.

status: implemented
check: harness_version

### R-012  The harness never produces a review verdict
Assembling the bundle and recording a human's ruling are the harness's job.
Calling a model and believing its answer is not, in any code path.

status: implemented
check: unit

### R-013  Documentation cannot quietly become untrue
Relative links resolve, every docs page is reachable, install commands name
the current version, and counts written in prose match what they describe.

status: implemented
check: docs_are_true

### R-014  The review prompt finds defects that are really there
A fixture with planted defects, one per category, and a recorded run. The
score is judged by a human; what is checked is that the fixture and its
answer key have not drifted apart.

status: implemented
check: docs_are_true

### R-015  Whether any of this is worth doing
Whether the four links are the right four, whether the ceremony costs more
than the errors it prevents, whether a person would rather ship. No command
settles that, and pretending otherwise would be the most expensive lie the
harness could tell.

status: agreed
gate: human

## Notes

R-015 is not a gap. It is the harness being honest about its edge. A green
run says the machinery does what it was told; it says nothing about whether
being told that was a good idea.
