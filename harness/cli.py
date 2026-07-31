"""Command line interface.

    harness list                 show every check
    harness red <name>           run a check and require it to FAIL
    harness run <name>           run a check and record the result
    harness gate <name>          decide whether the work is done
    harness guard                confirm protected paths were not edited
    harness verify               verify the trace chain
    harness log [name]           print recorded evidence
    harness spec list            requirements and how each is settled
    harness spec coverage        fail if a requirement has no check and no gate
    harness spec sync            fail if a requirement changed after review
    harness spec bless [id]      record that a check matches the spec as written
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .check import load_config, run
from .gate import evaluate
from .guard import check_protected
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
                    "fingerprint": r.fingerprint,
                }
                for r in reqs
            ], indent=2))
            return 0
        print(f"spec: {spec_path}\n")
        for r in reqs:
            how = {"check": f"check {r.check}", "human": f"gate {r.gate}",
                   "removed": "removed", "nothing": "NOTHING - unsettled"}[r.settled_by]
            print(f"  {r.id:<14} {r.fingerprint}  {how}")
            print(f"  {'':<14} {r.title}")
        return 0

    if action == "coverage":
        result = spec.coverage(reqs, set(cfg.checks))
        _emit(result, args.json)
        if not args.json:
            print(f"{result['total']} live requirements: "
                  f"{result['by_check']} by check, {result['by_human']} by human gate")
            print(f"{OK if result['ok'] else NO}  {result['reason']}")
        return 0 if result["ok"] else 1

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
            if spec.bless(cfg_path, r.check, r.fingerprint):
                print(f"blessed  {r.id:<14} {r.fingerprint}  -> check {r.check}")
            else:
                print(f"skipped  {r.id:<14} check '{r.check}' not found in {args.config}", file=sys.stderr)
        print("\nYou have stated that these checks match the spec as written.")
        return 0

    return 2


COMMANDS = {
    "list": cmd_list,
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
    p_bless = spec_sub.add_parser("bless")
    p_bless.add_argument("id", nargs="?", help="requirement id, or omit for all")

    args = parser.parse_args(argv)
    cwd = Path(args.cwd).resolve()

    try:
        cfg = load_config(Path(args.config) if Path(args.config).is_absolute() else cwd / args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    trace = Trace(cfg.project)
    return COMMANDS[args.command](cfg, args, cwd, trace)


if __name__ == "__main__":
    raise SystemExit(main())
