from __future__ import annotations
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import replace
from typing import Any

from .compiler import Compiler
from .config import DebuggerConfig
from .gdb_session import GdbSession, GdbCommandError
from .mi_transport import GdbExitedError, CommandTimeoutError
from .models import (
    CompileDiagnostic, EngineResult, ExpansionBudget,
    ResolvedBreakpoint, StopInfo, VariableNode,
)
from .snapshot_adapter import SnapshotAdapter
from .variable_reader import VariableReader
from app.models.snapshot_model import MemorySnapshot, HeapObject, PointerReference

logger = logging.getLogger(__name__)

class _SessionContext:
    def __init__(self, session_id: str, work_dir: str, source_path: str,
                 gdb_session: GdbSession, breakpoints: list[ResolvedBreakpoint]):
        self.session_id = session_id
        self.work_dir = work_dir
        self.source_path = source_path
        self.gdb_session = gdb_session
        self.breakpoints = breakpoints
        self.snapshots: list[MemorySnapshot] = []
        self.current_step: int = 0
        self.lock = threading.Lock()
        self.created_at: float = time.monotonic()
        self.global_names: list[str] = []
        self.known_heap_addresses: set[str] = set()
        self.exited: bool = False
        self.terminal_status: str = ""
        self.resources_closed: bool = False
        self.stop_requested: bool = False


