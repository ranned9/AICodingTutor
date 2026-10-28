from dataclasses import dataclass, field
from typing import Any


@dataclass
class MIRecord:
    token: int | None = None
    kind: str = ""
    klass: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


class MIParseError(Exception):
    def __init__(self, raw: str, reason: str):
        self.raw = raw
        self.reason = reason
        super().__init__(f"MI parse error: {reason} (raw: {raw!r})")


@dataclass
class StopInfo:
    reason: str = ""
    thread_id: int | None = None
    frame_level: int = 0
    function: str = ""
    file: str = ""
    line: int = 0
    address: str = ""
    signal: str = ""
    exit_code: int | None = None


@dataclass
class ResolvedBreakpoint:
    number: int = 0
    file: str = ""
    line: int = 0
    verified: bool = True
    status: str = "resolved"
    address: str = ""

@dataclass
class CompileDiagnostic:
    severity: str = "error"
    message: str = ""
    file: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass
class CompileOutcome:
    success: bool = False
    executable: str = ""
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    duration_ms: int = 0
    timed_out: bool = False


@dataclass
class ExpansionBudget:
    max_depth: int = 5
    max_children_per_aggregate: int = 100
    max_vars_per_stop: int = 500
    soft_time_limit: float = 1.0


@dataclass
class VariableNode:
    name: str = ""
    type: str = ""
    kind: str = "scalar"
    value: str = ""
    address: str = ""
    children: list = field(default_factory=list)
    available: bool = True
    unavailable_reason: str = ""
    truncated: bool = False
    cycle: bool = False


@dataclass
class EngineResult:
    success: bool = False
    status: str = ""
    session_id: str = ""
    current_step: int = 0
    total_steps: int = 0
    stop: StopInfo | None = None
    snapshot: Any = None
    snapshots: list[Any] = field(default_factory=list)
    breakpoints: list[ResolvedBreakpoint] = field(default_factory=list)
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
