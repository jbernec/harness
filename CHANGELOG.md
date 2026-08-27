# Changelog

When `harness version` refuses, it tells you to read what changed before
bumping the pin. This is that. Nothing else in the repo is allowed to send
you somewhere that does not exist.

Feature releases (0.5 -> 0.6) are **not** interchangeable in either
direction: a newer harness may add a gate condition, in which case older
evidence was gathered under weaker rules. Patch releases are fixes and are
interchangeable.

Read the **Breaking** and **Gate conditions** lines. Those are the ones that
change what a green result means.

---

## 0.8.1 - 2026-08-27

**Added**

- **`supersedes: D-nnn <reason>`** in `decisions.md`. `spec.md` could retire
  a requirement; decisions had no equivalent, so the only ways to retire one
  were to delete it or rewrite it - both of which lose the thing worth
  keeping. Checked: the target must exist, be older, not be itself, and
  carry a reason. `harness memory` reports how many are superseded and how
  many are live.
- **Duplicate requirements are reported** - identical fingerprints only.
  Judging whether two differently-worded requirements *mean* the same thing
  is a judgement, and a guard that guesses produces false positives until
  someone switches it off. What this catches is the real mechanism: copy a
  requirement to amend it, forget to delete the original, and whichever one
  you later edit, the other silently disagrees.

**Fixed**

- The `supersedes:` pattern used `\s*`, which matches newlines, so the
  reason group ran on and picked up the following paragraph. A supersession
  with no reason silently borrowed one and recorded the wrong text as its
  justification. Found by writing the test that was supposed to prove it
  failed.

No gate conditions changed.

## 0.8.0 - 2026-08-27

**Added**

- **`harness memory`** - the one question that decides whether your memory is
  in the right place: could a fresh session with zero context pick up the
  work by reading the repository? It checks that `spec.md`, `decisions.md`
  and `AGENTS.md` are present, that decision ids are unique, dated and in
  order, that `decisions.md` has only gained lines since HEAD, and that
  `CLAUDE.md` / `copilot-instructions.md` point at `AGENTS.md` rather than
  repeating it.

  The append-only line is the one that earns its keep. Editing an old
  decision is not a correction - it deletes the reason you did not take that
  turn twice, so you take it twice.

- `harness init` now writes a real dated first decision rather than a
  placeholder, so a fresh scaffold passes `harness memory` immediately. A
  scaffold that is red on day one for a reason nobody caused is how a check
  earns a reputation for crying wolf.

- `harness init` adds a `memory` check to new projects.

No gate conditions changed.

## 0.7.0 - 2026-08-27

**Gate conditions** — evidence recorded before this release is refused for
checks whose `expect` is anything other than the default, because those rows
do not record what "passing" meant. Re-run `harness red`.

**Security.** An adversarial review found five bypasses against 0.6.1. Three
are fixed and replayed as tests; two cannot be fixed in code and are now
documented as limits.

**Fixed**

- **`expect` was not part of a check's identity.** Earn a red with
  `expect = 0`, then set `expect = 1`, and a still-failing test counted as
  green while inheriting the old red - the command never changed, so the
  gate matched it. Observed exiting 0 on a failing test. `expect` is now in
  the gate's matching predicate and inside the HMAC, so it cannot be edited
  after the fact either.
- **A root `conftest.py` could skip every test.** Pytest exits 0 for skipped
  tests, and the guard said nothing because `conftest.py` sat outside
  `tests/`. The default `protected` list now covers `conftest.py` at any
  depth, `pytest.ini`, `tox.ini`, `.rspec` and the common JS runner configs.
  Deliberately not `pyproject.toml` or `setup.cfg`: they hold dependencies
  too, so protecting them by default would fire on ordinary work, and a
  guard that cries wolf gets switched off.
- **The project name could escape `HARNESS_HOME`.** `project = "../../x"` in
  checks.toml wrote the trace outside the home directory. The name comes
  from a file the agent can write, so it no longer gets to be a path.

**Documented, because they cannot be fixed**

- `HARNESS_HOME` is an environment variable: whoever sets the environment
  chooses which key is used, and can therefore verify a chain they wrote.
- `harness review --record ship` is a command: the tool cannot tell a person
  typing it from an agent shelling out.

Both reduce to one rule, now stated as a limit rather than a habit: **the
gate is not something the agent runs.** See `docs/security.md`.

**Added**

