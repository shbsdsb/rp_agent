"""终端颜色工具(ANSI,零依赖)。非 tty / NO_COLOR 时原样返回。"""
from __future__ import annotations

import os
import sys

_ANSI = {
    "yellow": "\033[1;33m",  # 黄 bold(与 prompt_toolkit ansiyellow bold 同步)
    "blue": "\033[96m",  # 亮天蓝(更浅)
    "gray": "\033[90m",
    "bold": "\033[1m",
}
_RESET = "\033[0m"


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


def rgb(text: str, r: int, g: int, b: int) -> str:
    """truecolor 着色(如 #FFE066 → rgb(255,224,102));禁用时原样返回。"""
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m" if _ENABLED else text
