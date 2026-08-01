# Retrofitting

Putting a harness on a project that already exists.

[README](../README.md) · [Concepts](concepts.md) · [Requirements](requirements.md) · [Runners](runners.md) · [How checks fail](failures.md) · [Retrofitting](retrofit.md) · [Trace and guard](security.md)

---

```bash
cd ~/code/my-project
harness init
```

Writes `checks.toml`, `spec.md`, `decisions.md`, `AGENTS.md`, detects your
test command, and **never overwrites anything that already exists**.

## The one thing you cannot recover

Code that already works has no red to observe. That evidence is gone and no
tool gets it back. Run `harness red unit` on a passing suite and you'll get:

```
FAIL  'unit' PASSED during the red step.
      A check that already passes is not testing your fix.
```

That is correct, not a bug. **Red-first applies from your next change
onward** — which is where it was going to matter anyway. Don't fake a red to
make the tool happy; you'd only be lying to yourself in a durable format.

## Order to do it in

1. **`harness init`**, then fix the test command if it guessed wrong.
2. **Write the objective** at the top of `spec.md`. One sentence, one number.
3. **Add requirements from real failures, not from imagination.** Something
   broke last month? That's `R-001`, and the check is a test that would have
   caught it. Something broke twice? That's your first check, today.
4. **`harness spec bless`** to record the fingerprints.
5. **From here on, new work goes red first.**

## What not to do

Do not sit down and write forty requirements before touching code. You'll
produce a document nobody maintains and drift starts on day two. Five
requirements that came from real incidents beat forty invented ones.

Start where it hurts. If nothing hurts yet, one check on the thing that
would ruin your week if it broke silently.

---
