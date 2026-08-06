from prompt_toolkit.document import Document

from rp_agent.shell import ShellCompleter


def _complete(monkeypatch, tmp_path, text: str):
    if monkeypatch is not None:
        monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    doc = Document(text)
    return list(ShellCompleter().get_completions(doc, None))


def _names(result):
    return [c.text for c in result]


def test_command_name_completes_after_prefix():
    assert "api" in _names(_complete(None, None, "a"))
    assert "agent" in _names(_complete(None, None, "a"))


def test_command_name_completes_empty_line():
    names = _names(_complete(None, None, ""))
    assert "api" in names and "help" in names


def test_slash_command_completes():
    assert "/load" in _names(_complete(None, None, "/l"))
    assert "/exit" in _names(_complete(None, None, "/e"))


def test_subcommand_completes_after_prefix():
    assert "list" in _names(_complete(None, None, "api li"))
    assert "modify" in _names(_complete(None, None, "api m"))


def test_subcommand_completes_all_after_space():
    names = _names(_complete(None, None, "api "))
    for sub in ("list", "get", "add", "del", "test", "pull", "sync", "modify", "use", "set"):
        assert sub in names


def test_unknown_command_offers_nothing():
    assert _complete(None, None, "foobar ") == []
