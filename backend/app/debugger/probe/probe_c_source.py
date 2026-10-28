def get_probe_c_source() -> str:
    return r"""#include <stdio.h>

int g_total = 4;

struct Point {
    int x;
    int y;
};

int add(int a, int b) {
    int values[3] = {a, b, a + b};
    struct Point p = {
        .x = values[0],
        .y = values[2]
    };
    g_total += p.y;
    return p.x + p.y;
}

int main(void) {
    int result = add(2, 5);
    int *ptr = &result;
    int sum = 0;
    for (int i = 0; i < 3; i++) {
        sum += i;
    }
    printf("%d %d %d\n", result, g_total, *ptr + sum);
    return 0;
}
"""