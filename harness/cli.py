"""Command line interface.

    harness init                 write starter files into an existing repo
    harness list                 show every check
    harness select               which checks concern the files you changed
    harness red <name>           run a check and require it to FAIL
    harness run <name>           run a check and record the result
    harness gate <name>          decide whether the work is done
    harness guard                confirm protected paths were not edited
    harness verify               verify the trace chain
    harness review               bundle the diff + spec for a fresh session
    harness review --record ...  record what a human decided
    harness version              fail if the installed harness is not the pinned one
    harness log [name]           print recorded evidence
    harness spec list            requirements and how each is settled
    harness spec coverage        fail if a requirement has no check and no gate
    harness spec sync            fail if a requirement changed after review
    harness spec history         fail if a change was made with no reason given
    harness spec amend <id>      record a dated reason for a change
    harness spec bless [id]      record that a check matches the spec as written
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .check import changed_files, did_not_run, load_config, run, select
from .gate import evaluate
from .guard import check_protected
from .init import init
from .trace import Trace
from . import review, spec
from .version import __version__, status as version_status

OK = "PASS"
NO = "FAIL"


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload))


def cmd_list(cfg, args, cwd, trace) -> int:
    if args.json:
        print(json.dumps([{"name": c.name, "cmd": c.cmd, "expect": c.expect} for c in cfg.checks.values()]))
        return 0
    print(f"project: {cfg.project}\n")
    for c in cfg.checks.values():
        print(f"  {c.name}")
        print(f"      cmd    {c.cmd}")
        print(f"      expect exit {c.expect}")
        if c.description:
            print(f"      {c.description}")
    print(f"\nprotected: {', '.join(cfg.protected)}")
    print(f"trace:     {trace.path}")
    return 0


def _resolve(cfg, name: str):
    if name not in cfg.checks:
        print(f"unknown check '{name}'. Known: {', '.join(cfg.checks)}", file=sys.stderr)
        raise SystemExit(2)
    return cfg.checks[name]


def cmd_red(cfg, args, cwd, trace) -> int:
    """Observe the failure first. This is the step that makes the rest mean anything."""
    check = _resolve(cfg, args.name)
    result = run(check, cwd)

    # A failure the check never earned is not a baseline. Recorded under a
    # phase the gate ignores, so it is auditable without counting as red.
    void = None if result.ok else did_not_run(check, result.exit_code)
    phase = "void" if void else "red"
    trace.append(check.name, check.cmd, phase, result.ok, result.exit_code, result.output)

    if result.ok:
        msg = (
            f"{NO}  '{check.name}' PASSED during the red step.\n"
            "      A check that already passes is not testing your fix.\n"
            "      Fix the check, then try again."
        )
        _emit({"ok": False, "check": check.name, "reason": "check passed during red step"}, args.json)
        if not args.json:
            print(msg)
        return 1

    if void:
        msg = (
            f"{NO}  '{check.name}' failed (exit {result.exit_code}), but it never ran: {void}.\n"
            "      A check that could not run has not told you anything about the code.\n"
            "      Write the failing test first, watch it fail on its own terms, then run red."
        )
        _emit(
            {"ok": False, "check": check.name, "exit_code": result.exit_code, "reason": f"did not run: {void}"},
            args.json,
        )
        if not args.json:
            print(msg)
        return 1

    _emit({"ok": True, "check": check.name, "exit_code": result.exit_code}, args.json)
    if not args.json:
        print(f"{OK}  '{check.name}' failed as required (exit {result.exit_code}). Baseline recorded.")
    return 0


def cmd_run(cfg, args, cwd, trace) -> int:
    if getattr(args, "all", False):
        return _run_all(cfg, args, cwd, trace)
    check = _resolve(cfg, args.name)
    result = run(check, cwd)

    # Same rule as red: `run` also writes rows the gate reads for saw_red, so
    # a check that never ran must not become red evidence by the back door.
    void = None if result.ok else did_not_run(check, result.exit_code)
    trace.append(check.name, check.cmd, "void" if void else "run", result.ok, result.exit_code, result.output)

    _emit(
        {"ok": result.ok, "check": check.name, "exit_code": result.exit_code, **({"reason": f"did not run: {void}"} if void else {})},
        args.json,
    )
    if not args.json:
        if void:
            print(f"{NO}  '{check.name}' did not run (exit {result.exit_code}): {void}.")
        else:
            state = "GREEN" if result.ok else "RED"
            print(f"{OK if result.ok else NO}  '{check.name}' is {state} (exit {result.exit_code}).")
    return 0 if result.ok else 1


def cmd_select(cfg, args, cwd, trace) -> int:
    """Which checks concern what you changed.

    A shortlist for the edit-run loop, never for the gate. Any check that
    would decide "done" runs in full, because the way to pass a selective
    suite is to touch nothing it watches.
    """
    paths = changed_files(cwd, args.base)

    if paths is None:
        chosen, why = list(cfg.checks.values()), "git could not answer - running everything"
    elif not paths:
        chosen, why = [], "nothing changed"
    else:
        chosen = select(cfg.checks, paths)
        why = f"{len(paths)} changed file(s)"

    payload = {
        "ok": True,
        "reason": why,
        "changed": paths or [],
        "checks": [c.name for c in chosen],
        "skipped": [c.name for c in cfg.checks.values() if c not in chosen],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"{why}\n")
    for c in chosen:
        scope = ", ".join(c.files) if c.files else "unscoped - always runs"
        print(f"  {c.name:<24} {scope}")
    if payload["skipped"]:
        print(f"\n  not concerned: {', '.join(payload['skipped'])}")
    print("\nThis is a shortlist for iterating. Gate on the full set.")
    return 0


def _run_all(cfg, args, cwd, trace) -> int:
    """Every check, once, without stopping at the first failure.

    CI wants the whole picture in one run - stopping early means fixing one
    thing, pushing, and waiting to discover the next. It does not select:
    running a subset in CI would let a change pass by touching nothing the
    suite watches.
    """
    results = []
    for check in cfg.checks.values():
        result = run(check, cwd)
        void = None if result.ok else did_not_run(check, result.exit_code)
        trace.append(
            check.name, check.cmd, "void" if void else "run",
            result.ok, result.exit_code, result.output,
        )
        results.append((check, result, void))

    failed = [c.name for c, r, _ in results if not r.ok]
    ok = not failed

    if args.json:
        print(json.dumps({
            "ok": ok,
            "total": len(results),
            "failed": failed,
            "checks": [
                {"check": c.name, "ok": r.ok, "exit_code": r.exit_code,
                 **({"reason": f"did not run: {v}"} if v else {})}
                for c, r, v in results
            ],
        }, indent=2))
        return 0 if ok else 1

    for check, result, void in results:
        if void:
            print(f"{NO}  {check.name:<28} did not run (exit {result.exit_code}): {void}")
        else:
            print(f"{OK if result.ok else NO}  {check.name:<28} exit {result.exit_code}")
    print()
    print(f"{OK if ok else NO}  {len(results) - len(failed)}/{len(results)} passed"
          + ("" if ok else f" - failed: {', '.join(failed)}"))
    return 0 if ok else 1


def cmd_gate(cfg, args, cwd, trace) -> int:
    check = _resolve(cfg, args.name)
    verdict = evaluate(trace, check, cwd)
    guard = (
        check_protected(cwd, cfg.protected, ignore=cfg.guard_ignore)
        if not args.skip_guard
        else {"ok": True, "reason": "guard skipped"}
    )

    # Opt-in. Requiring a human ruling on every check would make the gate
    # something people route around, and a gate people route around is worse
    # than no gate - it launders the habit into a green.
    sha = review.head_sha(cwd) if cfg.require_review else None
    seen = review.reviewed(trace, sha) if sha else {"reviewed": True, "verdict": None}
    review_ok = (not cfg.require_review) or (seen["reviewed"] and seen["verdict"] == "ship")

    ok = verdict.ok and guard["ok"] and review_ok

    trace.append(check.name, check.cmd, "gate", ok, 0 if ok else 1, f"{verdict.reason} | guard: {guard['reason']}")

    if not verdict.ok:
        reason = verdict.reason
    elif not guard["ok"]:
        reason = guard["reason"]
    elif not review_ok:
        reason = (
            f"reviewed and held: {seen['note']}" if seen["reviewed"]
            else "this revision has not been reviewed - run `harness review`"
        )
    else:
        reason = guard["reason"]

    if args.json:
        payload = {
            "ok": ok,
            "check": check.name,
            "chain_intact": verdict.chain_intact,
            "saw_red": verdict.saw_red,
            "green_after_red": verdict.green_after_red,
            "currently_green": verdict.currently_green,
            "protected_ok": guard["ok"],
            "reason": reason,
        }
        if cfg.require_review:
            payload["reviewed"] = review_ok
        print(json.dumps(payload))
    else:
        mark = lambda b: "yes" if b else "no "  # noqa: E731
        print(f"check              {check.name}")
        print(f"  chain intact     {mark(verdict.chain_intact)}")
        print(f"  saw red          {mark(verdict.saw_red)}")
        print(f"  green after red  {mark(verdict.green_after_red)}")
        print(f"  green now        {mark(verdict.currently_green)}")
        print(f"  tests untouched  {mark(guard['ok'])}")
        if cfg.require_review:
            print(f"  reviewed         {mark(review_ok)}")
        print()
        print(f"{OK if ok else NO}  {reason}")
    return 0 if ok else 1


def cmd_review(cfg, args, cwd, trace) -> int:
    """Assemble the bundle, or record what a human decided. Never both, and
    never a verdict this tool produced itself."""
    sha = review.head_sha(cwd)
    if sha is None:
        print("not a git repository - review needs a revision to key on", file=sys.stderr)
        return 2

    if args.record:
        note = args.note or ""
        if args.record == "hold" and not note:
            print("a HOLD needs --note: the reason is the whole value of it", file=sys.stderr)
            return 2
        trace.append("review", sha, "review", args.record == "ship", 0, note)
        _emit({"ok": True, "verdict": args.record, "revision": sha[:8], "note": note}, args.json)
        if not args.json:
            print(f"{OK}  recorded {args.record.upper()} for {sha[:8]}"
                  + (f": {note}" if note else ""))
        return 0

    if args.status:
        seen = review.reviewed(trace, sha)
        _emit({**seen, "revision": sha[:8]}, args.json)
        if not args.json:
            if seen["reviewed"]:
                print(f"{OK}  {sha[:8]} reviewed {seen['ts']}: "
                      f"{seen['verdict'].upper()}" + (f" - {seen['note']}" if seen["note"] else ""))
            else:
                print(f"{NO}  {sha[:8]} has not been reviewed")
        return 0 if seen["reviewed"] else 1

    change = review.diff(cwd, args.base)
    if not change:
        print(f"no changes against {args.base} - nothing to review", file=sys.stderr)
        return 2

    reviewer_md = ""
    for candidate in (cwd / "reviewer" / "README.md", cwd / "reviewer.md",
                      Path(__file__).resolve().parents[1] / "reviewer" / "README.md"):
        if candidate.exists():
            reviewer_md = candidate.read_text(encoding="utf-8")
            break
    if not reviewer_md:
        print("no reviewer prompt found (reviewer/README.md)", file=sys.stderr)
        return 2

    spec_path = cwd / cfg.spec
    text = review.bundle(
        cwd,
        review.extract_prompt(reviewer_md),
        spec_path.read_text(encoding="utf-8") if spec_path.exists() else None,
        change,
        args.base,
    )
    out = cwd / review.BUNDLE
    out.write_text(text, encoding="utf-8")

    _emit({"ok": True, "bundle": str(out), "revision": sha[:8]}, args.json)
    if not args.json:
        print(f"{OK}  wrote {review.BUNDLE} ({len(text.splitlines())} lines) for {sha[:8]}")
        print("\nOpen a session with no history of this work and paste that file.")
        print("Then: harness review --record ship|hold --note \"...\"")
    return 0


def cmd_guard(cfg, args, cwd, trace) -> int:
    result = check_protected(cwd, cfg.protected, ignore=cfg.guard_ignore)
    _emit(result, args.json)
    if not args.json:
        print(f"{OK if result['ok'] else NO}  {result['reason']}")
    return 0 if result["ok"] else 1


def cmd_verify(cfg, args, cwd, trace) -> int:
    result = trace.verify()
    _emit(result, args.json)
    if not args.json:
        print(f"{OK if result['ok'] else NO}  {result['reason']} ({result['rows']} rows)")
        print(f"      {trace.path}")
    return 0 if result["ok"] else 1


def cmd_log(cfg, args, cwd, trace) -> int:
    rows = [r for r in trace.rows() if not args.name or r.get("check") == args.name]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no evidence recorded yet")
        return 0
    for r in rows:
        state = "GREEN" if r["ok"] else "RED  "
        print(f"{r['ts']}  {state}  {r['phase']:<5}  {r['check']}")
    return 0


def cmd_version(cfg, args, cwd, trace) -> int:
    """Does the installed harness match the one this project was gated with?

    Exits non-zero on a mismatch, so it works as a check like any other and
    fails the whole suite rather than being something you remember to look at.
    """
    result = version_status(cfg.harness_version, __version__)
    _emit(result, args.json)
    if not args.json:
        print(f"{OK if result['ok'] else NO}  {result['reason']}")
    return 0 if result["ok"] else 1


def cmd_spec(cfg, args, cwd, trace) -> int:
    """Requirements, and whether each one is honestly accounted for."""
    spec_path = cwd / cfg.spec
    try:
        reqs = spec.parse(spec_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"spec error: {exc}", file=sys.stderr)
        return 2

    action = args.spec_action

    if action == "list":
        if args.json:
            print(json.dumps([
                {
                    "id": r.id,
                    "title": r.title,
                    "settled_by": r.settled_by,
                    "check": r.check,
                    "gate": r.gate,
                    "status": r.status,
                    "amendments": [str(a) for a in r.amendments],
                    "fingerprint": r.fingerprint,
                }
                for r in reqs
            ], indent=2))
            return 0
        print(f"spec: {spec_path}\n")
        for r in reqs:
            how = {"check": f"check {r.check}", "human": f"gate {r.gate}",
                   "removed": "removed", "nothing": "NOTHING - unsettled"}[r.settled_by]
            print(f"  {r.id:<14} {r.fingerprint}  {r.status:<12} {how}")
            print(f"  {'':<14} {r.title}")
            for a in r.amendments:
                print(f"  {'':<14} amended {a}")
        return 0

    if action == "coverage":
        result = spec.coverage(reqs, set(cfg.checks))
        _emit(result, args.json)
        if not args.json:
            print(f"{result['total']} live requirements: "
                  f"{result['by_check']} by check, {result['by_human']} by human gate")
            print(f"{OK if result['ok'] else NO}  {result['reason']}")
        return 0 if result["ok"] else 1

    if action == "history":
        result = spec.history(reqs)
        _emit(result, args.json)
        if not args.json:
            print(f"{result['amended']} recorded amendment(s)")
            print(f"{OK if result['ok'] else NO}  {result['reason']}")
        return 0 if result["ok"] else 1

    if action == "amend":
        if not spec.amend(spec_path, args.id, args.reason, args.on):
            print(f"no requirement '{args.id}' in {spec_path}", file=sys.stderr)
            return 2
        print(f"amended  {args.id}  {args.on or 'today'}  {args.reason}")
        print("\nThe old wording is in git. This says why it is no longer the wording.")
        return 0

    if action == "sync":
        result = spec.sync(reqs, cfg.checks)
        _emit(result, args.json)
        if not args.json:
            print(f"{OK if result['ok'] else NO}  {result['reason']}")
        return 0 if result["ok"] else 1

    if action == "bless":
        cfg_path = Path(args.config) if Path(args.config).is_absolute() else cwd / args.config
        targets = [r for r in reqs if r.check and not r.removed]
        if args.id:
            targets = [r for r in targets if r.id == args.id]
            if not targets:
                print(f"no requirement '{args.id}' with a check", file=sys.stderr)
                return 2

        for r in targets:
            recorded = getattr(cfg.checks.get(r.check), "requirement_hash", "")
            # Re-blessing after drift is the moment the change becomes
            # official. That is the only moment you still remember why.
            if recorded and recorded != r.fingerprint and not args.reason:
                print(
                    f"{NO}  {r.id} changed since it was last blessed "
                    f"({recorded} -> {r.fingerprint}).\n"
                    f"      Re-blessing needs a reason: "
                    f"harness spec bless {r.id} --reason \"...\"",
                    file=sys.stderr,
                )
                return 1

            if not spec.bless(cfg_path, r.check, r.fingerprint):
                print(f"skipped  {r.id:<14} check '{r.check}' not found in {args.config}", file=sys.stderr)
                continue
            note = ""
            if args.reason and recorded and recorded != r.fingerprint:
                spec.amend(spec_path, r.id, args.reason)
                note = "  (amendment recorded)"
            print(f"blessed  {r.id:<14} {r.fingerprint}  -> check {r.check}{note}")
        print("\nYou have stated that these checks match the spec as written.")
        return 0

    return 2


def cmd_init(args, cwd) -> int:
    """Write starter files into an existing repository."""
    result = init(cwd, args.project, ci=not args.no_ci)

    if args.json:
        print(json.dumps(result))
        return 0

    print(f"project: {result['project']}\n")
    for f in result["written"]:
        print(f"  created  {f}")
    for f in result["skipped"]:
        print(f"  kept     {f}  (already exists, left alone)")

    print(f"\ndetected test command: {result['test_cmd']}")
    print("""
