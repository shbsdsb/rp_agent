"""储存链路基础设施:data 目录管理、JSON 读写、安全路径校验。"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("rp_agent")

# 项目根/data(通过包路径推导:src/rp_agent/storage.py -> 项目根)
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CHARACTERS_DIR = DATA_DIR / "characters"
CHATS_DIR = DATA_DIR / "chats"
PRESETS_DIR = DATA_DIR / "presets"
API_DIR = DATA_DIR / "api"

_SUB_NAMES = ("characters", "chats", "presets", "api")


def ensure_dirs() -> None:
    """创建 data 及四个子目录,幂等(动态基于 DATA_DIR,便于测试注入)。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in _SUB_NAMES:
        (DATA_DIR / name).mkdir(parents=True, exist_ok=True)


def json_read(path: Path) -> object | None:
    """读 JSON;文件缺失/损坏返回 None 并告警,不崩溃。"""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取 JSON 失败(%s): %s", path, exc)
        return None


def json_write(path: Path, data: object) -> None:
    """原子写 JSON(临时文件 + os.replace);失败告警不崩溃。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.error("写入 JSON 失败(%s): %s", path, exc)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def safe_path(relative: str) -> Path:
    """将相对路径解析到 data 根;拒绝绝对路径与 .. 逃逸,抛 ValueError。"""
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"非法路径(禁止目录穿越): {relative}")
    return (DATA_DIR / rel).resolve()
