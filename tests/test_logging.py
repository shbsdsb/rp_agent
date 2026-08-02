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
