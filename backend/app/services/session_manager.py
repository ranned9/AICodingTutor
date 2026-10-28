import logging
import uuid
from dataclasses import dataclass, field

from app.api.response import ErrorCode
from app.debugger.config import DebuggerConfig
from app.debugger.gdb_engine import GdbDebugEngine
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
    status: str = ""
    stop: object | None = None
    diagnostics: list = field(default_factory=list)


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, DebugSession] = {}
        self._snapshots: dict[str, list[MemorySnapshot]] = {}
        self._current_step: dict[str, int] = {}
        self._store = SnapshotStore()
        self._gdb_engine = GdbDebugEngine(DebuggerConfig())

    def start_debug(self, code: str, mode: DebugMode, breakpoints: list[int],
                    engine: str = "gdb") -> DebugResult:
        if engine != "gdb":
            return DebugResult(success=False, error_code=ErrorCode.UNKNOWN_ERROR,
                               error_message=f"不支持的调试引擎: {engine}")
        result = self._gdb_engine.start(code, mode.value, breakpoints)
        if not result.success:
            error_code = {
                "SOURCE_EMPTY": ErrorCode.SOURCE_EMPTY,
                "COMPILE_ERROR": ErrorCode.COMPILE_ERROR,
                "TIMEOUT": ErrorCode.SANDBOX_LIMIT,
            }.get(result.error_code, ErrorCode.UNKNOWN_ERROR)
            return DebugResult(
                success=False,
                error_code=error_code,
                error_message=result.error_message,
                diagnostics=result.diagnostics,
            )
        session = DebugSession(
            session_id=result.session_id,
            mode=mode,
            source_code=code,
            breakpoints=breakpoints,
            status={
                "completed": SessionStatus.COMPLETED,
                "failed": SessionStatus.FAILED,
                "stopped": SessionStatus.STOPPED,
            }.get(result.status, SessionStatus.PAUSED),
        )
        self._sessions[result.session_id] = session
        snapshots = result.snapshots or ([result.snapshot] if result.snapshot else [])
        self._snapshots[result.session_id] = snapshots
        self._current_step[result.session_id] = result.current_step
        return DebugResult(
            success=True,
            session_id=result.session_id,
            snapshots=snapshots,
            current_step=result.current_step,
            finished=result.status in {"completed", "failed", "stopped"},
            status=result.status,
            stop=result.stop,
        )

    def step(self, session_id: str) -> DebugResult:
        return self._gdb_step(session_id, "step_over")

    def step_into(self, session_id: str) -> DebugResult:
        return self._gdb_step(session_id, "step_into")

    def _gdb_step(self, session_id: str, action: str) -> DebugResult:
        if action == "step_over":
            result = self._gdb_engine.step(session_id)
        elif action == "step_into":
            result = self._gdb_engine.step_into(session_id)
        else:
            result = self._gdb_engine.continue_execution(session_id)
        if not result.success:
            return DebugResult(success=False, error_code=ErrorCode.UNKNOWN_ERROR,
                               error_message=result.error_message,
                               session_id=session_id)
        if result.snapshot:
            self._snapshots.setdefault(session_id, []).append(result.snapshot)
        self._current_step[session_id] = result.current_step
        finished = result.status in {"completed", "failed", "stopped"}
        if result.status == "completed":
            session = self._sessions.get(session_id)
            if session:
                session.status = SessionStatus.COMPLETED
        elif result.status == "failed":
            session = self._sessions.get(session_id)
            if session:
                session.status = SessionStatus.FAILED
        elif result.status == "stopped":
            session = self._sessions.get(session_id)
            if session:
                session.status = SessionStatus.STOPPED
        return DebugResult(
            success=True,
            session_id=session_id,
            snapshots=[result.snapshot] if result.snapshot else [],
            current_step=result.current_step,
            finished=finished,
            status=result.status,
            stop=result.stop,
        )

    def continue_execution(self, session_id: str) -> DebugResult:
        return self._gdb_step(session_id, "continue")

    def stop(self, session_id: str) -> DebugResult:
        result = self._gdb_engine.stop(session_id)
        session = self._sessions.get(session_id)
        if session and result.success:
            session.status = SessionStatus.STOPPED
        return DebugResult(success=result.success, session_id=session_id,
                           status="stopped")

    def shutdown(self) -> None:
        self._gdb_engine.shutdown()

    def get_session(self, session_id: str) -> DebugSession | None:
        return self._sessions.get(session_id)

    def get_snapshots(self, session_id: str) -> list[MemorySnapshot] | None:
        return self._snapshots.get(session_id)


session_manager = SessionManager()
