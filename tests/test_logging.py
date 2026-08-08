import logging

from rp_agent.logging_setup import setup_logging


def test_log_to_stderr(capsys):
    setup_logging("INFO")
    logging.getLogger("rp_agent").info("hello-log")
    captured = capsys.readouterr()
    assert "hello-log" in captured.err
    assert captured.out == ""


def test_setup_idempotent():
    setup_logging("INFO")
    setup_logging("INFO")  # 不应抛错、不应重复添加我们的 handler
    logger = logging.getLogger("rp_agent")
    stream_handlers = [
        h for h in logger.handlers if type(h) is logging.StreamHandler
    ]
    assert len(stream_handlers) == 1


def test_install_emit_handler_routes_logs_to_emit(capsys):
    """TUI 下安装 emit handler 后,日志走 emit 而非 stderr。"""
    from rp_agent.logging_setup import install_emit_handler, uninstall_emit_handler

    collected: list[str] = []
    install_emit_handler(collected.append)
    try:
        logging.getLogger("rp_agent").info("tui-log")
    finally:
        uninstall_emit_handler()
    assert any("tui-log" in line for line in collected)
    assert capsys.readouterr().err == ""  # stderr 无输出


def test_uninstall_emit_handler_restores_stderr(capsys):
    """卸载后日志恢复走 stderr。"""
    from rp_agent.logging_setup import install_emit_handler, uninstall_emit_handler

    install_emit_handler(lambda s: None)
    uninstall_emit_handler()
    logging.getLogger("rp_agent").info("restored-log")
    assert "restored-log" in capsys.readouterr().err
