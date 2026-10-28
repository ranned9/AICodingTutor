from app.models.event_model import MemoryEvent, DebugMode, SessionStatus


def test_memory_event_values():
    assert MemoryEvent.NONE.value == "none"
    assert MemoryEvent.MALLOC.value == "malloc"
    assert MemoryEvent.FREE.value == "free"
    assert MemoryEvent.FUNCTION_CALL.value == "function_call"
    assert MemoryEvent.FUNCTION_RETURN.value == "function_return"


def test_debug_mode_values():
    assert DebugMode.STEP.value == "step"
    assert DebugMode.BREAKPOINT.value == "breakpoint"
    assert DebugMode.FULL.value == "full"


def test_session_status_values():
    assert SessionStatus.IDLE.value == "idle"
    assert SessionStatus.RUNNING.value == "running"
    assert SessionStatus.COMPLETED.value == "completed"
    assert SessionStatus.FAILED.value == "failed"