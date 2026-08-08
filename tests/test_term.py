from rp_agent import term


def test_colors_wrap_when_enabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", True)
    assert term.yellow("x") == "\033[1;33mx\033[0m"
    assert term.blue("x") == "\033[96mx\033[0m"
    assert term.gray("x") == "\033[90mx\033[0m"
    assert term.bold("x") == "\033[1mx\033[0m"


def test_colors_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", False)
    assert term.yellow("x") == "x"
    assert term.blue("x") == "x"
    assert term.gray("x") == "x"
    assert term.bold("x") == "x"


def test_rgb_truecolor_when_enabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", True)
    assert term.rgb("x", 255, 224, 102) == "\033[38;2;255;224;102mx\033[0m"
    assert term.rgb("x", 102, 170, 255) == "\033[38;2;102;170;255mx\033[0m"


def test_rgb_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", False)
    assert term.rgb("x", 255, 224, 102) == "x"


def _fake_windll(**methods) -> object:
    """构造 FakeKernel32 的 windll 代理,供 supports_color 的 Windows 分支测试。"""

    class FakeKernel32:
        def __getattr__(self, name):
            def _call(*_a, **_k):
                return methods.get(name, 1)

            return _call

    class FakeWindll:
        kernel32 = FakeKernel32()

    return FakeWindll()


def test_supports_color_false_when_getconsolemode_fails(monkeypatch):
    """Windows 下 GetConsoleMode 失败(返回 0)应返回 False(此前仍 True)。"""
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        "ctypes.windll",
        _fake_windll(GetStdHandle=1, GetConsoleMode=0, SetConsoleMode=1),
        raising=False,
    )
    assert term.supports_color() is False


def test_supports_color_false_when_setconsolemode_fails(monkeypatch):
    """Windows 下启用 VT 失败(SetConsoleMode 返回 0,legacy cmd)应返回 False(此前仍 True)。"""
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        "ctypes.windll",
        _fake_windll(GetStdHandle=1, GetConsoleMode=1, SetConsoleMode=0),
        raising=False,
    )
    assert term.supports_color() is False


def test_supports_color_true_when_vt_enabled_ok(monkeypatch):
    """Windows 下 GetConsoleMode/SetConsoleMode 均成功应返回 True(回归保护)。"""
    import sys

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        "ctypes.windll",
        _fake_windll(GetStdHandle=1, GetConsoleMode=1, SetConsoleMode=1),
        raising=False,
    )
    assert term.supports_color() is True

