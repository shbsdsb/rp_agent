"""API 连接管理命令:api 子命令分派与各子命令处理器(含交互编辑)。

共享状态(_current_mode/_chat_session)与可 monkeypatch 的名字
(_confirm/_prompt_field/_modify_interactive/test_connection/list_models/is_tui)
统一经 `rp_agent.shell` 包命名空间运行时访问,保证 REPL/TUI/测试共享同一份。
"""
from __future__ import annotations

from datetime import datetime, timezone

from prompt_toolkit.key_binding import KeyBindings

from rp_agent.api.args import parse_args
from rp_agent.api.client import ApiError
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
from rp_agent.config import get_config
from rp_agent.output import emit
from rp_agent.shell.chat_cmds import _chat_business
from rp_agent.term import yellow


def _cmd_api(args: list[str]) -> None:
    if not args:
        from rp_agent.shell.commands import _colorize_usage

        emit(
            f"用法: {_colorize_usage('api <list|get|add|del|test|pull|sync|modify|use|set> ...')}"
        )
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
    import rp_agent.shell as shell_mod

    if shell_mod._current_mode != "home":
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
    import rp_agent.shell as shell_mod

    if shell_mod._current_mode == "home":
        emit("api set 仅可在对话模式内使用")
        return
    if not rest:
        emit("用法: api set <name>")
        return
    name = rest[0]
    if get_connection(name) is None:
        emit(f"连接不存在: {name}")
        return
    if shell_mod._chat_session is None:
        emit("当前无会话,请先 /new 或 /load")
        return
    _chat_business("set_connection")(shell_mod._chat_session, name)


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
    import rp_agent.shell as shell_mod

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
            models = shell_mod.list_models(conn)
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
    import rp_agent.shell as shell_mod

    opts, pos = parse_args(rest)
    if not pos:
        emit("用法: api del <name> [-f]")
        return
    name = pos[0]
    if "force" not in opts:
        ans = shell_mod._confirm(f"确认删除连接 {name}? [y/N]: ")
        if not ans or ans.lower() not in ("y", "yes"):
            emit("已取消")
            return
    if delete_connection(name):
        emit(f"已删除连接: {name}")
    else:
        emit(f"连接不存在: {name}")


def _api_test(rest: list[str]) -> None:
    import rp_agent.shell as shell_mod

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
        shell_mod.test_connection(conn, timeout=timeout)
        conn.last_tested = datetime.now(timezone.utc).isoformat()
        save_connection(conn)
        emit("连接正常")
    except ApiError as exc:
        emit(f"测试失败: {exc}")


def _api_pull(rest: list[str]) -> None:
    import rp_agent.shell as shell_mod

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
        models = shell_mod.list_models(conn, timeout=timeout)
        for i, m in enumerate(models, 1):
            emit(f"  {i}. {m}")
        if "set-default" in opts and models and pos:
            conn.model = models[0]
            save_connection(conn)
            emit(f"已将默认模型设为: {models[0]}")
    except ApiError as exc:
        emit(f"拉取失败: {exc}")


def _api_sync(rest: list[str]) -> None:
    import rp_agent.shell as shell_mod

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
        shell_mod.test_connection(conn, timeout=timeout)
        models = shell_mod.list_models(conn, timeout=timeout)
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
    import rp_agent.shell as shell_mod

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
    elif shell_mod.is_tui():
        emit("TUI 下请使用非交互形式:api modify <name> --set field=value")
    else:
        shell_mod._modify_interactive(conn)


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
    import rp_agent.shell as shell_mod

    # 跳转短名 → 字段名(/url /key 是 UI token,字段键是 base_url/api_key)
    _SLASH_ALIASES = {"url": "base_url", "key": "api_key"}
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
        text, action = shell_mod._prompt_field(label, values[field], secret)
        if action == "cancel":
            emit("已放弃修改")
            return
        if text.startswith("/"):
            target = text[1:].lower()
            names = {f[0]: i for i, f in enumerate(fields)}
            field_name = _SLASH_ALIASES.get(target, target)
            if field_name in names:
                current = names[field_name]
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
