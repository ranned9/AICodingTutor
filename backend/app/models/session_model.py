from datetime import datetime

from pydantic import BaseModel, Field

from app.models.event_model import DebugMode, MemoryEvent, SessionStatus


class DebugSession(BaseModel):
    session_id: str
    mode: DebugMode
    source_code: str
    breakpoints: list[int] = Field(default_factory=list)
    total_steps: int | None = None
    status: SessionStatus = SessionStatus.IDLE
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class StepEvent(BaseModel):
    step: int
    event: MemoryEvent = MemoryEvent.NONE


class SnapshotSequenceMeta(BaseModel):
    session_id: str
    total_steps: int
    events: list[StepEvent] = Field(default_factory=list)


class AIAskRequest(BaseModel):
    step: int
    question: str


class AIAskResponse(BaseModel):
    answer: str


class DebugStartRequest(BaseModel):
    code: str
    mode: DebugMode = DebugMode.FULL
    breakpoints: list[int] = Field(default_factory=list)
    engine: str = "gdb"