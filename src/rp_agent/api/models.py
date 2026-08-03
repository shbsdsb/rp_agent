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
    timeout: float = 120.0
    models_endpoint: str = "/models"
    last_tested: str = ""

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
        if self.timeout <= 0:
            raise ValueError(f"timeout 必须为正数: {self.timeout}")


def mask_key(key: str) -> str:
    """密钥脱敏:长度<=8 显示 ****;否则 前4 + **** + 后4。"""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"
