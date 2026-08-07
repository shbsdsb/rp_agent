from rp_agent import output


def test_emit_default_goes_to_stdout(capsys):
    output.emit("你好")
    assert capsys.readouterr().out == "你好\n"


def test_set_emit_target_redirects(capsys):
    collected: list[str] = []
    output.set_emit_target(collected.append)
    try:
        output.emit("a")
        output.emit("b")
    finally:
        output.reset_emit_target()
    assert collected == ["a", "b"]
    assert capsys.readouterr().out == ""  # 未落 stdout


def test_is_tui_flips_with_target():
    assert output.is_tui() is False
    output.set_emit_target(lambda s: None)
    try:
        assert output.is_tui() is True
    finally:
        output.reset_emit_target()
