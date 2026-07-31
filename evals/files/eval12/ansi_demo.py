# ansi_demo.py — ANSI 颜色 + 中文 + Emoji + 回车刷新 + stdout/stderr 交错 + 退出码 3
import sys
import time

def progress(i, total):
    bar = "\u2588" * i + "\u2591" * (total - i)
    sys.stdout.write(f"\r\x1b[36m进度 [{bar}] {i * 100 // total}%\x1b[0m")
    sys.stdout.flush()

for i in range(1, 6):
    progress(i, 5)
    sys.stderr.write(f"警告: step {i} 重试\n")
    time.sleep(0.05)

print("\n\x1b[32m\u2713 任务完成\x1b[0m \U0001F600 中文Emoji混合输出")
print("\u6d4b\u8bd5\u4e2d\u6587\u5b57\u7b26\u5bbd\u5ea6: \u4f60\u597d\uff0c\u4e16\u754c\uff01")
sys.exit(3)
