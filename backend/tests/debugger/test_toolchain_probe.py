import sys
sys.path.insert(0, "backend")

from app.debugger.config import DebuggerConfig
from app.debugger.probe.toolchain_probe import ToolchainProbe
from app.debugger.probe.probe_report import ProbeReport, CapabilityResult
import os
import pytest


def test_probe_report_serialization():
    report = ProbeReport(
        compiler_version="gcc 10.2.0",
        debugger_version="gdb 9.2",
        conclusion="passed",
    )
    report.capability_results.append(
        CapabilityResult(name="mi2_start", passed=True, note="OK")
    )
    j = report.to_json()
    assert "gcc 10.2.0" in j
    assert "passed" in j
    assert "mi2_start" in j


def test_probe_report_all_passed():
    report = ProbeReport(conclusion="passed")
    assert report.all_passed
    report.failures.append("test")
    assert not report.all_passed


@pytest.mark.skipif(
    not os.path.isfile(os.environ.get("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")),
    reason="GCC not found"
)
@pytest.mark.skipif(
    not os.path.isfile(os.environ.get(
        "GDB_PATH",
        os.path.join(os.path.dirname(os.environ.get("GCC_PATH", "")), "gdb.exe")
    )),
    reason="GDB not found"
)
def test_toolchain_probe_run():
    config = DebuggerConfig()
    probe = ToolchainProbe(config)
    report = probe.run()
    assert report.conclusion in ("passed", "failed")
    assert len(report.capability_results) > 0
    assert report.compiler_version != ""
    assert report.debugger_version != ""