#!/usr/bin/env python3
"""
code-shot - 终端风格的代码截图命令行工具。
将代码文件渲染为带有语法高亮的 PNG 图像，样式类似于终端。
专为 Agent 设计：输出整洁，支持 JSON 模式，行为可预测。
"""

import argparse
import datetime
import getpass
import os
import socket
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pygments.lexers import get_lexer_for_filename, get_lexer_by_name, guess_lexer
from pygments.styles import get_style_by_name, get_all_styles
from pygments.token import Token
from pygments.util import ClassNotFound

# ---- 默认设置 ----
LIGHT_THEME = "default"              # Pygments 默认主题（浅色背景）
DARK_THEME = "monokai"               # 深色背景主题
DEFAULT_FONT_SIZE = 20
DEFAULT_PADDING = 30
# 浅色模式（默认）
BG_COLOR = (248, 248, 248)           # 近似白色的背景
LINE_NO_COLOR = (180, 180, 180)      # 中等灰色的行号
DEFAULT_FG = (30, 30, 30)            # 近似黑色的前景
# 深色模式
DARK_BG = (30, 30, 30)
DARK_FG = (248, 248, 242)
DARK_LINE_NO_COLOR = (128, 128, 128)


def parse_color(hex_str, default=DEFAULT_FG):
    """将 CSS 十六进制颜色字符串解析为 RGB 元组。"""
    if not hex_str:
        return default
    h = hex_str.lstrip("#")
    if len(h) == 6:
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    return default


def parse_line_ranges(ranges_str, total_lines):
    """
    将行范围字符串解析为已排序、已合并的 (start, end) 元组列表。
    格式示例: "10-25", "10-25,30-40", "10-", "-25", "42"
    所有数字均从 1 开始且包含边界。
    """
    if not ranges_str:
        return [(1, total_lines)]

    ranges = []
    for part in ranges_str.split(","):
        part = part.strip()
        if "-" not in part:
            n = int(part)
            ranges.append((n, n))
        else:
            a, b = part.split("-", 1)
            start = int(a) if a else 1
            end = int(b) if b else total_lines
            if start > end:
                raise ValueError(f"无效范围: {start}-{end} (起始行大于结束行)")
            ranges.append((start, end))

    ranges.sort()
    merged = []
    for s, e in ranges:
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def find_font(size):
    """查找可用的等宽字体。如果找不到，则回退到 PIL 默认字体。

    优先尝试常见等宽字体的完整文件路径（PIL 在 Windows 上常无法用裸
    字体名加载），并对候选做等宽性验证（'M' 与 'i' 宽度应一致），避免
    回退到非等宽字体导致字母间距过大。
    """
    import os

    candidates = (
        "C:/Windows/Fonts/consola.ttf",       # Consolas
        "C:/Windows/Fonts/consolab.ttf",
        "C:/Windows/Fonts/consolai.ttf",
        "C:/Windows/Fonts/cour.ttf",          # Courier New
        "C:/Windows/Fonts/courbd.ttf",
        "C:/Windows/Fonts/cascadia.ttf",      # Cascadia Code
        "C:/Windows/Fonts/cascadiamono.ttf",
        "Consolas", "Cascadia Code", "Cascadia Mono",
        "Courier New", "Menlo", "Monaco", "Courier",
    )
    for name in candidates:
        try:
            if os.path.isfile(name):
                font = ImageFont.truetype(name, size)
            else:
                font = ImageFont.truetype(name, size)
            # 等宽验证：'M' 与 'i' 的 advance 应一致
            if abs(font.getlength("M") - font.getlength("i")) < 0.5:
                return font
        except OSError:
            continue
    return ImageFont.load_default()


def find_cjk_font(size, explicit=None):
    """查找可用的中文字体（用于渲染中文注释等 CJK 字符）。"""
    if explicit:
        try:
            return ImageFont.truetype(explicit, size)
        except OSError:
            pass
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",   # 微软雅黑
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simsun.ttc", # 宋体
        "C:/Windows/Fonts/simhei.ttf", # 黑体
        "Sarasa Mono SC",
        "Sarasa Fixed SC",
        "Noto Sans Mono CJK SC",
        "Microsoft YaHei",
        "SimSun",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for name in candidates:
        try:
            font = ImageFont.truetype(name, size)
            if abs(font.getlength("中") - 2 * font.getlength("X")) < 4:
                return font
            return font
        except OSError:
            continue
    return None


