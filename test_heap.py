import sys
sys.path.insert(0, 'backend')
from app.core.instrumenter import Instrumenter
from app.core.sandbox_executor import SandboxExecutor
from app.core.snapshot_collector import SnapshotCollector

code = """#include <stdio.h>
#include <stdlib.h>

int main() {
    int *arr = (int*)malloc(5 * sizeof(int));
    arr[0] = 10;
    arr[1] = 20;
    arr[2] = 30;
    arr[3] = 40;
    arr[4] = 50;
    printf("sum=%d\\n", arr[0]+arr[1]+arr[2]+arr[3]+arr[4]);
    free(arr);
    return 0;
}
"""

instrumented = Instrumenter.instrument(code)
print("=== Instrumented (last 20 lines) ===")
for l in instrumented.splitlines()[-20:]:
    print(l)

import os
os.environ.setdefault("GCC_PATH", r"D:\Dve-cpp\MinGW32\bin\gcc.exe")
executor = SandboxExecutor()
result = executor.compile_and_execute(instrumented)
print("\n=== Compile success ===", result.success)
print("=== Output (last 5 lines) ===")
for l in result.stdout.splitlines()[-5:]:
    print(l)

if result.success:
    snapshots = SnapshotCollector.parse(result.stdout)
    print(f"\n=== Snapshots: {len(snapshots)} ===")
    for snap in snapshots:
        print(f"Step {snap.step}, line {snap.line}, heaps: {len(snap.heap_objects)}")
        for h in snap.heap_objects:
            print(f"  addr={h.address} size={h.size} freed={h.is_freed} content={h.content}")