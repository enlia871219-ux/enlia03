# -*- coding: utf-8 -*-
"""Lawcro V1.0 - 이미지 매크로 / Mabinogi Mobile helper
Python 3.10+ / PySide6 / OpenCV / mss / pynput

This is a desktop macro utility prototype. Use only where automation is permitted.
"""
from __future__ import annotations

import json, os, sys, time, threading, hashlib, shutil, ctypes, ctypes.wintypes
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import mss
from pynput import mouse, keyboard

from PySide6.QtCore import Qt, QObject, Signal, QSize, QRect, QPoint, QTimer
from PySide6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QPen, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QSpinBox, QDoubleSpinBox, QRadioButton, QComboBox,
    QLabel, QTabWidget, QSplitter, QHeaderView, QLineEdit, QCheckBox,
    QAbstractItemView, QGroupBox, QFormLayout, QDialog, QDialogButtonBox,
    QToolButton, QFrame, QTextBrowser, QScrollArea
)
from PySide6.QtSvg import QSvgRenderer

APP_NAME = "ShadeLawcro V1.0 - 이미지 매크로"
# In a one-file PyInstaller build, bundled assets live in the temporary
# extraction directory, while user data should stay beside the EXE.
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
ASSET_DIR = BUNDLE_DIR / "assets"
ICON_DIR = ASSET_DIR / "icons"
DATA_DIR = APP_DIR / "data"
TEMPLATE_DIR = DATA_DIR / "templates"
SVG_CACHE_DIR = DATA_DIR / "svg_cache"
for p in (ASSET_DIR, ICON_DIR, DATA_DIR, TEMPLATE_DIR, SVG_CACHE_DIR): p.mkdir(parents=True, exist_ok=True)


def now(): return datetime.now().strftime("%H:%M:%S")

def clamp(v, a, b): return max(a, min(b, v))


def window_process_name(hwnd):
    """Return executable file name for a top-level window."""
    if os.name != 'nt' or not hwnd: return ''
    user32=ctypes.windll.user32; kernel32=ctypes.windll.kernel32
    pid=ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value: return ''
    PROCESS_QUERY_LIMITED_INFORMATION=0x1000
    h=kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h: return ''
    try:
        size=ctypes.wintypes.DWORD(32768); buf=ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(h)
    return ''


def _window_matches(hwnd, title='', process_name=''):
    user32=ctypes.windll.user32
    if not user32.IsWindowVisible(hwnd): return False
    n=user32.GetWindowTextLengthW(hwnd)
    if n <= 0: return False
    buf=ctypes.create_unicode_buffer(n+1); user32.GetWindowTextW(hwnd, buf, n+1)
    wt=buf.value
    title=title.strip().lower(); process_name=process_name.strip().lower()
    title_ok=(not title) or (title in wt.lower())
    pn=window_process_name(hwnd).lower()
    process_name=process_name.split('\\')[-1].split('/')[-1]
    process_ok=(not process_name) or (process_name == pn) or (process_name in pn)
    return title_ok and process_ok


def list_visible_windows():
    """Return visible top-level windows with a non-empty title."""
    if os.name != 'nt': return []
    user32=ctypes.windll.user32; rows=[]
    own=0
    try: own=int(user32.GetForegroundWindow())
    except Exception: pass
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_proc(hwnd, lparam):
        try:
            if not user32.IsWindowVisible(hwnd): return True
            n=user32.GetWindowTextLengthW(hwnd)
            if n <= 0: return True
            buf=ctypes.create_unicode_buffer(n+1); user32.GetWindowTextW(hwnd, buf, n+1)
            title=buf.value.strip()
            if not title: return True
            rows.append((int(hwnd), title, window_process_name(hwnd)))
        except Exception:
            pass
        return True
    user32.EnumWindows(enum_proc, 0)
    # remove duplicate HWNDs while preserving Windows enumeration order
    seen=set(); out=[]
    for row in rows:
        if row[0] not in seen:
            seen.add(row[0]); out.append(row)
    return out


def find_window_by_title(title: str, process_name: str = ''):
    """Find a visible top-level window by title substring and/or executable name."""
    if os.name != 'nt' or (not title.strip() and not process_name.strip()): return None
    user32=ctypes.windll.user32; found=[]
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_proc(hwnd, lparam):
        if _window_matches(hwnd, title, process_name):
            found.append(hwnd); return False
        return True
    user32.EnumWindows(enum_proc, 0)
    return found[0] if found else None


def find_previous_window(exclude_hwnd=None):
    """Return the first visible titled top-level window other than the macro app."""
    if os.name != 'nt': return None
    user32=ctypes.windll.user32; found=[]
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_proc(hwnd, lparam):
        if exclude_hwnd and int(hwnd) == int(exclude_hwnd): return True
        if user32.IsWindowVisible(hwnd):
            n=user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                found.append(hwnd); return False
        return True
    user32.EnumWindows(enum_proc, 0)
    return found[0] if found else None


def foreground_window_title():
    if os.name != 'nt': return ''
    user32=ctypes.windll.user32; hwnd=user32.GetForegroundWindow()
    n=user32.GetWindowTextLengthW(hwnd); buf=ctypes.create_unicode_buffer(n+1)
    user32.GetWindowTextW(hwnd, buf, n+1); return buf.value


def window_client_origin(hwnd):
    if os.name != 'nt' or not hwnd: return (0,0)
    user32=ctypes.windll.user32; pt=ctypes.wintypes.POINT(0,0)
    if user32.ClientToScreen(hwnd, ctypes.byref(pt)): return (pt.x, pt.y)
    return (0,0)


def background_click(hwnd, x, y):
    """Send a client-coordinate left click without moving the real cursor."""
    if os.name != 'nt' or not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return False
    user32=ctypes.windll.user32
    x=int(x); y=int(y)
    lparam=(y << 16) | (x & 0xFFFF)
    # Send a move first; some window procedures only accept clicks after
    # receiving a mouse-position update.
    user32.PostMessageW(hwnd, 0x0200, 0, lparam)  # WM_MOUSEMOVE
    ok_down=bool(user32.PostMessageW(hwnd, 0x0201, 0x0001, lparam))
    ok_up=bool(user32.PostMessageW(hwnd, 0x0202, 0x0000, lparam))
    if ok_down and ok_up:
        return True
    try:
        ok_down=bool(user32.SendMessageW(hwnd, 0x0201, 0x0001, lparam))
        ok_up=bool(user32.SendMessageW(hwnd, 0x0202, 0x0000, lparam))
        return ok_down and ok_up
    except Exception:
        return False


def grab_window(hwnd):
    """Capture the client area with PrintWindow, then fall back to MSS for GPU-rendered windows."""
    if os.name != 'nt' or not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return None
    user32=ctypes.windll.user32; gdi32=ctypes.windll.gdi32
    rc=ctypes.wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        return None
    w,h=rc.right-rc.left,rc.bottom-rc.top
    if w<=0 or h<=0: return None
    hwnddc=user32.GetDC(hwnd)
    memdc=gdi32.CreateCompatibleDC(hwnddc) if hwnddc else 0
    bmp=gdi32.CreateCompatibleBitmap(hwnddc,w,h) if hwnddc and memdc else 0
    old=gdi32.SelectObject(memdc,bmp) if bmp else 0
    try:
        ok=False
        if bmp:
            ok=bool(user32.PrintWindow(hwnd,memdc,2))
            if not ok: ok=bool(user32.PrintWindow(hwnd,memdc,0))
        if ok:
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_=[('biSize',ctypes.wintypes.DWORD),('biWidth',ctypes.wintypes.LONG),('biHeight',ctypes.wintypes.LONG),('biPlanes',ctypes.wintypes.WORD),('biBitCount',ctypes.wintypes.WORD),('biCompression',ctypes.wintypes.DWORD),('biSizeImage',ctypes.wintypes.DWORD),('biXPelsPerMeter',ctypes.wintypes.LONG),('biYPelsPerMeter',ctypes.wintypes.LONG),('biClrUsed',ctypes.wintypes.DWORD),('biClrImportant',ctypes.wintypes.DWORD)]
            class BITMAPINFO(ctypes.Structure):
                _fields_=[('bmiHeader',BITMAPINFOHEADER),('bmiColors',ctypes.c_uint32*3)]
            bmi=BITMAPINFO(); bmi.bmiHeader.biSize=ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth=w; bmi.bmiHeader.biHeight=-h; bmi.bmiHeader.biPlanes=1
            bmi.bmiHeader.biBitCount=32; bmi.bmiHeader.biCompression=0
            buf=(ctypes.c_ubyte*(w*h*4))()
            if gdi32.GetDIBits(memdc,bmp,0,h,ctypes.byref(buf),ctypes.byref(bmi),0)>0:
                arr=np.frombuffer(buf,dtype=np.uint8).reshape((h,w,4))
                img=cv2.cvtColor(arr,cv2.COLOR_BGRA2BGR)
                gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
                if float(gray.std())>2.0 and float(gray.mean())>1.0:
                    return img
    except Exception:
        pass
    finally:
        if bmp:
            try: gdi32.SelectObject(memdc,old); gdi32.DeleteObject(bmp)
            except Exception: pass
        if memdc:
            try: gdi32.DeleteDC(memdc)
            except Exception: pass
        if hwnddc:
            try: user32.ReleaseDC(hwnd,hwnddc)
            except Exception: pass
    # Second fallback: BitBlt from the window DC. This can work for
    # classic/GDI-rendered windows where PrintWindow is unavailable.
    try:
        hwnddc=user32.GetDC(hwnd)
        memdc=gdi32.CreateCompatibleDC(hwnddc) if hwnddc else 0
        bmp=gdi32.CreateCompatibleBitmap(hwnddc,w,h) if hwnddc and memdc else 0
        old=gdi32.SelectObject(memdc,bmp) if bmp else 0
        if bmp and gdi32.BitBlt(memdc,0,0,w,h,hwnddc,0,0,0x00CC0020):
            class BITMAPINFOHEADER2(ctypes.Structure):
                _fields_=[('biSize',ctypes.wintypes.DWORD),('biWidth',ctypes.wintypes.LONG),('biHeight',ctypes.wintypes.LONG),('biPlanes',ctypes.wintypes.WORD),('biBitCount',ctypes.wintypes.WORD),('biCompression',ctypes.wintypes.DWORD),('biSizeImage',ctypes.wintypes.DWORD),('biXPelsPerMeter',ctypes.wintypes.LONG),('biYPelsPerMeter',ctypes.wintypes.LONG),('biClrUsed',ctypes.wintypes.DWORD),('biClrImportant',ctypes.wintypes.DWORD)]
            class BITMAPINFO2(ctypes.Structure):
                _fields_=[('bmiHeader',BITMAPINFOHEADER2),('bmiColors',ctypes.c_uint32*3)]
            bmi=BITMAPINFO2(); bmi.bmiHeader.biSize=ctypes.sizeof(BITMAPINFOHEADER2)
            bmi.bmiHeader.biWidth=w; bmi.bmiHeader.biHeight=-h; bmi.bmiHeader.biPlanes=1
            bmi.bmiHeader.biBitCount=32; bmi.bmiHeader.biCompression=0
            buf=(ctypes.c_ubyte*(w*h*4))()
            if gdi32.GetDIBits(memdc,bmp,0,h,ctypes.byref(buf),ctypes.byref(bmi),0)>0:
                arr=np.frombuffer(buf,dtype=np.uint8).reshape((h,w,4))
                img=cv2.cvtColor(arr,cv2.COLOR_BGRA2BGR)
                gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
                if float(gray.std())>2.0 and float(gray.mean())>1.0:
                    return img
        if bmp:
            try: gdi32.SelectObject(memdc,old); gdi32.DeleteObject(bmp)
            except Exception: pass
        if memdc:
            try: gdi32.DeleteDC(memdc)
            except Exception: pass
        if hwnddc:
            try: user32.ReleaseDC(hwnd,hwnddc)
            except Exception: pass
    except Exception:
        try:
            if hwnddc: user32.ReleaseDC(hwnd,hwnddc)
        except Exception: pass

    # Final fallback: capture the actual visible client rectangle.
    try:
        pt=ctypes.wintypes.POINT(0,0)
        if not user32.ClientToScreen(hwnd,ctypes.byref(pt)): return None
        with mss.mss() as sct:
            shot=np.array(sct.grab({"left":int(pt.x),"top":int(pt.y),"width":int(w),"height":int(h)}))
        return cv2.cvtColor(shot,cv2.COLOR_BGRA2BGR)
    except Exception:
        return None


