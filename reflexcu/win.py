"""Windows backend: screenshots (mss), UI Automation, RapidOCR, SendInput.

Coordinates: every x/y the backend takes or returns is in "view" space = physical pixels of the
primary monitor times the scale factor, so that what the model sees in a screenshot is what it
clicks. `zoom` screenshots keep physical resolution and are for reading only.
"""
import ctypes
import io
import os
import time
from ctypes import wintypes

import mss
from PIL import Image

VIEW_W = int(os.environ.get('CU_VIEW_W', '1600'))
TREE = 'uia'

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()
u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

MSS = getattr(mss, 'MSS', None) or mss.mss


# ---- screen geometry ----

def monitor(index=1):
    with MSS() as s:
        mons = s.monitors
        return mons[index if 0 < index < len(mons) else 1]


def scale(mon):
    return min(1.0, VIEW_W / mon['width'])


def to_phys(x, y, mon=None):
    mon = mon or monitor()
    k = scale(mon)
    return int(round(x / k)) + mon['left'], int(round(y / k)) + mon['top']


def to_view(px, py, mon=None):
    mon = mon or monitor()
    k = scale(mon)
    return int(round((px - mon['left']) * k)), int(round((py - mon['top']) * k))


def view_rect(l, t, r, b, mon=None):
    x0, y0 = to_view(l, t, mon)
    x1, y1 = to_view(r, b, mon)
    return [x0, y0, x1, y1]


def screen_size():
    mon = monitor()
    return mon['width'], mon['height']


def scale_factor():
    return scale(monitor())


def view_size():
    mon = monitor()
    return round(mon['width'] * scale(mon)), round(mon['height'] * scale(mon))


def grab(region=None, zoom=False, quality=70):
    """region is [x0, y0, x1, y1] in view space. zoom keeps physical resolution."""
    mon = monitor()
    k = scale(mon)
    box = dict(mon)
    if region:
        l, t = to_phys(region[0], region[1], mon)
        r, b = to_phys(region[2], region[3], mon)
        box = {'left': l, 'top': t, 'width': max(1, r - l), 'height': max(1, b - t)}
    with MSS() as s:
        raw = s.grab(box)
    img = Image.frombytes('RGB', raw.size, raw.bgra, 'raw', 'BGRX')
    if not zoom and k < 1:
        img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=quality)
    return img, buf.getvalue()


# ---- windows ----

def win_text(h):
    b = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(h, b, 512)
    return b.value


def win_exe(h):
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    hp = k32.OpenProcess(0x1000, False, pid.value)
    name = ''
    if hp:
        b = ctypes.create_unicode_buffer(520)
        n = wintypes.DWORD(520)
        if k32.QueryFullProcessImageNameW(hp, 0, b, ctypes.byref(n)):
            name = os.path.basename(b.value)
        k32.CloseHandle(hp)
    return name, pid.value


def win_info(h):
    r = wintypes.RECT()
    u32.GetWindowRect(h, ctypes.byref(r))
    exe, pid = win_exe(h)
    return {'hwnd': h, 'title': win_text(h), 'exe': exe, 'pid': pid,
            'rect': view_rect(r.left, r.top, r.right, r.bottom),
            'minimized': bool(u32.IsIconic(h)), 'foreground': h == u32.GetForegroundWindow()}


def list_windows():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if u32.IsWindowVisible(h) and win_text(h):
            cloaked = wintypes.DWORD()
            ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)
            if not cloaked.value:
                out.append(win_info(h))
        return True

    u32.EnumWindows(cb, 0)
    return out


def find_hwnd(spec):
    """spec: hwnd int, or a case-insensitive substring of the title or exe name."""
    if spec in (None, ''):
        return u32.GetForegroundWindow()
    if isinstance(spec, int) or str(spec).isdigit():
        return int(spec)
    s = str(spec).lower()
    wins = list_windows()
    for w in wins:
        if s == w['exe'].lower() or s == w['title'].lower():
            return w['hwnd']
    for w in wins:
        if s in w['title'].lower() or s in w['exe'].lower():
            return w['hwnd']
    raise ValueError(f'no window matches {spec!r}')


