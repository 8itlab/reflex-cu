"""Platform-neutral half: observation merging, Jev judgments and the operations the MCP tools map to.

A backend (win.py / mac.py) supplies pixels, windows, the UI tree, OCR and input; everything here
works in the backend's "view" coordinate space and never touches the OS directly.
"""
import base64
import os
import sys
import time
from pathlib import Path

import httpx

VERSION = '0.3.4'
# Where Jev can be reached. All of these speak the same System One protocol (state + typed questions
# in, probabilities out); only the address, the key and the name of the model differ.
PROVIDERS = {
    'typesafe': {'url': os.environ.get('TYPESAFE_API_URL', 'https://api.typesafe.ai/v1/systemone'),
                 'model': os.environ.get('TYPESAFE_MODEL', 'jev-latest'), 'env': 'TYPESAFE_API_KEY', 'file': 'typesafe_key'},
    'openrouter': {'url': 'https://openrouter.ai/api/v1/systemone', 'model': '~typesafe/jev-latest',
                   'env': 'OPENROUTER_API_KEY', 'file': 'openrouter_key'},
    'commandcode': {'url': 'https://api.commandcode.ai/provider/v1/systemone', 'model': 'typesafe/jev',
                    'env': 'COMMANDCODE_API_KEY', 'file': 'commandcode_key'},
}
CONF = Path.home() / '.reflexcu'

if sys.platform == 'win32':
    from . import win as B
elif sys.platform == 'darwin':
    from . import mac as B
else:
    raise ImportError(f'reflexcu has no backend for {sys.platform}')


# ---- observation ----

LAST = {'elements': [], 'window': None, 'time': 0}


def clip(rect):
    w, h = B.view_size()
    return [max(0, rect[0]), max(0, rect[1]), min(w, rect[2]), min(h, rect[3])]


