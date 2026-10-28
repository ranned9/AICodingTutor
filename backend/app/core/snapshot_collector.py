import json
import logging

from app.models.event_model import MemoryEvent
from app.models.snapshot_model import (
    GlobalVariable,
    HeapObject,
    LocalVariable,
    MemorySnapshot,
    PointerReference,
    StackFrame,
)

logger = logging.getLogger(__name__)


class SnapshotCollector:
    @staticmethod
    def parse_stdout(stdout: str, session_id: str) -> list[MemorySnapshot]:
        snapshots: list[MemorySnapshot] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("__SNAP__:"):
                continue
            json_str = line[len("__SNAP__:"):]
            try:
                data = json.loads(json_str)
                snapshot = SnapshotCollector._build_snapshot(data, session_id)
                snapshots.append(snapshot)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("快照解析失败: %s, line: %s", e, line[:100])
                continue
        return snapshots

    @staticmethod
    def _build_snapshot(data: dict, session_id: str) -> MemorySnapshot:
        step = data.get("step", 0)
        line = data.get("line", 0)
        event_str = data.get("event", "none")
        try:
            event = MemoryEvent(event_str)
        except ValueError:
            event = MemoryEvent.NONE

        globals_list = [
            GlobalVariable(
                name=g.get("name", ""),
                type=g.get("type", ""),
                address=g.get("address", ""),
                value=g.get("value", ""),
            )
            for g in data.get("globals", [])
        ]

        stack_frames = []
        for sf in data.get("stack_frames", []):
            locals_list = [
                LocalVariable(
                    name=lv.get("name", ""),
                    type=lv.get("type", ""),
                    address=lv.get("address", ""),
                    value=lv.get("value", ""),
                )
                for lv in sf.get("locals", [])
            ]
            stack_frames.append(StackFrame(function=sf.get("function", ""), args=sf.get("args", ""), locals=locals_list))

        heap_objects = [
            HeapObject(
                address=h.get("address", ""),
                size=h.get("size", 0),
                is_freed=h.get("is_freed", False),
            )
            for h in data.get("heap_objects", [])
        ]

        pointers = [
            PointerReference(
                name=p.get("name", ""),
                type=p.get("type", ""),
                value=p.get("value", ""),
                target_address=p.get("target_address", ""),
            )
            for p in data.get("pointers", [])
        ]

        is_complete = bool(data.get("is_complete", True))
        if not (globals_list or stack_frames or heap_objects or pointers):
            is_complete = False

        return MemorySnapshot(
            session_id=session_id,
            step=step,
            line=line,
            event=event,
            globals=globals_list,
            stack_frames=stack_frames,
            heap_objects=heap_objects,
            pointers=pointers,
            is_complete=is_complete,
        )