def find_window(spec):
    return win_info(find_hwnd(spec))


def focus(spec):
    h = find_hwnd(spec)
    if u32.IsIconic(h):
        u32.ShowWindow(h, 9)
    # A background process may not steal focus unless it shares input state with the foreground
    # thread. (Tapping Alt also works but puts the target window into menu mode.)
    me = k32.GetCurrentThreadId()
    other = u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), None)
    attached = other and other != me and u32.AttachThreadInput(me, other, True)
    u32.BringWindowToTop(h)
    u32.SetForegroundWindow(h)
    if attached:
        u32.AttachThreadInput(me, other, False)
    if u32.GetForegroundWindow() != h:
        send(INPUT(1, _IU(ki=KEYBDINPUT(0xE8, 0, 0, 0, 0))), INPUT(1, _IU(ki=KEYBDINPUT(0xE8, 0, 2, 0, 0))))
        u32.SetForegroundWindow(h)
    time.sleep(0.25)
    return win_info(h)


def idle_seconds():
    class LII(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]
    i = LII(ctypes.sizeof(LII), 0)
    u32.GetLastInputInfo(ctypes.byref(i))
    return round((k32.GetTickCount() - i.dwTime) / 1000, 1)


# ---- input ----

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]


class _IU(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('u', _IU)]


def send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    u32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def mouse(flags, dx=0, dy=0, data=0):
    return INPUT(0, _IU(mi=MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)))


def cursor():
    p = wintypes.POINT()
    u32.GetCursorPos(ctypes.byref(p))
    return to_view(p.x, p.y)


def move_rel(dx, dy):
    """Raw relative motion: what a first-person/third-person game camera listens to."""
    send(mouse(0x0001, int(dx), int(dy)))


def move_to(x, y):
    px, py = to_phys(x, y)
    vx, vy = u32.GetSystemMetrics(76), u32.GetSystemMetrics(77)
    vw, vh = u32.GetSystemMetrics(78), u32.GetSystemMetrics(79)
    nx = int((px - vx) * 65535 / max(1, vw - 1))
    ny = int((py - vy) * 65535 / max(1, vh - 1))
    send(mouse(0x0001 | 0x8000 | 0x4000, nx, ny))


BUTTONS = {'left': (0x0002, 0x0004), 'right': (0x0008, 0x0010), 'middle': (0x0020, 0x0040)}


def click(x, y, button='left', count=1, hold=0.04):
    move_to(x, y)
    time.sleep(0.05)
    down, up = BUTTONS[button]
    for i in range(count):
        send(mouse(down))
        time.sleep(hold)
        send(mouse(up))
        if i + 1 < count:
            time.sleep(0.08)


def drag(x0, y0, x1, y1, button='left', seconds=0.4):
    down, up = BUTTONS[button]
    move_to(x0, y0)
    time.sleep(0.05)
    send(mouse(down))
    steps = max(4, int(seconds / 0.016))
    for i in range(1, steps + 1):
        move_to(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        time.sleep(seconds / steps)
    send(mouse(up))


def scroll(x, y, dy=0, dx=0):
    """dy > 0 scrolls down, in wheel notches."""
    move_to(x, y)
    time.sleep(0.05)
    for _ in range(abs(int(dy))):
        send(mouse(0x0800, data=-120 if dy > 0 else 120))
        time.sleep(0.02)
    for _ in range(abs(int(dx))):
        send(mouse(0x1000, data=120 if dx > 0 else -120))
        time.sleep(0.02)


VK = {'ctrl': 0x11, 'control': 0x11, 'shift': 0x10, 'alt': 0x12, 'win': 0x5B, 'enter': 0x0D, 'return': 0x0D,
      'esc': 0x1B, 'escape': 0x1B, 'tab': 0x09, 'space': 0x20, 'backspace': 0x08, 'delete': 0x2E, 'del': 0x2E,
      'insert': 0x2D, 'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22, 'up': 0x26, 'down': 0x28,
      'left': 0x25, 'right': 0x27, 'capslock': 0x14, 'printscreen': 0x2C, 'apps': 0x5D,
      **{f'f{i}': 0x6F + i for i in range(1, 25)}, **{f'num{i}': 0x60 + i for i in range(10)}}
EXTENDED = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x26, 0x28, 0x25, 0x27, 0x5B, 0x5D, 0x2C}


