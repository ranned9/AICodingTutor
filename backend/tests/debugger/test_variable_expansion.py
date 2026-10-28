import sys, os, tempfile, shutil
sys.path.insert(0, "backend")

import pytest
from app.debugger.config import DebuggerConfig
from app.debugger.compiler import Compiler
from app.debugger.gdb_session import GdbSession
from app.debugger.variable_reader import VariableReader
from app.debugger.models import ExpansionBudget

GCC = os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
GDB = os.environ.get("GDB_PATH", os.path.join(os.path.dirname(GCC), "gdb.exe"))
SKIP = not os.path.isfile(GCC) or not os.path.isfile(GDB)


@pytest.fixture
def setup():
    work = tempfile.mkdtemp(prefix="var_exp_")
    config = DebuggerConfig()
    yield work, config
    shutil.rmtree(work, ignore_errors=True)


def _compile_and_stop(code, work, config, line):
    compiler = Compiler(config)
    outcome = compiler.compile(code, work, "test")
    assert outcome.success, outcome.diagnostics
    s = GdbSession(config.debugger_path)
    s.launch(outcome.executable, work)
    src = os.path.join(work, "main.c")
    s.insert_breakpoint(src, line)
    s.run_to_first_stop(timeout=15)
    return s


def _find_node(nodes, name):
    for n in nodes:
        if n.name == name:
            return n
    return None


# === 数组展开 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_array_expansion(setup):
    work, config = setup
    code = "int main(void){\n  int a[3]={10,20,30};\n  return a[0];\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    a = _find_node(nodes, "a")
    assert a is not None
    assert a.kind == "array"
    assert len(a.children) == 3
    assert a.children[0].value == "10"
    assert a.children[1].value == "20"
    assert a.children[2].value == "30"
    reader.cleanup_varobjs()
    s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_2d_array_expansion(setup):
    work, config = setup
    code = "int main(void){\n  int m[2][3]={{1,2,3},{4,5,6}};\n  return m[0][0];\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    m = _find_node(nodes, "m")
    assert m is not None
    assert m.kind == "array"
    assert len(m.children) == 2
    assert len(m.children[0].children) == 3
    assert m.children[0].children[0].value == "1"
    assert m.children[1].children[2].value == "6"
    reader.cleanup_varobjs()
    s.terminate()


# === 结构体展开 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_struct_expansion(setup):
    work, config = setup
    code = "struct P{int x;int y;};int main(void){\n  struct P p={3,7};\n  return p.x;\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    p = _find_node(nodes, "p")
    assert p is not None
    assert p.kind == "struct"
    assert len(p.children) == 2
    assert p.children[0].name == "x"
    assert p.children[0].value == "3"
    assert p.children[1].name == "y"
    assert p.children[1].value == "7"
    reader.cleanup_varobjs()
    s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_nested_struct_expansion(setup):
    work, config = setup
    code = "struct Inner{int a;int b;};struct Outer{struct Inner i;int c;};int main(void){\n  struct Outer o={{1,2},3};\n  return o.i.a;\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    o = _find_node(nodes, "o")
    assert o is not None
    assert o.kind == "struct"
    assert len(o.children) == 2
    inner = o.children[0]
    assert inner.kind == "struct"
    assert len(inner.children) == 2
    assert inner.children[0].value == "1"
    assert inner.children[1].value == "2"
    reader.cleanup_varobjs()
    s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_struct_array_expansion(setup):
    work, config = setup
    code = "struct P{int x;int y;};int main(void){\n  struct P ps[2]={{1,2},{3,4}};\n  return ps[0].x;\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    ps = _find_node(nodes, "ps")
    assert ps is not None
    assert ps.kind == "array"
    assert len(ps.children) == 2
    assert ps.children[0].kind == "struct"
    assert ps.children[0].children[0].value == "1"
    assert ps.children[1].children[1].value == "4"
    reader.cleanup_varobjs()
    s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_2d_array_expansion(setup):
    work, config = setup
    code = "int main(void){\n  int m[2][3]={{1,2,3},{4,5,6}};\n  return m[0][0];\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    m = _find_node(nodes, "m")
    assert m is not None
    assert m.kind == "array"
    assert len(m.children) == 2
    assert len(m.children[0].children) == 3
    assert m.children[0].children[0].value == "1"
    assert m.children[1].children[2].value == "6"
    reader.cleanup_varobjs()
    s.terminate()


