# Reviewer

A prompt for a **separate session** to review work the harness has already
passed. Paste it into a fresh chat with no history of building the thing.

Why separate: the checks prove the code does what the checks say. They cannot
tell you the checks were the right ones, or that the change is larger than the
problem. That judgement has to come from somewhere that did not do the work.

Do not run this in the session that wrote the code. An author reviewing their
own diff finds what they were already worried about, which is the set they
already handled.

---

## The prompt

```
You are reviewing a change you did not write. Assume the author is competent
and the tests pass - both are already established and neither is what I am
asking you about.

Read the diff and the spec. Report only what you can point at.

1. WRONG
   Logic that does not do what its name, its comment, or the spec says.
   Quote the line. Say what it does instead.

2. UNPROVEN
   Behaviour the change relies on that no check covers. For each one, name
   the check that should exist and what it would assert.

3. WIDER THAN THE PROBLEM
   Anything in the diff not required by the stated requirement. Files,
   flags, abstractions, dependencies. List them.

4. SILENT FAILURE
   Paths where an error is swallowed, a default hides a missing value, or a
   failure produces a passing exit code.

5. IRREVERSIBLE
   Anything that writes, deletes, migrates, deploys or spends. State whether
   it is behind a runner and whether a dry run exists.

Rules for your report:
- Every finding cites a file and line. No finding without a location.
- If you are unsure, say "unsure" and say what would settle it.
- Do not comment on style, naming, formatting or test organisation.
- Do not suggest refactors that are not fixing something in the list above.
- If a section has nothing, write "none" and move on. Do not pad.
- No summary paragraph. The findings are the output.

End with one line: SHIP or HOLD, and the single reason.
```

---

## Using it

```
git diff main...HEAD > /tmp/review.diff
```

Open a new session. Paste the prompt, the diff, and `spec.md`. Nothing else -
not the build log, not the reasoning that produced the change. Context that
explains why the author did something is exactly the context that stops a
reviewer noticing they should not have.

## What to do with the output

| Finding | Action |
|---|---|
| WRONG | Fix. Add a check that would have caught it - it will happen again. |
| UNPROVEN | Write the check. If you decide not to, `gate: human` in the spec. |
| WIDER | Delete it, or add the requirement that justifies it. |
| SILENT | Fix. This is the class that survives to production. |
| IRREVERSIBLE | Runner, or explain in `decisions.md` why not. |

A HOLD you disagree with is still worth recording. Write it down in
`decisions.md` with your reason. If the next reviewer raises the same point,
you have your answer ready - and if the point turns out to be right, you have
the date you were warned.

## What this is not

It is not a gate. It has no exit code and it cannot be trusted to be
repeatable - ask twice, get two answers. Keep it where judgement belongs and
out of the place where proof belongs.

One reviewer, generic on purpose. Splitting it into a security reviewer, a
performance reviewer and a correctness reviewer sounds thorough and produces
three shallow passes plus three files to keep in sync. Add a second only when
you can name a finding the first one demonstrably missed twice.

## Does it actually work?

A prompt is a claim about behaviour, and every other claim in this repo has
something behind it. [`fixture.md`](fixture.md) is a diff with five defects
planted in it, one per category, and the answers. Run the prompt cold against
[`fixture.diff`](fixture.diff) and count.

Run it again whenever you change the prompt. **A prompt edit that reads
better and finds less is the failure mode**, and without a fixture it is
invisible.

Last recorded run found 5/5, plus a defect that was not planted. That is a
pass, not proof: it says the prompt works on defects of this shape, not that
it works on yours.
