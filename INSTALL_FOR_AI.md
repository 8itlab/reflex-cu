# 给 AI 的安装说明

[English](INSTALL_FOR_AI.en.md)

这份文档是写给替用户安装 reflex-cu 的编码代理（Claude Code、Codex 等）看的。用户只需要对你说一句："按 https://github.com/8itlab/reflex-cu/blob/main/INSTALL_FOR_AI.md 给我装上。"

你要做的是：问清几件事，装好，验证，最后告诉用户怎么开始用。每一步都有检验方法，检验没过就不要往下走。

## 开始前先问用户

下面几项你自己查不出来，一次问完：

1. **要操作哪台机器？** 你正在运行的这台（本机模式），还是另一台 Windows（远程模式）。远程模式要问 SSH 别名，并先确认 `ssh <别名> hostname` 能通。
2. **在哪个客户端里用？** Claude Code、Codex（ChatGPT 桌面应用），或者两个都要。
3. **有没有 Jev 密钥？** `find`、`check`、`wait` 三个工具需要用户自己的密钥：TypeSafe 官方的密钥、OpenRouter 的密钥（不需要 TypeSafe 账号），或者 Command Code 的密钥，有一个就行。没有也能装，其余工具照常可用。
4. **访问 Jev 需不需要代理？** 如果用户所在网络访问不了 Jev 接口，问代理地址（例如 `http://127.0.0.1:7890`）。不确定就先不配，验证那一步会告诉你。

## 必须遵守的规则

- **不要抢用户的鼠标键盘。** 任何会发输入的测试之前，先看 `status` 的 `idle_seconds`；只有几秒说明用户正在用，等他停手或先问他。
- **打字前确认前台窗口。** 输入是发给前台窗口的，打错窗口会把字敲进用户别的程序里（包括别的代理会话）。
- **密钥不进仓库，也尽量不进对话。** 请用户自己把密钥写进文件（路径见下文），不要让他贴在聊天里，更不要写进任何会被提交的文件。
- **不动全局 Python 环境。** 一律装进独立的虚拟环境。
- **不要自己改系统权限。** Mac 上的"辅助功能"和"屏幕录制"由用户本人在系统设置里打开，你只负责告诉他要开哪一项、给哪个应用。
- **重启用户的应用前先说。** 包括重启 ChatGPT 应用来加载新配置。
- **不要重启机器。**

## 本机 Mac

```
git clone https://github.com/8itlab/reflex-cu ~/reflex-cu
python3 -m venv ~/.reflexcu/venv
~/.reflexcu/venv/bin/pip install -r ~/reflex-cu/requirements-macos.txt
```

要求 Python 3.10 以上。

检验：

```
~/.reflexcu/venv/bin/python ~/reflex-cu/reflexcu/server.py status
```

应返回一段 JSON。重点看三项：

- `accessibility` 和 `screen_recording` 都应为 `true`。哪一项是 `false`，就请用户到"系统设置 → 隐私与安全性"里，把对应权限开给**启动你的那个应用**（终端、IDE，或者 ChatGPT 应用），开完后重启那个应用再验。
- `jev` 为 `true` 表示密钥已就位，`jev_provider` 是当前用的来源（`typesafe`、`openrouter` 或 `commandcode`）。

第一次调用文字识别会慢十几秒，是系统的一次性初始化，之后不到一秒。

## 本机 Windows

```
git clone https://github.com/8itlab/reflex-cu C:\reflexcu
cd C:\reflexcu
python -m venv venv
venv\Scripts\pip install -r requirements-windows.txt
```

检验：

```
C:\reflexcu\venv\Scripts\python C:\reflexcu\reflexcu\server.py status
```

必须在用户的桌面会话里运行。如果你是通过 SSH 连到这台机器的，你看到的会是一块 1024×768 的虚拟屏幕，那说明该用远程模式。

要操作以管理员身份运行的程序，你自己也得以管理员身份运行。

## 远程 Windows

分两头装。被操作的机器上：

```
ssh <别名> "git clone https://github.com/8itlab/reflex-cu C:\reflexcu"
ssh <别名> "powershell -ExecutionPolicy Bypass -File C:\reflexcu\scripts\install-windows-daemon.ps1"
```

- 那台机器没有 git，就在你这边克隆后用 `scp -r` 把 `reflexcu`、`scripts`、`requirements-windows.txt` 拷过去。
- 访问 PyPI 慢或不通，给脚本加 `-PipIndex <镜像地址>`。
- 成功时脚本最后一行是 `reflexcu daemon listening on 127.0.0.1:8765`。输出 `NOT listening` 时，后面跟着的是日志尾部，按日志处理。
- 脚本会注册一个名为 `reflexcu-daemon` 的计划任务，用户登录后自动启动。服务必须由它启动：从 SSH 直接运行的进程看不到真实桌面。

你运行的这台机器上只需要仓库代码和系统自带的 Python 3，不用装依赖：

```
git clone https://github.com/8itlab/reflex-cu ~/reflex-cu
CU_SSH=<别名> CU_DIR='C:\reflexcu' python3 ~/reflex-cu/reflexcu/server.py status
```

返回的 `host` 应该是远程机器的名字，`screen` 应该是它真实的分辨率。

## Jev 密钥和代理

都放在**被操作的那台机器**上。优先用文件，环境变量在 Windows 计划任务里经常读不到。

