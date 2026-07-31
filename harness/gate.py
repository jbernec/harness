"""The gate: reads the trace and decides. Nothing else may write this answer.

A check is satisfied only when all four hold:

  1. the chain is intact          - the evidence has not been edited
  2. it was observed RED          - a check never seen failing proves nothing
  3. it went GREEN after that RED - in that order, not the reverse
  4. it is GREEN right now        - re-run at decision time, so a later
                                    regression cannot hide behind old evidence

The work is not done because the agent says so. It is done because the log
says it was broken, then wasn't.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .check import Check, run
from .trace import Trace


@dataclass(frozen=True)
class GateResult:
    check: str
    ok: bool
    chain_intact: bool
    saw_red: bool
    green_after_red: bool
    currently_green: bool
    reason: str


def evaluate(trace: Trace, check: Check, cwd: Path) -> GateResult:
    chain = trace.verify()
    chain_intact = chain["ok"]

    saw_red = False
    green_after_red = False
    for row in trace.rows():
        # A check is identified by name AND command: editing the command to
        # something weaker makes it a different check, so old RED evidence
        # no longer applies to it.
        if row.get("check") != check.name or row.get("cmd") != check.cmd:
            continue
        if row.get("phase") not in ("red", "run"):
            continue
        if not row.get("ok"):
            saw_red = True
        elif saw_red:
            green_after_red = True

    currently_green = run(check, cwd).ok

    ok = chain_intact and saw_red and green_after_red and currently_green

    if not chain_intact:
        reason = f"trace chain broken at row {chain['broken_at']} ({chain['reason']}) - evidence cannot be trusted"
    elif not saw_red:
        reason = "no RED observation for this exact check - a check never seen failing proves nothing. Run `harness red` first."
    elif not green_after_red:
        reason = "observed RED but never GREEN afterward - not done yet"
    elif not currently_green:
        reason = "trace shows red->green but the check is RED right now - it regressed"
    else:
        reason = "red -> green in an intact chain, and still green now"

    return GateResult(
        check=check.name,
        ok=ok,
        chain_intact=chain_intact,
        saw_red=saw_red,
        green_after_red=green_after_red,
        currently_green=currently_green,
        reason=reason,
    )
