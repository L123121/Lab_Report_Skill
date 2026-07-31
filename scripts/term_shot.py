#!/usr/bin/env python3
"""Capture command output through a terminal and render an ANSI-aware PNG."""

import argparse
import codecs
import datetime
import getpass
import json
import locale
import math
import ntpath
import os
import select
import shutil
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from code_shot import find_font

try:
    import pyte
except ImportError as exc:
    raise SystemExit("Missing dependency 'pyte'. Run the skill setup script first.") from exc

try:
    from wcwidth import wcwidth
except ImportError as exc:
    raise SystemExit("Missing dependency 'wcwidth'. Run the skill setup script first.") from exc

try:
    from winpty import PtyProcess
except ImportError:
    PtyProcess = None

DEFAULT_FONT_SIZE = 20
DEFAULT_PADDING = 30
DEFAULT_COLUMNS = 100
DEFAULT_ROWS = 30
DEFAULT_MAX_LINES = 500
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT = 300.0

THEMES = {
    "light": {
        "bg": (255, 255, 255),
        "fg": (24, 24, 24),
        "palette": {
            "black": (24, 24, 24),
            "red": (170, 35, 35),
            "green": (28, 130, 72),
            "brown": (145, 102, 0),
            "blue": (30, 92, 168),
            "magenta": (145, 55, 145),
            "cyan": (0, 125, 145),
            "white": (210, 210, 210),
            "brightblack": (95, 95, 95),
            "brightred": (220, 50, 47),
            "brightgreen": (50, 150, 80),
            "brightbrown": (181, 137, 0),
            "brightblue": (38, 110, 190),
            "brightmagenta": (190, 70, 190),
            "brightcyan": (0, 150, 170),
            "brightwhite": (120, 120, 120),
        },
    },
    "dark": {
        "bg": (12, 12, 12),
        "fg": (230, 230, 230),
        "palette": {
            "black": (0, 0, 0),
            "red": (205, 49, 49),
            "green": (13, 188, 121),
            "brown": (229, 229, 16),
            "blue": (36, 114, 200),
            "magenta": (188, 63, 188),
            "cyan": (17, 168, 205),
            "white": (229, 229, 229),
            "brightblack": (102, 102, 102),
            "brightred": (241, 76, 76),
            "brightgreen": (35, 209, 139),
            "brightbrown": (245, 245, 67),
            "brightblue": (59, 142, 234),
            "brightmagenta": (214, 112, 214),
            "brightcyan": (41, 184, 219),
            "brightwhite": (255, 255, 255),
        },
    },
}


class CaptureError(Exception):
    pass


@dataclass
class CaptureResult:
    text: str
    exit_code: Optional[int]
    mode: str
    shell: str
    timed_out: bool = False
    truncated: bool = False
    warnings: List[str] = field(default_factory=list)


def format_macos_prompt_path(work_dir: str) -> str:
    home = os.path.expanduser("~")
    work_dir = os.path.abspath(work_dir)
    if work_dir == home:
        return "~"
    return os.path.basename(work_dir.rstrip(os.sep)) or os.sep


def format_macos_hostname() -> str:
    return socket.gethostname().split(".", 1)[0]


def resolve_prompt_platform(platform: str) -> str:
    if platform != "auto":
        return platform
    return "windows" if os.name == "nt" else "mac"


def format_windows_prompt_path(work_dir: str, prompt_user: str, short: bool = False) -> str:
    work_dir = os.path.abspath(work_dir)
    if short:
        return os.path.basename(work_dir.rstrip(os.sep)) or os.sep
    if os.name == "nt":
        return ntpath.normpath(work_dir)
    home = os.path.expanduser("~")
    try:
        relative = os.path.relpath(work_dir, home)
    except ValueError:
        relative = None
    if relative and not relative.startswith(".."):
        parts = relative.replace(os.sep, "/").split("/")
        if parts == ["."]:
            return "C:\\Users\\%s" % prompt_user
        return "C:\\Users\\%s\\%s" % (prompt_user, "\\".join(parts))
    return "C:" + work_dir.replace("/", "\\")


