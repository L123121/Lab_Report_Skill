#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto-shot - 自动生成终端截图：优先真实捕获，失败时回退为"真实计算+模拟样式"渲染。

流程：
1. 用 term_shot.py 真实执行 --command 并捕获（ConPTY/PTY/pipe）。
2. 若真实捕获失败（命令不存在 / 退出非零 / 超时 / 工具错误）：
   - 从 --fallback-text / --fallback-file / --fallback-command 取得真实计算得到的输出文本；
   - 拼装"合成提示行 + 命令 + 输出"，通过 term_shot.py --stdin 走同一套 ANSI 终端模拟渲染管线，
     生成与真实截图一致的终端样式 PNG。

用法示例:
  python scripts/auto_shot.py -c "build/graph_test.exe" --cwd src \\
      -o screenshots/run.png --columns 100 --json
  python scripts/auto_shot.py -c "build/graph_test.exe" --cwd src \\
      --fallback-text "最大连续子段和: 6" -o screenshots/run.png --json
  python scripts/auto_shot.py -c "build/graph_test.exe" --cwd src \\
      --fallback-command "python compute.py" -o screenshots/run.png --json

输出 JSON:
  {"status": "ok", "path": ..., "capture_mode": "conpty"|"pipe"|"stdin",
   "mode": "captured"|"simulated", "command_exit_code": 0|null,
   "prompt_synthetic": true, "fallback_source": null|"text"|"file"|"command", ...}
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
TERM_SHOT = SCRIPT_DIR / "term_shot.py"


def run_term_shot(args_list: list[str], stdin_data: bytes | None = None) -> tuple[int, dict]:
    """Invoke term_shot.py and parse its JSON output."""
    cmd = [sys.executable, str(TERM_SHOT), *args_list, "--json"]
    proc = subprocess.run(cmd, capture_output=True, input=stdin_data)
    stdout_text = proc.stdout.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(stdout_text)
    except json.JSONDecodeError:
        parsed = {"status": "error",
                  "error": (stdout_text + proc.stderr.decode("utf-8", errors="replace")).strip()[:500]}
    return proc.returncode, parsed


def read_fallback_text(args: argparse.Namespace) -> tuple[str, str]:
    """Return (text, source) from fallback options; empty text means unavailable."""
    if args.fallback_file:
        path = Path(args.fallback_file).expanduser()
        if not path.is_file():
            raise FileNotFoundError("Fallback file not found: %s" % path)
        return path.read_text(encoding="utf-8", errors="replace"), "file"
    if args.fallback_command:
        proc = subprocess.run(args.fallback_command, shell=True,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              cwd=args.cwd or os.getcwd())
        return proc.stdout, "command"
    if args.fallback_text is not None:
        return args.fallback_text, "text"
    return "", ""


def build_simulated_text(command: str, output_text: str, cwd: str, short_path: bool = False) -> str:
    """Build a realistic terminal frame: prompt line + command + output."""
    command = " ".join(command.splitlines())
    display_cwd = os.path.basename(cwd.rstrip(os.sep)) or os.sep if short_path else cwd
    platform = "windows" if os.name == "nt" else "mac"
    if platform == "windows":
        prompt_line = "PS %s> %s" % (display_cwd, command) if args_shell_powershell() \
            else "%s> %s" % (display_cwd, command)
    else:
        prompt_line = "user@host %s %% %s" % (display_cwd, command)
    text = prompt_line + "\r\n" + output_text
    if not text.endswith("\n"):
        text += "\n"
    return text


_args_shell = "auto"


def args_shell_powershell() -> bool:
    return _args_shell == "powershell"


