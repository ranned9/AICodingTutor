from fastapi import APIRouter

from app.api.response import ErrorCode, error_response, ok_response
from app.models.session_model import AIAskRequest
from app.services.ai_proxy import AIProxy
from app.services.session_manager import session_manager
from app.services.snapshot_store import SnapshotStore

router = APIRouter(prefix="/api/debug", tags=["AI答疑"])
_store = SnapshotStore()


@router.post("/{session_id}/ask")
async def ask_ai(session_id: str, req: AIAskRequest):
    if not req.question.strip():
        return error_response(ErrorCode.AI_QUESTION_EMPTY)

    session = session_manager.get_session(session_id)
    if session is None:
        return error_response(ErrorCode.NOT_FOUND, "会话不存在")

    snapshots = session_manager.get_snapshots(session_id)
    snapshot = None
    if snapshots is not None:
        if 0 <= req.step < len(snapshots):
            snapshot = snapshots[req.step]
    else:
        snapshot = _store.get_snapshot(session_id, req.step)

    if snapshot is None:
        return error_response(ErrorCode.AI_NO_SNAPSHOT)

    error_code, answer = await AIProxy.ask(session.source_code, snapshot, req.question)
    if error_code != ErrorCode.SUCCESS:
        return error_response(error_code)

    return ok_response({"answer": answer})