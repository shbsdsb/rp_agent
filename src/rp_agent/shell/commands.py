"""基础命令与命令元数据:命令注册表、子命令/选项表(着色与补全共享数据源)。

界面状态(_ui_mode/_ui_switch_request/_history)经 `rp_agent.shell` 包命名空间
运行时访问,不在此模块持有副本。
"""
from __future__ import annotations

import logging
from typing import Callable, Literal

from rp_agent.api.args import KNOWN_OPTIONS
from rp_agent.config import get_config, reload_config
from rp_agent.help_data import HELP_ENTRIES, find_entry
from rp_agent.output import emit
from rp_agent.shell.api_cmds import _cmd_api
from rp_agent.shell.chat_cmds import _cmd_chat
from rp_agent.term import blue, gray, yellow

logger = logging.getLogger("rp_agent")

Mode = Literal["home", "chat", "rp", "agent"]
_MODE_COMMANDS: dict[str, Mode] = {"chat": "chat", "rp": "rp", "agent": "agent"}
_CHAT_COMMANDS: set[str] = {"new", "list", "load", "rename"}


def _prompt_for_mode(mode: Mode) -> str:
    return {"home": "home> ", "chat": "chat> ", "rp": "rp> ", "agent": "agent> "}[mode]


def _placeholder_msg(mode: Mode) -> str:
    return f"[{mode}] 对话功能尚未实现(占位模式),/exit 返回 home"


def _cmd_config(args: list[str]) -> None:
    if args and args[0] == "timeout":
        if len(args) < 2:
            emit("用法: config timeout <秒>")
            return
        try:
            secs = float(args[1])
        except ValueError:
            emit(f"非法超时: {args[1]}")
            return
        if secs <= 0:
            emit("超时必须为正数")
            return
        from rp_agent.config import save_config

        save_config({"timeout": secs})
        reload_config()
        emit(f"已设置全局超时: {secs}s")
        return
    cfg = get_config()
    emit(f"log_level={cfg.log_level}")
    emit(f"timeout={cfg.timeout}s")


def _cmd_reload(args: list[str]) -> None:
    if args in (["--tui"], ["--cli"]):
        import rp_agent.shell as shell_mod

        target = args[0][2:]
        if shell_mod._ui_mode == target:
            emit(f"已是 {target} 界面")
            return
        shell_mod._ui_switch_request = target
        emit(f"切换到 {target} 界面…")
        return
    changed = reload_config()
    cfg = get_config()
    emit(f"配置已重载,发生变化: {changed},log_level={cfg.log_level}")


def _cmd_hello(_args: list[str]) -> None:
    cfg = get_config()
    emit(f"你好!rp-agent 骨架已就绪,当前日志级别: {cfg.log_level}")
    logger.info("shell 中执行 hello")


def _cmd_history(_args: list[str]) -> None:
    import rp_agent.shell as shell_mod

    for i, h in enumerate(shell_mod._history, start=1):
        emit(f"  {i:>3}  {h}")


def _colorize_usage(usage: str) -> str:
    """usage 串按 token 着色:命令黄、-前缀选项灰、<>参数蓝。"""
    parts = []
    for tok in usage.split():
        if tok.startswith("-") and len(tok) > 1:
            parts.append(gray(tok))
        elif tok.startswith("<") and tok.endswith(">"):
            parts.append(blue(tok))
        else:
            parts.append(yellow(tok))
    return " ".join(parts)


def _print_command_help(command: str) -> None:
    entry = find_entry(command)
    if entry is None:
        emit(f"未知命令: {command}(输入 help 查看可用命令)")
        return
    emit(f"用法: {_colorize_usage(str(entry['usage']))}")
    for param, desc in entry["params"]:
        emit(f"  {blue(param):<34} {desc}")


def _cmd_help(args: list[str]) -> None:
    if args:
        _print_command_help(args[0])
        return
    emit("可用命令:")
    names = []
    for e in HELP_ENTRIES:
        name = e["command"]
        if e["aliases"]:
            name += "/" + "/".join(e["aliases"])
        names.append(name)
    width = max(len(n) for n in names)
    for e, name in zip(HELP_ENTRIES, names):
        emit(f"  {yellow(name.ljust(width))}  {e['desc']}")
    emit("  输入 <命令> --help 查看详细用法")


_COMMANDS: dict[str, tuple[str, Callable[[list[str]], None]]] = {
    "help": ("显示帮助", _cmd_help),
    "?": ("显示帮助", _cmd_help),
    "config": ("显示当前配置", _cmd_config),
    "reload": ("热重载配置", _cmd_reload),
    "hello": ("冒烟命令", _cmd_hello),
    "history": ("显示输入历史", _cmd_history),
    "api": ("API 连接管理(api list/get/add/del/test)", _cmd_api),
    "chat": ("会话管理(chat list/get/load/rename)", _cmd_chat),
}

_KNOWN_COMMANDS: set[str] = (
    set(_COMMANDS)
    | {e["command"] for e in HELP_ENTRIES}
    | {a for e in HELP_ENTRIES for a in e["aliases"]}
    | set(_MODE_COMMANDS)
    | set(_CHAT_COMMANDS)
)

# 每个命令的合法参数(仅这些词着色为"有效参数")
_COMMAND_ARGS: dict[str, set[str]] = {
    "api": {"list", "get", "add", "del", "test", "pull", "sync", "modify", "use", "set"},
    "chat": {"list", "get", "load", "rename"},
    "reload": {"--tui", "--cli"},
    "help": _KNOWN_COMMANDS,
    "?": _KNOWN_COMMANDS,
}

# 有效选项(--长选项 / -短选项,灰色):全部已知选项(与 args.py 同步)+ reload 的界面切换选项
_VALID_OPTIONS: set[str] = KNOWN_OPTIONS | {"--tui", "--cli"}
