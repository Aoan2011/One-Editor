# F:\one-editor\tests\conftest.py
"""
tests/conftest.py —— 所有测试共享的 fixture。

核心 fixture：
    - git_repo           临时 git 仓库，用于测试 Git 相关逻辑
    - sample_text_file   带内容的文本文件
    - isolated_config    完全隔离 ConfigManager / SwapManager / keymap，
                         避免读写真实 ~/.one-editor，导致测试结果不稳定
"""
import subprocess
import sys
from pathlib import Path

import pytest

# 防御性 sys.path 注入（根 conftest 已做，这里兜底）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ============================================================
# 文件系统 fixture
# ============================================================
@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """创建隔离的临时 git 仓库，已配置 user.email / user.name。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "ci@one-editor.dev"],
        cwd=repo, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "One-Editor CI"],
        cwd=repo, check=True,
    )
    return repo


@pytest.fixture
def sample_text_file(tmp_path: Path) -> Path:
    """一个带 UTF-8 内容的文本文件，用于测试 safe_read / 编码探测。"""
    f = tmp_path / "sample.txt"
    f.write_text("hello\nworld\n", encoding="utf-8")
    return f


# ============================================================
# 配置/状态隔离 fixture（最重要）
# ============================================================
@pytest.fixture
def isolated_config(monkeypatch, tmp_path: Path):
    """让所有配置/swap/keymap 读写都走 tmp_path 或内存。

    使用方式：
        def test_xxx(isolated_config):
            app = OneEditor()   # 不会读写真实 ~/.one-editor
            ...

    这个 fixture 会在测试结束后自动恢复 monkeypatch。

    Yields:
        dict: {
            "state":       state dict（会被 save_state 更新）
            "settings":    settings dict
            "plugins":     plugin config dict
            "config_dir":  tmp_path/.one-editor
            "swap_dir":    tmp_path/.one-editor/swap
        }
    """
    # 延迟导入，避免在 conftest 顶层就 import 整个项目
    import constants
    import config as config_mod
    import swap as swap_mod
    import keymap as keymap_mod
    from config import ConfigManager
    from constants import DEFAULT_SETTINGS

    # ---- 1. 计算临时路径 ----
    fake_config_dir = tmp_path / ".one-editor"
    fake_config_dir.mkdir()
    fake_swap_dir = fake_config_dir / "swap"
    fake_swap_dir.mkdir()
    fake_config_file = fake_config_dir / "state.json"
    fake_keymap_file = fake_config_dir / "keymap.json"
    fake_plugin_file = fake_config_dir / "plugins.json"

    # ---- 2. 重定向 constants 模块里的全局路径 ----
    monkeypatch.setattr(constants, "CONFIG_DIR", fake_config_dir)
    monkeypatch.setattr(constants, "CONFIG_FILE", fake_config_file)
    monkeypatch.setattr(constants, "KEYMAP_FILE", fake_keymap_file)
    monkeypatch.setattr(constants, "PLUGIN_CONFIG_FILE", fake_plugin_file)
    monkeypatch.setattr(constants, "SWAP_DIR", fake_swap_dir)

    # ---- 3. 重定向各模块已经 import 的副本 ----
    # swap.py 顶部是 from constants import SWAP_DIR，模块级全局变量
    monkeypatch.setattr(swap_mod, "SWAP_DIR", fake_swap_dir)
    # keymap.py 顶部是 from constants import KEYMAP_FILE
    monkeypatch.setattr(keymap_mod, "KEYMAP_FILE", fake_keymap_file)
    # config.py 顶部 from constants import CONFIG_DIR, CONFIG_FILE, ...
    monkeypatch.setattr(config_mod, "CONFIG_DIR", fake_config_dir)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", fake_config_file)
    monkeypatch.setattr(config_mod, "PLUGIN_CONFIG_FILE", fake_plugin_file)

    # ---- 4. ConfigManager 全走内存（双保险，防某个方法绕过上述路径）----
    fake_state: dict = {}
    fake_settings = DEFAULT_SETTINGS.copy()
    fake_plugins: dict = {}

    monkeypatch.setattr(
        ConfigManager, "load_state",
        classmethod(lambda cls: dict(fake_state)),
    )
    monkeypatch.setattr(
        ConfigManager, "save_state",
        classmethod(lambda cls, s: fake_state.update(s)),
    )
    monkeypatch.setattr(
        ConfigManager, "load_settings",
        classmethod(lambda cls: dict(fake_settings)),
    )
    monkeypatch.setattr(
        ConfigManager, "save_settings",
        classmethod(lambda cls, s: fake_settings.update(s)),
    )
    monkeypatch.setattr(
        ConfigManager, "load_recent_files",
        classmethod(lambda cls: []),
    )
    monkeypatch.setattr(
        ConfigManager, "add_recent_file",
        classmethod(lambda cls, fp: None),
    )
    monkeypatch.setattr(
        ConfigManager, "load_tree_width",
        classmethod(lambda cls: 30),
    )
    monkeypatch.setattr(
        ConfigManager, "save_tree_width",
        classmethod(lambda cls, w: None),
    )
    monkeypatch.setattr(
        ConfigManager, "load_plugin_config",
        classmethod(lambda cls: dict(fake_plugins)),
    )
    monkeypatch.setattr(
        ConfigManager, "save_plugin_config",
        classmethod(lambda cls, cfg: fake_plugins.update(cfg)),
    )

    # ---- 5. keymap 不落盘 ----
    monkeypatch.setattr(keymap_mod, "ensure_keymap_file", lambda: None)
    monkeypatch.setattr(keymap_mod, "load_custom_keymap", lambda: {})

    yield {
        "state": fake_state,
        "settings": fake_settings,
        "plugins": fake_plugins,
        "config_dir": fake_config_dir,
        "swap_dir": fake_swap_dir,
    }