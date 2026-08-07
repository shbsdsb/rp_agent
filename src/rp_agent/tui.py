"""全屏 TUI:三区布局(状态栏/可滚动输出区/输入框)。

滚动用 _tail_offset(距末尾偏移行数,0=贴底)对输出行切片渲染,
完全绕开 prompt_toolkit 锚点(光标)滚动机制——锚点在可视区内移动时视图不跟随是历史 bug 根因。
"""
from __future__ import annotations

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import ANSI, FormattedText, to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from rp_agent import output
from rp_agent.shell import (
    SHELL_STYLE,
    ShellCompleter,
    ShellLexer,
    _prompt_for_mode,
    handle_line,
)

MAX_LINES = 5000

_output_lines: list = []  # list[FormattedText],TUI 会话期间输出历史(跨界面切换保留)
_tail_offset = 0  # 0 = 贴底显示最新;正数 = 向上回看 offset 行

_current_mode_snapshot: str = ""


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


def _append(text: str) -> None:
    """emit 目标:模式变化 → 清空;追加行;贴底自动跟随。"""
    global _tail_offset, _current_mode_snapshot
    # 惰性读 shell 模块状态:handle_line 用 global 改写 shell._current_mode,
    # from-import 只会拿到导入时的值快照,必须经模块对象取最新值。
    import rp_agent.shell as shell_mod

    mode = shell_mod._current_mode
    if mode != _current_mode_snapshot:
        _output_lines.clear()
        _tail_offset = 0
        _current_mode_snapshot = mode
    for sub in str(text).splitlines():
        _output_lines.append(to_formatted_text(ANSI(sub)))
    del _output_lines[:-MAX_LINES]
    # 贴底(_tail_offset==0)时新行自动跟随;回看(_tail_offset>0)时偏移不变,不打断阅读
    _invalidate()


def _scroll_by(delta: int) -> None:
    """按 10 行步进滚动(输出区实际高度由渲染时计算,步进取固定值即可)。"""
    global _tail_offset
    _tail_offset = clamp_offset(len(_output_lines), 10, _tail_offset + delta)
    _invalidate()


def _invalidate() -> None:
    if _app is not None:
        _app.invalidate()


class OutputControl(FormattedTextControl):
    """可滚动输出区:create_content 时按 _tail_offset 切片,绕开锚点机制。"""

    def __init__(self) -> None:
        super().__init__(text="")
        self._height = 1

    def create_content(self, width: int, height: int | None):
        h = height or 1
        self._height = h
        start, end = visible_slice(len(_output_lines), h, _tail_offset)
        # 每行是 FormattedText(style, text) 列表;渲染按文本中的 \n 切行,
        # 故行间需显式插入换行 fragment,再把各行的 style 片段平铺。
        frags: list[tuple[str, str]] = []
        for i in range(start, end):
            if i > start:
                frags.append(("", "\n"))
            frags.extend(_output_lines[i])
        self.text = FormattedText(frags)
        return super().create_content(width, height)

    def mouse_handler(self, mouse_event):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            _scroll_by(3)
            return True
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            _scroll_by(-3)
            return True
        return NotImplemented


def _status_text() -> FormattedText:
    import rp_agent.shell as shell_mod  # 惰性,避免循环 import

    parts: list[tuple[str, str]] = [
        ("class:status-mode", f"[{shell_mod._current_mode}]")
    ]
    s = shell_mod._chat_session
    if s is not None:
        parts.append(("class:status-dim", f" 会话 {s.name or s.id}"))
        if s.connection:
            parts.append(("class:status-dim", f" 连接 {s.connection}"))
    return FormattedText(parts)


def _accept(buff: Buffer) -> None:
    import rp_agent.shell as shell_mod

    line = buff.text
    buff.reset()
    if not line.strip():
        return
    handle_line(line)
    if shell_mod._quit_request:
        _app.exit()
        return
    if _ui_switch_request():
        _app.exit()
        return
    _invalidate()


def _ui_switch_request() -> bool:
    import rp_agent.shell as shell_mod

    return shell_mod._ui_switch_request is not None


_app: Application | None = None


def run(initial_mode: str = "home") -> None:
    """进入全屏 TUI 事件循环;真正退出后恢复 emit 目标。"""
    global _app, _tail_offset, _current_mode_snapshot
    import rp_agent.shell as shell_mod

    shell_mod._current_mode = initial_mode
    _current_mode_snapshot = initial_mode
    output.set_emit_target(_append)
    try:
        # prompt_toolkit 3.0.53:completer 是 Buffer 的参数,BufferControl 不接受
        buff = Buffer(
            accept_handler=_accept, multiline=False, completer=ShellCompleter()
        )
        kb = KeyBindings()

        @kb.add("pageup")
        def _page_up(event):
            _scroll_by(10)

        @kb.add("pagedown")
        def _page_down(event):
            _scroll_by(-10)

        @kb.add("home")
        def _go_top(event):
            global _tail_offset
            _tail_offset = clamp_offset(len(_output_lines), 10, len(_output_lines))

        @kb.add("end")
        def _go_bottom(event):
            global _tail_offset
            _tail_offset = 0

        output_win = Window(
            OutputControl(), wrap_lines=False, allow_scroll_beyond_bottom=True
        )
        layout = Layout(
            HSplit(
                [
                    Window(
                        FormattedTextControl(_status_text),
                        height=1,
                        style="class:status",
                    ),
                    output_win,
                    Window(
                        FormattedTextControl(
                            "reload --tui/--cli 切换界面 | PageUp/PageDown/滚轮滚动 | exit 退出"
                        ),
                        height=1,
                        style="class:hint",
                    ),
                    VSplit(
                        [
                            Window(
                                FormattedTextControl(
                                    lambda: _prompt_for_mode(shell_mod._current_mode)
                                ),
                                width=10,
                                dont_extend_width=True,
                                style="class:chat-prompt",
                            ),
                            Window(
                                BufferControl(buffer=buff, lexer=ShellLexer()),
                                height=1,
                            ),
                        ]
                    ),
                ]
            )
        )
        _app = Application(
            layout=layout,
            style=SHELL_STYLE,
            full_screen=True,
            mouse_support=True,
            key_bindings=kb,
        )
        _app.run()
    finally:
        output.reset_emit_target()
        _app = None
