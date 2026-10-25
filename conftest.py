# F:\one-editor\conftest.py
"""
Root conftest.py —— 只负责让 pytest 能找到项目模块。

放在根目录的原因：
    pytest 会从 rootdir 开始，向上/向下逐层加载 conftest.py。
    根目录这份最早加载，保证后续 import 都能找到 utils / swap 等模块。

即使 pyproject.toml 里配了 pythonpath = ["."]，这里也保留一份，
作为对旧版 pytest 的兜底。
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))