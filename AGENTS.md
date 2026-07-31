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

5. **If a check will not pass, say why.** "I could not make
   `test_escrow.py` pass because the escrow model has no partial-refund
   state" is a genuinely useful answer. A green you engineered by gutting the
   assertion is worse than no answer at all.

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
