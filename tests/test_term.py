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
