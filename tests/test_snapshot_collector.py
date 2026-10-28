from app.core.snapshot_collector import SnapshotCollector
from app.models.event_model import MemoryEvent


def test_parse_empty_stdout():
    snapshots = SnapshotCollector.parse_stdout("", "test-session")
    assert snapshots == []


def test_parse_non_snap_lines_ignored():
    stdout = "Hello World\n__SNAP__:{\"step\":1,\"line\":1}\nSome output\n"
    snapshots = SnapshotCollector.parse_stdout(stdout, "test-session")
    assert len(snapshots) == 1
    assert snapshots[0].step == 1


def test_parse_single_snapshot():
    stdout = '__SNAP__:{"step":1,"line":5,"stack_frames":[{"function":"main","args":"","locals":[]}],"heap_objects":[],"globals":[]}\n'
    snapshots = SnapshotCollector.parse_stdout(stdout, "test-session")
    assert len(snapshots) == 1
    s = snapshots[0]
    assert s.step == 1
    assert s.line == 5
    assert s.session_id == "test-session"
    assert len(s.stack_frames) == 1
    assert s.stack_frames[0].function == "main"


def test_parse_multiple_snapshots():
    stdout = (
        '__SNAP__:{"step":1,"line":1,"stack_frames":[],"heap_objects":[],"globals":[]}\n'
        '__SNAP__:{"step":2,"line":2,"stack_frames":[],"heap_objects":[],"globals":[]}\n'
        '__SNAP__:{"step":3,"line":3,"stack_frames":[],"heap_objects":[],"globals":[]}\n'
    )
    snapshots = SnapshotCollector.parse_stdout(stdout, "test-session")
    assert len(snapshots) == 3
    assert snapshots[0].step == 1
    assert snapshots[1].step == 2
    assert snapshots[2].step == 3


def test_parse_heap_objects():
    stdout = '__SNAP__:{"step":1,"line":1,"stack_frames":[],"heap_objects":[{"address":"0x1000","size":20,"is_freed":false}],"globals":[]}\n'
    snapshots = SnapshotCollector.parse_stdout(stdout, "test-session")
    assert len(snapshots) == 1
    assert len(snapshots[0].heap_objects) == 1
    h = snapshots[0].heap_objects[0]
    assert h.address == "0x1000"
    assert h.size == 20
    assert h.is_freed is False


def test_parse_heap_freed():
    stdout = '__SNAP__:{"step":1,"line":1,"stack_frames":[],"heap_objects":[{"address":"0x2000","size":40,"is_freed":true}],"globals":[]}\n'
    snapshots = SnapshotCollector.parse_stdout(stdout, "test-session")
    assert len(snapshots[0].heap_objects) == 1
    assert snapshots[0].heap_objects[0].is_freed is True


def test_parse_invalid_json_skipped():
    stdout = '__SNAP__:INVALID JSON\n__SNAP__:{"step":1,"line":1,"stack_frames":[],"heap_objects":[],"globals":[]}\n'
    snapshots = SnapshotCollector.parse_stdout(stdout, "test-session")
    assert len(snapshots) == 1


def test_parse_globals():
    stdout = '__SNAP__:{"step":1,"line":1,"stack_frames":[],"heap_objects":[],"globals":[{"name":"g_count","type":"int","address":"0x4000","value":"3"}]}\n'
    snapshots = SnapshotCollector.parse_stdout(stdout, "test-session")
    assert len(snapshots[0].globals) == 1
    g = snapshots[0].globals[0]
    assert g.name == "g_count"
    assert g.type == "int"
    assert g.value == "3"