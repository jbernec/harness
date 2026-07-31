# decisions.md - template

Copy to your project root. Append only. Never edit an entry once written.

**When to add one:** you made a choice you would have to explain to someone
in six months. That's the whole trigger.

**Three lines each.** Date, what you chose, why. If it takes more, you're
writing a design doc — put that in `spec.md` and link to it.

**Superseding:** never delete or rewrite. Add a new entry, mark the old one
`SUPERSEDED by D-xxx`, and update the index. The wrong turn is often the
most useful thing in the file — it's the reason you won't take it twice.

---

# Decisions

## Active

- D-021  Postgres, not MongoDB
- D-019  Money stored as integer minor units
- D-014  Volatility-targeted position sizing

## Superseded

- D-008  → replaced by D-021

---

### D-008  2026-02-14  Use MongoDB
Flexible schema, moving fast, no migrations to slow us down.

SUPERSEDED by D-021.

### D-014  2026-04-02  Volatility-targeted position sizing
Fixed fractional sizing took the same risk in calm and violent markets.
Retires R-008, introduces R-012.

### D-019  2026-05-11  Money as integer minor units (kobo, cents)
Floats lost fractions on split payouts. Never floats for money, anywhere,
including in tests.

### D-021  2026-06-03  Postgres, not MongoDB
Payouts need real transactions. A double-payout bug in April traced back
to a non-atomic two-document update. Reverses D-008.
