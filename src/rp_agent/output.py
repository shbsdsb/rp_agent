"""统一输出回调:REPL 下默认落 stdout,TUI 下由 set_emit_target 重定向到输出区。

所有交互输出(shell 命令结果/chat 消息/错误提示)都经 emit(),界面层不感知输出目标。
"""
from __future__ import annotations

from typing import Callable

_emit_target: Callable[[str], None] = print


def emit(text: str) -> None:
    """输出一行文本,目标由 set_emit_target 决定(默认 print)。"""
    _emit_target(text)


def set_emit_target(fn: Callable[[str], None]) -> None:
    """重定向输出目标(如 TUI 输出区追加函数)。"""
    global _emit_target
    _emit_target = fn


def reset_emit_target() -> None:
    """恢复默认 print 目标。"""
    global _emit_target
    _emit_target = print


def is_tui() -> bool:
    """当前输出目标是否非默认 print(供 spinner 等降级用)。"""
    return _emit_target is not print
