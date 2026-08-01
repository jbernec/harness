"""Command line interface.

    harness init                 write starter files into an existing repo
    harness list                 show every check
    harness select               which checks concern the files you changed
    harness red <name>           run a check and require it to FAIL
    harness run <name>           run a check and record the result
    harness gate <name>          decide whether the work is done
    harness guard                confirm protected paths were not edited
    harness verify               verify the trace chain
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

from .check import changed_files, load_config, run, select
from .gate import evaluate
from .guard import check_protected
from .init import init
from .trace import Trace
from . import spec

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
    trace.append(check.name, check.cmd, "red", result.ok, result.exit_code, result.output)

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

    _emit({"ok": True, "check": check.name, "exit_code": result.exit_code}, args.json)
    if not args.json:
        print(f"{OK}  '{check.name}' failed as required (exit {result.exit_code}). Baseline recorded.")
    return 0


def cmd_run(cfg, args, cwd, trace) -> int:
    check = _resolve(cfg, args.name)
    result = run(check, cwd)
    trace.append(check.name, check.cmd, "run", result.ok, result.exit_code, result.output)
    _emit({"ok": result.ok, "check": check.name, "exit_code": result.exit_code}, args.json)
    if not args.json:
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


def cmd_gate(cfg, args, cwd, trace) -> int:
    check = _resolve(cfg, args.name)
    verdict = evaluate(trace, check, cwd)
    guard = (
        check_protected(cwd, cfg.protected, ignore=cfg.guard_ignore)
        if not args.skip_guard
        else {"ok": True, "reason": "guard skipped"}
    )
    ok = verdict.ok and guard["ok"]

    trace.append(check.name, check.cmd, "gate", ok, 0 if ok else 1, f"{verdict.reason} | guard: {guard['reason']}")

    if args.json:
        print(json.dumps({
            "ok": ok,
            "check": check.name,
            "chain_intact": verdict.chain_intact,
            "saw_red": verdict.saw_red,
            "green_after_red": verdict.green_after_red,
            "currently_green": verdict.currently_green,
            "protected_ok": guard["ok"],
            "reason": verdict.reason if not verdict.ok else guard["reason"],
        }))
    else:
        mark = lambda b: "yes" if b else "no "  # noqa: E731
        print(f"check              {check.name}")
        print(f"  chain intact     {mark(verdict.chain_intact)}")
        print(f"  saw red          {mark(verdict.saw_red)}")
        print(f"  green after red  {mark(verdict.green_after_red)}")
        print(f"  green now        {mark(verdict.currently_green)}")
        print(f"  tests untouched  {mark(guard['ok'])}")
        print()
        print(f"{OK if ok else NO}  {verdict.reason if not verdict.ok else guard['reason']}")
    return 0 if ok else 1


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
    result = init(cwd, args.project)

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
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness", description="Prove the work, don't trust the claim.")
    parser.add_argument("--config", default="checks.toml", help="path to checks.toml")
    parser.add_argument("--cwd", default=".", help="project directory")
    parser.add_argument("--json", action="store_true", help="machine-readable output")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p_select = sub.add_parser("select")
    p_select.add_argument("--base", help="git ref to diff against, e.g. main")
    for name in ("red", "run", "gate"):
        p = sub.add_parser(name)
        p.add_argument("name")
        if name == "gate":
            p.add_argument("--skip-guard", action="store_true")
    sub.add_parser("guard")
    sub.add_parser("verify")
    p_log = sub.add_parser("log")
    p_log.add_argument("name", nargs="?")

    p_spec = sub.add_parser("spec")
    spec_sub = p_spec.add_subparsers(dest="spec_action", required=True)
    spec_sub.add_parser("list")
    spec_sub.add_parser("coverage")
    spec_sub.add_parser("sync")
    spec_sub.add_parser("history")
    p_amend = spec_sub.add_parser("amend")
    p_amend.add_argument("id", help="requirement id")
    p_amend.add_argument("--reason", required=True, help="why it changed")
    p_amend.add_argument("--on", help="date, defaults to today")
    p_bless = spec_sub.add_parser("bless")
    p_bless.add_argument("id", nargs="?", help="requirement id, or omit for all")
    p_bless.add_argument("--reason", help="required when re-blessing a changed requirement")

    p_init = sub.add_parser("init")
    p_init.add_argument("--project", help="project name (defaults to the directory name)")

    args = parser.parse_args(argv)
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
