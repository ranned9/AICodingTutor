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
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"