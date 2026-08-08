import rp_agent.tui as tui
from rp_agent import output
from rp_agent.tui import clamp_offset, visible_slice


def test_visible_slice_tail():
    # 贴底(offset=0):显示最后 height 行
    assert visible_slice(total=100, height=10, tail_offset=0) == (90, 100)


def test_visible_slice_offsets_up():
    assert visible_slice(total=100, height=10, tail_offset=5) == (85, 95)


def test_visible_slice_content_less_than_height():
    assert visible_slice(total=3, height=10, tail_offset=0) == (0, 3)


def test_visible_slice_offset_clamped_at_bottom():
    # 3 行内容,height=10,offset 最多 0 → 显示全部
    assert visible_slice(total=3, height=10, tail_offset=7) == (0, 3)


def test_clamp_offset_bounds():
    assert clamp_offset(total=100, height=10, offset=-5) == 0
    assert clamp_offset(total=100, height=10, offset=3) == 3
    assert clamp_offset(total=100, height=10, offset=999) == 90
    assert clamp_offset(total=3, height=10, offset=5) == 0  # 内容不足一屏 → 只能贴底


def test_append_stores_lines_and_follows_tail(capsys):
    tui._output_lines.clear()
    tui._tail_offset = 0
    tui._current_mode_snapshot = "home"
    output.set_emit_target(tui._append)
    try:
        tui._append("第一行")
        tui._append("第二行\n第三行")  # 多行 splitlines
        assert len(tui._output_lines) == 3
        assert tui._tail_offset == 0  # 贴底时新行自动跟随
    finally:
        output.reset_emit_target()


def _fmt_text(fmt) -> str:
    """FormattedText → 纯文本(拼 style 元组的 text 段)。"""
    return "".join(seg[1] for seg in fmt)


def test_append_respects_max_lines():
    tui._output_lines.clear()
    tui._tail_offset = 0
    tui._current_mode_snapshot = "home"
    for i in range(tui.MAX_LINES + 10):
        tui._append(f"行{i}")
    assert len(tui._output_lines) == tui.MAX_LINES
    assert _fmt_text(tui._output_lines[0]) == "行10"  # 丢弃最旧 10 行


def test_append_keeps_offset_when_scrolled_back():
    tui._output_lines.clear()
    tui._tail_offset = 3  # 用户回看中
    tui._current_mode_snapshot = "home"
    for i in range(5):
        tui._append(f"行{i}")
    assert tui._tail_offset == 3  # 回看时新行不打断


def test_output_control_preferred_height_reflects_content():
    """HSplit 高度探测(preferred_height)应返回真实内容行数,而非 1。

    根因:preferred_height 内部以 create_content(width, None) 探测,
    旧实现 h = height or 1 只渲染最后 1 行 → preferred 恒为 1 → 输出区被压到极小。
    """
    import rp_agent.shell as shell_mod

    tui._output_lines.clear()
    tui._tail_offset = 0
    tui._current_mode_snapshot = "home"
    shell_mod._current_mode = "home"
    for i in range(10):
        tui._append(f"第{i}行")
    ctrl = tui.OutputControl()
    ph = ctrl.preferred_height(width=80, max_available_height=50, wrap_lines=False, get_line_prefix=None)
    assert ph == 10  # 修复前为 1


def test_scroll_changes_rendered_content():
    """滚动(tail_offset 变化)后,渲染应显示新切片,而非帧内缓存的上帧旧文本。"""
    import rp_agent.shell as shell_mod

    tui._output_lines.clear()
    tui._tail_offset = 0
    tui._current_mode_snapshot = "home"
    shell_mod._current_mode = "home"
    for i in range(30):
        tui._append(f"第{i}行")

    ctrl = tui.OutputControl()
    # 模拟一帧:先探测(帧内第一次读 self.text,命中旧值),再实际渲染
    ctrl.create_content(80, None)
    before = "".join(s[1] for s in ctrl.create_content(80, 26).get_line(0))
    assert before == "第4行"  # tail=0 → slice(4,30) 首行

    tui._scroll_by(10)  # 滚动(回看 10 行)
    ctrl.create_content(80, None)  # 新帧探测
    after = "".join(s[1] for s in ctrl.create_content(80, 26).get_line(0))
    assert after == "第0行"  # tail=10 → slice(0,20) 首行;修复前帧内缓存旧文本 → 仍"第4行"
