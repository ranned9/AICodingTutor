from __future__ import annotations
from typing import Any

from app.models.snapshot_model import (
    MemorySnapshot, StackFrame, LocalVariable, GlobalVariable,
    VariableNodeModel, HeapObject, PointerReference,
)
from .models import StopInfo, VariableNode


class SnapshotAdapter:
    @staticmethod
    def to_snapshot(
        session_id: str,
        step: int,
        stop: StopInfo,
        frame_vars: list[VariableNode],
        global_vars: list[VariableNode],
        engine: str = "gdb",
        frames: list[tuple[dict[str, Any], list[VariableNode]]] | None = None,
        heap_objects: list[HeapObject] | None = None,
        pointers: list[PointerReference] | None = None,
    ) -> MemorySnapshot:
        globals_list = [
            GlobalVariable(
                name=v.name, type=v.type,
                address=v.address, value=v.value,
            )
            for v in global_vars
            if v.available
        ]
        # An explicitly empty frame list means the inferior has no active
        # frames (for example, after return from main). Only synthesize the
        # legacy single frame when frame metadata was not supplied at all.
        source_frames = frames if frames is not None else [({}, frame_vars)]
        stack_frames = []
        for frame_info, variables in source_frames:
            variable_tree = [SnapshotAdapter._to_node_model(v) for v in variables]
            flat_locals = [
                LocalVariable(name=v.name, type=v.type, address=v.address, value=v.value)
                for v in variables if v.available and v.kind == "scalar"
            ]
            stack_frames.append(StackFrame(
                function=frame_info.get("func", stop.function),
                args="",
                locals=flat_locals,
                variable_tree=variable_tree,
            ))
        return MemorySnapshot(
            session_id=session_id,
            step=step,
            line=stop.line,
            stack_frames=stack_frames,
            globals=globals_list,
            heap_objects=heap_objects or [],
            pointers=pointers or [],
            engine=engine,
            stop_reason=stop.reason,
            is_complete="exited" in stop.reason,
        )

    @staticmethod
    def _to_node_model(node: VariableNode) -> VariableNodeModel:
        return VariableNodeModel(
            name=node.name,
            type=node.type,
            kind=node.kind,
            value=node.value,
            address=node.address,
            children=[
                SnapshotAdapter._to_node_model(c)
                for c in node.children
            ],
            available=node.available,
            unavailable_reason=node.unavailable_reason,
            truncated=node.truncated,
            cycle=node.cycle,
        )
