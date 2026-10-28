from dataclasses import dataclass


@dataclass
class CaseInfo:
    case_id: str
    title: str
    category: str
    code: str


_CASES: list[CaseInfo] = [
    CaseInfo(
        case_id="basic_var",
        title="基础变量与栈帧",
        category="栈帧",
        code="""#include <stdio.h>

int main() {
    int a = 10;
    int b = 20;
    int c = a + b;
    printf("c = %d\\n", c);
    return 0;
}
""",
    ),
    CaseInfo(
        case_id="stack_demo",
        title="函数调用栈演示",
        category="栈帧",
        code="""#include <stdio.h>

int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

int main() {
    int result = factorial(4);
    printf("4! = %d\\n", result);
    return 0;
}
""",
    ),
    CaseInfo(
        case_id="malloc_free",
        title="malloc/free堆管理",
        category="堆内存",
        code="""#include <stdio.h>
#include <stdlib.h>

int main() {
    int *p = (int *)malloc(5 * sizeof(int));
    for (int i = 0; i < 5; i++) {
        p[i] = i * 10;
    }
    printf("p[2] = %d\\n", p[2]);
    free(p);
    return 0;
}
""",
    ),
    CaseInfo(
        case_id="pointer_basic",
        title="指针基本操作",
        category="指针",
        code="""#include <stdio.h>

int main() {
    int x = 42;
    int *p = &x;
    printf("x = %d\\n", x);
    printf("*p = %d\\n", *p);
    *p = 100;
    printf("x = %d\\n", x);
    return 0;
}
""",
    ),
    CaseInfo(
        case_id="pointer_array",
        title="指针与数组",
        category="指针",
        code="""#include <stdio.h>

int main() {
    int arr[5] = {10, 20, 30, 40, 50};
    int *p = arr;
    for (int i = 0; i < 5; i++) {
        printf("arr[%d] = %d\\n", i, *(p + i));
    }
    return 0;
}
""",
    ),
    CaseInfo(
        case_id="struct_demo",
        title="结构体内存布局",
        category="结构体",
        code="""#include <stdio.h>

struct Point {
    int x;
    int y;
};

int main() {
    struct Point p1;
    p1.x = 3;
    p1.y = 7;
    printf("Point(%d, %d)\\n", p1.x, p1.y);
    return 0;
}
""",
    ),
    CaseInfo(
        case_id="wild_pointer",
        title="野指针风险演示",
        category="指针",
        code="""#include <stdio.h>
#include <stdlib.h>

int main() {
    int *p = (int *)malloc(sizeof(int));
    *p = 99;
    printf("*p = %d\\n", *p);
    free(p);
    printf("p已释放但未置NULL\\n");
    int val = *p;
    printf("野指针读取: *p = %d\\n", val);
    *p = 200;
    printf("野指针写入: *p = 200\\n");
    return 0;
}
""",
    ),
    CaseInfo(
        case_id="global_var",
        title="全局变量与局部变量",
        category="变量",
        code="""#include <stdio.h>

int g_count = 0;

void increment() {
    g_count++;
    int local = g_count * 10;
    printf("local = %d\\n", local);
}

int main() {
    increment();
    increment();
    increment();
    printf("g_count = %d\\n", g_count);
    return 0;
}
""",
    ),
]

_CASE_MAP: dict[str, CaseInfo] = {c.case_id: c for c in _CASES}


class CaseLibrary:
    @staticmethod
    def list_cases() -> list[dict]:
        return [{"case_id": c.case_id, "title": c.title, "category": c.category} for c in _CASES]

    @staticmethod
    def get_case(case_id: str) -> CaseInfo | None:
        return _CASE_MAP.get(case_id)