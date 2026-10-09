"""macOS backend: screencapture, the Accessibility tree, Vision OCR, Quartz events.

The app that launches the process (Terminal, an IDE, ...) needs the Accessibility and Screen
Recording permissions; macOS grants them per host app.

Coordinates: every x/y the backend takes or returns is in "view" space = main-display points times
the scale factor, the same convention as the Windows backend.
"""
import io
import os
import subprocess
import tempfile
import time
from pathlib import Path

import ApplicationServices as AS
import AppKit
import Quartz
import Vision
from Foundation import NSURL
from PIL import Image

VIEW_W = int(os.environ.get('CU_VIEW_W', '1600'))
TREE = 'ax'
TMP = Path(tempfile.gettempdir()) / 'reflexcu'
TMP.mkdir(exist_ok=True)


# ---- screen geometry (points <-> view) ----

def screen():
    b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    return b.size.width, b.size.height


def scale():
    return min(1.0, VIEW_W / screen()[0])


def screen_size():
    w, h = screen()
    return int(w), int(h)


def scale_factor():
    return scale()


def view_size():
    w, h = screen()
    return round(w * scale()), round(h * scale())


def to_pts(x, y):
    k = scale()
    return x / k, y / k


def view_rect(x, y, w, h):
    k = scale()
    return [int(round(x * k)), int(round(y * k)), int(round((x + w) * k)), int(round((y + h) * k))]


def capture(region=None, fmt='png'):
    """Native-resolution capture of the main display; region is [x0, y0, x1, y1] in view space."""
    path = TMP / f'cap.{fmt}'
    cmd = ['screencapture', '-x', '-D', '1', '-t', fmt]
    if region:
        x0, y0 = to_pts(region[0], region[1])
        x1, y1 = to_pts(region[2], region[3])
        cmd += ['-R', f'{x0:.0f},{y0:.0f},{max(1, x1 - x0):.0f},{max(1, y1 - y0):.0f}']
    subprocess.run(cmd + [str(path)], check=True, timeout=15)
    return path


def grab(region=None, zoom=False, quality=70):
    img = Image.open(capture(region)).convert('RGB')
    if not zoom:
        w, h = (region[2] - region[0], region[3] - region[1]) if region else [round(v * scale()) for v in screen()]
        if (w, h) != img.size:
            img = img.resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=quality)
    return img, buf.getvalue()


# ---- windows ----

def front_pid():
    err, app = AS.AXUIElementCopyAttributeValue(AS.AXUIElementCreateSystemWide(), 'AXFocusedApplication', None)
    if err == 0 and app is not None:
        err, pid = AS.AXUIElementGetPid(app, None)
        if err == 0:
            return pid
    for w in _cg_windows():
        return w['kCGWindowOwnerPID']
    return None


def _cg_windows():
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    return [w for w in Quartz.CGWindowListCopyWindowInfo(opts, 0) or []
            if w.get('kCGWindowLayer') == 0 and w['kCGWindowBounds']['Width'] > 40 and w['kCGWindowBounds']['Height'] > 40]


def popups(pid):
    """Open menus and popovers of an app: separate windows above the normal layer, invisible to the window's AX tree."""
    opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    out = []
    for w in Quartz.CGWindowListCopyWindowInfo(opts, 0) or []:
        b, layer = w['kCGWindowBounds'], w.get('kCGWindowLayer', 0)
        # layer 24/25 are the menu bar and its status items
        if w['kCGWindowOwnerPID'] == pid and layer > 0 and layer not in (24, 25) and b['Width'] > 30 and b['Height'] > 15:
            out.append(view_rect(b['X'], b['Y'], b['Width'], b['Height']))
    return out


def list_windows():
    fp, out, seen_front = front_pid(), [], False
    for w in _cg_windows():  # front to back
        b = w['kCGWindowBounds']
        fg = w['kCGWindowOwnerPID'] == fp and not seen_front
        seen_front = seen_front or fg
        out.append({'hwnd': int(w['kCGWindowNumber']), 'title': w.get('kCGWindowName') or '',
                    'exe': w.get('kCGWindowOwnerName') or '', 'pid': int(w['kCGWindowOwnerPID']),
                    'rect': view_rect(b['X'], b['Y'], b['Width'], b['Height']), 'minimized': False, 'foreground': fg})
    return out


