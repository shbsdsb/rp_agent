"""交互式 shell:供测试命令的 REPL 输入口。"""
from __future__ import annotations

import logging
import sys
from typing import Callable, Literal

from datetime import datetime, timezone

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.shortcuts import prompt as pt_prompt
from prompt_toolkit.styles import Style

from rp_agent.api.args import KNOWN_OPTIONS, parse_args
from rp_agent.api.client import ApiError, list_models, test_connection
from rp_agent.api.models import ApiConnection, mask_key
from rp_agent.api.store import (
    connection_exists,
    delete_connection,
    get_connection,
    get_default_name,
    list_connections,
    save_connection,
    set_default_connection,
)
from rp_agent.config import get_config, reload_config
from rp_agent.help_data import HELP_ENTRIES, find_entry
from rp_agent.output import emit
from rp_agent.term import blue, gray, yellow

logger = logging.getLogger("rp_agent")


def _chat_business(attr: str):
    from rp_agent.core import chat as chat_module

    return getattr(chat_module, attr)

Mode = Literal["home", "chat", "rp", "agent"]
_MODE_COMMANDS: dict[str, Mode] = {"chat": "chat", "rp": "rp", "agent": "agent"}
_CHAT_COMMANDS: set[str] = {"new", "list", "load", "rename"}
_current_mode: Mode = "home"
_chat_session = None  # ChatSession | None,运行时赋值(避免循环 import)
_mode_switch_request: Mode | None = None  # chat load 后请求切换模式
_quit_request = False
_ui_mode: Literal["tui", "cli"] = "tui"  # 默认全屏 TUI(Task 5 消费)
_ui_switch_request: Literal["tui", "cli"] | None = None  # 界面切换请求
_BANNER = "rp-agent 交互式 shell —— 输入 help 查看可用命令;chat/rp/agent 进入 AI 工作模式,模式内 / 转义调用命令,/exit 返回 home,exit 退出"
_history: list[str] = []


def _prompt_for_mode(mode: Mode) -> str:
    return {"home": "home> ", "chat": "chat> ", "rp": "rp> ", "agent": "agent> "}[mode]


def _placeholder_msg(mode: Mode) -> str:
    return f"[{mode}] 对话功能尚未实现(占位模式),/exit 返回 home"


def parse_line(line: str) -> tuple[str, list[str]]:
    """解析输入行 → (命令名, 参数列表);空行 → ("", [])。"""
    parts = line.strip().split()
    if not parts:
        return "", []
    return parts[0], parts[1:]


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


def _cmd_reload(_args: list[str]) -> None:
    changed = reload_config()
    cfg = get_config()
    emit(f"配置已重载,发生变化: {changed},log_level={cfg.log_level}")


def _cmd_hello(_args: list[str]) -> None:
    cfg = get_config()
    emit(f"你好!rp-agent 骨架已就绪,当前日志级别: {cfg.log_level}")
    logger.info("shell 中执行 hello")


def _cmd_history(_args: list[str]) -> None:
    for i, h in enumerate(_history, start=1):
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


def _cmd_api(args: list[str]) -> None:
    if not args:
        emit(f"用法: {_colorize_usage('api <list|get|add|del|test|pull|sync|modify> ...')}")
        return
    sub = args[0]
    try:
        _dispatch_api(sub, args[1:])
    except ValueError as exc:
        emit(f"参数错误: {exc}")
    except ApiError as exc:
        emit(f"API 错误: {exc}")


def _dispatch_api(sub: str, rest: list[str]) -> None:
    if sub == "list":
        _api_list(rest)
    elif sub == "get":
        _api_get(rest)
    elif sub == "add":
        _api_add(rest)
    elif sub == "del":
        _api_del(rest)
    elif sub == "test":
        _api_test(rest)
    elif sub == "pull":
        _api_pull(rest)
    elif sub == "sync":
        _api_sync(rest)
    elif sub == "modify":
        _api_modify(rest)
    elif sub == "use":
        _api_use(rest)
    elif sub == "set":
        _api_set(rest)
    else:
        # 等效命令:api <name> -m [--set f=v ...] 等价 api modify <name> [--set f=v ...]
        opts, _ = parse_args(rest)
        if "modify" in opts:
            keep = [a for a in rest if a not in ("-m", "--modify")]
            _api_modify([sub] + keep)
            return
        emit(f"未知子命令: {sub}(用法: api <list|get|add|del|test|pull|sync|modify> ...)")