# === 结构体展开 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_struct_expansion(setup):
    work, config = setup
    code = "struct P{int x;int y;};int main(void){\n  struct P p={3,7};\n  return p.x;\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    p = _find_node(nodes, "p")
    assert p is not None
    assert p.kind == "struct"
    assert len(p.children) == 2
    assert p.children[0].name == "x"
    assert p.children[0].value == "3"
    assert p.children[1].name == "y"
    assert p.children[1].value == "7"
    reader.cleanup_varobjs()
    s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_nested_struct_expansion(setup):
    work, config = setup
    code = "struct Inner{int a;int b;};struct Outer{struct Inner i;int c;};int main(void){\n  struct Outer o={{1,2},3};\n  return o.i.a;\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    o = _find_node(nodes, "o")
    assert o is not None
    assert o.kind == "struct"
    assert len(o.children) == 2
    inner = o.children[0]
    assert inner.kind == "struct"
    assert len(inner.children) == 2
    assert inner.children[0].value == "1"
    assert inner.children[1].value == "2"
    reader.cleanup_varobjs()
    s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_struct_array_expansion(setup):
    work, config = setup
    code = "struct P{int x;int y;};int main(void){\n  struct P ps[2]={{1,2},{3,4}};\n  return ps[0].x;\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    ps = _find_node(nodes, "ps")
    assert ps is not None
    assert ps.kind == "array"
    assert len(ps.children) == 2
    assert ps.children[0].kind == "struct"
    assert ps.children[0].children[0].value == "1"
    assert ps.children[1].children[1].value == "4"
    reader.cleanup_varobjs()
    s.terminate()


# === 指针展开 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_pointer_expansion(setup):
    work, config = setup
    code = "int main(void){\n  int x=42;\n  int *p=&x;\n  return *p;\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    p = _find_node(nodes, "p")
    assert p is not None
    assert p.kind == "pointer"
    assert len(p.children) >= 1
    reader.cleanup_varobjs()
    s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_null_pointer(setup):
    work, config = setup
    code = "int main(void){\n  int *p=0;\n  return 0;\n}"
    s = _compile_and_stop(code, work, config, 2)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    p = _find_node(nodes, "p")
    assert p is not None
    assert p.kind == "pointer"
    reader.cleanup_varobjs()
    s.terminate()


# === 循环检测 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_circular_linked_list(setup):
    work, config = setup
    code = """
struct Node{int val;struct Node*next;};
int main(void){
  struct Node a={1,0};
  struct Node b={2,&a};
  a.next=&b;
  return a.val;
}
"""
    s = _compile_and_stop(code, work, config, 6)
    reader = VariableReader(s, ExpansionBudget(max_depth=5))
    nodes = reader.read_frame()
    a = _find_node(nodes, "a")
    assert a is not None
    assert a.kind == "struct"
    reader.cleanup_varobjs()
    s.terminate()


# === 预算截断 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_large_array_truncation(setup):
    work, config = setup
    code = "int main(void){\n  int a[100];\n  for(int i=0;i<100;i++){a[i]=i;}\n  return a[0];\n}"
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s, ExpansionBudget(max_children_per_aggregate=10))
    nodes = reader.read_frame()
    a = _find_node(nodes, "a")
    assert a is not None
    assert len(a.children) <= 10
    reader.cleanup_varobjs()
    s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_deep_nesting_truncation(setup):
    work, config = setup
    code = """
struct L1{int v;};
struct L2{struct L1 l;};
struct L3{struct L2 l;};
struct L4{struct L3 l;};
struct L5{struct L4 l;};
struct L6{struct L5 l;};
int main(void){
  struct L6 deep={{{{{{42}}}}}};
  return deep.l.l.l.l.l.v;
}
"""
    s = _compile_and_stop(code, work, config, 8)
    reader = VariableReader(s, ExpansionBudget(max_depth=3))
    nodes = reader.read_frame()
    deep = _find_node(nodes, "deep")
    assert deep is not None
    node = deep
    depth = 0
    while node.children:
        node = node.children[0]
        depth += 1
        if depth > 10:
            break
    assert depth <= 4
    reader.cleanup_varobjs()
    s.terminate()


# === varobj 清理 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_varobj_cleanup_no_accumulation(setup):
    work, config = setup
    code = "int main(void){\n  int a[3]={10,20,30};\n  int b[2]={40,50};\n  return a[0]+b[0];\n}"
    s = _compile_and_stop(code, work, config, 3)
    for _ in range(3):
        reader = VariableReader(s)
        nodes = reader.read_frame()
        assert len(nodes) >= 2
        n_before = len(reader._varobj_names)
        reader.cleanup_varobjs()
        assert len(reader._varobj_names) == 0
    s.terminate()


# === 作用域 ===

@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_variable_out_of_scope(setup):
    work, config = setup
    code = """
int main(void){
  int x=1;
  {
    int y=2;
    x=x+y;
  }
  return x;
}
"""
    s = _compile_and_stop(code, work, config, 8)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    x = _find_node(nodes, "x")
    assert x is not None
    y = _find_node(nodes, "y")
    assert y is None
    reader.cleanup_varobjs()
    s.terminate()


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_recursive_call_same_var_different_frames(setup):
    work, config = setup
    code = """
int fact(int n){
  if(n<=1){return 1;}
  return n*fact(n-1);
}
int main(void){
  int r=fact(3);
  return r;
}
"""
    s = _compile_and_stop(code, work, config, 3)
    reader = VariableReader(s)
    nodes = reader.read_frame()
    n = _find_node(nodes, "n")
    assert n is not None
    assert n.value == "3"
    reader.cleanup_varobjs()
    s.terminate()