def find_window(spec):
    """spec: window number, or a case-insensitive substring of the window title or app name."""
    wins = list_windows()
    if spec in (None, ''):
        for w in wins:
            if w['foreground']:
                return w
        raise ValueError('no foreground window')
    if isinstance(spec, int) or str(spec).isdigit():
        for w in wins:
            if w['hwnd'] == int(spec):
                return w
        raise ValueError(f'no window {spec}')
    s = str(spec).lower()
    for test in (lambda w: s == w['exe'].lower() or s == w['title'].lower(),
                 lambda w: s in w['title'].lower(), lambda w: s in w['exe'].lower()):
        for w in wins:
            if test(w):
                return w
    raise ValueError(f'no window matches {spec!r}')


def ax_app(pid):
    app = AS.AXUIElementCreateApplication(pid)
    AS.AXUIElementSetMessagingTimeout(app, 1.5)
    return app


def ax_get(el, attr):
    err, v = AS.AXUIElementCopyAttributeValue(el, attr, None)
    return v if err == 0 else None


def ax_window(info):
    """The AX element of the CG window `info` (matched by title, then by position)."""
    app = ax_app(info['pid'])
    wins = ax_get(app, 'AXWindows') or []
    for w in wins:
        if (ax_get(w, 'AXTitle') or '') == info['title'] and info['title']:
            return app, w
    for w in wins:
        r = ax_rect(ax_get(w, 'AXPosition'), ax_get(w, 'AXSize'))
        if r and abs(r[0] - info['rect'][0]) < 3 and abs(r[1] - info['rect'][1]) < 3:
            return app, w
    return app, ax_get(app, 'AXFocusedWindow') or (wins[0] if wins else None)


def focus(spec):
    info = find_window(spec)
    app, win = ax_window(info)
    if win is not None:
        AS.AXUIElementPerformAction(win, 'AXRaise')
    AS.AXUIElementSetAttributeValue(app, 'AXFrontmost', True)
    time.sleep(0.3)
    return find_window(info['hwnd'])


def idle_seconds():
    return round(Quartz.CGEventSourceSecondsSinceLastEventType(Quartz.kCGEventSourceStateHIDSystemState, 0xFFFFFFFF), 1)


# ---- input ----

def post(ev):
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


MOUSE = {'left': (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp, Quartz.kCGEventLeftMouseDragged, 0),
         'right': (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp, Quartz.kCGEventRightMouseDragged, 1),
         'middle': (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp, Quartz.kCGEventOtherMouseDragged, 2)}


def mouse_event(kind, x, y, button=0, clicks=1):
    ev = Quartz.CGEventCreateMouseEvent(None, kind, to_pts(x, y), button)
    Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, clicks)
    post(ev)


def cursor():
    p = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    k = scale()
    return int(p.x * k), int(p.y * k)


def move_rel(dx, dy):
    cx, cy = cursor()
    move_to(cx + int(dx), cy + int(dy))


def move_to(x, y):
    mouse_event(Quartz.kCGEventMouseMoved, x, y)


def click(x, y, button='left', count=1, hold=0.04):
    down, up, _, b = MOUSE[button]
    move_to(x, y)
    time.sleep(0.05)
    for i in range(count):
        mouse_event(down, x, y, b, i + 1)
        time.sleep(hold)
        mouse_event(up, x, y, b, i + 1)
        if i + 1 < count:
            time.sleep(0.08)


def drag(x0, y0, x1, y1, button='left', seconds=0.4):
    down, up, dragged, b = MOUSE[button]
    move_to(x0, y0)
    time.sleep(0.05)
    mouse_event(down, x0, y0, b)
    time.sleep(0.15)  # the window server drops motion that arrives before it has recognised the drag
    steps = max(4, int(seconds / 0.016))
    for i in range(1, steps + 1):
        mouse_event(dragged, x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps, b)
        time.sleep(seconds / steps)
    time.sleep(0.12)
    mouse_event(dragged, x1, y1, b)
    time.sleep(0.05)
    mouse_event(up, x1, y1, b)


def scroll(x, y, dy=0, dx=0):
    """dy > 0 scrolls down, in lines."""
    move_to(x, y)
    time.sleep(0.05)
    for _ in range(abs(int(dy))):
        post(Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 2, -1 if dy > 0 else 1, 0))
        time.sleep(0.02)
    for _ in range(abs(int(dx))):
        post(Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 2, 0, -1 if dx > 0 else 1))
        time.sleep(0.02)


