import os
import sys
import subprocess
import shutil
import time
import ctypes
import ctypes.wintypes
from dataclasses import dataclass
from typing import Optional, List, Tuple

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QComboBox, QSpinBox, QScrollArea,
    QGridLayout, QFrame, QMessageBox, QGroupBox
)

APP_NAME = "PandaMirror 20"


def app_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_tool(name):
    root = app_root()
    candidates = [
        os.path.join(root, "tools", name),
        os.path.join(root, "tools", "platform-tools", name),
        os.path.join(root, "tools", "scrcpy", name),
        os.path.join(root, name),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return shutil.which(name)


def run_quiet(args, timeout=6):
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


class Adb:
    def __init__(self):
        self.path = find_tool("adb.exe") or find_tool("adb")

    def devices(self):
        if not self.path:
            return [], "ADB tidak ditemukan. Letakkan adb.exe di tools/platform-tools/ atau pastikan PATH sudah benar."
        rc, out, err = run_quiet([self.path, "devices", "-l"])
        if rc:
            return [], err or "ADB gagal dijalankan."
        rows: List[Tuple[str, str]] = []
        for line in out.splitlines()[1:]:
            bits = line.split()
            if len(bits) >= 2 and bits[1] == "device":
                serial = bits[0]
                detail = " ".join(bits[2:])
                rows.append((serial, detail))
        return rows, ""

    def run(self, serial, args, timeout=10):
        if not self.path:
            return 1, "", "ADB tidak ditemukan"
        cmd = [self.path, "-s", serial] + args
        return run_quiet(cmd, timeout=timeout)

    def shell(self, serial, cmd_string, timeout=10):
        return self.run(serial, ["shell", cmd_string], timeout=timeout)

    def get_size(self, serial):
        rc, out, err = self.shell(serial, "wm size")
        if rc:
            return None
        for line in out.splitlines():
            if "Physical size" in line or "Override size" in line or "size:" in line:
                # e.g. Physical size: 1080x2340
                if "x" in line.lower():
                    part = line.split(":")[-1].strip()
                    if "x" in part.lower():
                        try:
                            width, height = [int(v) for v in part.lower().replace("x", " ").split()[:2]]
                            return width, height
                        except Exception:
                            pass
        return None


@dataclass
class Device:
    serial: str
    detail: str = ""
    selected: bool = True
    mirrored: bool = False
    leader: bool = False
    process: Optional[subprocess.Popen] = None
    screen_w: int = 0
    screen_h: int = 0


class DeviceTile(QFrame):
    selected_changed = Signal(str, bool)
    leader_clicked = Signal(str)
    mirror_clicked = Signal(str, bool)
    status_clicked = Signal(str)

    def __init__(self, device):
        super().__init__()
        self.device = device
        self.serial = device.serial
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { background:#17191d; border:2px solid #1688dc; border-radius:4px; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        self.screen = QWidget(self)
        self.screen.setMinimumSize(140, 220)
        self.screen.setStyleSheet("background:#050505;color:#9aa4b2;border:1px solid #2b2f34;border-radius:4px;")
        self.screen.setObjectName("tileScreen")
        outer.addWidget(self.screen, 1)

        top_bar = QHBoxLayout()
        self.check = QCheckBox(device.serial)
        self.check.setChecked(device.selected)
        self.check.setStyleSheet("color:white;border:0;")
        self.check.toggled.connect(lambda value: self.selected_changed.emit(self.serial, value))
        top_bar.addWidget(self.check, 1)

        self.status = QLabel("Tersambung")
        self.status.setStyleSheet("color:#cbd5e1;border:0;font-size:10px;")
        top_bar.addWidget(self.status)
        outer.addLayout(top_bar)

        buttons = QHBoxLayout()
        self.leader_btn = QPushButton("♟ Leader")
        self.leader_btn.setToolTip("Jadikan HP ini sebagai Leader untuk sinkronisasi input")
        self.leader_btn.clicked.connect(lambda: self.leader_clicked.emit(self.serial))
        buttons.addWidget(self.leader_btn)

        self.mirror_btn = QPushButton("Mirror")
        self.mirror_btn.clicked.connect(lambda: self.mirror_clicked.emit(self.serial, True))
        buttons.addWidget(self.mirror_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(lambda: self.mirror_clicked.emit(self.serial, False))
        buttons.addWidget(self.stop_btn)
        outer.addLayout(buttons)

    def set_leader(self, active):
        self.leader_btn.setText("★ LEADER" if active else "♟ Leader")
        self.leader_btn.setStyleSheet("background:#087ed0;color:white;" if active else "")
        self.setStyleSheet("QFrame { background:#17191d; border:2px solid %s; border-radius:4px; }" % ("#ffbf36" if active else "#1688dc"))

    def set_status(self, text):
        self.status.setText(text)

    def set_screen_text(self, text):
        if self.screen is not None:
            self.screen.setStyleSheet("background:#050505;color:#9aa4b2;border:1px solid #2b2f34;border-radius:4px;font-size:11px;")
            self.screen.setProperty("screenText", text)
            self.screen.setToolTip(text)


class WinApi:
    @staticmethod
    def find_window_by_title(title):
        if os.name != "nt":
            return None
        EnumWindows = ctypes.windll.user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        windows = []

        def callback(hwnd, lparam):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                if buf.value == title:
                    windows.append(hwnd)
                    return False
            return True

        proc = EnumWindowsProc(callback)
        EnumWindows(proc, 0)
        return windows[0] if windows else None

    @staticmethod
    def set_parent(child_hwnd, parent_hwnd):
        if os.name != "nt":
            return
        user32 = ctypes.windll.user32
        user32.SetParent.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HWND]
        user32.SetParent.restype = ctypes.c_int
        user32.SetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowPos.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        style = user32.GetWindowLongW(child_hwnd, -16)
        style = style & ~0x00C00000  # remove WS_CAPTION + WS_THICKFRAME
        user32.SetWindowLongW(child_hwnd, -16, style)
        user32.SetParent(child_hwnd, parent_hwnd)
        user32.SetWindowPos(child_hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1450, 900)
        self.adb = Adb()
        self.devices: dict[str, Device] = {}
        self.leader_serial: Optional[str] = None
        self.scrcpy_path = find_tool("scrcpy.exe") or find_tool("scrcpy")
        self._build_ui()
        self.refresh_devices()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_devices)
        self.timer.start(5000)

    def _build_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#292b2f; color:#f5f7fa; }
            QPushButton { background:#087bc7; color:white; padding:6px 10px; border:0; border-radius:3px; }
            QPushButton:hover { background:#1594e8; }
            QComboBox, QSpinBox { background:#3b3d42; padding:5px; border:1px solid #555; }
            QCheckBox { spacing:6px; }
        """)
        central = QWidget()
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        title = QLabel("PandaMirror 20  |  USB Android multi-mirror")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        top.addWidget(title, 1)
        self.refresh_btn = QPushButton("Refresh perangkat")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        top.addWidget(self.refresh_btn)
        self.start_btn = QPushButton("Mirror perangkat terpilih")
        self.start_btn.clicked.connect(self.start_selected)
        top.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Stop semua")
        self.stop_btn.clicked.connect(self.stop_all)
        top.addWidget(self.stop_btn)
        root.addLayout(top)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Maksimum aktif:"))
        self.max_devices = QSpinBox()
        self.max_devices.setRange(1, 20)
        self.max_devices.setValue(10)
        controls.addWidget(self.max_devices)

        controls.addWidget(QLabel("Resolusi:"))
        self.resolution = QComboBox()
        self.resolution.addItems(["480", "600", "720", "800", "1024"])
        self.resolution.setCurrentText("600")
        controls.addWidget(self.resolution)

        controls.addWidget(QLabel("FPS:"))
        self.fps = QComboBox()
        self.fps.addItems(["10", "15", "20", "30", "45", "60"])
        self.fps.setCurrentText("15")
        controls.addWidget(self.fps)

        self.no_audio = QCheckBox("Matikan audio (lebih ringan)")
        self.no_audio.setChecked(True)
        controls.addWidget(self.no_audio)

        self.show_offline = QCheckBox("Tampilkan perangkat offline")
        self.show_offline.setChecked(True)
        controls.addWidget(self.show_offline)
        controls.addStretch(1)
        root.addLayout(controls)

        self.info = QLabel("Menunggu perangkat…")
        self.info.setStyleSheet("background:#0868ad;padding:7px;")
        root.addWidget(self.info)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.panel = QWidget()
        self.grid = QGridLayout(self.panel)
        self.grid.setSpacing(8)
        self.scroll.setWidget(self.panel)
        root.addWidget(self.scroll, 1)

        note = QLabel(
            "Catatan: versi ini mencoba meng-embed jendela scrcpy ke dalam tile Qt, tetapi implementasi input Leader ke follower tetap memerlukan pengujian perangkat Android nyata di Windows 10 x64."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#ffd479;padding:4px;")
        root.addWidget(note)

        self.setCentralWidget(central)

    def refresh_devices(self):
        rows, error = self.adb.devices()
        if error:
            self.info.setText(error)
            return

        seen = set()
        for serial, detail in rows:
            seen.add(serial)
            if serial not in self.devices:
                self.devices[serial] = Device(serial=serial, detail=detail, selected=True)
            else:
                self.devices[serial].detail = detail

        for serial in list(self.devices.keys()):
            if serial not in seen:
                dev = self.devices[serial]
                if dev.process and dev.process.poll() is None:
                    try:
                        dev.process.terminate()
                    except Exception:
                        pass
                del self.devices[serial]

        self.rebuild_grid()
        active = sum(1 for d in self.devices.values() if d.process and d.process.poll() is None)
        self.info.setText(f"Perangkat online: {len(rows)}  |  Mirror aktif: {active}  |  Leader: {self.leader_serial or 'belum dipilih'}")

    def rebuild_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        online = {serial for serial, _ in self.adb.devices()[0]}
        shown = [d for d in self.devices.values() if (self.show_offline.isChecked() or d.serial in online)]
        self.tiles = {}

        columns = 5
        if len(shown) > 0:
            columns = min(5, max(1, int(len(shown) ** 0.5) + 1))
        for i, dev in enumerate(shown):
            tile = DeviceTile(dev)
            tile.selected_changed.connect(self.set_selected)
            tile.leader_clicked.connect(self.set_leader)
            tile.mirror_clicked.connect(self.toggle_mirror)
            tile.set_leader(dev.serial == self.leader_serial)
            tile.set_status("Mirroring" if dev.process and dev.process.poll() is None else ("Online" if dev.serial in online else "Offline"))
            tile.set_screen_text("Terhubung\n\nKlik Mirror untuk membuka layar")
            self.grid.addWidget(tile, i // columns, i % columns)
            self.tiles[dev.serial] = tile

    def set_selected(self, serial, value):
        if serial in self.devices:
            self.devices[serial].selected = value

    def set_leader(self, serial):
        self.leader_serial = serial
        for d in self.devices.values():
            d.leader = d.serial == serial
        self.rebuild_grid()
        self.info.setText(f"Leader dipilih: {serial}. Input akan diteruskan ke perangkat pengikut yang terpilih.")

    def toggle_mirror(self, serial, start):
        dev = self.devices.get(serial)
        if not dev:
            return
        if start:
            self.start_device(dev)
        else:
            self.stop_device(dev)
        self.rebuild_grid()

    def start_device(self, dev):
        if not self.scrcpy_path:
            QMessageBox.warning(self, "scrcpy tidak ditemukan", "Letakkan scrcpy.exe di folder tools/scrcpy/ atau pastikan PATH benar.")
            return
        if dev.process and dev.process.poll() is None:
            return

        args = [
            self.scrcpy_path,
            "--serial", dev.serial,
            "--max-size", self.resolution.currentText(),
            "--max-fps", self.fps.currentText(),
            "--window-title", f"{dev.serial} - PandaMirror 20",
            "--stay-awake",
        ]
        if self.no_audio.isChecked():
            args.append("--no-audio")
        if dev.serial != self.leader_serial:
            args.append("--no-control")

        try:
            dev.process = subprocess.Popen(
                args,
                cwd=os.path.dirname(self.scrcpy_path),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            QTimer.singleShot(600, lambda: self.attach_scrcpy_window(dev))
        except Exception as exc:
            QMessageBox.warning(self, "Gagal menjalankan scrcpy", str(exc))
            dev.process = None

    def attach_scrcpy_window(self, dev):
        if dev.serial not in self.tiles:
            return
        tile = self.tiles[dev.serial]
        hwnd = WinApi.find_window_by_title(f"{dev.serial} - PandaMirror 20")
        if not hwnd:
            tile.set_screen_text("Menunggu jendela scrcpy…")
            return
        try:
            WinApi.set_parent(hwnd, int(tile.screen.winId()))
            rect = tile.screen.geometry()
            ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, rect.width(), rect.height(), 0x0001 | 0x0002 | 0x0004)
            tile.set_screen_text("Live screen")
        except Exception:
            tile.set_screen_text("Scrcpy aktif\nReparent gagal")

    def start_selected(self):
        selected = [d for d in self.devices.values() if d.selected]
        cap = self.max_devices.value()
        selected = selected[:cap]
        for dev in selected:
            self.start_device(dev)
            time.sleep(0.12)
        self.rebuild_grid()
        self.refresh_devices()

    def stop_device(self, dev):
        if dev.process and dev.process.poll() is None:
            try:
                dev.process.terminate()
            except Exception:
                pass
        dev.process = None

    def stop_all(self):
        for dev in self.devices.values():
            self.stop_device(dev)
        self.leader_serial = None
        self.rebuild_grid()
        self.refresh_devices()

    def closeEvent(self, event):
        self.stop_all()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

