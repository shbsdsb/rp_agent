"""chat 会话命令:chat 子命令分派与交互确认。

状态(_current_mode/_chat_session/_mode_switch_request)与可 monkeypatch 的名字
(_read_line/is_tui/_confirm)统一经 `rp_agent.shell` 包命名空间运行时访问,
保证与 REPL/TUI/测试的共享契约一致。
"""
from __future__ import annotations

from rp_agent.output import emit


def _chat_business(attr: str):
    from rp_agent.core import chat as chat_module

    return getattr(chat_module, attr)


def _cmd_chat(args: list[str]) -> None:
    if not args:
        from rp_agent.shell.commands import _colorize_usage

        emit(f"用法: {_colorize_usage('chat <list|get|load|rename> ...')}")
        return
    _dispatch_chat(args[0], args[1:])


def _dispatch_chat(sub: str, rest: list[str]) -> None:
    if sub == "list":
        _chat_business("list_sessions")()
    elif sub == "get":
        if not rest:
            emit("用法: chat get <id|name>")
            return
        _chat_business("get_session")(rest[0])
    elif sub == "load":
        if not rest:
            emit("用法: chat load <id|name>")
            return
        _chat_load(rest[0])
    elif sub == "rename":
        _chat_rename(rest)
    else:
        emit(f"未知子命令: {sub}(用法: chat <list|get|load|rename> ...)")


def _chat_load(key: str) -> None:
    import rp_agent.shell as shell_mod

    loaded = _chat_business("load_into_session")(key)
    if loaded is not None:
        shell_mod._chat_session = loaded
        shell_mod._mode_switch_request = "chat"
        # TUI 不消费 _mode_switch_request(仅 _run_repl 消费),状态栏/输入分派/
        # _sync_mode_clear 都读 _current_mode,必须在此直接同步,否则 TUI 下
        # chat load 后界面仍停在 home(输入被按 home 命令分派)。
        shell_mod._current_mode = "chat"


def _chat_rename(rest: list[str]) -> None:
    import rp_agent.shell as shell_mod

    if len(rest) == 2:
        _chat_business("rename_by_key")(rest[0], rest[1])
    elif len(rest) == 1:
        if shell_mod.is_tui():
            emit("TUI 下请使用完整形式:chat rename <会话> <新名称>")
            return
        # 交互:第二行输入新名
        new_name = shell_mod._read_line(f"新名称({rest[0]}): ").strip()
        if not new_name:
            emit("已取消")
            return
        _chat_business("rename_by_key")(rest[0], new_name)
    else:
        emit("用法: chat rename <旧名> <新名>(旧名输入时可按 Tab 补全选择)")


def _confirm(prompt: str) -> str | bool:
    """交互确认(可被测试 monkeypatch)。TUI 下不可交互,返回 False 拒绝。

    REPL 下复用 _read_line(prompt_toolkit 交互:着色/历史/补全),符合
    "禁止裸 input()" 约定;Ctrl+C 转为"已取消"返回 False,避免冒泡崩溃。
    """
    import rp_agent.shell as shell_mod

    if shell_mod.is_tui():
        emit("TUI 下不可交互确认,请加 -f 参数")
        return False
    try:
        return shell_mod._read_line(prompt).strip()
    except KeyboardInterrupt:
        emit("已取消")
        return False
