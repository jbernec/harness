"""Append-only, HMAC-chained evidence log.

The trace lives OUTSIDE the project directory and is keyed by a secret the
agent never sees. This is the difference between tamper-evident and
tamper-proof: a plain SHA-256 chain can be recomputed by anyone who can write
the file, so an agent with workspace access can forge a clean red->green
history. An HMAC chain cannot be forged without the key.
"""

from __future__ import annotations

import hmac
import json
import os
import time
from hashlib import sha256
from pathlib import Path

GENESIS = "GENESIS"


def harness_home() -> Path:
    """Root for all trace data. Override with HARNESS_HOME."""
    return Path(os.environ.get("HARNESS_HOME", Path.home() / ".harness"))


def key_path() -> Path:
    return harness_home() / "key"


def load_key() -> bytes:
    """Read the chain key, creating one on first use."""
    kp = key_path()
    if not kp.exists():
        kp.parent.mkdir(parents=True, exist_ok=True)
        kp.write_bytes(os.urandom(32))
        try:
            os.chmod(kp, 0o600)
        except OSError:
            pass
    return kp.read_bytes()


def _canonical(row: dict) -> bytes:
    body = {k: row[k] for k in ("ts", "check", "cmd", "phase", "ok", "exit_code", "evidence")}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def row_mac(row: dict, key: bytes) -> str:
    mac = hmac.new(key, digestmod=sha256)
    mac.update(row["prev"].encode())
    mac.update(_canonical(row))
    return mac.hexdigest()


class Trace:
    """One append-only chained log per project."""

    def __init__(self, project: str) -> None:
        self.project = project
        self.path = harness_home() / project / "trace.jsonl"
        self.key = load_key()

    def _rows_raw(self) -> tuple[list[dict], list[int]]:
        """Return parsed rows plus indices of lines that failed to parse.

        An unparseable line is evidence of tampering, not an absent row.
        Dropping it would let a whole entry be destroyed without breaking any
        link in the chain.
        """
        if not self.path.exists():
            return [], []
        rows, bad = [], []
        text = self.path.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        for i, line in enumerate(lines):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad.append(i)
        return rows, bad

    def rows(self) -> list[dict]:
        return self._rows_raw()[0]

    def head(self) -> str:
        rows = self.rows()
        return rows[-1]["mac"] if rows else GENESIS

    def append(self, check: str, cmd: str, phase: str, ok: bool, exit_code: int, evidence: str = "") -> dict:
        """Append one chained event. `phase` is 'red', 'run', 'gate',
        'void', or 'review'."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "check": check,
            "cmd": cmd,
            "phase": phase,
            "ok": ok,
            "exit_code": exit_code,
            "evidence": evidence[:2000],
            "prev": self.head(),
            "mac": "",
        }
        row["mac"] = row_mac(row, self.key)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return row

    def verify(self) -> dict:
        """Recompute the chain. Any edit, deletion, or reorder breaks it."""
        rows, bad = self._rows_raw()
        total = len(rows) + len(bad)
        if bad:
            return {"ok": False, "rows": total, "broken_at": bad[0], "reason": "unparseable row"}
        prev = GENESIS
        for i, row in enumerate(rows):
            if row.get("prev") != prev:
                return {"ok": False, "rows": total, "broken_at": i, "reason": "chain link mismatch"}
            expected = row_mac(row, self.key)
            if not hmac.compare_digest(expected, row.get("mac", "")):
                return {"ok": False, "rows": total, "broken_at": i, "reason": "bad MAC"}
            prev = row["mac"]
        return {"ok": True, "rows": total, "broken_at": None, "reason": "chain intact"}
