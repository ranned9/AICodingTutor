import sys, os, tempfile, shutil, subprocess
sys.path.insert(0, "backend")

import pytest
from app.debugger.config import DebuggerConfig
from app.debugger.compiler import Compiler
from app.debugger.gdb_session import GdbSession
from app.debugger.snapshot_adapter import SnapshotAdapter
from app.debugger.variable_reader import VariableReader
from app.debugger.models import StopInfo
from app.debugger.mi_transport import GdbExitedError, CommandTimeoutError


def _need_tools():
    gcc = os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
    gdb = os.environ.get("GDB_PATH", os.path.join(os.path.dirname(gcc), "gdb.exe"))
    return gcc, gdb


GCC_PATH, GDB_PATH = _need_tools()
SKIP = not os.path.isfile(GCC_PATH) or not os.path.isfile(GDB_PATH)


@pytest.fixture
def work_dir():
    d = tempfile.mkdtemp(prefix="integration test ")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def config():
    return DebuggerConfig()


def _compile_and_run(code, work_dir, config, session_id="test"):
    compiler = Compiler(config)
    outcome = compiler.compile(code, work_dir, session_id)
    assert outcome.success, f"Compile failed: {outcome.diagnostics}"
    return outcome.executable


def _mi_path(p):
    return '"' + p.replace('\\', '\\\\') + '"'


# === C 特性覆盖 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_array(work_dir, config):
    code = "int main(void){\n  int a[3]={10,20,30};\n  return a[0]+a[1]+a[2];\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        s.insert_breakpoint(os.path.join(work_dir, "main.c"), 3)
        s.run_to_first_stop(timeout=15)
        v0 = s.data_evaluate_expression("a[0]")
        v1 = s.data_evaluate_expression("a[1]")
        v2 = s.data_evaluate_expression("a[2]")
        assert v0 == "10"
        assert v1 == "20"
        assert v2 == "30"
    finally:
        s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_struct(work_dir, config):
    code = "struct P{int x;int y;};int main(void){\n  struct P p={3,7};\n  return p.x+p.y;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        s.insert_breakpoint(os.path.join(work_dir, "main.c"), 3)
        s.run_to_first_stop(timeout=15)
        assert s.data_evaluate_expression("p.x") == "3"
        assert s.data_evaluate_expression("p.y") == "7"
    finally:
        s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_pointer(work_dir, config):
    code = "int main(void){\n  int x=42;\n  int *p=&x;\n  return *p;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        s.insert_breakpoint(os.path.join(work_dir, "main.c"), 4)
        s.run_to_first_stop(timeout=15)
        assert s.data_evaluate_expression("x") == "42"
        assert s.data_evaluate_expression("*p") == "42"
    finally:
        s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_loop(work_dir, config):
    code = "int main(void){\n  int sum=0;\n  for(int i=0;i<5;i++){sum+=i;}\n  return sum;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        s.insert_breakpoint(os.path.join(work_dir, "main.c"), 4)
        s.run_to_first_stop(timeout=15)
        assert s.data_evaluate_expression("sum") == "10"
    finally:
        s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_global_variable(work_dir, config):
    code = "int g=99;int main(void){\n  return g;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        s.insert_breakpoint(os.path.join(work_dir, "main.c"), 2)
        s.run_to_first_stop(timeout=15)
        assert s.data_evaluate_expression("g") == "99"
    finally:
        s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_function_call_and_step_into(work_dir, config):
    code = "int add(int a,int b){return a+b;}\nint main(void){\n  int r=add(3,4);\n  return r;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        s.insert_breakpoint(os.path.join(work_dir, "main.c"), 3)
        s.run_to_first_stop(timeout=15)
        stop = s.step_into(timeout=10)
        assert stop.function == "add"
        assert s.data_evaluate_expression("a") == "3"
        assert s.data_evaluate_expression("b") == "4"
    finally:
        s.terminate()


# === 调试协议覆盖 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_continue_to_exit(work_dir, config):
    code = "int main(void){\n  return 0;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        s.insert_breakpoint(os.path.join(work_dir, "main.c"), 2)
        s.run_to_first_stop(timeout=15)
        stop = s.continue_to_stop(timeout=15)
        assert "exited" in stop.reason
    finally:
        s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_breakpoint_resolved_line(work_dir, config):
    code = "int main(void){\n  int x = 1;\n  return x;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        bp = s.insert_breakpoint(os.path.join(work_dir, "main.c"), 2)
        assert bp.verified
        assert bp.line == 2
    finally:
        s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_unresolved_breakpoint(work_dir, config):
    code = "int main(void){return 0;}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        bp = s.insert_breakpoint(os.path.join(work_dir, "main.c"), 999)
        assert not bp.verified
    finally:
        s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_consecutive_steps(work_dir, config):
    code = "int main(void){\n  int a=1;\n  int b=2;\n  int c=3;\n  return a+b+c;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        s.insert_breakpoint(os.path.join(work_dir, "main.c"), 2)
        s.run_to_first_stop(timeout=15)
        lines = []
        for _ in range(3):
            stop = s.step_over(timeout=10)
            lines.append(stop.line)
        assert len(lines) == 3
    finally:
        s.terminate()


# === 资源清理覆盖 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_process_cleanup(work_dir, config):
    code = "int main(void){\n  return 0;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    s.launch(exe, work_dir)
    s.insert_breakpoint(os.path.join(work_dir, "main.c"), 2)
    s.run_to_first_stop(timeout=15)
    s.terminate()
    assert not s.is_alive


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_temp_dir_cleanup(work_dir, config):
    code = "int main(void){\n  return 0;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    s.launch(exe, work_dir)
    s.terminate()
    assert os.path.exists(work_dir)


# === 编译错误覆盖 ===

def test_compile_error_diagnostics(work_dir, config):
    compiler = Compiler(config)
    if not os.path.isfile(GCC_PATH):
        pytest.skip("GCC not found")
    outcome = compiler.compile("int main(void){return 0;", work_dir, "err")
    assert not outcome.success
    assert len(outcome.diagnostics) > 0


# === SnapshotAdapter 集成 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_snapshot_from_gdb(work_dir, config):
    code = "int g=5;int main(void){\n  int x=10;\n  return x+g;\n}"
    exe = _compile_and_run(code, work_dir, config)
    s = GdbSession(GDB_PATH)
    try:
        s.launch(exe, work_dir)
        s.insert_breakpoint(os.path.join(work_dir, "main.c"), 3)
        stop = s.run_to_first_stop(timeout=15)
        variables = s.stack_list_variables()
        frame_vars = []
        from app.debugger.models import VariableNode
        for v in variables:
            name = v.get("name", "")
            val = v.get("value", "")
            frame_vars.append(VariableNode(name=name, value=val, kind="scalar"))
        global_vars = [
            VariableNode(name="g", value=s.data_evaluate_expression("g"), kind="scalar")
        ]
        snap = SnapshotAdapter.to_snapshot("s1", 0, stop, frame_vars, global_vars)
        assert snap.engine == "gdb"
        assert snap.schema_version == 2
        assert snap.line == 3
        assert snap.stop_reason == "breakpoint-hit"
    finally:
        s.terminate()