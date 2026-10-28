import sys, os
sys.path.insert(0, "backend")

import pytest
from app.debugger.config import DebuggerConfig

GCC = os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
GDB = os.environ.get("GDB_PATH", os.path.join(os.path.dirname(GCC), "gdb.exe"))
SKIP = not os.path.isfile(GCC) or not os.path.isfile(GDB)


def test_config_defaults():
    config = DebuggerConfig()
    assert config.c_standard == "c11"
    assert "-g3" in config.full_compile_flags
    assert "-O0" in config.full_compile_flags
    assert "-std=c11" in config.full_compile_flags
    assert config.default_engine == "gdb"
    assert config.max_sessions > 0
    assert config.session_ttl > 0


def test_config_platform_detection():
    config = DebuggerConfig()
    assert config.platform in ("windows", "linux")


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("GCC_PATH", "/custom/path/gcc")
    monkeypatch.setenv("GDB_PATH", "/custom/path/gdb")
    config = DebuggerConfig()
    assert config.compiler_path == "/custom/path/gcc"
    assert config.debugger_path == "/custom/path/gdb"


def test_config_diagnose_returns_structure():
    config = DebuggerConfig()
    diag = config.diagnose()
    assert "platform" in diag
    assert "compiler_path" in diag
    assert "compiler_available" in diag
    assert "debugger_path" in diag
    assert "debugger_available" in diag
    assert "healthy" in diag
    assert "issues" in diag
    assert isinstance(diag["issues"], list)


@pytest.mark.skipif(SKIP, reason="GCC/GDB not found")
def test_config_diagnose_healthy():
    config = DebuggerConfig()
    diag = config.diagnose()
    assert diag["compiler_available"] is True
    assert diag["debugger_available"] is True
    assert diag["healthy"] is True
    assert len(diag["issues"]) == 0


def test_config_diagnose_missing_toolchain():
    config = DebuggerConfig(
        compiler_path="/nonexistent/gcc",
        debugger_path="/nonexistent/gdb",
    )
    diag = config.diagnose()
    assert diag["compiler_available"] is False
    assert diag["debugger_available"] is False
    assert diag["healthy"] is False
    assert len(diag["issues"]) == 2