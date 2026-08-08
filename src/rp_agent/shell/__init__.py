"""交互式 shell 包:REPL/TUI 共享的命令分派、输入读取与界面分发循环。

模块职责拆分:
- 本文件:模块级界面状态、`parse_line`/`handle_line`/`run_shell`/`_run_repl`/`_read_line`
- `commands.py`:基础命令、命令注册表、子命令/选项元数据
- `api_cmds.py`:api 连接管理命令(含交互编辑)
- `chat_cmds.py`:chat 会话命令与交互确认
- `completion.py`:词法着色(ShellLexer)与 Tab 补全(ShellCompleter)

状态与可 monkeypatch 的名字统一留在本包命名空间,子模块与 tui.py 经
`import rp_agent.shell as shell_mod` 运行时访问,保证 REPL/TUI/测试共享同一份。
"""
from __future__ import annotations

import logging
import sys
from typing import Callable, Literal

from prompt_toolkit.shortcuts import prompt as pt_prompt

# 被测试 monkeypatch 的外部名字:统一 re-export 到包命名空间
from rp_agent.api.client import ApiError, list_models, test_connection
from rp_agent.output import emit, is_tui
from rp_agent.term import gray

from rp_agent.shell.commands import (
    Mode,
    _CHAT_COMMANDS,
    _COMMAND_ARGS,
    _COMMANDS,
    _KNOWN_COMMANDS,
    _MODE_COMMANDS,
    _VALID_OPTIONS,
    _cmd_config,
    _cmd_hello,
    _cmd_help,
    _cmd_history,
    _cmd_reload,
    _colorize_usage,
    _placeholder_msg,
    _print_command_help,
    _prompt_for_mode,
)
from rp_agent.shell.chat_cmds import (
    _chat_business,
    _chat_load,
    _chat_rename,
    _cmd_chat,
    _confirm,
    _dispatch_chat,
)
from rp_agent.shell.api_cmds import (
    _api_add,
    _api_del,
    _api_get,
    _api_list,
    _api_modify,
    _api_modify_set,
    _api_pull,
    _api_set,
    _api_sync,
    _api_test,
    _api_use,
    _cmd_api,
    _dispatch_api,
    _modify_interactive,
    _persist_connection,
    _prompt_field,
)
from rp_agent.shell.completion import (
    SHELL_STYLE,
    ShellCompleter,
    ShellLexer,
    _COMMAND_NAMES,
    _pt_history,
)

logger = logging.getLogger("rp_agent")

_current_mode: Mode = "home"
_chat_session = None  # ChatSession | None,运行时赋值(避免循环 import)
_mode_switch_request: Mode | None = None  # chat load 后请求切换模式
_quit_request = False
_ui_mode: Literal["tui", "cli"] = "tui"  # 默认全屏 TUI(Task 5 消费)
_ui_switch_request: Literal["tui", "cli"] | None = None  # 界面切换请求
_BANNER = "rp-agent 交互式 shell —— 输入 help 查看可用命令;chat/rp/agent 进入 AI 工作模式,模式内 / 转义调用命令,/exit 返回 home,exit 退出"
_history: list[str] = []


def parse_line(line: str) -> tuple[str, list[str]]:
    """解析输入行 → (命令名, 参数列表);空行 → ("", [])。"""
    parts = line.strip().split()
    if not parts:
        return "", []
    return parts[0], parts[1:]


def _read_line(prompt: str) -> str:
    """读取输入行:tty 用 prompt_toolkit(实时着色 + 方向键历史),否则回退 input。"""
    if sys.stdin.isatty():
        # chat 模式输入前缀用 chat-prompt 样式(#FFE066)
        fmt: object = (
            [("class:chat-prompt", prompt)] if prompt == "chat> " else prompt
        )
        return pt_prompt(
            fmt,
            lexer=ShellLexer(),
            style=SHELL_STYLE,
            history=_pt_history,
            completer=ShellCompleter(),
        )
    return input(prompt)


