import sys, os
sys.path.insert(0, 'backend')
os.environ['GCC_PATH'] = r'D:\Dve-cpp\MinGW32\bin\gcc.exe'
from app.core.instrumenter import Instrumenter
from app.core.sandbox_executor import SandboxExecutor
from app.core.snapshot_collector import SnapshotCollector

code = """int main(){int *a=(int*)malloc(3*sizeof(int));a[0]=7;a[1]=14;a[2]=21;printf("%d",a[0]+a[1]+a[2]);free(a);return 0;}"""
inst = Instrumenter.instrument(code)
cr, er = SandboxExecutor().compile_and_execute(inst)
print('compile:', cr.success)
if er:
    print('exec success:', er.success)
    print('stdout:', repr(er.stdout[:500]))
    if er.success:
        snaps = SnapshotCollector.parse_stdout(er.stdout, "test")
        print('snapshots:', len(snaps))
        for s in snaps:
            print(f'  step={s.step} line={s.line} heaps={len(s.heap_objects)}')
            for h in s.heap_objects:
                print(f'    {h.address} sz={h.size} freed={h.is_freed} content={h.content}')
    else:
        print('error:', er.error_desc)
else:
    print('no exec result')