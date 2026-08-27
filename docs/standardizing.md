# Standardizing across projects

One harness, many applications. Read once, then it is four commands.

[README](../README.md) · [Concepts](concepts.md) · [Requirements](requirements.md) · [Runners](runners.md) · [How checks fail](failures.md) · [Retrofitting](retrofit.md) · [Standardizing](standardizing.md) · [Trace and guard](security.md)

---

## What is shared, and what is not

The whole point is that "green" means the same thing in every project. That
only holds if the machinery is identical and only the content varies.

| | Shared, never forked | Per project |
|---|---|---|
| `harness/` | ✅ installed from one repo | |
| `AGENTS.md` | ✅ same rules everywhere | |
| `checks.toml` | | ✅ your checks |
| `spec.md` | | ✅ your requirements |
| `decisions.md` | | ✅ your history |
| runner | | ✅ only where actions are irreversible |

**If you find yourself editing `harness/` inside an application, stop.** That
is a fork, and from that moment your five projects have five definitions of
done. Fix it in the harness repo, release, bump the pin.

---

## Install

```bash
pip install "harness @ git+https://github.com/jbernec/harness@v0.6.1"
```

Pin the tag, not `main`. `main` moves; a tag is a decision.

Then in each project:

```bash
harness init            # writes checks.toml, spec.md, decisions.md,
                        # AGENTS.md and a CI workflow. Never overwrites.
harness init --no-ci    # ...without the workflow
```

---

## The version pin

`harness init` writes the release it used into `checks.toml`:

```toml
harness_version = "0.5.0"
```

and a check that enforces it:

```
$ harness version
FAIL  this project was gated with harness 0.4.0, but 0.5.0 is installed.
      Either install 0.4.0 or, if you have read what changed, set
      harness_version = "0.5.0" in checks.toml.
```

**Patch releases are interchangeable** — 0.5.0 and 0.5.7 both satisfy a pin of
0.5.0, because patches are fixes. Forcing five repos to move together for a
bug fix makes upgrading painful enough that nobody does it.

**Feature releases are not**, in either direction. A newer harness may add a
gate condition, which means older evidence was gathered under weaker rules.
An older one is obviously worse. Either way the point is that you looked.

### Upgrading

One repo at a time, deliberately:

```bash
pip install --upgrade "harness @ git+https://github.com/jbernec/harness@vNEXT"
harness version                     # tells you exactly what to change
# read what changed, then edit harness_version in checks.toml
harness run --all
```

There is no `--force`. Skipping the reading is the thing the pin exists to
prevent.

---

## CI

`harness init` writes `.github/workflows/harness.yml`. It installs the pinned
version, then:

```yaml
- run: harness version
- run: harness guard
- run: harness run --all
```

`harness run --all` runs every check and does not stop at the first failure —
CI should give you the whole picture, not one problem per push.

**CI does not gate.** The trace and key live outside the repo, so a fresh
runner has no history and therefore no red to point at. That is honest rather
than a gap:

| | Proves |
|---|---|
| Local `harness gate` | red → green, in order, tests untouched |
| CI `harness run --all` | everything passes from a clean checkout |

Do not fabricate a red in CI to make the gate open. A gate that can be
satisfied by a machine with no memory of the work is not a gate.

---

## Rolling it out

Do not do all of this at once. In order:

1. **One project.** Install, `harness init`, delete the checks you will not
   use. Get `harness run --all` green.
2. **Prove one red.** Break something on purpose, `harness red`, fix it,
   `harness gate`. Until you have done this once, none of it is real.
3. **Second project.** If you find yourself changing `harness/` to make it
   fit — that is a bug in the harness, not in the project. Fix it upstream.
4. **Then the rest.** By now the shape is stable.

Adding a runner is separate and only where actions are irreversible. See
[runners](runners.md).

---

## Agent instruction files

One copy of the rules. `AGENTS.md` holds them; the others point at it:

```
AGENTS.md                          <- the rules
CLAUDE.md                          <- "See AGENTS.md."
.github/copilot-instructions.md    <- "See AGENTS.md."
```

Three files with the same rules is three files that drift, and when they
disagree nobody knows which is current.
