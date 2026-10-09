"""Input self-test for the macOS backend on a scratch TextEdit document.

usage: open -a TextEdit <empty .txt> && python tests/selftest_mac.py <same .txt> [shot.jpg]
Aborts as soon as TextEdit is not the foreground app, so keystrokes never land elsewhere.
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reflexcu import core, mac

O = core.OPS
NAME = os.path.basename(sys.argv[1]).rsplit('.', 1)[0]


def front():
    return mac.find_window(None)


def guard():
    f = front()
    if f['exe'] not in ('文本编辑', 'TextEdit'):
        raise SystemExit(f'ABORT: foreground is {f["exe"]}, not TextEdit')
    return f


def doc_text():
    app, win = mac.ax_window(guard())
    q = [win]
    while q:
        el = q.pop(0)
        if mac.ax_get(el, 'AXRole') == 'AXTextArea':
            return mac.ax_get(el, 'AXValue')
        q += list(mac.ax_get(el, 'AXChildren') or [])


def ocr_lines():
    return [e['text'] for e in core.observe(NAME, 'ocr')[1] if e['text'].lower().startswith('line')]


print('idle before', mac.idle_seconds(), '| front:', front()['exe'])
r = O['wait']({'question': f'是否有一个名为 {NAME} 的文本编辑窗口？', 'window': NAME, 'timeout': 8})
print('1 wait window', r['polls'], 'polls')
O['focus']({'window': NAME})
w = guard()
print('2 focus ->', w['title'], w['rect'])
cx, cy = (w['rect'][0] + w['rect'][2]) // 2, (w['rect'][1] + w['rect'][3]) // 2
O['click']({'x': cx, 'y': cy})
guard()
O['type']({'text': 'Hello maccu 123\n中文输入测试，标点！\n'})
guard()
for i in (1, 2, 3):
    O['type']({'text': f'P{i} 粘贴 word{i} tail\n', 'paste': True})
time.sleep(0.3)
print('3 type+paste ->', json.dumps(doc_text(), ensure_ascii=False))
O['key']({'keys': 'shift+1', 'times': 3})
O['key']({'keys': 'enter'})
time.sleep(0.2)
print('4 key times ->', json.dumps(doc_text().splitlines()[-1:], ensure_ascii=False))

els = core.observe(NAME, 'ocr')[1]
e = next(e for e in els if 'word2' in e['text'])
r = e['rect']
frac = (e['text'].index('word2') + 2.5) / len(e['text'])
guard()
O['click']({'x': int(r[0] + (r[2] - r[0]) * frac), 'y': (r[1] + r[3]) // 2, 'count': 2})
time.sleep(0.2)
O['type']({'text': '双击替换'})
time.sleep(0.2)
print('5 double click ->', [l for l in doc_text().splitlines() if l.startswith('P2')])

guard()
O['click']({'x': cx, 'y': cy, 'button': 'right'})
time.sleep(0.5)
r = O['check']({'question': '是否弹出了带有“粘贴”“拷贝”或“剪切”等项的右键菜单？', 'window': NAME})
print('6 right click menu', r['yes'], r['probability'])
O['key']({'keys': 'esc'})
time.sleep(0.3)

guard()
O['key']({'keys': 'cmd+a'})
O['type']({'text': '\n'.join(f'line {i}' for i in range(1, 121)) + '\n', 'paste': True})
time.sleep(0.5)
a = ocr_lines()
O['scroll']({'x': cx, 'y': cy, 'dy': -30})
time.sleep(0.6)
b = ocr_lines()
print('7 scroll: before', a[:1], a[-1:], '| after up 30', b[:1], b[-1:])

w = guard()
x0, y0 = (w['rect'][0] + w['rect'][2]) // 2, w['rect'][1] + 12
O['drag']({'x0': x0, 'y0': y0, 'x1': x0 + 100, 'y1': y0 + 50, 'seconds': 0.5})
time.sleep(0.4)
print('8 drag window', w['rect'], '->', guard()['rect'])

r = O['find']({'goal': '菜单栏里的“格式”菜单', 'click': True, 'window': NAME})
print('9 find+click', r['match'] and r['match']['label'], r['confidence'], r.get('clicked'))
time.sleep(0.5)
if len(sys.argv) > 2:
    open(sys.argv[2], 'wb').write(base64.b64decode(O['screenshot']({})['image']))
O['key']({'keys': 'esc'})
time.sleep(0.3)
guard()
O['key']({'keys': 'cmd+w'})
time.sleep(0.8)
print('10 after cmd+w front:', front()['exe'], '|', front()['title'][:30])