def vk_of(name):
    n = name.strip().lower()
    if n in VK:
        return VK[n]
    if len(n) == 1:
        v = u32.VkKeyScanW(ord(n)) & 0xFF
        if v != 0xFF:
            return v
    raise ValueError(f'unknown key {name!r}')


def key_event(vk, up=False):
    # Scancodes, not virtual keys: games read raw/DirectInput and ignore VK-only events.
    sc = u32.MapVirtualKeyW(vk, 0)
    flags = 0x0008 | (0x0002 if up else 0) | (0x0001 if vk in EXTENDED else 0)
    return INPUT(1, _IU(ki=KEYBDINPUT(0, sc, flags, 0, 0)))


def press(combo, hold=0.05, times=1):
    vks = [vk_of(k) for k in combo.split('+')]
    for i in range(times):
        for v in vks:
            send(key_event(v))
            time.sleep(0.01)
        time.sleep(hold)
        for v in reversed(vks):
            send(key_event(v, True))
        if i + 1 < times:
            time.sleep(0.06)


def type_text(text, paste=False):
    if paste:
        import win32clipboard as cb
        cb.OpenClipboard()
        try:
            cb.EmptyClipboard()
            cb.SetClipboardText(text, cb.CF_UNICODETEXT)
        finally:
            cb.CloseClipboard()
        time.sleep(0.12)  # clipboard listeners grab it right after a write; pasting at once can lose the race
        press('ctrl+v')
        time.sleep(0.05)
        return
    for ch in text:
        if ch == '\n':
            press('enter')
            continue
        data = ch.encode('utf-16-le')
        for i in range(0, len(data), 2):
            code = int.from_bytes(data[i:i + 2], 'little')
            send(INPUT(1, _IU(ki=KEYBDINPUT(0, code, 0x0004, 0, 0))),
                 INPUT(1, _IU(ki=KEYBDINPUT(0, code, 0x0004 | 0x0002, 0, 0))))
        time.sleep(0.006)


# ---- observation: UI Automation + OCR ----

_uia = None
ROLES = {50000: '按钮', 50002: '复选框', 50003: '下拉框', 50004: '输入框', 50005: '链接', 50006: '图片',
         50007: '列表项', 50008: '列表', 50009: '菜单', 50010: '菜单栏', 50011: '菜单项', 50013: '单选',
         50015: '滑块', 50016: '微调', 50018: '标签页组', 50019: '标签页', 50020: '文本', 50021: '工具栏',
         50023: '树', 50024: '树节点', 50025: '自定义', 50026: '分组', 50028: '表格', 50029: '单元格',
         50030: '文档', 50031: '分隔按钮', 50032: '窗口', 50033: '面板', 50034: '表头', 50035: '表头项',
         50036: '表格', 50037: '标题栏'}
CLICKABLE = {50000, 50002, 50003, 50004, 50005, 50007, 50011, 50013, 50015, 50019, 50024, 50029, 50031}
CONTAINERS = {50008, 50009, 50010, 50018, 50021, 50023, 50026, 50028, 50032, 50033, 50036, 50037}


def uia():
    global _uia
    if _uia is None:
        import comtypes
        import comtypes.client
        comtypes.client.GetModule('UIAutomationCore.dll')
        from comtypes.gen import UIAutomationClient as U
        _uia = (comtypes.CoCreateInstance(U.CUIAutomation._reg_clsid_, interface=U.IUIAutomation,
                                          clsctx=comtypes.CLSCTX_INPROC_SERVER), U)
    return _uia


