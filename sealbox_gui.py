"""SealBox 启动脚本（源码运行用）。

把 src 加进 sys.path，这样不安装也能用：
    pythonw sealbox_gui.py --seal "D:\\some\\file"
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from sealbox.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
