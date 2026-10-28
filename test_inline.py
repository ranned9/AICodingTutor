import sys
sys.path.insert(0, 'backend')
from app.core.instrumenter import Instrumenter

code = "int main() {int a = 10; return 0;}"
result = Instrumenter.instrument(code)
print(result)
print("=== HAS_ENTER:", "__mem_enter" in result)
print("=== HAS_TRACE:", "__mem_trace" in result)
print("=== HAS_CLEANUP:", "__MEM_CLEANUP" in result)