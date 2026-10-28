from enum import Enum


class MemoryEvent(str, Enum):
    NONE = "none"
    MALLOC = "malloc"
    FREE = "free"
    FUNCTION_CALL = "function_call"
    FUNCTION_RETURN = "function_return"


class DebugMode(str, Enum):
    STEP = "step"
    BREAKPOINT = "breakpoint"
    FULL = "full"


class SessionStatus(str, Enum):
    IDLE = "idle"
    VALIDATING = "validating"
    INSTRUMENTING = "instrumenting"
    COMPILING = "compiling"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"