def _text_display_width(text, char_width):
    """按终端显示宽度计算文本宽度（CJK 字符占 2 个 ASCII 单元）。"""
    try:
        from wcwidth import wcwidth
    except ImportError:
        wcwidth = lambda ch: 1
    total = 0
    for ch in text:
        w = wcwidth(ch)
        total += char_width * (w if w > 0 else 1)
    return total


def build_lines(tokens):
    """
    将 pygments 标记流转换为行列表。
    每一行都是 (文本, 标记类型) 段的列表。
    处理制表符 (Tab) 到 4 个空格的转换以及末尾空行。
    """
    lines = []
    current_line = []

    for token_type, text in tokens:
        parts = text.split("\n")
        for i, part in enumerate(parts):
            # 制表符 → 4 个空格
            expanded = part.replace("\t", "    ")
            if expanded:
                current_line.append((expanded, token_type))
            if i < len(parts) - 1:
                lines.append(current_line)
                current_line = []

    # 如果源文件以 \n 结尾，不要吞掉末尾的空行
    if current_line:
        lines.append(current_line)

    return lines


def _token_fg(token_type, style_rules, default=DEFAULT_FG):
    """向上遍历标记层级结构，查找最具体的前景颜色。"""
    t = token_type
    while t is not Token:
        if t in style_rules:
            return style_rules[t]
        t = t.parent
    return default


