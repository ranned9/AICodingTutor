from fastapi import APIRouter

from app.api.response import ErrorCode, error_response, ok_response
from app.models.event_model import DebugMode
from app.models.session_model import DebugStartRequest
from app.services.session_manager import session_manager

router = APIRouter(prefix="/api/debug", tags=["调试执行"])


@router.post("/start")
async def start_debug(req: DebugStartRequest):
    result = session_manager.start_debug(req.code, req.mode, req.breakpoints)
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
        return error_response(result.error_code, result.error_message, data if data else None)

    if req.mode == DebugMode.FULL:
        return ok_response({
            "session_id": result.session_id,
            "total_steps": len(result.snapshots),
            "snapshots": [s.model_dump() for s in result.snapshots],
        })
    else:
        snap = result.snapshots[0] if result.snapshots else None
        return ok_response({
            "session_id": result.session_id,
            "current_step": result.current_step,
            "snapshot": snap.model_dump() if snap else None,
            "finished": result.finished,
        })


@router.post("/{session_id}/step")
async def step(session_id: str):
    result = session_manager.step(session_id)
    if not result.success:
        return error_response(result.error_code, result.error_message)

    snap = result.snapshots[0] if result.snapshots else None
    return ok_response({
        "current_step": result.current_step,
        "snapshot": snap.model_dump() if snap else None,
        "finished": result.finished,
    })


@router.post("/{session_id}/continue")
async def continue_execution(session_id: str):
    result = session_manager.continue_execution(session_id)
    if not result.success:
        return error_response(result.error_code, result.error_message)

    snap = result.snapshots[0] if result.snapshots else None
    return ok_response({
        "current_step": result.current_step,
        "snapshot": snap.model_dump() if snap else None,
        "finished": result.finished,
    })


@router.post("/{session_id}/stop")
async def stop(session_id: str):
    result = session_manager.stop(session_id)
    if not result.success:
        return error_response(result.error_code, result.error_message)
    return ok_response({"session_id": session_id})