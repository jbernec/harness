"""harness - prove the work, don't trust the claim."""

from .check import Check, CheckResult, Config, load_config, run
from .gate import GateResult, evaluate
from .guard import check_protected
from .trace import Trace

__version__ = "0.1.0"

__all__ = [
    "Check",
    "CheckResult",
    "Config",
    "GateResult",
    "Trace",
    "check_protected",
    "evaluate",
    "load_config",
    "run",
]
