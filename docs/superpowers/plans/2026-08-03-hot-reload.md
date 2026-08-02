# 热重载功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 rp-agent 添加热重载:JSON 配置文件(env > 文件 > 默认)+ `--watch` 开发热重载(.py 变更重启、config 变更热生效)。

**Architecture:** `config.py` 扩展文件加载与 `reload_config()` 变化检测;新增 `watch.py`(零依赖 mtime 轮询 `Watcher`);`cli.py` 加 `--watch` 全局选项,父进程 spawn 子进程(`[sys.executable, "-m", "rp_agent", *args]`),.py 变更 kill+重启,json 变更调用 `reload_config()` 热生效。

**Tech Stack:** Python 3.14、UV、Typer、标准库(logging/subprocess/threading/time/pathlib)、pytest。

## Global Constraints

- Python >= 3.14;依赖/运行一律 `uv run`(Windows 环境,不用 python3)
- **不新增运行时依赖**(watch 用标准库轮询,禁止 watchdog 等);`uv.lock` 不变
- 日志只用标准库 `logging`,输出 stderr
- 配置优先级:**环境变量(`RP_AGENT_LOG_LEVEL`)> 配置文件(`log_level`)> 默认值(`"INFO"`)**
- watch 分工:**.py 变更 → 重启子进程**; **configs/*.json 变更 → 不重启,热生效**
- 工作分支 `feat/hot-reload`;现有 12 项测试必须保持通过(向后兼容)
- 配置文件目录:`src/rp_agent/configs/`(与 tools/prompts/core 平级)

---

### Task 1: 配置文件 + `config.py` 文件加载与热重载

**Files:**
- Create: `src/rp_agent/configs/__init__.py`
- Create: `src/rp_agent/configs/app.json`
- Modify: `src/rp_agent/config.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: 现有 `AppConfig`(dataclass,`log_level: str = "INFO"`)、`get_config(force_reload: bool = False)`、`ENV_LOG_LEVEL`
- Produces:
  - `DEFAULT_CONFIG_PATH: Path`(包内 `configs/app.json`)
  - `load_config_file(path: Path | None = None) -> dict[str, object]`:读 JSON;缺失/损坏返回 `{}` 并 `logger.warning`
  - `reload_config() -> bool`:重新加载(文件+env)并更新单例,返回是否变化
  - `get_config(force_reload)` 语义不变(force 时走文件+env 合并)

- [ ] **Step 1: 扩展失败测试 `tests/test_config.py`(追加以下测试)**

```python
import json

from rp_agent.config import get_config, load_config_file, reload_config


def test_load_config_file(tmp_path):
    p = tmp_path / "app.json"
    p.write_text(json.dumps({"log_level": "WARNING"}), encoding="utf-8")
    assert load_config_file(p) == {"log_level": "WARNING"}


def test_load_config_missing_returns_empty(tmp_path):
    assert load_config_file(tmp_path / "nope.json") == {}


def test_load_config_broken_json_returns_empty(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_config_file(p) == {}


def test_file_overrides_default(monkeypatch, tmp_path):
    p = tmp_path / "app.json"
    p.write_text(json.dumps({"log_level": "WARNING"}), encoding="utf-8")
    monkeypatch.setattr("rp_agent.config.DEFAULT_CONFIG_PATH", p)
    assert get_config(force_reload=True).log_level == "WARNING"


def test_env_overrides_file(monkeypatch, tmp_path):
    p = tmp_path / "app.json"
    p.write_text(json.dumps({"log_level": "WARNING"}), encoding="utf-8")
    monkeypatch.setattr("rp_agent.config.DEFAULT_CONFIG_PATH", p)
    monkeypatch.setenv("RP_AGENT_LOG_LEVEL", "DEBUG")
    assert get_config(force_reload=True).log_level == "DEBUG"


def test_reload_config_changed_detection(monkeypatch, tmp_path):
    p = tmp_path / "app.json"
    p.write_text(json.dumps({"log_level": "INFO"}), encoding="utf-8")
    monkeypatch.setattr("rp_agent.config.DEFAULT_CONFIG_PATH", p)
    reload_config()
    assert reload_config() is False  # 内容未变
    p.write_text(json.dumps({"log_level": "DEBUG"}), encoding="utf-8")
    assert reload_config() is True  # 内容已变
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_config.py -v
```
Expected: 新测试 FAIL(如 `AttributeError: module 'rp_agent.config' has no attribute 'DEFAULT_CONFIG_PATH'`)

- [ ] **Step 3: 创建配置资源与重写 `src/rp_agent/config.py`**

`src/rp_agent/configs/__init__.py`:
```python
"""configs: 运行时 JSON 配置文件(包内资源)。"""
```

`src/rp_agent/configs/app.json`:
```json
{ "log_level": "INFO" }
```

`src/rp_agent/config.py`(整体替换):
```python
"""全局配置:JSON 配置文件 + 环境变量加载,模块级单例,支持热重载。

优先级:环境变量(RP_AGENT_LOG_LEVEL)> 配置文件(log_level)> 默认值(INFO)。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("rp_agent")

DEFAULT_LOG_LEVEL = "INFO"
ENV_LOG_LEVEL = "RP_AGENT_LOG_LEVEL"
DEFAULT_CONFIG_PATH = Path(__file__).parent / "configs" / "app.json"


@dataclass
class AppConfig:
    """应用配置。骨架阶段仅含日志级别,后续按需扩展字段。"""

    log_level: str = DEFAULT_LOG_LEVEL


_config: AppConfig | None = None


def load_config_file(path: Path | None = None) -> dict[str, object]:
    """读取 JSON 配置文件。缺失/损坏时返回 {} 并告警,不崩溃。"""
    cfg_path = path or DEFAULT_CONFIG_PATH
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("配置文件读取失败(%s): %s,回退默认值", cfg_path, exc)
        return {}


def _merge_config(file_data: dict[str, object]) -> AppConfig:
    """合并优先级:环境变量 > 配置文件 > 默认值。"""
    log_level = DEFAULT_LOG_LEVEL
    file_level = file_data.get("log_level")
    if isinstance(file_level, str) and file_level:
        log_level = file_level
    env_level = os.environ.get(ENV_LOG_LEVEL)
    if env_level:
        log_level = env_level
    return AppConfig(log_level=log_level)


def reload_config() -> bool:
    """重新加载配置(文件 + env),更新单例;返回配置是否发生变化。"""
    global _config
    new_config = _merge_config(load_config_file())
    changed = _config is None or new_config != _config
    _config = new_config
    return changed


def get_config(force_reload: bool = False) -> AppConfig:
    """返回全局配置单例。force_reload=True 时强制重新加载。"""
    if _config is None or force_reload:
        reload_config()
    assert _config is not None
    return _config
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_config.py -v
```
Expected: 9 passed(原 3 + 新 6)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/configs src/rp_agent/config.py tests/test_config.py
git commit -m "feat: 配置文件 configs/app.json + config 文件加载/热重载"
```

---

### Task 2: `watch.py` — Watcher 轮询热重载

**Files:**
- Create: `src/rp_agent/watch.py`
- Create: `tests/test_watch.py`

**Interfaces:**
- Consumes: 无(仅标准库)
- Produces:
  - `Watcher(py_dirs: Sequence[Path], config_files: Sequence[Path], on_restart: Callable[[], None], on_reload: Callable[[], None], interval: float = 0.5)`
  - `Watcher.run() -> None`:阻塞轮询,`KeyboardInterrupt` 或 `stop()` 退出
  - `Watcher.stop() -> None`:设置运行标志为 False
  - 行为:`.py`(py_dirs 递归 `*.py`)mtime 变化 → `on_restart()`;配置文件 mtime 变化 → `on_reload()`

- [ ] **Step 1: 写失败测试 `tests/test_watch.py`**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_watch.py -v
```
Expected: FAIL(`ModuleNotFoundError: No module named 'rp_agent.watch'`)

- [ ] **Step 3: 写 `src/rp_agent/watch.py`**

```python
"""开发热重载:轮询(mtime)监控文件变化,分发重启/热重载回调。零依赖。"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Sequence

logger = logging.getLogger("rp_agent")


class Watcher:
    """轮询监控 .py 与配置文件。

    - py_dirs 下递归 `*.py` 变化 → on_restart()(重启子进程)
    - config_files 变化 → on_reload()(不重启,热生效)
    """

    def __init__(
        self,
        py_dirs: Sequence[Path],
        config_files: Sequence[Path],
        on_restart: Callable[[], None],
        on_reload: Callable[[], None],
        interval: float = 0.5,
    ) -> None:
        self._py_dirs = list(py_dirs)
        self._config_files = list(config_files)
        self._on_restart = on_restart
        self._on_reload = on_reload
        self._interval = interval
        self._py_snapshot: dict[Path, int] = {}
        self._config_snapshot: dict[Path, int] = {}
        self._running = False

    def _scan_py_files(self) -> dict[Path, int]:
        files: dict[Path, int] = {}
        for d in self._py_dirs:
            if not d.is_dir():
                continue
            for p in d.rglob("*.py"):
                try:
                    files[p] = p.stat().st_mtime_ns
                except OSError:
                    continue
        return files

    def _scan_config_files(self) -> dict[Path, int]:
        files: dict[Path, int] = {}
        for p in self._config_files:
            try:
                files[p] = p.stat().st_mtime_ns
            except OSError:
                continue
        return files

    @staticmethod
    def _changed_files(
        now: dict[Path, int], prev: dict[Path, int]
    ) -> set[Path]:
        added = set(now) - set(prev)
        removed = set(prev) - set(now)
        modified = {k for k in now if k in prev and now[k] != prev[k]}
        return added | removed | modified

    def _check(self) -> None:
        py_now = self._scan_py_files()
        if py_now != self._py_snapshot:
            changed = self._changed_files(py_now, self._py_snapshot)
            logger.info("[watch] 检测到代码变更: %s", sorted(str(p) for p in changed))
            self._py_snapshot = py_now
            self._on_restart()

        cfg_now = self._scan_config_files()
        if cfg_now != self._config_snapshot:
            changed = self._changed_files(cfg_now, self._config_snapshot)
            logger.info("[watch] 检测到配置变更: %s", sorted(str(p) for p in changed))
            self._config_snapshot = cfg_now
            self._on_reload()

    def run(self) -> None:
        """阻塞轮询,直到 stop() 或 KeyboardInterrupt。"""
        self._py_snapshot = self._scan_py_files()
        self._config_snapshot = self._scan_config_files()
        self._running = True
        try:
            while self._running:
                time.sleep(self._interval)
                self._check()
        except KeyboardInterrupt:
            self._running = False

    def stop(self) -> None:
        self._running = False
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_watch.py -v
```
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/watch.py tests/test_watch.py
git commit -m "feat: Watcher 轮询热重载(watch.py,零依赖)"
```

---

### Task 3: `cli.py` — `--watch` 通用选项集成

**Files:**
- Modify: `src/rp_agent/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - `Watcher`(Task 2:`py_dirs`/`config_files`/`on_restart`/`on_reload`/`interval`)
  - `reload_config() -> bool`、`get_config()`、`DEFAULT_CONFIG_PATH`(Task 1)
  - `setup_logging(level: str)`(现有)
- Produces:
  - `main` callback 新增 `ctx: typer.Context` 与 `watch: bool` 全局选项
  - `_run_watch(args: list[str]) -> None`:spawn 子进程 `[sys.executable, "-m", "rp_agent", *args]`;.py 变更 kill+重启;config 变更 `reload_config()` 热生效;finally 终止子进程
  - `_spawn_child(args: list[str]) -> subprocess.Popen`

- [ ] **Step 1: 追加失败测试 `tests/test_cli.py`**

```python
def test_watch_with_subcommand(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "rp_agent.cli._run_watch", lambda args: captured.update(args=args)
    )
    result = runner.invoke(app, ["--watch", "hello"])
    assert result.exit_code == 0
    assert captured.get("args") == ["hello"]


def test_watch_without_subcommand(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        "rp_agent.cli._run_watch", lambda args: captured.update(args=args)
    )
    result = runner.invoke(app, ["--watch"])
    assert result.exit_code == 0
    assert captured.get("args") == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: 新测试 FAIL(Typer 报 `Got unexpected extra argument (--watch)`)

- [ ] **Step 3: 修改 `src/rp_agent/cli.py`(整体替换)**

```python
"""Typer CLI 入口:唯一命令注册点。未来子命令(chat/character/agent)在此注册。"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import typer

from rp_agent import __version__
from rp_agent.config import DEFAULT_CONFIG_PATH, get_config, reload_config
from rp_agent.logging_setup import setup_logging
from rp_agent.watch import Watcher

logger = logging.getLogger("rp_agent")

app = typer.Typer(
    name="rp-agent",
    help="AI 角色扮演 agent 平台(长期愿景:取代 SillyTavern)",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"rp-agent {__version__}")
        raise typer.Exit()


def _spawn_child(args: list[str]) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "rp_agent", *args]
    logger.info("[watch] 启动子进程: %s", " ".join(cmd))
    return subprocess.Popen(cmd)


def _run_watch(args: list[str]) -> None:
    """--watch 模式:代码变更重启子进程,配置变更热生效。"""
    src_dir = Path(__file__).parent
    child: subprocess.Popen | None = _spawn_child(args)

    def on_restart() -> None:
        nonlocal child
        logger.info("[watch] 检测到代码变更,重启子进程…")
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        child = _spawn_child(args)

    def on_reload() -> None:
        if reload_config():
            cfg = get_config()
            setup_logging(cfg.log_level)
            logger.info("[watch] 配置已热重载: log_level=%s", cfg.log_level)
        else:
            logger.info("[watch] 配置无变化")

    watcher = Watcher(
        py_dirs=[src_dir],
        config_files=[DEFAULT_CONFIG_PATH],
        on_restart=on_restart,
        on_reload=on_reload,
    )
    try:
        watcher.run()
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        is_eager=True,
        callback=_version_callback,
        help="显示版本并退出",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        help="开发热重载:代码变更自动重启,配置变更热生效",
    ),
) -> None:
    """rp-agent 全局入口:初始化配置与日志。"""
    cfg = get_config()
    setup_logging(cfg.log_level)
    if watch:
        args = [ctx.invoked_subcommand or ""] + list(ctx.args)
        args = [a for a in args if a]
        logger.debug("进入 --watch 模式,目标命令: %s", args or ["(无,显示帮助)"])
        _run_watch(args)
        raise typer.Exit()
    logger.debug("配置加载完成: log_level=%s", cfg.log_level)


@app.command()
def hello() -> None:
    """冒烟命令:验证 命令 → 配置 → 日志 全链路。"""
    cfg = get_config()
    typer.echo(f"你好!rp-agent 骨架已就绪,当前日志级别: {cfg.log_level}")
    logger.info("hello 命令执行完成")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: 5 passed(原 3 + 新 2)

- [ ] **Step 5: 手动冒烟(watch 模式,3 秒后自动终止)**

```bash
timeout 3 uv run rp-agent --watch hello || true
```
Expected: 日志显示启动子进程、子进程输出 `你好!rp-agent…`;3 秒后 timeout 终止(退出码非 0 属预期,已 `|| true`)

- [ ] **Step 6: 提交**

```bash
git add src/rp_agent/cli.py tests/test_cli.py
git commit -m "feat: cli --watch 开发热重载集成(.py 重启 / config 热生效)"
```

---

### Task 4: 全量验证与收尾

**Files:**
- Modify: `README.md`(补充 `--watch` 用法与配置说明)

**Interfaces:**
- Consumes: 全部 Task 1-3 产物
- Produces: 全绿测试套件 + 完整 git 历史

- [ ] **Step 1: 运行全量测试**

```bash
uv run pytest -v
```
Expected: 22 passed(9 + 2 + 5 + 2 + 2 + 1 + 1 = 22,含原 logging/tools/prompts/start_scripts)

- [ ] **Step 2: 全量冒烟**

```bash
uv run rp-agent --version
uv run rp-agent hello
timeout 3 uv run rp-agent --watch hello || true
```
Expected: 版本/hello 正常;watch 启动子进程后 3 秒被 timeout 终止。

- [ ] **Step 3: 更新 README.md(在快速开始后追加)**

```markdown
## 热重载

- 配置文件:`src/rp_agent/configs/app.json`(JSON),优先级:环境变量 > 配置文件 > 默认值
- 开发热重载:

\`\`\`bash
uv run rp-agent --watch hello
\`\`\`

代码变更(.py)自动重启;配置文件变更热生效,无需重启。
```

- [ ] **Step 4: 确认工作树整洁并提交收尾**

```bash
git status --short
git add -A
git commit -m "chore: 热重载功能完成(README 更新)"
git log --oneline
```
Expected: `git log --oneline` 显示连续提交历史(Task 1-4)。

---

## 验收清单(对照 spec)

- [ ] `configs/app.json` 存在,`load_config_file` 缺失/损坏回退 `{}` 并告警 → spec §3.1、§3.2、§5
- [ ] 优先级 env > 文件 > 默认 生效(test_env_overrides_file / test_file_overrides_default)→ spec §3.2
- [ ] `reload_config()` 变化检测(改文件→True,未改→False)→ spec §3.2
- [ ] Watcher:.py 变更触发 restart,.json 变更触发 reload(不重启)→ spec §3.3
- [ ] `--watch` 通用选项;子进程 `[sys.executable, -m, rp_agent, *args]` → spec §3.4
- [ ] config 变更热生效打印日志;Ctrl+C/finally 终止子进程 → spec §3.4、§5
- [ ] 不新增依赖,`uv.lock` 不变 → Global Constraints
- [ ] 现有 12 项测试保持通过,总计 22 passed → spec §7
