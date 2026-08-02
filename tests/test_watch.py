import threading
import time

from rp_agent.watch import Watcher


def _wait_for(events: list[str], name: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and name not in events:
        time.sleep(0.05)


def test_py_change_triggers_restart(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    py = pkg / "mod.py"
    py.write_text("x = 1\n", encoding="utf-8")
    cfg = tmp_path / "app.json"
    cfg.write_text("{}", encoding="utf-8")

    events: list[str] = []
    watcher = Watcher(
        py_dirs=[pkg],
        config_files=[cfg],
        on_restart=lambda: events.append("restart"),
        on_reload=lambda: events.append("reload"),
        interval=0.05,
    )
    t = threading.Thread(target=watcher.run, daemon=True)
    t.start()
    time.sleep(0.2)  # 建立初始快照
    py.write_text("x = 2\n", encoding="utf-8")  # 触发变更
    _wait_for(events, "restart")
    watcher.stop()
    t.join(timeout=1.0)
    assert "restart" in events
    assert "reload" not in events


def test_config_change_triggers_reload(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "mod.py").write_text("x = 1\n", encoding="utf-8")
    cfg = tmp_path / "app.json"
    cfg.write_text("{}", encoding="utf-8")

    events: list[str] = []
    watcher = Watcher(
        py_dirs=[pkg],
        config_files=[cfg],
        on_restart=lambda: events.append("restart"),
        on_reload=lambda: events.append("reload"),
        interval=0.05,
    )
    t = threading.Thread(target=watcher.run, daemon=True)
    t.start()
    time.sleep(0.2)
    cfg.write_text('{"log_level": "DEBUG"}', encoding="utf-8")
    _wait_for(events, "reload")
    watcher.stop()
    t.join(timeout=1.0)
    assert "reload" in events
    assert "restart" not in events
