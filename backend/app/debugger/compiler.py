from __future__ import annotations
import os
import re
import subprocess
import time
from pathlib import Path

from .config import DebuggerConfig
from .models import CompileDiagnostic, CompileOutcome


_DIAG_RE = re.compile(
    r'^(?P<file>(?:[A-Za-z]:)?[^:\r\n]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*'
    r'(?P<severity>error|warning|note):\s*(?P<msg>.+)$'
)


class Compiler:
    def __init__(self, config: DebuggerConfig | None = None):
        self._config = config or DebuggerConfig()

    def compile(self, source_code: str, work_dir: str,
                session_id: str = "session") -> CompileOutcome:
        start = time.monotonic()
        source_path = os.path.join(work_dir, "main.c")
        executable = os.path.join(work_dir, f"program_{session_id}.exe")

        if not source_code.strip():
            return CompileOutcome(
                success=False,
                diagnostics=[CompileDiagnostic(severity="error", message="源代码为空")],
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        with open(source_path, "w", encoding="utf-8") as f:
            f.write(source_code)

        if not os.path.isfile(self._config.compiler_path):
            return CompileOutcome(
                success=False,
                diagnostics=[CompileDiagnostic(
                    severity="error",
                    message=f"编译器未找到: {self._config.compiler_path}"
                )],
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        env = os.environ.copy()
        gcc_dir = os.path.dirname(self._config.compiler_path)
        env["PATH"] = gcc_dir + os.pathsep + env.get("PATH", "")

        cmd = (
            [self._config.compiler_path]
            + self._config.full_compile_flags.split()
            + [source_path, os.path.join(os.path.dirname(__file__), "heap_tracker.c")]
            + [
                "-Wl,--wrap=malloc", "-Wl,--wrap=calloc",
                "-Wl,--wrap=realloc", "-Wl,--wrap=free",
                "-o", executable,
            ]
        )

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self._config.compile_timeout,
                env=env, errors="replace",
            )
        except subprocess.TimeoutExpired:
            return CompileOutcome(
                success=False, timed_out=True,
                diagnostics=[CompileDiagnostic(
                    severity="error", message="编译超时"
                )],
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as e:
            return CompileOutcome(
                success=False,
                diagnostics=[CompileDiagnostic(
                    severity="error", message=f"编译异常: {e}"
                )],
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        diagnostics = self._parse_stderr(result.stderr)
        duration_ms = int((time.monotonic() - start) * 1000)

        if result.returncode == 0 and os.path.isfile(executable):
            return CompileOutcome(
                success=True, executable=executable,
                diagnostics=diagnostics, duration_ms=duration_ms,
            )
        return CompileOutcome(
            success=False, executable="",
            diagnostics=diagnostics or [CompileDiagnostic(
                severity="error",
                message=f"编译失败，返回码: {result.returncode}"
            )],
            duration_ms=duration_ms,
        )

    @staticmethod
    def _parse_stderr(stderr: str) -> list[CompileDiagnostic]:
        diagnostics: list[CompileDiagnostic] = []
        for line in stderr.splitlines():
            m = _DIAG_RE.match(line.strip())
            if m:
                diagnostics.append(CompileDiagnostic(
                    severity=m.group("severity"),
                    message=m.group("msg"),
                    file=m.group("file"),
                    line=int(m.group("line")) if m.group("line") else None,
                    column=int(m.group("col")) if m.group("col") else None,
                ))
        return diagnostics
