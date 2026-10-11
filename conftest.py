"""确保 pytest 在任何工作目录下都能导入 deck 包。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
