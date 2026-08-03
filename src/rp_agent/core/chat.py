"""chat 模式:AI 聊天(占位,未来接 client.chat)。"""


def run() -> None:
    from rp_agent.shell import run_shell

    run_shell(initial_mode="chat")