def _api_use(rest: list[str]) -> None:
    """设置全局默认连接(仅 home 模式)。"""
    if _current_mode != "home":
        emit("api use 仅可在 home 模式使用")
        return
    if not rest:
        emit("用法: api use <name>")
        return
    name = rest[0]
    if get_connection(name) is None:
        emit(f"连接不存在: {name}")
        return
    set_default_connection(name)
    emit(f"已设置全局默认连接: {name}")


def _api_set(rest: list[str]) -> None:
    """切换当前会话连接(仅对话模式内)。"""
    if _current_mode == "home":
        emit("api set 仅可在对话模式内使用")
        return
    if not rest:
        emit("用法: api set <name>")
        return
    name = rest[0]
    if get_connection(name) is None:
        emit(f"连接不存在: {name}")
        return
    if _chat_session is None:
        emit("当前无会话,请先 /new 或 /load")
        return
    _chat_business("set_connection")(_chat_session, name)


def _cmd_chat(args: list[str]) -> None:
    if not args:
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
    global _chat_session, _mode_switch_request
    loaded = _chat_business("load_into_session")(key)
    if loaded is not None:
        _chat_session = loaded
        _mode_switch_request = "chat"


def _chat_rename(rest: list[str]) -> None:
    if len(rest) == 2:
        _chat_business("rename_by_key")(rest[0], rest[1])
    elif len(rest) == 1:
        # 交互:第二行输入新名
        new_name = _read_line(f"新名称({rest[0]}): ").strip()
        if not new_name:
            emit("已取消")
            return
        _chat_business("rename_by_key")(rest[0], new_name)
    else:
        emit("用法: chat rename <旧名> <新名>(旧名输入时可按 Tab 补全选择)")


def _confirm(prompt: str) -> str:
    """交互确认(可被测试 monkeypatch)。"""
    return input(prompt).strip()


def _api_list(rest: list[str]) -> None:
    opts, _ = parse_args(rest)
    conns = [c for n in list_connections() if (c := get_connection(n)) is not None]
    filters = opts.get("filter", [])
    if isinstance(filters, str):
        filters = [filters]
    for f in filters:
        if "=" not in f:
            emit(f"[警告] 忽略非法筛选: {f}(应为 k=v)")
            continue
        k, v = f.split("=", 1)
        conns = [c for c in conns if str(getattr(c, k, "")).startswith(v)]
    if not conns:
        emit("(无连接)")
        return
    default_name = get_default_name()
    if "verbose" in opts:
        for c in conns:
            name_col = yellow(f"{c.name} *") if c.name == default_name else c.name
            emit(f"{name_col}\t{c.base_url}\t{c.model}\t{c.last_tested or '-'}")
    else:
        for c in conns:
            if c.name == default_name:
                emit(f"  {yellow(c.name + ' *')}")
            else:
                emit(f"  {c.name}")


def _api_get(rest: list[str]) -> None:
    _, pos = parse_args(rest)
    if not pos:
        emit("用法: api get <name>")
        return
    conn = get_connection(pos[0])
    if conn is None:
        emit(f"连接不存在: {pos[0]}")
        return
    emit(f"name={conn.name}")
    emit(f"base_url={conn.base_url}")
    emit(f"api_key={mask_key(conn.api_key) if conn.api_key else '(空)'}")
    emit(f"model={conn.model}")
    emit(f"timeout={conn.timeout}")
    emit(f"models_endpoint={conn.models_endpoint}")
    emit(f"last_tested={conn.last_tested or '(未测试)'}")


