"""交互式 shell:供测试命令的 REPL 输入口。"""
from __future__ import annotations

import logging
import sys
from typing import Callable

from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.shortcuts import prompt as pt_prompt
from prompt_toolkit.styles import Style

from rp_agent.api.client import ApiError, test_connection
from rp_agent.api.models import ApiConnection
from rp_agent.api.store import (
    delete_connection,
    get_connection,
    list_connections,
    save_connection,
)
from rp_agent.config import get_config, reload_config
from rp_agent.help_data import HELP_ENTRIES, find_entry
from rp_agent.storage import DATA_DIR, ensure_dirs
from rp_agent.term import blue, gray, yellow

logger = logging.getLogger("rp_agent")

PROMPT = "rp-agent> "
_BANNER = "rp-agent 交互式 shell —— 输入 help 查看可用命令,exit 退出"
_history: list[str] = []


def parse_line(line: str) -> tuple[str, list[str]]:
    """解析输入行 → (命令名, 参数列表);空行 → ("", [])。"""
    parts = line.strip().split()
    if not parts:
        return "", []
    return parts[0], parts[1:]


def _cmd_config(_args: list[str]) -> None:
    cfg = get_config()
    print(f"log_level={cfg.log_level}")


def _cmd_reload(_args: list[str]) -> None:
    changed = reload_config()
    cfg = get_config()
    print(f"配置已重载,发生变化: {changed},log_level={cfg.log_level}")


def _cmd_storage(_args: list[str]) -> None:
    ensure_dirs()
    print(f"data 目录: {DATA_DIR}")
    for sub in sorted(p for p in DATA_DIR.iterdir() if p.is_dir()):
        items = sorted(p.name for p in sub.iterdir())
        print(f"  {sub.name}/: {items}")


def _cmd_hello(_args: list[str]) -> None:
    cfg = get_config()
    print(f"你好!rp-agent 骨架已就绪,当前日志级别: {cfg.log_level}")
    logger.info("shell 中执行 hello")


def _cmd_history(_args: list[str]) -> None:
    for i, h in enumerate(_history, start=1):
        print(f"  {i:>3}  {h}")


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
        print(f"未知命令: {command}(输入 help 查看可用命令)")
        return
    print(f"用法: {_colorize_usage(str(entry['usage']))}")
    for param, desc in entry["params"]:
        print(f"  {blue(param):<34} {desc}")


def _cmd_help(args: list[str]) -> None:
    if args:
        _print_command_help(args[0])
        return
    print("可用命令:")
    for e in HELP_ENTRIES:
        name = e["command"]
        if e["aliases"]:
            name += "/" + "/".join(e["aliases"])
        print(f"  {yellow(name)}\t{e['desc']}")
    print("  输入 <命令> --help 查看详细用法")


def _cmd_api(args: list[str]) -> None:
    if not args:
        print(f"用法: {_colorize_usage('api <list|get|add|del|test> ...')}")
        return
    sub = args[0]
    if sub == "list":
        names = list_connections()
        if not names:
            print("(无连接)")
            return
        for n in names:
            print(f"  {n}")
    elif sub == "get":
        if len(args) < 2:
            print(f"用法: {_colorize_usage('api get <name>')}")
            return
        conn = get_connection(args[1])
        if conn is None:
            print(f"连接不存在: {args[1]}")
            return
        key = conn.api_key
        masked = key[:3] + "***" if key else "(空)"
        print(f"name={conn.name}")
        print(f"base_url={conn.base_url}")
        print(f"api_key={masked}")
        print(f"model={conn.model}")
        print(f"timeout={conn.timeout}")
    elif sub == "add":
        if len(args) < 4:
            print(f"用法: {_colorize_usage('api add <name> <base_url> <model> [api_key]')}")
            return
        conn = ApiConnection(
            name=args[1],
            base_url=args[2],
            model=args[3],
            api_key=args[4] if len(args) > 4 else "",
        )
        try:
            save_connection(conn)
            print(f"已保存连接: {conn.name}")
        except ValueError as exc:
            print(f"配置无效: {exc}")
    elif sub == "del":
        if len(args) < 2:
            print(f"用法: {_colorize_usage('api del <name>')}")
            return
        if delete_connection(args[1]):
            print(f"已删除连接: {args[1]}")
        else:
            print(f"连接不存在: {args[1]}")
    elif sub == "test":
        if len(args) < 2:
            print(f"用法: {_colorize_usage('api test <name>')}")
            return
        conn = get_connection(args[1])
        if conn is None:
            print(f"连接不存在: {args[1]}")
            return
        print(f"正在测试连接: {conn.name} ({conn.base_url})…")
        try:
            print(f"模型回复: {test_connection(conn)}")
        except ApiError as exc:
            print(f"测试失败: {exc}")
    else:
        print(f"未知子命令: {sub}(用法: {_colorize_usage('api <list|get|add|del|test> ...')})")