| 内容 | 文件 | 环境变量 |
|---|---|---|
| TypeSafe 的密钥 | `~/.reflexcu/typesafe_key` | `TYPESAFE_API_KEY` |
| 或 OpenRouter 的密钥 | `~/.reflexcu/openrouter_key` | `OPENROUTER_API_KEY` |
| 或 Command Code 的密钥 | `~/.reflexcu/commandcode_key` | `COMMANDCODE_API_KEY` |
| 代理（可选） | `~/.reflexcu/proxy` | `CU_PROXY` |

Windows 上 `~` 是 `%USERPROFILE%`。文件里只写值本身，不要加引号。三种密钥配一种就够；配了不止一种时按表里的顺序取第一个，要指定就在 `~/.reflexcu/jev_provider` 里写 `typesafe`、`openrouter` 或 `commandcode`。

检验（只读，不发任何输入）：

```
python reflexcu/server.py check '{"question":"屏幕上是否有可以阅读的文字？"}'
```

- 返回 `"yes": true` 即正常。
- 报 `HTTP 451`：所在网络被 TypeSafe 的接口拒绝，需要配代理，或者改用别的来源（比如 OpenRouter）的密钥。
- 报 `rejected the Jev key`：密钥不对；报 `no credit left`：那个账户没有余额了。
- 报 `no Jev key`：密钥没放对位置。
- 改了密钥或代理文件后，远程模式要重跑一次安装脚本来重启服务。

## 注册到客户端

把路径换成实际安装位置。

Claude Code：

```
# 本机
claude mcp add reflexcu -s user -- ~/.reflexcu/venv/bin/python ~/reflex-cu/reflexcu/server.py
# 远程
claude mcp add winbox -s user -e CU_SSH=<别名> -e 'CU_DIR=C:\reflexcu' -- python3 ~/reflex-cu/reflexcu/server.py
```

Codex：

```
codex mcp add reflexcu -- ~/.reflexcu/venv/bin/python ~/reflex-cu/reflexcu/server.py
codex mcp add winbox --env CU_SSH=<别名> --env 'CU_DIR=C:\reflexcu' -- python3 ~/reflex-cu/reflexcu/server.py
```

- 本机 Windows 上，命令换成 `C:\reflexcu\venv\Scripts\python.exe C:\reflexcu\reflexcu\server.py`。
- 连多台远程机器时，每台注册一个，并各给一个不同的 `CU_LPORT`（默认 18765）。
- 新注册的工具要**新开会话**才出现；ChatGPT 桌面应用要**重启应用**。
- 用 `claude mcp list` 或 `codex mcp list` 确认状态。

## 最终验证

先做只读的，再做会发输入的。

**只读**：`python tests/local_smoke.py`（本机模式）会通过真实的 MCP 协议依次调用 `status`、`windows`、`observe`、`screenshot`、`check`，每项的 `error` 都应为 `false`。

**输入**（先确认用户没在用那台机器）：

- Mac：建一个空的临时 `.txt`，用"文本编辑"打开，然后 `python tests/selftest_mac.py <那个文件>`。脚本每次输入前都会核对前台应用，不对就中止。测完退出文本编辑并删掉临时文件。
- Windows：用 `steps` 做一轮不留痕迹的测试：按 `win+r`，`wait` 等"运行"对话框出现，`type` 输入一段字，`check` 确认看得到，最后 `find` 找到"取消"并点击。不要用记事本，Windows 11 的记事本会保留未保存的内容。

## 常见问题

| 现象 | 原因和处理 |
|---|---|
| `status` 里屏幕是 1024×768，截图是黑的 | 进程不在桌面会话里。远程模式要用安装脚本注册的计划任务启动服务 |
| `import onnxruntime` 报错 | 用了全局 Python。改用虚拟环境里的解释器 |
| Jev 返回 `HTTP 451` | 网络被拒，配代理文件 |
| 给服务设了环境变量但不生效 | Windows 计划任务读不到登录之后才设的变量，改用 `~/.reflexcu/` 下的文件 |
| 远程模式返回的内容莫名其妙，或提示连不上 | 本地隧道端口被别的程序占了，换一个 `CU_LPORT` |
| Mac 上点击和打字没有任何效果 | 启动你的应用没有"辅助功能"权限 |
| Mac 上截图只有桌面壁纸、看不到窗口 | 启动你的应用没有"屏幕录制"权限 |
| Codex 报 `MCP tool call requires approval` | 非交互运行只放行只读工具；会发输入的工具要在交互界面里批准 |
| ChatGPT 应用里的 Codex 说找不到工具 | 改完配置后应用没重启；或者你的指令禁止了它用自己的方式调用工具 |
| `key` 打出来的符号是全角的 | 字符键会经过输入法。输入文字一律用 `type` |

## 装完后告诉用户什么

- 装的是哪种模式、注册的工具名叫什么、需要新开会话或重启应用才能看到工具。
- Jev 是否可用；不可用时哪三个工具用不了。
- 这个工具能看到屏幕并控制鼠标键盘，`find`、`check`、`wait` 会把屏幕上的文字发给 TypeSafe（用 OpenRouter 或 Command Code 的密钥时经由它们转发）。
- 哪些步骤你没能验证，原样说明。

## 以后你自己怎么用好它

- 每次开始先调 `status`。
- 能用 `observe`、`find`、`check`、`wait` 就不要截图；只有图标、游戏画面这类没有文字的内容才看截图按坐标点。
- 路径明确的多步操作用一次 `steps` 做完，它会在没把握的地方自己停下。切窗口和随后的打字放在同一个 `steps` 里，中间就不会被别的窗口抢走焦点。
- Jev 给出低置信度时不要硬点，换成看截图。
- 坐标一律以不带 `zoom` 的截图为准。
