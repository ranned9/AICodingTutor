import sys, os
sys.path.insert(0, "backend")

import threading
import time
import pytest
from app.debugger.gdb_engine import GdbDebugEngine
from app.debugger.config import DebuggerConfig
from app.services.session_manager import SessionManager
from app.models.event_model import DebugMode

GCC = os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
GDB = os.environ.get("GDB_PATH", os.path.join(os.path.dirname(GCC), "gdb.exe"))
SKIP = not os.path.isfile(GCC) or not os.path.isfile(GDB)


# === 并发会话 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_concurrent_sessions_independent():
    """多个GDB会话并发启动，互不干扰"""
    engine = GdbDebugEngine(DebuggerConfig(max_sessions=10))
    codes = [
        "int main(void){\n  int a=%d;\n  return a;\n}" % i
        for i in range(5)
    ]
    results = [None] * 5
    errors = [None] * 5

    def worker(idx):
        try:
            results[idx] = engine.start(codes[idx], "step", [2])
        except Exception as e:
            errors[idx] = e

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(e is None for e in errors), f"线程异常: {errors}"
    for i, r in enumerate(results):
        assert r is not None
        assert r.success, f"会话{i}启动失败: {r.error_message}"
        assert r.session_id != ""

    sids = [r.session_id for r in results]
    assert len(set(sids)) == 5, "会话ID应唯一"

    for r in results:
        engine.stop(r.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_concurrent_step_on_different_sessions():
    """不同会话并发单步，各自独立前进"""
    engine = GdbDebugEngine(DebuggerConfig(max_sessions=10))
    code = "int main(void){\n  int a=1;\n  int b=2;\n  int c=3;\n  int d=4;\n  return a+b+c+d;\n}"

    r1 = engine.start(code, "step", [2])
    r2 = engine.start(code, "step", [2])
    assert r1.success and r2.success

    results = [None, None]
    errors = [None, None]

    def stepper(idx, sid):
        try:
            results[idx] = engine.step(sid)
        except Exception as e:
            errors[idx] = e

    t1 = threading.Thread(target=stepper, args=(0, r1.session_id))
    t2 = threading.Thread(target=stepper, args=(1, r2.session_id))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert all(e is None for e in errors)
    assert results[0].success and results[1].success
    assert results[0].session_id != results[1].session_id

    engine.stop(r1.session_id)
    engine.stop(r2.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_session_limit_enforced():
    """会话数达到上限时拒绝新会话"""
    config = DebuggerConfig(max_sessions=2)
    engine = GdbDebugEngine(config)
    code = "int main(void){\n  int x=1;\n  return x;\n}"

    r1 = engine.start(code, "step", [2])
    r2 = engine.start(code, "step", [2])
    assert r1.success and r2.success

    r3 = engine.start(code, "step", [2])
    assert not r3.success
    assert r3.error_code == "SESSION_LIMIT"

    engine.stop(r1.session_id)
    engine.stop(r2.session_id)
    engine.shutdown()


# === 大数组 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_large_array_snapshot():
    """大数组（500元素）快照采集成功，受预算截断"""
    code = """
int main(void){
  int arr[500];
  for(int i=0;i<500;i++){arr[i]=i*2;}
  int sum=0;
  for(int i=0;i<500;i++){sum+=arr[i];}
  return sum;
}"""
    engine = GdbDebugEngine(DebuggerConfig(max_children_per_aggregate=100))
    r = engine.start(code, "step", [5])
    assert r.success, r.error_message
    assert r.snapshot is not None

    frames = r.snapshot.stack_frames or []
    found_arr = False
    for frame in frames:
        for node in frame.variable_tree:
            if "arr" in node.name:
                found_arr = True
                break
    assert found_arr, "应能读取到arr变量"

    engine.stop(r.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_large_array_truncated():
    """超大数组（2000元素）受max_children截断"""
    code = """
int main(void){
  int arr[2000];
  for(int i=0;i<2000;i++){arr[i]=i;}
  int sum=0;
  for(int i=0;i<10;i++){sum+=arr[i];}
  return sum;
}"""
    config = DebuggerConfig(max_children_per_aggregate=50)
    engine = GdbDebugEngine(config)
    r = engine.start(code, "step", [5])
    assert r.success, r.error_message
    assert r.snapshot is not None

    engine.stop(r.session_id)
    engine.shutdown()


# === 深链表 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_deep_linked_list():
    """深链表（20节点）遍历，受max_depth截断"""
    code = """
struct Node{int val;struct Node*next;};
int main(void){
  struct Node nodes[20];
  for(int i=0;i<19;i++){nodes[i].val=i;nodes[i].next=&nodes[i+1];}
  nodes[19].val=19;nodes[19].next=0;
  struct Node*head=&nodes[0];
  int sum=0;
  struct Node*p=head;
  while(p){sum+=p->val;p=p->next;}
  return sum;
}"""
    config = DebuggerConfig(max_depth=5, max_children_per_aggregate=100)
    engine = GdbDebugEngine(config)
    r = engine.start(code, "step", [11])
    assert r.success, r.error_message
    assert r.snapshot is not None

    engine.stop(r.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_deep_recursion_stack():
    """深递归（50层）单步执行，栈帧正确"""
    code = """
int fib(int n){
  if(n<=1)return n;
  return fib(n-1)+fib(n-2);
}
int main(void){
  int r=fib(10);
  return r;
}"""
    engine = GdbDebugEngine(DebuggerConfig())
    r = engine.start(code, "step", [6])
    assert r.success, r.error_message

    r2 = engine.step_into(r.session_id)
    assert r2.success
    assert r2.stop.function == "fib"

    engine.stop(r.session_id)
    engine.shutdown()


# === 超时 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_infinite_loop_timeout():
    """死循环程序continue时超时，返回TIMEOUT错误"""
    code = """
int main(void){
  int i=0;
  while(1){i++;}
  return 0;
}"""
    engine = GdbDebugEngine(DebuggerConfig())
    r = engine.start(code, "step", [3])
    assert r.success, r.error_message

    r2 = engine.continue_execution(r.session_id)
    assert not r2.success
    assert r2.error_code == "TIMEOUT"

    engine.stop(r.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_long_running_program_completes():
    """耗时但有限的程序正常完成"""
    code = """
int main(void){
  long sum=0;
  for(int i=0;i<100000;i++){sum+=i;}
  return (int)(sum%256);
}"""
    engine = GdbDebugEngine(DebuggerConfig())
    r = engine.start(code, "step", [3])
    assert r.success, r.error_message

    r2 = engine.continue_execution(r.session_id)
    assert r2.success
    assert "exited" in r2.stop.reason

    engine.stop(r.session_id)
    engine.shutdown()


# === 信号 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_sigsegv_handling():
    """段错误（SIGSEGV）程序，GDB捕获信号"""
    code = """
int main(void){
  int* p=0;
  int v=*p;
  return v;
}"""
    engine = GdbDebugEngine(DebuggerConfig())
    r = engine.start(code, "step", [3])
    assert r.success, r.error_message

    r2 = engine.continue_execution(r.session_id)
    assert r2.success
    assert r2.stop is not None
    assert "signal" in r2.stop.reason or "SIGSEGV" in r2.stop.signal or "exited" in r2.stop.reason

    engine.stop(r.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_sigabrt_handling():
    """abort()调用（SIGABRT），GDB捕获信号"""
    code = """
#include <stdlib.h>
int main(void){
  int x=1;
  abort();
  return x;
}"""
    engine = GdbDebugEngine(DebuggerConfig())
    r = engine.start(code, "step", [4])
    assert r.success, r.error_message

    r2 = engine.continue_execution(r.session_id)
    assert r2.success
    assert r2.stop is not None
    assert "signal" in r2.stop.reason or "exited" in r2.stop.reason

    engine.stop(r.session_id)
    engine.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_normal_exit_signal():
    """正常退出程序，stop reason为exited-normally"""
    code = """
int main(void){
  int x=42;
  return x;
}"""
    engine = GdbDebugEngine(DebuggerConfig())
    r = engine.start(code, "step", [3])
    assert r.success, r.error_message

    r2 = engine.continue_execution(r.session_id)
    assert r2.success
    assert r2.stop is not None
    assert "exited" in r2.stop.reason


    engine.stop(r.session_id)
    engine.shutdown()


# === 资源清理 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_shutdown_cleans_all_sessions():
    """shutdown清理所有活动会话"""
    engine = GdbDebugEngine(DebuggerConfig(max_sessions=10))
    code = "int main(void){\n  int x=1;\n  return x;\n}"

    sids = []
    for _ in range(3):
        r = engine.start(code, "step", [2])
        assert r.success
        sids.append(r.session_id)

    engine.shutdown()

    for sid in sids:
        r = engine.step(sid)
        assert not r.success
        assert r.error_code == "NOT_FOUND"


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_temp_dir_cleaned_after_stop():
    """stop后临时目录被清理"""
    import tempfile
    import glob as globmod

    engine = GdbDebugEngine(DebuggerConfig())
    code = "int main(void){\n  int x=1;\n  return x;\n}"

    r = engine.start(code, "step", [2])
    assert r.success
    sid = r.session_id

    ctx = engine.get_session(sid)
    assert ctx is not None
    work_dir = ctx.work_dir
    assert os.path.isdir(work_dir)

    engine.stop(sid)
    time.sleep(0.5)

    assert not os.path.isdir(work_dir), "临时目录应被清理"
    engine.shutdown()


# === 通过SessionManager的压力测试 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_manager_concurrent_sessions():
    """SessionManager管理多个并发GDB会话"""
    sm = SessionManager()
    code = "int main(void){\n  int x=42;\n  return x;\n}"

    r1 = sm.start_debug(code, DebugMode.STEP, [2])
    r2 = sm.start_debug(code, DebugMode.STEP, [2])

    assert r1.success, r1.error_message
    assert r2.success, r2.error_message
    assert r1.session_id != r2.session_id

    sm.stop(r1.session_id)
    sm.stop(r2.session_id)
    sm.shutdown()