def handle_line(line: str) -> None:
    """执行一行输入(与界面无关):命令分派/模式切换/对话消息。

    REPL 与 TUI 共用:模式变化写 _mode_switch_request(并同步 _current_mode,
    便于 REPL/TUI 在消费循环中读取);home 模式 exit 置 _quit_request。
    """
    global _current_mode, _chat_session, _mode_switch_request, _quit_request
    cmd, args = parse_line(line)
    if not cmd:
        return
    if line.strip() not in _history:
        _history.append(line.strip())
    escaped = cmd.startswith("/")
    if escaped:
        cmd = cmd[1:]
    if not cmd:
        return
    mode = _current_mode
    if cmd in ("exit", "quit"):
        if escaped and mode != "home":
            _mode_switch_request = "home"
            _current_mode = "home"
            return
        if mode == "home":
            emit("退出")
            _quit_request = True
            return
        emit(gray(_placeholder_msg(mode)))
        return
    if mode != "home" and not escaped:
        if mode == "chat":
            if _chat_session is None:
                _chat_session = _chat_business("new_session")()
            _chat_business("send_message")(_chat_session, line.strip())
        else:
            emit(gray(_placeholder_msg(mode)))
        return
    if args == ["--help"]:
        _print_command_help(cmd)
        return
    if cmd in _MODE_COMMANDS and (cmd != "chat" or not args):
        _mode_switch_request = _MODE_COMMANDS[cmd]
        _current_mode = _mode_switch_request
        if _mode_switch_request == "chat":
            _chat_session = _chat_business("new_session")()
        return
    if mode != "home" and cmd in _CHAT_COMMANDS:
        if mode != "chat":
            # rp/agent 占位模式:chat 会话命令不得越权执行,明确提示
            emit(f"/{cmd} 仅 chat 模式可用")
            return
        if cmd == "new":
            _chat_session = _chat_business("new_session")()
        elif cmd == "list":
            _chat_business("list_sessions")()
        elif cmd == "load":
            if args:
                _chat_load(args[0])
            else:
                emit("用法: /load <会话id|name>(用 /list 查看)")
        elif cmd == "rename":
            if args:
                _chat_business("rename_session")(_chat_session, args[0])
            else:
                emit("用法: /rename <新名称>")
        return
    entry = _COMMANDS.get(cmd)
    if entry is None:
        emit(f"未知命令: {cmd}(输入 help 查看可用命令)")
        return
    try:
        entry[1](args)
    except Exception:
        logger.exception("命令执行失败: %s", cmd)
        emit(f"命令执行出错: {cmd}(详情见日志)")


def run_shell(
    _input: Callable[[str], str] = _read_line, initial_mode: Mode = "home"
) -> None:
    """界面分发循环:TUI(默认)与旧 REPL 之间按 _ui_switch_request 切换。

    首轮以 initial_mode 启动;此后保留 _current_mode 跨界面切换(chat 模式
    reload --cli 切到 REPL 不应掉回 home),避免模式丢失造成状态错乱。
    """
    global _ui_mode, _ui_switch_request, _current_mode
    first = True
    while True:
        _ui_switch_request = None
        if first:
            _current_mode = initial_mode
            first = False
        mode = _current_mode
        if _ui_mode == "tui":
            try:
                from rp_agent.tui import run as tui_run

                tui_run(mode)
            except Exception:
                logger.exception("TUI 运行异常,回退 REPL")
                _run_repl(_input, mode)
        else:
            _run_repl(_input, mode)
        if _ui_switch_request is not None:
            _ui_mode = _ui_switch_request
            continue
        return


def _run_repl(
    _input: Callable[[str], str] = _read_line, initial_mode: Mode = "home"
) -> None:
    """逐行 REPL 循环(Task 2 改造后的原 run_shell 主体)。"""
    global _current_mode, _chat_session, _mode_switch_request, _quit_request, _ui_switch_request
    _history.clear()
    _quit_request = False
    mode = initial_mode
    emit(_BANNER)
    while True:
        if _mode_switch_request is not None:
            mode = _mode_switch_request
            _mode_switch_request = None
        _current_mode = mode
        try:
            line = _input(_prompt_for_mode(mode))
        except (EOFError, KeyboardInterrupt):
            emit("退出")
            _ui_switch_request = None  # 丢弃 pending 界面切换,避免 Ctrl+C 后误入 TUI
            return
        handle_line(line)
        if _ui_switch_request is not None:
            # REPL 侧即时消费界面切换请求,与 TUI 侧 _accept 对称:
            # reload --tui 后无需再 exit 即切入 TUI
            return
        if _quit_request:
            return
