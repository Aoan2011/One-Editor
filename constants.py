# MIT License (与原文件相同)
"""全局常量、默认设置、数据类型。"""
from pathlib import Path
from typing import Optional

VERSION = "1.2.0"

CONFIG_DIR = Path.home() / ".one-editor"
CONFIG_FILE = CONFIG_DIR / "state.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
PLUGIN_CONFIG_FILE = CONFIG_DIR / "plugins.json"

DEFAULT_SETTINGS = {
    "theme": "textual-dark",
    "indent_width": 4,
    "show_line_numbers": True,
    "autosave_interval": 0,
    "tab_width": 4,
    "font_size": 12,
    "language": "zh",
    "wrap": True,
    "indent_type": "spaces",
    "default_dir": str(Path.home()),
    "ollama_url": "http://localhost:11434",
    "ollama_model": "gpt-oss:20b-cloud",
}

LANGUAGE_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".jsx": "javascript",
    ".tsx": "typescript", ".html": "html", ".htm": "html", ".css": "css",
    ".scss": "scss", ".json": "json", ".md": "markdown", ".sh": "bash",
    ".bash": "bash", ".sql": "sql", ".java": "java", ".c": "c", ".cpp": "cpp",
    ".h": "c", ".hpp": "cpp", ".cs": "csharp", ".go": "go", ".rs": "rust",
    ".rb": "ruby", ".php": "php", ".swift": "swift", ".kt": "kotlin",
    ".xml": "xml", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".ini": "ini", ".txt": None,
}

# 文件树忽略目录
IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache", ".tox", "dist", "build",
    ".DS_Store",
}

MAX_OPEN_TABS = 9
COMPANION_PORT = 10045


class FileOperation:
    """文件树操作的可撤销记录。"""
    __slots__ = ("op_type", "path", "old_data", "new_data", "old_path")

    def __init__(self, op_type, path, old_data=None, new_data=None, old_path=None):
        self.op_type = op_type
        self.path = path
        self.old_data = old_data
        self.new_data = new_data
        self.old_path = old_path