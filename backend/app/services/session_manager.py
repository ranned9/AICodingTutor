import logging
import uuid
from dataclasses import dataclass, field

from app.api.response import ErrorCode
from app.core.breakpoint_validator import BreakpointValidator
from app.core.event_detector import EventDetector
from app.core.instrumenter import Instrumenter
from app.core.sandbox_executor import SandboxExecutor
from app.core.snapshot_collector import SnapshotCollector
from app.models.event_model import DebugMode, SessionStatus
from app.models.session_model import DebugSession
from app.models.snapshot_model import MemorySnapshot
from app.services.snapshot_store import SnapshotStore

logger = logging.getLogger(__name__)


@dataclass
class DebugResult:
    success: bool
    error_code: ErrorCode = ErrorCode.SUCCESS
    error_message: str = ""
    error_line: int | None = None
    crash_line: int | None = None
    session_id: str | None = None
    snapshots: list[MemorySnapshot] = field(default_factory=list)
    current_step: int = 0
    finished: bool = False


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, DebugSession] = {}
        self._snapshots: dict[str, list[MemorySnapshot]] = {}
        self._current_step: dict[str, int] = {}
        self._store = SnapshotStore()
        self._sandbox = SandboxExecutor()

    def start_debug(self, code: str, mode: DebugMode, breakpoints: list[int]) -> DebugResult:
        if not code.strip():
            return DebugResult(success=False, error_code=ErrorCode.SOURCE_EMPTY)

        valid, invalid_line = BreakpointValidator.validate_breakpoints(code, breakpoints)
        if not valid:
            return DebugResult(success=False, error_code=ErrorCode.BREAKPOINT_INVALID)

        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        session = DebugSession(
            session_id=session_id,
            mode=mode,
            source_code=code,
            breakpoints=breakpoints,
            status=SessionStatus.INSTRUMENTING,
        )
        self._sessions[session_id] = session

        try:
            instrumented_code = Instrumenter.instrument(code)
        except Exception as e:
            logger.exception("插桩失败: %s", e)
            session.status = SessionStatus.FAILED
            return DebugResult(success=False, error_code=ErrorCode.INSTRUMENT_FAILED)

        session.status = SessionStatus.COMPILING

        compile_result, exec_result = self._sandbox.compile_and_execute(instrumented_code)

        if not compile_result.success:
            session.status = SessionStatus.FAILED
            return DebugResult(
                success=False,
                error_code=ErrorCode.COMPILE_ERROR,
                error_line=compile_result.error_line,
                error_message=compile_result.error_desc or "编译错误",
            )

        if exec_result is None or not exec_result.success:
            session.status = SessionStatus.FAILED
            error_code = exec_result.error_code if exec_result else ErrorCode.RUNTIME_ERROR
            error_msg = exec_result.error_message if exec_result else "执行失败"
            snapshots = []
            crash_line = None
            if exec_result and exec_result.stdout:
                snapshots = SnapshotCollector.parse_stdout(exec_result.stdout, session_id)
                if snapshots:
                    source_lines = code.splitlines()
                    snapshots = EventDetector.detect_and_label(snapshots, source_lines)
                    self._snapshots[session_id] = snapshots
                    self._store.save_sequence(session_id, snapshots)
                    last_line = snapshots[-1].line if snapshots else 0
                    crash_line = last_line if last_line > 0 else None
                    if crash_line and crash_line <= len(source_lines):
                        def _is_safe_stmt(s):
                            s = s.strip()
                            return s.startswith('return') or s.startswith('printf')
                        if _is_safe_stmt(source_lines[crash_line - 1]):
                            for snap in reversed(snapshots):
                                if snap.line > 0 and snap.line <= len(source_lines):
                                    snap_source = source_lines[snap.line - 1]
                                    if not _is_safe_stmt(snap_source):
                                        crash_line = snap.line
                                        break
            return DebugResult(
                success=False,
                error_code=error_code,
                error_message=error_msg,
                crash_line=crash_line,
                session_id=session_id,
                snapshots=snapshots,
            )

        try:
            snapshots = SnapshotCollector.parse_stdout(exec_result.stdout, session_id)
            source_lines = code.splitlines()
            snapshots = EventDetector.detect_and_label(snapshots, source_lines)
        except Exception as e:
            logger.exception("快照解析失败: %s", e)
            snapshots = []

        self._snapshots[session_id] = snapshots
        self._current_step[session_id] = 0
        session.total_steps = len(snapshots)
        self._store.save_sequence(session_id, snapshots)

        if mode == DebugMode.FULL:
            session.status = SessionStatus.COMPLETED
            return DebugResult(
                success=True,
                session_id=session_id,
                snapshots=snapshots,
                finished=True,
            )
        else:
            session.status = SessionStatus.PAUSED
            first_snap = snapshots[0] if snapshots else None
            return DebugResult(
                success=True,
                session_id=session_id,
                snapshots=[first_snap] if first_snap else [],
                current_step=0,
                finished=False,
            )

    def step(self, session_id: str) -> DebugResult:
        session = self._sessions.get(session_id)
        if session is None:
            return DebugResult(success=False, error_code=ErrorCode.NOT_FOUND)

        snapshots = self._snapshots.get(session_id, [])
        current = self._current_step.get(session_id, 0)

        if current + 1 >= len(snapshots):
            session.status = SessionStatus.COMPLETED
            return DebugResult(success=True, session_id=session_id, finished=True)

        current += 1
        self._current_step[session_id] = current
        return DebugResult(
            success=True,
            session_id=session_id,
            snapshots=[snapshots[current]],
            current_step=current,
            finished=False,
        )

    def continue_execution(self, session_id: str) -> DebugResult:
        session = self._sessions.get(session_id)
        if session is None:
            return DebugResult(success=False, error_code=ErrorCode.NOT_FOUND)

        snapshots = self._snapshots.get(session_id, [])
        current = self._current_step.get(session_id, 0)
        breakpoints = set(session.breakpoints)

        for i in range(current + 1, len(snapshots)):
            if snapshots[i].line in breakpoints:
                self._current_step[session_id] = i
                return DebugResult(
                    success=True,
                    session_id=session_id,
                    snapshots=[snapshots[i]],
                    current_step=i,
                    finished=False,
                )

        session.status = SessionStatus.COMPLETED
        self._current_step[session_id] = len(snapshots) - 1
        return DebugResult(
            success=True,
            session_id=session_id,
            snapshots=[snapshots[-1]] if snapshots else [],
            current_step=len(snapshots) - 1,
            finished=True,
        )

    def stop(self, session_id: str) -> DebugResult:
        session = self._sessions.get(session_id)
        if session is None:
            return DebugResult(success=False, error_code=ErrorCode.NOT_FOUND)
        session.status = SessionStatus.COMPLETED
        return DebugResult(success=True, session_id=session_id)

    def get_session(self, session_id: str) -> DebugSession | None:
        return self._sessions.get(session_id)

    def get_snapshots(self, session_id: str) -> list[MemorySnapshot] | None:
        return self._snapshots.get(session_id)


session_manager = SessionManager()