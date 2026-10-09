"""Smoke test of the local mode through the real MCP protocol. Read-only: sends no input.

usage: python tests/local_smoke.py [out.json]     (run it inside the desktop session)
"""
import json
import os
import subprocess
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
calls = [('status', {}), ('windows', {}), ('observe', {'limit': 5}), ('screenshot', {'region': [0, 0, 300, 100]}),
         ('check', {'question': '屏幕上是否有可以阅读的文字？'})]
msgs = [{'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18', 'capabilities': {}}},
        {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}]
msgs += [{'jsonrpc': '2.0', 'id': i + 2, 'method': 'tools/call', 'params': {'name': n, 'arguments': a}} for i, (n, a) in enumerate(calls)]
env = dict(os.environ, CU_SSH='local')
p = subprocess.run([sys.executable, os.path.join(root, 'reflexcu', 'server.py')], input='\n'.join(json.dumps(m) for m in msgs) + '\n',
                   capture_output=True, text=True, encoding='utf-8', env=env, timeout=120)
out = []
for line in p.stdout.splitlines():
    r = json.loads(line).get('result', {})
    if 'tools' in r:
        out.append({'tools': len(r['tools'])})
    elif 'content' in r:
        out.append({'error': r.get('isError', False),
                    'content': [c['text'][:400] if c['type'] == 'text' else f"<image {len(c['data'])} b64 chars>" for c in r['content']]})
    else:
        out.append({'server': r.get('serverInfo'), 'instructions': r.get('instructions', '')[:30]})
text = json.dumps({'results': out, 'stderr': p.stderr[-800:]}, ensure_ascii=False, indent=1)
if len(sys.argv) > 1:
    open(sys.argv[1], 'w', encoding='utf-8').write(text)
else:
    print(text)
