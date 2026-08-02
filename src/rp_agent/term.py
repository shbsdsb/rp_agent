"""终端颜色工具(ANSI,零依赖)。非 tty / NO_COLOR 时原样返回。"""
from __future__ import annotations

import os
import sys

_ANSI = {
    "yellow": "\033[33m",
    "blue": "\033[96m",  # 亮天蓝(更浅)
    "gray": "\033[90m",
    "bold": "\033[1m",
}
_RESET = "\033[0m"
_INPUT_ESCAPE = "\033[96m"  # 输入回显色:亮天蓝


def supports_color() -> bool:
    """是否启用颜色:stdout 是 tty 且未设 NO_COLOR;Windows 启用 VT 模式。"""
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except (AttributeError, OSError):
            return False
    return True


_ENABLED = supports_color()


def yellow(text: str) -> str:
    return f"{_ANSI['yellow']}{text}{_RESET}" if _ENABLED else text


def blue(text: str) -> str:
    return f"{_ANSI['blue']}{text}{_RESET}" if _ENABLED else text


def gray(text: str) -> str:
    return f"{_ANSI['gray']}{text}{_RESET}" if _ENABLED else text


def bold(text: str) -> str:
    return f"{_ANSI['bold']}{text}{_RESET}" if _ENABLED else text


def input_prompt(text: str) -> str:
    """构造输入提示符:文字白色,用户输入回显亮天蓝。非 tty 原样返回。"""
    if not _ENABLED:
        return text
    return _RESET + text + _INPUT_ESCAPE


def reset_after_input() -> None:
    """输入后重置终端颜色(避免污染后续输出)。非 tty 无操作。"""
    if _ENABLED:
        sys.stdout.write(_RESET)
        sys.stdout.flush()