def render_image(lines, style_name, font_size, padding, show_line_numbers, start_line, output_path, dark=False):
    """将预构建的行渲染为 PNG 图像。返回绝对输出路径。"""
    font = find_font(font_size)
    cjk_font = find_cjk_font(font_size)

    # 字符度量（等宽字体：所有字符宽度相同）
    bbox = font.getbbox("X")
    char_width = bbox[2] - bbox[0]
    ascent, descent = font.getmetrics()
    cjk_ascent, cjk_descent = (cjk_font.getmetrics() if cjk_font else (ascent, descent))
    # 行高取主字体与 CJK 字体的较大者，避免中文溢出
    line_height = max(ascent + descent, cjk_ascent + cjk_descent) + 2  # 行间距为 2 px

    # ---- 计算图像尺寸（按终端显示宽度：CJK 字符占 2 单元）----
    # _text_display_width 已返回像素宽度，max_line_len 直接作为内容宽度
    max_line_len = 0
    for line in lines:
        line_len = sum(_text_display_width(seg[0], char_width) for seg in line)
        max_line_len = max(max_line_len, line_len)

    line_no_width = 0
    if show_line_numbers:
        max_line_no = start_line + len(lines) - 1
        gutter_chars = max(len(str(max_line_no)), 4) + 1  # +1 用于末尾空格
        line_no_width = gutter_chars * char_width

    content_w = max_line_len
    total_w = padding * 2 + line_no_width + max(content_w, 1)
    total_h = padding * 2 + len(lines) * line_height

    if total_w < 200:
        total_w = padding * 2 + line_no_width + 200
    if len(lines) == 0:
        total_h = padding * 2 + line_height  # 至少一行高

    # ---- 创建图像 ----
    img = Image.new("RGB", (total_w, total_h), DARK_BG if dark else BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ---- 构建样式颜色映射表 ----
    pyg_style = get_style_by_name(style_name)
    style_rules = {}
    for ttype, tstyle in pyg_style:
        fg = parse_color(tstyle.get("color"))
        style_rules[ttype] = fg

    # ---- 渲染 ----
    default_fg = DARK_FG if dark else DEFAULT_FG
    line_no_clr = DARK_LINE_NO_COLOR if dark else LINE_NO_COLOR
    y = padding
    line_num = start_line

    for line in lines:
        x = padding + line_no_width

        if show_line_numbers:
            ln_text = str(line_num).rjust(line_no_width // char_width - 1)
            draw.text((padding, y), ln_text, fill=line_no_clr, font=font)

        # Merge adjacent same-color segments to reduce draw.text calls
        merged = []
        for text, token_type in line:
            fg = _token_fg(token_type, style_rules, default_fg)
            if merged and merged[-1][0] == fg:
                merged[-1] = (fg, merged[-1][1] + text)
            else:
                merged.append((fg, text))
        for fg, text in merged:
            # 含 CJK 字符的段用中文字体渲染，并按显示宽度推进；
            # CJK 字符按共享基线定位（基线 = y + 主字体 ascent），
            # 避免中文因 CJK 字体 ascent 更大而整体偏下。
            if cjk_font and any(ord(ch) > 0x2E7F for ch in text):
                baseline_y = y + ascent
                for ch in text:
                    if ord(ch) > 0x2E7F:
                        draw.text((x, baseline_y - cjk_ascent), ch, fill=fg, font=cjk_font)
                        x += 2 * char_width
                    else:
                        draw.text((x, y), ch, fill=fg, font=font)
                        x += char_width
            else:
                draw.text((x, y), text, fill=fg, font=font)
                x += len(text) * char_width

        y += line_height
        line_num += 1

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "PNG")
    return os.path.abspath(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="专为 Agent 设计的终端风格代码截图工具。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  code-shot -f app.py\n"
               "  code-shot -f app.py -l 10-25 --dark\n"
               "  code-shot -c 'python experiment.py' -o result.png\n"
               "  echo 'print(1)' | code-shot --stdin -L python\n"
               "  code-shot --text 'SELECT 1;' -L sql -o query.png",
    )
    parser.add_argument("-f", "--file", help="代码文件路径")
    parser.add_argument("-l", "--lines", help='行范围，例如 "10-25" 或 "10-25,30-40"')
    parser.add_argument("-o", "--output", help="输出 PNG 路径（默认：自动生成）")
    parser.add_argument("-t", "--theme", help="Pygments 样式名称（默认：浅色为 'default'，深色为 'monokai'）")
    parser.add_argument("--font-size", type=int, default=DEFAULT_FONT_SIZE, help=f"字体大小，单位 px（默认：{DEFAULT_FONT_SIZE}）")
    parser.add_argument("--padding", type=int, default=DEFAULT_PADDING, help=f"内边距，单位 px（默认：{DEFAULT_PADDING}）")
    parser.add_argument("--scale", type=float, default=2, help="高 DPI 渲染的缩放因子（默认：2）")
    parser.add_argument("--no-line-numbers", action="store_true", help="不显示行号")
    parser.add_argument("--dark", action="store_true", help="使用深色终端风格背景（默认使用浅色背景）")
    parser.add_argument("--list-themes", action="store_true", help="列出所有可用的主题名称并退出")
    parser.add_argument("--json", action="store_true", help="成功后输出 JSON 格式（方便 Agent 调用）")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取代码/文本")
    parser.add_argument("--text", help="直接传入文本内容（适用于短文本）")
    parser.add_argument("-c", "--command", help="执行命令并截图其输出（自动包含终端提示符）")
    parser.add_argument("-L", "--language", help="手动指定 Pygments lexer 名称（如 bash, python, console, json）")
    args = parser.parse_args()

    # --list-themes (不需要文件)
    if args.list_themes:
        for name in sorted(get_all_styles()):
            print(name)
        return

    # 输入源解析：优先级 --command > --text > --stdin > --file
    filepath = None
    if args.command:
        try:
            result = subprocess.run(
                args.command, shell=True, capture_output=True, text=True,
                timeout=120, cwd=os.getcwd(),
            )
        except subprocess.TimeoutExpired:
            print('{"error": "命令执行超时 (120s)"}' if args.json else "错误: 命令执行超时 (120s)", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            msg = f"命令执行失败: {e}"
            print(f'{{"error": "{msg}"}}' if args.json else f"错误: {msg}", file=sys.stderr)
            sys.exit(1)
        # 构建终端提示符行
        user = getpass.getuser()
        host = socket.gethostname()
        try:
            cwd = os.getcwd().replace(os.path.expanduser("~"), "~")
        except Exception:
            cwd = os.getcwd()
        output_text = result.stdout
        if result.stderr:
            output_text += result.stderr
        if output_text and not output_text.endswith("\n"):
            output_text += "\n"
        if os.name == "nt":
            code = f"{cwd}> {args.command}\n{output_text}"
        else:
            code = f"{user}@{host} {cwd} % {args.command}\n{output_text}"
    elif args.text is not None:
        code = args.text
    elif args.stdin:
        code = sys.stdin.read()
    elif args.file:
        filepath = Path(args.file).resolve()
        if not filepath.exists():
            print(f'{{"error": "file not found", "path": "{args.file}"}}' if args.json else f"错误: 找不到文件: {args.file}", file=sys.stderr)
            sys.exit(1)
        try:
            code = filepath.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                code = filepath.read_text(encoding="gbk")
            except Exception as e:
                msg = f"无法读取文件: {e}"
                print(f'{{"error": "{msg}"}}' if args.json else f"错误: {msg}", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            msg = f"无法读取文件: {e}"
            print(f'{{"error": "{msg}"}}' if args.json else f"错误: {msg}", file=sys.stderr)
            sys.exit(1)
    else:
        print('{"error": "必须指定 -c、--text、--stdin 或 -f 之一"}' if args.json else "错误: 必须指定 -c、--text、--stdin 或 -f/--file 之一", file=sys.stderr)
        sys.exit(1)

    all_lines = code.split("\n")
    total_lines = len(all_lines)

    # 解析行范围
    try:
        ranges = parse_line_ranges(args.lines, total_lines)
    except ValueError as e:
        msg = f"无效的行范围: {e}"
        print(f'{{"error": "{msg}"}}' if args.json else f"错误: {msg}", file=sys.stderr)
        sys.exit(1)

    # 验证范围
    for s, e in ranges:
        if s < 1 or e > total_lines:
            msg = f"行范围 {s}-{e} 超出边界（文件共有 {total_lines} 行）"
            print(f'{{"error": "{msg}"}}' if args.json else f"错误: {msg}", file=sys.stderr)
            sys.exit(1)

    # 提取选定的行
    selected_lines = []
    for s, e in ranges:
        selected_lines.extend(all_lines[s - 1 : e])

    selected_code = "\n".join(selected_lines)
    start_line = ranges[0][0]

    # 检测词法分析器 (Lexer)
    if args.language:
        try:
            lexer = get_lexer_by_name(args.language, stripall=False)
        except ClassNotFound:
            msg = f"找不到 lexer '{args.language}'"
            print(f'{{"error": "{msg}"}}' if args.json else f"错误: {msg}", file=sys.stderr)
            sys.exit(1)
    elif args.command:
        # 命令模式默认使用 console lexer（高亮提示符和输出）
        try:
            lexer = get_lexer_by_name("console", stripall=False)
        except ClassNotFound:
            lexer = get_lexer_by_name("text", stripall=False)
    elif filepath:
        try:
            lexer = get_lexer_for_filename(str(filepath))
        except ClassNotFound:
            try:
                lexer = guess_lexer(code)
            except ClassNotFound:
                lexer = get_lexer_by_name("text", stripall=False)
    else:
        # stdin/text 模式：尝试自动检测，失败则用纯文本
        try:
            lexer = guess_lexer(code)
        except ClassNotFound:
            lexer = get_lexer_by_name("text", stripall=False)

    # 标记化 (Tokenize) → 构建显示行
    tokens = list(lexer.get_tokens(selected_code))
    display_lines = build_lines(tokens)

    # 输出路径
    if args.output:
        output_path = args.output
    elif filepath:
        stem = filepath.stem
        range_tag = args.lines.replace(",", "_").replace("-", "_") if args.lines else "full"
        output_path = f"{stem}-L{range_tag}.png"
    else:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = f"code-shot-{ts}.png"

    # 确定主题：用户指定 > 模式默认
    theme = args.theme or (DARK_THEME if args.dark else LIGHT_THEME)

    # 应用缩放以进行高 DPI 渲染
    font_size = int(args.font_size * args.scale)
    padding = int(args.padding * args.scale)

    # 渲染
    try:
        result = render_image(
            display_lines, theme, font_size, padding,
            not args.no_line_numbers, start_line, output_path, args.dark,
        )
    except ClassNotFound:
        msg = f"找不到主题 '{theme}'。使用 --list-themes 查看可用主题。"
        print(f'{{"error": "{msg}"}}' if args.json else f"错误: {msg}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(f'{{"status": "ok", "path": "{result}"}}')
    else:
        print(f"已保存: {result}")


if __name__ == "__main__":
    main()
