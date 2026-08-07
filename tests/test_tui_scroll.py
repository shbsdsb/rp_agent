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
