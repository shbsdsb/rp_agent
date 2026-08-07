# 全屏 TUI 界面设计

- 日期:2026-08-08
- 状态:已获用户逐段确认
- 范围:rp-agent 交互界面从逐行 REPL 升级为全屏 TUI

## 背景与目标

当前 rp-agent 是逐行 REPL:输入一行命令 → 打印输出,输出被终端滚动淹没,多轮对话无法回看。目标是把交互界面升级为真正的全屏 TUI(prompt_toolkit `Application`),核心诉求是**可回看上下文(聊天/日志滚动)**。

## 需求确认(用户选择)

- 形态:真正的全屏 TUI(非 REPL 美化)
- 核心目标:可回看上下文(聊天/日志滚动)
- 覆盖模式:home/chat/rp/agent **全部统一**一套全屏布局
- 与旧 REPL 关系:运行中通过 `reload --tui` / `reload --cli` 命令切换界面(仅运行中命令,无启动参数)
- 默认界面:全屏 TUI
- 方案:自定义单屏布局(Window + 手动滚动管理),不用现成 ScrollablePane 控件

## 架构

新增模块 `src/rp_agent/tui.py`,承载全屏 Application 布局;与现有 `shell.py` 的命令/解析逻辑解耦复用。

```
┌──────────────────────────────────────────────┐
│ 状态栏  [home]  conn: openai · gpt-4o · s-xxx │  ← 顶部:模式/连接/模型/会话 id(chat 时)
├──────────────────────────────────────────────┤
│                                              │
│  输出区(可滚动,回看上下文)                    │  ← 中部:命令输出/对话消息/错误,滚轮+PageUp/Down
│                                              │
├──────────────────────────────────────────────┤
│ home> api list -v                            │  ← 底部:输入框,复用 ShellLexer 着色 + ShellCompleter 补全
└──────────────────────────────────────────────┘
```

### 组件

- **状态栏**:`Window` + 静态 `FormattedTextControl`,内容按当前模式/连接/会话动态更新;输入框正下方单独一行提示 `reload --tui/--cli 切换界面`(不作为状态栏内容,位置固定于界面底部)
- **输出区**:`Window` + `FormattedTextControl`,输出行存内存列表,可滚动(核心目标)
- **输入框**:复用现有 `ShellLexer`/`ShellCompleter`,提示符 `home>` / `chat>` 等按模式
- **布局**:`HSplit` 纵向三区,`full_screen=True`

## 输出区滚动与渲染机制(核心)

- **数据**:`_output_lines: list[FormattedText]`,每条输出(命令回显、对话消息、错误)追加为一行,颜色样式保留;上限 5000 行防内存膨胀
- **渲染**:`create_content(width, height)` 按可视高度对列表切片,只渲染可视行 → 滚动就是改切片偏移,零重绘浪费
- **滚动位置**:用"距末尾偏移" `_tail_offset`(0 = 贴底显示最新):
  - 用户贴底时,新输出到达 → 自动跟随(offset 保持 0)
  - 用户往上回看时 → 新输出到达不打断,offset 不变
  - 设计理由:显式 offset 完全绕开 prompt_toolkit 锚点(光标)机制——上次排查已知锚点在可视区内移动时视图不跟随,本次用显式滚动偏移规避
- **操作**:输出区绑定滚轮上/下、PageUp/PageDown、Home(回顶)/End(回底)
- **生命周期**:模式切换(chat/rp/agent/exit 回 home)清空输出区,开新上下文;`reload --cli/--tui` 切换界面时输出历史保存在模块级 `_output_lines`,跨界面会话保留,切回 TUI 还能看到
- **兜底**:渲染/滚动异常绝不崩进程,回退到逐行 `print` 输出

## 命令分发与界面切换

- **命令分发**:输入框回车 → 现有 `parse_line` 拆解 → 查 `_COMMANDS` 表执行 → 输出统一走"输出区追加"而不是 `print`;`_cmd_*` 函数内部逻辑原样复用,只把输出目标从 stdout 换成输出区(实现方式:shell 层注入 `emit(line)` 输出回调,TUI 下追加到 `_output_lines`,REPL 下落到 `print`,`_cmd_*` 自身不感知输出目标)
- **模式切换**:chat/rp/agent/exit 沿用现有 `_mode_switch_request` 机制,切换时清空输出区
- **界面切换(`reload --tui/--cli`)**:在 `run_shell` 外层加一层**界面分发循环**:

  ```
  while True:
      ui = "tui" if _ui_mode == "tui" else "cli"
      跑 TUI Application 或旧 REPL
      if 内部请求切换(_ui_switch_request): 继续循环(换界面重启)
      else: break  # 真正退出
  ```

  - `reload --tui` / `reload --cli`:设置 `_ui_switch_request`,让当前界面会话干净退出(释放 alt screen buffer),外层循环以新界面重启
  - 默认 `_ui_mode = "tui"`;`reload --tui` 已处于 TUI 时提示"已是 TUI 界面",不重复重启
- **兼容**:旧的 `reload`(无参数)行为不变 = 热重载配置;加 `--tui`/`--cli` 参数后才切换界面

## 错误处理

- 输出区渲染异常 → 捕获并回退逐行 `print`,进程不崩
- 切换界面时当前会话干净退出(释放 alt screen buffer),再以新界面重启
- `_output_lines` 超上限时丢弃最旧行,保持 5000 行内

## 测试

- `parse_line` 不变,现有测试全绿
- 新增 `_ui_mode`/`_ui_switch_request` 分发逻辑单测:`reload --tui`/`--cli` 切换与幂等(已处于目标界面时提示不重启)
- `reload` 无参数行为不变(热重载配置)单测
- TUI 渲染层(Application 布局/滚动)不依赖 pytest 覆盖,靠启动冒烟人工验证;滚动逻辑(切片/offset 计算)抽纯函数可单测

## 范围外(YAGNI)

- 不做多面板/标签页/会话列表侧栏(未来 chat 列表可加,本次不做)
- 不做鼠标点击交互(仅滚轮滚动)
- 不引入新第三方依赖(继续用 prompt_toolkit)
- 不删旧 REPL 代码(保留为 `--cli` 形态,供切换与回退)
