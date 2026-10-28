import sys, os
sys.path.insert(0, "backend")

import pytest
from app.debugger.gdb_engine import GdbDebugEngine
from app.debugger.config import DebuggerConfig
from app.services.session_manager import SessionManager
from app.models.event_model import DebugMode

GCC = os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
GDB = os.environ.get("GDB_PATH", os.path.join(os.path.dirname(GCC), "gdb.exe"))
SKIP = not os.path.isfile(GCC) or not os.path.isfile(GDB)


@pytest.fixture
def engine():
    return GdbDebugEngine(DebuggerConfig())


# === GdbDebugEngine 全链路 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_engine_start_step_continue_stop(engine):
    code = "int main(void){\n  int a=1;\n  int b=2;\n  int c=a+b;\n  return c;\n}"
    r = engine.start(code, "step", [2])
    assert r.success, r.error_message
    sid = r.session_id
    assert r.snapshot is not None
    assert r.stop is not None
    assert r.stop.line == 2

    r2 = engine.step(sid)
    assert r2.success
    assert r2.stop.line == 3

    r3 = engine.step(sid)
    assert r3.success
    assert r3.stop.line == 4

    r4 = engine.continue_execution(sid)
    assert r4.success
    assert "exited" in r4.stop.reason

    r5 = engine.stop(sid)
    assert r5.success
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_engine_without_breakpoints_stops_at_main(engine):
    code = "int main(void){\n  int a=1;\n  int b=2;\n  return a+b;\n}"
    result = engine.start(code, "step", [])
    assert result.success, result.error_message
    assert result.status == "paused"
    assert result.stop.function == "main"
    assert result.stop.line > 0
    next_result = engine.step(result.session_id)
    assert next_result.success
    assert next_result.status == "paused"
    engine.stop(result.session_id)


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_full_mode_starts_at_main_and_can_be_stopped(engine):
    code = "int main(void){\n  int i=0;\n  while(i<100){i++;}\n  return i;\n}"
    result = engine.start(code, "full", [])
    assert result.success, result.error_message
    assert result.status == "paused"
    assert result.stop.function == "main"
    stopped = engine.stop(result.session_id)
    assert stopped.success


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_engine_step_into(engine):
    code = "int add(int a,int b){return a+b;}\nint main(void){\n  int r=add(3,4);\n  return r;\n}"
    r = engine.start(code, "step", [3])
    assert r.success
    sid = r.session_id

    r2 = engine.step_into(sid)
    assert r2.success
    assert r2.stop.function == "add"
    engine.stop(sid)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_engine_continue_to_breakpoint(engine):
    code = "int main(void){\n  int x=0;\n  x=x+1;\n  x=x+2;\n  x=x+3;\n  return x;\n}"
    r = engine.start(code, "breakpoint", [2, 4])
    assert r.success
    sid = r.session_id
    assert r.stop.line == 2

    r2 = engine.continue_execution(sid)
    assert r2.success
    assert r2.stop.line == 4
    engine.stop(sid)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_engine_compile_error(engine):
    code = "int main(void){return 0;"
    r = engine.start(code, "step", [])
    assert not r.success
    assert r.error_code == "COMPILE_ERROR"
    assert len(r.diagnostics) > 0
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_engine_get_snapshots(engine):
    code = "int main(void){\n  int a=1;\n  int b=2;\n  return a+b;\n}"
    r = engine.start(code, "step", [2])
    sid = r.session_id
    engine.step(sid)
    snaps = engine.get_snapshots(sid)
    assert len(snaps) == 2
    assert all(s.engine == "gdb" for s in snaps)
    assert all(s.schema_version == 2 for s in snaps)
    engine.stop(sid)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_exit_snapshot_does_not_fabricate_unknown_frame(engine):
    code = "int main(void){\n  return 0;\n}"
    started = engine.start(code, "step", [])
    assert started.success, started.error_message
    exited = engine.continue_execution(started.session_id)
    assert exited.success
    assert exited.snapshot is not None
    assert all(frame.function != "??" for frame in exited.snapshot.stack_frames)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_malloc_pointer_and_block_are_rendered_separately(engine):
    code = (
        "#include <stdlib.h>\n"
        "int main(void) {\n"
        "  int *p = malloc(5 * sizeof(int));\n"
        "  p[0] = 99;\n"
        "  return 0;\n"
        "}\n"
    )
    started = engine.start(code, "step", [])
    assert started.success, started.error_message
    assert engine.step(started.session_id).success
    assigned = engine.step(started.session_id)
    assert assigned.success
    snapshot = assigned.snapshot
    assert snapshot is not None
    pointer = next(
        node for node in snapshot.stack_frames[0].variable_tree if node.name == "p"
    )
    assert pointer.kind == "pointer"
    assert pointer.children == []
    assert len(snapshot.heap_objects) == 1
    assert snapshot.heap_objects[0].size == 5 * 4
    assert snapshot.heap_objects[0].element_type == "int"
    assert len(snapshot.heap_objects[0].elements) == 5
    assert snapshot.heap_objects[0].elements[0].value == "99"
    assert snapshot.pointers[0].name == "p"
    engine.stop(started.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_stack_pointer_does_not_create_heap_object(engine):
    code = (
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "  int x = 42;\n"
        "  int *p = &x;\n"
        "  printf(\"%d\\n\", *p);\n"
        "  return 0;\n"
        "}\n"
    )
    result = engine.start(code, "full", [])
    assert result.success, result.error_message
    assert result.snapshot is not None
    assert result.snapshot.heap_objects == []
    engine.stop(result.session_id)
    engine.shutdown()


# === 并发会话独立 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def engine_concurrent_sessions(engine):
    code = "int main(void){\n  int x=42;\n  return x;\n}"
    r1 = engine.start(code, "step", [2])
    r2 = engine.start(code, "step", [2])
    assert r1.success and r2.success
    assert r1.session_id != r2.session_id

    s1 = engine.step(r1.session_id)
    s2 = engine.step(r2.session_id)
    assert s1.success and s2.success

    engine.stop(r1.session_id)
    engine.stop(r2.session_id)
    engine.shutdown()


# === 资源清理 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_engine_shutdown_cleans_all(engine):
    code = "int main(void){\n  int x=1;\n  return x;\n}"
    r1 = engine.start(code, "step", [2])
    r2 = engine.start(code, "step", [2])
    assert r1.success and r2.success
    engine.shutdown()
    assert len(engine._sessions) == 0


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_engine_stop_preserves_snapshots(engine):
    code = "int main(void){\n  int a=1;\n  int b=2;\n  return a+b;\n}"
    r = engine.start(code, "step", [2])
    sid = r.session_id
    engine.step(sid)
    snaps_before = engine.get_snapshots(sid)
    engine.stop(sid)
    assert len(snaps_before) == 2
    engine.shutdown()


# === 引擎开关 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_session_manager_gdb_engine():
    sm = SessionManager()
    code = "int main(void){\n  int x=42;\n  return x;\n}"
    r = sm.start_debug(code, DebugMode.STEP, [2], engine="gdb")
    assert r.success, r.error_message
    assert r.session_id is not None

    r2 = sm.step(r.session_id)
    assert r2.success

    r3 = sm.stop(r.session_id)
    assert r3.success
    sm.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_session_manager_step_into_gdb():
    sm = SessionManager()
    code = "int add(int a,int b){return a+b;}\nint main(void){\n  int r=add(3,4);\n  return r;\n}"
    r = sm.start_debug(code, DebugMode.STEP, [3], engine="gdb")
    assert r.success
    r2 = sm.step_into(r.session_id)
    assert r2.success
    sm.stop(r.session_id)
    sm.shutdown()
