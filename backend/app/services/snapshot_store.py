import json
import logging
import os
from pathlib import Path

from app.models.event_model import MemoryEvent
from app.models.session_model import SnapshotSequenceMeta, StepEvent
from app.models.snapshot_model import MemorySnapshot

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "snapshots"


class SnapshotStore:
    def __init__(self, storage_root: Path | None = None):
        self.root = storage_root or STORAGE_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def save_sequence(self, session_id: str, snapshots: list[MemorySnapshot]) -> SnapshotSequenceMeta:
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        meta_path = session_dir / "meta.json"
        seq_path = session_dir / "sequence.jsonl"

        events = [StepEvent(step=s.step, event=s.event) for s in snapshots]
        meta = SnapshotSequenceMeta(session_id=session_id, total_steps=len(snapshots), events=events)

        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(meta.model_dump_json())

        with open(seq_path, "w", encoding="utf-8") as f:
            for snap in snapshots:
                f.write(snap.model_dump_json() + "\n")

        return meta

    def get_meta(self, session_id: str) -> SnapshotSequenceMeta | None:
        meta_path = self._session_dir(session_id) / "meta.json"
        if not meta_path.exists():
            return None
        with open(meta_path, "r", encoding="utf-8") as f:
            return SnapshotSequenceMeta.model_validate_json(f.read())

    def get_snapshot(self, session_id: str, step: int) -> MemorySnapshot | None:
        seq_path = self._session_dir(session_id) / "sequence.jsonl"
        if not seq_path.exists():
            return None
        with open(seq_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i == step:
                    return MemorySnapshot.model_validate_json(line.strip())
        return None

    def get_all_snapshots(self, session_id: str) -> list[MemorySnapshot] | None:
        seq_path = self._session_dir(session_id) / "sequence.jsonl"
        if not seq_path.exists():
            return None
        snapshots = []
        with open(seq_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    snapshots.append(MemorySnapshot.model_validate_json(line))
        return snapshots

    def session_exists(self, session_id: str) -> bool:
        return self._session_dir(session_id).exists()