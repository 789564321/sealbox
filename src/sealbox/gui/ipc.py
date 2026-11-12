"""单实例：把右键菜单/第二次拖入的任务投递给已打开的窗口。"""

from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def instance_key() -> str:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "user"
    return f"SealBox-{user}-{abs(hash(sys.executable)) % 100000}"


class SingleInstance(QObject):
    payload = Signal(dict)

    def __init__(self, key: str | None = None):
        super().__init__()
        self.key = key or instance_key()
        self.server: QLocalServer | None = None

    def try_start(self) -> bool:
        probe = QLocalSocket()
        probe.connectToServer(self.key)
        if probe.waitForConnected(200):
            probe.disconnectFromServer()
            return False

        QLocalServer.removeServer(self.key)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_connection)
        return self.server.listen(self.key)

    def notify(self, data: dict) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self.key)
        if not sock.waitForConnected(400):
            return False
        sock.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(400)
        sock.disconnectFromServer()
        return True

    def _on_connection(self) -> None:
        if self.server is None:
            return
        conn = self.server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda c=conn: self._read(c))

    def _read(self, conn: QLocalSocket) -> None:
        raw = bytes(conn.readAll())
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict):
            self.payload.emit(data)
        conn.disconnectFromServer()