def screen_region_to_client(region, hwnd):
    """Convert a region selected on the desktop to target-window client coordinates."""
    if not region or len(region) < 4 or int(region[2]) <= 0 or not hwnd:
        return [0, 0, 0, 0]
    ox, oy = window_client_origin(hwnd)
    x, y, w, h = map(int, region)
    return [x - ox, y - oy, w, h]


def find_image_background(path, accuracy, region, hwnd):
    template=cv_image(path)
    if template is None: return None
    screen=grab_window(hwnd)
    if screen is None: return None
    ox=oy=0
    if region and region[2]>0 and region[3]>0:
        x,y,w,h=map(int,region); x=max(0,x); y=max(0,y); w=min(w,screen.shape[1]-x); h=min(h,screen.shape[0]-y)
        if w<=0 or h<=0: return None
        screen=screen[y:y+h,x:x+w]; ox,oy=x,y
    if screen.shape[0]<template.shape[0] or screen.shape[1]<template.shape[1]: return None
    gs=cv2.cvtColor(screen,cv2.COLOR_BGR2GRAY); gt=cv2.cvtColor(template,cv2.COLOR_BGR2GRAY)
    result=cv2.matchTemplate(gs,gt,cv2.TM_CCOEFF_NORMED); _,score,_,loc=cv2.minMaxLoc(result)
    if score<accuracy:return None
    hh,ww=template.shape[:2]
    return score, loc[0]+ox, loc[1]+oy, ww, hh

@dataclass
class Step:
    type: str = "image"
    name: str = ""
    path: str = ""
    wait: float = 0.0
    accuracy: float = 0.80
    region: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    click_mode: str = "center"
    click_x: int = 0
    click_y: int = 0
    enabled: bool = True
    failure_action: str = "retry"  # retry / ignore / goto
    retry_count: int = 3
    retry_delay: float = 1.0
    failure_target: int = 0  # zero-based step index
    events: list[dict] = field(default_factory=list)  # recorded macro events

@dataclass
class Group:
    name: str
    chains: list[str] = field(default_factory=list)

class Signals(QObject):
    event = Signal(str)
    run = Signal(str)
    status = Signal(str)
    finished = Signal()
    recorded = Signal(object)
    step = Signal(int)


def svg_to_png(svg_path: str) -> str | None:
    p = Path(svg_path)
    if not p.exists(): return None
    key = hashlib.sha1((str(p.resolve()) + str(p.stat().st_mtime_ns)).encode()).hexdigest()
    out = SVG_CACHE_DIR / f"{key}.png"
    if out.exists(): return str(out)
    renderer = QSvgRenderer(str(p))
    if not renderer.isValid(): return None
    size = renderer.defaultSize()
    w = clamp(size.width() or 256, 1, 2048); h = clamp(size.height() or 256, 1, 2048)
    img = QImage(w, h, QImage.Format_RGBA8888)
    img.fill(Qt.transparent)
    painter = QPainter(img); renderer.render(painter); painter.end()
    img.save(str(out), "PNG")
    return str(out)


def image_to_qpixmap(path: str, max_size: QSize = QSize(520, 300)) -> QPixmap:
    actual = svg_to_png(path) if str(path).lower().endswith('.svg') else path
    pm = QPixmap(actual) if actual else QPixmap()
    if pm.isNull(): return pm
    return pm.scaled(max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def cv_image(path: str):
    actual = svg_to_png(path) if str(path).lower().endswith('.svg') else path
    if not actual: return None
    return cv2.imread(actual, cv2.IMREAD_COLOR)


def grab_screen(region=None):
    with mss.mss() as sct:
        mon = sct.monitors[1]
        if region and region[2] > 0 and region[3] > 0:
            box = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
        else:
            box = mon
        shot = np.array(sct.grab(box))
        return cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)


