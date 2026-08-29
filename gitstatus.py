'''
MIT License

Copyright (c) 2026 Aoan2011

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''
from textual.widgets import DirectoryTree
from pathlib import Path
from git import Repo, InvalidGitRepositoryError
from typing import Optional, Dict
from rich.text import Text


class GitStatusTree(DirectoryTree):
    """自定义文件树，根据 git 状态显示标记"""

    def __init__(self, path: str, *args, **kwargs):
        super().__init__(path, *args, **kwargs)
        self._repo: Optional[Repo] = None
        self._status_cache: Dict[str, str] = {}  # {绝对路径: 状态代码}
        self._try_load_repo(path)

    def _try_load_repo(self, path: str):
        """尝试加载 git 仓库"""
        try:
            self._repo = Repo(path, search_parent_directories=True)
            self.refresh_status()
        except InvalidGitRepositoryError:
            self._repo = None
            self._status_cache = {}

    def refresh_status(self):
        """刷新所有文件的 git 状态（同步方法）"""
        self._status_cache.clear()
        if not self._repo:
            return
        try:
            porcelain = self._repo.git.status("--porcelain", "--untracked-files=all").splitlines()
            for line in porcelain:
                if len(line) >= 3:
                    x, y = line[0], line[1]
                    path_str = line[3:].strip()
                    # 处理重命名: R  old -> new
                    if "->" in path_str:
                        path_str = path_str.split("->")[-1].strip()
                    abs_path = str((Path(self._repo.working_dir) / path_str).resolve())
                    self._status_cache[abs_path] = f"{x}{y}"
        except Exception:
            pass

    async def reload(self):
        """重载文件树时刷新状态（异步）"""
        self.refresh_status()
        await super().reload()

    def get_status(self, path: str) -> str:
        """返回文件的 git 状态代码（如 'M'、'??'）"""
        return self._status_cache.get(str(path), "")

    def render_label(self, node, meta, style):
        """重写 render_label 来添加状态标记（返回 Text 对象）"""
        label = super().render_label(node, meta, style)  # 父类返回 Text 对象
        if node.data is not None:
            path = node.data.path if hasattr(node.data, 'path') else str(node.data)
            status = self.get_status(path)
            if status:
                marker = ""
                if status.startswith("??"):
                    marker = " [bold green]?"
                elif status.startswith("M"):
                    marker = " [bold yellow]M"
                elif status.startswith("A"):
                    marker = " [bold green]A"
                elif status.startswith("D"):
                    marker = " [bold red]D"
                elif status.startswith("R"):
                    marker = " [bold cyan]R"
                elif status.startswith("U"):
                    marker = " [bold magenta]U"
                if marker:
                    # 将标记转换为 Text 对象并追加，保持返回类型仍为 Text
                    label.append_text(Text.from_markup(marker))
        return label

    def filter_paths(self, paths):
        # 排除 .git 目录
        return [p for p in paths if not p.name == ".git"]