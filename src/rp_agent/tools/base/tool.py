"""工具基类:所有工具(未来含 MCP 工具)的统一接口锚点。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTool(ABC):
    """工具抽象基类。

    约定:子类必须定义 `name`/`description` 类属性并实现 `run()`。
    """

    name: str
    description: str

    @abstractmethod
    def run(self, **kwargs: object) -> str:
        """执行工具,返回结果文本。骨架阶段签名从简,后续按需演进。"""
        raise NotImplementedError