def find_image(path, accuracy, region):
    template = cv_image(path)
    if template is None: return None
    screen = grab_screen(region if region[2] > 0 and region[3] > 0 else None)
    if screen.shape[0] < template.shape[0] or screen.shape[1] < template.shape[1]: return None
    gray_s = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    gray_t = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(gray_s, gray_t, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    if score < accuracy: return None
    x = loc[0] + (region[0] if region[2] > 0 and region[3] > 0 else 0)
    y = loc[1] + (region[1] if region[2] > 0 and region[3] > 0 else 0)
    h, w = template.shape[:2]
    return score, x, y, w, h

class RegionSelector(QWidget):
    selected = Signal(object)
    cancelled = Signal()
    def __init__(self, mode='region', parent=None):
        super().__init__(parent)
        self.mode = mode; self.origin = None; self.rubber = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowOpacity(0.25); self.setCursor(Qt.CrossCursor)
        screen = QApplication.primaryScreen().geometry(); self.setGeometry(screen)
        self.setStyleSheet('background:#1c2430;')
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton: return
        self.origin = e.position().toPoint()
        if self.mode == 'region':
            from PySide6.QtWidgets import QRubberBand
            self.rubber = QRubberBand(QRubberBand.Rectangle, self); self.rubber.setGeometry(QRect(self.origin, QSize())); self.rubber.show()
    def mouseMoveEvent(self, e):
        if self.mode == 'region' and self.rubber and self.origin:
            self.rubber.setGeometry(QRect(self.origin, e.position().toPoint()).normalized())
    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton: return
        p = e.position().toPoint(); geo = self.geometry()
        if self.mode == 'click':
            self.selected.emit([geo.x()+p.x(), geo.y()+p.y()]); self.close(); return
        r = QRect(self.origin, p).normalized()
        if r.width() > 3 and r.height() > 3:
            self.selected.emit([geo.x()+r.x(), geo.y()+r.y(), r.width(), r.height()])
        else: self.cancelled.emit()
        self.close()
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape: self.cancelled.emit(); self.close()

class StepEditor(QDialog):
    def __init__(self, step: Step, parent=None):
        super().__init__(parent); self.step = step
        self.setWindowTitle("이미지 매크로 항목 편집"); self.resize(760, 650)
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.preview = QLabel("이미지 없음"); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumSize(420, 250); self.preview.setFrameShape(QFrame.StyledPanel)
        top.addWidget(self.preview, 2)
        info = QFormLayout()
        self.name = QLineEdit(step.name)
        self.wait = QDoubleSpinBox(); self.wait.setRange(0, 3600); self.wait.setDecimals(2); self.wait.setSingleStep(.1); self.wait.setValue(step.wait)
        self.acc = QDoubleSpinBox(); self.acc.setRange(.01, 1.0); self.acc.setDecimals(2); self.acc.setSingleStep(.01); self.acc.setValue(step.accuracy)
        self.click = QComboBox(); self.click.addItems(["이미지 중앙", "직접 지정"]); self.click.setCurrentIndex(0 if step.click_mode=='center' else 1)
        self.cx = QSpinBox(); self.cx.setRange(-10000,10000); self.cx.setValue(step.click_x)
        self.cy = QSpinBox(); self.cy.setRange(-10000,10000); self.cy.setValue(step.click_y)
        info.addRow("이름", self.name); info.addRow("대기시간(초)", self.wait); info.addRow("이미지 정확도", self.acc); info.addRow("클릭 위치", self.click)
        xy = QHBoxLayout(); xy.addWidget(self.cx); xy.addWidget(QLabel(",")); xy.addWidget(self.cy); xyw=QWidget(); xyw.setLayout(xy); info.addRow("상대 위치 X,Y", xyw)
        self.region_label = QLabel(self._region_text()); info.addRow("검색 영역", self.region_label)
        btn_region = QPushButton("화면에서 검색영역 지정")
        btn_click = QPushButton("화면에서 클릭 위치 지정")
        info.addRow(btn_region); info.addRow(btn_click)
        top.addLayout(info, 1); root.addLayout(top)
        pathbox = QHBoxLayout(); self.path = QLineEdit(step.path); self.path.setReadOnly(True); pathbox.addWidget(self.path); root.addLayout(pathbox)
        root.addWidget(QLabel("※ SVG 파일도 미리보기 및 이미지 인식 대상으로 사용할 수 있습니다. SVG는 내부적으로 PNG로 렌더링됩니다."))

        failbox = QGroupBox("이미지 인식 실패 시 동작")
        fl = QGridLayout(failbox)
        self.fail_action = QComboBox(); self.fail_action.addItems(["다시 시도하기", "무시하고 다음 단계", "특정 단계로 이동"])
        action_map = {"retry": 0, "ignore": 1, "goto": 2}
        self.fail_action.setCurrentIndex(action_map.get(getattr(step, 'failure_action', 'retry'), 0))
        self.retry_count = QSpinBox(); self.retry_count.setRange(0, 999); self.retry_count.setValue(getattr(step, 'retry_count', 3))
        self.retry_delay = QDoubleSpinBox(); self.retry_delay.setRange(0, 3600); self.retry_delay.setDecimals(2); self.retry_delay.setSingleStep(.1); self.retry_delay.setValue(getattr(step, 'retry_delay', 1.0))
        self.fail_target = QSpinBox(); self.fail_target.setRange(1, 9999); self.fail_target.setValue(getattr(step, 'failure_target', 0) + 1)
        fl.addWidget(QLabel("실패 시 동작"),0,0); fl.addWidget(self.fail_action,0,1,1,3)
        fl.addWidget(QLabel("다시 시도 횟수"),1,0); fl.addWidget(self.retry_count,1,1)
        fl.addWidget(QLabel("재시도 지연(초)"),1,2); fl.addWidget(self.retry_delay,1,3)
        fl.addWidget(QLabel("이동할 단계 번호"),2,0); fl.addWidget(self.fail_target,2,1)
        fl.addWidget(QLabel("※ 이미지 대기시간 초과 후 적용됩니다. '특정 단계'는 1부터 시작합니다."),3,0,1,4)
        root.addWidget(failbox)
        self.fail_action.currentIndexChanged.connect(self._failure_changed)
        self._failure_changed()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); root.addWidget(buttons)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        btn_region.clicked.connect(self.pick_region); btn_click.clicked.connect(self.pick_click)
        self._update_preview(); self.click.currentIndexChanged.connect(self._click_changed); self._click_changed()
    def _region_text(self):
        r=self.step.region; return "전체 화면" if not r[2] else f"X={r[0]}, Y={r[1]}, W={r[2]}, H={r[3]}"
    def _update_preview(self):
        pm=image_to_qpixmap(self.step.path, QSize(420,250)) if self.step.path else QPixmap()
        self.preview.setPixmap(pm if not pm.isNull() else QPixmap());
        if pm.isNull(): self.preview.setText("미리볼 이미지가 없습니다")
    def _click_changed(self):
        en=self.click.currentIndex()==1; self.cx.setEnabled(en); self.cy.setEnabled(en)
    def pick_region(self):
        self.selector=RegionSelector('region', self); self.selector.selected.connect(self.region_done); self.selector.show()
    def region_done(self, r): self.step.region=list(map(int,r)); self.region_label.setText(self._region_text())
    def pick_click(self):
        self.selector=RegionSelector('click', self); self.selector.selected.connect(self.click_done); self.selector.show()
    def click_done(self, p):
        r=self.step.region
        if r[2]: self.cx.setValue(p[0]-r[0]); self.cy.setValue(p[1]-r[1])
        else: self.cx.setValue(p[0]); self.cy.setValue(p[1])
        self.click.setCurrentIndex(1)
    def _failure_changed(self):
        retry = self.fail_action.currentIndex() == 0
        goto = self.fail_action.currentIndex() == 2
        self.retry_count.setEnabled(retry); self.retry_delay.setEnabled(retry); self.fail_target.setEnabled(goto)
    def accept(self):
        self.step.name=self.name.text().strip() or Path(self.step.path).name
        self.step.wait=self.wait.value(); self.step.accuracy=self.acc.value(); self.step.click_mode='center' if self.click.currentIndex()==0 else 'offset'; self.step.click_x=self.cx.value(); self.step.click_y=self.cy.value()
        self.step.failure_action = ['retry','ignore','goto'][self.fail_action.currentIndex()]
        self.step.retry_count = self.retry_count.value()
        self.step.retry_delay = self.retry_delay.value()
        self.step.failure_target = max(0, self.fail_target.value()-1)
        super().accept()

