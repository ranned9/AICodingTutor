from __future__ import annotations
import os
from typing import Any

from .mi_transport import MITransport, GdbExitedError, CommandTimeoutError
from .models import StopInfo, ResolvedBreakpoint, MIRecord


class GdbCommandError(RuntimeError):
    pass


class GdbSession:
    def __init__(self, gdb_path: str):
        self._transport = MITransport(gdb_path)
        self._source_path: str = ""

    @staticmethod
    def _mi_escape_path(path: str) -> str:
        escaped = path.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _command_error(record: MIRecord, command: str) -> None:
        if record.klass == "error":
            message = record.payload.get("msg", "GDB command failed")
            raise GdbCommandError(f"{command}: {message}")

    @property
    def is_alive(self) -> bool:
        return self._transport.is_alive

    def launch(self, executable: str, cwd: str, source_path: str = "") -> None:
        self._source_path = source_path
        self._transport.start(cwd=cwd)
        self._transport.command("-gdb-set pagination off", timeout=10)
        self._transport.command("-gdb-set confirm off", timeout=10)
        self._transport.command(f"-file-exec-and-symbols {self._mi_escape_path(executable)}", timeout=10)
        self._transport.command("-gdb-set print pretty on", timeout=10)

    def insert_breakpoint(self, file: str, line: int) -> ResolvedBreakpoint:
        location = self._mi_escape_path(f"{file}:{line}")
        rec = self._transport.command(
            f'-break-insert {location}', timeout=10
        )
        return self._breakpoint_from_record(rec, file, line)

    def insert_main_breakpoint(self) -> ResolvedBreakpoint:
        rec = self._transport.command("-break-insert -t main", timeout=10)
        return self._breakpoint_from_record(rec, "main", 0)

    @staticmethod
    def _breakpoint_from_record(rec: MIRecord, file: str, line: int) -> ResolvedBreakpoint:
        if rec.klass == "done":
            bkpt = rec.payload.get("bkpt", {})
            if isinstance(bkpt, dict):
                try:
                    number = int(str(bkpt.get("number", "0")).split(".", 1)[0])
                except ValueError:
                    number = 0
                try:
                    actual_line = int(bkpt.get("line", str(line)))
                except (ValueError, TypeError):
                    actual_line = line
                actual_file = bkpt.get("file", file)
                addr = bkpt.get("addr", "")
                return ResolvedBreakpoint(
                    number=number, file=actual_file, line=actual_line,
                    verified=True, status="resolved", address=addr
                )
        elif rec.klass == "error":
            msg = rec.payload.get("msg", "")
            if "No line" in msg or "not found" in msg:
                return ResolvedBreakpoint(file=file, line=line, verified=False, status="unresolved")
        return ResolvedBreakpoint(file=file, line=line, verified=False, status="unresolved")

    def delete_breakpoint(self, gdb_number: int) -> None:
        try:
            self._transport.command(f"-break-delete {gdb_number}", timeout=10)
        except (GdbExitedError, CommandTimeoutError):
            pass

    def _parse_stop(self, rec: MIRecord) -> StopInfo:
        payload = rec.payload
        reason = payload.get("reason", "")
        frame = payload.get("frame", {})
        if not isinstance(frame, dict):
            frame = {}
        signal = payload.get("signal", "")
        exit_code = None
        if "exit-code" in payload:
            try:
                exit_code = int(payload["exit-code"])
            except (ValueError, TypeError):
                pass
        thread_id = None
        if "thread-id" in payload:
            try:
                thread_id = int(payload["thread-id"])
            except (ValueError, TypeError):
                pass
        return StopInfo(
            reason=reason,
            thread_id=thread_id,
            function=frame.get("func", ""),
            file=frame.get("file", ""),
            line=int(frame.get("line", "0")) if frame.get("line") else 0,
            address=frame.get("addr", ""),
            signal=signal,
            exit_code=exit_code,
        )

    def run_to_first_stop(self, timeout: float = 10.0) -> StopInfo:
        rec = self._transport.command("-exec-run", timeout=min(timeout, 10.0))
        self._command_error(rec, "-exec-run")
        rec = self._transport.wait_for_stop(timeout=timeout)
        return self._parse_stop(rec)

    def step_over(self, timeout: float = 10.0) -> StopInfo:
        rec = self._transport.command("-exec-next", timeout=min(timeout, 10.0))
        self._command_error(rec, "-exec-next")
        rec = self._transport.wait_for_stop(timeout=timeout)
        return self._parse_stop(rec)

    def step_into(self, timeout: float = 10.0, source_path: str = "") -> StopInfo:
        rec = self._transport.command("-exec-step", timeout=min(timeout, 10.0))
        self._command_error(rec, "-exec-step")
        stop = self._parse_stop(self._transport.wait_for_stop(timeout=timeout))
        if not source_path:
            return stop

        # A source-level step should enter functions from this program, not libc
        # or other system libraries that happen to have debug symbols installed.
        hop_timeout = min(timeout, 2.0)
        for _ in range(6):
            if (self._same_source_file(stop.file, source_path)
                    or stop.reason != "end-stepping-range"):
                break
            rec = self._transport.command("-exec-finish", timeout=hop_timeout)
            self._command_error(rec, "-exec-finish")
            stop = self._parse_stop(self._transport.wait_for_stop(timeout=hop_timeout))
        return stop

    @staticmethod
    def _same_source_file(frame_file: str, source_path: str) -> bool:
        if not frame_file:
            return False
        frame_path = frame_file if os.path.isabs(frame_file) else os.path.join(os.path.dirname(source_path), frame_file)
        return os.path.normcase(os.path.realpath(frame_path)) == os.path.normcase(os.path.realpath(source_path))

    def continue_to_stop(self, timeout: float = 10.0) -> StopInfo:
        rec = self._transport.command("-exec-continue", timeout=min(timeout, 10.0))
        self._command_error(rec, "-exec-continue")
        rec = self._transport.wait_for_stop(timeout=timeout)
        return self._parse_stop(rec)

    def interrupt(self) -> None:
        try:
            self._transport.command("-exec-interrupt", timeout=3)
        except (GdbExitedError, CommandTimeoutError):
            pass

    def stack_list_frames(self) -> list[dict[str, Any]]:
        rec = self._transport.command("-stack-list-frames", timeout=10)
        if rec.klass == "done":
            stack = rec.payload.get("stack", [])
            if isinstance(stack, list):
                return [f for f in stack if isinstance(f, dict)]
        return []

    def stack_list_variables(self) -> list[dict[str, Any]]:
        rec = self._transport.command("-stack-list-variables --all-values", timeout=10)
        if rec.klass == "done":
            variables = rec.payload.get("variables", [])
            if isinstance(variables, list):
                return [v for v in variables if isinstance(v, dict)]
        return []

    def select_frame(self, level: int) -> None:
        rec = self._transport.command(f"-stack-select-frame {level}", timeout=5)
        self._command_error(rec, f"-stack-select-frame {level}")

    def symbol_info_variables(self) -> list[str]:
        rec = self._transport.command("-symbol-info-variables", timeout=10)
        self._command_error(rec, "-symbol-info-variables")
        names: list[str] = []
        seen: set[str] = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                name = value.get("name")
                if isinstance(name, str) and name not in seen and "type" in value:
                    seen.add(name)
                    if not name.startswith("tutor_"):
                        names.append(name)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(rec.payload.get("symbols", {}).get("debug", []))
        return names

    def tracked_allocations(self, limit: int = 1024) -> list[dict[str, str]]:
        raw_count = self.data_evaluate_expression("tutor_alloc_count")
        try:
            count = min(int(raw_count, 0), limit)
        except (TypeError, ValueError):
            return []
        allocations = []
        for index in range(count):
            prefix = f"tutor_allocations[{index}]"
            address = self.data_evaluate_expression(f"{prefix}.address")
            size = self.data_evaluate_expression(f"{prefix}.size")
            is_freed = self.data_evaluate_expression(f"{prefix}.is_freed")
            allocations.append({
                "address": address,
                "size": size,
                "is_freed": is_freed,
            })
        return allocations

    def enable_heap_tracking(self) -> None:
        rec = self._transport.command(
            '-data-evaluate-expression "tutor_tracking_enabled = 1"', timeout=5
        )
        self._command_error(rec, "enable heap tracking")

    def var_create(self, expression: str) -> dict[str, Any]:
        rec = self._transport.command(f'-var-create - * {expression}', timeout=10)
        if rec.klass == "done":
            return rec.payload
        return {}

    def var_list_children(self, name: str) -> list[dict[str, Any]]:
        rec = self._transport.command(f"-var-list-children --all-values {name}", timeout=10)
        if rec.klass == "done":
            children = rec.payload.get("children", [])
            if isinstance(children, list):
                result = []
                for c in children:
                    if isinstance(c, dict):
                        if "child" in c and isinstance(c["child"], dict):
                            result.append(c["child"])
                        else:
                            result.append(c)
                return result
        return []

    def var_delete(self, name: str) -> None:
        try:
            self._transport.command(f"-var-delete {name}", timeout=10)
        except (GdbExitedError, CommandTimeoutError):
            pass

    def data_evaluate_expression(self, expression: str) -> str:
        rec = self._transport.command(f'-data-evaluate-expression {expression}', timeout=10)
        if rec.klass == "done":
            return rec.payload.get("value", "")
        return ""

    def terminate(self) -> None:
        self._transport.close(graceful=True)
