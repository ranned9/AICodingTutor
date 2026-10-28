from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from typing import Any

from ..config import DebuggerConfig
from ..gdb_session import GdbSession
from ..mi_transport import GdbExitedError, CommandTimeoutError
from .probe_c_source import get_probe_c_source
from .probe_report import ProbeReport, CapabilityResult, PathValidation


class ToolchainProbe:
    def __init__(self, config: DebuggerConfig | None = None):
        self._config = config or DebuggerConfig()

    def run(self, check_chinese_path: bool = False) -> ProbeReport:
        report = ProbeReport(
            compile_command=f"{self._config.compiler_path} {self._config.full_compile_flags} main.c -o program.exe",
            debugger_start_command=f"{self._config.debugger_path} --quiet --nx --interpreter=mi2",
        )

        if not os.path.isfile(self._config.compiler_path):
            report.failures.append(f"编译器未找到: {self._config.compiler_path}")
            report.conclusion = "failed"
            return report

        if not os.path.isfile(self._config.debugger_path):
            report.failures.append(f"调试器未找到: {self._config.debugger_path}")
            report.conclusion = "failed"
            return report

        report.compiler_version = self._get_version(self._config.compiler_path)
        report.debugger_version = self._get_version(self._config.debugger_path)

        work_dir = None
        try:
            work_dir = tempfile.mkdtemp(prefix="probe test ")
            source_path = os.path.join(work_dir, "probe.c")
            with open(source_path, "w", encoding="utf-8") as f:
                f.write(get_probe_c_source())

            compile_ok = self._compile(source_path, work_dir, report)
            if not compile_ok:
                report.conclusion = "failed"
                return report

            executable = os.path.join(work_dir, "program.exe")
            self._run_gdb_capabilities(executable, work_dir, source_path, report)

            report.path_validation.path_with_spaces = True
            report.path_validation.spaces_detail = f"成功在含空格目录运行: {work_dir}"

            if check_chinese_path:
                self._check_chinese_path(report)

            failed = [c for c in report.capability_results if not c.passed]
            if failed or report.failures:
                if failed:
                    report.failures.extend(f"能力项失败: {c.name}" for c in failed)
                report.conclusion = "failed"
            else:
                report.conclusion = "passed"

        except Exception as e:
            report.failures.append(f"探针异常: {e}")
            report.conclusion = "failed"
        finally:
            if work_dir:
                try:
                    shutil.rmtree(work_dir, ignore_errors=True)
                except Exception:
                    pass

        return report

    def _get_version(self, exe_path: str) -> str:
        try:
            env = os.environ.copy()
            env["PATH"] = os.path.dirname(exe_path) + os.pathsep + env.get("PATH", "")
            result = subprocess.run(
                [exe_path, "--version"], capture_output=True, text=True,
                timeout=10, env=env, errors="replace"
            )
            return result.stdout.strip().split("\n")[0]
        except Exception as e:
            return f"获取版本失败: {e}"

    def _compile(self, source_path: str, work_dir: str, report: ProbeReport) -> bool:
        executable = os.path.join(work_dir, "program.exe")
        env = os.environ.copy()
        env["PATH"] = os.path.dirname(self._config.compiler_path) + os.pathsep + env.get("PATH", "")
        try:
            result = subprocess.run(
                [self._config.compiler_path] + self._config.full_compile_flags.split()
                + [source_path, "-o", executable],
                capture_output=True, text=True, timeout=self._config.compile_timeout,
                env=env, errors="replace"
            )
            if result.returncode == 0 and os.path.isfile(executable):
                return True
            report.failures.append(f"编译失败: {result.stderr}")
            return False
        except subprocess.TimeoutExpired:
            report.failures.append("编译超时")
            return False
        except Exception as e:
            report.failures.append(f"编译异常: {e}")
            return False

    def _run_gdb_capabilities(
        self, executable: str, work_dir: str, source_path: str, report: ProbeReport
    ) -> None:
        session = GdbSession(self._config.debugger_path)
        try:
            session.launch(executable, work_dir, source_path)
            self._cap_mi2_start(report, session)
            self._cap_breakpoint(report, session, source_path)
            self._cap_run_and_step(report, session)
            self._cap_step_into_add(report, session)
            self._cap_local_vars(report, session)
            self._cap_global_vars(report, session)
            self._cap_array_children(report, session)
            self._cap_struct_children(report, session)
            self._cap_continue_and_exit(report, session)
        except GdbExitedError as e:
            report.failures.append(f"GDB退出: {e}")
        except CommandTimeoutError as e:
            report.failures.append(f"命令超时: {e}")
        except Exception as e:
            report.failures.append(f"调试异常: {e}")
        finally:
            try:
                session.terminate()
            except Exception:
                pass

    def _add_cap(self, report: ProbeReport, name: str, passed: bool,
                 req: str = "", resp: str = "", note: str = "") -> None:
        report.capability_results.append(
            CapabilityResult(name=name, passed=passed, raw_request=req, raw_response=resp, note=note)
        )

    def _cap_mi2_start(self, report: ProbeReport, session: GdbSession) -> None:
        passed = session.is_alive
        self._add_cap(report, "mi2_start", passed,
                      note="GDB MI2 已启动" if passed else "GDB 未存活")

    def _cap_breakpoint(self, report: ProbeReport, session: GdbSession, source_file: str) -> None:
        try:
            bp = session.insert_breakpoint(source_file, 21)
            passed = bp.verified
            self._add_cap(report, "breakpoint", passed,
                          req=f"-break-insert {source_file}:21",
                          note=f"resolved line={bp.line}, verified={bp.verified}")
        except Exception as e:
            self._add_cap(report, "breakpoint", False, note=str(e))

    def _cap_run_and_step(self, report: ProbeReport, session: GdbSession) -> None:
        try:
            stop = session.run_to_first_stop(timeout=15)
            passed = "breakpoint" in stop.reason or stop.line > 0
            self._add_cap(report, "run_to_breakpoint", passed,
                          note=f"reason={stop.reason}, line={stop.line}, func={stop.function}")
        except Exception as e:
            self._add_cap(report, "run_to_breakpoint", False, note=str(e))

    def _cap_step_into_add(self, report: ProbeReport, session: GdbSession) -> None:
        try:
            stop = session.step_into(timeout=10)
            passed = stop.function == "add"
            self._add_cap(report, "step_into", passed,
                          note=f"line={stop.line}, func={stop.function}")
            stop2 = session.step_over(timeout=10)
            self._add_cap(report, "step", stop2.line > 0,
                          note=f"line={stop2.line}, func={stop2.function}")
        except Exception as e:
            self._add_cap(report, "step_into", False, note=str(e))
            self._add_cap(report, "step", False, note=str(e))

    def _cap_local_vars(self, report: ProbeReport, session: GdbSession) -> None:
        try:
            variables = session.stack_list_variables()
            passed = len(variables) > 0
            var_names = [v.get("name", "") for v in variables]
            self._add_cap(report, "local_vars", passed,
                          note=f"variables={var_names}")

        except Exception as e:
            self._add_cap(report, "local_vars", False, note=str(e))

    def _cap_global_vars(self, report: ProbeReport, session: GdbSession) -> None:
        try:
            val = session.data_evaluate_expression("g_total")
            passed = val != ""
            self._add_cap(report, "global_vars", passed,
                          req='-data-evaluate-expression "g_total"',
                          resp=val, note=f"g_total={val}")
        except Exception as e:
            self._add_cap(report, "global_vars", False, note=str(e))

    def _cap_array_children(self, report: ProbeReport, session: GdbSession) -> None:
        try:
            vals = []
            for i in range(3):
                v = session.data_evaluate_expression(f"values[{i}]")
                vals.append(v)
            passed = all(v != "" for v in vals)
            self._add_cap(report, "array_children", passed,
                          note=f"values=[{', '.join(vals)}]")
        except Exception as e:
            self._add_cap(report, "array_children", False, note=str(e))

    def _cap_struct_children(self, report: ProbeReport, session: GdbSession) -> None:
        try:
            session.step_over(timeout=10)
            px = session.data_evaluate_expression("p.x")
            py = session.data_evaluate_expression("p.y")
            passed = px != "" and py != ""
            self._add_cap(report, "struct_children", passed,
                          note=f"p.x={px}, p.y={py}")
        except Exception as e:
            self._add_cap(report, "struct_children", False, note=str(e))

    def _cap_continue_and_exit(self, report: ProbeReport, session: GdbSession) -> None:
        try:
            stop = session.continue_to_stop(timeout=15)
            passed = "exited" in stop.reason or "exit" in stop.reason
            self._add_cap(report, "normal_exit", passed,
                          note=f"reason={stop.reason}, exit_code={stop.exit_code}")
        except Exception as e:
            self._add_cap(report, "normal_exit", False, note=str(e))

    def _check_chinese_path(self, report: ProbeReport) -> None:
        chinese_dir = None
        try:
            parent = tempfile.gettempdir()
            chinese_dir = os.path.join(parent, "探针测试 目录")
            os.makedirs(chinese_dir, exist_ok=True)
            source_path = os.path.join(chinese_dir, "probe.c")
            with open(source_path, "w", encoding="utf-8") as f:
                f.write(get_probe_c_source())
            executable = os.path.join(chinese_dir, "program.exe")
            env = os.environ.copy()
            env["PATH"] = os.path.dirname(self._config.compiler_path) + os.pathsep + env.get("PATH", "")
            result = subprocess.run(
                [self._config.compiler_path] + self._config.full_compile_flags.split()
                + [source_path, "-o", executable],
                capture_output=True, text=True, timeout=self._config.compile_timeout,
                env=env, errors="replace"
            )
            if result.returncode == 0 and os.path.isfile(executable):
                report.path_validation.path_with_chinese = True
                report.path_validation.chinese_detail = f"中文路径编译成功: {chinese_dir}"
            else:
                report.path_validation.chinese_detail = f"中文路径编译失败: {result.stderr}"
        except Exception as e:
            report.path_validation.chinese_detail = f"中文路径测试异常: {e}"
        finally:
            if chinese_dir:
                shutil.rmtree(chinese_dir, ignore_errors=True)