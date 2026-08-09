"""chat 模式:真实 AI 对话(多轮上下文 + 会话持久化)。"""
from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from rp_agent import output
from rp_agent.api.client import ApiError, chat
from rp_agent.api.store import get_connection, get_default_connection, list_connections
from rp_agent.core import session as session_store
from rp_agent.output import emit
from rp_agent.term import rgb

SYSTEM_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "system" / "chat.txt"
)

# assistant> 前缀色:#66AAFF(与输入前缀 chat> 的 #FFE066 区分)
ASSISTANT_PREFIX = "assistant> "
# user> 前缀色:暖黄(与输入前缀 chat> 的 #FFE066 同色系;assistant 用 #66AAFF 区分)
USER_PREFIX = "user> "

# TUI 请求进行中标志:后台线程请求期间为 True,TUI 点阵加载动画轮询它
_request_active = False


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
    emit(f"新会话: {s.id}")
    if connection:
        conn = get_connection(connection)
        model = conn.model if conn else "?"
        emit(f"连接: {connection} | 模型: {model}")
        emit("提示: /api set <name> 可临时切换连接;/exit 返回 home")
    else:
        emit("未设置全局默认连接,请在 home 模式用 api use <name> 设置")
        conns = list_connections()
        if conns:
            emit("可用连接: " + ", ".join(conns))
        else:
            emit("当前没有任何 API 连接,请先回 home 用 api add 添加")
    return s


def send_message(s: session_store.ChatSession, text: str) -> None:
    """发送一条用户消息:TUI 下异步(立即 emit user + 后台请求,避免阻塞事件循环),
    CLI 下同步(spinner 点阵/静态提示)。

    连接不存在时不写入消息——避免"未发出却已持久化"的悬空 user 消息污染上下文
    (重试/换连接后 AI 会收到一条无 assistant 回复的重复问题)。
    """
    conn = get_connection(s.connection)
    if conn is None:
        emit(f"未设置连接: 请用 /api set <name> 或回 home 用 api use <name> 设置")
        return
    session_store.append_message(s, "user", text)
    session_store.save_session(s)
    if output.is_tui():
        # TUI:user 立即渲染;API 调用放后台线程,主事件循环保持运转
        # (同步阻塞会导致 prompt_toolkit 无法重绘——user 与 assistant 一同渲染的根因)
        emit(f"{rgb(USER_PREFIX, 255, 224, 102)}{text}")
        _start_request(s, conn)
        return
    _do_request(s, conn)


def _do_request(s: session_store.ChatSession, conn) -> None:
    """实际请求:组装上下文 → spinner 中调用 API → emit assistant 并持久化。"""
    messages: list[dict] = []
    sp = system_prompt()
    if sp:
        messages.append({"role": "system", "content": sp})
    messages.extend(dict(m) for m in s.messages)
    from rp_agent.config import get_config

    try:
        with _spinner():
            reply = chat(conn, messages, timeout=get_config().timeout)
    except ApiError as exc:
        emit(f"API 错误: {exc}")
        return
    emit(f"{rgb(ASSISTANT_PREFIX, 102, 170, 255)}{reply}")
    session_store.append_message(s, "assistant", reply)
    session_store.save_session(s)


def _start_request(s: session_store.ChatSession, conn) -> None:
    """后台线程执行请求;期间置 _request_active(TUI spinner 动画轮询),结束复位。"""
    global _request_active
    _request_active = True

    def run() -> None:
        global _request_active
        try:
            _do_request(s, conn)
        finally:
            _request_active = False

    threading.Thread(target=run, daemon=True).start()


def list_sessions() -> None:
    """打印历史会话(最新在前);显示 name or id。"""
    sessions = session_store.list_sessions()
    if not sessions:
        emit("(无历史会话)")
        return
    for s in sessions:
        conn = s.connection or "(未设置)"
        emit(f"{_display_key(s)}  {s.updated_at}  连接: {conn}  消息数: {len(s.messages)}")


def load_session(session_id: str) -> session_store.ChatSession | None:
    s = session_store.load_session(session_id)
    if s is None:
        emit(f"会话不存在: {session_id}")
        return None
    emit(f"已加载会话: {s.id} | 连接: {s.connection or '(未设置)'} | 消息数: {len(s.messages)}")
    return s


def set_connection(s: session_store.ChatSession, name: str) -> None:
    """切换当前会话连接(api set):校验存在→更新→保存。"""
    if get_connection(name) is None:
        emit(f"连接不存在: {name}")
        return
    s.connection = name
    session_store.save_session(s)
    emit(f"已切换会话连接: {name}")


def _display_key(s: session_store.ChatSession) -> str:
    return s.name or s.id


def find_session(key: str) -> session_store.ChatSession | None:
    """按 id 精确,或按 name 匹配;找不到返回 None。"""
    key = key.strip()
    sessions = session_store.list_sessions()
    for s in sessions:
        if s.id == key:
            return s
    matches = [s for s in sessions if s.name == key]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        emit(f"名称 {key} 对应多个会话,请改用 id(chat list 查看)")
    return None


def get_session(key: str) -> None:
    s = find_session(key)
    if s is None:
        emit(f"会话不存在: {key}")
        return
    emit(f"会话: {_display_key(s)} | id: {s.id}")
    emit(f"连接: {s.connection or '(未设置)'} | 消息数: {len(s.messages)}")
    for i, m in enumerate(s.messages, 1):
        emit(f"  [{m.get('role', '?')}] {m.get('content', '')}")


def load_into_session(key: str) -> session_store.ChatSession | None:
    s = find_session(key)
    if s is None:
        emit(f"会话不存在: {key}")
        return None
    emit(f"已加载会话: {_display_key(s)} | 消息数: {len(s.messages)}")
    for i, m in enumerate(s.messages, 1):
        emit(f"  [{m.get('role', '?')}] {m.get('content', '')}")
    return s


def rename_session(s: session_store.ChatSession, new_name: str) -> None:
    new_name = new_name.strip()
    if not new_name:
        emit("名称不能为空")
        return
    s.name = new_name
    session_store.save_session(s)
    emit(f"已重命名: {_display_key(s)}")


def rename_by_key(key: str, new_name: str) -> None:
    s = find_session(key)
    if s is None:
        emit(f"会话不存在: {key}")
        return
    rename_session(s, new_name)


def session_names() -> list[str]:
    return [_display_key(s) for s in session_store.list_sessions()]


@contextmanager
def _spinner(label: str = "正在请求"):
    """点阵 spinner:tty 下后台线程 100ms 推进帧,非 tty 退化为静态一行,TUI 下静默。"""
    if output.is_tui():
        yield  # TUI 下静默:全屏渲染自有刷新,不打印占位
        return
    if not sys.stdin.isatty():
        emit(f"{label}…")
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
