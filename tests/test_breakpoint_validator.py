from app.core.breakpoint_validator import BreakpointValidator


def test_executable_line_code():
    assert BreakpointValidator.is_executable_line("int a = 1;") is True
    assert BreakpointValidator.is_executable_line("    return 0;") is True
    assert BreakpointValidator.is_executable_line("printf(\"hello\");") is True


def test_non_executable_empty_line():
    assert BreakpointValidator.is_executable_line("") is False
    assert BreakpointValidator.is_executable_line("   ") is False


def test_non_executable_comment():
    assert BreakpointValidator.is_executable_line("// comment") is False
    assert BreakpointValidator.is_executable_line("/* block */") is False
    assert BreakpointValidator.is_executable_line("* continued") is False


def test_non_executable_preprocessor():
    assert BreakpointValidator.is_executable_line("#include <stdio.h>") is False
    assert BreakpointValidator.is_executable_line("#define MAX 100") is False


def test_non_executable_brace_only():
    assert BreakpointValidator.is_executable_line("{") is False
    assert BreakpointValidator.is_executable_line("}") is False
    assert BreakpointValidator.is_executable_line("  {  ") is False


def test_validate_valid_breakpoints():
    code = "int main() {\n    int a = 1;\n    return 0;\n}\n"
    valid, invalid = BreakpointValidator.validate_breakpoints(code, [2, 3])
    assert valid is True
    assert invalid is None


def test_validate_invalid_breakpoint_empty_line():
    code = "int main() {\n\n    return 0;\n}\n"
    valid, invalid = BreakpointValidator.validate_breakpoints(code, [2])
    assert valid is False
    assert invalid == 2


def test_validate_out_of_range():
    code = "int main() {\n    return 0;\n}\n"
    valid, invalid = BreakpointValidator.validate_breakpoints(code, [10])
    assert valid is False
    assert invalid == 10


def test_validate_empty_breakpoints():
    code = "int main() { return 0; }\n"
    valid, invalid = BreakpointValidator.validate_breakpoints(code, [])
    assert valid is True
    assert invalid is None