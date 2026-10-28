from app.core.event_detector import EventDetector
from app.models.event_model import MemoryEvent
from app.models.snapshot_model import MemorySnapshot, StackFrame, HeapObject


def _make_snapshot(step=1, line=1, frames=None, heap=None):
    return MemorySnapshot(
        session_id="test",
        step=step,
        line=line,
        stack_frames=frames or [],
        heap_objects=heap or [],
    )


def test_empty_snapshots():
    result = EventDetector.detect_and_label([], [])
    assert result == []


def test_first_snapshot_function_call():
    s1 = _make_snapshot(1, 1, frames=[StackFrame(function="main")])
    result = EventDetector.detect_and_label([s1], [])
    assert result[0].event == MemoryEvent.FUNCTION_CALL


def test_malloc_event_detected():
    s1 = _make_snapshot(1, 1, frames=[StackFrame(function="main")])
    s2 = _make_snapshot(2, 2, frames=[StackFrame(function="main")], heap=[HeapObject(address="0x1000", size=20)])
    result = EventDetector.detect_and_label([s1, s2], [])
    assert result[0].event == MemoryEvent.FUNCTION_CALL
    assert result[1].event == MemoryEvent.MALLOC


def test_free_event_detected():
    s1 = _make_snapshot(1, 1, frames=[StackFrame(function="main")], heap=[HeapObject(address="0x1000", size=20)])
    s2 = _make_snapshot(2, 2, frames=[StackFrame(function="main")], heap=[HeapObject(address="0x1000", size=20, is_freed=True)])
    result = EventDetector.detect_and_label([s1, s2], [])
    assert result[0].event == MemoryEvent.MALLOC
    assert result[1].event == MemoryEvent.FREE


def test_function_call_detected():
    s1 = _make_snapshot(1, 1, frames=[StackFrame(function="main")])
    s2 = _make_snapshot(2, 2, frames=[StackFrame(function="main"), StackFrame(function="add")])
    result = EventDetector.detect_and_label([s1, s2], [])
    assert result[0].event == MemoryEvent.FUNCTION_CALL
    assert result[1].event == MemoryEvent.FUNCTION_CALL


def test_function_return_detected():
    s1 = _make_snapshot(1, 1, frames=[StackFrame(function="main"), StackFrame(function="add")])
    s2 = _make_snapshot(2, 2, frames=[StackFrame(function="main")])
    result = EventDetector.detect_and_label([s1, s2], [])
    assert result[0].event == MemoryEvent.FUNCTION_CALL
    assert result[1].event == MemoryEvent.FUNCTION_RETURN


def test_none_event_when_no_change():
    s1 = _make_snapshot(1, 1, frames=[StackFrame(function="main")])
    s2 = _make_snapshot(2, 2, frames=[StackFrame(function="main")])
    result = EventDetector.detect_and_label([s1, s2], [])
    assert result[0].event == MemoryEvent.FUNCTION_CALL
    assert result[1].event == MemoryEvent.NONE


def test_malloc_takes_priority_over_call():
    s1 = _make_snapshot(1, 1, frames=[StackFrame(function="main")])
    s2 = _make_snapshot(2, 2, frames=[StackFrame(function="main"), StackFrame(function="f")], heap=[HeapObject(address="0x1000", size=4)])
    result = EventDetector.detect_and_label([s1, s2], [])
    assert result[0].event == MemoryEvent.FUNCTION_CALL
    assert result[1].event == MemoryEvent.MALLOC