import pytest

from rp_agent.tools.base.tool import BaseTool


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        BaseTool()  # type: ignore[abstract]


def test_concrete_tool_run():
    class EchoTool(BaseTool):
        name = "echo"
        description = "回显输入文本"

        def run(self, **kwargs: object) -> str:
            return str(kwargs.get("text", ""))

    tool = EchoTool()
    assert tool.name == "echo"
    assert tool.description == "回显输入文本"
    assert tool.run(text="hi") == "hi"
