"""HTTP daemon for remote use: exposes the operations of core.py on 127.0.0.1 only.

Run it inside the interactive desktop session of the machine to be controlled (on Windows:
scripts/install-windows-daemon.ps1 registers a logon task). The MCP server reaches it through an
SSH tunnel and must send the token from token.txt. Single-threaded on purpose: UI Automation is
COM and stays on one thread, and callers are sequential anyway.

usage: python daemon.py            (CU_PORT, default 8765; CU_HOME, default the directory above this package)
"""
import json
import os
import secrets
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
HOME = Path(os.environ.get('CU_HOME') or Path(__file__).resolve().parent.parent)
PORT = int(os.environ.get('CU_PORT', '8765'))


def load_token():
    f = HOME / 'token.txt'
    if not f.exists():
        f.write_text(secrets.token_hex(24), encoding='ascii')
    return f.read_text(encoding='ascii').strip()


class Handler(BaseHTTPRequestHandler):
    token = ''
    core = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        op = self.path.strip('/')
        try:
            if not secrets.compare_digest(self.headers.get('X-Token', ''), self.token):
                return self.reply(403, {'error': 'bad token'})
            n = int(self.headers.get('Content-Length') or 0)
            args = json.loads(self.rfile.read(n) or b'{}')
            if op not in self.core.OPS:
                return self.reply(404, {'error': f'unknown op {op!r}', 'ops': sorted(self.core.OPS)})
            self.reply(200, self.core.run(op, args))
        except Exception as e:
            self.reply(500, {'error': repr(e)[:400], 'trace': traceback.format_exc()[-1200:]})

    def reply(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    if not sys.stdout or os.environ.get('CU_LOG', '1') == '1':  # pythonw has no console
        sys.stderr = sys.stdout = open(HOME / 'daemon.log', 'a', encoding='utf-8', buffering=1)
    from reflexcu import core
    Handler.core, Handler.token = core, load_token()
    print(time.strftime('%F %T'), 'reflexcu daemon', core.VERSION, 'listening on 127.0.0.1:%d' % PORT)
    HTTPServer(('127.0.0.1', PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