class GdbDebugEngine:
    def __init__(self, config: DebuggerConfig | None = None):
        self._config = config or DebuggerConfig()
        self._sessions: dict[str, _SessionContext] = {}
        self._lock = threading.Lock()

    def start(self, code: str, mode: str = "step",
              breakpoints: list[int] | None = None) -> EngineResult:
        breakpoints = breakpoints or []
        if not code.strip():
            return EngineResult(success=False, error_code="SOURCE_EMPTY",
                                error_message="源代码为空")

        with self._lock:
            now = time.monotonic()
            expired = [
                sid for sid, ctx in self._sessions.items()
                if ctx.exited and now - ctx.created_at > self._config.session_ttl
            ]
            for sid in expired:
                expired_ctx = self._sessions.pop(sid, None)
                if expired_ctx is not None:
                    self._close_session_resources(expired_ctx)
            active_count = sum(not ctx.exited for ctx in self._sessions.values())
            if active_count >= self._config.max_sessions:
                return EngineResult(success=False, error_code="SESSION_LIMIT",
                                    error_message="会话数已达上限")

        session_id = f"gdb_{uuid.uuid4().hex[:12]}"
        work_dir = tempfile.mkdtemp(prefix=f"gdb_{session_id}_")
        compiler = Compiler(self._config)

        outcome = compiler.compile(code, work_dir, session_id)
        if not outcome.success:
            shutil.rmtree(work_dir, ignore_errors=True)
            return EngineResult(
                success=False, error_code="COMPILE_ERROR",
                error_message=outcome.diagnostics[0].message if outcome.diagnostics else "编译失败",
                diagnostics=outcome.diagnostics,
            )

        source_path = os.path.join(work_dir, "main.c")
        gdb_session = GdbSession(self._config.debugger_path)
        resolved_bps: list[ResolvedBreakpoint] = []
        user_bps: list[ResolvedBreakpoint] = []

        try:
            gdb_session.launch(outcome.executable, work_dir, source_path)
            for bp_line in breakpoints:
                rb = gdb_session.insert_breakpoint(source_path, bp_line)
                resolved_bps.append(rb)
                user_bps.append(rb)
            if mode != "full" and breakpoints and not any(bp.verified for bp in user_bps):
                raise GdbCommandError("没有可解析的断点，请检查断点行号")
            # Always stop at main once so startup/runtime allocations are not
            # mistaken for user heap objects. For breakpoint mode execution
            # continues to the user's requested breakpoint after tracking starts.
            resolved_bps.append(gdb_session.insert_main_breakpoint())
        except Exception as e:
            gdb_session.terminate()
            shutil.rmtree(work_dir, ignore_errors=True)
            return EngineResult(success=False, error_code="GDB_START_FAILED",
                                error_message=f"GDB启动失败: {e}")

        ctx = _SessionContext(session_id, work_dir, source_path, gdb_session, resolved_bps)
        with self._lock:
            self._sessions[session_id] = ctx

        try:
            stop = gdb_session.run_to_first_stop(timeout=15.0)
        except (GdbExitedError, CommandTimeoutError, GdbCommandError) as e:
            self._cleanup_session(session_id)
            return EngineResult(success=False, error_code="GDB_RUN_FAILED",
                                error_message=f"运行失败: {e}")

        if not self._terminal_status(stop):
            try:
                gdb_session.enable_heap_tracking()
            except (GdbExitedError, CommandTimeoutError, GdbCommandError) as e:
                # Heap visualization is optional; a tracking initialization
                # failure must not prevent ordinary source-level debugging.
                logger.warning("Could not enable heap tracking for %s: %s", session_id, e)

        if (mode != "full" and user_bps
                and stop.line not in {bp.line for bp in user_bps if bp.verified}
                and not self._terminal_status(stop)):
            try:
                stop = gdb_session.continue_to_stop(timeout=30.0)
            except (GdbExitedError, CommandTimeoutError, GdbCommandError) as e:
                self._cleanup_session(session_id)
                return EngineResult(success=False, error_code="GDB_RUN_FAILED",
                                    error_message=f"运行至断点失败: {e}")

        stop = self._prefer_user_stop(ctx, stop)
        snapshot = self._collect_snapshot(ctx, stop)
        ctx.snapshots.append(snapshot)

        initial_terminal_status = self._terminal_status(stop)
        if initial_terminal_status:
            ctx.exited = True
            ctx.terminal_status = initial_terminal_status
            self._close_session_resources(ctx)
            return EngineResult(
                success=True, status=initial_terminal_status, session_id=session_id,
                current_step=0, total_steps=1, stop=stop, snapshot=snapshot,
                snapshots=[snapshot], breakpoints=resolved_bps,
            )

        return EngineResult(
            success=True, status="paused", session_id=session_id,
            current_step=0, total_steps=1, stop=stop,
            snapshot=snapshot, snapshots=[snapshot], breakpoints=resolved_bps,
        )

    @staticmethod
    def _terminal_status(stop: StopInfo) -> str:
        if stop.reason in {"exited", "exited-normally"}:
            return "completed"
        if stop.reason in {"exited-signalled", "signal-received"}:
            return "stopped" if stop.signal == "SIGINT" else "failed"
        return ""

    def step(self, session_id: str) -> EngineResult:
        return self._exec_step(session_id, "step_over")

    def step_into(self, session_id: str) -> EngineResult:
        return self._exec_step(session_id, "step_into")

    def continue_execution(self, session_id: str) -> EngineResult:
        return self._exec_step(session_id, "continue")

    def _exec_step(self, session_id: str, action: str) -> EngineResult:
        ctx = self._get_session(session_id)
        if ctx is None:
            return EngineResult(success=False, error_code="NOT_FOUND",
                                error_message="会话不存在")
        if ctx.exited:
            return EngineResult(success=True, status=ctx.terminal_status or "completed",
                                session_id=session_id,
                                current_step=ctx.current_step,
                                total_steps=len(ctx.snapshots),
                                stop=StopInfo(reason="exited-normally"),
                                snapshot=ctx.snapshots[-1] if ctx.snapshots else None,
                                snapshots=list(ctx.snapshots))

        with ctx.lock:
            try:
                if action == "step_over":
                    stop = ctx.gdb_session.step_over(timeout=5.0)
                elif action == "step_into":
                    stop = ctx.gdb_session.step_into(
                        timeout=5.0, source_path=ctx.source_path
                    )
                else:
                    stop = ctx.gdb_session.continue_to_stop(timeout=30.0)
            except GdbExitedError:
                ctx.exited = True
                stop = StopInfo(reason="exited-normally", exit_code=0)
            except GdbCommandError as e:
                return EngineResult(success=False, error_code="GDB_COMMAND_FAILED",
                                    error_message=str(e), session_id=session_id)
            except CommandTimeoutError as e:
                try:
                    ctx.gdb_session.interrupt()
                    ctx.gdb_session._transport.wait_for_stop(timeout=2.0)
                except Exception:
                    pass
                return EngineResult(success=False, error_code="TIMEOUT",
                                    error_message=f"命令超时: {e}",
                                    session_id=session_id)

            stop = self._prefer_user_stop(ctx, stop)
            ctx.current_step += 1
            snapshot = self._collect_snapshot(ctx, stop)
            ctx.snapshots.append(snapshot)

            terminal_status = self._terminal_status(stop)
            if ctx.stop_requested:
                terminal_status = "stopped"
            if terminal_status:
                ctx.exited = True
                ctx.terminal_status = terminal_status
                status = terminal_status
            else:
                status = "paused"
            response = EngineResult(
                success=True, status=status, session_id=session_id,
                current_step=ctx.current_step,
                total_steps=len(ctx.snapshots),
                stop=stop, snapshot=snapshot, snapshots=list(ctx.snapshots),
            )
            if ctx.exited:
                self._close_session_resources(ctx)
            return response

    def stop(self, session_id: str) -> EngineResult:
        ctx = self._get_session(session_id)
        if ctx is None:
            return EngineResult(success=False, error_code="NOT_FOUND",
                                error_message="会话不存在")
        if not ctx.exited:
            ctx.stop_requested = True
            try:
                ctx.gdb_session.interrupt()
            except Exception:
                pass
        with ctx.lock:
            self._cleanup_session(session_id)
        return EngineResult(
            success=True, status="stopped", session_id=session_id,
            current_step=ctx.current_step,
            total_steps=len(ctx.snapshots),
        )

    def get_snapshots(self, session_id: str) -> list[MemorySnapshot]:
        ctx = self._get_session(session_id)
        if ctx is None:
            return []
        return list(ctx.snapshots)

    def get_session(self, session_id: str) -> _SessionContext | None:
        return self._get_session(session_id)

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._sessions.keys())
        for sid in ids:
            self._cleanup_session(sid)
        logger.info("GdbDebugEngine shutdown: cleaned %d sessions", len(ids))

    def _get_session(self, session_id: str) -> _SessionContext | None:
        with self._lock:
            return self._sessions.get(session_id)

    def _collect_snapshot(self, ctx: _SessionContext, stop: StopInfo) -> MemorySnapshot:
        budget = ExpansionBudget(
            max_depth=self._config.max_depth,
            max_children_per_aggregate=self._config.max_children_per_aggregate,
            max_vars_per_stop=self._config.max_vars_per_stop,
            soft_time_limit=self._config.frame_collect_soft_limit,
        )
        reader = VariableReader(ctx.gdb_session, budget)
        stack_frames: list[tuple[dict[str, Any], list[VariableNode]]] = []
        try:
            raw_frames = ctx.gdb_session.stack_list_frames()
            user_frames = [item for item in raw_frames
                           if self._is_user_frame(ctx, item.get("frame", item))]
            for index, item in enumerate(user_frames[:64]):
                frame = item.get("frame", item)
                if not isinstance(frame, dict):
                    continue
                try:
                    level = int(frame.get("level", index))
                except (ValueError, TypeError):
                    level = index
                stack_frames.append((frame, reader.read_frame(level)))
        except Exception:
            stack_frames = []
        frame_vars = stack_frames[0][1] if stack_frames else []
        try:
            ctx.gdb_session.select_frame(0)
            ctx.global_names = ctx.gdb_session.symbol_info_variables()
            global_vars = reader.read_globals(ctx.global_names)
        except Exception:
            global_vars = []

        heap_objects, pointers = self._collect_heap(
            ctx, reader, stack_frames, global_vars,
        )
        try:
            reader.cleanup_varobjs()
        except Exception:
            pass

        return SnapshotAdapter.to_snapshot(
            ctx.session_id, ctx.current_step, stop,
            frame_vars, global_vars, engine="gdb", frames=stack_frames,
            heap_objects=heap_objects, pointers=pointers,
        )

    def _collect_heap(
        self, ctx: _SessionContext, reader: VariableReader,
        stack_frames: list[tuple[dict[str, Any], list[VariableNode]]],
        global_vars: list[VariableNode],
    ) -> tuple[list[HeapObject], list[PointerReference]]:
        try:
            tracked = ctx.gdb_session.tracked_allocations(
                1024
            )
        except Exception:
            return [], []

        pointer_nodes: list[tuple[str, VariableNode, str, int, str]] = []

        def visit(nodes: list[VariableNode], frame_level: int,
                  expression_prefix: str = "", display_prefix: str = "") -> None:
            for node in nodes:
                display_name = f"{display_prefix}.{node.name}" if display_prefix else node.name
                expression = f"{expression_prefix}{node.name}"
                if node.kind == "pointer":
                    match = re.search(r"0x[0-9a-fA-F]+", node.value or "")
                    if match:
                        pointer_nodes.append((display_name, node, match.group(0).lower(),
                                              frame_level, expression))
                visit(node.children, frame_level, f"{expression}.", display_name)

        for frame_info, frame_variables in stack_frames:
            try:
                frame_level = int(frame_info.get("level", 0))
            except (TypeError, ValueError):
                frame_level = 0
            visit(frame_variables, frame_level)
        visit(global_vars, 0, "::")
        allocations_by_address: dict[str, list[dict[str, str]]] = {}
        for allocation in tracked:
            match = re.search(r"0x[0-9a-fA-F]+", allocation["address"] or "")
            try:
                size = int(allocation["size"], 0)
            except (TypeError, ValueError):
                continue
            if not match or size < 0:
                continue
            address = match.group(0).lower()
            allocations_by_address.setdefault(address, []).append({
                "address": address,
                "size": str(size),
                "is_freed": allocation["is_freed"],
            })

        pointers: list[PointerReference] = []
        nodes_by_address: dict[str, list[tuple[str, VariableNode, int, str]]] = {}
        for name, node, address, frame_level, expression in pointer_nodes:
            if address not in allocations_by_address:
                continue
            pointers.append(PointerReference(
                name=name, type=node.type, value=node.value,
                target_address=address,
            ))
            nodes_by_address.setdefault(address, []).append(
                (name, node, frame_level, expression)
            )
        ctx.known_heap_addresses.update(nodes_by_address)

        heap_objects: list[HeapObject] = []
        for address, records in allocations_by_address.items():
            if address not in ctx.known_heap_addresses:
                continue
            refs = nodes_by_address.get(address, [])
            # The linker wrapper may also see allocations made by the C runtime
            # during process startup. Only show blocks reachable through a
            # pointer in a user frame/global, not those implementation details.
            if not refs:
                continue
            for record in records:
                size = int(record["size"])
                is_freed = record["is_freed"].strip().lower() in {"1", "true"}
                element_type = ""
                elements = []
                if refs and size > 0 and not is_freed:
                    pointer_type = refs[0][1].type
                    try:
                        ctx.gdb_session.select_frame(refs[0][2])
                        element_size = int(ctx.gdb_session.data_evaluate_expression(
                            f"sizeof(*({refs[0][3]}))"
                        ), 0)
                    except (TypeError, ValueError):
                        element_size = 0
                    if element_size > 0:
                        element_type = pointer_type.rstrip().rstrip("*").strip()
                        count = min(size // element_size,
                                    self._config.max_children_per_aggregate)
                        for index in range(count):
                            ctx.gdb_session.select_frame(refs[0][2])
                            element_expression = f"{refs[0][3]}[{index}]"
                            element = reader.read_expression(element_expression, f"[{index}]")
                            if element is not None:
                                elements.append(element)
                heap_objects.append(HeapObject(
                    address=address, size=size, is_freed=is_freed,
                    element_type=element_type,
                    elements=[SnapshotAdapter._to_node_model(node) for node in elements],
                ))
        return heap_objects, pointers

    @staticmethod
    def _is_user_frame(ctx: _SessionContext, frame: dict[str, Any]) -> bool:
        frame_file = frame.get("fullname") or frame.get("file") or ""
        if not frame_file:
            return frame.get("func") == "main"
        if not os.path.isabs(frame_file):
            frame_file = os.path.join(os.path.dirname(ctx.source_path), frame_file)
        return os.path.normcase(os.path.realpath(frame_file)) == os.path.normcase(os.path.realpath(ctx.source_path))

    @classmethod
    def _prefer_user_stop(cls, ctx: _SessionContext, stop: StopInfo) -> StopInfo:
        if cls._is_user_frame(ctx, {"file": stop.file, "func": stop.function}):
            return stop
        try:
            for item in ctx.gdb_session.stack_list_frames():
                frame = item.get("frame", item)
                if cls._is_user_frame(ctx, frame):
                    return replace(
                        stop,
                        function=frame.get("func", stop.function),
                        file=frame.get("fullname") or frame.get("file", stop.file),
                        line=int(frame.get("line", stop.line) or stop.line),
                    )
        except Exception:
            pass
        return stop

    def _cleanup_session(self, session_id: str) -> None:
        with self._lock:
            ctx = self._sessions.pop(session_id, None)
        if ctx is None:
            return
        self._close_session_resources(ctx)

    @staticmethod
    def _close_session_resources(ctx: _SessionContext) -> None:
        if ctx.resources_closed:
            return
        ctx.resources_closed = True
        try:
            ctx.gdb_session.terminate()
        except Exception:
            pass
        try:
            self._kill_process_tree(ctx)
        except Exception:
            pass
        shutil.rmtree(ctx.work_dir, ignore_errors=True)

    @staticmethod
    def _kill_process_tree(ctx: _SessionContext) -> None:
        # MITransport owns GDB; GDB is configured to terminate its inferior on exit.
        return
