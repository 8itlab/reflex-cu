# Installation guide for AI agents

[中文](INSTALL_FOR_AI.md)

This document is written for the coding agent (Claude Code, Codex, ...) that installs reflex-cu on a user's behalf. The user only has to say: "Install this for me, following https://github.com/monstercode2/reflex-cu/blob/main/INSTALL_FOR_AI.en.md."

Your job: ask a few questions, install, verify, and tell the user how to start. Every step comes with a check. Do not move on while a check fails.

## Ask the user first

You cannot find these out yourself. Ask them all at once:

1. **Which machine should be controlled?** The one you are running on (local mode), or another Windows machine (remote mode). For remote mode, ask for the SSH alias and confirm that `ssh <alias> hostname` works.
2. **Which client will use it?** Claude Code, Codex (the ChatGPT desktop app), or both.
3. **Do they have a Jev key?** `find`, `check` and `wait` need a key the user obtains from TypeSafe themselves. Installing without one is fine; the other tools still work.
4. **Is a proxy needed to reach Jev?** If the user's network cannot reach the Jev API, ask for the proxy URL (for example `http://127.0.0.1:7890`). If unsure, skip it; the verification step will tell you.

## Rules you must follow

- **Do not take over the user's mouse and keyboard.** Before any test that sends input, read `idle_seconds` from `status`. A few seconds means the user is working: wait until they stop, or ask.
- **Check the foreground window before typing.** Input goes to the foreground window. Typing into the wrong one puts text into the user's other programs, including other agent sessions.
- **The key stays out of the repo and, where possible, out of the conversation.** Ask the user to write the key into the file themselves (paths below) instead of pasting it into chat, and never put it in a file that could be committed.
- **Leave the global Python environment alone.** Always install into a dedicated virtual environment.
- **Do not change system permissions yourself.** On macOS, the user turns on Accessibility and Screen Recording in System Settings. You only tell them which permission, for which app.
- **Say so before restarting the user's apps.** That includes restarting the ChatGPT app to load a new configuration.
- **Do not reboot the machine.**

## Local Mac

```
git clone https://github.com/monstercode2/reflex-cu ~/reflex-cu
python3 -m venv ~/.reflexcu/venv
~/.reflexcu/venv/bin/pip install -r ~/reflex-cu/requirements-macos.txt
```

Python 3.10 or later is required.

Check:

```
~/.reflexcu/venv/bin/python ~/reflex-cu/reflexcu/server.py status
```

It should print JSON. Look at three fields:

- `accessibility` and `screen_recording` should both be `true`. If one is `false`, ask the user to open System Settings → Privacy & Security and grant that permission to **the app that launches you** (Terminal, an IDE, or the ChatGPT app), then restart that app and check again.
- `jev` is `true` when a key is in place.

The first OCR call takes ten seconds or more while the system initialises; later calls take under a second.

## Local Windows

```
git clone https://github.com/monstercode2/reflex-cu C:\reflexcu
cd C:\reflexcu
python -m venv venv
venv\Scripts\pip install -r requirements-windows.txt
```

Check:

```
C:\reflexcu\venv\Scripts\python C:\reflexcu\reflexcu\server.py status
```

This must run inside the user's desktop session. If you reached the machine over SSH, you will see a virtual 1024×768 screen, which means remote mode is the right choice.

To control programs running as administrator, you must run as administrator too.

## Remote Windows

There are two sides. On the machine to be controlled:

```
ssh <alias> "git clone https://github.com/monstercode2/reflex-cu C:\reflexcu"
ssh <alias> "powershell -ExecutionPolicy Bypass -File C:\reflexcu\scripts\install-windows-daemon.ps1"
```

- If that machine has no git, clone on your side and copy `reflexcu`, `scripts` and `requirements-windows.txt` over with `scp -r`.
- If PyPI is slow or unreachable, pass `-PipIndex <mirror URL>` to the script.
- On success the last line is `reflexcu daemon listening on 127.0.0.1:8765`. If it prints `NOT listening`, the tail of the log follows; act on that.
- The script registers a scheduled task named `reflexcu-daemon` that starts when the user logs on. The daemon has to be started by it: a process run directly over SSH cannot see the real desktop.

The machine you run on needs only the repository and the system Python 3, no dependencies:

```
git clone https://github.com/monstercode2/reflex-cu ~/reflex-cu
CU_SSH=<alias> CU_DIR='C:\reflexcu' python3 ~/reflex-cu/reflexcu/server.py status
```

`host` should be the remote machine's name and `screen` its real resolution.

## Jev key and proxy