def format_prompt(
    work_dir: str,
    command: str,
    prompt_user: str,
    prompt_host: str,
    platform: str,
    shell_name: str,
    short_path: bool = False,
) -> str:
    command = " ".join(command.splitlines())
    platform = resolve_prompt_platform(platform)
    if platform == "windows":
        display_cwd = format_windows_prompt_path(work_dir, prompt_user, short=short_path)
        if shell_name == "powershell":
            return "PS %s> %s" % (display_cwd, command)
        return "%s> %s" % (display_cwd, command)
    display_cwd = format_macos_prompt_path(work_dir)
    return "%s@%s %s %% %s" % (
        prompt_user,
        prompt_host,
        display_cwd,
        command,
    )


def resolve_shell(command: str, requested: str) -> Tuple[List[str], str]:
    shell_name = requested
    if shell_name == "auto":
        if os.name == "nt":
            shell_name = "cmd"
        else:
            configured = os.environ.get("SHELL") or "/bin/sh"
            base = os.path.basename(configured).lower()
            shell_name = base if base in {"bash", "zsh", "fish", "sh"} else "sh"

    if shell_name == "cmd":
        executable = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
        return [executable, "/d", "/s", "/c", command], "cmd"
    if shell_name == "powershell":
        executable = shutil.which("pwsh") or shutil.which("powershell.exe")
        if not executable:
            raise CaptureError("PowerShell executable was not found")
        return [executable, "-NoLogo", "-NoProfile", "-Command", command], "powershell"
    if shell_name in {"bash", "zsh", "fish", "sh"}:
        executable = shutil.which(shell_name)
        if not executable:
            raise CaptureError("Shell executable was not found: %s" % shell_name)
        option = "-lc" if shell_name in {"bash", "zsh", "fish"} else "-c"
        return [executable, option, command], shell_name
    raise CaptureError("Unsupported shell: %s" % requested)


def terminal_environment() -> Dict[str, str]:
    environment = dict(os.environ)
    environment.setdefault("TERM", "xterm-256color")
    environment.setdefault("COLORTERM", "truecolor")
    if os.name == "nt":
        environment.setdefault("PYTHONUTF8", "1")
        environment.setdefault("PYTHONIOENCODING", "utf-8")
    return environment


def windows_oem_encoding() -> Optional[str]:
    if os.name != "nt":
        return None
    try:
        import ctypes

        return "cp%d" % ctypes.windll.kernel32.GetOEMCP()
    except Exception:
        return None


def encoding_candidates(requested: str) -> List[str]:
    values: List[Optional[str]] = []
    if requested and requested != "auto":
        values.append(requested)
    values.extend([
        "utf-8",
        locale.getpreferredencoding(False),
        windows_oem_encoding(),
    ])
    result: List[str] = []
    for value in values:
        if value and value.lower() not in {item.lower() for item in result}:
            result.append(value)
    return result or ["utf-8"]


def decode_output_bytes(data: bytes, requested: str) -> Tuple[str, str]:
    candidates = encoding_candidates(requested)
    for encoding in candidates:
        try:
            return data.decode(encoding), encoding
        except (LookupError, UnicodeDecodeError):
            continue
    fallback = candidates[0]
    return data.decode(fallback, errors="replace"), fallback


def stream_encoding(requested: str) -> str:
    return encoding_candidates(requested)[0]


def _limit_text(text: str, max_bytes: int) -> Tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    clipped = encoded[:max_bytes]
    return clipped.decode("utf-8", errors="ignore"), True