def observe(window=None, source='auto', region=None):
    """Elements of a window: the UI tree first, OCR when the tree is (nearly) empty, plus any open menu."""
    info = B.find_window(window)
    els = []
    tree_only = source in ('tree', 'uia', 'ax')
    if source in ('auto', 'both') or tree_only:
        try:
            els = B.observe_tree(info)
        except Exception as e:
            info['tree_error'] = repr(e)[:160]
    # Games and custom-drawn apps expose almost nothing to accessibility APIs: read the pixels instead.
    named = sum(1 for e in els if e['text'] and e['role'] != '菜单')
    if source in ('ocr', 'both') or (source == 'auto' and named < 6):
        seen = {e['text'] for e in els}
        els += [e for e in B.observe_ocr(region or clip(info['rect'])) if e['text'] not in seen]
    if not region:
        try:
            seen = {(e['text'], e['rect'][1] // 8) for e in els}
            els += [dict(e, popup=True) for e in B.observe_popups(info) if (e['text'], e['rect'][1] // 8) not in seen]
        except Exception as e:
            info['popup_error'] = repr(e)[:160]
    else:
        els = [e for e in els if e['rect'][2] > region[0] and e['rect'][0] < region[2]
               and e['rect'][3] > region[1] and e['rect'][1] < region[3]]
    for i, e in enumerate(els):
        e['id'] = i
    LAST.update(elements=els, window=info, time=time.time())
    return info, els


def center(e):
    r = e['rect']
    return (r[0] + r[2]) // 2, (r[1] + r[3]) // 2


def label(e, picking=False):
    """One line a text-only judge (and the agent) can act on: role, name, then whatever disambiguates it.

    When the judge is choosing what to operate, "selected" is left off ordinary items: it reads it as
    "nothing to do here" and backs away from the very item that was asked for."""
    owner = e.get('of')
    notes = [(f'“{owner}”的选项' if owner else '弹出菜单的选项') if e.get('popup') else f'属于“{owner}”' if owner else '',
             e.get('state') or '', '已选中' if e.get('selected') and (e.get('popup') or not picking) else '',
             '要滚动才能看到' if e.get('hidden') else '', '禁用' if e.get('disabled') else '']
    notes = '，'.join(n for n in notes if n)
    return f"{e['role']}：{e['text'] or '（无名称）'}" + (f'（{notes}）' if notes else '')


def brief(e):
    if e.get('hidden'):
        return {'id': e['id'], 'label': label(e), 'offscreen': True}  # no position until it is scrolled to
    x, y = center(e)
    out = {'id': e['id'], 'label': label(e), 'x': x, 'y': y, 'rect': e['rect']}
    if e.get('popup'):
        out['popup'] = True
    return out


def shown(e):
    """Make sure an element can be clicked: one that is scrolled out of view is brought in first."""
    if e.get('hidden'):
        e['rect'] = clip(B.reveal(e))
        del e['hidden']
        time.sleep(0.1)
    return e


def name_of(info):
    return info.get('title') or info.get('exe') or ''


# ---- Jev ----

def setting(env, name):
    """An environment variable, or the file ~/.reflexcu/<name>. The file form exists because a daemon
    started by the Windows task scheduler does not see variables set after the last logon."""
    v = os.environ.get(env, '').strip()
    f = CONF / name
    return v or (f.read_text().strip() if f.exists() else '')


# System proxies are ignored on purpose (on Windows they add seconds per request); name one explicitly
# when the Jev API is not reachable directly.
_http = httpx.Client(trust_env=False, timeout=8, proxy=setting('CU_PROXY', 'proxy') or None)


def jev_provider():
    """(name, key) of the provider to ask: the one named in CU_JEV_PROVIDER (or the file jev_provider),
    otherwise the first one that has a key. The key is '' when none is configured."""
    want = setting('CU_JEV_PROVIDER', 'jev_provider').lower()
    if want and want not in PROVIDERS:
        raise RuntimeError(f"unknown Jev provider {want!r}: use one of {', '.join(PROVIDERS)}")
    for name, p in PROVIDERS.items():
        if want in ('', name):
            key = setting(p['env'], p['file'])
            if key or want:
                return name, key
    return None, ''


def jev(state, questions):
    name, key = jev_provider()
    if not key:
        raise RuntimeError('no Jev key: bring your own, from any one of ' + '; '.join(
            f"{n} ({q['env']}, or the file {CONF / q['file']})" for n, q in PROVIDERS.items()))
    p = PROVIDERS[name]
    # CU_JEV_URL / CU_JEV_MODEL point the chosen key at any other gateway that speaks the same protocol
    r = _http.post(setting('CU_JEV_URL', 'jev_url') or p['url'], headers={'Authorization': 'Bearer ' + key},
                   json={'model': setting('CU_JEV_MODEL', 'jev_model') or p['model'], 'state': state, 'questions': questions})
    if r.status_code == 451:
        raise RuntimeError(f"the Jev API at {name} refuses requests from this network (HTTP 451); put a proxy URL in CU_PROXY "
                           f"or in the file {CONF / 'proxy'}" + (', or reach Jev through another provider (OpenRouter, Command Code)' if name == 'typesafe' else ''))
    if r.status_code in (401, 403):
        raise RuntimeError(f"{name} rejected the Jev key (HTTP {r.status_code}); check the key in {p['env']} or {CONF / p['file']}")
    if r.status_code == 402:
        raise RuntimeError(f"the {name} account has no credit left for Jev (HTTP 402)")
    if r.status_code >= 400:
        raise RuntimeError(f"Jev request to {name} failed (HTTP {r.status_code}): {r.text[:200]}")
    body = r.json()
    if 'answers' not in body:
        raise RuntimeError(f"unexpected Jev response from {name}: {r.text[:200]}")
    return body['answers']


def screen_text(els, cap=6000):
    """Reading order (top to bottom, left to right) so a text-only judge can follow the layout."""
    rows = sorted(els, key=lambda e: (e['rect'][1] // 12, e['rect'][0]))
    # An open menu is what matters right now; a judge reading 100 lines of window text would miss it at the end.
    menu = [label(e) for e in rows if e.get('popup')]
    head = '【当前弹出的菜单或下拉列表】\n' + '\n'.join(menu) + '\n【窗口内容】\n' if menu else ''
    below = [e['text'] for e in els if e.get('hidden')]
    tail = '\n【窗口里还有这些项，但要滚动才能看到】\n' + '、'.join(below) if below else ''
    body = '\n'.join(label(e) for e in rows if e['text'] and not e.get('popup') and not e.get('hidden'))
    return (head + body)[:cap - len(tail)] + tail


def dedupe(cands):
    """One option per control. A UI tree usually lists the same control several times (a list item,
    the group inside it, its text label); offered as separate options they split the judge's
    confidence between them. Keep the clickable one, or else the smallest."""
    def inside(a, b):
        cx, cy = center(a)
        return b['rect'][0] <= cx <= b['rect'][2] and b['rect'][1] <= cy <= b['rect'][3]

    area = lambda e: (e['rect'][2] - e['rect'][0]) * (e['rect'][3] - e['rect'][1])
    kept = []
    for e in sorted(cands, key=lambda e: (not e['clickable'], area(e))):
        if e['text'] and any(o['text'] == e['text'] and (inside(e, o) or inside(o, e)) for o in kept):
            continue
        kept.append(e)
    return sorted(kept, key=lambda e: e['id'])


PICK = '要完成 `goal`，现在应该操作 `window` 窗口里的哪一个界面元素？只在有明确对应的元素时才选，否则选 none。'
# Without this the judge hedges between an option and the control it belongs to: a flat list of
# candidates does not say that an open list is waiting for an answer.
PICK_OPEN = ' `open` 说明当前有一个展开的下拉列表或菜单，它的选项在文字里标了“的选项”；这种时候目标通常是其中一个选项。'


def jev_pick(goal, els, context=''):
    """Which element serves `goal`? Returns (element or None, confidence, ranked alternatives)."""
    cands = dedupe([e for e in els if e['text'] or e['clickable']])
    if not cands:
        return None, 0.0, []
    byid = {e['id']: e for e in els}
    # An agent often quotes a label it has just read. That needs no judgment, and a fuzzy judge is
    # oddly unsure about it when two controls share a name.
    said = goal.strip()
    exact = [e for e in cands if said in (label(e), label(e, True), f"{e['role']}：{e['text']}", e['text'])]
    if len(exact) == 1:
        return exact[0], 1.0, [(1.0, exact[0])]

    state, instructions = {'goal': goal, 'window': context}, PICK
    owners = {e.get('of') or '' for e in cands if e.get('popup')}
    if owners:
        named = '、'.join(f'“{o}”' for o in sorted(owners) if o)
        state['open'] = (f'下拉列表{named}已展开' if named else '有一个菜单已弹出') + '，正在等待选择一个选项'
        instructions += PICK_OPEN

    def ask(crit):
        crit = dict(crit, none='以上都不是，或者屏幕上没有合适的元素')
        probs = jev(state, {'pick': {'type': 'choice', 'criteria': crit, 'instructions': instructions}})['pick'].get('probabilities') or {}
        return sorted(((p, k) for k, p in probs.items() if k != 'none'), reverse=True)

    # Jev caps a choice at 255 options: run heats, then a final among the heat winners.
    heats = [cands[i:i + 200] for i in range(0, len(cands), 200)]
    best = []
    for heat in heats:
        best += ask({f"e{e['id']}": label(e, True) for e in heat})[:5]
    best.sort(reverse=True)
    if len(heats) > 1 and best:
        best = ask({k: label(byid[int(k[1:])], True) for _, k in best[:20]})
    ranked = [(round(p, 3), byid[int(k[1:])]) for p, k in best[:4] if p > 0.01]
    if not ranked:
        return None, 0.0, []
    return ranked[0][1], ranked[0][0], ranked


def jev_check(question, window=None, source='auto'):
    info, els = observe(window, source)
    state = {'window': info.get('title', ''), 'app': info.get('exe', ''), 'screen': screen_text(els)}
    p = jev(state, {'q': {'type': 'noul', 'instructions':
                          f'`screen` 是当前屏幕上按阅读顺序列出的界面文字。根据它判断：{question}'}})['q'].get('noul', 0.0)
    return round(p, 3), info, els


# ---- operations ----

def jev_status():
    try:
        name, key = jev_provider()
    except RuntimeError as e:
        return {'jev': False, 'jev_error': str(e)}
    return {'jev': bool(key), 'jev_provider': name} if key else {'jev': False}


def op_status(a):
    try:
        fg = B.find_window(None)
    except Exception:
        fg = None
    return {'version': VERSION, 'host': os.environ.get('COMPUTERNAME') or os.uname().nodename,
            'screen': list(B.screen_size()), 'view': list(B.view_size()), 'scale': round(B.scale_factor(), 4),
            'foreground': fg, 'idle_seconds': B.idle_seconds(), **jev_status(), 'time': round(time.time(), 3),
            **B.status_extra()}


def op_screenshot(a):
    region = a.get('region')
    if a.get('window') and not region:
        region = clip(B.find_window(a['window'])['rect'])
    img, data = B.grab(region, zoom=bool(a.get('zoom')), quality=int(a.get('quality', 70)))
    return {'image': base64.b64encode(data).decode(), 'size': list(img.size), 'region': region,
            'note': 'zoom 图只用来看清细节，坐标仍以普通截图为准' if a.get('zoom') else None}


def op_windows(a):
    return {'windows': B.list_windows()}


def op_focus(a):
    return {'window': B.focus(a.get('window'))}


def op_observe(a):
    info, els = observe(a.get('window'), a.get('source', 'auto'), a.get('region'))
    # "模式|透明" keeps elements containing either word; the label is searched too, so "已展开" or "关" work
    words = [w for w in (a.get('filter') or '').lower().split('|') if w.strip()]
    shown = [e for e in els if any(w.strip() in label(e).lower() for w in words)] if words else els
    return {'window': info, 'count': len(els), 'elements': [brief(e) for e in shown[:int(a.get('limit', 150))]]}


def target(a):
    if a.get('id') is not None:
        els = LAST['elements']
        i = int(a['id'])
        if not 0 <= i < len(els):
            raise ValueError(f'no element {i} in the last observation')
        return center(shown(els[i]))
    return int(a['x']), int(a['y'])


def op_click(a):
    x, y = target(a)
    B.click(x, y, a.get('button', 'left'), int(a.get('count', 1)), float(a.get('hold', 0.04)))
    return {'clicked': [x, y]}


def op_move(a):
    if a.get('relative'):
        B.move_rel(a['x'], a['y'])
        return {'moved_by': [a['x'], a['y']]}
    x, y = target(a)
    B.move_to(x, y)
    return {'moved': [x, y]}


def op_drag(a):
    B.drag(a['x0'], a['y0'], a['x1'], a['y1'], a.get('button', 'left'), float(a.get('seconds', 0.4)))
    return {'dragged': [a['x0'], a['y0'], a['x1'], a['y1']]}


def op_scroll(a):
    x, y = target(a) if ('x' in a or 'id' in a) else B.cursor()
    B.scroll(x, y, a.get('dy', 0), a.get('dx', 0))
    return {'scrolled': [a.get('dx', 0), a.get('dy', 0)], 'at': [x, y]}


def op_key(a):
    B.press(a['keys'], float(a.get('hold', 0.05)), int(a.get('times', 1)))
    return {'pressed': a['keys']}


def op_type(a):
    B.type_text(a['text'], bool(a.get('paste')))
    if a.get('enter'):
        B.press('enter')
    return {'typed': len(a['text'])}


def op_find(a):
    info, els = observe(a.get('window'), a.get('source', 'auto'), a.get('region'))
    t = time.time()
    el, conf, ranked = jev_pick(a['goal'], els, name_of(info))
    out = {'window': name_of(info), 'elements': len(els), 'confidence': conf, 'jev_ms': int((time.time() - t) * 1000),
           'match': brief(el) if el else None,
           'alternatives': [dict(brief(e), confidence=p) for p, e in ranked[1:]]}
    need = float(a.get('min_confidence', 0.75))
    if a.get('click') and el:
        if conf >= need and not el.get('disabled'):
            x, y = center(shown(el))
            B.click(x, y, a.get('button', 'left'), int(a.get('count', 1)))
            out['clicked'] = [x, y]
        else:
            out['clicked'] = None
            out['why'] = '元素被禁用' if el.get('disabled') else f'置信度 {conf} 低于 {need}，没有点击'
    return out


def op_check(a):
    t = time.time()
    p, info, els = jev_check(a['question'], a.get('window'), a.get('source', 'auto'))
    return {'probability': p, 'yes': p >= float(a.get('threshold', 0.7)), 'window': name_of(info),
            'elements': len(els), 'ms': int((time.time() - t) * 1000)}


def op_wait(a):
    """Poll until Jev says `question` holds. Saves a full model round trip per poll."""
    deadline = time.time() + min(float(a.get('timeout', 10)), 120)
    need = float(a.get('threshold', 0.7))
    polls, p, info = 0, 0.0, {}
    while True:
        try:
            p, info, _ = jev_check(a['question'], a.get('window'), a.get('source', 'auto'))
        except ValueError:  # the window being waited for does not exist yet
            p = 0.0
        polls += 1
        if p >= need or time.time() >= deadline:
            break
        time.sleep(float(a.get('interval', 0.6)))
    return {'yes': p >= need, 'probability': p, 'polls': polls, 'window': name_of(info)}


def op_steps(a):
    """Run a short scripted sequence without going back to the planner between steps.

    Each step is one op ({"op": "find", "goal": ..., "click": true}, {"op": "key", ...}, ...).
    Stops at the first step that fails or that Jev is not confident about.
    """
    done, t0 = [], time.time()
    for i, step in enumerate(a['steps']):
        op, ts = step.get('op'), time.time()
        if op not in OPS or op in ('steps', 'screenshot'):
            done.append({'step': i, 'error': f'unknown op {op!r}'})
            break
        try:
            res = OPS[op](step)
        except Exception as e:
            done.append({'step': i, 'op': op, 'error': repr(e)[:300]})
            break
        if op == 'observe' and i < len(a['steps']) - 1:
            res.pop('elements', None)  # only a closing observe is worth its length
        # when each step began and how long it took: without this a slow batch cannot be diagnosed
        done.append({'step': i, 'op': op, **res, 'at_ms': int((ts - t0) * 1000), 'ms': int((time.time() - ts) * 1000)})
        stuck = (op == 'find' and step.get('click') and not res.get('clicked')) or \
                (op in ('wait', 'check') and not res.get('yes') and step.get('required', True))
        if stuck:
            done[-1]['stopped'] = True
            break
        # the screen needs a moment after something was done to it, not after it was merely read
        if i < len(a['steps']) - 1 and (op in ACTING or res.get('clicked')):
            time.sleep(float(step.get('pause', a.get('pause', 0.35))))
    return {'completed': len(done) == len(a['steps']) and not done[-1].get('stopped') and 'error' not in done[-1],
            'started': round(t0, 3), 'steps': done}


ACTING = {'focus', 'click', 'move', 'drag', 'scroll', 'key', 'type'}
OPS = {'status': op_status, 'screenshot': op_screenshot, 'windows': op_windows, 'focus': op_focus,
       'observe': op_observe, 'click': op_click, 'move': op_move, 'drag': op_drag, 'scroll': op_scroll,
       'key': op_key, 'type': op_type, 'find': op_find, 'check': op_check, 'wait': op_wait, 'steps': op_steps}


def run(op, args):
    if op not in OPS:
        raise KeyError(f'unknown op {op!r}')
    t = time.time()
    res = OPS[op](args or {})
    res['took_ms'] = int((time.time() - t) * 1000)
    return res
