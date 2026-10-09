# reflex-cu

给编码代理（Claude Code、Codex 等）用的桌面操作（computer use）MCP 服务。

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
- 读不到东西的窗口（游戏、自绘界面）自动改用文字识别：Windows 用 RapidOCR，Mac 用系统自带的 Vision。
- Jev 只接收文字。纯图标、游戏画面这类没有文字的内容它判断不了，代理仍然要看截图按坐标操作。

### 坐标

所有坐标都以不带 `zoom` 的截图为准：主显示器等比缩放到最宽 1600（环境变量 `CU_VIEW_W` 可改）。截图上看到的位置就是要点的位置。

## 安装

需要 Python 3.10 以上。

### Jev 密钥（需自备）

本项目不附带、也不代理任何 Jev 额度。`find`、`check`、`wait` 三个工具要用你自己在 TypeSafe 申请的 API 密钥，费用由你的 TypeSafe 账户承担。不配置密钥也能用，只是这三个工具会报错，其余工具不受影响。

密钥放在**被操作的那台机器**上，二选一：

- 环境变量 `TYPESAFE_API_KEY`
- 文件 `~/.reflexcu/typesafe_key`（Windows 上是 `%USERPROFILE%\.reflexcu\typesafe_key`），内容只有密钥本身

如果所在网络访问不了 Jev 接口（返回 HTTP 451），再配一个代理：环境变量 `CU_PROXY`，或文件 `~/.reflexcu/proxy`，内容形如 `http://127.0.0.1:7890`。Windows 上由计划任务启动的远程服务读不到登录之后才设置的环境变量，这种情况用文件。

### 本机 Mac

```
git clone https://github.com/monstercode2/reflex-cu && cd reflex-cu
python3 -m venv ~/.reflexcu/venv
~/.reflexcu/venv/bin/pip install -r requirements-macos.txt
claude mcp add reflexcu -s user -- ~/.reflexcu/venv/bin/python "$PWD/reflexcu/server.py"
```

启动代理的那个应用（终端、IDE）需要"辅助功能"和"屏幕录制"两项权限，`status` 会报告它们是否到位。

### 本机 Windows

```
git clone https://github.com/monstercode2/reflex-cu
cd reflex-cu
python -m venv venv
venv\Scripts\pip install -r requirements-windows.txt
claude mcp add reflexcu -s user -- "%CD%\venv\Scripts\python.exe" "%CD%\reflexcu\server.py"
```

要操作以管理员身份运行的程序，代理本身也得以管理员身份运行，否则输入会被系统拦掉。

### 远程 Windows

在被操作的机器上（需要已经能从你的机器 SSH 过去）：

```
git clone https://github.com/monstercode2/reflex-cu C:\reflexcu
powershell -ExecutionPolicy Bypass -File C:\reflexcu\scripts\install-windows-daemon.ps1
```

脚本会建虚拟环境、装依赖，并注册一个登录时启动的计划任务。服务必须跑在桌面会话里：从 SSH 直接启动的进程看不到屏幕。

在运行代理的机器上（这一侧只用标准库）：

```
claude mcp add winbox -s user -e CU_SSH=<ssh 别名> -e 'CU_DIR=C:\reflexcu' -- python3 /path/to/reflexcu/reflexcu/server.py
```

要连多台机器，就各注册一个，并用 `CU_LPORT` 给每台分一个不同的本地端口。

## 配置

| 环境变量 | 用在哪 | 含义 |
|---|---|---|
| `CU_SSH` | MCP 服务 | 不设或 `local` 是本机；否则是远程机器的 SSH 别名 |
| `CU_DIR` | MCP 服务 | 远程机器上的安装目录，用来读 `token.txt`（默认 `C:\reflexcu`） |
| `CU_TOKEN` | MCP 服务 | 直接给出令牌，不通过 SSH 读取 |
| `CU_LPORT` / `CU_RPORT` | MCP 服务 | 隧道的本地端口（默认 18765）和远程服务端口（默认 8765） |
| `CU_PORT` | 远程服务 | 监听端口（默认 8765） |
| `CU_VIEW_W` | 后端 | 坐标系宽度（默认 1600） |
| `TYPESAFE_API_KEY` | 后端 | 你自己的 Jev 密钥；也可以写在 `~/.reflexcu/typesafe_key` |
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
- `find`、`check`、`wait` 会把屏幕上的文字发给 TypeSafe 的 Jev 接口。屏幕上有敏感内容时不要用这三个工具，或者不配置密钥。
- 输入是发给前台窗口的。先切对窗口再打字，否则按键会进别的程序；有人正在用那台机器时，`status` 的 `idle_seconds` 会很小。
- 带内核反作弊的在线游戏可能把模拟输入当作外挂，请自行判断，不要在这类游戏里使用。

## 已知限制

- 只操作主显示器。
- `key` 发的字符键会经过输入法；输入文字用 `type`。`key` 的长按只是保持按下，不会连发字符。
- Mac 上打开的菜单靠文字识别读取，没有禁用状态；Windows 上经典菜单和归属于该窗口的弹出层走 UI Automation。
- 远程模式目前只有 Windows 的安装脚本。Mac 后端也能跑 `daemon.py`，但没有测过。
- 游戏里的相对移动（转镜头）没有系统测试过。

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
