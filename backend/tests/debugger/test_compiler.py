import sys, os, tempfile, shutil
sys.path.insert(0, "backend")

import pytest
from app.debugger.compiler import Compiler
from app.debugger.config import DebuggerConfig


@pytest.fixture
def work_dir():
    d = tempfile.mkdtemp(prefix="test compile ")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def compiler():
    gcc = os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
    if not os.path.isfile(gcc):
        pytest.skip("GCC not found")
    return Compiler(DebuggerConfig())


def test_compile_valid_code(compiler, work_dir):
    code = 'int main(void) { return 0; }'
    result = compiler.compile(code, work_dir, "test1")
    assert result.success
    assert os.path.isfile(result.executable)
    assert result.duration_ms >= 0


def test_compile_syntax_error(compiler, work_dir):
    code = 'int main(void) { return 0;'
    result = compiler.compile(code, work_dir, "test2")
    assert not result.success
    assert len(result.diagnostics) > 0
    assert any(d.severity == "error" for d in result.diagnostics)


def test_compile_missing_compiler(work_dir):
    config = DebuggerConfig()
    config.compiler_path = "/nonexistent/gcc.exe"
    c = Compiler(config)
    result = c.compile('int main(void){return 0;}', work_dir, "test3")
    assert not result.success
    assert "未找到" in result.diagnostics[0].message


def test_compile_diagnostic_parsing(compiler, work_dir):
    code = 'int main(void) {\n  int x = ;\n  return 0;\n}'
    result = compiler.compile(code, work_dir, "test4")
    assert not result.success
    assert len(result.diagnostics) > 0
    assert any(d.severity == "error" for d in result.diagnostics)


def test_parse_windows_drive_path_diagnostic():
    diagnostics = Compiler._parse_stderr(
        r"D:\workspace\main.c:12:7: error: expected expression"
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].file == r"D:\workspace\main.c"
    assert diagnostics[0].line == 12
    assert diagnostics[0].column == 7
