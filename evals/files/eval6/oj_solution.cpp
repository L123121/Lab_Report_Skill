// oj_solution.cpp — 大作业 OJ 题解示例：最大连续子段和
#include <cstdio>
#include <algorithm>
using namespace std;

int main() {
    int n;
    scanf("%d", &n);
    int cur = 0, best = -1000000, x;
    for (int i = 0; i < n; i++) {
        scanf("%d", &x);
        cur = max(x, cur + x);
        best = max(best, cur);
    }
    printf("最大连续子段和: %d\n", best);
    return 0;
}
