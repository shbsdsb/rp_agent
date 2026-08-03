from rp_agent.core.agent import run as agent_run
from rp_agent.core.chat import run as chat_run
from rp_agent.core.rp import run as rp_run


def _capture_run_shell(monkeypatch) -> dict:
    captured: dict = {}
    monkeypatch.setattr(
        "rp_agent.shell.run_shell",
        lambda _input=None, initial_mode="home": captured.update(mode=initial_mode),
    )
    return captured


def test_chat_run_enters_chat_mode(monkeypatch):
    captured = _capture_run_shell(monkeypatch)
    chat_run()
    assert captured.get("mode") == "chat"


def test_rp_run_enters_rp_mode(monkeypatch):
    captured = _capture_run_shell(monkeypatch)
    rp_run()
    assert captured.get("mode") == "rp"


def test_agent_run_enters_agent_mode(monkeypatch):
    captured = _capture_run_shell(monkeypatch)
    agent_run()
    assert captured.get("mode") == "agent"
