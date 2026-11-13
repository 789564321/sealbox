"""全局单实例：命名管道（Windows）／Unix domain socket（macOS、Linux）。

* 实例键只与当前用户有关，**不再包含可执行文件路径**，所以源码运行、
  `SealBox.exe`、`SealBoxCLI.exe` 会共用同一个实例。
* 新实例把 JSON 任务写入管道，旧实例处理后回 ACK；没有 ACK 视为投递失败，
  此时新实例会尝试接管（清理残留管道后监听）。
* 旧实例收到任务后加入队列；没有任务时只把窗口唤醒到前台。
"""

from __future__ import annotations

import getpass
import json
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

MAX_PAYLOAD = 2 * 1024 * 1024  # 2 MB，防止异常消息撑爆内存
ACK = b'{"ok":true}\n'


def instance_key() -> str:
    user = os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser()
    safe = "".join(ch for ch in user if ch.isalnum() or ch in "-_") or "default"
    return f"SealBox-single-{safe}"


class SingleInstance(QObject):
    payload = Signal(dict)

    def __init__(self, key: str | None = None):
        super().__init__()
        self.key = key or instance_key()
        self.server: QLocalServer | None = None

    # ---------- 角色判定 ----------
    def _probe(self, timeout: int = 300) -> bool:
        """已有实例是否在监听。"""
        sock = QLocalSocket()
        sock.connectToServer(self.key)
        connected = sock.waitForConnected(timeout)
        if connected:
            sock.disconnectFromServer()
        return connected

    def try_start(self) -> bool:
        """尝试成为主实例；已有实例时返回 False。"""
        if self._probe():
            return False

        QLocalServer.removeServer(self.key)
        self.server = QLocalServer(self)
        self.server.setMaxPendingConnections(8)
        self.server.newConnection.connect(self._on_connection)
        if self.server.listen(self.key):
            return True

        # 竞态：另一个实例刚好先一步监听成功
        self.server = None
        return not self._probe()

    # ---------- 投递 ----------
    def notify(self, data: dict, timeout: int = 1500) -> bool:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if len(raw) > MAX_PAYLOAD:
            return False
        sock = QLocalSocket()
        sock.connectToServer(self.key)
        if not sock.waitForConnected(timeout):
            return False
        sock.write(raw + b"\n")
        if not sock.waitForBytesWritten(timeout):
            sock.disconnectFromServer()
            return False
        ok = False
        if sock.waitForReadyRead(timeout):
            ok = b'"ok":true' in bytes(sock.readAll())
        sock.disconnectFromServer()
        return ok

    # ---------- 服务端 ----------
    def _on_connection(self) -> None:
        if self.server is None:
            return
        conn = self.server.nextPendingConnection()
        if conn is None:
            return
        buffer = bytearray()

        def read(c=conn) -> None:
            buffer.extend(c.readAll())
            if len(buffer) > MAX_PAYLOAD:
                c.disconnectFromServer()
                return
            if b"\n" not in buffer:
                return
            line, _, _ = buffer.partition(b"\n")
            buffer.clear()
            try:
                data = json.loads(line.decode("utf-8"))
            except Exception:
                data = None
            if isinstance(data, dict):
                self.payload.emit(data)
            c.write(ACK)
            c.flush()
            c.disconnectFromServer()

        conn.readyRead.connect(read)
        if conn.bytesAvailable() > 0:
            read()