def capture_with_winpty(
    argv: Sequence[str],
    cwd: str,
    environment: Mapping[str, str],
    rows: int,
    columns: int,
    timeout: float,
    max_bytes: int,
    shell_name: str,
) -> CaptureResult:
    if PtyProcess is None:
        raise CaptureError("pywinpty is not installed")

    process = PtyProcess.spawn(
        list(argv),
        cwd=cwd,
        env=dict(environment),
        dimensions=(rows, columns),
    )
    process.fileobj.settimeout(0.1)
    chunks: List[str] = []
    captured_bytes = 0
    deadline = time.monotonic() + timeout
    timed_out = False
    truncated = False
    quiet_after_exit = 0

    try:
        while True:
            if time.monotonic() >= deadline:
                timed_out = True
                process.terminate(force=True)
                break
            try:
                chunk = process.read(4096)
            except socket.timeout:
                if process.isalive():
                    continue
                quiet_after_exit += 1
                if quiet_after_exit >= 3:
                    break
                continue
            except EOFError:
                break

            if not chunk:
                continue
            quiet_after_exit = 0
            chunks.append(chunk)
            captured_bytes += len(chunk.encode("utf-8", errors="replace"))
            if captured_bytes > max_bytes:
                truncated = True
                process.terminate(force=True)
                break
    finally:
        if process.isalive() and (timed_out or truncated):
            process.terminate(force=True)

    exit_code = process.wait()
    try:
        process.close(force=True)
    except Exception:
        pass

    text, clipped = _limit_text("".join(chunks), max_bytes)
    truncated = truncated or clipped
    warnings: List[str] = []
    if timed_out:
        warnings.append("Command exceeded the timeout and was terminated")
    if truncated:
        warnings.append("Captured output exceeded the byte limit and was truncated")
    return CaptureResult(
        text=text,
        exit_code=exit_code,
        mode="conpty",
        shell=shell_name,
        timed_out=timed_out,
        truncated=truncated,
        warnings=warnings,
    )


def capture_with_posix_pty(
    argv: Sequence[str],
    cwd: str,
    environment: Mapping[str, str],
    rows: int,
    columns: int,
    timeout: float,
    max_bytes: int,
    encoding: str,
    shell_name: str,
) -> CaptureResult:
    import fcntl
    import pty
    import termios

    master_fd, slave_fd = pty.openpty()
    fcntl.ioctl(
        slave_fd,
        termios.TIOCSWINSZ,
        struct.pack("HHHH", rows, columns, 0, 0),
    )
    process = subprocess.Popen(
        list(argv),
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=cwd,
        env=dict(environment),
        close_fds=True,
    )
    os.close(slave_fd)
    decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
    chunks: List[str] = []
    captured_bytes = 0
    deadline = time.monotonic() + timeout
    timed_out = False
    truncated = False

    try:
        while True:
            if time.monotonic() >= deadline:
                timed_out = True
                process.kill()
                break
            readable, _, _ = select.select([master_fd], [], [], 0.1)
            if readable:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    data = b""
                if data:
                    chunks.append(decoder.decode(data))
                    captured_bytes += len(data)
                    if captured_bytes > max_bytes:
                        truncated = True
                        process.kill()
                        break
                elif process.poll() is not None:
                    break
            elif process.poll() is not None:
                break
    finally:
        os.close(master_fd)

    exit_code = process.wait()
    chunks.append(decoder.decode(b"", final=True))
    text, clipped = _limit_text("".join(chunks), max_bytes)
    truncated = truncated or clipped
    warnings: List[str] = []
    if timed_out:
        warnings.append("Command exceeded the timeout and was terminated")
    if truncated:
        warnings.append("Captured output exceeded the byte limit and was truncated")
    return CaptureResult(
        text=text,
        exit_code=exit_code,
        mode="pty",
        shell=shell_name,
        timed_out=timed_out,
        truncated=truncated,
        warnings=warnings,
    )


def capture_with_pipe(
    argv: Sequence[str],
    cwd: str,
    environment: Mapping[str, str],
    timeout: float,
    max_bytes: int,
    encoding: str,
    shell_name: str,
) -> CaptureResult:
    process = subprocess.Popen(
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=dict(environment),
    )
    timed_out = False
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        output, _ = process.communicate()

    output = output or b""
    truncated = len(output) > max_bytes
    if truncated:
        output = output[:max_bytes]
    text, used_encoding = decode_output_bytes(output, encoding)
    warnings = [
        "Pipe capture does not provide full TTY behavior; ANSI emission and buffering may differ",
        "Pipe output decoded as %s" % used_encoding,
    ]
    if timed_out:
        warnings.append("Command exceeded the timeout and was terminated")
    if truncated:
        warnings.append("Captured output exceeded the byte limit and was truncated")
    return CaptureResult(
        text=text,
        exit_code=process.returncode,
        mode="pipe",
        shell=shell_name,
        timed_out=timed_out,
        truncated=truncated,
        warnings=warnings,
    )


