"""配置、状态、树宽、插件配置的统一读写。"""
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from constants import CONFIG_DIR, CONFIG_FILE, DEFAULT_SETTINGS, PLUGIN_CONFIG_FILE, RECENT_MAX


class ConfigManager:
    """线程安全的配置文件读写（UI 线程和后台线程都会用）。"""

    _lock = threading.RLock()

    # ---------- settings ----------
    @classmethod
    def load_settings(cls) -> Dict[str, Any]:
        with cls._lock:
            settings = DEFAULT_SETTINGS.copy()
            if CONFIG_FILE.exists():
                try:
                    state = json.loads(CONFIG_FILE.read_text("utf-8"))
                    settings.update(state.get("settings", {}))
                except Exception:
                    pass
            return settings

    @classmethod
    def save_settings(cls, settings: Dict[str, Any]) -> None:
        with cls._lock:
            state = cls._read_state()
            state["settings"] = settings
            cls._write_state(state)

    # ---------- state ----------
    @classmethod
    def _read_state(cls) -> Dict[str, Any]:
        if not CONFIG_FILE.exists():
            return {}
        try:
            return json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception:
            return {}

    @classmethod
    def _write_state(cls, state: Dict[str, Any]) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(state, indent=2, ensure_ascii=False), "utf-8"
        )

    @classmethod
    def load_state(cls) -> Dict[str, Any]:
        with cls._lock:
            return cls._read_state()

    @classmethod
    def save_state(cls, state: Dict[str, Any]) -> None:
        with cls._lock:
            existing = cls._read_state()
            existing.update(state)
            cls._write_state(existing)

    # ---------- tree width ----------
    @classmethod
    def load_tree_width(cls) -> int:
        with cls._lock:
            try:
                w = int(cls._read_state().get("tree_width", 30))
                return max(30, min(60, w))
            except Exception:
                return 30

    @classmethod
    def save_tree_width(cls, width: int) -> None:
        with cls._lock:
            state = cls._read_state()
            state["tree_width"] = width
            cls._write_state(state)

    # ---------- plugin config ----------
    @classmethod
    def load_plugin_config(cls) -> Dict[str, Any]:
        with cls._lock:
            if PLUGIN_CONFIG_FILE.exists():
                try:
                    return json.loads(PLUGIN_CONFIG_FILE.read_text("utf-8"))
                except Exception:
                    pass
            return {}

    @classmethod
    def save_plugin_config(cls, cfg: Dict[str, Any]) -> None:
        with cls._lock:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            PLUGIN_CONFIG_FILE.write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8"
            )
    # ---------- recent files ----------
    @classmethod
    def load_recent_files(cls) -> list[str]:
        with cls._lock:
            return list(cls._read_state().get("recent_files", []))

    @classmethod
    def add_recent_file(cls, filepath: str) -> None:
        if not filepath:
            return
        with cls._lock:
            state = cls._read_state()
            recent = list(state.get("recent_files", []))
            # 去重并放到最前
            recent = [f for f in recent if f != filepath]
            recent.insert(0, filepath)
            state["recent_files"] = recent[:RECENT_MAX]
            cls._write_state(state)