Next, in order:

  1. Open checks.toml and confirm that test command is right.
  2. harness red unit        -> it should FAIL. If it passes, the check is
                               not testing what you think it is.
  3. Write your objective at the top of spec.md. One sentence, one number.
  4. Add requirements as things break, not all at once.
  5. harness spec bless      -> record that the checks match the spec.

You cannot recover red-first evidence for code that already works. That is
fine. You get it from the next change onward, which is where it mattered.""")
    return 0


COMMANDS = {
    "list": cmd_list,
    "select": cmd_select,
    "red": cmd_red,
    "run": cmd_run,
    "gate": cmd_gate,
    "guard": cmd_guard,
    "verify": cmd_verify,
    "log": cmd_log,
    "spec": cmd_spec,
    "version": cmd_version,
    "review": cmd_review,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness", description="Prove the work, don't trust the claim.")
    parser.add_argument("--config", default="checks.toml", help="path to checks.toml")
    parser.add_argument("--cwd", default=".", help="project directory")
    parser.add_argument("--json", action="store_true", help="machine-readable output")

    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, parent=sub):
        """Register a subcommand that also accepts the global flags.

        `harness list --json` is what everybody types, and argparse rejects it
        by default because the flag belongs to the parent. SUPPRESS means the
        subparser only sets the value when the flag is actually given, so the
        parent's value survives when it isn't.
        """
        p = parent.add_parser(name)
        for flag, kwargs in (
            ("--json", {"action": "store_true"}),
            ("--config", {}),
            ("--cwd", {}),
        ):
            p.add_argument(flag, default=argparse.SUPPRESS, **kwargs)
        return p

    add("list")
    p_select = add("select")
    p_select.add_argument("--base", help="git ref to diff against, e.g. main")
    for name in ("red", "run", "gate"):
        p = add(name)
        p.add_argument("name", nargs="?" if name == "run" else None)
        if name == "gate":
            p.add_argument("--skip-guard", action="store_true")
        if name == "run":
            p.add_argument("--all", action="store_true", help="run every check")
    add("guard")
    add("verify")
    add("version")
    p_log = add("log")
    p_log.add_argument("name", nargs="?")

    p_spec = add("spec")
    spec_sub = p_spec.add_subparsers(dest="spec_action", required=True)
    add("list", spec_sub)
    add("coverage", spec_sub)
    add("sync", spec_sub)
    add("history", spec_sub)
    p_amend = add("amend", spec_sub)
    p_amend.add_argument("id", help="requirement id")
    p_amend.add_argument("--reason", required=True, help="why it changed")
    p_amend.add_argument("--on", help="date, defaults to today")
    p_bless = add("bless", spec_sub)
    p_bless.add_argument("id", nargs="?", help="requirement id, or omit for all")
    p_bless.add_argument("--reason", help="required when re-blessing a changed requirement")

    p_review = add("review")
    p_review.add_argument("--base", default="main", help="git ref to diff against")
    p_review.add_argument("--record", choices=["ship", "hold"], help="record a human verdict")
    p_review.add_argument("--note", help="why - required for a hold")
    p_review.add_argument("--status", action="store_true", help="has this revision been reviewed?")

    p_init = add("init")
    p_init.add_argument("--project", help="project name (defaults to the directory name)")
    p_init.add_argument("--no-ci", action="store_true", help="skip the CI workflow")

    args = parser.parse_args(argv)
    if getattr(args, "command", None) == "run" and not args.all and not args.name:
        parser.error("run needs a check name, or --all")
    cwd = Path(args.cwd).resolve()

    # init runs before a config exists, so it cannot require one.
    if args.command == "init":
        return cmd_init(args, cwd)

    try:
        cfg = load_config(Path(args.config) if Path(args.config).is_absolute() else cwd / args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    trace = Trace(cfg.project)
    return COMMANDS[args.command](cfg, args, cwd, trace)


if __name__ == "__main__":
    raise SystemExit(main())
