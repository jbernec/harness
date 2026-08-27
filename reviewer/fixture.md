# Reviewer fixture

A diff with five defects planted in it, one per category, and the answers.

## Why this exists

`reviewer.md` is a prompt, and a prompt is a claim about behaviour. Every
other claim in this repo has a check behind it; this one had nothing, which
made it the only part running on the honour system.

You cannot assert on a language model's output the way you assert on an exit
code - ask twice, get two wordings. But you *can* answer the question that
actually matters: **does the prompt surface a defect that is really there?**
Plant known defects, run it cold, count.

Run this whenever you change the prompt. A prompt edit that reads better and
finds less is the failure mode, and without a fixture it is invisible.

## How to run it

Open a session with no history of this repo. Paste the prompt from
[`README.md`](README.md), then `fixture.diff`, and nothing else.
Then compare against the answer key below.

Do not paste the answer key. That is the whole test.

## The answer key

| # | Category | Defect | Where |
|---|---|---|---|
| 1 | WRONG | `REFUND_WINDOW_DAYS + 1` makes the window 91 days; R-015 says 90 and "never after" | `within_refund_window` |
| 2 | SILENT FAILURE | `except Exception` returns `{"ok": True, "reason": "refund submitted"}` - a failed gateway call reports success | `issue_refund` |
| 3 | IRREVERSIBLE | `DELETE FROM charges` with no runner, no dry run, no confirmation | `purge_settled_charges` |
| 4 | WIDER | `retry_with_backoff` and `format_money` are unrelated to R-015 | both |
| 5 | UNPROVEN | R-015 requires refunds in the original currency; `currency` is passed through and never checked against the charge | `issue_refund` |

Also worth finding, not planted deliberately:

- `gateway` and `db` are never imported. The `NameError` is swallowed by the
  bare `except Exception`, which then returns `ok: True` - two defects
  compounding into one that is worse than either.
- The two tests sit at 10 and 400 days, so neither goes near the boundary.
  They pass whether the window is 90, 91 or 200.

**Should not be flagged.** The tests are reasonable, the naming is fine, and
there is nothing to say about formatting. A run that spends findings on those
is padding, and the prompt forbids it.

## Recorded runs

| Date | Model | Planted found | Bonus | Format rules |
|---|---|---|---|---|
| 2026-08-27 | Claude Opus 4.6 | 5/5 | the unimported `gateway`/`db` chain | followed |

Notes from that run: it cross-listed the swallowed exception under both WRONG
and SILENT FAILURE, which is correct rather than duplication - it is both. It
used "unsure" exactly once, where it should have, about whether `gateway` is
a live client. It ended on one line: **HOLD**, naming the off-by-one and the
silent success.

One 5/5 is a pass, not proof. It says the prompt works on defects of this
shape. It does not say it works on yours.
