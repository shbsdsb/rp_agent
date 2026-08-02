"""API 连接数据模型。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApiConnection:
    """OpenAI 兼容 API 连接配置。"""

    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float = 30.0

    def validate(self) -> None:
        """校验字段;非法抛 ValueError。"""
        if not self.name:
            raise ValueError("连接名不能为空")
        if not (
            self.base_url.startswith("http://")
            or self.base_url.startswith("https://")
        ):
            raise ValueError(
                f"base_url 必须以 http:// 或 https:// 开头: {self.base_url}"
            )
        if not self.model:
            raise ValueError("模型名不能为空")
        if self.timeout <= 0:
            raise ValueError(f"timeout 必须为正数: {self.timeout}")
