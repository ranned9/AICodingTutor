from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.api.response import ErrorCode, error_response, ok_response
from app.models.event_model import DebugMode
from app.models.session_model import DebugStartRequest
from app.services.session_manager import session_manager

router = APIRouter(prefix="/api/debug", tags=["调试执行"])


def _stop_to_dict(stop) -> dict:
    if stop is None:
        return None
    return {
        "reason": getattr(stop, "reason", ""),
        "signal": getattr(stop, "signal", ""),
        "function": getattr(stop, "function", ""),
        "file": getattr(stop, "file", ""),
        "line": getattr(stop, "line", 0),
        "address": getattr(stop, "address", ""),
    }


def _diag_to_dict(diagnostics: list) -> list:
    result = []
    for d in diagnostics:
        result.append({
            "severity": getattr(d, "severity", "error"),
            "message": getattr(d, "message", ""),
            "file": getattr(d, "file", None),
            "line": getattr(d, "line", None),
            "column": getattr(d, "column", None),
        })
    return result


@router.post("/start")
async def start_debug(req: DebugStartRequest):
    result = await run_in_threadpool(
        session_manager.start_debug, req.code, req.mode, req.breakpoints, req.engine
    )
    if not result.success:
        data = {}
        if result.error_line is not None:
            data["error_line"] = result.error_line
            data["error_desc"] = result.error_message
        if result.crash_line is not None:
            data["crash_line"] = result.crash_line
        if result.snapshots:
            data["session_id"] = result.session_id
            data["total_steps"] = len(result.snapshots)
            data["snapshots"] = [s.model_dump() for s in result.snapshots]
        if result.diagnostics:
            data["diagnostics"] = _diag_to_dict(result.diagnostics)
        return error_response(result.error_code, result.error_message, data if data else None)


    snap = result.snapshots[0] if result.snapshots else None
    if req.mode == DebugMode.FULL:
        return ok_response({
            "session_id": result.session_id,
            "status": result.status or "paused",
            "current_step": result.current_step,
            "total_steps": len(result.snapshots),
            "snapshots": [s.model_dump() for s in result.snapshots],
            "finished": result.finished,
            "stop": _stop_to_dict(result.stop),
        })
    return ok_response({
        "session_id": result.session_id,
        "status": result.status or "paused",
        "current_step": result.current_step,
        "total_steps": len(result.snapshots),
        "snapshot": snap.model_dump() if snap else None,
        "stop": _stop_to_dict(result.stop),
        "finished": result.finished,
    })


@router.post("/{session_id}/step")
async def step(session_id: str):
    result = await run_in_threadpool(session_manager.step, session_id)
    if not result.success:
        return error_response(result.error_code, result.error_message)

    snap = result.snapshots[0] if result.snapshots else None
    return ok_response({
        "session_id": session_id,
        "status": result.status or ("completed" if result.finished else "paused"),
        "current_step": result.current_step,
        "snapshot": snap.model_dump() if snap else None,
        "stop": _stop_to_dict(result.stop),
        "finished": result.finished,
    })


@router.post("/{session_id}/step_into")
async def step_into(session_id: str):
    result = await run_in_threadpool(session_manager.step_into, session_id)
    if not result.success:
        return error_response(result.error_code, result.error_message)

    snap = result.snapshots[0] if result.snapshots else None
    return ok_response({
        "session_id": session_id,
        "status": result.status or ("completed" if result.finished else "paused"),
        "current_step": result.current_step,
        "snapshot": snap.model_dump() if snap else None,
        "stop": _stop_to_dict(result.stop),
        "finished": result.finished,
    })


@router.post("/{session_id}/continue")
async def continue_execution(session_id: str):
    result = await run_in_threadpool(session_manager.continue_execution, session_id)
    if not result.success:
        return error_response(result.error_code, result.error_message)

    snap = result.snapshots[0] if result.snapshots else None
    return ok_response({
        "session_id": session_id,
        "status": result.status or ("completed" if result.finished else "paused"),
        "current_step": result.current_step,
        "snapshot": snap.model_dump() if snap else None,
        "stop": _stop_to_dict(result.stop),
        "finished": result.finished,
    })


@router.post("/{session_id}/stop")
async def stop(session_id: str):
    result = await run_in_threadpool(session_manager.stop, session_id)
    if not result.success:
        return error_response(result.error_code, result.error_message)
    return ok_response({"session_id": session_id, "status": result.status or "stopped"})
