// graph.cpp — 数据结构实验：图的邻接表存储与广度优先遍历
#include <cstdio>
#include <queue>
#include <vector>
using namespace std;

int main() {
    int n = 6; // 顶点编号 1..6
    vector<int> adj[7];
    adj[1] = {2, 3};
    adj[2] = {1, 4, 5};
    adj[3] = {1, 5};
    adj[4] = {2, 6};
    adj[5] = {2, 3, 6};
    adj[6] = {4, 5};

    printf("邻接表:\n");
    for (int i = 1; i <= n; i++) {
        printf("%d: ", i);
        for (int v : adj[i]) printf("%d ", v);
        printf("\n");
    }

    bool vis[7] = {false};
    queue<int> q;
    q.push(1);
    vis[1] = true;
    printf("BFS 遍历顺序: ");
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        printf("%d ", u);
        for (int v : adj[u])
            if (!vis[v]) { vis[v] = true; q.push(v); }
    }
    printf("\n");
    return 0;
}
