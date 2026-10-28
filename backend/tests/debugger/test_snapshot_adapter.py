import sys
sys.path.insert(0, "backend")

from app.debugger.models import StopInfo, VariableNode
from app.debugger.snapshot_adapter import SnapshotAdapter
from app.models.snapshot_model import HeapObject, MemorySnapshot


def test_snapshot_adapter_basic():
    stop = StopInfo(reason="breakpoint-hit", function="main", line=10)
    frame_vars = [
        VariableNode(name="x", type="int", kind="scalar", value="42"),
    ]
    global_vars = [
        VariableNode(name="g_total", type="int", kind="scalar", value="4"),
    ]
    snap = SnapshotAdapter.to_snapshot(
        "sess1", 0, stop, frame_vars, global_vars
    )
    assert snap.session_id == "sess1"
    assert snap.step == 0
    assert snap.line == 10
    assert snap.engine == "gdb"
    assert snap.stop_reason == "breakpoint-hit"
    assert snap.schema_version == 2


def test_snapshot_adapter_variable_tree():
    stop = StopInfo(function="main", line=5)
    frame_vars = [
        VariableNode(
            name="arr", type="int [3]", kind="array", value="{1, 2, 3}",
            children=[
                VariableNode(name="[0]", value="1"),
                VariableNode(name="[1]", value="2"),
                VariableNode(name="[2]", value="3"),
            ],
        ),
    ]
    snap = SnapshotAdapter.to_snapshot("s1", 1, stop, frame_vars, [])
    assert len(snap.stack_frames) == 1
    frame = snap.stack_frames[0]
    assert len(frame.variable_tree) == 1
    tree = frame.variable_tree[0]
    assert tree.name == "arr"
    assert tree.kind == "array"
    assert len(tree.children) == 3
    assert tree.children[0].value == "1"


def test_snapshot_adapter_flat_locals():
    stop = StopInfo(function="main", line=5)
    frame_vars = [
        VariableNode(name="x", type="int", kind="scalar", value="10"),
        VariableNode(name="arr", type="int [3]", kind="array", value="{...}"),
    ]
    snap = SnapshotAdapter.to_snapshot("s1", 0, stop, frame_vars, [])
    frame = snap.stack_frames[0]
    assert len(frame.locals) == 1
    assert frame.locals[0].name == "x"
    assert frame.locals[0].value == "10"


def test_snapshot_adapter_exit():
    stop = StopInfo(reason="exited-normally", function="", line=0)
    snap = SnapshotAdapter.to_snapshot("s1", 5, stop, [], [])
    assert snap.is_complete is True
    assert snap.stop_reason == "exited-normally"


def test_snapshot_adapter_preserves_explicitly_empty_frames():
    stop = StopInfo(reason="exited-normally", function="??", line=0)
    snap = SnapshotAdapter.to_snapshot("s1", 6, stop, [], [], frames=[])
    assert snap.stack_frames == []


def test_heap_elements_convert_to_snapshot_nodes():
    element = VariableNode(name="[0]", type="int", value="99")
    model_element = SnapshotAdapter._to_node_model(element)
    snap = SnapshotAdapter.to_snapshot(
        "s1", 1, StopInfo(function="main", line=4), [], [],
        heap_objects=[
            HeapObject(address="0x1000", size=4, element_type="int",
                       elements=[model_element])
        ],
    )
    assert snap.heap_objects[0].elements[0].value == "99"