KEYCODE = {**dict(zip('asdfhgzxcv', range(10))), 'b': 11, 'q': 12, 'w': 13, 'e': 14, 'r': 15, 'y': 16, 't': 17,
           '1': 18, '2': 19, '3': 20, '4': 21, '6': 22, '5': 23, '=': 24, '9': 25, '7': 26, '-': 27, '8': 28, '0': 29,
           ']': 30, 'o': 31, 'u': 32, '[': 33, 'i': 34, 'p': 35, 'l': 37, 'j': 38, "'": 39, 'k': 40, ';': 41,
           '\\': 42, ',': 43, '/': 44, 'n': 45, 'm': 46, '.': 47, '`': 50,
           'enter': 36, 'return': 36, 'tab': 48, 'space': 49, 'backspace': 51, 'esc': 53, 'escape': 53,
           'cmd': 55, 'command': 55, 'win': 55, 'shift': 56, 'capslock': 57, 'alt': 58, 'option': 58, 'opt': 58,
           'ctrl': 59, 'control': 59, 'fn': 63, 'home': 115, 'pageup': 116, 'delete': 117, 'del': 117, 'end': 119,
           'pagedown': 121, 'left': 123, 'right': 124, 'down': 125, 'up': 126,
           'f1': 122, 'f2': 120, 'f3': 99, 'f4': 118, 'f5': 96, 'f6': 97, 'f7': 98, 'f8': 100, 'f9': 101,
           'f10': 109, 'f11': 103, 'f12': 111}
FLAGS = {55: Quartz.kCGEventFlagMaskCommand, 56: Quartz.kCGEventFlagMaskShift,
         58: Quartz.kCGEventFlagMaskAlternate, 59: Quartz.kCGEventFlagMaskControl}


def keycode(name):
    n = name.strip().lower() or name  # a bare ' ' is not a key name; use "space"
    if n not in KEYCODE:
        raise ValueError(f'unknown key {name!r}')
    return KEYCODE[n]


def key_event(code, down, flags):
    ev = Quartz.CGEventCreateKeyboardEvent(None, code, down)
    Quartz.CGEventSetFlags(ev, flags)
    post(ev)


def press(combo, hold=0.05, times=1):
    codes = [keycode(k) for k in combo.split('+')]
    for i in range(times):
        flags = 0
        for c in codes:
            flags |= FLAGS.get(c, 0)
            key_event(c, True, flags)
            time.sleep(0.01)
        time.sleep(hold)
        for c in reversed(codes):
            flags &= ~FLAGS.get(c, 0)
            key_event(c, False, flags)
        if i + 1 < times:
            time.sleep(0.06)


def type_text(text, paste=False):
    if paste:
        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
        time.sleep(0.12)
        press('cmd+v')
        time.sleep(0.05)
        return
    for ch in text:
        if ch == '\n':
            press('enter')
            continue
        n = len(ch.encode('utf-16-le')) // 2
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
            Quartz.CGEventSetFlags(ev, 0)
            Quartz.CGEventKeyboardSetUnicodeString(ev, n, ch)
            post(ev)
        time.sleep(0.008)


# ---- observation: Accessibility tree + Vision OCR ----

ROLES = {'AXButton': '按钮', 'AXCheckBox': '复选框', 'AXPopUpButton': '下拉框', 'AXComboBox': '下拉框',
         'AXTextField': '输入框', 'AXTextArea': '输入框', 'AXSearchField': '输入框', 'AXLink': '链接',
         'AXImage': '图片', 'AXMenuItem': '菜单项', 'AXMenuBarItem': '菜单', 'AXMenuButton': '按钮',
         'AXRadioButton': '单选', 'AXSlider': '滑块', 'AXStaticText': '文本', 'AXRow': '行', 'AXCell': '单元格',
         'AXHeading': '标题', 'AXDisclosureTriangle': '展开箭头', 'AXTabGroup': '标签页组', 'AXToolbar': '工具栏',
         'AXIncrementor': '微调', 'AXColorWell': '颜色', 'AXOutline': '列表', 'AXTable': '表格', 'AXList': '列表'}
CLICKABLE = {'AXButton', 'AXCheckBox', 'AXPopUpButton', 'AXComboBox', 'AXTextField', 'AXTextArea', 'AXSearchField',
             'AXLink', 'AXMenuItem', 'AXMenuBarItem', 'AXMenuButton', 'AXRadioButton', 'AXSlider', 'AXRow', 'AXCell',
             'AXDisclosureTriangle', 'AXIncrementor'}
ATTRS = ['AXRole', 'AXSubrole', 'AXTitle', 'AXDescription', 'AXValue', 'AXPosition', 'AXSize', 'AXChildren', 'AXEnabled']


