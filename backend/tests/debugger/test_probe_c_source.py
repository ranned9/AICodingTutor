import sys
sys.path.insert(0, "backend")

from app.debugger.probe.probe_c_source import get_probe_c_source


def test_c_source_has_array():
    src = get_probe_c_source()
    assert "int values[3]" in src


def test_c_source_has_struct():
    src = get_probe_c_source()
    assert "struct Point" in src


def test_c_source_has_pointer():
    src = get_probe_c_source()
    assert "int *ptr" in src


def test_c_source_has_loop():
    src = get_probe_c_source()
    assert "for (int i" in src


def test_c_source_has_function_call():
    src = get_probe_c_source()
    assert "add(2, 5)" in src


def test_c_source_has_global_variable():
    src = get_probe_c_source()
    assert "int g_total" in src


def test_c_source_has_cross_line_init():
    src = get_probe_c_source()
    assert ".x = values[0]" in src
    assert ".y = values[2]" in src


def test_c_source_is_valid_c_syntax():
    import subprocess, os, tempfile
    gcc = os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
    if not os.path.isfile(gcc):
        import pytest
        pytest.skip("GCC not found")
    src = get_probe_c_source()
    with tempfile.NamedTemporaryFile(suffix=".c", delete=False, mode="w") as f:
        f.write(src)
        path = f.name
    try:
        env = os.environ.copy()
        env["PATH"] = os.path.dirname(gcc) + os.pathsep + env.get("PATH", "")
        result = subprocess.run(
            [gcc, "-c", "-std=c11", path, "-o", os.devnull],
            capture_output=True, timeout=10, env=env
        )
        assert result.returncode == 0, f"Compile error: {result.stderr}"
    finally:
        os.unlink(path)