from rp_agent import term


def test_colors_wrap_when_enabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", True)
    assert term.yellow("x") == "\033[33mx\033[0m"
    assert term.blue("x") == "\033[96mx\033[0m"
    assert term.gray("x") == "\033[90mx\033[0m"
    assert term.bold("x") == "\033[1mx\033[0m"


def test_input_prompt_when_enabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", True)
    assert term.input_prompt("rp-agent> ") == "\033[0mrp-agent> \033[96m"


def test_input_prompt_when_disabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", False)
    assert term.input_prompt("rp-agent> ") == "rp-agent> "


def test_colors_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", False)
    assert term.yellow("x") == "x"
    assert term.blue("x") == "x"
    assert term.gray("x") == "x"
    assert term.bold("x") == "x"
