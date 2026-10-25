# MIT License
# Copyright (c) 2026 Aoan2011
"""大文件检测工具。"""
from pathlib import Path

LARGE_FILE_THRESHOLD = 5 * 1024 * 1024  # 5 MB
HUGE_FILE_THRESHOLD = 50 * 1024 * 1024  # 50 MB


def get_file_size(path: str) -> int:
    try:
        return Path(path).stat().st_size
    except Exception:
        return 0


def is_large_file(path: str) -> bool:
    return get_file_size(path) > LARGE_FILE_THRESHOLD


def is_huge_file(path: str) -> bool:
    return get_file_size(path) > HUGE_FILE_THRESHOLD


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / 1024 / 1024:.1f}MB"