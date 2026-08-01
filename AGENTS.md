# AGENTS.md

Instructions for any coding agent working in a repo that uses this harness.
Applies to GitHub Copilot, Claude Code, Codex, and anything else.

## The rules

1. **Do not edit anything listed under `protected` in `checks.toml`.**
   Usually that's `tests/`. If you believe a test is wrong, say so and stop.
   Do not change it.

2. **Do not edit `checks.toml`.** Not the commands, not the expected exit
   codes, not the timeouts. Weakening a check is not progress.

3. **Do not write to `~/.harness/`.** That is the trace and the key. It is
   not yours.

4. **Do not report success.** You do not decide when work is done.
   `harness gate` decides. Report what you changed; stop there.

5. **Never hand-write a sequence that already has a runner.**
   Before writing any script for a multi-step procedure, **check whether a
   runner already exists** — search for entry points and read them. Building
   a second runner creates the drift you were removing.

   If a procedure exists as a script, a make target, or a documented ordered
   list, invoke it. Do not retype it, do not write a "temp script" that does
   the same thing, do not do the steps individually because it seemed faster.

   This is where real damage happens. A dropped step in an ordered procedure
   is not a typo, it's an unrecoverable state. If the runner is wrong, say so
   and stop — do not route around it.

   Read-only probes are fine. Investigating with a throwaway `SELECT` script
   is reversible and costs nothing. Delete it when you're done.

6. **Irreversible actions are on rails.**
   Writing to production, submitting orders, moving money, deploying, sending
   messages to real people: runner only, never improvised. You may improvise
   freely anywhere the cost of being wrong is `git checkout`.

7. **If a check will not pass, say why.** "I could not make
   `test_escrow.py` pass because the escrow model has no partial-refund
   state" is a genuinely useful answer. A green you engineered by gutting the
   assertion is worse than no answer at all.

8. **If you write a check, do not hardcode what it guards.**
   A duplication check that repeats the constant becomes another copy of it.
   Derive the value from the source file. Never type a value the tool can
   compute.

9. **If you write a guard, prove it both ways.**
   Show it failing on the thing it must catch, and passing on legitimate
   work. A guard that only ever passes is decoration; one that blocks normal
   work gets bypassed. Report both exit codes.

## The loop you are part of

```
human:  harness red <check>     the check must fail first
you:    change source code      tests/ is off limits
human:  harness run <check>     did it go green?
human:  harness gate <check>    red -> green, in order, tests untouched?
```

You only occupy the second row.

## Task template for the human

```
`<command>` currently fails.
Make it pass.

Do not edit anything under tests/.
Do not change the command.
When you are done, list only the files you changed.
```

## Why it is set up this way

Not distrust of any particular model — a structural point. Whoever does the
work cannot also certify the work, because the cheapest way to satisfy a
grader you control is to lower it. Removing that shortcut is what makes a
green result mean something.

The runner rules are a separate concern. They exist because recalling a
sequence correctly is a thing every agent (and every human) eventually gets
wrong, and the cost is paid in data rather than in time. A step you never
type is a step you cannot drop.