def capture_command(
    command: str,
    cwd: str,
    capture_mode: str,
    shell_request: str,
    rows: int,
    columns: int,
    timeout: float,
    max_bytes: int,
    encoding: str,
) -> CaptureResult:
    argv, shell_name = resolve_shell(command, shell_request)
    environment = terminal_environment()

    if capture_mode in {"auto", "pty"}:
        if os.name == "nt" and PtyProcess is not None:
            return capture_with_winpty(
                argv,
                cwd,
                environment,
                rows,
                columns,
                timeout,
                max_bytes,
                shell_name,
            )
        if os.name != "nt":
            return capture_with_posix_pty(
                argv,
                cwd,
                environment,
                rows,
                columns,
                timeout,
                max_bytes,
                stream_encoding(encoding),
                shell_name,
            )
        if capture_mode == "pty":
            raise CaptureError("PTY capture was requested but pywinpty is unavailable")

    return capture_with_pipe(
        argv,
        cwd,
        environment,
        timeout,
        max_bytes,
        encoding,
        shell_name,
    )


def normalize_pipe_newlines(text: str) -> str:
    result: List[str] = []
    previous = ""
    for character in text:
        if character == "\n" and previous != "\r":
            result.append("\r")
        result.append(character)
        previous = character
    return "".join(result)


def build_terminal_screen(
    terminal_text: str,
    columns: int,
    rows: int,
    max_lines: int,
) -> Any:
    history = max(1, max_lines - rows)
    screen = pyte.HistoryScreen(columns, rows, history=history, ratio=0.5)
    stream = pyte.Stream(screen)
    stream.feed(terminal_text)
    return screen


def screen_rows(screen: Any) -> List[Mapping[int, Any]]:
    rows: List[Mapping[int, Any]] = list(screen.history.top)
    rows.extend(screen.buffer[index] for index in range(screen.lines))
    while len(rows) > 1 and row_last_used_column(rows[-1], screen.default_char) == 0:
        rows.pop()
    return rows


def cell_is_visible(cell: Any) -> bool:
    return (
        cell.data not in {"", " "}
        or cell.bg != "default"
        or cell.reverse
        or cell.underscore
        or cell.strikethrough
    )


def row_last_used_column(row: Mapping[int, Any], default_char: Any) -> int:
    last_used = 0
    for column, cell in row.items():
        if cell_is_visible(cell):
            last_used = max(last_used, column + 1)
        elif cell.data == "" and cell != default_char:
            last_used = max(last_used, column + 1)
    return last_used


def screen_text(screen: Any) -> str:
    lines: List[str] = []
    for row in screen_rows(screen):
        last_used = row_last_used_column(row, screen.default_char)
        characters: List[str] = []
        for column in range(last_used):
            data = row.get(column, screen.default_char).data
            if data:
                characters.append(data)
        lines.append("".join(characters).rstrip())
    return "\n".join(lines).rstrip()


def resolve_color(value: str, theme: str, foreground: bool) -> Tuple[int, int, int]:
    theme_data = THEMES[theme]
    if value == "default":
        return theme_data["fg" if foreground else "bg"]
    if len(value) == 6:
        try:
            return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
        except ValueError:
            pass
    return theme_data["palette"].get(
        value,
        theme_data["fg" if foreground else "bg"],
    )


