import sys, os
sys.path.insert(0, "backend")

import pytest
from app.services.session_manager import SessionManager
from app.models.event_model import DebugMode

GCC = os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
GDB = os.environ.get("GDB_PATH", os.path.join(os.path.dirname(GCC), "gdb.exe"))
SKIP = not os.path.isfile(GCC) or not os.path.isfile(GDB)


TEST_CASES = [
    {
        "name": "simple_return",
        "code": "int main(void){\n  int x=42;\n  return x;\n}",
        "breakpoints": [2],
    },
    {
        "name": "array_sum",
        "code": "int main(void){\n  int a[3]={10,20,30};\n  int sum=0;\n  for(int i=0;i<3;i++){sum+=a[i];}\n  return sum;\n}",
        "breakpoints": [3],
    },
    {
        "name": "struct_access",
        "code": "struct P{int x;int y;};int main(void){\n  struct P p={3,7};\n  return p.x+p.y;\n}",
        "breakpoints": [2],
    },
    {
        "name": "function_call",
        "code": "int add(int a,int b){return a+b;}\nint main(void){\n  int r=add(3,4);\n  return r;\n}",
        "breakpoints": [3],
    },
    {
        "name": "global_var",
        "code": "int g=99;int main(void){\n  return g;\n}",
        "breakpoints": [2],
    },
    {
        "name": "pointer_deref",
        "code": "int main(void){\n  int x=42;\n  int *p=&x;\n  return *p;\n}",
        "breakpoints": [3],
    },
]


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
@pytest.mark.parametrize("case", TEST_CASES, ids=[c["name"] for c in TEST_CASES])
def test_gdb_engine_produces_valid_snapshot(case):
    sm = SessionManager()
    try:
        r = sm.start_debug(case["code"], DebugMode.STEP, case["breakpoints"], engine="gdb")
        assert r.success, f"{case['name']}: {r.error_message}"
        assert r.session_id is not None
        assert len(r.snapshots) > 0
        snap = r.snapshots[0]
        assert snap.engine == "gdb"
        assert snap.schema_version == 2
        assert snap.line > 0
    finally:
        if r.success:
            sm.stop(r.session_id)
        sm.shutdown()



@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_step_into_endpoint_via_manager():
    sm = SessionManager()
    code = "int add(int a,int b){return a+b;}\nint main(void){\n  int r=add(3,4);\n  return r;\n}"
    try:
        r = sm.start_debug(code, DebugMode.STEP, [3], engine="gdb")
        assert r.success
        r2 = sm.step_into(r.session_id)
        assert r2.success
        assert r2.stop is not None
        assert r2.stop.function == "add"
    finally:
        if r.success:
            sm.stop(r.session_id)
        sm.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_unified_response_structure():
    sm = SessionManager()
    code = "int main(void){\n  int x=42;\n  return x;\n}"
    try:
        r = sm.start_debug(code, DebugMode.STEP, [2], engine="gdb")
        assert r.success
        assert hasattr(r, 'status')
        assert hasattr(r, 'stop')
        assert r.status == "paused"
        assert r.stop is not None
        assert r.stop.line == 2
    finally:
        if r.success:
            sm.stop(r.session_id)
        sm.shutdown()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_default_engine_is_gdb():
    sm = SessionManager()
    code = "int main(void){\n  int x=42;\n  return x;\n}"
    try:
        r = sm.start_debug(code, DebugMode.STEP, [2])
        assert r.success
        assert r.session_id is not None
        snap = r.snapshots[0]
        assert snap.engine == "gdb"
    finally:
        if r.success:
            sm.stop(r.session_id)
        sm.shutdown()