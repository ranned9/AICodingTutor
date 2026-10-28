from pydantic import BaseModel, Field

from app.models.event_model import MemoryEvent

SCHEMA_VERSION = 1


class GlobalVariable(BaseModel):
    name: str
    type: str
    address: str
    value: str


class LocalVariable(BaseModel):
    name: str
    type: str
    address: str
    value: str


class StackFrame(BaseModel):
    function: str
    args: str = ""
    locals: list[LocalVariable] = Field(default_factory=list)


class HeapObject(BaseModel):
    address: str
    size: int
    is_freed: bool = False
    content: list[int] = Field(default_factory=list)


class PointerReference(BaseModel):
    name: str
    type: str
    value: str
    target_address: str


class MemorySnapshot(BaseModel):
    schema_version: int = SCHEMA_VERSION
    session_id: str
    step: int
    line: int = 0
    event: MemoryEvent = MemoryEvent.NONE
    globals: list[GlobalVariable] = Field(default_factory=list)
    stack_frames: list[StackFrame] = Field(default_factory=list)
    heap_objects: list[HeapObject] = Field(default_factory=list)
    pointers: list[PointerReference] = Field(default_factory=list)
    is_complete: bool = True