- `tests/test_attacks.py` - every bypass that worked once, replayed.
- `CHANGELOG.md` and `decisions.md`. The pin's refusal told you to read what
  changed, and there was nothing to read.
- `tests/test_examples.py` - the example configs are the first thing anyone
  copies and nothing checked them.

## 0.6.1 - 2026-08-27

**Fixed**

- **`spec sync` was unsatisfiable for any check settling more than one
  requirement.** `bless` recorded one fingerprint per check, so blessing
  R-002 erased what was recorded for R-001 on the same check. The check went
  permanently red with no way to make it green, and a check that can never
  pass gets deleted. `requirement_hash` now holds one fingerprint per
  requirement (`R-001:abc123,R-002:def456`), and `sync` names exactly which
  requirement moved. The old single-value form still works for checks that
  settle one requirement, so nothing already blessed goes red.
- **The gate recorded a different reason than it printed.** The trace row was
  built before the review status was known, so the evidence never mentioned
  review and disagreed with what you were told. The trace outlives the
  terminal; if they disagree, the trace is what is wrong.
- **`require_review` outside a git repository** reported "reviewed and held:"
  with an empty note. Now fails closed with the real reason: no revision
  means nothing to have ruled on.
- **`extract_prompt` fell back to the whole file** when it found no fenced
  block, so a review bundle could carry the prose *about* reviewing instead
  of the instructions - looking fine and reviewing worse. Now refuses.
- **`protected = []` protected everything.** `git diff -- ` with an empty
  pathspec means every path, so the natural way to write "protect nothing"
  inverted into the strictest possible guard.

**Added**

- The harness is now under its own verification: `checks.toml` and `spec.md`
  with 15 numbered requirements and 7 checks.

No gate conditions changed.

## 0.6.0 - 2026-08-27

**Gate conditions** — a sixth is available, off by default.

**Added**

- `harness review` assembles the prompt, spec and diff into a bundle for a
  session with no history of the work.
- `harness review --record ship|hold --note "..."` records a **human**
  ruling in the trace. A hold requires a reason.
- `harness review --status` — has *this* revision been ruled on? Keyed to
  the commit, so an approval cannot carry forward to later work.
- `require_review = true` in `checks.toml` adds a sixth gate condition.
  Off by default: a gate people route around is worse than none.
- `reviewer/fixture.diff` and `fixture.md` - a diff with five planted
  defects and the answer key, so the prompt is not just a claim.

**Not added, deliberately.** The harness does not call a model and believe
the answer. That would move judgement into the machine, and a reviewer the
harness invokes and trusts is the agent grading itself with extra steps.

## 0.5.0 - 2026-08-26

**Breaking** — projects should add `harness_version` to `checks.toml`.
Without it the harness runs but warns.

**Added**

- **Version pinning.** `harness version` refuses when the installed feature
  release differs from the project's pin, in either direction.
- `harness select` shortlists checks whose `files` patterns match what you
  changed. Selection can only widen: a check with no `files` always runs,
  and the gate ignores selection entirely.
- `harness run --all` runs every check without stopping at the first
  failure.
- `harness init` writes a CI workflow.
- Global flags (`--json`, `--config`, `--cwd`) now work after the
  subcommand, not only before it.

## 0.4.0 - 2026-08-02

**Gate conditions** — `red` became stricter. Evidence gathered before this
release may have banked failures the check never earned.

**Added**

- **A red must be earned.** A test file that does not exist yet fails with a
  non-zero exit code exactly like a test that fails. Exit codes attributable
  to the check never running (2/3/4/5 for pytest, 126/127 for any runner)
  are refused rather than banked. Configurable per check with
  `inconclusive = [...]`, or `[]` to opt out.

## 0.3.0 - 2026-08-01

**Added**

- Spec amendments: `status:` and `amended:` on requirements. Re-blessing a
  drifted requirement requires `--reason`, written back into `spec.md`.
- `harness spec history` fails on anything superseded or removed with no
  reason given.
- `harness init` for retrofitting onto an existing repository.
- Runner guidance and per-project examples.

## 0.2.0 - 2026-07-31

**Added**

- The spec layer: numbered requirements, coverage, drift fingerprints,
  `harness spec list|coverage|sync|bless`.

## 0.1.0 - 2026-07-31

The four links: check, red first, trace, gate. HMAC-chained trace with the
key outside the project, and a guard so the graded cannot edit the grader.