def _api_add(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    name = opts.get("name") or (pos[0] if pos else None)
    url = opts.get("url") or (pos[1] if len(pos) > 1 else None)
    key = opts.get("key") or (pos[2] if len(pos) > 2 else None)
    model = opts.get("model") or (pos[3] if len(pos) > 3 else "")
    if not (name and url and key):
        emit("用法: api add --name <name> --url <base_url> --key <api_key> [--model <model>]")
        emit("  或(弃用) api add <name> <base_url> <api_key> [model]")
        return
    if pos:
        emit("[弃用] 位置参数形式将移除,请改用 --name/--url/--key/--model")
    if connection_exists(name) and "modify" not in opts:
        emit(f"连接已存在: {name}(使用 api modify {name} 或 api add --modify ... 覆盖)")
        return
    conn = ApiConnection(name=name, base_url=url, api_key=key, model=model)
    if "pull" in opts:
        try:
            models = list_models(conn)
            emit(f"拉取到模型: {', '.join(models)}")
        except ApiError as exc:
            emit(f"[警告] 拉取模型失败({exc}),仍保存连接(可后续 api pull)")
    try:
        save_connection(conn)
        emit(f"已保存连接: {name}")
        if not model:
            emit("提示: 未设置默认模型,可用 api modify 设置")
    except ValueError as exc:
        emit(f"配置无效: {exc}")


def _api_del(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        emit("用法: api del <name> [-f]")
        return
    name = pos[0]
    if "force" not in opts:
        ans = _confirm(f"确认删除连接 {name}? [y/N]: ")
        if ans.lower() not in ("y", "yes"):
            emit("已取消")
            return
    if delete_connection(name):
        emit(f"已删除连接: {name}")
    else:
        emit(f"连接不存在: {name}")


def _api_test(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        emit("用法: api test <name> [--timeout <秒>]")
        return
    conn = get_connection(pos[0])
    if conn is None:
        emit(f"连接不存在: {pos[0]}")
        return
    timeout = float(opts.get("timeout", get_config().timeout))
    emit(f"正在测试连接: {conn.name} ({conn.base_url})…")
    try:
        test_connection(conn, timeout=timeout)
        conn.last_tested = datetime.now(timezone.utc).isoformat()
        save_connection(conn)
        emit("连接正常")
    except ApiError as exc:
        emit(f"测试失败: {exc}")


def _api_pull(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if pos:
        conn = get_connection(pos[0])
        if conn is None:
            emit(f"连接不存在: {pos[0]}")
            return
    elif "url" in opts and "key" in opts:
        conn = ApiConnection(name="(临时)", base_url=opts["url"], api_key=opts["key"], model="")
        try:
            conn.validate()
        except ValueError as exc:
            emit(f"URL 无效: {exc}")
            return
    else:
        emit("用法: api pull <name> [--set-default] | api pull --url <base_url> --key <api_key> [--timeout <秒>]")
        return
    timeout = float(opts.get("timeout", get_config().timeout))
    try:
        models = list_models(conn, timeout=timeout)
        for i, m in enumerate(models, 1):
            emit(f"  {i}. {m}")
        if "set-default" in opts and models and pos:
            conn.model = models[0]
            save_connection(conn)
            emit(f"已将默认模型设为: {models[0]}")
    except ApiError as exc:
        emit(f"拉取失败: {exc}")


def _api_sync(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        emit("用法: api sync <name> [--set-default]")
        return
    conn = get_connection(pos[0])
    if conn is None:
        emit(f"连接不存在: {pos[0]}")
        return
    timeout = float(opts.get("timeout", get_config().timeout))
    try:
        test_connection(conn)
        models = list_models(conn)
        emit("测试通过,模型列表:")
        for i, m in enumerate(models, 1):
            emit(f"  {i}. {m}")
        conn.last_tested = datetime.now(timezone.utc).isoformat()
        if "set-default" in opts and models:
            conn.model = models[0]
            emit(f"已将默认模型设为: {models[0]}")
        save_connection(conn)
    except ApiError as exc:
        emit(f"同步失败: {exc}")


def _api_modify(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        emit("用法: api modify <name> [--set field=value ...]")
        return
    conn = get_connection(pos[0])
    if conn is None:
        emit(f"连接不存在: {pos[0]}")
        return
    sets = opts.get("set", [])
    if isinstance(sets, str):
        sets = [sets]
    if sets:
        _api_modify_set(conn, sets)
    else:
        _modify_interactive(conn)


def _prompt_field(label: str, current: str, secret: bool) -> tuple[str, str]:
    """询问一个字段。返回 (text, action):action ∈ normal/save/cancel。"""
    from prompt_toolkit.shortcuts import prompt as pt_prompt

    kb = KeyBindings()
    state: dict[str, str] = {"action": "normal"}

    @kb.add("c-o")
    def _on_save(event):
        state["action"] = "save"
        event.app.exit(result=event.current_buffer.text)

    @kb.add("c-x")
    def _on_cancel(event):
        state["action"] = "cancel"
        event.app.exit(result=event.current_buffer.text)

    shown = mask_key(current) if secret and current else current
    try:
        text = pt_prompt(
            f"{label} (回车保留: {shown}): ",
            is_password=secret,
            key_bindings=kb,
            bottom_toolbar="^O 保存   ^X 放弃   /name /url /key /model 跳转字段",
        )
    except KeyboardInterrupt:
        return "", "cancel"
    return text, state["action"]


def _modify_interactive(conn: ApiConnection) -> None:
    """交互式编辑:nano 风格(Ctrl+O 保存 / Ctrl+X 放弃)+ 字段跳转。"""
    fields = [
        ("name", "Name", False),
        ("base_url", "Base URL", False),
        ("api_key", "API Key", True),
        ("model", "Model", False),
    ]
    values: dict[str, str] = {
        "name": conn.name,
        "base_url": conn.base_url,
        "api_key": conn.api_key,
        "model": conn.model,
    }
    old_name = conn.name
    current = 0
    while True:
        field, label, secret = fields[current]
        text, action = _prompt_field(label, values[field], secret)
        if action == "cancel":
            emit("已放弃修改")
            return
        if text.startswith("/"):
            target = text[1:].lower()
            names = {f[0]: i for i, f in enumerate(fields)}
            if target in names:
                current = names[target]
                continue
            emit(f"未知字段: {target}(可用: /url /key /model)")
            continue
        if text == "":
            text = values[field]  # 回车保留原值
        if field == "base_url" and not (
            text.startswith("http://") or text.startswith("https://")
        ):
            emit("Base URL 无效,需以 http(s):// 开头")
            continue
        values[field] = text
        if action == "save":
            for k, v in values.items():
                setattr(conn, k, v)
            if _persist_connection(conn, old_name):
                emit("已保存")
            return
        current = (current + 1) % len(fields)


def _persist_connection(conn: ApiConnection, old_name: str) -> bool:
    """保存连接;改名时校验冲突并删除旧文件。成功返回 True,失败打印原因。"""
    if not conn.name.strip():
        emit("连接名不能为空")
        return False
    if conn.name != old_name and connection_exists(conn.name):
        emit(f"连接已存在: {conn.name}")
        return False
    try:
        save_connection(conn)
    except ValueError as exc:
        emit(f"配置无效: {exc}")
        return False
    if conn.name != old_name:
        delete_connection(old_name)
    return True


def _api_modify_set(conn: ApiConnection, sets: list[str]) -> None:
    """非交互 --set:先验证全部,再原子更新。"""
    updates: dict[str, object] = {}
    for s in sets:
        if "=" not in s:
            emit(f"非法 --set: {s}(应为 field=value)")
            return
        k, v = s.split("=", 1)
        if k not in ("base_url", "api_key", "model", "timeout", "models_endpoint", "name"):
            emit(f"未知字段: {k}")
            return
        updates[k] = v
    for k, v in updates.items():
        if k == "base_url" and not (
            v.startswith("http://") or v.startswith("https://")
        ):
            emit(f"base_url 无效: {v}")
            return
        if k == "timeout":
            try:
                float(v)
            except ValueError:
                emit(f"timeout 无效: {v}")
                return
    old_name = conn.name
    for k, v in updates.items():
        setattr(conn, k, float(v) if k == "timeout" else v)
    if not _persist_connection(conn, old_name):
        return
    emit(f"已更新连接: {conn.name}")


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
    "help": _KNOWN_COMMANDS,
    "?": _KNOWN_COMMANDS,
}

# 有效选项(--长选项 / -短选项,灰色):全部已知选项(与 args.py 同步)
_VALID_OPTIONS: set[str] = KNOWN_OPTIONS

SHELL_STYLE = Style.from_dict(
    {
        "cmd": "ansiyellow bold",  # 有效命令:黄色
        "param": "ansibrightcyan",  # 有效参数:亮天蓝
        "opt": "ansibrightblack",  # 有效选项:灰色(prompt_toolkit 无 ansigray,用亮黑)
        "chat-prompt": "#FFE066 bold",  # chat 模式输入前缀:暖黄(与 assistant> 的 #66AAFF 区分)
        "status": "bg:#1a1a2e #e0e0e0",  # 状态栏:深底浅字
        "status-mode": "ansiyellow bold",
        "status-dim": "ansibrightblack",
        "hint": "ansibrightblack",
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
            bare = first[1:] if first.startswith("/") else first  # / 转义命令剥前缀后判断
            is_known_cmd = bare in _KNOWN_COMMANDS
            valid_args = _COMMAND_ARGS.get(bare, set()) if is_known_cmd else set()
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


# 命令名补全候选:已知命令 + / 转义变体(模式内 /load、/exit 等)
_COMMAND_NAMES: set[str] = _KNOWN_COMMANDS | {f"/{c}" for c in _KNOWN_COMMANDS}


class ShellCompleter(Completer):
    """全范围 Tab 补全(dropdown):命令名/蓝色子命令/灰色选项/连接名/会话名。

    与 ShellLexer 共用 _KNOWN_COMMANDS/_COMMAND_ARGS/_VALID_OPTIONS 数据源,
    保证"着色的词 = 可补全的词"。按正在输入词的 0-based 位置分派:
    0=命令名,1=蓝色子命令,2=第一位置参数(词以 - 开头时优先补选项)。
    """

    # (命令, 子命令) → 第一个位置参数类型;未列出者不补位置参数
    _POSITIONAL: dict[tuple[str, str], str] = {
        ("api", "get"): "connection",
        ("api", "del"): "connection",
        ("api", "test"): "connection",
        ("api", "pull"): "connection",
        ("api", "sync"): "connection",
        ("api", "modify"): "connection",
        ("api", "use"): "connection",
        ("api", "set"): "connection",
        ("chat", "get"): "session",
        ("chat", "load"): "session",
        ("chat", "rename"): "session",
    }

    def get_completions(self, document, complete_event):
        text = document.text
        if not text.strip():
            yield from self._words(_COMMAND_NAMES, document, complete_event)
            return
        parts = text.split()
        # 尾空格说明上一词已完成、正在输入新词
        position = len(parts) if text.endswith(" ") else len(parts) - 1
        if position == 0:
            yield from self._words(_COMMAND_NAMES, document, complete_event)
            return
        first = parts[0]
        if first == "/load" and position == 1:
            yield from self._sessions(document, complete_event)
            return
        cmd = first.lstrip("/")
        if position == 1:
            subs = _COMMAND_ARGS.get(cmd, set())
            if subs:
                yield from self._words(subs, document, complete_event)
            return
        current = parts[-1]
        if current.startswith("-"):
            # 选项补全:任意后续位置(第 3+ 词)均可补,与规格一致
            if position >= 2:
                yield from self._words(_VALID_OPTIONS, document, complete_event)
            return
        if position != 2:
            return  # 只补第一个位置参数(chat rename 第二参等不补)
        ptype = self._POSITIONAL.get((cmd, parts[1]))
        if ptype == "connection":
            try:
                names = list_connections()
            except Exception:
                return
            yield from self._words(names, document, complete_event)
        elif ptype == "session":
            yield from self._sessions(document, complete_event)

    def _sessions(self, document, complete_event):
        try:
            names = _chat_business("session_names")() or []
        except Exception:
            return
        yield from self._words(names, document, complete_event)

    @staticmethod
    def _words(words, document, complete_event):
        """对 words 做大小写不敏感前缀补全。

        用 WORD=True 提取正在输入的完整词(含 / 前缀、-- 选项等,
        仅以空白分界),避免 WordCompleter 的字母数字正则把 / 当分隔符。
        """
        if not words:
            return
        word = document.get_word_before_cursor(WORD=True)
        lower = word.lower()
        for w in sorted(words):
            if w.lower().startswith(lower):
                yield Completion(text=w, start_position=-len(word) if word else 0)


_pt_history = InMemoryHistory()


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
    """交互式主循环(逐行 REPL)。"""
    global _current_mode, _chat_session, _mode_switch_request, _quit_request
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
            return
        handle_line(line)
        if _quit_request:
            return


