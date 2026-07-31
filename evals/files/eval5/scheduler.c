// scheduler.c — 操作系统实验：时间片轮转调度算法模拟
#include <stdio.h>

typedef struct {
    int pid;
    int remain;
    int arrive;
} Proc;

int main() {
    Proc p[] = {{1, 10, 0}, {2, 4, 2}, {3, 6, 4}, {4, 8, 6}};
    int n = sizeof(p) / sizeof(p[0]);
    int quantum = 3, t = 0, done = 0;

    printf("时间片轮转调度模拟 (quantum=%d)\n", quantum);
    while (done < n) {
        int progressed = 0;
        for (int i = 0; i < n; i++) {
            if (p[i].remain > 0 && t >= p[i].arrive) {
                int run = p[i].remain < quantum ? p[i].remain : quantum;
                printf("t=%d: 进程 P%d 运行 %d 个时间片\n", t, p[i].pid, run);
                p[i].remain -= run;
                t += run;
                if (p[i].remain == 0) {
                    done++;
                    printf("t=%d: 进程 P%d 完成\n", t, p[i].pid);
                }
                progressed = 1;
            }
        }
        if (!progressed) t++;
    }
    return 0;
}
