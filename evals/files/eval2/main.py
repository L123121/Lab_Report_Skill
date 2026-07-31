# main.py — Python 实验：学生成绩统计分析
def compute_stats(scores):
    return {
        "avg": sum(scores) / len(scores),
        "max": max(scores),
        "min": min(scores),
        "pass_rate": sum(1 for s in scores if s >= 60) / len(scores),
    }

if __name__ == "__main__":
    scores = [78, 92, 55, 88, 61, 45, 100, 73, 82, 96]
    stats = compute_stats(scores)
    for k, v in stats.items():
        print(f"{k}: {v:.2f}" if isinstance(v, float) else f"{k}: {v}")
