"""交互式 shell:供测试命令的 REPL 输入口。"""
from __future__ import annotations

import logging
import sys
from typing import Callable, Literal

from datetime import datetime, timezone

from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.shortcuts import prompt as pt_prompt
from prompt_toolkit.styles import Style

from rp_agent.api.args import KNOWN_OPTIONS, parse_args
from rp_agent.api.client import ApiError, list_models, test_connection
from rp_agent.api.models import ApiConnection, mask_key
from rp_agent.api.store import (
    delete_connection,
    get_connection,
    list_connections,
    save_connection,
    set_default_connection,
)
from rp_agent.config import get_config, reload_config
from rp_agent.help_data import HELP_ENTRIES, find_entry
from rp_agent.storage import DATA_DIR, ensure_dirs
from rp_agent.term import blue, gray, yellow

logger = logging.getLogger("rp_agent")


def _chat_business(attr: str):
    from rp_agent.core import chat as chat_module

    return getattr(chat_module, attr)

Mode = Literal["home", "chat", "rp", "agent"]
_MODE_COMMANDS: dict[str, Mode] = {"chat": "chat", "rp": "rp", "agent": "agent"}
_CHAT_COMMANDS: set[str] = {"new", "list", "load"}
_current_mode: Mode = "home"
_chat_session = None  # ChatSession | None,运行时赋值(避免循环 import)
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
            print("用法: config timeout <秒>")
            return
        try:
            secs = float(args[1])
        except ValueError:
            print(f"非法超时: {args[1]}")
            return
        if secs <= 0:
            print("超时必须为正数")
            return
        from rp_agent.config import save_config

        save_config({"timeout": secs})
        reload_config()
        print(f"已设置全局超时: {secs}s")
        return
    cfg = get_config()
    print(f"log_level={cfg.log_level}")
    print(f"timeout={cfg.timeout}s")


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
        print(f"用法: {_colorize_usage('api <list|get|add|del|test|pull|sync|modify> ...')}")
        return
    sub = args[0]
    try:
        _dispatch_api(sub, args[1:])
    except ValueError as exc:
        print(f"参数错误: {exc}")
    except ApiError as exc:
        print(f"API 错误: {exc}")


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
        print(f"未知子命令: {sub}(用法: api <list|get|add|del|test|pull|sync|modify> ...)")


def _api_use(rest: list[str]) -> None:
    """设置全局默认连接(仅 home 模式)。"""
    if _current_mode != "home":
        print("api use 仅可在 home 模式使用")
        return
    if not rest:
        print("用法: api use <name>")
        return
    name = rest[0]
    if get_connection(name) is None:
        print(f"连接不存在: {name}")
        return
    set_default_connection(name)
    print(f"已设置全局默认连接: {name}")


def _api_set(rest: list[str]) -> None:
    """切换当前会话连接(仅对话模式内)。"""
    if _current_mode == "home":
        print("api set 仅可在对话模式内使用")
        return
    if not rest:
        print("用法: api set <name>")
        return
    name = rest[0]
    if get_connection(name) is None:
        print(f"连接不存在: {name}")
        return
    if _chat_session is None:
        print("当前无会话,请先 /new 或 /load")
        return
    _chat_business("set_connection")(_chat_session, name)


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
            print(f"[警告] 忽略非法筛选: {f}(应为 k=v)")
            continue
        k, v = f.split("=", 1)
        conns = [c for c in conns if str(getattr(c, k, "")).startswith(v)]
    if not conns:
        print("(无连接)")
        return
    if "verbose" in opts:
        for c in conns:
            print(f"{c.name}\t{c.base_url}\t{c.model}\t{c.last_tested or '-'}")
    else:
        for c in conns:
            print(f"  {c.name}")


def _api_get(rest: list[str]) -> None:
    _, pos = parse_args(rest)
    if not pos:
        print("用法: api get <name>")
        return
    conn = get_connection(pos[0])
    if conn is None:
        print(f"连接不存在: {pos[0]}")
        return
    print(f"name={conn.name}")
    print(f"base_url={conn.base_url}")
    print(f"api_key={mask_key(conn.api_key) if conn.api_key else '(空)'}")
    print(f"model={conn.model}")
    print(f"timeout={conn.timeout}")
    print(f"models_endpoint={conn.models_endpoint}")
    print(f"last_tested={conn.last_tested or '(未测试)'}")


