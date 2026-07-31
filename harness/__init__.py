"""harness - prove the work, don't trust the claim."""

from .check import Check, CheckResult, Config, load_config, run
from .gate import GateResult, evaluate
from .guard import check_protected
from .spec import Requirement, coverage, parse_spec, sync
from .trace import Trace

__version__ = "0.2.0"

__all__ = [
    "Check",
    "CheckResult",
    "Config",
    "GateResult",
    "Requirement",
    "Trace",
    "check_protected",
    "coverage",
    "evaluate",
    "load_config",
    "parse_spec",
    "run",
    "sync",
]
