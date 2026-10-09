#!/usr/bin/env python3
"""MCP (stdio) server for reflexcu.

Two modes, chosen by CU_SSH:
  unset or "local"   drive this machine in-process (needs the backend's Python packages, see README)
  an ssh alias       drive a remote machine: forwards to its daemon (reflexcu/daemon.py) over an SSH
                     tunnel; this mode needs only the standard library

Environment for the remote mode:
  CU_DIR    daemon directory on the remote machine, used to read token.txt   (default C:\\reflexcu)
  CU_TOKEN  the token itself, instead of reading it over ssh
  CU_LPORT  local end of the tunnel   (default 18765; use a different one per machine)
  CU_RPORT  daemon port on the remote (default 8765)
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

SSH = os.environ.get('CU_SSH', 'local')
DIR = os.environ.get('CU_DIR', 'C:\\reflexcu')
LPORT = int(os.environ.get('CU_LPORT', '18765'))
RPORT = int(os.environ.get('CU_RPORT', '8765'))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_token = None
_tunnel = None


def port_open():
    try:
        socket.create_connection(('127.0.0.1', LPORT), timeout=0.5).close()
        return True
    except OSError:
        return False


def ensure_tunnel():
    global _tunnel
    if port_open():
        return
    _tunnel = subprocess.Popen(
        ['ssh', '-N', '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=20', '-o', 'ConnectTimeout=15',
         '-L', f'127.0.0.1:{LPORT}:127.0.0.1:{RPORT}', SSH],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if port_open():
            return
        if _tunnel.poll() is not None:
            break
        time.sleep(0.25)
    raise RuntimeError(f'cannot open the SSH tunnel to {SSH}')


def token():
    global _token
    if _token is None:
        _token = os.environ.get('CU_TOKEN', '').strip() or None
    if _token is None:
        sep = '\\' if '\\' in DIR or ':' in DIR else '/'
        cmd = f'type {DIR}{sep}token.txt' if sep == '\\' else f'cat {DIR}/token.txt'
        out = subprocess.run(['ssh', '-n', '-o', 'ConnectTimeout=15', SSH, cmd], capture_output=True, text=True, timeout=30)
        _token = out.stdout.strip() or None
        if not _token:
            raise RuntimeError(f'cannot read the daemon token on {SSH} ({DIR}): {out.stderr.strip()[:200]}')
    return _token


LOCAL = SSH == 'local'
_core = None


def call_local(op, args):
    global _core
    if _core is None:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from reflexcu import core
        _core = core
    try:
        return _core.run(op, args)
    except Exception as e:
        raise RuntimeError(repr(e)[:400])


def call(op, args, timeout=150):
    if LOCAL:
        return call_local(op, args)
    ensure_tunnel()
    req = urllib.request.Request(f'http://127.0.0.1:{LPORT}/{op}', json.dumps(args).encode(),
                                 {'Content-Type': 'application/json', 'X-Token': token()})
    try:
        return json.load(OPENER.open(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        body = json.loads(e.read() or b'{}')
        raise RuntimeError(body.get('error') or f'HTTP {e.code}')
    except (ConnectionError, urllib.error.URLError) as e:
        raise RuntimeError(f'daemon on {SSH} is not answering ({e}); is reflexcu/daemon.py running in its desktop session?')


XY = {'x': {'type': 'integer'}, 'y': {'type': 'integer'},
      'id': {'type': 'integer', 'description': '上一次 observe/find 返回的元素 id，代替 x/y'}}
WIN = {'window': {'type': 'string', 'description': '窗口标题或应用名的一部分，或 windows 返回的 hwnd；不填就是前台窗口'}}
SRC = {'source': {'type': 'string', 'enum': ['auto', 'tree', 'ocr', 'both'],
                  'description': 'auto：先读界面树，读不到（游戏、自绘界面）再用文字识别'}}

TOOLS = {
    'status': ('机器状态：分辨率、坐标系、前台窗口、用户多久没动鼠标键盘（idle_seconds）。操作前先看 idle_seconds，'
               '用户正在用电脑时不要抢鼠标。', {}, []),
    'screenshot': ('截图。所有坐标都以不带 zoom 的截图为准。region 截局部；zoom=true 按原始分辨率截（只用来看清小字）。',
                   {**WIN, 'region': {'type': 'array', 'items': {'type': 'integer'}, 'description': '[x0,y0,x1,y1]'},
                    'zoom': {'type': 'boolean'}}, []),
    'windows': ('列出可见窗口（标题、进程、位置、是否前台）。', {}, []),
    'focus': ('把窗口切到前台。', WIN, ['window']),
    'observe': ('读出窗口里的界面元素（名称、类型、中心坐标），不经过截图，比看图快得多。打开着的菜单也会列出（popup=true）。filter 按文字过滤。',
                {**WIN, **SRC, 'filter': {'type': 'string'}, 'limit': {'type': 'integer'},
                 'region': {'type': 'array', 'items': {'type': 'integer'}}}, []),
    'click': ('点击坐标或元素 id。', {**XY, 'button': {'type': 'string', 'enum': ['left', 'right', 'middle']},
                              'count': {'type': 'integer', 'description': '2 是双击'},
                              'hold': {'type': 'number', 'description': '按住秒数'}}, []),
    'move': ('移动鼠标。relative=true 时 x/y 是相对位移（用来转游戏镜头）。',
             {**XY, 'relative': {'type': 'boolean'}}, []),
    'drag': ('按住拖动。', {k: {'type': 'integer'} for k in ('x0', 'y0', 'x1', 'y1')} |
             {'seconds': {'type': 'number'}, 'button': {'type': 'string'}}, ['x0', 'y0', 'x1', 'y1']),
    'scroll': ('滚轮。dy>0 向下，单位是格。', {**XY, 'dy': {'type': 'integer'}, 'dx': {'type': 'integer'}}, []),
    'key': ('按键或组合键，如 "ctrl+s"（Mac 上是 "cmd+s"）、"esc"、"w"。hold 是按住秒数（游戏里走路用），times 是重复次数。'
            '字符键会经过输入法，输入文字请用 type。',
            {'keys': {'type': 'string'}, 'hold': {'type': 'number'}, 'times': {'type': 'integer'}}, ['keys']),
    'type': ('输入文字（支持中文）。paste=true 走剪贴板粘贴；enter=true 输完按回车。',
             {'text': {'type': 'string'}, 'paste': {'type': 'boolean'}, 'enter': {'type': 'boolean'}}, ['text']),
    'find': ('【Jev】用一句话描述要操作的东西，Jev 在界面元素里选出对应的那个并给出置信度。click=true 时置信度够就直接点。'
             '约 0.3 秒，不需要截图。只认得有文字或有名称的元素，纯图标和游戏画面要用 screenshot 自己看。',
             {'goal': {'type': 'string', 'description': '例如 "保存按钮"、"把语言改成中文的那个下拉框"'},
              'click': {'type': 'boolean'}, 'min_confidence': {'type': 'number', 'description': '默认 0.75'},
              'button': {'type': 'string'}, 'count': {'type': 'integer'}, **WIN, **SRC}, ['goal']),
    'check': ('【Jev】对当前屏幕上的文字问一个是非题，返回概率。用来确认上一步有没有成功。',
              {'question': {'type': 'string', 'description': '例如 "保存对话框是否已经打开？"'},
               'threshold': {'type': 'number'}, **WIN, **SRC}, ['question']),
    'wait': ('【Jev】反复看屏幕，直到是非题成立或超时（默认 20 秒，最长 120 秒）。等加载、等弹窗时用，不用一遍遍截图。',
             {'question': {'type': 'string'}, 'timeout': {'type': 'number'}, 'interval': {'type': 'number'},
              'threshold': {'type': 'number'}, **WIN, **SRC}, ['question']),
    'steps': ('一次执行一串操作，中途不回来问。每步是 {"op": 上面任一工具名（screenshot 除外）, ...该工具的参数}。'
              'find 没把握、wait/check 不成立或出错时立刻停下并返回已做到哪一步。适合路径明确的多步操作。',
              {'steps': {'type': 'array', 'items': {'type': 'object'}},
               'pause': {'type': 'number', 'description': '步间停顿秒数，默认 0.35'}}, ['steps']),
}


if not LOCAL:
    WHERE = f'远程操作机器 {SSH} 的桌面。'
elif sys.platform == 'darwin':
    WHERE = '操作本机 Mac 的桌面（组合键用 cmd，例如 "cmd+s"）。'
else:
    WHERE = '操作本机 Windows 的桌面。'


def tool_list():
    return [{'name': n, 'description': d, 'inputSchema': {'type': 'object', 'properties': p, 'required': r}}
            for n, (d, p, r) in TOOLS.items()]


def run_tool(name, args):
    if name not in TOOLS:
        raise RuntimeError(f'unknown tool {name}')
    res = call(name, args or {})
    if name == 'screenshot':
        img = res.pop('image')
        return [{'type': 'image', 'data': img, 'mimeType': 'image/jpeg'},
                {'type': 'text', 'text': json.dumps({k: v for k, v in res.items() if v is not None}, ensure_ascii=False)}]
    return [{'type': 'text', 'text': json.dumps(res, ensure_ascii=False)}]


def handle(msg):
    m, i = msg.get('method'), msg.get('id')
    if m == 'initialize':
        return {'jsonrpc': '2.0', 'id': i, 'result': {
            'protocolVersion': msg['params'].get('protocolVersion', '2024-11-05'),
            'capabilities': {'tools': {}}, 'serverInfo': {'name': 'reflexcu', 'version': '0.3.0'},
            'instructions': (WHERE + '优先用 observe/find/check/wait/steps（读界面文字 + Jev 判断，快且省），'
                             '只有图标、游戏画面这类没有文字的内容才用 screenshot 看图再按坐标点。'
                             '每次开始前先调 status：idle_seconds 很小说明用户正在用，先问用户。')}}
    if m == 'tools/list':
        return {'jsonrpc': '2.0', 'id': i, 'result': {'tools': tool_list()}}
    if m == 'tools/call':
        try:
            content = run_tool(msg['params']['name'], msg['params'].get('arguments'))
            return {'jsonrpc': '2.0', 'id': i, 'result': {'content': content}}
        except Exception as e:
            return {'jsonrpc': '2.0', 'id': i, 'result': {'content': [{'type': 'text', 'text': f'错误：{e}'}], 'isError': True}}
    if m == 'ping':
        return {'jsonrpc': '2.0', 'id': i, 'result': {}}
    if i is not None:
        return {'jsonrpc': '2.0', 'id': i, 'error': {'code': -32601, 'message': f'method not found: {m}'}}
    return None


def main():
    # MCP is UTF-8 on the wire; a Windows console code page would mangle non-ASCII text.
    for stream in (sys.stdin, sys.stdout):
        stream.reconfigure(encoding='utf-8')
    try:
        serve()
    finally:
        if _tunnel:
            _tunnel.terminate()


def serve():
    if len(sys.argv) > 1:  # CLI for testing: server.py <op> '<json args>'
        try:
            res = call(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})
        except RuntimeError as e:
            sys.exit(f'error: {e}')
        if 'image' in res:
            import base64
            path = os.environ.get('CU_SHOT', 'shot.jpg')
            open(path, 'wb').write(base64.b64decode(res.pop('image')))
            res['saved'] = path
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        out = handle(json.loads(line))
        if out is not None:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
