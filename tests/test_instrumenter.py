import json
import shutil
import subprocess

import pytest

from app.core.instrumenter import Instrumenter


def test_instrument_basic_code():
    code = "int main() {\n    int a = 1;\n    return 0;\n}\n"
    result = Instrumenter.instrument(code)
    assert "__mem_trace" in result
    assert "__SNAP__" in result
    assert "__heap_head" in result


def test_instrument_preserves_user_code():
    code = "int main() {\n    int a = 1;\n    return 0;\n}\n"
    result = Instrumenter.instrument(code)
    assert "int a = 1;" in result
    assert "return 0;" in result


def test_instrument_includes_runtime_header():
    code = "int main() { return 0; }\n"
    result = Instrumenter.instrument(code)
    assert "#include <stdio.h>" in result
    assert "#include <stdlib.h>" in result
    assert "__mem_heap_record" in result
    assert "__tracked_malloc" in result
    assert "__tracked_free" in result


def test_instrument_malloc_macro():
    code = '#include <stdlib.h>\nint main() {\n    int *p = (int *)malloc(sizeof(int));\n    free(p);\n    return 0;\n}\n'
    result = Instrumenter.instrument(code)
    assert "#define malloc(sz) __tracked_malloc(sz)" in result
    assert "#define free(ptr) __tracked_free(ptr)" in result


def test_instrument_function_tracking():
    code = "int add(int a, int b) {\n    return a + b;\n}\nint main() {\n    int c = add(1, 2);\n    return 0;\n}\n"
    result = Instrumenter.instrument(code)
    assert "__mem_enter" in result
    assert "__MEM_CLEANUP" in result
    assert "__attribute__((cleanup" in result


def test_instrument_heap_traversal_limit():
    code = "int main() { return 0; }\n"
    result = Instrumenter.instrument(code)
    assert "__heap_cnt < 256" in result


def test_instrument_empty_code():
    result = Instrumenter.instrument("")
    assert "__mem_trace" in result


def test_instrument_includes_stdio():
    code = "int main() { return 0; }\n"
    result = Instrumenter.instrument(code)
    assert "#include <stdio.h>" in result
    assert "#include <string.h>" in result


def test_struct_scalar_fields_are_captured_after_initialization(tmp_path):
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("gcc is required for the struct instrumentation integration test")

    code = """#include <stdio.h>
struct Point {
    int x;
    int y;
};
int main() {
    struct Point p1;
    p1.x = 3;
    p1.y = 7;
    printf(\"Point(%d, %d)\\n\", p1.x, p1.y);
    return 0;
}
"""
    source_path = tmp_path / "struct_demo.c"
    executable_path = tmp_path / "struct_demo.exe"
    source_path.write_text(Instrumenter.instrument(code), encoding="utf-8")

    compile_result = subprocess.run(
        [gcc, "-g", "-O0", "-std=c99", "-w", "-o", str(executable_path), str(source_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    execution = subprocess.run(
        [str(executable_path)], capture_output=True, text=True, encoding="utf-8", timeout=5
    )
    assert execution.returncode == 0, execution.stderr
    snapshots = [
        json.loads(line[len("__SNAP__:"):])
        for line in execution.stdout.splitlines()
        if line.startswith("__SNAP__:")
    ]
    assert snapshots
    locals_by_name = {
        variable["name"]: variable["value"]
        for variable in snapshots[-1]["stack_frames"][0]["locals"]
    }
    assert locals_by_name["p1.x"] == "3"
    assert locals_by_name["p1.y"] == "7"
    before_first_assignment = {
        variable["name"]: variable["value"]
        for variable in snapshots[1]["stack_frames"][0]["locals"]
    }
    assert before_first_assignment["p1.x"] == "uninitialized"
    assert before_first_assignment["p1.y"] == "uninitialized"
