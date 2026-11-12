"""拖拽区：文件/文件夹拖入即触发，点击打开选择框。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class DropZone(QFrame):
    filesDropped = Signal(list)
    clicked = Signal()

    def __init__(self, title: str, hint: str, icon: str = "⇣", parent=None):
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        self._icon = QLabel(icon)
        self._icon.setObjectName("dzIcon")
        self._icon.setAlignment(Qt.AlignCenter)
        self._title = QLabel(title)
        self._title.setObjectName("dzTitle")
        self._title.setAlignment(Qt.AlignCenter)
        self._hint = QLabel(hint)
        self._hint.setObjectName("dzHint")
        self._hint.setAlignment(Qt.AlignCenter)

        layout.addWidget(self._icon)
        layout.addWidget(self._title)
        layout.addWidget(self._hint)

    def set_texts(self, title: str, hint: str) -> None:
        self._title.setText(title)
        self._hint.setText(hint)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drag(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_drag(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_drag(False)
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _set_drag(self, active: bool) -> None:
        self.setProperty("drag", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
