# TUI 分区边框 + chat user 消息交替显示 设计

日期:2026-08-09
分支:feat/tui-borders-chat-display

## 背景与问题

### 问题 1:chat 模式下 user 消息丢失(bug)

**现象**:TUI 中 user 消息发出后在输入区短暂停留,AI 回复完成后彻底消失;期望与 CLI 模式一致,user 消息与 AI 消息在输出区交替显示。

**根因**:`core/chat.py` 的 `send_message`(63-90 行)从不 emit user 消息——CLI 模式依赖终端输入回显展示用户输入,而 TUI 的输入框与输出区分离,user 消息从未进入输出区,输出区只有 `assistant>` 回复。

### 问题 2:TUI 分区无视觉分隔

当前 TUI 三区+提示行(HSplit:状态栏/输出区/输入区/提示行)之间没有边缘线,分区边界不清晰。需求:用边缘线对全部四个分区进行包裹。

## 决策(经头脑风暴确认)

| 决策点 | 选择 |
|---|---|
| user 消息格式 | `user> ` 前缀(与 `assistant> ` 对称) |
| 生效范围 | 仅 TUI emit(CLI 保持终端回显,零重复) |
| 边框字符集 | Unicode 圆角线(`╭─╮│╰╯`) |
| 边框范围 | 全部四区:状态栏 / 输出区 / 输入区 / 提示行 |
| user emit 位置 | `send_message` 内、调 API 前,TUI 门控(A1) |
| 边框实现 | 自定义 `framed()` 容器(B2) |

## 设计

### 功能 A:user 消息交替显示

**改动文件**:`src/rp_agent/core/chat.py`

1. 新增常量,与 `ASSISTANT_PREFIX` 并列:

   ```python
   USER_PREFIX = "user> "
   ```

2. `send_message` 中,在 `session_store.save_session(s)` 之后、`with _spinner():` 之前插入:

   ```python
   if output.is_tui():
       emit(f"{rgb(USER_PREFIX, 255, 224, 102)}{text}")
   ```

   - `output.is_tui()` 门控:仅 TUI 显示,CLI 行为不变(避免与终端回显重复)
   - 前缀色 `rgb(255, 224, 102)`(暖黄,与 `chat>` 输入前缀 #FFE066 同色系;assistant 用 #66AAFF,形成用户/助手视觉区分)
   - `output` 模块已在 chat.py 顶层导入(`from rp_agent import output`)

3. **边界行为**:
   - 无连接:`conn is None` 提前 return,不 emit user(消息未发出)✅ 现有逻辑不变
   - API 失败:user 已 emit(消息确实发出),随后 emit 错误提示;user 行保留在输出区,符合"消息已发送但回复失败"的语义

### 功能 B:分区边缘线包裹

**改动文件**:`src/rp_agent/tui.py`、`src/rp_agent/shell/completion.py`

1. `tui.py` 新增 `framed(inner)` 辅助容器:

   ```python
   def framed(inner: AnyContainer) -> AnyContainer:
       """四边框包裹 inner:Unicode 圆角(╭─╮│╰╯),宽度/高度自适应。

       顶/底边框行 = HSplit(左角, char='─' 填充, 右角):角字符固定在两端,
       中间由 Window char 填充横线;左右竖线 = VSplit 中空内容 Window
       char='│' 填充整列(高度由 inner 决定)。
       """
       def _line(left: str, right: str) -> AnyContainer:
           return HSplit(
               [
                   Window(
                       FormattedTextControl(left),
                       width=1,
                       height=1,
                       dont_extend_width=True,
                       style="class:border",
                   ),
                   Window(
                       FormattedTextControl(""),
                       char="─",
                       height=1,
                       style="class:border",
                   ),
                   Window(
                       FormattedTextControl(right),
                       width=1,
                       height=1,
                       dont_extend_width=True,
                       style="class:border",
                   ),
               ]
           )

       return HSplit(
           [
               _line("╭", "╮"),
               VSplit(
                   [
                       Window(
                           FormattedTextControl(""),
                           char="│",
                           width=1,
                           dont_extend_width=True,
                           style="class:border",
                       ),
                       inner,
                       Window(
                           FormattedTextControl(""),
                           char="│",
                           width=1,
                           dont_extend_width=True,
                           style="class:border",
                       ),
                   ]
               ),
               _line("╰", "╯"),
           ]
       )
   ```

   - 顶线:`╭`(左角,宽 1)+ `char="─"` 填充(宽度自适应)+ `╮`(右角,宽 1)→ `╭────╮`
   - 底线:同理 `╰────╯`
   - 左右竖线:内容空、`char="│"`、宽 1 列,VSplit 高度 = 内部内容高度,竖线填充整列

2. `completion.py` 的 `SHELL_STYLE` 增加:

   ```python
   "border": "ansibrightblack",  # 边框线:灰色(prompt_toolkit 无 ansigray,用亮黑)
   ```

3. `tui.py` 布局改为四区全部包裹:

   ```python
   layout = Layout(
       HSplit(
           [
               framed(Window(FormattedTextControl(_status_text), height=1, style="class:status")),
               framed(output_win),
               framed(VSplit([prompt_win, input_win])),   # 输入区:prompt + 输入框
               framed(Window(FormattedTextControl(hint), height=1, style="class:hint")),
           ]
       )
   )
   ```

4. **滚动适配**:`OutputControl.create_content` 收到的 `height` 是框内净高(外层 HSplit 分配高度后扣除顶/底边框行),`_render_height`、`visible_slice`、`clamp_offset`、`top_offset` 逻辑不变,无需改动。

### 测试策略

- `tests/test_chat.py`:
  - TUI 下(`monkeypatch` `output.is_tui` 返回 True)`send_message` emit 包含 `user> <text>`,且顺序在 assistant 之前
  - 非 TUI:`send_message` 不 emit user 前缀行
  - 无连接:不 emit user(现有断言补充)
- `tests/test_tui_scroll.py`:纯函数(`visible_slice`/`clamp_offset`/`top_offset`)不受布局影响,应保持全绿
- 全量 `uv run pytest -q` 保持绿(现有 231 + 新增)
- TUI 视觉验证:真实 Windows 控制台/Windows Terminal 运行 `uv run rp-agent shell`,目测边框与 user/assistant 交替;当前开发环境非 tty,只能验证 import 与回退路径

## 不做的事(YAGNI)

- 不改 CLI 模式显示(user 靠终端回显,维持现状)
- 不做边框标题/可配置边框样式
- 不引入第三方 TUI 库
- 不重构 shell 包架构
