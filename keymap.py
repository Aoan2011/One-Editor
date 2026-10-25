# MIT License
# Copyright (c) 2026 Aoan2011
"""自定义键位：从 ~/.one-editor/keymap.json 读取，覆盖默认 BINDINGS。

格式：
{
    "ctrl+shift+x": "action_show_symbols",
    "ctrl+p": "action_command_palette"
}
"""
import json
from pathlib import Path

from constants import KEYMAP_FILE


DEFAULT_KEYMAP = {}


def load_custom_keymap() -> dict[str, str]:
    """读取用户自定义键位。文件不存在时返回空 dict。"""
    if not KEYMAP_FILE.exists():
        return {}
    try:
        data = json.loads(KEYMAP_FILE.read_text("utf-8"))
        return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}
    except Exception:
        return {}


def save_custom_keymap(mapping: dict[str, str]) -> None:
    KEYMAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYMAP_FILE.write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False), "utf-8"
    )


def ensure_keymap_file() -> None:
    """首次启动时创建空模板，方便用户编辑。"""
    if not KEYMAP_FILE.exists():
        KEYMAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEYMAP_FILE.write_text(
            json.dumps(DEFAULT_KEYMAP, indent=2, ensure_ascii=False), "utf-8"
        )