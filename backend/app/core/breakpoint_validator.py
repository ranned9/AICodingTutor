import re


class BreakpointValidator:
    _COMMENT_PATTERN = re.compile(r'^\s*(//|/\*|\*|/\*\*)')
    _PREPROCESSOR_PATTERN = re.compile(r'^\s*#')
    _BRACE_ONLY_PATTERN = re.compile(r'^\s*[{}]\s*$')

    @classmethod
    def is_executable_line(cls, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if cls._COMMENT_PATTERN.match(stripped):
            return False
        if cls._PREPROCESSOR_PATTERN.match(stripped):
            return False
        if cls._BRACE_ONLY_PATTERN.match(stripped):
            return False
        return True

    @classmethod
    def validate_breakpoints(cls, source_code: str, breakpoints: list[int]) -> tuple[bool, int | None]:
        lines = source_code.splitlines()
        for bp in breakpoints:
            if bp < 1 or bp > len(lines):
                return False, bp
            if not cls.is_executable_line(lines[bp - 1]):
                return False, bp
        return True, None