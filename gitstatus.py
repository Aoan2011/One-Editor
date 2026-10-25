"""Git 状态文件树：修复 render_label 兼容性，加入每文件 hash 缓存和忽略目录。"""
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from git import Repo, InvalidGitRepositoryError
from textual.widgets import DirectoryTree
from rich.text import Text

from constants import IGNORED_DIRS


class GitStatusTree(DirectoryTree):
    def __init__(self, path: str, *args, **kwargs):
        super().__init__(path, *args, **kwargs)
        self._repo: Optional[Repo] = None
        self._status_cache: Dict[str, str] = {}
        self._hash_cache: Dict[str, str] = {}
        self._diagnostics_provider: Optional[Callable[[str], Tuple[int, int]]] = None
        self._try_load_repo(path)

    def _try_load_repo(self, path: str) -> None:
        try:
            self._repo = Repo(path, search_parent_directories=True)
            self.refresh_status()
        except InvalidGitRepositoryError:
            self._repo = None
            self._status_cache = {}
            self._hash_cache = {}

    def refresh_status(self) -> None:
        self._status_cache.clear()
        self._hash_cache.clear()
        if not self._repo:
            return
        try:
            porcelain = self._repo.git.status(
                "--porcelain", "--untracked-files=all"
            ).splitlines()
            for line in porcelain:
                if len(line) < 3:
                    continue
                xy = line[:2]
                path_str = line[3:].strip()
                if "->" in path_str:
                    path_str = path_str.split("->")[-1].strip()
                abs_path = str(
                    (Path(self._repo.working_dir) / path_str).resolve()
                )
                self._status_cache[abs_path] = xy
        except Exception as e:
            self.log.warning(f"git status failed: {e}")

    def get_status(self, path: str) -> str:
        return self._status_cache.get(str(Path(path).resolve()), "")

    def get_short_hash(self, path: str) -> str:
        """每个文件最新的 commit 短 hash（节流缓存）。"""
        if not self._repo:
            return ""
        abs_path = str(Path(path).resolve())
        if abs_path in self._hash_cache:
            return self._hash_cache[abs_path]
        try:
            rel = Path(abs_path).relative_to(Path(self._repo.working_dir).resolve())
            h = self._repo.git.log("-1", "--format=%h", "--", str(rel)).strip()
            self._hash_cache[abs_path] = h
            return h
        except Exception:
            return ""

    def set_diagnostics_provider(
        self, provider: Callable[[str], Tuple[int, int]]
    ) -> None:
        self._diagnostics_provider = provider

    def get_diagnostics(self, path: str) -> Tuple[int, int]:
        if self._diagnostics_provider:
            return self._diagnostics_provider(str(Path(path).resolve()))
        return 0, 0

    # ---------- 兼容不同 Textual 版本的 render_label ----------
    def render_label(self, node, base_style=None, style=None):
        try:
            label = super().render_label(node, base_style, style)
        except TypeError:
            try:
                label = super().render_label(node)
            except TypeError:
                label = Text(str(node.label))

        data = getattr(node, "data", None)
        if data is None:
            return label

        path = getattr(data, "path", None) or str(data)
        path = str(Path(path).resolve())

        status = self.get_status(path)
        errors, warnings = self.get_diagnostics(path)
        short_hash = self.get_short_hash(path) if status else ""

        parts = []
        if status:
            symbol, color = self._status_symbol(status)
            git_part = f"Git:[bold {color}]{symbol}[/]"
            if short_hash:
                git_part += f" [bold {color}]<{short_hash}>[/]"
            parts.append(git_part)

        diag_parts = []
        if warnings > 0:
            diag_parts.append(f"[bold #FFA500]{warnings}[/]")
        if errors > 0:
            diag_parts.append(f"[bold red]{errors}[/]")
        if diag_parts:
            parts.append(", ".join(diag_parts))

        if parts:
            label.append_text(Text.from_markup(f" ({'   '.join(parts)})"))
        return label

    @staticmethod
    def _status_symbol(status: str) -> Tuple[str, str]:
        if status.startswith("??"):
            return "?", "green"
        if status.startswith("M"):
            return "M", "yellow"
        if status.startswith("A"):
            return "A", "green"
        if status.startswith("D"):
            return "D", "red"
        if status.startswith("R"):
            return "R", "cyan"
        if status.startswith("U"):
            return "U", "magenta"
        return "·", "white"

    def filter_paths(self, paths):
        return [p for p in paths if p.name not in IGNORED_DIRS]