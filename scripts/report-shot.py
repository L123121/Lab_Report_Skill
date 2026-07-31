#!/usr/bin/env python3
"""
report-shot - 实验报告批量截图工具。

读取 JSON 配置文件，批量调用 code-shot 和 term-shot 生成截图，
输出截图路径列表供后续组装实验报告使用。

配置文件格式:
{
  "output_dir": "screenshots",   // 可选，默认 screenshots
  "code_files": [
    {"path": "src/main.py", "output": "main.png", "lines": "1-50", "dark": false},
    {"path": "src/utils.py", "output": "utils.png", "dark": true}
  ],
  "commands": [
    {"command": "python main.py", "output": "run.png", "transcript": "run.txt", "cwd": "src", "columns": 100},
    {"command": "pytest", "output": "test.png", "theme": "dark"}
  ]
}

输出 JSON:
{
  "status": "ok",
  "screenshots": [
    {"type": "code", "path": "/abs/screenshots/main.png", "caption": "main.py"},
    {"type": "term", "path": "/abs/screenshots/run.png", "caption": "python main.py", "capture_mode": "pty", "command_exit_code": 0, "transcript": "/abs/screenshots/run.txt"}
  ],
  "errors": []  // 如有失败项
}
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def run_code_shot(config, output_dir):
    """调用 code-shot 生成代码截图。"""
    script_dir = Path(__file__).parent.resolve()
    code_shot = script_dir / "code_shot.py"

    filepath = config["path"]
    output_name = config.get("output", f"{Path(filepath).stem}.png")
    output_path = os.path.join(output_dir, output_name)

    cmd = [sys.executable, str(code_shot), "-f", filepath, "-o", output_path, "--json"]

    if config.get("lines"):
        cmd.extend(["-l", config["lines"]])
    if config.get("dark"):
        cmd.append("--dark")
    if config.get("no_line_numbers"):
        cmd.append("--no-line-numbers")
    if config.get("font_size"):
        cmd.extend(["--font-size", str(config["font_size"])])
    if config.get("language"):
        cmd.extend(["-L", config["language"]])

    return _run(cmd, "code", output_path, filepath)


def run_term_shot(config, output_dir):
    """调用 term-shot 生成终端输出截图。"""
    script_dir = Path(__file__).parent.resolve()
    term_shot = script_dir / "term_shot.py"

    command = config["command"]
    command_id = hashlib.sha256(command.encode("utf-8")).hexdigest()[:8]
    output_name = config.get("output", f"term-{command_id}.png")
    output_path = os.path.join(output_dir, output_name)
    cmd = [sys.executable, str(term_shot), "-c", command, "-o", output_path, "--json"]

    option_flags = {
        "cwd": "--cwd",
        "theme": "--theme",
        "capture_mode": "--capture-mode",
        "shell": "--shell",
        "columns": "--columns",
        "rows": "--rows",
        "max_lines": "--max-lines",
        "max_bytes": "--max-bytes",
        "timeout": "--timeout",
        "encoding": "--encoding",
        "prompt_platform": "--prompt-platform",
        "prompt_user": "--prompt-user",
        "prompt_host": "--prompt-host",
        "font": "--font",
        "cjk_font": "--cjk-font",
        "font_size": "--font-size",
        "padding": "--padding",
        "scale": "--scale",
    }
    for key, flag in option_flags.items():
        if key in config and config[key] is not None:
            cmd.extend([flag, str(config[key])])

    transcript_name = config.get("transcript")
    if transcript_name:
        transcript_path = Path(transcript_name)
        if not transcript_path.is_absolute():
            transcript_path = Path(output_dir) / transcript_path
        cmd.extend(["--transcript", str(transcript_path)])

    boolean_flags = {
        "dark": "--dark",
        "allow_nonzero": "--allow-nonzero",
        "no_prompt": "--no-prompt",
        "no_crop": "--no-crop",
    }
    for key, flag in boolean_flags.items():
        if config.get(key):
            cmd.append(flag)

    wrapper_timeout = float(config.get("timeout", 300)) + 60
    return _run(cmd, "term", output_path, command, wrapper_timeout)


def _run(cmd, shot_type, output_path, caption, timeout=300):
    """执行截图命令，返回结果字典。"""
    try:
        environment = dict(os.environ)
        environment.setdefault("PYTHONUTF8", "1")
        environment.setdefault("PYTHONIOENCODING", "utf-8")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=environment,
        )
        output = result.stdout.strip()
        parsed = {}
        path = os.path.abspath(output_path)
        try:
            parsed = json.loads(output)
            if parsed.get("path"):
                path = os.path.abspath(parsed["path"])
        except (json.JSONDecodeError, TypeError):
            parsed = {}

        item = {
            "type": shot_type,
            "caption": caption,
            "path": path if os.path.exists(path) else None,
            "capture_mode": parsed.get("capture_mode"),
            "command_exit_code": parsed.get("command_exit_code"),
            "warnings": parsed.get("warnings", []),
            "transcript": parsed.get("transcript"),
        }

        if result.returncode != 0:
            error_msg = (
                parsed.get("error")
                or result.stderr.strip()
                or "Screenshot command returned exit code %s" % result.returncode
            )
            item.update({"success": False, "error": error_msg})
            return item

        item["success"] = True
        return item
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "截图超时 (%ss)" % timeout,
            "type": shot_type,
            "caption": caption,
            "path": os.path.abspath(output_path) if os.path.exists(output_path) else None,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "type": shot_type,
            "caption": caption,
            "path": os.path.abspath(output_path) if os.path.exists(output_path) else None,
        }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="实验报告批量截图工具 - 根据配置文件批量生成代码和终端截图",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python scripts/report-shot.py report-config.json\n"
               "  python scripts/report-shot.py config.json --output-dir my-shots\n",
    )
    parser.add_argument("config", help="JSON 配置文件路径")
    parser.add_argument("--output-dir", help="截图输出目录（覆盖配置文件中的 output_dir）")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="仅输出 JSON 结果")
    args = parser.parse_args()

    # 读取配置
    config_path = Path(args.config)
    if not config_path.exists():
        result = {"status": "error", "error": f"配置文件不存在: {args.config}"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as e:
        result = {"status": "error", "error": f"配置文件解析失败: {e}"}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    # 确定输出目录
    output_dir = args.output_dir or config.get("output_dir", "screenshots")
    os.makedirs(output_dir, exist_ok=True)
    output_dir = str(Path(output_dir).resolve())

    screenshots = []
    errors = []

    # 处理代码文件
    for code_config in config.get("code_files", []):
        if "path" not in code_config:
            errors.append({"error": "code_files 项缺少 path 字段", "config": code_config})
            continue
        result = run_code_shot(code_config, output_dir)
        if result["success"]:
            screenshots.append(result)
            if not args.json_output:
                print(f"[code-shot] ✓ {result['caption']} -> {result['path']}")
        else:
            errors.append(result)
            if not args.json_output:
                print(f"[code-shot] ✗ {result['caption']}: {result['error']}")

    # 处理命令
    for cmd_config in config.get("commands", []):
        if "command" not in cmd_config:
            errors.append({"error": "commands 项缺少 command 字段", "config": cmd_config})
            continue
        result = run_term_shot(cmd_config, output_dir)
        if result["success"]:
            screenshots.append(result)
            if not args.json_output:
                print(f"[term-shot] ✓ {result['caption']} -> {result['path']}")
        else:
            errors.append(result)
            if not args.json_output:
                print(f"[term-shot] ✗ {result['caption']}: {result['error']}")

    # 输出结果
    status = "ok" if not errors else ("partial" if screenshots else "error")
    result = {
        "status": status,
        "screenshots": [
            {
                key: value
                for key, value in s.items()
                if key in {
                    "type", "path", "caption", "capture_mode",
                    "command_exit_code", "warnings", "transcript",
                } and value is not None
            }
            for s in screenshots
        ],
        "errors": [
            {
                key: value
                for key, value in e.items()
                if key in {
                    "type", "path", "caption", "error", "capture_mode",
                    "command_exit_code", "warnings", "transcript",
                } and value is not None
            }
            for e in errors
        ],
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