class RecordingEditorDialog(QDialog):
    """Editor for a recorded macro step. Recording events remain intact while
    execution wait, accuracy and enabled state can be edited like image steps."""
    def __init__(self, step: Step, parent=None):
        super().__init__(parent)
        self.step = step
        self.setWindowTitle("녹화 매크로 항목 편집")
        self.resize(700, 520)
        root = QVBoxLayout(self)

        info = QFormLayout()
        self.name = QLineEdit(step.name)
        self.wait = QDoubleSpinBox(); self.wait.setRange(0, 3600); self.wait.setDecimals(2); self.wait.setSingleStep(.1); self.wait.setValue(step.wait)
        self.acc = QDoubleSpinBox(); self.acc.setRange(.01, 1.0); self.acc.setDecimals(2); self.acc.setSingleStep(.01); self.acc.setValue(step.accuracy)
        self.enabled = QCheckBox("이 매크로 사용")
        self.enabled.setChecked(step.enabled)
        info.addRow("매크로 이름", self.name)
        info.addRow("실행 후 대기(초)", self.wait)
        info.addRow("정확도", self.acc)
        info.addRow("사용 여부", self.enabled)
        root.addLayout(info)

        root.addWidget(QLabel(f"녹화된 클릭 수: {len(step.events)}개"))
        table = QTableWidget(len(step.events), 3)
        table.setHorizontalHeaderLabels(["순서", "좌표", "이전 동작 후 대기(초)"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for i, ev in enumerate(step.events):
            table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            table.setItem(i, 1, QTableWidgetItem(f"({int(ev.get('x',0))}, {int(ev.get('y',0))})"))
            table.setItem(i, 2, QTableWidgetItem(f"{float(ev.get('wait',0)):.4f}"))
        root.addWidget(table, 1)
        root.addWidget(QLabel("※ 녹화된 클릭 순서/좌표는 이 창에서 변경하지 않고, 실행 후 대기·정확도·사용 여부만 편집합니다."))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def accept(self):
        self.step.name = self.name.text().strip() or self.step.name or "녹화 매크로"
        self.step.wait = self.wait.value()
        self.step.accuracy = self.acc.value()
        self.step.enabled = self.enabled.isChecked()
        super().accept()


class MacroWorker(threading.Thread):
    def __init__(self, steps, settings, signals):
        super().__init__(daemon=True); self.steps=[Step(**asdict(x)) for x in steps]; self.settings=settings; self.sig=signals
        self.stop_evt=threading.Event(); self.pause_evt=threading.Event(); self.pause_evt.set(); self.advance_evt=threading.Event(); self.idx=0
        self.step_lock=threading.Lock(); self.step_request=None
        self.mouse=mouse.Controller()
        self.background=bool(self.settings.get("background", False))
        self.target_title=str(self.settings.get("target_title", ""))
        self.target_process=str(self.settings.get("target_process", ""))
        self.target_hwnd=int(self.settings.get("target_hwnd") or 0) or None
    def stop(self): self.stop_evt.set(); self.pause_evt.set(); self.advance_evt.set()
    def pause(self): self.pause_evt.clear()
    def resume(self): self.pause_evt.set(); self.advance_evt.set()
    def next_step(self):
        with self.step_lock:
            self.step_request=('next', self.idx)
        self.advance_evt.set()
    def prev_step(self):
        with self.step_lock:
            self.step_request=('prev', self.idx)
        self.advance_evt.set()
    def _wait(self, sec):
        end=time.monotonic()+max(0,sec/max(.1,float(self.settings['speed'])))
        while time.monotonic()<end and not self.stop_evt.is_set():
            if not self.pause_evt.is_set(): time.sleep(.05); continue
            time.sleep(.02)
    def run(self):
        mode=self.settings['mode']; repeat=self.settings['repeat']; until=time.monotonic()+self.settings['minutes']*60 if mode=='time' else None; count=0
        self.sig.run.emit(f"[{now()}] 재생 시작")
        try:
            while not self.stop_evt.is_set():
                if mode=='count' and count>=repeat: break
                if mode=='time' and until and time.monotonic()>=until: break
                i = 0
                while i < len(self.steps) and not self.stop_evt.is_set():
                    self.idx=i
                    self.sig.step.emit(i)
                    st=self.steps[i]
                    forced_step=False
                    while self.pause_evt.is_set() and not self.stop_evt.is_set():
                        request=None
                        with self.step_lock:
                            request=self.step_request
                            self.step_request=None
                        if request is not None:
                            direction, base_idx=request
                            if direction == 'next':
                                target=min(len(self.steps)-1, base_idx+1)
                            else:
                                target=max(0, base_idx-1)
                            if target != i:
                                i=target
                                self.idx=i
                                self.sig.step.emit(i)
                                st=self.steps[i]
                            # While paused, step navigation ONLY changes the selected
                            # step. It must not resume or execute that step.
                            # The selected step will execute only after the user presses
                            # Resume.
                            continue
                        time.sleep(.05)
                    if self.stop_evt.is_set(): break
                    if not self.pause_evt.is_set() and not forced_step:
                        continue
                    if not st.enabled:
                        i += 1; continue
                    self.sig.run.emit(f"[{now()}] 단계 {i+1}/{len(self.steps)}: {st.name}")
                    next_i = i + 1
                    if st.type=='recording':
                        self.sig.run.emit(f"[{now()}] 녹화 매크로 실행: {st.name} ({len(st.events)}개 동작)")
                        for ev in st.events:
                            while not self.pause_evt.is_set() and not self.stop_evt.is_set(): time.sleep(.05)
                            if self.stop_evt.is_set(): break
                            self._wait(float(ev.get('wait', 0)))
                            x=int(ev.get('x', 0)); y=int(ev.get('y', 0))
                            if self.background:
                                if not self.target_hwnd: self.target_hwnd=find_window_by_title(self.target_title, self.target_process)
                                ox,oy=window_client_origin(self.target_hwnd) if self.target_hwnd else (0,0)
                                if not background_click(self.target_hwnd, x-ox, y-oy):
                                    self.sig.run.emit(f"[{now()}] 백그라운드 클릭 실패: 대상 창을 찾지 못했거나 입력을 받지 않습니다.")
                            else:
                                self.mouse.position=(x,y); self.mouse.click(mouse.Button.left)
                            self.sig.run.emit(f"[{now()}] 클릭 실행: ({int(ev.get('x',0))},{int(ev.get('y',0))})")
                    elif st.type=='image':
                        found=None
                        attempts=0
                        while not self.stop_evt.is_set():
                            deadline=time.monotonic()+max(0,self.settings['image_wait'])
                            found=None
                            while time.monotonic()<=deadline and not self.stop_evt.is_set():
                                while not self.pause_evt.is_set() and not self.stop_evt.is_set(): time.sleep(.05)
                                if self.background:
                                    if not self.target_hwnd: self.target_hwnd=find_window_by_title(self.target_title, self.target_process)
                                    if self.target_hwnd:
                                        client_region=screen_region_to_client(st.region, self.target_hwnd)
                                        found=find_image_background(st.path, st.accuracy, client_region, self.target_hwnd)
                                    else:
                                        client_region=[0,0,0,0]
                                        found=None
                                    if found is None and attempts == 0 and time.monotonic() + 0.1 >= deadline:
                                        self.sig.run.emit(f"[{now()}] 이미지 인식 실패: 대상 창 캡처 또는 정확도 미달 (기준 {st.accuracy:.2f}, 검색영역={client_region})")
                                else:
                                    found=find_image(st.path, st.accuracy, st.region)
                                if found: break
                                time.sleep(.08)
                            if found: break
                            action=getattr(st,'failure_action','retry')
                            if action == 'retry' and attempts < max(0, int(getattr(st,'retry_count',3))):
                                attempts += 1
                                delay=max(0,float(getattr(st,'retry_delay',1.0)))
                                self.sig.run.emit(f"[{now()}] 인식 실패: {st.name} → 재시도 {attempts}/{st.retry_count} ({delay:.2f}초 후)")
                                self._wait(delay)
                                continue
                            if action == 'ignore':
                                self.sig.run.emit(f"[{now()}] 인식 실패: {st.name} → 무시하고 다음 단계로 이동")
                                break
                            if action == 'goto':
                                target=clamp(int(getattr(st,'failure_target',0)), 0, max(0,len(self.steps)-1))
                                self.sig.run.emit(f"[{now()}] 인식 실패: {st.name} → 단계 {target+1}로 이동")
                                next_i=target
                                break
                            self.sig.run.emit(f"[{now()}] 인식 실패: {st.name} → 재시도 횟수 초과, 다음 단계로 이동")
                            break
                        if found:
                            score,x,y,w,h=found
                            cx=x+w//2; cy=y+h//2
                            if st.click_mode=='offset': cx=x+st.click_x; cy=y+st.click_y
                            if self.background:
                                if not self.target_hwnd: self.target_hwnd=find_window_by_title(self.target_title, self.target_process)
                                clicked=background_click(self.target_hwnd, cx, cy)
                                if clicked:
                                    self.sig.run.emit(f"[{now()}] 이미지 인식 성공: {st.name} ({score:.2f}) → 백그라운드 클릭 ({cx},{cy})")
                                else:
                                    self.sig.run.emit(f"[{now()}] 이미지 인식 성공: {st.name} ({score:.2f}) → 백그라운드 클릭 실패 ({cx},{cy})")
                            else:
                                self.mouse.position=(cx,cy); self.mouse.click(mouse.Button.left)
                                self.sig.run.emit(f"[{now()}] 이미지 인식 성공: {st.name} ({score:.2f}) → 클릭 ({cx},{cy})")
                    self._wait(st.wait)
                    i = next_i
                count+=1
                self.sig.run.emit(f"[{now()}] 반복 {count}회 완료")
                if self.stop_evt.is_set(): break
                self._wait(self.settings['cycle_wait'])
        except Exception as e:
            self.sig.run.emit(f"[{now()}] 오류: {e}")
        self.sig.run.emit(f"[{now()}] 재생 종료"); self.sig.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(APP_NAME); self.resize(1460, 980); self.setMinimumSize(1180,760)
        self.steps=[]; self.groups=[]
        self.worker=None
        self._worker_signals=None
        self.playing=False
        self.recording=False
        self.record_listener=None
        self.record_last=0
        self.record_events=[]
        self.current_file=None
        self._clean_chain_snapshot=None
        self.current_step=-1
        self.load_groups()
        self._last_target_hwnd = None
        self._fg_timer = QTimer(self)
        self._fg_timer.timeout.connect(self._track_foreground_window)
        self._fg_timer.start(200)
        self.event_lines=[]; self.run_lines=[]
        self.build_ui()
        self.apply_style()
        # Stylesheet is installed after the widgets are created, so apply the
        # state once more here to guarantee the disabled buttons are rendered
        # correctly on first launch.
        self.update_button_states()
        self.refresh_groups(); self.refresh_image_list(); self.setup_hotkeys()
        self._mark_chain_clean()
        self.log_event("프로그램 준비 완료. 사용할 탭을 선택하고 시작하세요.")
    def setup_hotkeys(self):
        def on_press(key):
            try:
                if key==keyboard.Key.f1: self.start_record()
                elif key==keyboard.Key.f2: self.stop_record()
                elif key==keyboard.Key.f3: self.start_play()
                elif key==keyboard.Key.f4: self.stop_play()
                elif key==keyboard.Key.f5: self.toggle_pause()
            except Exception: pass
        self.hotkey_listener=keyboard.Listener(on_press=on_press); self.hotkey_listener.daemon=True; self.hotkey_listener.start()
    def apply_style(self):
        self.setStyleSheet('''
        QWidget{font-family:"Malgun Gothic";font-size:13px;color:#243447;} QMainWindow{background:#edf3fb;}
        QTabWidget::pane{border:1px solid #cfd9e6;background:#f7faff;} QTabBar::tab{padding:11px 24px;background:#e7eef7;border:1px solid #d3dce8;border-bottom:none;color:#27466f;} QTabBar::tab:selected{background:white;font-weight:700;}
        QGroupBox{border:1px solid #d4deeb;margin-top:12px;padding:12px;background:#f7faff;} QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 6px;color:#31557f;font-weight:700;}
        QPushButton{background:#fff;border:1px solid #c7d3e1;border-radius:3px;padding:8px 13px;} QPushButton:hover{background:#f0f6ff;border-color:#8da9c8;} QPushButton:pressed{background:#e1ecfa;}
        QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox{background:#fff;border:1px solid #c7d3e1;border-radius:3px;padding:6px;} QTableWidget,QListWidget,QTextBrowser{background:white;border:1px solid #c8d3e0;alternate-background-color:#f7faff;}
        QHeaderView::section{background:#e7eef7;padding:8px;border:1px solid #d0dbe8;color:#31557f;font-weight:700;} QCheckBox,QRadioButton{padding:4px;}
        QLabel#title{font-size:18px;font-weight:700;color:#1d416b;} QLabel#hint{color:#60738a;}
        QPushButton#blueAction{background:#e5f0ff;color:#174a8b;font-weight:700;border:1px solid #9dbde6;}
        QPushButton#greenAction{background:#e7f5ea;color:#176b2c;font-weight:700;border:1px solid #9bcda5;}
        QPushButton#redAction{background:#fff0f0;color:#b32626;font-weight:700;border:1px solid #e1aaaa;}
        QPushButton#stepAction{font-weight:700;}

        /* Disabled state must be visibly grey, not merely unclickable.
           These selectors intentionally have the same ID specificity as the
           coloured action buttons so their disabled grey appearance wins. */
        QPushButton:disabled,
        QPushButton#blueAction:disabled,
        QPushButton#greenAction:disabled,
        QPushButton#redAction:disabled,
        QPushButton#stepAction:disabled{
            background:#e2e2e2;
            color:#666666;
            border:1px solid #c8c8c8;
        }
        QPushButton:disabled:hover,
        QPushButton#blueAction:disabled:hover,
        QPushButton#greenAction:disabled:hover,
        QPushButton#redAction:disabled:hover,
        QPushButton#stepAction:disabled:hover,
        QPushButton:disabled:pressed,
        QPushButton#blueAction:disabled:pressed,
        QPushButton#greenAction:disabled:pressed,
        QPushButton#redAction:disabled:pressed,
        QPushButton#stepAction:disabled:pressed{
            background:#e2e2e2;
            color:#666666;
            border:1px solid #c8c8c8;
        }
        ''')
    def log_box(self, title, kind):
        box=QGroupBox(title); lay=QVBoxLayout(box); w=QTextBrowser(); w.setOpenExternalLinks(False); lay.addWidget(w); setattr(self,kind,w); return box
    def build_ui(self):
        central=QWidget(); self.setCentralWidget(central); root=QVBoxLayout(central); root.setContentsMargins(8,8,8,8)
        tabs=QTabWidget(); root.addWidget(tabs)
        tabs.addTab(self.chain_tab(),'매크로 체인'); tabs.addTab(self.group_tab(),'매크로 그룹'); tabs.addTab(self.image_tab(),'이미지 매크로'); tabs.addTab(self.help_tab(),'도움말')
    def chain_tab(self):
        page=QWidget(); lay=QVBoxLayout(page)
        bar=QHBoxLayout(); title=QLabel('ShadeLawcro V1.0 이미지 매크로'); title.setObjectName('title'); bar.addWidget(title); bar.addStretch()
        self.rec_start_btn=QPushButton('녹화 시작 (F1)'); self.rec_start_btn.clicked.connect(self.start_record)
        self.rec_stop_btn=QPushButton('녹화 중지 (F2)'); self.rec_stop_btn.clicked.connect(self.stop_record)
        self.play_start_btn=QPushButton('재생 시작 (F3)'); self.play_start_btn.clicked.connect(self.start_play)
        self.pause_btn=QPushButton('일시정지 (F5)'); self.pause_btn.clicked.connect(self.toggle_pause)
        self.play_stop_btn=QPushButton('재생 중지 (F4)'); self.play_stop_btn.clicked.connect(self.stop_play)
        self.prev_btn=QPushButton('◀ 이전 단계'); self.prev_btn.clicked.connect(self.prev_step)
        self.next_btn=QPushButton('다음 단계 ▶'); self.next_btn.clicked.connect(self.next_step)
        # Keep the three control groups visually separated:
        # [Record Start / Record Stop] | [Play Start / Pause / Play Stop] | [Previous / Next]
        record_group=QHBoxLayout(); record_group.setSpacing(6)
        play_group=QHBoxLayout(); play_group.setSpacing(6)
        step_group=QHBoxLayout(); step_group.setSpacing(6)
        for b in (self.rec_start_btn,self.rec_stop_btn):
            b.setMinimumHeight(36); record_group.addWidget(b)
        for b in (self.play_start_btn,self.pause_btn,self.play_stop_btn):
            b.setMinimumHeight(36); play_group.addWidget(b)
        for b in (self.prev_btn,self.next_btn):
            b.setMinimumHeight(36); step_group.addWidget(b)
        bar.addLayout(record_group)
        bar.addSpacing(12)
        sep1=QFrame(); sep1.setFrameShape(QFrame.VLine); sep1.setFrameShadow(QFrame.Sunken); bar.addWidget(sep1)
        bar.addSpacing(12)
        bar.addLayout(play_group)
        bar.addSpacing(12)
        sep2=QFrame(); sep2.setFrameShape(QFrame.VLine); sep2.setFrameShadow(QFrame.Sunken); bar.addWidget(sep2)
        bar.addSpacing(12)
        bar.addLayout(step_group)
        bar.addStretch()
        self.update_button_states()
        lay.addLayout(bar)
        upper=QHBoxLayout()
        filebox=QGroupBox('체인 파일'); fl=QVBoxLayout(filebox)
        for text,slot in [('불러오기',self.load_chain),('저장',self.save_chain),('다른 이름으로...',self.save_chain_as)]:
            b=QPushButton(text); b.clicked.connect(slot); fl.addWidget(b)
        fl.addStretch(); upper.addWidget(filebox,0)
        editbox=QGroupBox('매크로 체인 편집기 (재생 목록)'); el=QVBoxLayout(editbox)
        self.table=QTableWidget(0,6); self.table.setHorizontalHeaderLabels(['매크로','실행 후 대기(초)','정확도','검색 영역','클릭 위치','사용']); self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setAlternatingRowColors(True); self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        for c in range(1,6): self.table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(self.edit_selected); self.table.itemSelectionChanged.connect(self._table_selection_changed); el.addWidget(self.table)
        btns=QHBoxLayout();
        for text,slot in [('이미지 추가',self.add_image),('편집',self.edit_selected),('제거',self.remove_selected),('▲',self.move_up),('▼',self.move_down),('모두 삭제',self.clear_all)]:
            b=QPushButton(text); b.clicked.connect(slot); btns.addWidget(b)
        el.addLayout(btns); upper.addWidget(editbox,6)
        playbox=QGroupBox('재생 설정'); pl=QFormLayout(playbox)
        self.r_inf=QRadioButton('무한 반복'); self.r_count=QRadioButton('횟수'); self.r_time=QRadioButton('시간(분)'); self.r_inf.setChecked(True)
        rr=QHBoxLayout(); rr.addWidget(self.r_inf); rr.addWidget(self.r_count); rr.addWidget(self.r_time); rw=QWidget(); rw.setLayout(rr); pl.addRow('반복 방식',rw)
        self.repeat=QSpinBox(); self.repeat.setRange(1,999999); self.repeat.setValue(1); pl.addRow('횟수',self.repeat)
        self.minutes=QDoubleSpinBox(); self.minutes.setRange(.1,999999); self.minutes.setValue(10); self.minutes.setSuffix(' 분'); pl.addRow('시간',self.minutes)
        self.cycle_wait=QDoubleSpinBox(); self.cycle_wait.setRange(0,3600); self.cycle_wait.setDecimals(2); pl.addRow('전체 반복 대기(초)',self.cycle_wait)
        self.speed=QComboBox(); self.speed.addItems(['1.0x','1.2x','1.5x','2.0x','3.0x','5.0x']); pl.addRow('재생 속도',self.speed)
        self.image_wait=QDoubleSpinBox(); self.image_wait.setRange(.1,3600); self.image_wait.setDecimals(2); self.image_wait.setValue(10); pl.addRow('이미지 대기(초)',self.image_wait)
        self.default_acc=QDoubleSpinBox(); self.default_acc.setRange(.01,1); self.default_acc.setDecimals(2); self.default_acc.setValue(.80); pl.addRow('기본 이미지 정확도',self.default_acc)
        self.background_mode=QCheckBox('비활성(백그라운드) 입력 모드'); pl.addRow('입력 방식',self.background_mode)
        targetrow=QHBoxLayout(); self.target_title=QLineEdit(); self.target_title.setPlaceholderText('창 이름(제목)'); targetrow.addWidget(self.target_title)
        self.select_target_btn=QPushButton('창 선택...'); self.select_target_btn.clicked.connect(self.select_target_window); targetrow.addWidget(self.select_target_btn); self.pick_target_btn=QPushButton('현재 창 가져오기'); self.pick_target_btn.clicked.connect(self.pick_target_window); targetrow.addWidget(self.pick_target_btn)
        tw=QWidget(); tw.setLayout(targetrow); pl.addRow('창 이름',tw)
        self.target_process=QLineEdit(); self.target_process.setPlaceholderText('프로세스 이름 예: Game.exe'); pl.addRow('프로세스 이름',self.target_process)
        self.target_status=QLabel('대상 창: 아직 선택되지 않음'); self.target_status.setStyleSheet('color:#666;font-weight:700;'); pl.addRow('선택 상태',self.target_status)
        pl.addRow(QLabel('※ 비활성 모드는 실제 마우스를 움직이지 않고 Windows 백그라운드 메시지를 대상 창으로 보냅니다. 대상 프로그램이 이를 지원하지 않을 수 있습니다.'))
        upper.addWidget(playbox,4); lay.addLayout(upper,3)
        logs=QHBoxLayout()
        event_box=self.log_box('이벤트 로그','event_log')
        run_box=self.log_box('실행 로그','run_log')
        event_col=QVBoxLayout(); event_col.addWidget(event_box)
        run_col=QVBoxLayout(); run_col.addWidget(run_box)
        self.clear_event_btn=QPushButton('이벤트 로그 지우기'); self.clear_event_btn.clicked.connect(self.clear_event_log); event_col.addWidget(self.clear_event_btn)
        self.clear_run_btn=QPushButton('실행 로그 지우기'); self.clear_run_btn.clicked.connect(self.clear_run_log); run_col.addWidget(self.clear_run_btn)
        ew=QWidget(); ew.setLayout(event_col); rw=QWidget(); rw.setLayout(run_col)
        logs.addWidget(ew,1); logs.addWidget(rw,1); lay.addLayout(logs,1)
        return page
    def group_tab(self):
        page=QWidget(); lay=QHBoxLayout(page)
        left=QGroupBox('매크로 그룹'); ll=QVBoxLayout(left); self.group_list=QListWidget(); ll.addWidget(self.group_list)
        for t,s in [('그룹 추가',self.add_group),('이름 변경',self.rename_group),('그룹 삭제',self.delete_group),('선택 그룹 재생',self.play_group)]: b=QPushButton(t); b.clicked.connect(s); ll.addWidget(b)
        lay.addWidget(left,1)
        right=QGroupBox('그룹 구성'); rl=QVBoxLayout(right); self.group_chain_list=QListWidget(); rl.addWidget(self.group_chain_list)
        for t,s in [('체인 추가',self.add_chain_to_group),('선택 체인 제거',self.remove_chain_from_group),('체인 불러오기',self.load_group_chain)]: b=QPushButton(t); b.clicked.connect(s); rl.addWidget(b)
        lay.addWidget(right,2); self.group_list.currentRowChanged.connect(self.refresh_group_chains); return page
    def image_tab(self):
        page=QWidget(); lay=QHBoxLayout(page)
        left=QGroupBox('이미지 라이브러리'); ll=QVBoxLayout(left); self.image_list=QListWidget(); ll.addWidget(self.image_list)
        for t,s in [('이미지 가져오기',self.import_image),('선택 이미지 미리보기',self.preview_image),('파일에서 열기',self.import_image),('선택 삭제',self.delete_image)]: b=QPushButton(t); b.clicked.connect(s); ll.addWidget(b)
        lay.addWidget(left,1)
        right=QGroupBox('SVG / 이미지 미리보기'); rl=QVBoxLayout(right); self.image_preview=QLabel('이미지를 선택하세요'); self.image_preview.setAlignment(Qt.AlignCenter); self.image_preview.setFrameShape(QFrame.StyledPanel); rl.addWidget(self.image_preview,1); self.image_info=QLabel(''); self.image_info.setObjectName('hint'); rl.addWidget(self.image_info); lay.addWidget(right,2)
        self.image_list.currentRowChanged.connect(self.preview_image); self.image_list.itemDoubleClicked.connect(lambda _: self.add_library_to_chain()); return page
    def help_tab(self):
        page=QWidget(); lay=QVBoxLayout(page); tb=QTextBrowser(); tb.setHtml('''<h2>ShadeLawcro V1.0 이미지 매크로</h2><p>Law의 비활성(백그라운드) 이미지 매크로 V1.0 프로토타입입니다.</p><h3>핵심 기능</h3><ul><li>F1/F2 녹화, F3/F4 재생, F5 일시정지</li><li>이미지 항목 더블클릭 → SVG/PNG/JPG 미리보기, 정확도, 검색영역, 클릭 위치, 대기시간 편집</li><li>검색영역은 화면에서 드래그 지정</li><li>클릭 위치는 이미지 중앙 또는 화면에서 직접 지정</li><li>매크로 그룹 및 이미지 라이브러리</li><li>JSON 기반 .pchain 저장</li></ul><p>게임에서 해당 프로그램을 사용하는 경우 해당 서비스의 운영정책을 확인하세요. 해당 프로그램 사용으로 인해 발생되는 문제는 책임지지 않으니 꼭 확인하시기 바랍니다.</p>'''); lay.addWidget(tb); return page
    def log_event(self,msg): self.event_lines.append(msg); self.event_log.append(msg); self.event_log.verticalScrollBar().setValue(self.event_log.verticalScrollBar().maximum())
    def runlog(self,msg): self.run_lines.append(msg); self.run_log.append(msg); self.run_log.verticalScrollBar().setValue(self.run_log.verticalScrollBar().maximum())
    def _table_selection_changed(self):
        if not hasattr(self, 'table'): return
        r=self.table.currentRow()
        if r >= 0 and not self.playing:
            self.current_step = r

    def clear_event_log(self):
        self.event_lines.clear()
        self.event_log.clear()

    def clear_run_log(self):
        self.run_lines.clear()
        self.run_log.clear()

    def highlight_step(self, index):
        if not hasattr(self, 'table') or index < 0 or index >= self.table.rowCount():
            return
        self.current_step = index
        self.table.setCurrentCell(index, 0)
        self.table.selectRow(index)
        item = self.table.item(index, 0)
        if item:
            self.table.scrollToItem(item, QAbstractItemView.PositionAtCenter)

    def clear_step_highlight(self):
        self.current_step = -1
        if hasattr(self, 'table'):
            self.table.clearSelection()
            self.table.setCurrentItem(None)

    def refresh_table(self):
        self.table.setRowCount(len(self.steps))
        for i, st in enumerate(self.steps):
            if st.type == 'recording':
                vals=[f'🎬 {st.name} ({len(st.events)}개 클릭)', f'{st.wait:.2f}', f'{st.accuracy:.2f}', '녹화 매크로', '순서대로 클릭', ('예' if st.enabled else '아니오')]
            else:
                vals=[st.name, f'{st.wait:.2f}', f'{st.accuracy:.2f}', ('전체 화면' if not st.region[2] else f'{st.region[0]},{st.region[1]} {st.region[2]}x{st.region[3]}'), ('중앙' if st.click_mode=='center' else f'{st.click_x},{st.click_y}'), ('예' if st.enabled else '아니오')]
            for j,v in enumerate(vals): self.table.setItem(i,j,QTableWidgetItem(v))
        if 0 <= self.current_step < len(self.steps):
            self.table.selectRow(self.current_step)

    def add_image(self):
        files,_=QFileDialog.getOpenFileNames(self,'이미지 추가',str(TEMPLATE_DIR),'Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg)')
        for f in files:
            dest=TEMPLATE_DIR/Path(f).name
            if Path(f).resolve()!=dest.resolve():
                try: shutil.copy2(f,dest)
                except Exception: dest=Path(f)
            self.steps.append(Step(name=Path(dest).stem,path=str(dest),accuracy=self.default_acc.value()))
            self.log_event(f'[{now()}] 이미지 추가: {Path(dest).name}')
        self.refresh_table()
    def import_image(self):
        files,_=QFileDialog.getOpenFileNames(self,'이미지 라이브러리로 가져오기',str(TEMPLATE_DIR),'Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg)')
        for f in files:
            dest=TEMPLATE_DIR/Path(f).name
            if Path(f).resolve()!=dest.resolve():
                try: shutil.copy2(f,dest)
                except Exception: pass
        self.refresh_image_list()
    def refresh_image_list(self):
        self.image_list.clear()
        for p in sorted(TEMPLATE_DIR.iterdir()):
            if p.suffix.lower() in ('.png','.jpg','.jpeg','.bmp','.webp','.svg'): self.image_list.addItem(str(p))
    def preview_image(self):
        row=self.image_list.currentRow()
        if row<0: return
        p=self.image_list.item(row).text(); pm=image_to_qpixmap(p,QSize(720,520)); self.image_preview.setPixmap(pm); self.image_info.setText(f'{p}  |  {Path(p).suffix.lower()}  |  {Path(p).stat().st_size/1024:.1f} KB')
    def add_library_to_chain(self):
        row=self.image_list.currentRow()
        if row<0: return
        p=self.image_list.item(row).text()
        self.steps.append(Step(name=Path(p).stem,path=p,accuracy=self.default_acc.value()))
        self.refresh_table()
        self.log_event(f'[{now()}] 이미지 라이브러리 항목을 체인에 추가: {Path(p).name}')

    def delete_image(self):
        row=self.image_list.currentRow()
        if row<0:return
        p=Path(self.image_list.item(row).text())
        if QMessageBox.question(self,'삭제',f'{p.name}을(를) 삭제할까요?')==QMessageBox.Yes:
            try:p.unlink()
            except:pass
            self.refresh_image_list()
    def edit_selected(self,*_):
        r=self.table.currentRow()
        if r<0 or r>=len(self.steps): return
        if self.steps[r].type=='recording':
            d=RecordingEditorDialog(self.steps[r], self)
        else:
            d=StepEditor(self.steps[r],self)
        if d.exec()==QDialog.Accepted:
            self.log_event(f'[{now()}] 항목 편집: {self.steps[r].name}'); self.refresh_table()
    def remove_selected(self):
        rows=sorted({x.row() for x in self.table.selectedIndexes()},reverse=True)
        for r in rows:
            if 0<=r<len(self.steps): self.log_event(f'[{now()}] 항목 제거: {self.steps[r].name}'); self.steps.pop(r)
        self.refresh_table()
    def move_up(self):
        r=self.table.currentRow()
        if r>0:
            self.steps[r-1],self.steps[r]=self.steps[r],self.steps[r-1]
            self.refresh_table(); self.table.selectRow(r-1)
            self.current_step = r-1 if self.current_step == r else self.current_step
    def move_down(self):
        r=self.table.currentRow()
        if 0<=r<len(self.steps)-1:
            self.steps[r+1],self.steps[r]=self.steps[r],self.steps[r+1]
            self.refresh_table(); self.table.selectRow(r+1)
            self.current_step = r+1 if self.current_step == r else self.current_step
    def clear_all(self):
        if not self.steps:return
        if QMessageBox.question(self,'모두 삭제','현재 체인을 모두 삭제할까요?')==QMessageBox.Yes: self.steps.clear(); self.refresh_table(); self.log_event(f'[{now()}] 매크로 체인 모두 삭제')
    def _chain_snapshot(self):
        """Return a stable representation of the current macro chain and settings."""
        try:
            return json.dumps(self.chain_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            return None

    def _mark_chain_clean(self):
        self._clean_chain_snapshot = self._chain_snapshot()

    def _has_unsaved_changes(self):
        return self._chain_snapshot() != self._clean_chain_snapshot

    def chain_payload(self):
        if self.r_count.isChecked(): mode='count'
        elif self.r_time.isChecked(): mode='time'
        else: mode='infinite'
        return {'version':'5.2','steps':[asdict(x) for x in self.steps],'settings':{'mode':mode,'repeat':self.repeat.value(),'minutes':self.minutes.value(),'cycle_wait':self.cycle_wait.value(),'speed':self.speed.currentText().replace('x',''),'image_wait':self.image_wait.value(),'default_acc':self.default_acc.value(),'background':self.background_mode.isChecked(),'target_title':self.target_title.text().strip(),'target_process':self.target_process.text().strip(),'target_hwnd':getattr(self,'_last_target_hwnd',None)}}
    def apply_payload(self,data):
        self.steps=[Step(**x) for x in data.get('steps',[])]
        s=data.get('settings',{}); mode=s.get('mode','infinite'); self.r_inf.setChecked(mode=='infinite'); self.r_count.setChecked(mode=='count'); self.r_time.setChecked(mode=='time'); self.repeat.setValue(int(s.get('repeat',1))); self.minutes.setValue(float(s.get('minutes',10))); self.cycle_wait.setValue(float(s.get('cycle_wait',0))); self.speed.setCurrentText(str(s.get('speed','1.0'))+'x'); self.image_wait.setValue(float(s.get('image_wait',10))); self.default_acc.setValue(float(s.get('default_acc',.8))); self.background_mode.setChecked(bool(s.get('background',False))); self.target_title.setText(str(s.get('target_title',''))); self.target_process.setText(str(s.get('target_process',''))); self.refresh_table()
    def save_chain(self):
        if not self.current_file:return self.save_chain_as()
        Path(self.current_file).write_text(json.dumps(self.chain_payload(),ensure_ascii=False,indent=2),encoding='utf-8'); self._mark_chain_clean(); self.log_event(f'[{now()}] 체인 저장 완료: {Path(self.current_file).name}')
    def save_chain_as(self):
        f,_=QFileDialog.getSaveFileName(self,'체인 저장',str(APP_DIR/'새 매크로.pchain'),'PChain (*.pchain);;JSON (*.json)')
        if f:self.current_file=f; self.save_chain()
    def load_chain(self):
        f,_=QFileDialog.getOpenFileName(self,'체인 불러오기',str(APP_DIR),'PChain (*.pchain *.json)')
        if not f:return
        try:self.apply_payload(json.loads(Path(f).read_text(encoding='utf-8'))); self.current_file=f; self._mark_chain_clean(); self.log_event(f'[{now()}] 체인 불러오기 완료: {Path(f).name}')
        except Exception as e: QMessageBox.critical(self,'불러오기 실패',str(e))
    def _style_action_buttons(self):
        for b in (self.rec_start_btn, self.play_start_btn, self.pause_btn): b.setObjectName('blueAction')
        self.pause_btn.setObjectName('greenAction')
        for b in (self.rec_stop_btn, self.play_stop_btn): b.setObjectName('redAction')
        for b in (self.prev_btn, self.next_btn): b.setObjectName('stepAction')
        # Re-polish after objectName changes.
        for b in (self.rec_start_btn,self.rec_stop_btn,self.play_start_btn,self.pause_btn,self.play_stop_btn,self.prev_btn,self.next_btn):
            self.style().unpolish(b); self.style().polish(b); b.update()

    def update_button_states(self):
        """Synchronize the toolbar's enabled/disabled state with the macro state."""
        if not hasattr(self, 'rec_start_btn'):
            return

        recording = bool(self.recording)
        playing = bool(self.playing)
        paused = bool(playing and self.worker and getattr(self.worker, '_paused', False))

        # Initial state: record/play/previous/next are usable; stop/pause are greyed out.
        # While recording: only Record Stop is enabled among record controls.
        # While playing: Play Start is disabled; Pause and Play Stop are enabled.
        self.rec_start_btn.setEnabled(not recording and not playing)
        self.rec_stop_btn.setEnabled(recording)
        self.play_start_btn.setEnabled(not recording and not playing)
        self.pause_btn.setEnabled(playing)
        self.play_stop_btn.setEnabled(playing)

        # Previous/Next are intentionally always enabled, matching the requested UI.
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)

        self.pause_btn.setText('재개 (F5)' if paused else '일시정지 (F5)')
        self._style_action_buttons()


    def start_record(self):
        if self.recording or (self.worker and self.worker.is_alive()): return
        self.recording=True; self.record_last=time.monotonic(); self.record_events=[]
        self.log_event(f'[{now()}] 녹화 시작')
        self.update_button_states()
        def on_click(x,y,button,pressed):
            if not self.recording or not pressed or button!=mouse.Button.left:return
            elapsed=time.monotonic()-self.record_last; self.record_last=time.monotonic()
            wait=elapsed if self.record_events else 0.0
            self.record_events.append({'x':int(x),'y':int(y),'wait':round(wait,4)})
            self.log_event(f'[{now()}] 녹화 중 클릭: ({int(x)},{int(y)}) / 이전 클릭 후 {wait:.2f}s')
        self.record_listener=mouse.Listener(on_click=on_click); self.record_listener.daemon=True; self.record_listener.start()

    def stop_record(self):
        if not self.recording:return
        self.recording=False
        try:
            if self.record_listener: self.record_listener.stop()
        except: pass
        self.record_listener=None
        events=list(getattr(self,'record_events',[]))
        if events:
            name=f'녹화_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
            self.steps.append(Step(type='recording', name=name, wait=0, accuracy=self.default_acc.value(), events=events))
            self.refresh_table()
            self.log_event(f'[{now()}] 녹화 중지 → 하나의 녹화 매크로로 추가 ({len(events)}개 클릭)')
        else:
            self.log_event(f'[{now()}] 녹화 중지 → 녹화된 동작 없음')
        self.record_events=[]
        self.update_button_states()

    def foreground_window_title_for(self, hwnd):
        if os.name != 'nt' or not hwnd: return ''
        user32=ctypes.windll.user32; n=user32.GetWindowTextLengthW(hwnd)
        buf=ctypes.create_unicode_buffer(n+1); user32.GetWindowTextW(hwnd, buf, n+1); return buf.value

    def _track_foreground_window(self):
        if os.name != 'nt': return
        try:
            # Once the user explicitly selected a target window, never replace it
            # merely because the macro application's own window became foreground.
            # Previously this silently changed MabinogiMobile -> Whale and caused
            # background playback to capture/click the wrong window.
            current=int(getattr(self, '_last_target_hwnd', 0) or 0)
            if current and ctypes.windll.user32.IsWindow(current):
                return
            hwnd=int(ctypes.windll.user32.GetForegroundWindow())
            own=int(self.winId())
            if hwnd and hwnd != own and ctypes.windll.user32.IsWindowVisible(hwnd):
                self._last_target_hwnd=hwnd
        except Exception:
            pass

    def _set_target_status(self, ok, text):
        if hasattr(self, 'target_status'):
            self.target_status.setText(text)
            self.target_status.setStyleSheet('color:#176b2c;font-weight:700;' if ok else 'color:#b32626;font-weight:700;')

    def select_target_window(self):
        """Open a reliable window picker. Selecting a row immediately stores the HWND."""
        if os.name != 'nt':
            QMessageBox.warning(self, '대상 창', 'Windows에서만 사용할 수 있습니다.')
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton, QLabel, QMessageBox
        from PySide6.QtCore import Qt

        dlg = QDialog(self)
        dlg.setWindowTitle('대상 창 선택')
        dlg.resize(900, 600)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel('목록에서 대상 프로그램의 창을 클릭하세요. 선택한 창은 아래 상태에 즉시 표시됩니다.'))

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(['창 이름', '프로세스', 'HWND'])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        lay.addWidget(table, 1)

        selected = {'hwnd': None, 'title': '', 'proc': ''}

        def load_rows(preferred=None):
            table.setRowCount(0)
            rows = list_visible_windows()
            for hwnd, title, proc in rows:
                r = table.rowCount()
                table.insertRow(r)
                table.setItem(r, 0, QTableWidgetItem(title))
                table.setItem(r, 1, QTableWidgetItem(proc or '(읽기 실패)'))
                table.setItem(r, 2, QTableWidgetItem(str(hwnd)))
                table.item(r, 0).setData(Qt.UserRole, int(hwnd))
            if preferred:
                for r in range(table.rowCount()):
                    if int(table.item(r, 0).data(Qt.UserRole)) == int(preferred):
                        table.selectRow(r)
                        table.scrollToItem(table.item(r, 0))
                        break

        def capture_row(row):
            if row < 0 or row >= table.rowCount():
                return
            item = table.item(row, 0)
            if item is None:
                return
            hwnd = int(item.data(Qt.UserRole))
            if not ctypes.windll.user32.IsWindow(hwnd):
                self._set_target_status(False, '✗ 선택한 창이 더 이상 존재하지 않습니다.')
                return
            title = table.item(row, 0).text()
            proc = table.item(row, 1).text()
            if proc == '(읽기 실패)':
                proc = window_process_name(hwnd)
            selected.update(hwnd=hwnd, title=title, proc=proc)
            # IMPORTANT: apply immediately, not after dlg.exec().
            self._last_target_hwnd = hwnd
            self._target_window_locked = True
            self.target_title.setText(title)
            self.target_process.setText(proc)
            self._set_target_status(True, f'✓ 선택됨: {title}  [{proc or "프로세스명 읽기 실패"}]')
            self.log_event(f'[{now()}] 대상 창 선택: HWND={hwnd}, 창={title}, 프로세스={proc}')

        load_rows(getattr(self, '_last_target_hwnd', None))
        table.cellClicked.connect(lambda row, col: capture_row(row))
        table.cellDoubleClicked.connect(lambda row, col: (capture_row(row), dlg.accept()))

        btnrow = QHBoxLayout(); btnrow.addStretch()
        refresh = QPushButton('새로고침')
        ok = QPushButton('선택 완료')
        cancel = QPushButton('취소')
        btnrow.addWidget(refresh); btnrow.addWidget(ok); btnrow.addWidget(cancel)
        lay.addLayout(btnrow)

        refresh.clicked.connect(lambda: load_rows(selected['hwnd'] or getattr(self, '_last_target_hwnd', None)))
        ok.clicked.connect(lambda: dlg.accept() if selected['hwnd'] else QMessageBox.warning(dlg, '대상 창 선택', '먼저 목록에서 대상 창을 클릭하세요.'))
        cancel.clicked.connect(dlg.reject)

        # Do not require the dialog's return code to commit the selection: capture_row already did it.
        dlg.exec()

        if selected['hwnd']:
            hwnd = int(selected['hwnd'])
            title = selected['title'] or self.foreground_window_title_for(hwnd)
            proc = selected['proc'] or window_process_name(hwnd)
            self._last_target_hwnd = hwnd
            self.target_title.setText(title)
            self.target_process.setText(proc)
            self._set_target_status(True, f'✓ 선택됨: {title}  [{proc or "프로세스명 읽기 실패"}]')
            QMessageBox.information(self, '대상 창 선택 완료', f'대상 창이 선택되었습니다.\n\n창 이름: {title}\n프로세스: {proc or "읽지 못함"}\nHWND: {hwnd}')

    def pick_target_window(self):
        hwnd=self._last_target_hwnd
        title_filter=self.target_title.text().strip(); process_filter=self.target_process.text().strip()
        if title_filter or process_filter: hwnd=find_window_by_title(title_filter, process_filter) or hwnd
        if hwnd:
            title=self.foreground_window_title_for(hwnd); proc=window_process_name(hwnd)
            if not title and not proc:
                self._set_target_status(False, '대상 창 정보를 읽지 못했습니다.')
                QMessageBox.warning(self,'대상 창','선택된 창의 이름/프로세스 정보를 읽지 못했습니다.'); return
            self.target_title.setText(title); self.target_process.setText(proc)
            self._set_target_status(True, f'✓ 대상 창 선택됨: {title}  [{proc or "프로세스명 읽기 실패"}]')
            self.log_event(f'[{now()}] 백그라운드 대상 창 지정: {title} / {proc}')
            QMessageBox.information(self,'대상 창 선택 완료',f'대상 창이 선택되었습니다.\n\n창 이름: {title}\n프로세스: {proc or "읽지 못함"}')
        else:
            self._set_target_status(False, '대상 창을 찾지 못했습니다.')
            QMessageBox.warning(self,'대상 창','대상 창을 찾지 못했습니다.\n\n대상 프로그램을 먼저 활성화한 뒤 이 버튼을 눌러주세요.')

    def settings(self):
        mode='count' if self.r_count.isChecked() else 'time' if self.r_time.isChecked() else 'infinite'; return {'mode':mode,'repeat':self.repeat.value(),'minutes':self.minutes.value(),'cycle_wait':self.cycle_wait.value(),'speed':float(self.speed.currentText().replace('x','')),'image_wait':self.image_wait.value(),'background':self.background_mode.isChecked(),'target_title':self.target_title.text().strip(),'target_process':self.target_process.text().strip(),'target_hwnd':getattr(self,'_last_target_hwnd',None)}
    def next_step(self):
        if not self.steps: return
        if self.current_step < len(self.steps)-1:
            self.highlight_step(self.current_step + 1 if self.current_step >= 0 else 0)
        if self.worker and self.worker.is_alive():
            self.worker.next_step(); self.log_event(f'[{now()}] 다음 단계로 이동')

    def prev_step(self):
        if not self.steps: return
        if self.current_step > 0:
            self.highlight_step(self.current_step - 1)
        elif self.current_step < 0:
            self.highlight_step(0)
        if self.worker and self.worker.is_alive():
            self.worker.prev_step(); self.log_event(f'[{now()}] 이전 단계로 이동')

    def start_play(self):
        # Never fail silently: record the button entry and every early-return reason.
        try:
            self.runlog(f"[{now()}] 재생 시작 버튼 입력")
        except Exception:
            pass
        if self.recording:
            self.runlog(f"[{now()}] 재생 시작 무시: 현재 녹화 중입니다.")
            return
        if self.worker and self.worker.is_alive():
            self.runlog(f"[{now()}] 재생 시작 무시: 기존 재생 스레드가 아직 실행 중입니다.")
            return
        if not self.steps:
            self.runlog(f"[{now()}] 재생 시작 실패: 재생할 매크로가 없습니다.")
            QMessageBox.information(self,'재생','재생할 매크로가 없습니다.')
            return
        settings=self.settings()
        self.runlog(f"[{now()}] 재생 설정 확인: 단계={len(self.steps)}, 백그라운드={settings.get('background')}, 대상HWND={settings.get('target_hwnd')}, 대상창={settings.get('target_title')} [{settings.get('target_process')}]")
        if settings.get('background'):
            hwnd=int(getattr(self,'_last_target_hwnd',0) or 0)
            if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
                hwnd=find_window_by_title(settings.get('target_title',''), settings.get('target_process',''))
            if not hwnd:
                self._set_target_status(False, '✗ 대상 창을 찾지 못했습니다.')
                self.runlog(f'[{now()}] 백그라운드 재생 시작 실패: 대상 HWND가 없습니다.')
                QMessageBox.warning(self,'백그라운드 재생','선택된 대상 창을 찾지 못했습니다.\n\n창 선택에서 대상 창을 다시 선택해주세요.')
                return
            settings['target_hwnd']=int(hwnd)
            title=self.foreground_window_title_for(hwnd); proc=window_process_name(hwnd)
            self._set_target_status(True, f'✓ 재생 대상 확인: {title}  [{proc or "프로세스명 읽기 실패"}]')
            self.log_event(f'[{now()}] 재생 대상 확인: HWND={hwnd}, 창={title}, 프로세스={proc}')
        try:
            # Keep the QObject alive explicitly for the entire worker lifetime.
            self._worker_signals=Signals()
            self.worker=MacroWorker(self.steps,settings,self._worker_signals)
            self.worker._paused=False
            self.playing=True
            self.worker.sig.run.connect(self.runlog)
            self.worker.sig.step.connect(self.highlight_step)
            self.worker.sig.finished.connect(self._play_finished)
            self.runlog(f'[{now()}] 재생 스레드 생성 완료')
            self.update_button_states()
            self.worker.start()
            self.runlog(f'[{now()}] 재생 스레드 시작 완료 (단계 {len(self.steps)}개)')
            self.log_event(f'[{now()}] 재생 시작')
        except Exception as e:
            self.playing=False
            self.runlog(f'[{now()}] 재생 시작 예외: {type(e).__name__}: {e}')
            self.update_button_states()
            QMessageBox.critical(self,'재생 시작 오류',f'재생을 시작하지 못했습니다.\n\n{type(e).__name__}: {e}')

    def _play_finished(self):
        self.playing=False
        self.clear_step_highlight()
        self.runlog(f'[{now()}] 실행 스레드 종료')
        self.update_button_states()

    def stop_play(self):
        if self.worker and self.worker.is_alive():
            self.worker.stop(); self.log_event(f'[{now()}] 재생 중지 요청')
        self.playing=False
        self.clear_step_highlight()
        if self.worker:
            self.worker._paused=False
        # Always restore the normal Play/Pause button state after Stop.
        self.pause_btn.setText('일시정지 (F5)') if hasattr(self, 'pause_btn') else None
        self.update_button_states()

    def toggle_pause(self):
        if not self.worker or not self.worker.is_alive(): return
        if getattr(self.worker,'_paused',False):
            self.worker._paused=False; self.worker.resume(); self.log_event(f'[{now()}] 재생 재개')
        else:
            self.worker._paused=True; self.worker.pause(); self.log_event(f'[{now()}] 재생 일시정지')
        self.update_button_states()

    @property
    def groups_file(self): return DATA_DIR / 'groups.json'
    def load_groups(self):
        try:
            data=json.loads(self.groups_file.read_text(encoding='utf-8'))
            self.groups=[Group(**x) for x in data]
        except Exception:
            self.groups=[]
    def save_groups(self):
        try: self.groups_file.write_text(json.dumps([asdict(g) for g in self.groups],ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception: pass

    def add_group(self):
        name,ok=QInputDialog.getText(self,'그룹 추가','그룹 이름:') if False else (None,False)
        # keep dependency-free fallback dialog
        d=QDialog(self); d.setWindowTitle('그룹 추가'); l=QVBoxLayout(d); e=QLineEdit(); l.addWidget(e); b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); l.addWidget(b); b.accepted.connect(d.accept); b.rejected.connect(d.reject)
        if d.exec()==QDialog.Accepted and e.text().strip(): self.groups.append(Group(e.text().strip())); self.save_groups(); self.refresh_groups()
    def rename_group(self):
        i=self.group_list.currentRow();
        if i<0:return
        d=QDialog(self); d.setWindowTitle('이름 변경'); l=QVBoxLayout(d); e=QLineEdit(self.groups[i].name); l.addWidget(e); b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); l.addWidget(b); b.accepted.connect(d.accept); b.rejected.connect(d.reject)
        if d.exec()==QDialog.Accepted and e.text().strip(): self.groups[i].name=e.text().strip(); self.save_groups(); self.refresh_groups()
    def delete_group(self):
        i=self.group_list.currentRow();
        if i>=0:self.groups.pop(i); self.save_groups(); self.refresh_groups()
    def refresh_groups(self):
        self.group_list.clear(); self.group_list.addItems([g.name for g in self.groups]); self.refresh_group_chains()
    def refresh_group_chains(self):
        self.group_chain_list.clear(); i=self.group_list.currentRow();
        if i>=0:self.group_chain_list.addItems(self.groups[i].chains)
    def add_chain_to_group(self):
        i=self.group_list.currentRow();
        if i<0:return
        f,_=QFileDialog.getOpenFileName(self,'체인 추가',str(APP_DIR),'PChain (*.pchain *.json)');
        if f:self.groups[i].chains.append(f); self.save_groups(); self.refresh_group_chains()
    def remove_chain_from_group(self):
        gi=self.group_list.currentRow(); ci=self.group_chain_list.currentRow();
        if gi>=0 and ci>=0:self.groups[gi].chains.pop(ci); self.save_groups(); self.refresh_group_chains()
    def load_group_chain(self):
        gi=self.group_list.currentRow(); ci=self.group_chain_list.currentRow();
        if gi<0 or ci<0:return
        f=self.groups[gi].chains[ci]
        try:self.apply_payload(json.loads(Path(f).read_text(encoding='utf-8'))); self.current_file=f; self._mark_chain_clean(); self.log_event(f'[{now()}] 그룹 체인 불러오기: {Path(f).name}')
        except Exception as e: QMessageBox.warning(self,'오류',str(e))
    def play_group(self):
        self.load_group_chain(); self.start_play()
    def closeEvent(self,e):
        if self._has_unsaved_changes():
            answer = QMessageBox.question(
                self,
                '종료 확인',
                '저장되지 않은 변경사항이 있습니다. 저장하지 않고 종료하시겠습니까?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if answer != QMessageBox.Yes:
                e.ignore()
                return
        self.stop_record(); self.stop_play()
        try:self.hotkey_listener.stop()
        except:pass
        e.accept()

# Fix missing import without making it visible in UI
from PySide6.QtWidgets import QInputDialog

if __name__=='__main__':
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); w=MainWindow(); w.show(); sys.exit(app.exec())
