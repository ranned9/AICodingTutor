from app.models.event_model import MemoryEvent
from app.models.snapshot_model import MemorySnapshot


class EventDetector:
    @staticmethod
    def detect_and_label(snapshots: list[MemorySnapshot], source_lines: list[str]) -> list[MemorySnapshot]:
        if not snapshots:
            return snapshots

        prev_heap_addrs: set[str] = set()
        prev_frame_funcs: list[str] = []

        for i, snap in enumerate(snapshots):
            current_heap_addrs = {h.address for h in snap.heap_objects if not h.is_freed}
            current_frame_funcs = [sf.function for sf in snap.stack_frames]

            new_heap = current_heap_addrs - prev_heap_addrs
            freed_heap = prev_heap_addrs - current_heap_addrs
            frame_grew = len(current_frame_funcs) > len(prev_frame_funcs)
            frame_shrank = len(current_frame_funcs) < len(prev_frame_funcs)
            frame_changed = current_frame_funcs != prev_frame_funcs

            if new_heap:
                snap.event = MemoryEvent.MALLOC
            elif freed_heap:
                snap.event = MemoryEvent.FREE
            elif frame_grew:
                snap.event = MemoryEvent.FUNCTION_CALL
            elif frame_shrank:
                snap.event = MemoryEvent.FUNCTION_RETURN
            elif frame_changed and len(current_frame_funcs) == len(prev_frame_funcs):
                snap.event = MemoryEvent.FUNCTION_CALL
            else:
                snap.event = MemoryEvent.NONE

            prev_heap_addrs = current_heap_addrs
            prev_frame_funcs = current_frame_funcs

        return snapshots