def load_explicit_font(value: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(value, size)
    except OSError as exc:
        raise CaptureError("Unable to load font: %s" % value) from exc


def find_cjk_font(size: int, explicit: Optional[str]) -> ImageFont.ImageFont:
    if explicit:
        return load_explicit_font(explicit, size)
    candidates = [
        "Sarasa Mono SC",
        "Sarasa Fixed SC",
        "Noto Sans Mono CJK SC",
        "Microsoft YaHei",
        "SimSun",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return find_font(size)


def font_metrics(font: ImageFont.ImageFont) -> Tuple[int, int]:
    try:
        return font.getmetrics()
    except AttributeError:
        bbox = font.getbbox("Mg")
        return bbox[3] - bbox[1], 0


def font_source(font: ImageFont.ImageFont) -> str:
    source = getattr(font, "path", None)
    if isinstance(source, bytes):
        return source.decode(errors="replace")
    if isinstance(source, (str, Path)):
        return str(source)
    return font.__class__.__name__


def render_terminal_image(
    screen: Any,
    theme: str,
    font_size: int,
    padding: int,
    output_path: str,
    scale: float,
    crop: bool,
    explicit_font: Optional[str],
    explicit_cjk_font: Optional[str],
) -> Tuple[str, Dict[str, Any]]:
    scaled_font_size = max(6, int(round(font_size * scale)))
    scaled_padding = max(0, int(round(padding * scale)))
    primary_font = (
        load_explicit_font(explicit_font, scaled_font_size)
        if explicit_font
        else find_font(scaled_font_size)
    )
    cjk_font = find_cjk_font(scaled_font_size, explicit_cjk_font)
    primary_ascent, primary_descent = font_metrics(primary_font)
    cjk_ascent, cjk_descent = font_metrics(cjk_font)
    line_height = max(
        primary_ascent + primary_descent,
        cjk_ascent + cjk_descent,
    ) + max(2, int(round(2 * scale)))
    primary_width = float(primary_font.getlength("M"))
    cjk_width = float(cjk_font.getlength("中")) / 2.0
    cell_width = max(1, int(math.ceil(max(primary_width, cjk_width))))

    rows = screen_rows(screen)
    used_columns = max(
        (row_last_used_column(row, screen.default_char) for row in rows),
        default=1,
    )
    visible_columns = max(1, min(screen.columns, used_columns if crop else screen.columns))
    image_width = scaled_padding * 2 + visible_columns * cell_width
    image_height = scaled_padding * 2 + max(1, len(rows)) * line_height
    image = Image.new("RGB", (image_width, image_height), THEMES[theme]["bg"])
    draw = ImageDraw.Draw(image)

    for row_index, row in enumerate(rows):
        y = scaled_padding + row_index * line_height
        for column in range(visible_columns):
            cell = row.get(column, screen.default_char)
            foreground = resolve_color(cell.fg, theme, True)
            background = resolve_color(cell.bg, theme, False)
            if cell.reverse:
                foreground, background = background, foreground
            x = scaled_padding + column * cell_width
            if background != THEMES[theme]["bg"]:
                draw.rectangle(
                    (x, y, x + cell_width, y + line_height),
                    fill=background,
                )
            if cell.data in {"", " "}:
                continue

            character_font = cjk_font if any(wcwidth(char) != 1 for char in cell.data) else primary_font
            # 同一行所有字符共享一条基线：以主字体的 ascent 定位基线，
            # 再按各字符所用字体的 ascent 计算绘制起点。不能用 getbbox
            # 逐字符定位——不同字符的 bbox 顶部不同（如 '(' 与 'M'），
            # 会导致同一行字母上下浮动。
            character_ascent, _ = font_metrics(character_font)
            baseline_y = y + primary_ascent
            text_y = baseline_y - character_ascent
            draw.text(
                (x, text_y),
                cell.data,
                fill=foreground,
                font=character_font,
                stroke_width=max(1, int(round(scale))) if cell.bold else 0,
                stroke_fill=foreground,
            )
            if cell.underscore:
                underline_y = y + line_height - max(1, int(round(2 * scale)))
                draw.line(
                    (x, underline_y, x + cell_width, underline_y),
                    fill=foreground,
                    width=max(1, int(round(scale))),
                )
            if cell.strikethrough:
                strike_y = y + line_height // 2
                draw.line(
                    (x, strike_y, x + cell_width, strike_y),
                    fill=foreground,
                    width=max(1, int(round(scale))),
                )

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output), "PNG")
    metadata = {
        "visible_lines": len(rows),
        "visible_columns": visible_columns,
        "terminal_columns": screen.columns,
        "terminal_rows": screen.lines,
        "pixel_width": image_width,
        "pixel_height": image_height,
        "font": font_source(primary_font),
        "cjk_font": font_source(cjk_font),
    }
    return str(output), metadata


