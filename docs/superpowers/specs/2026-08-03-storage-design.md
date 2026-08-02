# 储存链路设计(基础设施层)

日期:2026-08-03
状态:已获用户口头批准

## 1. 背景

`rp-agent` 已完成 CLI 骨架与热重载。本阶段构建**储存链路基础设施**:项目根 `data/` 目录管理、JSON 读写封装、安全路径校验,为未来的角色卡/聊天记录/预设/API 连接等数据提供统一存储底座。

## 2. 目标与范围

### 做
- 项目根 `data/` 目录 + 四个子目录:characters/、chats/、presets/、api/
- 新增 `src/rp_agent/storage.py`:路径管理、JSON 读写、安全路径校验
- `data/` 加入 `.gitignore`(运行时数据不入库)
- 测试 `tests/test_storage.py`

### 不做
- 不做领域仓库层(CharacterRepository/ChatRepository 等,未来阶段)
- 不做数据 schema / 迁移 / 加密
- 不做 `data/` 可配置(固定项目根,用户已确认)

## 3. 技术方案

### 3.1 目录结构(项目根)

```
rp-agent/
└── data/                      # 固定:项目根/data(通过包路径推导,不依赖 cwd)
    ├── characters/            # 角色卡
    ├── chats/                 # 聊天记录
    ├── presets/               # RP 预设
    └── api/                   # API 连接配置
```

与 `configs/` 的区别:`configs/` 是包内只读默认配置资源(热重载用);`data/` 是项目根运行时可变数据,职责分离。

### 3.2 `storage.py` API

| API | 语义 |
|---|---|
| `DATA_DIR: Path` | 项目根/data:`Path(__file__).resolve().parents[2] / "data"`(src/rp_agent → 项目根) |
| `CHARACTERS_DIR / CHATS_DIR / PRESETS_DIR / API_DIR: Path` | 四个子目录常量 |
| `ensure_dirs() -> None` | 创建 data 及四个子目录,幂等(`mkdir(parents=True, exist_ok=True)`) |
| `json_read(path: Path) -> object \| None` | 读 JSON;文件缺失/损坏返回 `None` 并 `logger.warning`,不崩溃 |
| `json_write(path: Path, data: object) -> None` | 写 JSON(utf-8、`ensure_ascii=False`、缩进 2);父目录自动创建;**原子写入**(临时文件 + `os.replace`);失败 `logger.error` 不崩溃 |
| `safe_path(relative: str) -> Path` | 相对路径解析到 data 根;**防目录穿越**:含 `..` 逃逸抛 `ValueError` |

### 3.3 约定

- 所有 data 读写统一走 `storage.py`,禁止散落裸 `open()`/`Path.write_text` 直接操作 data
- `safe_path` 是读写前的必经校验;未来领域仓库层基于它构建

## 4. 错误处理

| 场景 | 处理 |
|---|---|
| data 目录不存在 | `ensure_dirs()` 自动创建 |
| JSON 缺失/损坏 | `json_read` 返回 `None` + 告警 |
| 写入失败(权限/磁盘) | `logger.error`,不抛异常中断 CLI |
| 相对路径含 `..` 逃逸 | `safe_path` 抛 `ValueError` |

## 5. 测试策略

| 测试 | 覆盖 |
|---|---|
| `test_data_dir_points_to_project_root` | `DATA_DIR` 指向项目根/data |
| `test_ensure_dirs_creates_subdirs` | monkeypatch `DATA_DIR` 到 tmp_path,`ensure_dirs()` 创建四个子目录且幂等 |
| `test_json_write_read_roundtrip` | `json_write` → `json_read` 往返一致 |
| `test_json_read_missing_returns_none` | 缺失文件返回 `None` |
| `test_json_read_broken_returns_none` | 损坏 JSON 返回 `None` |
| `test_safe_path_normal` | 合法相对路径解析到 data 根下 |
| `test_safe_path_traversal_raises` | `../` 逃逸抛 `ValueError` |

## 6. 文件清单

```
src/rp_agent/storage.py    # 新增:基础设施
tests/test_storage.py      # 新增:测试
.gitignore                 # 追加:data/
```

## 7. 兼容性

- 不修改现有模块;现有 22 项测试保持通过
- 不新增依赖(标准库 json/os/pathlib/logging)
- `uv.lock` 不变

## 8. 未来扩展点(记录,不在本阶段)

- 领域仓库层:CharacterRepository / ChatRepository / PresetRepository / ApiConnectionStore
- 数据 schema 与校验、聊天记录格式
- `data/` 可配置(如环境变量覆盖)
