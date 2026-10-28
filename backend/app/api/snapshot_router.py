from fastapi import APIRouter

from app.api.response import ErrorCode, error_response, ok_response
from app.services.session_manager import session_manager
from app.services.snapshot_store import SnapshotStore

router = APIRouter(prefix="/api/debug", tags=["快照查询"])
_store = SnapshotStore()


@router.get("/{session_id}/snapshots")
async def get_snapshot_meta(session_id: str):
    snapshots = session_manager.get_snapshots(session_id)
    if snapshots is None:
        meta = _store.get_meta(session_id)
        if meta is None:
            return error_response(ErrorCode.NOT_FOUND, "会话或快照不存在")
        return ok_response({
            "total_steps": meta.total_steps,
            "events": [{"step": e.step, "event": e.event.value} for e in meta.events],
        })

    return ok_response({
        "total_steps": len(snapshots),
        "events": [{"step": i, "event": s.event.value} for i, s in enumerate(snapshots)],
    })


@router.get("/{session_id}/snapshots/{step}")
async def get_snapshot(session_id: str, step: int):
    snapshots = session_manager.get_snapshots(session_id)
    if snapshots is not None:
        if step < 0 or step >= len(snapshots):
            return error_response(ErrorCode.NOT_FOUND, "请求的快照步骤不存在")
        return ok_response(snapshots[step].model_dump())

    snap = _store.get_snapshot(session_id, step)
    if snap is None:
        meta = _store.get_meta(session_id)
        if meta is None:
            return error_response(ErrorCode.NOT_FOUND, "请求的快照步骤不存在")
        if step < 0 or step >= meta.total_steps:
            return error_response(ErrorCode.NOT_FOUND, "请求的快照步骤不存在")
        return error_response(ErrorCode.SNAPSHOT_LOAD_FAILED)

    return ok_response(snap.model_dump())