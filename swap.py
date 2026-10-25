# MIT License
# Copyright (c) 2026 Aoan2011
"""崩溃恢复：编辑时定期写入 swap 文件，重启时恢复未保存内容。"""
import hashlib
import json
import time
from pathlib import Path

from constants import SWAP_DIR


def _swap_path(filepath: str) -> Path:
    """根据文件路径计算 swap 文件名（内容无关，仅路径相关）。"""
    h = hashlib.sha1(filepath.encode("utf-8")).hexdigest()[:16]
    return SWAP_DIR / f"{h}.swp"


class SwapManager:
    """管理 swap 文件的写入、读取、删除、扫描。"""

    def __init__(self):
        SWAP_DIR.mkdir(parents=True, exist_ok=True)

    def write(self, filepath: str, content: str) -> None:
        """写入 swap（覆盖）。filepath 为原文件路径。"""
        if not filepath:
            return
        try:
            data = {
                "filepath": filepath,
                "content": content,
                "saved_at": time.time(),
                "mtime": Path(filepath).stat().st_mtime
                if Path(filepath).exists() else 0,
            }
            _swap_path(filepath).write_text(
                json.dumps(data, ensure_ascii=False), "utf-8"
            )
        except Exception:
            pass

    def delete(self, filepath: str) -> None:
        try:
            _swap_path(filepath).unlink(missing_ok=True)
        except Exception:
            pass

    def restore(self, filepath: str) -> str | None:
        """读取 swap 内容。"""
        try:
            data = json.loads(_swap_path(filepath).read_text("utf-8"))
            return data.get("content")
        except Exception:
            return None

    def scan(self) -> list[dict]:
        """扫描所有 swap 文件，返回待恢复列表。

        每个条目：{"filepath", "content", "saved_at", "stale"}
        stale=True 表示 swap 比原文件旧（原文件已被正常保存过），可丢弃。
        """
        results = []
        for swp in SWAP_DIR.glob("*.swp"):
            try:
                data = json.loads(swp.read_text("utf-8"))
            except Exception:
                continue
            fp = data.get("filepath", "")
            if not fp:
                swp.unlink(missing_ok=True)
                continue
            p = Path(fp)
            if not p.exists():
                # 原文件不存在：保留，提示用户另存
                results.append({**data, "stale": False})
                continue
            # 原文件 mtime 晚于 swap 保存时间 → 原文件是"最新"的，swap 过期
            if p.stat().st_mtime > data.get("saved_at", 0):
                swp.unlink(missing_ok=True)
                continue
            results.append({**data, "stale": False})
        # 按时间倒序
        results.sort(key=lambda x: x.get("saved_at", 0), reverse=True)
        return results

    def cleanup(self, filepath: str) -> None:
        self.delete(filepath)