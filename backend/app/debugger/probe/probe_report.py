from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CapabilityResult:
    name: str
    passed: bool
    raw_request: str = ""
    raw_response: str = ""
    note: str = ""


@dataclass
class PathValidation:
    path_with_spaces: bool = False
    path_with_chinese: bool = False
    spaces_detail: str = ""
    chinese_detail: str = ""


@dataclass
class ProbeReport:
    compiler_version: str = ""
    debugger_version: str = ""
    compile_command: str = ""
    debugger_start_command: str = ""
    capability_results: list[CapabilityResult] = field(default_factory=list)
    path_validation: PathValidation = field(default_factory=PathValidation)
    failures: list[str] = field(default_factory=list)
    conclusion: str = "failed"
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "compiler_version": self.compiler_version,
            "debugger_version": self.debugger_version,
            "compile_command": self.compile_command,
            "debugger_start_command": self.debugger_start_command,
            "capability_results": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "raw_request": c.raw_request,
                    "raw_response": c.raw_response,
                    "note": c.note,
                }
                for c in self.capability_results
            ],
            "path_validation": {
                "path_with_spaces": self.path_validation.path_with_spaces,
                "path_with_chinese": self.path_validation.path_with_chinese,
                "spaces_detail": self.path_validation.spaces_detail,
                "chinese_detail": self.path_validation.chinese_detail,
            },
            "failures": self.failures,
            "conclusion": self.conclusion,
            "generated_at": self.generated_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def save_to_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @property
    def all_passed(self) -> bool:
        return self.conclusion == "passed" and len(self.failures) == 0