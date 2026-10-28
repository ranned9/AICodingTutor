from __future__ import annotations
import argparse
import os
import sys

from ..config import DebuggerConfig
from .toolchain_probe import ToolchainProbe


def main() -> int:
    parser = argparse.ArgumentParser(description="GDB/MI 工具链探针")
    parser.add_argument("--chinese-path", action="store_true", help="验证中文路径")
    parser.add_argument("--output", default=None, help="报告输出路径")
    args = parser.parse_args()

    config = DebuggerConfig()
    probe = ToolchainProbe(config)
    report = probe.run(check_chinese_path=args.chinese_path)

    print(f"=== 工具链探针报告 ===")
    print(f"编译器: {report.compiler_version}")
    print(f"调试器: {report.debugger_version}")
    print(f"结论: {report.conclusion}")
    print()
    for cap in report.capability_results:
        status = "PASS" if cap.passed else "FAIL"
        print(f"  [{status}] {cap.name}: {cap.note}")
    if report.failures:
        print()
        print("失败项:")
        for f in report.failures:
            print(f"  - {f}")

    output_path = args.output or os.path.join(
        os.path.dirname(__file__), "fixtures", "probe_report.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    report.save_to_file(output_path)
    print(f"\n报告已保存: {output_path}")

    return 0 if report.conclusion == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())