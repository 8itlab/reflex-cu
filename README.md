# reflex-cu

> **reflex-cu** is an open-source **computer use** MCP server for Claude Code, Codex and other AI agents. It controls macOS and Windows desktops, including a remote Windows machine over SSH, by reading the accessibility / UI Automation tree instead of taking a screenshot at every step, and uses **Jev** (TypeSafe's System One decision model; a TypeSafe, OpenRouter or Command Code key works) as a fast judge. → [English README](README.en.md)

给编码代理（Claude Code、Codex 等）用的桌面操作（computer use）MCP 服务：让 AI 自己操作 Mac 和 Windows 的桌面，也能通过 SSH 操作另一台 Windows。

名字里的 reflex 是"反射"：除了常规的截图、点击、打字，它把"点哪个""成功了没""加载完没"这类不需要思考的高频小判断，交给一个反射式的快速判断模型去做，代理不用每一步都看截图。目前接的判断模型是 [Jev](https://typesafe.ai)（TypeSafe 的 System One 模型，一次约 0.3 秒）。

[English](README.en.md)

## 三种用法

| 用法 | 被操作的机器 | 怎么连 |
|---|---|---|
| 本机 Mac | 运行代理的这台 Mac | MCP 服务进程内直接调用系统接口 |
| 本机 Windows | 运行代理的这台 Windows | 同上 |
| 远程 | 另一台 Windows | 那台机器的桌面会话里跑一个只监听本机的服务，MCP 服务通过 SSH 隧道访问 |

三种用法的工具、参数、坐标约定完全相同。

## 工具

| 工具 | 作用 |
|---|---|
| `status` | 分辨率、前台窗口、用户多久没动鼠标键盘 |
| `screenshot` | 截图，可截窗口或局部 |
| `windows` / `focus` | 列出窗口、切到前台 |
| `observe` | 不截图，直接读出窗口里的界面元素和它们的坐标；打开着的菜单也会列出 |
| `click` / `move` / `drag` / `scroll` | 鼠标，可以用坐标，也可以用 `observe` 返回的元素编号 |
| `key` / `type` | 按键和组合键；输入文字（含中文），可走剪贴板 |
| `find` | **Jev**：一句话描述要操作的元素，返回最匹配的那个和置信度，可以直接点 |
| `check` | **Jev**：对当前屏幕问一个是非题 |
| `wait` | **Jev**：轮询直到是非题成立或超时 |
| `steps` | 一次执行一串操作，Jev 没把握或某步失败就停下 |

带 **Jev** 标记的三个工具需要你自备 Jev 密钥（见下文）；没有密钥时它们不可用，其余工具照常工作。

### 界面是怎么读出来的

- Windows 用 UI Automation，Mac 用辅助功能树：能拿到控件的名称、类型、位置和是否禁用，通常 0.1–0.5 秒。
- 控件的状态会一起读出来：开关是开还是关，下拉框当前选的是什么、有没有展开，哪一项被选中，输入框里填了什么（密码框除外）。几个控件重名时标出各自属于哪个分组。
- Windows 上，滚动区域里还没滚到的项也会列出；用元素编号点击或用 `find` 点击时会先自动滚动到它。
- 读不到东西的窗口（游戏、自绘界面）自动改用文字识别：Windows 用 RapidOCR，Mac 用系统自带的 Vision。
- Jev 只接收文字。纯图标、游戏画面这类没有文字的内容它判断不了，代理仍然要看截图按坐标操作。

### 坐标

所有坐标都以不带 `zoom` 的截图为准：主显示器等比缩放到最宽 1600（环境变量 `CU_VIEW_W` 可改）。截图上看到的位置就是要点的位置。

## 安装

想让 AI 替你装：把 [INSTALL_FOR_AI.md](INSTALL_FOR_AI.md) 的链接发给你的编码代理，让它照着做。下面是手动安装的步骤。

需要 Python 3.10 以上。

### Jev 密钥（需自备）

本项目不附带、也不代理任何 Jev 额度。`find`、`check`、`wait` 三个工具要用你自己的密钥，费用由你自己的账户承担。不配置密钥也能用，只是这三个工具会报错，其余工具不受影响。

密钥有三种来源，任选其一：

| 来源 | 环境变量 | 或者写进文件 |
|---|---|---|
| [TypeSafe](https://typesafe.ai) 官方 | `TYPESAFE_API_KEY` | `~/.reflexcu/typesafe_key` |
| [OpenRouter](https://openrouter.ai/typesafe/jev-1.13)（不需要 TypeSafe 账号） | `OPENROUTER_API_KEY` | `~/.reflexcu/openrouter_key` |
| [Command Code](https://commandcode.ai) 的 Provider API | `COMMANDCODE_API_KEY` | `~/.reflexcu/commandcode_key` |

密钥放在**被操作的那台机器**上，文件里只写密钥本身（Windows 上 `~` 是 `%USERPROFILE%`）。配了不止一种时按表里的顺序取第一个；要指定就把 `CU_JEV_PROVIDER`（或文件 `~/.reflexcu/jev_provider`）设成 `typesafe`、`openrouter` 或 `commandcode`。`status` 的 `jev_provider` 会显示当前用的是哪一个。

别的兼容同一协议（System One）的网关也能接：用 `CU_JEV_URL` 和 `CU_JEV_MODEL`（或文件 `~/.reflexcu/jev_url`、`~/.reflexcu/jev_model`）覆盖地址和模型名，密钥仍按上面的方式放。

如果所在网络访问不了 TypeSafe 的接口（返回 HTTP 451），可以换一种来源（比如 OpenRouter），或者配一个代理：环境变量 `CU_PROXY`，或文件 `~/.reflexcu/proxy`，内容形如 `http://127.0.0.1:7890`。Windows 上由计划任务启动的远程服务读不到登录之后才设置的环境变量，这种情况用文件。

### 本机 Mac

```
git clone https://github.com/8itlab/reflex-cu && cd reflex-cu
python3 -m venv ~/.reflexcu/venv
~/.reflexcu/venv/bin/pip install -r requirements-macos.txt
claude mcp add reflexcu -s user -- ~/.reflexcu/venv/bin/python "$PWD/reflexcu/server.py"
```

启动代理的那个应用（终端、IDE）需要"辅助功能"和"屏幕录制"两项权限，`status` 会报告它们是否到位。

### 本机 Windows

```
git clone https://github.com/8itlab/reflex-cu
cd reflex-cu
python -m venv venv
venv\Scripts\pip install -r requirements-windows.txt
claude mcp add reflexcu -s user -- "%CD%\venv\Scripts\python.exe" "%CD%\reflexcu\server.py"
```

要操作以管理员身份运行的程序，代理本身也得以管理员身份运行，否则输入会被系统拦掉。

### 远程 Windows

在被操作的机器上（需要已经能从你的机器 SSH 过去）：

```
git clone https://github.com/8itlab/reflex-cu C:\reflexcu
powershell -ExecutionPolicy Bypass -File C:\reflexcu\scripts\install-windows-daemon.ps1
```

脚本会建虚拟环境、装依赖，并注册一个登录时启动的计划任务。服务必须跑在桌面会话里：从 SSH 直接启动的进程看不到屏幕。

在运行代理的机器上（这一侧只用标准库）：

```
claude mcp add winbox -s user -e CU_SSH=<ssh 别名> -e 'CU_DIR=C:\reflexcu' -- python3 /path/to/reflexcu/reflexcu/server.py
```

要连多台机器，就各注册一个，并用 `CU_LPORT` 给每台分一个不同的本地端口。

## 在 Codex（ChatGPT 桌面应用）里用

它是标准的 stdio MCP 服务，Codex 同样能用。把上面 `claude mcp add` 换成 `codex mcp add`，环境变量用 `--env`：

```
codex mcp add reflexcu -- ~/.reflexcu/venv/bin/python /path/to/reflex-cu/reflexcu/server.py
codex mcp add winbox --env CU_SSH=<ssh 别名> --env 'CU_DIR=C:\reflexcu' -- python3 /path/to/reflex-cu/reflexcu/server.py
```

只读工具（`status`、`screenshot`、`windows`、`observe`、`check`、`wait`）带有只读标注，`codex exec` 这类非交互运行可以直接调用；会动鼠标键盘的工具需要你在交互界面里批准。在 Mac 上，系统权限是按启动服务的应用给的：从 ChatGPT 应用里用，就要给 ChatGPT 开"辅助功能"和"屏幕录制"。

## 配置

| 环境变量 | 用在哪 | 含义 |
|---|---|---|
| `CU_SSH` | MCP 服务 | 不设或 `local` 是本机；否则是远程机器的 SSH 别名 |
| `CU_DIR` | MCP 服务 | 远程机器上的安装目录，用来读 `token.txt`（默认 `C:\reflexcu`） |
| `CU_TOKEN` | MCP 服务 | 直接给出令牌，不通过 SSH 读取 |
| `CU_LPORT` / `CU_RPORT` | MCP 服务 | 隧道的本地端口（默认 18765）和远程服务端口（默认 8765） |
| `CU_PORT` | 远程服务 | 监听端口（默认 8765） |
| `CU_VIEW_W` | 后端 | 坐标系宽度（默认 1600） |
| `TYPESAFE_API_KEY` | 后端 | 你自己的 TypeSafe 密钥；也可以写在 `~/.reflexcu/typesafe_key` |
| `OPENROUTER_API_KEY` | 后端 | 通过 OpenRouter 用 Jev 时的密钥；也可以写在 `~/.reflexcu/openrouter_key` |
| `COMMANDCODE_API_KEY` | 后端 | 通过 Command Code 用 Jev 时的密钥；也可以写在 `~/.reflexcu/commandcode_key` |
| `CU_JEV_PROVIDER` | 后端 | `typesafe`、`openrouter` 或 `commandcode`；不设时按这个顺序用第一个配了密钥的。也可以写在 `~/.reflexcu/jev_provider` |
| `CU_JEV_URL` / `CU_JEV_MODEL` | 后端 | 覆盖接口地址和模型名，用来接别的兼容网关；也可以写在 `~/.reflexcu/jev_url`、`~/.reflexcu/jev_model` |
| `CU_PROXY` | 后端 | 访问 Jev 用的代理，例如 `http://127.0.0.1:7890`；也可以写在 `~/.reflexcu/proxy`。系统代理不会被自动使用 |

## 命令行调试

`server.py` 带参数时直接执行一个工具并打印结果：

```
python reflexcu/server.py status
python reflexcu/server.py find '{"goal":"保存按钮"}'
CU_SHOT=shot.jpg python reflexcu/server.py screenshot
```

`tests/local_smoke.py` 通过真实的 MCP 协议做一遍只读检查；`tests/selftest_mac.py` 在一个临时的"文本编辑"文档里测鼠标键盘。

## 安全

这个工具能看到屏幕、能控制鼠标键盘，请按这个分量对待它。

- 远程服务只监听 `127.0.0.1`，每个请求都要带 `token.txt` 里的令牌，对外只走 SSH 隧道。不要把端口暴露到网络上。
- 远程服务以最高权限运行，这样才能操作管理员窗口。能访问那个端口和令牌的人就能控制那台机器。
- `find`、`check`、`wait` 会把屏幕上的文字发给 TypeSafe 的 Jev 接口（用 OpenRouter 或 Command Code 的密钥时经由它们转发）。
- 用 OpenRouter 的密钥时，请求会带上本项目的名称和仓库地址（OpenRouter 的应用归属标头，用于它公开的应用榜单），不含你的任何信息；设 `CU_NO_ATTRIBUTION=1` 可以关掉。屏幕上有敏感内容时不要用这三个工具，或者不配置密钥。
- 输入是发给前台窗口的。先切对窗口再打字，否则按键会进别的程序；有人正在用那台机器时，`status` 的 `idle_seconds` 会很小。
- 带内核反作弊的在线游戏可能把模拟输入当作外挂，请自行判断，不要在这类游戏里使用。

## 已知限制

- 只操作主显示器。
- `key` 发的字符键会经过输入法；输入文字用 `type`。`key` 的长按只是保持按下，不会连发字符。
- Mac 上打开的菜单靠文字识别读取，没有禁用状态；Windows 上经典菜单和归属于该窗口的弹出层走 UI Automation。
- 远程模式目前只有 Windows 的安装脚本。Mac 后端也能跑 `daemon.py`，但没有测过。
- 游戏里的相对移动（转镜头）没有系统测试过。

## 实测数据

都是同一个代理（Claude Opus 5.5）、同一句任务描述，只换工具：一组用 reflex-cu 的全部工具，另一组把同一个服务限制成只有截图、点击、按键（`CU_TOOLS=screenshot`）。对照组是本项目自己的截图模式，不是别家产品。每格只跑了 2 次，数字只能看量级。

| 任务 | reflex-cu 全部工具 | 只用截图和点击 |
|---|---|---|
| Mac，只说一句话："打开 ChatGPT 应用" | 8 / 9 秒，4 次调用 | 18 / 30 秒，7 / 12 次调用 |
| Mac，只说一句话："打开计算器，算出 1234 乘以 56" | 23 / 22 秒，5–6 次调用 | 35 / 38 秒，21 次调用 |
| Mac，只说一句话："打开系统设置，查 macOS 版本号" | 25 / 24 秒，4 次调用 | 31 / 26 秒，11–13 次调用 |
| 远程 Windows，在"设置"里连改五项 | 61 / 88 秒，11–15 次调用，约 $0.27 | 54 / 72 秒，28–38 次调用，$0.40–0.56 |

短任务上更快，调用次数少一半以上；步骤很多的长任务上速度没有优势，但花费更低。

## 常见问题

**reflex-cu 是什么？** 一个标准的 stdio MCP 服务，给 AI 代理提供"看屏幕、动鼠标键盘"的工具，也就是通常说的 computer use。它装在你自己的机器上，由你已经在用的代理（Claude Code、Codex、ChatGPT 桌面应用里的 Codex）来调用。

**和模型自带的 computer use 有什么不同？** 常见做法是每一步截一张图交给大模型看。reflex-cu 优先直接读出界面上的控件（名称、状态、坐标），只有图标、游戏画面这类没有文字的内容才截图；"点哪个""成功了没"这类小判断交给 Jev。它还能通过 SSH 操作另一台 Windows 的真实桌面。

**没有 Jev 密钥能用吗？** 能。截图、读界面、鼠标、键盘都不需要密钥，只有 `find`、`check`、`wait` 三个工具需要。

**Jev 的密钥从哪来？** TypeSafe 官方、OpenRouter、Command Code 三选一，见上文"Jev 密钥"。在访问不了 TypeSafe 的网络里，可以用 OpenRouter 的密钥。

**支持哪些系统和客户端？** 被操作的机器：macOS、Windows；远程模式目前只支持操作 Windows。客户端：在 Claude Code 和 Codex（含 ChatGPT 桌面应用）里实测过，其他支持 stdio MCP 的客户端按同样方式注册。

## 代码结构

```
reflexcu/core.py     与平台无关：合并界面树和文字识别、Jev 判断、各个工具的实现
reflexcu/win.py      Windows 后端
reflexcu/mac.py      Mac 后端
reflexcu/server.py   MCP 服务（stdio）：本机直连，或经 SSH 隧道转发
reflexcu/daemon.py   远程模式下跑在被操作机器上的 HTTP 服务
```

## 许可证

MIT
