# reflex-cu

[中文](README.md)

**reflex-cu** is an open-source **computer use** MCP server for coding agents such as Claude Code and Codex. It lets an AI agent operate a macOS or Windows desktop, or a remote Windows machine over SSH, by reading the accessibility / UI Automation tree instead of taking a screenshot at every step.

The "reflex" in the name is the idea: besides the usual screenshots, clicks and typing, the small, frequent decisions that need no deliberation ("which element?", "did that work?", "has it finished loading?") go to a fast, reflex-like judge model, so the agent no longer has to look at a screenshot after every step. The judge currently wired in is [Jev](https://typesafe.ai), TypeSafe's System One model, which answers in about 0.3 seconds.

> **New in 0.4: Jev can look.** Pass `look: true` to `find`, `check` or `wait` and Jev looks at the screenshot itself: it finds bare icons and characters or objects in game scenes, and answers "is there a … on screen?". The screenshot goes to Jev only, never into the agent's context. Experimental, TypeSafe keys only; see [Looking at pixels](#looking-at-pixels-look-experimental).

Tool descriptions and element labels are currently in Chinese.

## Three ways to use it

| Mode | Machine being controlled | How it connects |
|---|---|---|
| Local Mac | The Mac the agent runs on | The MCP server calls system APIs in-process |
| Local Windows | The Windows machine the agent runs on | Same |
| Remote | Another Windows machine | A daemon in that machine's desktop session listens on localhost only; the MCP server reaches it through an SSH tunnel |

Tools, parameters and the coordinate convention are identical in all three.

## Tools

| Tool | What it does |
|---|---|
| `status` | Resolution, foreground window, seconds since the user last touched mouse or keyboard |
| `screenshot` | Screenshot of the screen, a window or a region |
| `windows` / `focus` | List windows, bring one to the front |
| `observe` | Read a window's UI elements and their coordinates without a screenshot; open menus are included |
| `click` / `move` / `drag` / `scroll` | Mouse, by coordinates or by an element id from `observe` |
| `key` / `type` | Keys and shortcuts; text input (any script), optionally through the clipboard |
| `find` | **Jev**: describe the element in a sentence, get the best match with a confidence, optionally click it; with `look`, find it in the screenshot (icons, game scenes) |
| `check` | **Jev**: ask a yes/no question about the current screen; with `look`, Jev sees the screenshot too |
| `wait` | **Jev**: poll until a yes/no question holds or a timeout expires |
| `steps` | Run a sequence of operations in one call; stops when Jev is unsure or a step fails |

The three tools marked **Jev** need your own Jev API key (see below). Without a key they fail; everything else works.

### How the UI is read

- Windows uses UI Automation and macOS the Accessibility tree: names, roles, positions and disabled state, usually in 0.1 to 0.5 seconds.
- Control state is read too: whether a switch is on, what a dropdown is set to and whether it is open, which item is selected, what a text field contains (password fields excluded). Controls that share a name are labelled with the group they belong to.
- On Windows, items in a scrollable area that have not been scrolled to are listed as well; clicking one by element id, or through `find`, scrolls it into view first.
- Windows that expose nothing (games, custom-drawn UIs) fall back to OCR automatically: RapidOCR on Windows, the built-in Vision framework on macOS.
- By default Jev receives text only. For icons and game scenes with no text, pass `look: true` to `find`, `check` or `wait` and Jev looks at the screenshot itself (next section).

### Looking at pixels (`look`, experimental)

Jev reads images since 1.13, and 1.14 adds a question type that boxes one thing in a picture. With `look: true`:

- `find` boxes the target roughly on the whole window, then again on an enlarged crop around it, and returns the centre. `confidence` is Jev's probability, after zooming in, that the target is really there; it clicks only when that is high enough.
- `check` and `wait` give Jev the window's screenshot along with the text read from it.
- The screenshot goes to Jev only, never into the agent's context, so the agent pays nothing to look.

Measured on this machine, without clicking, against known positions: on a game screenshot, 8 of 8 targets (characters, a lantern, an archery target, banners) were hit after the two passes; on a browser toolbar, 6 of 8 small buttons were hit, one was refused for low confidence, and one landed on a tab's title instead of its close button. A `find` takes about 1–3 s, a `check` about 0.6 s.

Asked "is there a character on screen?" in a full-screen game on a 4K display (Black Myth: Wukong), Jev answered 0.06 (wrong) from text alone, which was one recognised element, and 0.98 with `look`.

Limits:

- TypeSafe labels this experimental ("Dreamer-ready"); format and accuracy may change. Tightly packed small icons can still be missed; confirm important clicks with `check`, or look at a screenshot yourself.
- Only a TypeSafe key works for now. OpenRouter already serves Jev 1.14 but drops the image and lets the model answer blind, so through OpenRouter or Command Code `look` fails with an error instead of guessing. `jev_images` in `status` says whether the current source can see images.
- Boxing needs Jev 1.14, so `look` uses `jev-preview` by default; once TypeSafe moves `jev-latest` to 1.14, `CU_JEV_VISION_MODEL` can point back to it.

### Coordinates

All coordinates refer to a screenshot taken without `zoom`: the main display scaled down to at most 1600 wide (`CU_VIEW_W` changes that). Where something appears in the screenshot is where to click.

## Installation

To have an AI install it for you, give your coding agent the link to [INSTALL_FOR_AI.en.md](INSTALL_FOR_AI.en.md) and ask it to follow that. Manual steps are below.

Python 3.10 or later.

### Jev API key (bring your own)

This project does not ship with, or proxy, any Jev quota. `find`, `check` and `wait` use your own key, billed to your own account. Running without a key is fine: those three tools return an error and the rest are unaffected.

The key can come from any one of three places:

| Source | Environment variable | Or a file | Looking (`look`) |
|---|---|---|---|
| [TypeSafe](https://typesafe.ai) directly | `TYPESAFE_API_KEY` | `~/.reflexcu/typesafe_key` | Yes |
| [OpenRouter](https://openrouter.ai/typesafe/jev-1.13) (no TypeSafe account needed) | `OPENROUTER_API_KEY` | `~/.reflexcu/openrouter_key` | Not yet (images are dropped) |
| [Command Code](https://commandcode.ai)'s Provider API | `COMMANDCODE_API_KEY` | `~/.reflexcu/commandcode_key` | Unverified; images not sent by default |

The key lives on **the machine being controlled**; the file contains only the key (`~` is `%USERPROFILE%` on Windows). With more than one configured, the first in the table's order is used; to choose, set `CU_JEV_PROVIDER` (or the file `~/.reflexcu/jev_provider`) to `typesafe`, `openrouter` or `commandcode`. `jev_provider` in `status` shows which one is active.

Any other gateway that speaks the same protocol (System One) works too: override the address and model name with `CU_JEV_URL` and `CU_JEV_MODEL` (or the files `~/.reflexcu/jev_url` and `~/.reflexcu/jev_model`); the key is still supplied as above.

If your network cannot reach TypeSafe's API (HTTP 451), switch to another source (OpenRouter, for example), or configure a proxy: the environment variable `CU_PROXY`, or the file `~/.reflexcu/proxy`, with a value like `http://127.0.0.1:7890`. A remote daemon started by the Windows task scheduler does not see environment variables set after the last logon; use the file in that case.

### Local Mac

```
git clone https://github.com/8itlab/reflex-cu && cd reflex-cu
python3 -m venv ~/.reflexcu/venv
~/.reflexcu/venv/bin/pip install -r requirements-macos.txt
claude mcp add reflexcu -s user -- ~/.reflexcu/venv/bin/python "$PWD/reflexcu/server.py"
```

The app that launches the agent (Terminal, an IDE) needs the Accessibility and Screen Recording permissions. `status` reports whether both are in place.

### Local Windows

```
git clone https://github.com/8itlab/reflex-cu
cd reflex-cu
python -m venv venv
venv\Scripts\pip install -r requirements-windows.txt
claude mcp add reflexcu -s user -- "%CD%\venv\Scripts\python.exe" "%CD%\reflexcu\server.py"
```

To control programs running as administrator, the agent itself must run as administrator; otherwise Windows blocks the input.

### Remote Windows

On the machine to be controlled (you must already be able to SSH into it):

```
git clone https://github.com/8itlab/reflex-cu C:\reflexcu
powershell -ExecutionPolicy Bypass -File C:\reflexcu\scripts\install-windows-daemon.ps1
```

The script creates a virtual environment, installs the dependencies and registers a scheduled task that starts at logon. The daemon has to live in the desktop session: a process started directly over SSH cannot see the screen.

On the machine the agent runs on (this side needs only the standard library):

```
claude mcp add winbox -s user -e CU_SSH=<ssh alias> -e 'CU_DIR=C:\reflexcu' -- python3 /path/to/reflexcu/reflexcu/server.py
```

For several machines, register one server per machine and give each its own local port with `CU_LPORT`.

## Using it from Codex (the ChatGPT desktop app)

It is a standard stdio MCP server, so Codex can use it too. Replace `claude mcp add` above with `codex mcp add`, and pass environment variables with `--env`:

```
codex mcp add reflexcu -- ~/.reflexcu/venv/bin/python /path/to/reflex-cu/reflexcu/server.py
codex mcp add winbox --env CU_SSH=<ssh alias> --env 'CU_DIR=C:\reflexcu' -- python3 /path/to/reflex-cu/reflexcu/server.py
```

The read-only tools (`status`, `screenshot`, `windows`, `observe`, `check`, `wait`) carry a read-only annotation, so non-interactive runs such as `codex exec` can call them directly; tools that move the mouse or press keys need your approval in the interactive UI. On macOS, permissions belong to the app that launches the server: when used from the ChatGPT app, grant Accessibility and Screen Recording to ChatGPT.

## Configuration

| Variable | Read by | Meaning |
|---|---|---|
| `CU_SSH` | MCP server | Unset or `local` means this machine; otherwise the SSH alias of the remote machine |
| `CU_DIR` | MCP server | Install directory on the remote machine, used to read `token.txt` (default `C:\reflexcu`) |
| `CU_TOKEN` | MCP server | The token itself, instead of reading it over SSH |
| `CU_LPORT` / `CU_RPORT` | MCP server | Local end of the tunnel (default 18765) and the daemon port on the remote (default 8765) |
| `CU_PORT` | Daemon | Listening port (default 8765) |
| `CU_VIEW_W` | Backend | Width of the coordinate space (default 1600) |
| `TYPESAFE_API_KEY` | Backend | Your own TypeSafe key; may also be stored in `~/.reflexcu/typesafe_key` |
| `OPENROUTER_API_KEY` | Backend | The key for reaching Jev through OpenRouter; may also be stored in `~/.reflexcu/openrouter_key` |
| `COMMANDCODE_API_KEY` | Backend | The key for reaching Jev through Command Code; may also be stored in `~/.reflexcu/commandcode_key` |
| `CU_JEV_PROVIDER` | Backend | `typesafe`, `openrouter` or `commandcode`; unset means the first one, in that order, that has a key. May also be stored in `~/.reflexcu/jev_provider` |
| `CU_JEV_URL` / `CU_JEV_MODEL` | Backend | Override the endpoint and the model name, for other compatible gateways; may also be stored in `~/.reflexcu/jev_url` and `~/.reflexcu/jev_model` |
| `CU_JEV_VISION_MODEL` | Backend | Model used for `look` (default `jev-preview`); may also be stored in `~/.reflexcu/jev_vision_model` |
| `CU_JEV_IMAGES` | Backend | `1` sends images even through a source not confirmed to support them (for compatible gateways that do) |
| `CU_PROXY` | Backend | Proxy for reaching Jev, e.g. `http://127.0.0.1:7890`; may also be stored in `~/.reflexcu/proxy`. System proxies are not picked up automatically |

## Command-line debugging

With arguments, `server.py` runs one tool and prints the result:

```
python reflexcu/server.py status
python reflexcu/server.py find '{"goal":"the Save button"}'
python reflexcu/server.py find '{"goal":"the gear icon at the top right","look":true}'
python reflexcu/server.py check '{"question":"Is a dialog open?","look":true}'
CU_SHOT=shot.jpg python reflexcu/server.py screenshot
```

`tests/local_smoke.py` does a read-only pass through the real MCP protocol. `tests/selftest_mac.py` exercises mouse and keyboard in a scratch TextEdit document.

## Security

This tool can see the screen and control the mouse and keyboard. Treat it accordingly.

- The remote daemon listens on `127.0.0.1` only, every request must carry the token from `token.txt`, and the only way in from outside is the SSH tunnel. Do not expose the port to a network.
- The remote daemon runs with the highest privileges so that it can operate administrator windows. Anyone who can reach that port with the token controls the machine.
- `find`, `check` and `wait` send the text on screen to TypeSafe's Jev API (through OpenRouter or Command Code when one of their keys is used). With `look`, they also send a screenshot of that window.
- With an OpenRouter key, requests carry this project's name and repository URL (OpenRouter's app attribution headers, used for its public app rankings) and nothing about you. Set `CU_NO_ATTRIBUTION=1` to turn that off. Do not use them while sensitive content is on screen, or leave the key unconfigured.
- Input goes to the foreground window. Focus the right window before typing, or the keystrokes land in another program. When someone is using the machine, `idle_seconds` in `status` is small.
- Online games with kernel anti-cheat may treat synthetic input as cheating. Use your own judgment and do not use this tool in such games.

## Known limitations

- Only the main display is controlled.
- `look` is experimental: tightly packed small icons can be missed, and Jev is occasionally confident about a wrong spot; confirm important clicks. Very large windows are slower: on a full-screen 4K game one judgment with `look` takes about 8 s, about 4 s of it text recognition; when only the picture matters, `source: "tree"` skips recognition and it takes about 4 s.
- Character keys sent with `key` go through the input method; use `type` for text. Holding a key with `key` keeps it down but does not auto-repeat characters.
- On macOS, open menus are read by OCR and carry no disabled state. On Windows, classic menus and popups owned by the window are read through UI Automation.
- Remote mode has an install script for Windows only. The macOS backend can run `daemon.py` too, but that is untested.
- Relative mouse motion in games (turning the camera) has not been tested systematically.

## Measurements

Same agent (Claude Opus 5.5) and same task sentence each time; only the tools differ. One arm has all of reflex-cu's tools, the other is the same server restricted to screenshots, clicks and keys (`CU_TOOLS=screenshot`). The baseline is this project's own screenshot mode, not another product. Two runs per cell: read these as orders of magnitude.

| Task | All reflex-cu tools | Screenshots and clicks only |
|---|---|---|
| macOS, one sentence: "open the ChatGPT app" | 8 / 9 s, 4 calls | 18 / 30 s, 7 / 12 calls |
| macOS, one sentence: "open Calculator and work out 1234 times 56" | 23 / 22 s, 5–6 calls | 35 / 38 s, 21 calls |
| macOS, one sentence: "open System Settings and tell me the macOS version" | 25 / 24 s, 4 calls | 31 / 26 s, 11–13 calls |
| Remote Windows, five changes in a row in Settings | 61 / 88 s, 11–15 calls, about $0.27 | 54 / 72 s, 28–38 calls, $0.40–0.56 |

Faster on short tasks, with less than half the tool calls. On a long task with many steps there is no speed advantage, but the cost is lower.

## FAQ

**What is reflex-cu?** A standard stdio MCP server that gives an AI agent the tools to see the screen and use the mouse and keyboard, what is usually called computer use. It runs on your own machine and is called by the agent you already use (Claude Code, Codex, Codex inside the ChatGPT desktop app).

**How is it different from a model's built-in computer use?** The usual loop sends a screenshot to a large model at every step. reflex-cu reads the controls on screen directly (names, state, coordinates) and looks at pixels only for content without text, such as icons or game scenes, and even then Jev can do the looking (`look`) so the screenshot never enters the large model's context. Small decisions like "which element?" and "did that work?" go to Jev. It can also operate the real desktop of another Windows machine over SSH.

**Does it work without a Jev key?** Yes. Screenshots, reading the UI, mouse and keyboard need no key. Only `find`, `check` and `wait` do.

**Can Jev see images?** Yes, since Jev 1.13, still as an experimental feature. reflex-cu 0.4 uses it to find icons and things in game scenes (`look`), with a TypeSafe key only; see "Looking at pixels" above.

**Where does a Jev key come from?** TypeSafe directly, OpenRouter, or Command Code: see "Jev API key" above. On a network that cannot reach TypeSafe, an OpenRouter key is an alternative.

**Which systems and clients are supported?** Controlled machine: macOS or Windows; remote mode currently controls Windows only. Clients: tested in Claude Code and Codex (including the ChatGPT desktop app); other stdio MCP clients register it the same way.

## Layout

```
reflexcu/core.py     platform-neutral: merges the UI tree with OCR, Jev judgments, the tool implementations
reflexcu/win.py      Windows backend
reflexcu/mac.py      macOS backend
reflexcu/server.py   MCP server (stdio): local in-process, or forwarding through an SSH tunnel
reflexcu/daemon.py   HTTP daemon that runs on the controlled machine in remote mode
```

## License

MIT