def ax_rect(pos, size):
    try:
        ok1, p = AS.AXValueGetValue(pos, AS.kAXValueCGPointType, None)
        ok2, s = AS.AXValueGetValue(size, AS.kAXValueCGSizeType, None)
        return (p.x, p.y, s.width, s.height) if ok1 and ok2 else None
    except Exception:
        return None


def observe_tree(info, limit=600, budget=3.0):
    app, win = ax_window(info)
    # Electron and Chromium build their accessibility tree only once a client asks for it.
    AS.AXUIElementSetAttributeValue(app, 'AXManualAccessibility', True)
    out, deadline = [], time.time() + budget
    wx0, wy0, wx1, wy1 = info['rect']
    queue = [win] if win is not None else []
    menubar = ax_get(app, 'AXMenuBar') if info['foreground'] else None
    queue += list(ax_get(menubar, 'AXChildren') or []) if menubar is not None else []
    seen = 0
    while queue and len(out) < limit and seen < 4000 and time.time() < deadline:
        el = queue.pop(0)
        seen += 1
        err, vals = AS.AXUIElementCopyMultipleAttributeValues(el, ATTRS, 0, None)
        if err != 0 or vals is None:
            continue
        # Attributes an element does not have come back as AXValue error markers, not None.
        role, sub, title, desc, value = [v if isinstance(v, str) else None for v in vals[:5]]
        pos, size = vals[5], vals[6]
        kids = vals[7] if hasattr(vals[7], '__len__') and not isinstance(vals[7], str) else None
        enabled = vals[8] if isinstance(vals[8], bool) else None
        r = ax_rect(pos, size)
        if role != 'AXMenuBarItem' and kids:
            queue += list(kids)
        if not isinstance(role, str) or not r or r[2] < 3 or r[3] < 3:
            continue
        rect = view_rect(*r)
        if role != 'AXMenuBarItem' and (rect[2] <= wx0 or rect[0] >= wx1 or rect[3] <= wy0 or rect[1] >= wy1):
            continue
        text = next((t.strip() for t in (title, desc, value if role in ('AXStaticText', 'AXTextField', 'AXLink', 'AXHeading') else None)
                     if isinstance(t, str) and t.strip()), '')
        if not text and role not in CLICKABLE:
            continue
        if role in ('AXRow', 'AXCell') and not text:
            continue
        item = {'role': '标签页' if sub == 'AXTabButton' else ROLES.get(role, '元素'), 'text': text[:120].replace('\n', ' '),
                'rect': rect, 'src': 'ax', 'clickable': role in CLICKABLE}
        if enabled is False:
            item['disabled'] = True
        out.append(item)
    return out


def observe_ocr(region=None):
    path = capture(region)
    img = Image.open(path)
    vw0 = (region[2] - region[0]) if region else screen()[0] * scale()
    if img.width < vw0 * 1.5:
        # On a non-Retina display UI text is ~10 px tall and Vision skips whole lines; enlarge first.
        img = img.convert('RGB').resize((img.width * 2, img.height * 2), Image.LANCZOS)
        path = TMP / 'ocr.png'
        img.save(path)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_(['zh-Hans', 'en-US'])
    req.setUsesLanguageCorrection_(False)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(path)), None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(f'OCR failed: {err}')
    # Vision boxes are normalised with the origin at the bottom-left of the captured image.
    vw, vh = (region[2] - region[0], region[3] - region[1]) if region else [v * scale() for v in screen()]
    ox, oy = (region[0], region[1]) if region else (0, 0)
    out = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)
        if not cand or cand[0].confidence() < 0.2 or not cand[0].string().strip():
            continue
        b = obs.boundingBox()
        x0, x1 = b.origin.x * vw + ox, (b.origin.x + b.size.width) * vw + ox
        y0, y1 = (1 - b.origin.y - b.size.height) * vh + oy, (1 - b.origin.y) * vh + oy
        out.append({'role': '文字', 'text': cand[0].string().strip()[:120], 'src': 'ocr', 'clickable': True,
                    'rect': [int(x0), int(y0), int(x1), int(y1)]})
    return out


def observe_popups(info):
    els = []
    vw, vh = view_size()
    for r in popups(info['pid']):
        area = [max(0, r[0]), max(0, r[1]), min(vw, r[2]), min(vh, r[3])]
        if area[2] > area[0] and area[3] > area[1]:
            els += [dict(e, role='菜单项') for e in observe_ocr(area)]
    return els


def status_extra():
    return {'os': 'macOS', 'accessibility': bool(AS.AXIsProcessTrusted()),
            'screen_recording': bool(Quartz.CGPreflightScreenCaptureAccess())}
