"""chat 模式:真实 AI 对话(多轮上下文 + 会话持久化)。"""
from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from rp_agent.api.client import ApiError, chat
from rp_agent.api.store import get_connection, get_default_connection, list_connections
from rp_agent.core import session as session_store

SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "system" / "chat.txt"
)


def system_prompt() -> str | None:
    """读 prompts/system/chat.txt;缺失/读失败返回 None(无 system 降级)。"""
    try:
        text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
        return text or None
    except OSError:
        return None


def run() -> None:
    """CLI 入口:rp-agent chat 直接进入 chat 模式。"""
    from rp_agent.shell import run_shell

    run_shell(initial_mode="chat")


def new_session(connection: str = "") -> session_store.ChatSession:
    """创建新会话;connection 为空时取全局默认连接;打印欢迎/提示。"""
    if not connection:
        default = get_default_connection()
        connection = default.name if default else ""
    s = session_store.create_session(connection=connection)
    print(f"新会话: {s.id}")
    if connection:
        conn = get_connection(connection)
        model = conn.model if conn else "?"
        print(f"连接: {connection} | 模型: {model}")
        print("提示: /api set <name> 可临时切换连接;/exit 返回 home")
    else:
        print("未设置全局默认连接,请在 home 模式用 api use <name> 设置")
        conns = list_connections()
        if conns:
            print("可用连接: " + ", ".join(conns))
        else:
            print("当前没有任何 API 连接,请先回 home 用 api add 添加")
    return s


def send_message(s: session_store.ChatSession, text: str) -> None:
    """发送一条用户消息:先保存 user 消息,spinner 中阻塞调用,成功后追加 assistant。"""
    session_store.append_message(s, "user", text)
    session_store.save_session(s)
    conn = get_connection(s.connection)
    if conn is None:
        print(f"未设置连接: 请用 /api set <name> 或回 home 用 api use <name> 设置")
        return
    messages: list[dict] = []
    sp = system_prompt()
    if sp:
        messages.append({"role": "system", "content": sp})
    messages.extend(dict(m) for m in s.messages)
    try:
        with _spinner():
            reply = chat(conn, messages)
    except ApiError as exc:
        print(f"API 错误: {exc}")
        return
    print(reply)
    session_store.append_message(s, "assistant", reply)
    session_store.save_session(s)


def list_sessions() -> None:
    """打印历史会话(最新在前)。"""
    sessions = session_store.list_sessions()
    if not sessions:
        print("(无历史会话)")
        return
    for s in sessions:
        conn = s.connection or "(未设置)"
        print(f"{s.id}  {s.updated_at}  连接: {conn}  消息数: {len(s.messages)}")


def load_session(session_id: str) -> session_store.ChatSession | None:
    s = session_store.load_session(session_id)
    if s is None:
        print(f"会话不存在: {session_id}")
        return None
    print(f"已加载会话: {s.id} | 连接: {s.connection or '(未设置)'} | 消息数: {len(s.messages)}")
    return s


def set_connection(s: session_store.ChatSession, name: str) -> None:
    """切换当前会话连接(api set):校验存在→更新→保存。"""
    if get_connection(name) is None:
        print(f"连接不存在: {name}")
        return
    s.connection = name
    session_store.save_session(s)
    print(f"已切换会话连接: {name}")


@contextmanager
def _spinner(label: str = "正在请求"):
    """点阵 spinner:tty 下后台线程 100ms 推进帧,非 tty 退化为静态一行。"""
    if not sys.stdin.isatty():
        print(f"{label}…", flush=True)
        yield
        return
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    stop = threading.Event()

    def _run() -> None:
        i = 0
        while not stop.is_set():
            sys.stdout.write(f"\r{frames[i % len(frames)]} {label}…")
            sys.stdout.flush()
            i += 1
            time.sleep(0.1)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join()
        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()
