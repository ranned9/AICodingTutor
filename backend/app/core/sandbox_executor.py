import logging
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass

from app.api.response import ErrorCode

logger = logging.getLogger(__name__)

SANDBOX_CPU_LIMIT = 5
SANDBOX_MEMORY_LIMIT = 256
SANDBOX_TIME_LIMIT = 10
GCC_PATH = os.environ.get("GCC_PATH", "gcc")


@dataclass
class CompileResult:
    success: bool
    error_line: int | None = None
    error_desc: str | None = None
    executable_path: str | None = None


@dataclass
class ExecutionResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    error_code: ErrorCode = ErrorCode.SUCCESS
    error_message: str = ""


class SandboxExecutor:
    def __init__(
        self,
        cpu_limit: int = SANDBOX_CPU_LIMIT,
        memory_limit: int = SANDBOX_MEMORY_LIMIT,
        time_limit: int = SANDBOX_TIME_LIMIT,
    ):
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.time_limit = time_limit

    def _get_env_with_gcc_path(self) -> dict:
        env = os.environ.copy()
        gcc_dir = os.path.dirname(GCC_PATH)
        if gcc_dir and os.path.isdir(gcc_dir):
            sep = os.pathsep
            env["PATH"] = gcc_dir + sep + env.get("PATH", "")
        return env

    def compile(self, source_code: str) -> CompileResult:
        work_dir = tempfile.mkdtemp(prefix="sandbox_")
        source_path = os.path.join(work_dir, "program.c")
        exec_path = os.path.join(work_dir, "program.exe")

        with open(source_path, "w", encoding="utf-8") as f:
            f.write(source_code)

        env = self._get_env_with_gcc_path()
        try:
            result = subprocess.run(
                [GCC_PATH, "-g", "-O0", "-std=c99", "-w", "-o", exec_path, source_path],
                capture_output=True,
                text=True,

                errors="replace",
                timeout=self.cpu_limit,
                env=env,
            )
            if result.returncode != 0:
                error_line, error_desc = self._parse_compile_error(result.stderr)
                return CompileResult(success=False, error_line=error_line, error_desc=error_desc)
            return CompileResult(success=True, executable_path=exec_path)
        except subprocess.TimeoutExpired:
            return CompileResult(success=False, error_desc="编译超时")
        except FileNotFoundError:
            return CompileResult(success=False, error_desc="gcc编译器未找到")

    def execute(self, executable_path: str) -> ExecutionResult:
        env = self._get_env_with_gcc_path()
        try:
            result = subprocess.run(
                [executable_path],
                capture_output=True,
                text=True,

                errors="replace",
                timeout=self.time_limit,
                env=env,
            )
            if result.returncode == 0:
                return ExecutionResult(success=True, stdout=result.stdout, stderr=result.stderr, return_code=0)
            else:
                error_msg = f"程序运行异常，返回码: {result.returncode}"
                if result.returncode == 3221225477 or result.returncode == -1073741819:
                    error_msg = "程序发生段错误(访问了非法内存地址)，可能是野指针或越界访问"
                elif result.returncode == 3221225622 or result.returncode == -1073741571:
                    error_msg = "程序发生栈溢出"
                return ExecutionResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    return_code=result.returncode,
                    error_code=ErrorCode.RUNTIME_ERROR,
                    error_message=error_msg,
                )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                error_code=ErrorCode.SANDBOX_LIMIT,
                error_message="代码执行超时或资源超限，已被强制终止",
            )
        except Exception as e:
            logger.exception("执行异常: %s", e)
            return ExecutionResult(
                success=False,
                error_code=ErrorCode.RUNTIME_ERROR,
                error_message=f"执行异常: {str(e)}",
            )

    def compile_and_execute(self, source_code: str) -> tuple[CompileResult, ExecutionResult | None]:
        compile_result = self.compile(source_code)
        if not compile_result.success:
            return compile_result, None
        exec_result = self.execute(compile_result.executable_path)
        return compile_result, exec_result

    @staticmethod
    def _parse_compile_error(stderr: str) -> tuple[int | None, str]:
        for line in stderr.splitlines():
            if "error:" in line:
                parts = line.split(":")
                if len(parts) >= 3:
                    try:
                        error_line = int(parts[1])
                        error_desc = ":".join(parts[2:]).strip()
                        return error_line, error_desc
                    except ValueError:
                        pass
                return None, line.strip()
        return None, stderr.strip()[:200] if stderr else "未知编译错误"

    @staticmethod
    def cleanup(path: str):
        try:
            if os.path.isfile(path):
                os.remove(path)
            parent = os.path.dirname(path)
            if os.path.isdir(parent) and parent.startswith(tempfile.gettempdir()):
                import shutil
                shutil.rmtree(parent, ignore_errors=True)
        except Exception:
            pass