"""主窗口：拖拽加密 / 解压、队列进度、系统托盘、压缩记录。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRectF, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import history as history_mod
from ..core import job, manifest, password, verifier
from ..core.sevenzip import SevenZip, SevenZipNotFound, find_sevenzip
from ..platform_ import autostart
from .dropzone import DropZone
from .ipc import SingleInstance
from .theme import STYLE

EXIT_OK = 0

ARCHIVE_EXTS = (".7z", ".zip", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst", ".cab", ".iso")
SEVEN_SIG = b"7z\xbc\xaf\x27\x1c"


def human_size(size: int) -> str:
    if size <= 0:
        return "—"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return "—"


def looks_like_archive(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(ARCHIVE_EXTS):
        return True
    if path.suffix.lower() in (".exe", ".command", ".run"):
        try:
            size = path.stat().st_size
            with open(path, "rb") as fh:
                head = fh.read(2)
                if path.suffix.lower() == ".exe" and head != b"MZ":
                    return False
                fh.seek(max(0, size - 2 * 1024 * 1024))
                return SEVEN_SIG in fh.read()
        except OSError:
            return False
    return False


def make_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#2563eb"))
    painter.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), size * 0.28, size * 0.28)
    pen = QPen(QColor("#ffffff"), max(2.0, size * 0.075))
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawArc(QRectF(size * 0.30, size * 0.20, size * 0.40, size * 0.40), 0, 180 * 16)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(QRectF(size * 0.27, size * 0.42, size * 0.46, size * 0.36), size * 0.08, size * 0.08)
    painter.end()
    return QIcon(pixmap)


class WorkerSignals(QObject):
    progress = Signal(int, float, str)
    state = Signal(int)
    log = Signal(int, str)
    done = Signal(int)


class TaskRunnable(QRunnable):
    def __init__(self, index: int, task: job.Task, cancel: Event, signals: WorkerSignals):
        super().__init__()
        self.index = index
        self.task = task
        self.cancel = cancel
        self.signals = signals

    def run(self) -> None:
        callbacks = job.Callbacks(
            progress=lambda frac, stage: self.signals.progress.emit(self.index, frac, stage),
            state=lambda _task: self.signals.state.emit(self.index),
            log=lambda line: self.signals.log.emit(self.index, line),
        )
        try:
            job.execute_task(self.task, cancel=self.cancel, cb=callbacks)
        finally:
            self.signals.done.emit(self.index)


class ExtractSignals(QObject):
    done = Signal(bool, str)


class ExtractRunnable(QRunnable):
    def __init__(self, archive: Path, out_dir: Path, pw, verify_only: bool, signals: ExtractSignals):
        super().__init__()
        self.archive = archive
        self.out_dir = out_dir
        self.pw = pw
        self.verify_only = verify_only
        self.signals = signals

    def run(self) -> None:
        try:
            sz = SevenZip(find_sevenzip())
            if self.verify_only:
                ok, hint = verifier.test_archive(sz, self.archive, self.pw)
            else:
                ok, hint = verifier.extract_archive(sz, self.archive, self.out_dir, self.pw)
        except Exception as exc:
            ok, hint = False, f"{type(exc).__name__}: {exc}"
        self.signals.done.emit(bool(ok), str(hint))


class ResultDialog(QDialog):
    """加密完成后的信息弹窗。"""

    def __init__(self, tasks: list[job.Task], parent=None):
        super().__init__(parent)
        self.setWindowTitle("加密完成")
        self.setModal(True)
        self.setMinimumWidth(580)
        self._tasks = tasks

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("✓ 加密完成")
        title.setObjectName("okTitle")
        layout.addWidget(title)

        total = sum(len(task.outputs) for task in tasks)
        subtitle = QLabel(f"{len(tasks)} 个任务 · {total} 个加密包 · 密码已写入 TXT")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        for task in tasks:
            origin = "、".join(path.name for path in task.inputs[:3])
            if len(task.inputs) > 3:
                origin += " 等"
            for entry in task.entries:
                line = QLabel(f"{origin}  →  {entry.get('name', '')}")
                line.setWordWrap(True)
                line.setTextInteractionFlags(Qt.TextSelectableByMouse)
                card_layout.addWidget(line)

            pw_row = QHBoxLayout()
            pw_label = QLabel(f"密码：{task.pw_text or ''}")
            pw_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            pw_label.setWordWrap(True)
            pw_row.addWidget(pw_label, 1)
            copy_button = QPushButton("复制")
            copy_button.setObjectName("ghost")
            copy_button.clicked.connect(
                lambda _checked=False, text=task.pw_text: QApplication.clipboard().setText(text or "")
            )
            pw_row.addWidget(copy_button)
            card_layout.addLayout(pw_row)

            if task.pwd_file is not None:
                path_label = QLabel(f"密码 TXT：{task.pwd_file}")
                path_label.setObjectName("hint")
                path_label.setWordWrap(True)
                path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                card_layout.addWidget(path_label)

        layout.addWidget(card)

        buttons = QHBoxLayout()
        open_button = QPushButton("打开输出目录")
        open_button.setObjectName("ghost")
        open_button.clicked.connect(self._open_dir)
        close_button = QPushButton("完成")
        close_button.setObjectName("primary")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(open_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _open_dir(self) -> None:
        for task in self._tasks:
            if task.outputs:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(task.outputs[0].parent)))
                return


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SealBox 封印盒")
        self.setWindowIcon(make_icon(64))
        self.resize(1000, 780)
        self.setMinimumSize(880, 640)

        self.tasks: list[job.Task] = []
        self.cancel_event = Event()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.signals = WorkerSignals(self)
        self.ex_signals = ExtractSignals(self)
        self._quitting = False
        self.tray: QSystemTrayIcon | None = None
        self._pending_pw_text: str | None = None
        self._run_tasks: list[int] = []

        self._build_ui()
        self._build_tray()
        self._wire()
        self._init_autostart()

    # ---------- 界面 ----------
    def _section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        return label

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 16, 20, 14)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("SealBox 封印盒")
        title.setObjectName("title")
        subtitle = QLabel("一次性 UUID 密码 · 加密包 + 密码 TXT · 拖拽即用")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)

        seg_wrap = QFrame()
        seg_wrap.setObjectName("segWrap")
        seg_layout = QHBoxLayout(seg_wrap)
        seg_layout.setContentsMargins(3, 3, 3, 3)
        seg_layout.setSpacing(2)
        self.seg_group = QButtonGroup(self)
        self.seg_group.setExclusive(True)
        self.seg_buttons: list[QPushButton] = []
        for index, label in enumerate(("加密", "解压", "记录")):
            button = QPushButton(label)
            button.setObjectName("seg")
            button.setCheckable(True)
            self.seg_group.addButton(button, index)
            seg_layout.addWidget(button)
            self.seg_buttons.append(button)
        self.seg_buttons[0].setChecked(True)
        header.addWidget(seg_wrap)
        outer.addLayout(header)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_seal_page())
        self.stack.addWidget(self._build_extract_page())
        self.stack.addWidget(self._build_history_page())
        outer.addWidget(self.stack, 1)

        self.seg_group.idClicked.connect(self.switch_page)

    def _build_seal_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.seal_drop = DropZone(
            "把文件 / 文件夹拖到这里",
            "松开即入队 · 点击选择 · 也可以直接拖到程序图标上",
        )
        layout.addWidget(self.seal_drop)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self._section("输出格式"))
        self.format_checks: dict[str, QCheckBox] = {}
        for key, label in (("7z", "7z"), ("zip", "ZIP"), ("sfx", "自解压")):
            box = QCheckBox(label)
            box.setObjectName("chip")
            box.setChecked(key == "zip")
            if key == "7z":
                box.setToolTip("AES-256 + 头加密：内容与文件名都看不到，适合敏感数据")
            elif key == "zip":
                box.setToolTip("AES-256 加密内容；兼容性最好，但文件名不加密")
            else:
                box.setToolTip("生成自解压程序，对方无需安装 7-Zip")
            self.format_checks[key] = box
            row1.addWidget(box)
        row1.addSpacing(14)
        row1.addWidget(self._section("密码形态"))
        self.pwd_style_combo = QComboBox()
        for style in password.STYLES:
            self.pwd_style_combo.addItem(password.LABELS[style], style)
        row1.addWidget(self.pwd_style_combo)
        row1.addStretch(1)
        card_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._section("输出目录"))
        self.out_dir_edit = QLineEdit()
        self.out_dir_edit.setPlaceholderText("默认：与原文件同目录")
        row2.addWidget(self.out_dir_edit, 1)
        btn_out = QPushButton("选择")
        btn_out.setObjectName("ghost")
        btn_out.clicked.connect(self.pick_out_dir)
        row2.addWidget(btn_out)
        card_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.addWidget(self._section("本次密码"))
        self.pwd_line = QLineEdit()
        self.pwd_line.setReadOnly(True)
        self.pwd_line.setPlaceholderText("生成任务后自动出现")
        row3.addWidget(self.pwd_line, 1)
        self.btn_copy_pw = QPushButton("复制")
        self.btn_copy_pw.setObjectName("ghost")
        self.btn_regen = QPushButton("换一个")
        self.btn_regen.setObjectName("ghost")
        row3.addWidget(self.btn_copy_pw)
        row3.addWidget(self.btn_regen)
        card_layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.setSpacing(18)
        self.chk_txt = QCheckBox("同时写密码 TXT")
        self.chk_txt.setChecked(True)
        self.chk_verify = QCheckBox("生成后自动校验")
        self.chk_verify.setChecked(True)
        self.chk_auto = QCheckBox("拖入后自动开始")
        self.chk_auto.setChecked(True)
        self.chk_close_tray = QCheckBox("关闭时最小化到托盘")
        self.chk_close_tray.setChecked(True)
        self.chk_autostart = QCheckBox("开机自启动")
        for box in (self.chk_txt, self.chk_verify, self.chk_auto, self.chk_close_tray, self.chk_autostart):
            row4.addWidget(box)
        row4.addStretch(1)
        card_layout.addLayout(row4)
        layout.addWidget(card)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "大小", "格式", "进度"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        header_view = self.table.horizontalHeader()
        header_view.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(150)
        layout.addWidget(self.table, 1)

        self.seal_log = QPlainTextEdit()
        self.seal_log.setObjectName("console")
        self.seal_log.setReadOnly(True)
        self.seal_log.setMaximumBlockCount(600)
        self.seal_log.setMaximumHeight(96)
        self.seal_log.setVisible(False)
        layout.addWidget(self.seal_log)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_start = QPushButton("开始加密")
        self.btn_start.setObjectName("primary")
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("ghost")
        self.btn_open = QPushButton("打开输出目录")
        self.btn_open.setObjectName("ghost")
        self.btn_toggle_log = QPushButton("日志")
        self.btn_toggle_log.setObjectName("link")
        actions.addWidget(self.btn_start)
        actions.addWidget(self.btn_cancel)
        actions.addWidget(self.btn_toggle_log)
        actions.addStretch(1)
        actions.addWidget(self.btn_open)
        layout.addLayout(actions)

        self.seal_status = QLabel("就绪 · 拖入文件即可开始")
        self.seal_status.setObjectName("status")
        layout.addWidget(self.seal_status)
        return page

    def _build_extract_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.ex_drop = DropZone(
            "把压缩包拖到这里",
            "支持 7z / zip / 自解压 exe / .command · 自动读取同目录的密码 TXT",
            icon="⇪",
        )
        layout.addWidget(self.ex_drop)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self._section("压缩包"))
        self.ex_archive_edit = QLineEdit()
        self.ex_archive_edit.setPlaceholderText("选择或拖入一个压缩包")
        row1.addWidget(self.ex_archive_edit, 1)
        btn_pick = QPushButton("选择")
        btn_pick.setObjectName("ghost")
        btn_pick.clicked.connect(self.pick_archive)
        row1.addWidget(btn_pick)
        card_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._section("密码"))
        self.ex_pwd_edit = QLineEdit()
        self.ex_pwd_edit.setEchoMode(QLineEdit.Password)
        self.ex_pwd_edit.setPlaceholderText("输入密码，或点右侧从 TXT 读取")
        row2.addWidget(self.ex_pwd_edit, 1)
        self.btn_eye = QPushButton("显示")
        self.btn_eye.setObjectName("ghost")
        self.btn_eye.setCheckable(True)
        self.btn_txt_read = QPushButton("从 TXT 读取")
        self.btn_txt_read.setObjectName("ghost")
        row2.addWidget(self.btn_eye)
        row2.addWidget(self.btn_txt_read)
        card_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.addWidget(self._section("解压到"))
        self.ex_out_edit = QLineEdit()
        row3.addWidget(self.ex_out_edit, 1)
        btn_ex_out = QPushButton("选择")
        btn_ex_out.setObjectName("ghost")
        btn_ex_out.clicked.connect(self.pick_ex_out_dir)
        row3.addWidget(btn_ex_out)
        card_layout.addLayout(row3)
        layout.addWidget(card)

        self.ex_log = QPlainTextEdit()
        self.ex_log.setObjectName("console")
        self.ex_log.setReadOnly(True)
        self.ex_log.setMaximumBlockCount(400)
        layout.addWidget(self.ex_log, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_extract = QPushButton("解压")
        self.btn_extract.setObjectName("primary")
        self.btn_verify = QPushButton("仅校验")
        self.btn_verify.setObjectName("ghost")
        self.btn_ex_open = QPushButton("打开解压目录")
        self.btn_ex_open.setObjectName("ghost")
        actions.addWidget(self.btn_extract)
        actions.addWidget(self.btn_verify)
        actions.addStretch(1)
        actions.addWidget(self.btn_ex_open)
        layout.addLayout(actions)

        self.ex_status = QLabel("等待选择压缩包")
        self.ex_status.setObjectName("status")
        layout.addWidget(self.ex_status)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(self._section("压缩记录"))
        hint = QLabel("仅存本机，含明文密码")
        hint.setObjectName("hint")
        head.addWidget(hint)
        head.addStretch(1)
        self.btn_hist_refresh = QPushButton("刷新")
        self.btn_hist_refresh.setObjectName("ghost")
        self.btn_hist_copy = QPushButton("复制密码")
        self.btn_hist_copy.setObjectName("ghost")
        self.btn_hist_open = QPushButton("打开位置")
        self.btn_hist_open.setObjectName("ghost")
        self.btn_hist_csv = QPushButton("导出 CSV")
        self.btn_hist_csv.setObjectName("ghost")
        self.btn_hist_clear = QPushButton("清空")
        self.btn_hist_clear.setObjectName("ghost")
        for button in (
            self.btn_hist_refresh,
            self.btn_hist_copy,
            self.btn_hist_open,
            self.btn_hist_csv,
            self.btn_hist_clear,
        ):
            head.addWidget(button)
        card_layout.addLayout(head)

        self.hist_table = QTableWidget(0, 5)
        self.hist_table.setHorizontalHeaderLabels(["时间", "原文件", "加密包", "密码", "大小"])
        self.hist_table.verticalHeader().setVisible(False)
        self.hist_table.setShowGrid(False)
        self.hist_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hist_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.hist_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hist_header = self.hist_table.horizontalHeader()
        hist_header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hist_header.setSectionResizeMode(1, QHeaderView.Stretch)
        hist_header.setSectionResizeMode(2, QHeaderView.Stretch)
        for column in (0, 3, 4):
            hist_header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        card_layout.addWidget(self.hist_table, 1)
        layout.addWidget(card, 1)
        return page

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(make_icon(64), self)
        self.tray.setToolTip("SealBox 封印盒")
        menu = QMenu(self)
        act_show = menu.addAction("显示主窗口")
        act_show.triggered.connect(self.show_normal)
        menu.addSeparator()
        act_quit = menu.addAction("退出 SealBox")
        act_quit.triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _wire(self) -> None:
        self.seal_drop.filesDropped.connect(self.add_paths)
        self.seal_drop.clicked.connect(self.pick_files)
        self.ex_drop.filesDropped.connect(lambda paths: self.set_archive(Path(paths[0])))
        self.btn_start.clicked.connect(self.start_queue)
        self.btn_cancel.clicked.connect(self.cancel_queue)
        self.btn_open.clicked.connect(self.open_output_dir)
        self.btn_toggle_log.clicked.connect(lambda: self.seal_log.setVisible(not self.seal_log.isVisible()))
        self.btn_copy_pw.clicked.connect(self.copy_pw)
        self.btn_regen.clicked.connect(self.regenerate_pw)
        self.chk_autostart.toggled.connect(self.toggle_autostart)
        self.btn_extract.clicked.connect(lambda: self.run_extract(False))
        self.btn_verify.clicked.connect(lambda: self.run_extract(True))
        self.btn_ex_open.clicked.connect(self.open_extract_dir)
        self.btn_eye.toggled.connect(self.toggle_pw_visible)
        self.btn_txt_read.clicked.connect(self.read_sibling_txt)
        self.btn_hist_refresh.clicked.connect(self.refresh_history)
        self.btn_hist_copy.clicked.connect(self.copy_history_pw)
        self.btn_hist_open.clicked.connect(self.open_history_location)
        self.btn_hist_csv.clicked.connect(self.export_history)
        self.btn_hist_clear.clicked.connect(self.clear_history)
        self.hist_table.doubleClicked.connect(lambda _index: self.open_history_location())

        self.signals.progress.connect(self.on_progress)
        self.signals.state.connect(self.on_state)
        self.signals.log.connect(self.on_log)
        self.signals.done.connect(self.on_done)
        self.ex_signals.done.connect(self.on_extract_done)

    # ---------- 页面 ----------
    def switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.seg_buttons):
            button.setChecked(i == index)
        if index == 2:
            self.refresh_history()

    # ---------- 加密队列 ----------
    def current_options(self) -> job.JobOptions:
        formats = tuple(key for key, box in self.format_checks.items() if box.isChecked()) or ("7z",)
        out = self.out_dir_edit.text().strip()
        return job.JobOptions(
            formats=formats,
            output_dir=Path(out) if out else None,
            pwd_style=self.pwd_style_combo.currentData(),
            write_pwd_file=self.chk_txt.isChecked(),
            verify=self.chk_verify.isChecked(),
            record_history=True,
        )

    def add_paths(self, paths) -> None:
        files = [Path(p) for p in paths if Path(p).exists()]
        if not files:
            return
        options = self.current_options()
        task = job.plan_task(files, options)
        task.pw_text = self._pending_pw_text or password.generate(options.pwd_style)
        self._pending_pw_text = None
        task.index = len(self.tasks)
        self.tasks.append(task)
        self._append_row(task)
        self.pwd_line.setText(task.pw_text)
        self.seal_status.setText(f"已加入 {len(files)} 项")
        self.switch_page(0)
        if self.chk_auto.isChecked():
            self.start_queue()

    def _append_row(self, task: job.Task) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        name_item = QTableWidgetItem(task.name)
        name_item.setToolTip("\n".join(str(p) for p in task.inputs))
        self.table.setItem(row, 0, name_item)

        total = 0
        for path in task.inputs:
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
        self.table.setItem(row, 1, QTableWidgetItem(human_size(total)))
        self.table.setItem(row, 2, QTableWidgetItem(" + ".join(task.options.formats).upper()))

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setFormat("待处理")
        bar.setTextVisible(True)
        self.table.setCellWidget(row, 3, bar)

    def start_queue(self) -> None:
        if self.pool.activeThreadCount() > 0:
            return
        self.cancel_event.clear()
        self._run_tasks = [i for i, task in enumerate(self.tasks) if task.state == job.STATE_PENDING]
        self._start_next()

    def _start_next(self) -> None:
        for index, task in enumerate(self.tasks):
            if task.state == job.STATE_PENDING:
                self.seal_status.setText(f"处理中：{task.name}")
                self.pool.start(TaskRunnable(index, task, self.cancel_event, self.signals))
                return
        self.seal_status.setText("全部完成")

    def cancel_queue(self) -> None:
        self.cancel_event.set()
        cancelled = 0
        for task in self.tasks:
            if task.state == job.STATE_PENDING:
                task.state = job.STATE_CANCELLED
                self.on_state(task.index)
                cancelled += 1
        self.seal_status.setText(f"已取消（{cancelled} 项待处理）" if cancelled else "正在取消当前任务…")

    def on_progress(self, index: int, frac: float, stage: str) -> None:
        bar = self.table.cellWidget(index, 3)
        if isinstance(bar, QProgressBar):
            bar.setValue(int(max(0.0, min(1.0, frac)) * 100))
            bar.setFormat(f"{stage} {int(frac * 100)}%")
        if index == self._active_index():
            self.seal_status.setText(stage)

    def _active_index(self) -> int:
        for index, task in enumerate(self.tasks):
            if task.state == job.STATE_RUNNING:
                return index
        return -1

    def on_state(self, index: int) -> None:
        if not (0 <= index < len(self.tasks)):
            return
        task = self.tasks[index]
        bar = self.table.cellWidget(index, 3)
        if task.state == job.STATE_DONE:
            self._style_bar(bar, 100, "完成", "#10b981")
        elif task.state == job.STATE_FAILED:
            self._style_bar(bar, 0, "失败", "#ef4444")
            if isinstance(bar, QProgressBar):
                bar.setToolTip(task.error or "")
        elif task.state == job.STATE_CANCELLED:
            self._style_bar(bar, 0, "已取消", "#94a3b8")
        elif task.state == job.STATE_RUNNING:
            self._style_bar(bar, 0, "加密中", "#3b82f6")
        if task.pw_text and task.state in (job.STATE_RUNNING, job.STATE_DONE):
            self.pwd_line.setText(task.pw_text)

    @staticmethod
    def _style_bar(bar, value: int, text: str, color: str) -> None:
        if not isinstance(bar, QProgressBar):
            return
        bar.setValue(value)
        bar.setFormat(text)
        bar.setStyleSheet(
            f"QProgressBar::chunk {{ background: {color}; border-radius: 5px; }}"
        )

    def on_log(self, index: int, line: str) -> None:
        self.seal_log.appendPlainText(line)

    def on_done(self, index: int) -> None:
        if not (0 <= index < len(self.tasks)):
            return
        task = self.tasks[index]
        if task.state == job.STATE_DONE:
            self.seal_status.setText(f"完成：{len(task.outputs)} 个加密包")
            self.refresh_history()
            if self.tray and not self.isVisible():
                self.tray.showMessage(
                    "SealBox",
                    f"已生成 {len(task.outputs)} 个加密包",
                    QSystemTrayIcon.Information,
                    3000,
                )
        elif task.state == job.STATE_FAILED:
            self.seal_status.setText(f"失败：{task.error}")
        elif task.state == job.STATE_CANCELLED:
            self.seal_status.setText("已取消")

        if self.cancel_event.is_set():
            return
        self._start_next()
        self._maybe_show_result()

    def _maybe_show_result(self) -> None:
        """整批任务结束后弹出一次结果窗。"""
        if not self._run_tasks:
            return
        if any(
            self.tasks[i].state in (job.STATE_PENDING, job.STATE_RUNNING)
            for i in self._run_tasks
            if i < len(self.tasks)
        ):
            return
        finished = [self.tasks[i] for i in self._run_tasks if self.tasks[i].state == job.STATE_DONE]
        self._run_tasks = []
        if finished:
            dialog = ResultDialog(finished, self)
            dialog.exec()

    # ---------- 开机自启动 ----------
    def _init_autostart(self) -> None:
        try:
            enabled = autostart.is_enabled()
        except Exception:
            enabled = False
        self.chk_autostart.blockSignals(True)
        self.chk_autostart.setChecked(enabled)
        self.chk_autostart.blockSignals(False)

    def toggle_autostart(self, checked: bool) -> None:
        try:
            autostart.enable() if checked else autostart.disable()
        except Exception as exc:
            self.chk_autostart.blockSignals(True)
            self.chk_autostart.setChecked(not checked)
            self.chk_autostart.blockSignals(False)
            QMessageBox.warning(self, "开机自启动", f"设置失败：{exc}")
            return
        self.seal_status.setText(
            "已开启开机自启动（登录后静默驻留托盘）" if checked else "已关闭开机自启动"
        )

    # ---------- 密码 ----------
    def copy_pw(self) -> None:
        text = self.pwd_line.text().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.seal_status.setText("密码已复制到剪贴板")

    def regenerate_pw(self) -> None:
        style = self.pwd_style_combo.currentData()
        fresh = password.generate(style)
        self._pending_pw_text = fresh
        for task in self.tasks:
            if task.state == job.STATE_PENDING:
                task.pw_text = fresh
        self.pwd_line.setText(fresh)

    # ---------- 选择 ----------
    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件", "")
        if files:
            self.add_paths(files)

    def pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.add_paths([folder])

    def pick_out_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.out_dir_edit.setText(folder)

    def open_output_dir(self) -> None:
        target = Path(self.out_dir_edit.text().strip()) if self.out_dir_edit.text().strip() else None
        if target is None:
            for task in reversed(self.tasks):
                if task.outputs:
                    target = task.outputs[0].parent
                    break
        if target and target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    # ---------- 解压 ----------
    def pick_archive(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择压缩包", "", "压缩包 (*.7z *.zip *.rar *.exe *.command *.run);;所有文件 (*)"
        )
        if path:
            self.set_archive(Path(path))

    def set_archive(self, path: Path) -> None:
        self.ex_archive_edit.setText(str(path))
        self.ex_out_edit.setText(str(path.parent / path.stem))
        self.ex_log.clear()
        sibling = manifest.find_sibling_pw_file(path)
        if sibling is not None:
            value = manifest.read_pw_file(sibling)
            if value:
                self.ex_pwd_edit.setText(value)
                self.ex_status.setText(f"已读取密码：{sibling.name}")
                self.ex_log.appendPlainText(f"从 {sibling} 读取到密码。")
        else:
            self.ex_status.setText("未找到同目录密码 TXT，请手动输入")
        self.switch_page(1)

    def pick_ex_out_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择解压目录")
        if folder:
            self.ex_out_edit.setText(folder)

    def toggle_pw_visible(self, visible: bool) -> None:
        self.ex_pwd_edit.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.btn_eye.setText("隐藏" if visible else "显示")

    def read_sibling_txt(self) -> None:
        archive = Path(self.ex_archive_edit.text().strip())
        if not archive.exists():
            self.ex_status.setText("请先选择压缩包")
            return
        sibling = manifest.find_sibling_pw_file(archive)
        if sibling is None:
            path, _ = QFileDialog.getOpenFileName(self, "选择密码 TXT", str(archive.parent), "文本 (*.txt)")
            if path:
                sibling = Path(path)
        if sibling is not None:
            value = manifest.read_pw_file(sibling)
            if value:
                self.ex_pwd_edit.setText(value)
                self.ex_status.setText(f"已读取：{sibling.name}")
                return
        self.ex_status.setText("没有读到密码")

    def run_extract(self, verify_only: bool) -> None:
        archive = Path(self.ex_archive_edit.text().strip())
        if not archive.is_file():
            self.ex_status.setText("请先选择有效的压缩包")
            return
        pw = self.ex_pwd_edit.text()
        if not pw:
            self.ex_status.setText("请输入密码")
            return
        out_dir = Path(self.ex_out_edit.text().strip() or (archive.parent / archive.stem))
        self.btn_extract.setEnabled(False)
        self.btn_verify.setEnabled(False)
        self.ex_status.setText("校验中…" if verify_only else "解压中…")
        self.ex_log.appendPlainText(("校验 " if verify_only else "解压 ") + archive.name)
        self.pool.start(ExtractRunnable(archive, out_dir, pw, verify_only, self.ex_signals))

    def on_extract_done(self, ok: bool, hint: str) -> None:
        self.btn_extract.setEnabled(True)
        self.btn_verify.setEnabled(True)
        self.ex_status.setText(("完成：" if ok else "失败：") + hint)
        self.ex_log.appendPlainText(("✔ " if ok else "✘ ") + hint)

    def open_extract_dir(self) -> None:
        target = Path(self.ex_out_edit.text().strip())
        if target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    # ---------- 记录 ----------
    def refresh_history(self) -> None:
        rows = history_mod.load(300)
        self.hist_table.setRowCount(len(rows))
        for row, entry in enumerate(rows):
            outputs = entry.get("outputs") or []
            inputs = entry.get("inputs") or []
            stamp = str(entry.get("ts", ""))[:19].replace("T", " ")
            values = [
                stamp,
                "、".join(Path(p).name for p in inputs[:3]) + (" 等" if len(inputs) > 3 else ""),
                "、".join(str(o.get("name", "")) for o in outputs),
                entry.get("pw", ""),
                human_size(sum(int(o.get("size", 0)) for o in outputs)),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, entry)
                if column == 3:
                    item.setToolTip("双击行可打开位置；选中后点「复制密码」")
                self.hist_table.setItem(row, column, item)

    def _selected_history(self) -> dict | None:
        row = self.hist_table.currentRow()
        if row < 0:
            return None
        item = self.hist_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def copy_history_pw(self) -> None:
        entry = self._selected_history()
        if not entry:
            return
        value = entry.get("pw", "")
        if value:
            QApplication.clipboard().setText(value)

    def open_history_location(self) -> None:
        entry = self._selected_history()
        if not entry:
            return
        for out in entry.get("outputs", []):
            path = Path(out.get("path", ""))
            if path.parent.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
                return

    def export_history(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出记录", "sealbox-history.csv", "CSV (*.csv)")
        if path:
            history_mod.export_csv(Path(path))
            self.seal_status.setText(f"已导出：{path}")

    def clear_history(self) -> None:
        if QMessageBox.question(self, "清空记录", "确定清空全部压缩记录？此操作不可恢复。") == QMessageBox.Yes:
            history_mod.clear()
            self.refresh_history()

    # ---------- 托盘 / 关闭 ----------
    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_normal()

    def show_normal(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        if (
            self.tray is not None
            and self.tray.isVisible()
            and self.chk_close_tray.isChecked()
            and not self._quitting
        ):
            event.ignore()
            self.hide()
            self.tray.showMessage("SealBox", "已最小化到托盘，右键托盘图标可退出。", QSystemTrayIcon.Information, 2500)
            return
        self.quit_app()
        event.accept()

    def quit_app(self) -> None:
        self._quitting = True
        self.cancel_event.set()
        try:
            self.pool.waitForDone(2000)
        except Exception:
            pass
        if self.tray is not None:
            self.tray.hide()
        QApplication.quit()

    # ---------- 外部投递 ----------
    def startup(self, paths, action="auto", formats=None, out_dir=None, pwd_style=None, pwd_text=None):
        if paths:
            self.show_normal()
        if formats:
            for key, box in self.format_checks.items():
                box.setChecked(key in formats)
        if out_dir:
            self.out_dir_edit.setText(str(out_dir))
        if pwd_style:
            index = self.pwd_style_combo.findData(pwd_style)
            if index >= 0:
                self.pwd_style_combo.setCurrentIndex(index)
        self._pending_pw_text = pwd_text
        self.handle_paths([Path(p) for p in paths], action)

    def handle_payload(self, data: dict) -> None:
        self.show_normal()
        self.startup(
            [Path(p) for p in data.get("paths", [])],
            data.get("action", "auto"),
            data.get("formats"),
            data.get("out_dir"),
            data.get("pwd_style"),
            data.get("pwd_text"),
        )

    def handle_paths(self, paths: list[Path], action: str = "auto") -> None:
        existing = [p for p in paths if p.exists()]
        if not existing:
            return
        archives = [p for p in existing if p.is_file() and looks_like_archive(p)]
        others = [p for p in existing if p not in archives]

        if action == "extract" or (action == "auto" and archives):
            if archives:
                self.set_archive(archives[0])
                if action == "verify":
                    self.run_extract(True)
            if others:
                self.add_paths([str(p) for p in others])
            return
        self.add_paths([str(p) for p in existing])


def run_gui(
    paths=None,
    action="auto",
    formats=("7z",),
    out_dir=None,
    pwd_style="short22",
    pwd_text=None,
    tray_only: bool = False,
) -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    app.setApplicationName("SealBox")
    app.setApplicationDisplayName("SealBox 封印盒")
    app.setWindowIcon(make_icon(64))
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)

    instance = SingleInstance()
    if not instance.try_start():
        instance.notify(
            {
                "paths": list(paths or []),
                "action": action,
                "formats": list(formats or ("7z",)),
                "out_dir": str(out_dir) if out_dir else None,
                "pwd_style": pwd_style,
                "pwd_text": pwd_text,
            }
        )
        return EXIT_OK

    window = MainWindow()
    instance.payload.connect(window.handle_payload)
    if tray_only and window.tray is not None:
        window.tray.showMessage(
            "SealBox",
            "已在托盘运行；把文件拖到窗口图标或右键菜单即可加密。",
            QSystemTrayIcon.Information,
            3000,
        )
    else:
        window.show()
    QTimer.singleShot(
        0,
        lambda: window.startup(
            list(paths or []), action, formats, out_dir, pwd_style, pwd_text
        ),
    )
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui(sys.argv[1:], "auto"))
