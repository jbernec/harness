# spec.md - template

Copy this to your project root. Delete this header block.

**Rules, all five of them:**

1. Every requirement gets an ID. `R-014`, or `R-RISK-014` once you split by area.
2. **IDs never change and are never reused.** Old traces point at them.
3. Every requirement ends in either `check:` or `gate: human`. No third option.
4. Retiring a requirement means marking it `[REMOVED]`, not deleting it.
5. Changing or retiring a settled requirement needs an `amended:` line saying
   why. The old wording is in git; the reason is not.

Optional per requirement:

```
status: draft | agreed | implemented | superseded    (default: agreed)
amended: 2026-08-01  raised from 10% after the March drawdown
```

`status:` and `amended:` are not part of the fingerprint - recording that
something changed must not itself count as a change.

Write whatever prose you like around the requirements. Only the `### R-xxx`
headings are parsed; everything else is context for humans.

Then:

```bash
harness spec list        # what have I got?
harness spec coverage    # is anything unaccounted for?
harness spec bless       # I have reviewed these; record the fingerprints
harness spec sync        # has anything changed since I reviewed it?
harness spec history     # did anything change without saying why?
```

---

# ARIA - specification

## Objective

Beat VTI by at least 2% over a rolling 12 months, with maximum drawdown
under 15%.

One sentence, one number. Everything below exists to serve it. If a
requirement doesn't serve it, cut the requirement.

## Requirements

### R-001  Approved universe only
The agent may only trade instruments on the approved universe list. Anything
else is rejected before it reaches the broker, not logged and allowed.

check: no_trades_outside_universe

### R-002  Position limit
No single position may exceed 20% of book value at the moment of order
submission.

amended: 2026-03-02  raised from 10% - see decisions.md D-014
status: implemented
check: position_limit

### R-003  Drawdown kill switch
If drawdown from peak exceeds 15%, trading halts. Resuming is a human
action. The system may never resume itself.

check: kill_switch

### R-004  Deterministic replay
Given identical market data, the strategy produces identical orders. Two
runs, byte-identical output.

check: determinism

### R-005  Paper trading until deliberately released
Live broker credentials are unreachable while this requirement stands.
Removing it is a deliberate, logged act.

check: paper_before_live

### R-006  Beats the benchmark on unseen data
Measured once, on held-out data, after the strategy is frozen.

check: beats_vti_holdout

### R-009  Orders are well-formed
Every generated order has a valid side, quantity, symbol and type before it
leaves the system. Malformed orders are rejected, not repaired.

check: order_validity

### R-007  The strategy is sound
Whether the approach is *wise* - not whether it is implemented correctly.
No command settles this. It is mine to judge, and pretending otherwise
would be the most expensive kind of lie the harness could tell.

gate: human

### R-008  Position sizing by fixed fractional rule  [REMOVED]
amended: 2026-03-02  replaced by volatility-targeted sizing, see decisions.md D-014
Kept so older traces referencing R-008 still resolve.

## Notes on the human gates

R-007 is not a gap in the harness. It is the harness being honest about
its edge. A green run means the machinery does what it was told - it says
nothing about whether being told that was a good idea.
