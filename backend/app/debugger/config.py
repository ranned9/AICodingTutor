import os
import shutil
from dataclasses import dataclass, field
from typing import Any


def _default_compiler_path() -> str:
    env = os.environ.get("GCC_PATH")
    if env:
        return env
    if os.name == "nt":
        return r"D:\Dve-cpp\MinGW32\bin\gcc.exe"
    return shutil.which("gcc") or "gcc"


def _default_debugger_path() -> str:
    env = os.environ.get("GDB_PATH")
    if env:
        return env
    gcc_env = os.environ.get("GCC_PATH")
    if gcc_env:
        candidate = os.path.join(os.path.dirname(gcc_env), "gdb.exe" if os.name == "nt" else "gdb")
        if os.path.isfile(candidate):
            return candidate
    if os.name == "nt":
        return r"D:\Dve-cpp\MinGW32\bin\gdb.exe"
    return shutil.which("gdb") or "gdb"


@dataclass
class DebuggerConfig:
    compiler_path: str = field(default_factory=_default_compiler_path)
    debugger_path: str = field(default_factory=_default_debugger_path)
    c_standard: str = "c11"
    compile_flags: str = "-g3 -O0 -fno-inline"
    compile_timeout: int = 30
    exec_wait_timeout: int = 10
    max_depth: int = 5
    max_children_per_aggregate: int = 100
    max_vars_per_stop: int = 500
    frame_collect_soft_limit: float = 1.0
    session_ttl: int = 1800
    max_sessions: int = 50
    default_engine: str = "gdb"

    @property
    def full_compile_flags(self) -> str:
        return f"{self.compile_flags} -std={self.c_standard}"

    @property
    def platform(self) -> str:
        return "windows" if os.name == "nt" else "linux"

    def diagnose(self) -> dict[str, Any]:
        issues: list[str] = []
        compiler_ok = os.path.isfile(self.compiler_path)
        debugger_ok = os.path.isfile(self.debugger_path)

        if not compiler_ok:
            issues.append(f"编译器未找到: {self.compiler_path}")
        if not debugger_ok:
            issues.append(f"调试器未找到: {self.debugger_path}")

        return {
            "platform": self.platform,
            "compiler_path": self.compiler_path,
            "compiler_available": compiler_ok,
            "debugger_path": self.debugger_path,
            "debugger_available": debugger_ok,
            "c_standard": self.c_standard,
            "compile_flags": self.full_compile_flags,
            "default_engine": self.default_engine,
            "max_sessions": self.max_sessions,
            "session_ttl": self.session_ttl,
            "healthy": compiler_ok and debugger_ok,
            "issues": issues,
        }
