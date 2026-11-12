"""浅色现代主题（QSS）。"""

ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
OK = "#10b981"
ERR = "#ef4444"

STYLE = """
* {
    font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", "Noto Sans CJK SC", sans-serif;
    font-size: 13px;
    color: #1f2937;
}
QMainWindow, QWidget#root, QDialog { background: #f4f6fb; }

QLabel#title { font-size: 22px; font-weight: 700; color: #0f172a; }
QLabel#okTitle { font-size: 20px; font-weight: 700; color: #059669; }
QLabel#subtitle { color: #64748b; font-size: 12px; }
QLabel#section { color: #334155; font-weight: 600; }
QLabel#hint { color: #94a3b8; font-size: 12px; }
QLabel#status { color: #475569; font-size: 12px; }
QLabel#danger { color: #ef4444; font-size: 12px; }

QFrame#card {
    background: #ffffff;
    border: 1px solid #e6ebf5;
    border-radius: 16px;
}
QFrame#segWrap {
    background: #e8edf7;
    border-radius: 12px;
}
QPushButton#seg {
    background: transparent;
    border: none;
    padding: 7px 18px;
    border-radius: 9px;
    color: #475569;
}
QPushButton#seg:hover { color: #1d4ed8; }
QPushButton#seg:checked {
    background: #ffffff;
    color: #1d4ed8;
    font-weight: 600;
}

QFrame#dropzone {
    background: #fbfdff;
    border: 2px dashed #c7d2fe;
    border-radius: 16px;
}
QFrame#dropzone[drag="true"] {
    background: #eef4ff;
    border-color: #2563eb;
}
QLabel#dzIcon { font-size: 32px; color: #6366f1; }
QLabel#dzTitle { font-size: 16px; font-weight: 600; color: #1e3a8a; }
QLabel#dzHint { color: #7c8aa5; font-size: 12px; }

QPushButton#primary {
    background: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 9px 22px;
    font-weight: 600;
}
QPushButton#primary:hover { background: #1d4ed8; }
QPushButton#primary:pressed { background: #1e40af; }
QPushButton#primary:disabled { background: #c7d2fe; color: #eef2ff; }

QPushButton#ghost {
    background: #ffffff;
    border: 1px solid #dbe3f0;
    border-radius: 10px;
    padding: 8px 16px;
    color: #334155;
}
QPushButton#ghost:hover { background: #f1f5ff; border-color: #bfd0f7; }
QPushButton#ghost:disabled { color: #cbd5e1; border-color: #eef2f7; }

QPushButton#link {
    background: transparent;
    border: none;
    color: #2563eb;
    padding: 2px 6px;
}
QPushButton#link:hover { color: #1d4ed8; text-decoration: underline; }

QLineEdit, QComboBox {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 9px;
    padding: 7px 10px;
    selection-background-color: #bfdbfe;
    selection-color: #1e3a8a;
}
QLineEdit:focus, QComboBox:focus { border-color: #93c5fd; background: #ffffff; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    selection-background-color: #eff6ff;
    selection-color: #1d4ed8;
    outline: none;
}

QCheckBox { spacing: 7px; color: #475569; }
QCheckBox#chip {
    background: #f6f8fd;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 5px 13px;
    color: #475569;
}
QCheckBox#chip:checked {
    background: #dbeafe;
    border-color: #93c5fd;
    color: #1d4ed8;
    font-weight: 600;
}

QTableWidget {
    background: transparent;
    border: none;
    gridline-color: transparent;
    outline: none;
}
QTableWidget::item { padding: 7px 4px; border-bottom: 1px solid #f1f5f9; }
QTableWidget::item:selected { background: #eff6ff; color: #1e3a8a; }
QHeaderView::section {
    background: transparent;
    border: none;
    color: #94a3b8;
    font-weight: 600;
    padding: 6px 4px;
}

QProgressBar {
    background: #eef2ff;
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    font-size: 10px;
    color: #1e3a8a;
}
QProgressBar::chunk { background: #3b82f6; border-radius: 5px; }

QPlainTextEdit#console {
    background: #0f172a;
    color: #cbd5e1;
    border: none;
    border-radius: 12px;
    padding: 10px;
    font-family: "Cascadia Mono", Consolas, "Menlo", monospace;
    font-size: 12px;
}

QMenu {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item { padding: 7px 18px; border-radius: 6px; }
QMenu::item:selected { background: #eff6ff; color: #1d4ed8; }

QToolTip {
    background: #1e293b;
    color: #e2e8f0;
    border: none;
    padding: 6px 8px;
    border-radius: 6px;
}

QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #d7dfec; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #b9c6dc; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 2px; }
QScrollBar::handle:horizontal { background: #d7dfec; border-radius: 4px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""