def observe_uia(hwnd, limit=600, clip=True):
    auto, U = uia()
    root = auto.ElementFromHandle(hwnd)
    req = auto.CreateCacheRequest()
    for p in (30005, 30003, 30001, 30010, 30011):  # Name, ControlType, BoundingRectangle, IsEnabled, AutomationId
        req.AddProperty(p)
    cond = auto.CreatePropertyCondition(30022, False)  # IsOffscreen == false
    found = root.FindAllBuildCache(U.TreeScope_Descendants, cond, req)
    mon = monitor()
    wr = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(wr))
    out = []
    for i in range(min(found.Length, 4000)):
        e = found.GetElement(i)
        try:
            ct = e.CachedControlType
            name = (e.CachedName or '').strip()
            r = e.CachedBoundingRectangle
        except Exception:
            continue
        w, h = r.right - r.left, r.bottom - r.top
        if w < 3 or h < 3 or (clip and (r.right <= wr.left or r.left >= wr.right or r.bottom <= wr.top or r.top >= wr.bottom)):
            continue
        if not name and ct not in CLICKABLE:
            continue
        if ct in CONTAINERS and not name:
            continue
        item = {'role': ROLES.get(ct, '元素'), 'text': name[:120], 'rect': view_rect(r.left, r.top, r.right, r.bottom, mon),
                'src': 'uia', 'clickable': ct in CLICKABLE}
        if not name:
            try:
                item['text'] = (e.CachedAutomationId or '')[:60]
            except Exception:
                pass
        try:
            if not e.CachedIsEnabled:
                item['disabled'] = True
        except Exception:
            pass
        out.append(item)
        if len(out) >= limit:
            break
    return out


_ocr = None


def observe_ocr(region=None):
    """OCR works on physical pixels (small text survives), results come back in view space."""
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    import numpy as np
    img, _ = grab(region, zoom=True)
    res, _ = _ocr(np.asarray(img)[:, :, ::-1])
    mon = monitor()
    k = scale(mon)
    ox, oy = (region[0], region[1]) if region else (0, 0)
    out = []
    for box, text, conf in res or []:
        if float(conf) < 0.5 or not text.strip():
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        out.append({'role': '文字', 'text': text.strip()[:120], 'src': 'ocr', 'clickable': True,
                    'rect': [int(min(xs) * k + ox), int(min(ys) * k + oy), int(max(xs) * k + ox), int(max(ys) * k + oy)]})
    return out


def observe_tree(info):
    return observe_uia(info['hwnd'])


def win_class(h):
    b = ctypes.create_unicode_buffer(128)
    u32.GetClassNameW(h, b, 128)
    return b.value


def popup_windows(info):
    """Open menus, dropdowns and flyouts: separate top-level windows, so not descendants of the main one.

    Classic menus have the class #32768; modern toolkits use an uncaptioned popup owned by the window.
    """
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if h == info['hwnd'] or not u32.IsWindowVisible(h):
            return True
        cls = win_class(h)
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        style = u32.GetWindowLongW(h, -16)
        menu = cls == '#32768'
        # Owned by the window, not merely the same process: Explorer's taskbar and desktop are
        # same-process popups of every Explorer dialog.
        owner = u32.GetWindow(h, 4)
        owned = owner and (owner == info['hwnd'] or u32.GetAncestor(owner, 3) == info['hwnd'])
        flyout = owned and pid.value == info['pid'] and (style & 0x80000000) and (style & 0x00C00000) != 0x00C00000
        if not (menu or flyout):
            return True
        cloaked = wintypes.DWORD()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)
        r = wintypes.RECT()
        u32.GetWindowRect(h, ctypes.byref(r))
        if not cloaked.value and r.right - r.left > 30 and r.bottom - r.top > 15:
            out.append((h, view_rect(r.left, r.top, r.right, r.bottom), menu))
        return True

    u32.EnumWindows(cb, 0)
    return out[:6]


def observe_popups(info):
    els = []
    vw, vh = view_size()
    for h, rect, menu in popup_windows(info):
        try:
            found = observe_uia(h, limit=120, clip=False)
        except Exception:
            found = []
        if menu and not any(e['text'] for e in found):
            # owner-drawn menus expose nothing: read the pixels. Not for other flyouts: an app's
            # transparent overlay window would turn the whole screen into "menu items".
            area = [max(0, rect[0]), max(0, rect[1]), min(vw, rect[2]), min(vh, rect[3])]
            found = [dict(e, role='菜单项') for e in observe_ocr(area)] if area[2] > area[0] and area[3] > area[1] else []
        els += found
    return els


def status_extra():
    return {'os': 'Windows'}