def _api_add(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    name = opts.get("name") or (pos[0] if pos else None)
    url = opts.get("url") or (pos[1] if len(pos) > 1 else None)
    key = opts.get("key") or (pos[2] if len(pos) > 2 else None)
    model = opts.get("model") or (pos[3] if len(pos) > 3 else "")
    if not (name and url and key):
        print("用法: api add --name <name> --url <base_url> --key <api_key> [--model <model>]")
        print("  或(弃用) api add <name> <base_url> <api_key> [model]")
        return
    if pos:
        print("[弃用] 位置参数形式将移除,请改用 --name/--url/--key/--model")
    if get_connection(name) is not None and "modify" not in opts:
        print(f"连接已存在: {name}(使用 api modify {name} 或 api add --modify ... 覆盖)")
        return
    conn = ApiConnection(name=name, base_url=url, api_key=key, model=model)
    if "pull" in opts:
        try:
            models = list_models(conn)
            print(f"拉取到模型: {', '.join(models)}")
        except ApiError as exc:
            print(f"[警告] 拉取模型失败({exc}),仍保存连接(可后续 api pull)")
    try:
        save_connection(conn)
        print(f"已保存连接: {name}")
        if not model:
            print("提示: 未设置默认模型,可用 api modify 设置")
    except ValueError as exc:
        print(f"配置无效: {exc}")


def _api_del(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api del <name> [-f]")
        return
    name = pos[0]
    if "force" not in opts:
        ans = _confirm(f"确认删除连接 {name}? [y/N]: ")
        if ans.lower() not in ("y", "yes"):
            print("已取消")
            return
    if delete_connection(name):
        print(f"已删除连接: {name}")
    else:
        print(f"连接不存在: {name}")


def _api_test(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api test <name> [--timeout <秒>]")
        return
    conn = get_connection(pos[0])
    if conn is None:
        print(f"连接不存在: {pos[0]}")
        return
    timeout = float(opts.get("timeout", get_config().timeout))
    print(f"正在测试连接: {conn.name} ({conn.base_url})…")
    try:
        test_connection(conn, timeout=timeout)
        conn.last_tested = datetime.now(timezone.utc).isoformat()
        save_connection(conn)
        print("连接正常")
    except ApiError as exc:
        print(f"测试失败: {exc}")


def _api_pull(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if pos:
        conn = get_connection(pos[0])
        if conn is None:
            print(f"连接不存在: {pos[0]}")
            return
    elif "url" in opts and "key" in opts:
        conn = ApiConnection(name="(临时)", base_url=opts["url"], api_key=opts["key"], model="")
        try:
            conn.validate()
        except ValueError as exc:
            print(f"URL 无效: {exc}")
            return
    else:
        print("用法: api pull <name> [--set-default] | api pull --url <base_url> --key <api_key> [--timeout <秒>]")
        return
    timeout = float(opts.get("timeout", get_config().timeout))
    try:
        models = list_models(conn, timeout=timeout)
        for i, m in enumerate(models, 1):
            print(f"  {i}. {m}")
        if "set-default" in opts and models and pos:
            conn.model = models[0]
            save_connection(conn)
            print(f"已将默认模型设为: {models[0]}")
    except ApiError as exc:
        print(f"拉取失败: {exc}")


def _api_sync(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api sync <name> [--set-default]")
        return
    conn = get_connection(pos[0])
    if conn is None:
        print(f"连接不存在: {pos[0]}")
        return
    timeout = float(opts.get("timeout", get_config().timeout))
    try:
        test_connection(conn)
        models = list_models(conn)
        print("测试通过,模型列表:")
        for i, m in enumerate(models, 1):
            print(f"  {i}. {m}")
        conn.last_tested = datetime.now(timezone.utc).isoformat()
        if "set-default" in opts and models:
            conn.model = models[0]
            print(f"已将默认模型设为: {models[0]}")
        save_connection(conn)
    except ApiError as exc:
        print(f"同步失败: {exc}")


def _api_modify(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api modify <name> [--set field=value ...]")
        return
    conn = get_connection(pos[0])
    if conn is None:
        print(f"连接不存在: {pos[0]}")
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
            bottom_toolbar="^O 保存   ^X 放弃   /url /key /model 跳转字段",
        )
    except KeyboardInterrupt:
        return "", "cancel"
    return text, state["action"]


def _modify_interactive(conn: ApiConnection) -> None:
    """交互式编辑:nano 风格(Ctrl+O 保存 / Ctrl+X 放弃)+ 字段跳转。"""
    fields = [
        ("base_url", "Base URL", False),
        ("api_key", "API Key", True),
        ("model", "Model", False),
    ]
    values: dict[str, str] = {
        "base_url": conn.base_url,
        "api_key": conn.api_key,
        "model": conn.model,
    }
    current = 0
    while True:
        field, label, secret = fields[current]
        text, action = _prompt_field(label, values[field], secret)
        if action == "cancel":
            print("已放弃修改")
            return
        if text.startswith("/"):
            target = text[1:].lower()
            names = {f[0]: i for i, f in enumerate(fields)}
            if target in names:
                current = names[target]
                continue
            print(f"未知字段: {target}(可用: /url /key /model)")
            continue
        if text == "":
            text = values[field]  # 回车保留原值
        if field == "base_url" and not (
            text.startswith("http://") or text.startswith("https://")
        ):
            print("Base URL 无效,需以 http(s):// 开头")
            continue
        values[field] = text
        if action == "save":
            for k, v in values.items():
                setattr(conn, k, v)
            save_connection(conn)
            print("已保存")
            return
        current = (current + 1) % len(fields)


def _api_modify_set(conn: ApiConnection, sets: list[str]) -> None:
    """非交互 --set:先验证全部,再原子更新。"""
    updates: dict[str, object] = {}
    for s in sets:
        if "=" not in s:
            print(f"非法 --set: {s}(应为 field=value)")
            return
        k, v = s.split("=", 1)
        if k not in ("base_url", "api_key", "model", "timeout", "models_endpoint"):
            print(f"未知字段: {k}")
            return
        updates[k] = v
    for k, v in updates.items():
        if k == "base_url" and not (
            v.startswith("http://") or v.startswith("https://")
        ):
            print(f"base_url 无效: {v}")
            return
        if k == "timeout":
            try:
                float(v)
            except ValueError:
                print(f"timeout 无效: {v}")
                return
    for k, v in updates.items():
        setattr(conn, k, float(v) if k == "timeout" else v)
    save_connection(conn)
    print(f"已更新连接: {conn.name}")


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
        )
    return input(prompt)


def run_shell(
    _input: Callable[[str], str] = _read_line, initial_mode: Mode = "home"
) -> None:
    """交互式主循环。_input 可注入(测试用);Ctrl+C/Ctrl+D 正常退出。

    模式:home 为默认;chat 为真实对话;rp/agent 仍为占位。
    非 home 模式下,非 / 开头的输入在 chat 模式视为对话消息,其余模式打印占位报错;
    / 开头的输入剥掉 / 后走正常命令分派,其中 /exit 返回 home(home 模式 /exit 退出 shell)。
    """
    global _current_mode, _chat_session
    _history.clear()
    mode = initial_mode
    print(_BANNER)
    while True:
        _current_mode = mode
        try:
            line = _input(_prompt_for_mode(mode))
        except (EOFError, KeyboardInterrupt):
            print("退出")
            return
        cmd, args = parse_line(line)
        if not cmd:
            continue
        if line.strip() not in _history:
            _history.append(line.strip())
        escaped = cmd.startswith("/")
        if escaped:
            cmd = cmd[1:]
        if not cmd:
            continue
        if cmd in ("exit", "quit"):
            if escaped and mode != "home":
                mode = "home"
                continue
            if mode == "home":
                print("退出")
                return
            print(gray(_placeholder_msg(mode)))
            continue
        if mode != "home" and not escaped:
            if mode == "chat":
                if _chat_session is None:
                    _chat_session = _chat_business("new_session")()
                _chat_business("send_message")(_chat_session, line.strip())
            else:
                print(gray(_placeholder_msg(mode)))
            continue
        if args == ["--help"]:
            _print_command_help(cmd)
            continue
        if cmd in _MODE_COMMANDS:
            mode = _MODE_COMMANDS[cmd]
            if mode == "chat":
                # 每次进入 chat 都新建会话(用当前默认连接),不复用旧会话
                _chat_session = _chat_business("new_session")()
            continue
        if mode != "home" and cmd in _CHAT_COMMANDS:
            if cmd == "new":
                _chat_session = _chat_business("new_session")()
            elif cmd == "list":
                _chat_business("list_sessions")()
            elif cmd == "load":
                if args:
                    loaded = _chat_business("load_session")(args[0])
                    if loaded is not None:
                        _chat_session = loaded
                else:
                    print("用法: /load <会话id>(用 /list 查看)")
            continue
        entry = _COMMANDS.get(cmd)
        if entry is None:
            print(f"未知命令: {cmd}(输入 help 查看可用命令)")
            continue
        try:
            entry[1](args)
        except Exception:
            logger.exception("命令执行失败: %s", cmd)
            print(f"命令执行出错: {cmd}(详情见日志)")
