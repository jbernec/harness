# How checks fail

Four ways a check quietly stops working.

[README](../README.md) · [Concepts](concepts.md) · [Requirements](requirements.md) · [Runners](runners.md) · [How checks fail](failures.md) · [Retrofitting](retrofit.md) · [Trace and guard](security.md)

---

Red-first catches the check that could never fail. These are the other four,
all learned the expensive way.

## 1. The check that copies what it guards

You write a check to catch a value being duplicated in two places. You
hardcode that value in the check. The check now finds **three** copies —
including itself:

```
assert 3 == 2
found in: ['src/config.py', 'src/legacy.py', 'tests/test_no_duplicates.py']
```

A duplication check must **derive** its needle from the source, never repeat
it:

```python
# wrong - the check is now another copy
LIMIT = "0.20"

# right - one source of truth, the check reads it
LIMIT = re.search(r"MAX_POSITION\s*=\s*([\d.]+)", SOURCE.read_text()).group(1)
```

Same rule as `bless`: never type a value the tool can compute.

## 2. The guard that cries wolf

A guard that flags legitimate work gets bypassed, and a bypassed guard
catches nothing. It is worse than no guard, because you think you're covered.

Scope guards by **what actually caused harm**, not by what looks suspicious:

```
too broad   any scratch file in the tree      <- blocks exploration
right       a scratch file that WRITES        <- catches only the real thing
```

Read-only exploration is the reversible side of the line. Improvising there
is correct and must stay cheap.

## 3. The guard nobody proved

Every guard needs testing **in both directions**, or you don't know which
kind you built:

```bash
# must FAIL - the thing it exists to catch
<create the violation>
python scripts/guard.py; echo "expect 1, got $?"

# must PASS - normal, legitimate work
<create something harmless>
python scripts/guard.py; echo "expect 0, got $?"
```

Only the first passing means it's decoration. Only the second passing means
it's an obstacle. You need both.

## 4. The code nothing can reach

A function that exists only in a scratch script is invisible: no caller, no
test, no path from any entry point. It never shows up as broken because
nothing runs it.

Check reachability from the real entry point:

```toml
[[check]]
name = "no_orphan_entrypoints"
cmd = "python -m pytest tests/test_reachability.py -q"
description = "every registered handler is reachable from the entry point"
```

Make it a test, not a script. An unreachable module should fail CI, not wait
for someone to remember a linter exists.

## 5. The red that was never earned

The other four are checks that stop working. This one is a check that never
started, and it is the only one on the list that fakes its own evidence.

`harness red` requires a check to fail before the work begins. But a test file
that does not exist yet fails too, and by exit code alone it looks identical
to a test that fails:

```bash
pytest tests/test_parser.py -q   # assertion failed        -> 1
pytest tests/test_parser.py -q   # ImportError collecting  -> 2
pytest tests/test_parser.py -q   # file does not exist     -> 4
pytest tests/test_parser.py -q   # nothing collected       -> 5
```

Bank one of the last three as your baseline and the trace shows a clean
red → green for a test that was never written. The gate accepts it, correctly:
the trace says it was broken, then wasn't.

`red` now refuses exits 2, 3, 4 and 5 for pytest, and 126/127 everywhere. What
it cannot see is a missing runner — `python -m pytest` without pytest installed
exits 1 like any failing test. Run the suite once by hand before the first red.

The discipline the tool cannot enforce: write the failing test, watch it fail
**for the reason you expect**, then run `red`. An exit code is not a reason.

## And before you write any of it

**Check whether the thing already exists.** A runner you didn't know about
is worse than no runner — build a second one and you've created the drift
you were removing.

```bash
grep -rn "def main\|^run:\|entry_points\|\"scripts\"" \
  --include=*.py --include=Makefile --include=package.json --include=*.toml .
```

---
