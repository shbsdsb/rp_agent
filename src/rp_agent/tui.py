"""全屏 TUI:三区布局(状态栏/可滚动输出区/输入框)。

滚动用 _tail_offset(距末尾偏移行数,0=贴底)对输出行切片渲染,
完全绕开 prompt_toolkit 锚点(光标)滚动机制——锚点在可视区内移动时视图不跟随是历史 bug 根因。
"""
from __future__ import annotations

MAX_LINES = 5000

_output_lines: list = []  # list[FormattedText],TUI 会话期间输出历史(跨界面切换保留)
_tail_offset = 0  # 0 = 贴底显示最新;正数 = 向上回看 offset 行


def visible_slice(total: int, height: int, tail_offset: int) -> tuple[int, int]:
    """可见行区间 [start, end):height 可视高度,tail_offset 距末尾偏移。

    先经 clamp_offset 钳制,确保超界 offset 落回合法范围(内容不足一屏时贴底显示全部)。
    """
    offset = clamp_offset(total, height, tail_offset)
    end = max(0, total - offset)
    start = max(0, end - height)
    return start, end


def clamp_offset(total: int, height: int, offset: int) -> int:
    """把 tail_offset 限制在合法范围:最小 0,最大 total-height(内容不足一屏只能贴底)。"""
    return max(0, min(offset, max(0, total - height)))
