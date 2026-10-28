import sys, os
sys.path.insert(0, "backend")

import threading
import time
import tempfile
import pytest
from app.debugger.gdb_engine import GdbDebugEngine
from app.debugger.config import DebuggerConfig
from app.debugger.compiler import Compiler
from app.services.session_manager import SessionManager
from app.models.event_model import DebugMode

GCC = os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
GDB = os.environ.get("GDB_PATH", os.path.join(os.path.dirname(GCC), "gdb.exe"))
SKIP = not os.path.isfile(GCC) or not os.path.isfile(GDB)


# === OS级隔离：独立进程 + 临时目录 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_gdb_runs_in_separate_process():
    """GDB在独立子进程中运行，与主进程隔离"""
    import subprocess
    engine = GdbDebugEngine(DebuggerConfig())
    code = "int main(void){\n  int x=1;\n  return x;\n}"

    r = engine.start(code, "step", [2])
    assert r.success

    ctx = engine.get_session(r.session_id)
    assert ctx is not None
    transport = ctx.gdb_session._transport
    assert transport._proc is not None
    assert transport._proc.poll() is None, "GDB进程应仍在运行"

    main_pid = os.getpid()
    gdb_pid = transport._proc.pid
    assert gdb_pid != main_pid, "GDB进程PID应不同于主进程"

    engine.stop(r.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_each_session_isolated_temp_dir():
    """每个会话使用独立的临时目录"""
    engine = GdbDebugEngine(DebuggerConfig(max_sessions=10))
    code = "int main(void){\n  int x=1;\n  return x;\n}"

    r1 = engine.start(code, "step", [2])
    r2 = engine.start(code, "step", [2])
    assert r1.success and r2.success

    ctx1 = engine.get_session(r1.session_id)
    ctx2 = engine.get_session(r2.session_id)
    assert ctx1.work_dir != ctx2.work_dir, "两个会话的临时目录应不同"
    assert os.path.isdir(ctx1.work_dir)
    assert os.path.isdir(ctx2.work_dir)

    engine.stop(r1.session_id)
    engine.stop(r2.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_no_source_modification():
    """GDB引擎不修改用户源码（不插桩）"""

    engine = GdbDebugEngine(DebuggerConfig())
    original = "int main(void){\n  int x=42;\n  return x;\n}"

    r = engine.start(original, "step", [2])
    assert r.success

    ctx = engine.get_session(r.session_id)
    with open(ctx.source_path, "r") as f:
        file_content = f.read()

    assert "SNAPSHOT" not in file_content, "源文件不应包含插桩标记"
    assert "snapshot" not in file_content.lower(), "源文件不应包含插桩代码"
    assert file_content.strip() == original.strip(), "源文件应与原始代码一致"

    engine.stop(r.session_id)
    engine.shutdown()


# === 资源限制 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_session_count_limit():
    """会话数不超过max_sessions"""
    config = DebuggerConfig(max_sessions=3)
    engine = GdbDebugEngine(config)
    code = "int main(void){\n  int x=1;\n  return x;\n}"

    sids = []
    for _ in range(3):
        r = engine.start(code, "step", [2])
        assert r.success
        sids.append(r.session_id)

    r4 = engine.start(code, "step", [2])
    assert not r4.success
    assert r4.error_code == "SESSION_LIMIT"

    engine.stop(sids[0])

    r5 = engine.start(code, "step", [2])
    assert r5.success, "释放一个会话后应能新建"

    for sid in sids[1:]:
        engine.stop(sid)
    engine.stop(r5.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_cleanup_releases_resources():
    """stop后GDB进程终止、临时目录删除"""
    engine = GdbDebugEngine(DebuggerConfig())
    code = "int main(void){\n  int x=1;\n  return x;\n}"

    r = engine.start(code, "step", [2])
    assert r.success

    ctx = engine.get_session(r.session_id)
    transport = ctx.gdb_session._transport
    gdb_pid = transport._proc.pid
    work_dir = ctx.work_dir

    engine.stop(r.session_id)
    time.sleep(1.0)

    assert transport._proc is None or transport._proc.poll() is not None, "GDB进程应已终止"
    assert not os.path.isdir(work_dir), "临时目录应已删除"
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_double_stop_safe():
    """对同一会话重复stop不抛异常"""
    engine = GdbDebugEngine(DebuggerConfig())
    code = "int main(void){\n  int x=1;\n  return x;\n}"

    r = engine.start(code, "step", [2])
    assert r.success

    engine.stop(r.session_id)
    r2 = engine.stop(r.session_id)
    assert not r2.success
    assert r2.error_code == "NOT_FOUND"
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_step_nonexistent_session():
    """对不存在的会话step返回NOT_FOUND"""
    engine = GdbDebugEngine(DebuggerConfig())
    r = engine.step("nonexistent_session_id")
    assert not r.success
    assert r.error_code == "NOT_FOUND"
    engine.shutdown()


# === 并发控制 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_concurrent_step_same_session_serialized():
    """同一会话并发step被串行化（不崩溃）"""
    engine = GdbDebugEngine(DebuggerConfig())
    code = "int main(void){\n  int a=1;\n  int b=2;\n  int c=3;\n  int d=4;\n  return a+b+c+d;\n}"

    r = engine.start(code, "step", [2])
    assert r.success
    sid = r.session_id

    results = []
    errors = []

    def worker():
        try:
            res = engine.step(sid)
            results.append(res)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"并发step不应抛异常: {errors}"
    assert all(r.success for r in results), "并发step应全部成功"

    engine.stop(sid)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_shutdown_idempotent():
    """shutdown可重复调用"""
    engine = GdbDebugEngine(DebuggerConfig())
    code = "int main(void){\n  int x=1;\n  return x;\n}"

    r = engine.start(code, "step", [2])
    assert r.success

    engine.shutdown()
    engine.shutdown()


# === 编译安全 ===

def test_compiler_rejects_empty_source():
    """空源码编译失败"""
    compiler = Compiler(DebuggerConfig())
    work_dir = tempfile.mkdtemp(prefix="test_compile_")
    outcome = compiler.compile("", work_dir, "test")
    assert not outcome.success
    import shutil
    shutil.rmtree(work_dir, ignore_errors=True)


def test_compiler_reports_syntax_error():
    """语法错误产生结构化诊断"""
    compiler = Compiler(DebuggerConfig())
    work_dir = tempfile.mkdtemp(prefix="test_compile_")
    bad_code = "int main(void){\n  int x=\n  return x;\n}"
    outcome = compiler.compile(bad_code, work_dir, "test")
    assert not outcome.success
    assert len(outcome.diagnostics) > 0
    assert outcome.diagnostics[0].severity == "error"
    import shutil
    shutil.rmtree(work_dir, ignore_errors=True)


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_compiler_no_user_flags():
    """编译器不接受用户自定义编译参数（由配置固定）"""
    config = DebuggerConfig()
    assert "-g3" in config.full_compile_flags
    assert "-O0" in config.full_compile_flags
    assert "std=" in config.full_compile_flags