Both live on **the machine being controlled**. Prefer the files; environment variables often do not reach a Windows scheduled task.

| What | File | Environment variable |
|---|---|---|
| Key | `~/.reflexcu/typesafe_key` | `TYPESAFE_API_KEY` |
| Proxy (optional) | `~/.reflexcu/proxy` | `CU_PROXY` |

On Windows `~` is `%USERPROFILE%`. The file holds the bare value, without quotes.

Check (read-only, sends no input):

```
python reflexcu/server.py check '{"question":"Is there readable text on the screen?"}'
```

- `"yes": true` means it works.
- `HTTP 451`: the network is refused by the Jev API; configure a proxy.
- `no Jev key`: the key is not where it should be.
- After changing the key or proxy file in remote mode, rerun the install script to restart the daemon.

## Register with the client

Replace the paths with the real install location.

Claude Code:

```
# local
claude mcp add reflexcu -s user -- ~/.reflexcu/venv/bin/python ~/reflex-cu/reflexcu/server.py
# remote
claude mcp add winbox -s user -e CU_SSH=<alias> -e 'CU_DIR=C:\reflexcu' -- python3 ~/reflex-cu/reflexcu/server.py
```

Codex:

```
codex mcp add reflexcu -- ~/.reflexcu/venv/bin/python ~/reflex-cu/reflexcu/server.py
codex mcp add winbox --env CU_SSH=<alias> --env 'CU_DIR=C:\reflexcu' -- python3 ~/reflex-cu/reflexcu/server.py
```

- On local Windows the command is `C:\reflexcu\venv\Scripts\python.exe C:\reflexcu\reflexcu\server.py`.
- For several remote machines, register one server each and give every one its own `CU_LPORT` (default 18765).
- Newly registered tools appear only in a **new session**; the ChatGPT desktop app must be **restarted**.
- Confirm with `claude mcp list` or `codex mcp list`.

## Final verification

Read-only first, input second.

**Read-only**: `python tests/local_smoke.py` (local mode) calls `status`, `windows`, `observe`, `screenshot` and `check` through the real MCP protocol. Every result should have `error: false`.

**Input** (first confirm the user is not using that machine):

- Mac: create an empty scratch `.txt`, open it in TextEdit, then run `python tests/selftest_mac.py <that file>`. The script checks the foreground app before every input and aborts if it is wrong. Afterwards quit TextEdit and delete the file.
- Windows: use `steps` for a test that leaves nothing behind: press `win+r`, `wait` for the Run dialog, `type` some text, `check` that it is visible, then `find` the Cancel button and click it. Do not use Notepad; on Windows 11 it keeps unsaved content.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `status` reports a 1024×768 screen, screenshots are black | The process is not in the desktop session. In remote mode the daemon must be started by the scheduled task from the install script |
| `import onnxruntime` fails | The global Python is being used. Use the interpreter in the virtual environment |
| Jev returns `HTTP 451` | The network is refused; add the proxy file |
| An environment variable set for the daemon has no effect | A Windows scheduled task does not see variables set after the last logon; use the files under `~/.reflexcu/` |
| Remote mode returns nonsense or cannot connect | Another program occupies the local tunnel port; pick a different `CU_LPORT` |
| On macOS clicks and typing do nothing | The app that launches you lacks the Accessibility permission |
| On macOS screenshots show only the wallpaper | The app that launches you lacks the Screen Recording permission |
| Codex says `MCP tool call requires approval` | Non-interactive runs allow only the read-only tools; input tools need approval in the interactive UI |
| Codex in the ChatGPT app says the tool does not exist | The app was not restarted after the configuration change, or your instructions forbade it from calling tools its own way |
| `key` produces full-width punctuation | Character keys go through the input method. Always use `type` for text |

## What to tell the user when you are done

- Which mode was installed, what the registered server is called, and that a new session or an app restart is needed before the tools show up.
- Whether Jev works; if not, which three tools are unavailable.
- That this tool can see the screen and control the mouse and keyboard, and that `find`, `check` and `wait` send on-screen text to TypeSafe.
- Any step you could not verify, stated as it is.

## Using it well afterwards

- Call `status` at the start of every task.
- Prefer `observe`, `find`, `check` and `wait` over screenshots; look at a screenshot and click by coordinates only for things without text, such as icons and game scenes.
- For a multi-step path you already know, use a single `steps` call; it stops by itself where it is unsure. Put the window focus and the typing that follows into the same `steps` call so that no other window can take focus in between.
- When Jev reports low confidence, do not force the click; fall back to a screenshot.
- Coordinates always refer to a screenshot taken without `zoom`.