_COMMANDS: dict[str, tuple[str, Callable[[list[str]], None]]] = {
    "help": ("显示帮助", _cmd_help),
    "?": ("显示帮助", _cmd_help),
    "config": ("显示当前配置", _cmd_config),
    "reload": ("热重载配置", _cmd_reload),
    "storage": ("列出 data 目录内容", _cmd_storage),
    "hello": ("冒烟命令", _cmd_hello),
    "history": ("显示输入历史", _cmd_history),
    "api": ("API 连接管理(api list/get/add/del/test)", _cmd_api),
}

_KNOWN_COMMANDS: set[str] = set(_COMMANDS) | {
    a for e in HELP_ENTRIES for a in e["aliases"]
}

# 每个命令的合法参数(仅这些词着色为"有效参数")
_COMMAND_ARGS: dict[str, set[str]] = {
    "api": {"list", "get", "add", "del", "test"},
    "help": _KNOWN_COMMANDS,
    "?": _KNOWN_COMMANDS,
}

# 有效选项(--长选项 / -短选项,灰色)
_VALID_OPTIONS: set[str] = {"--help", "-h"}

SHELL_STYLE = Style.from_dict(
    {
        "cmd": "ansiyellow bold",  # 有效命令:黄色
        "param": "ansibrightcyan",  # 有效参数:亮天蓝
        "opt": "ansigray",  # --长/-短选项:灰色
        # 其他 token(class:default)不定义:保持终端默认白色
    }
)


class ShellLexer(Lexer):
    """实时词法着色:有效命令黄、有效参数亮天蓝、有效选项灰,其余默认白。"""

    def lex_document(self, document):
        def get_line(lineno: int):
            if lineno != 0:
                return []
            tokens: list[tuple[str, str]] = []
            parts = document.text.split()
            index = 0
            first = parts[0] if parts else ""
            is_known_cmd = first in _KNOWN_COMMANDS
            valid_args = _COMMAND_ARGS.get(first, set()) if is_known_cmd else set()
            for i, part in enumerate(parts):
                start = document.text.find(part, index)
                if start > index:
                    tokens.append(("class:space", document.text[index:start]))
                if i == 0 and is_known_cmd:
                    style = "class:cmd"
                elif part.startswith("-") and part in _VALID_OPTIONS:
                    style = "class:opt"
                elif i > 0 and part in valid_args:
                    style = "class:param"
                else:
                    style = "class:default"
                tokens.append((style, part))
                index = start + len(part)
            if index < len(document.text):
                tokens.append(("class:space", document.text[index:]))
            return tokens

        return get_line


_pt_history = InMemoryHistory()


def _read_line(prompt: str) -> str:
    """读取输入行:tty 用 prompt_toolkit(实时着色 + 方向键历史),否则回退 input。"""
    if sys.stdin.isatty():
        return pt_prompt(
            prompt,
            lexer=ShellLexer(),
            style=SHELL_STYLE,
            history=_pt_history,
        )
    return input(prompt)


def run_shell(_input: Callable[[str], str] = _read_line) -> None:
    """交互式主循环。_input 可注入(测试用);Ctrl+C/Ctrl+D 正常退出。"""
    _history.clear()
    print(_BANNER)
    while True:
        try:
            line = _input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print("退出")
            return
        cmd, args = parse_line(line)
        if not cmd:
            continue
        if cmd in ("exit", "quit"):
            print("退出")
            return
        if line.strip() not in _history:
            _history.append(line.strip())
        entry = _COMMANDS.get(cmd)
        if entry is None:
            print(f"未知命令: {cmd}(输入 help 查看可用命令)")
            continue
        if args == ["--help"]:
            _print_command_help(cmd)
            continue
        try:
            entry[1](args)
        except Exception:
            logger.exception("命令执行失败: %s", cmd)
            print(f"命令执行出错: {cmd}(详情见日志)")