def validate_arguments(args: argparse.Namespace) -> None:
    if bool(args.command) == bool(args.stdin):
        raise CaptureError("Specify exactly one of --command or --stdin")
    if args.columns < 20:
        raise CaptureError("--columns must be at least 20")
    if args.rows < 2:
        raise CaptureError("--rows must be at least 2")
    if args.max_lines < args.rows:
        raise CaptureError("--max-lines must be greater than or equal to --rows")
    if args.max_bytes < 1024:
        raise CaptureError("--max-bytes must be at least 1024")
    if args.timeout <= 0:
        raise CaptureError("--timeout must be positive")
    if args.font_size <= 0 or args.scale <= 0 or args.padding < 0:
        raise CaptureError("Font size, scale, and padding values are invalid")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture real terminal output and render an ANSI-aware PNG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  term-shot -c 'python experiment.py'\n"
            "  term-shot -c 'pytest -q' --columns 110 --theme dark\n"
            "  echo 'output' | term-shot --stdin\n"
            "\n"
            "Note: on Windows, the default ConPTY path decodes through the\n"
            "console code page (usually GBK/cp936). If a program prints\n"
            "UTF-8 Chinese and the screenshot shows mojibake, add\n"
            "  --capture-mode pipe\n"
            "or prefix the command with 'chcp 65001 >nul && '."
        ),
    )
    parser.add_argument("-c", "--command", help="Command to execute")
    parser.add_argument("--cwd", help="Working directory for the command")
    parser.add_argument("--stdin", action="store_true", help="Read terminal text from stdin")
    parser.add_argument("-o", "--output", help="Output PNG path")
    parser.add_argument("--transcript", help="Write the final visible terminal text to UTF-8")
    parser.add_argument("-L", "--language", default="console", help=argparse.SUPPRESS)
    parser.add_argument("--theme", choices=sorted(THEMES), default="light")
    parser.add_argument("--dark", action="store_true", help="Equivalent to --theme dark")
    parser.add_argument(
        "--capture-mode",
        choices=["auto", "pty", "pipe"],
        default="auto",
        help="Terminal capture mode; auto prefers PTY/ConPTY",
    )
    parser.add_argument(
        "--shell",
        choices=["auto", "cmd", "powershell", "bash", "zsh", "fish", "sh"],
        default="auto",
        help="Shell used to execute the command",
    )
    parser.add_argument("--columns", type=int, default=DEFAULT_COLUMNS)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--encoding",
        default="auto",
        help="Output decoding: auto tries UTF-8, system, then Windows OEM encoding",
    )
    parser.add_argument(
        "--allow-nonzero",
        action="store_true",
        help="Return success even when the captured command exits nonzero",
    )
    parser.add_argument("--no-prompt", action="store_true", help="Do not add a synthetic prompt line")
    parser.add_argument(
        "--prompt-short",
        action="store_true",
        help="Show only the current directory name in the prompt instead of the full path",
    )
    parser.add_argument("--no-crop", action="store_true", help="Keep the full terminal column width")
    parser.add_argument(
        "--prompt-platform",
        choices=["auto", "mac", "windows"],
        default="auto",
    )
    parser.add_argument("--prompt-user", default=getpass.getuser())
    parser.add_argument("--prompt-host", default=format_macos_hostname())
    parser.add_argument("--font", help="Primary terminal font name or path")
    parser.add_argument("--cjk-font", help="CJK fallback font name or path")
    parser.add_argument("--font-size", type=int, default=DEFAULT_FONT_SIZE)
    parser.add_argument("--padding", type=int, default=DEFAULT_PADDING)
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--json", action="store_true", help="Print machine-readable result JSON")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.json and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        validate_arguments(args)
        if args.dark:
            args.theme = "dark"

        work_dir = os.getcwd()
        if args.cwd:
            work_dir = os.path.abspath(os.path.expanduser(args.cwd))
        if not os.path.isdir(work_dir):
            raise CaptureError("Working directory does not exist: %s" % work_dir)

        if args.command:
            capture = capture_command(
                command=args.command,
                cwd=work_dir,
                capture_mode=args.capture_mode,
                shell_request=args.shell,
                rows=args.rows,
                columns=args.columns,
                timeout=args.timeout,
                max_bytes=args.max_bytes,
                encoding=args.encoding,
            )
            output_text = capture.text
            if capture.mode == "pipe":
                output_text = normalize_pipe_newlines(output_text)
            prompt = ""
            if not args.no_prompt:
                prompt = format_prompt(
                    work_dir=work_dir,
                    command=args.command,
                    prompt_user=args.prompt_user,
                    prompt_host=args.prompt_host,
                    platform=args.prompt_platform,
                    shell_name=capture.shell,
                    short_path=args.prompt_short,
                )
            terminal_text = (prompt + "\r\n" if prompt else "") + output_text
        else:
            stdin_bytes = sys.stdin.buffer.read()
            stdin_text, stdin_encoding = decode_output_bytes(stdin_bytes, args.encoding)
            terminal_text = normalize_pipe_newlines(stdin_text)
            capture = CaptureResult(
                text=stdin_text,
                exit_code=None,
                mode="stdin",
                shell="none",
                warnings=["Stdin decoded as %s" % stdin_encoding],
            )

        estimated_lines = terminal_text.count("\n") + 1
        if estimated_lines > args.max_lines:
            capture.warnings.append(
                "Terminal history exceeded --max-lines; oldest rows may be omitted"
            )
        screen = build_terminal_screen(
            terminal_text=terminal_text,
            columns=args.columns,
            rows=args.rows,
            max_lines=args.max_lines,
        )

        if args.output:
            output_path = args.output
        else:
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            output_path = "term-shot-%s.png" % timestamp

        transcript_path = None
        if args.transcript:
            transcript = Path(args.transcript).expanduser().resolve()
            transcript.parent.mkdir(parents=True, exist_ok=True)
            transcript.write_text(screen_text(screen) + "\n", encoding="utf-8")
            transcript_path = str(transcript)

        result_path, render_metadata = render_terminal_image(
            screen=screen,
            theme=args.theme,
            font_size=args.font_size,
            padding=args.padding,
            output_path=output_path,
            scale=args.scale,
            crop=not args.no_crop,
            explicit_font=args.font,
            explicit_cjk_font=args.cjk_font,
        )

        command_failed = capture.exit_code not in {None, 0}
        status = "ok"
        if capture.timed_out or capture.truncated:
            status = "error"
        elif command_failed and not args.allow_nonzero:
            status = "error"
        if command_failed and args.allow_nonzero:
            capture.warnings.append(
                "Command exited nonzero but --allow-nonzero was specified"
            )

        error_message = None
        if capture.timed_out:
            error_message = "Command timed out"
        elif capture.truncated:
            error_message = "Captured output was truncated"
        elif command_failed and not args.allow_nonzero:
            error_message = "Command exited with code %s" % capture.exit_code

        result = {
            "status": status,
            "path": result_path,
            "transcript": transcript_path,
            "capture_mode": capture.mode,
            "shell": capture.shell,
            "command_exit_code": capture.exit_code,
            "timed_out": capture.timed_out,
            "truncated": capture.truncated,
            "prompt_synthetic": bool(args.command and not args.no_prompt),
            "warnings": capture.warnings,
            "render": render_metadata,
        }
        if error_message:
            result["error"] = error_message
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("Saved: %s" % result_path)
            print("Capture mode: %s" % capture.mode)
            if capture.exit_code is not None:
                print("Command exit code: %s" % capture.exit_code)
            for warning in capture.warnings:
                print("Warning: %s" % warning)

        return 0 if status == "ok" else 1
    except (CaptureError, OSError, UnicodeError) as exc:
        result = {"status": "error", "error": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("Error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())