def main() -> int:
    global _args_shell
    parser = argparse.ArgumentParser(
        description="Auto terminal screenshot: real capture first, "
                    "simulated render of real computed output as fallback",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--command", required=True,
                        help="Command to execute for real capture")
    parser.add_argument("--cwd", help="Working directory")
    parser.add_argument("-o", "--output", required=True,
                        help="Output PNG path")
    parser.add_argument("--transcript", help="Write final visible terminal text")
    parser.add_argument("--columns", type=int, default=100)
    parser.add_argument("--rows", type=int, default=24)
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--shell", choices=["auto", "cmd", "powershell", "bash"],
                        default="auto")
    parser.add_argument("--capture-mode", choices=["auto", "pty", "pipe"],
                        default=None,
                        help="Terminal capture mode passed to term_shot. "
                             "Default: pipe on Windows (avoids GBK console "
                             "mojibake for UTF-8 output), auto elsewhere. "
                             "Use conpty/pty explicitly only when ANSI colors "
                             "or TTY behavior must be preserved.")
    parser.add_argument("--prompt-short", action="store_true",
                        help="Show only the current directory name in the "
                             "synthetic prompt instead of the full path")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--allow-nonzero", action="store_true",
                        help="Accept a nonzero exit as a successful real capture")
    parser.add_argument("--fallback-text", help="Literal output text to render on fallback")
    parser.add_argument("--fallback-file", help="File containing real computed output text")
    parser.add_argument("--fallback-command", help="Command that computes real output for fallback")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    _args_shell = args.shell

    if args.json and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cwd = os.path.abspath(os.path.expanduser(args.cwd)) if args.cwd else os.getcwd()
    if not os.path.isdir(cwd):
        result = {"status": "error", "error": "Working directory does not exist: %s" % cwd}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    # Platform-aware default: pipe on Windows avoids GBK console mojibake for
    # UTF-8 program output; auto (PTY/ConPTY) elsewhere preserves ANSI/TTY.
    capture_mode = args.capture_mode or ("pipe" if os.name == "nt" else "auto")

    # ---- Step 1: try real capture ----
    term_args = ["-c", args.command, "--cwd", cwd,
                 "-o", args.output, "--columns", str(args.columns),
                 "--rows", str(args.rows), "--theme", args.theme,
                 "--shell", args.shell, "--capture-mode", capture_mode,
                 "--timeout", str(args.timeout)]
    if args.prompt_short:
        term_args.append("--prompt-short")
    if args.transcript:
        term_args += ["--transcript", args.transcript]
    if args.allow_nonzero:
        term_args.append("--allow-nonzero")

    rc, real = run_term_shot(term_args)
    if real.get("status") == "ok" or (args.allow_nonzero and "path" in real):
        real["mode"] = "captured"
        real["fallback_source"] = None
        print(json.dumps(real, ensure_ascii=False, indent=2))
        return 0

    # ---- Step 2: fallback - simulated render of real computed output ----
    try:
        output_text, source = read_fallback_text(args)
    except (FileNotFoundError, OSError) as exc:
        result = {"status": "error", "mode": "simulated",
                  "fallback_source": None, "error": str(exc),
                  "real_capture_error": real.get("error")}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    if not output_text.strip():
        result = {"status": "error", "mode": "simulated",
                  "fallback_source": None,
                  "error": "No fallback output available; real capture failed",
                  "real_capture_error": real.get("error")}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    simulated = build_simulated_text(args.command, output_text, cwd,
                                     short_path=args.prompt_short)
    stdin_rc, sim = run_term_shot(
        ["--stdin", "-o", args.output, "--columns", str(args.columns),
         "--rows", str(args.rows), "--theme", args.theme]
        + (["--transcript", args.transcript] if args.transcript else []),
        stdin_data=simulated.encode("utf-8", errors="replace"),
    )
    if sim.get("status") != "ok":
        sim["mode"] = "simulated"
        sim["fallback_source"] = source
        print(json.dumps(sim, ensure_ascii=False, indent=2))
        return stdin_rc

    sim["mode"] = "simulated"
    sim["fallback_source"] = source
    sim["real_capture_error"] = real.get("error")
    sim["command_exit_code"] = None
    print(json.dumps(sim, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
