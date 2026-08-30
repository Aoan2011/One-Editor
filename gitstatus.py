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
from typing import Optional, Dict, Callable, Tuple
from rich.text import Text

class GitStatusTree(DirectoryTree):
    def __init__(self, path: str, *args, **kwargs):
        super().__init__(path, *args, **kwargs)
        self._repo: Optional[Repo] = None
        self._status_cache: Dict[str, str] = {}
        self._diagnostics_provider: Optional[Callable[[str], Tuple[int, int]]] = None
        self._short_hash: Optional[str] = None
        self._try_load_repo(path)

    def _try_load_repo(self, path: str):
        try:
            self._repo = Repo(path, search_parent_directories=True)
            self.refresh_status()
        except InvalidGitRepositoryError:
            self._repo = None
            self._status_cache = {}
            self._short_hash = None

    def refresh_status(self):
        self._status_cache.clear()
        if not self._repo:
            self._short_hash = None
            return
        try:
            self._short_hash = self._repo.git.rev_parse("HEAD", short=True)
            porcelain = self._repo.git.status("--porcelain", "--untracked-files=all").splitlines()
            for line in porcelain:
                if len(line) >= 3:
                    x, y = line[0], line[1]
                    path_str = line[3:].strip()
                    if "->" in path_str:
                        path_str = path_str.split("->")[-1].strip()
                    abs_path = str((Path(self._repo.working_dir) / path_str).resolve())
                    self._status_cache[abs_path] = f"{x}{y}"
        except Exception:
            pass

    async def reload(self):
        self.refresh_status()
        await super().reload()

    def get_status(self, path: str) -> str:
        return self._status_cache.get(str(Path(path).resolve()), "")

    def set_diagnostics_provider(self, provider: Callable[[str], Tuple[int, int]]):
        self._diagnostics_provider = provider

    def get_diagnostics(self, path: str) -> Tuple[int, int]:
        if self._diagnostics_provider:
            return self._diagnostics_provider(str(Path(path).resolve()))
        return 0, 0

    def render_label(self, node, meta, style):
        label = super().render_label(node, meta, style)
        
        if node.data is not None:
            path = node.data.path if hasattr(node.data, 'path') else str(node.data)
            path = str(Path(path).resolve())
            status = self.get_status(path).strip()
            errors, warnings = self.get_diagnostics(path)

            # 构建标记
            parts = []

            # --- Git 状态部分：Git:符号 <短哈希> ---
            if status:
                # 根据状态映射颜色和符号
                if status.startswith("??"):
                    git_symbol = "[bold green]?[/]"
                    hash_color = "[bold green]"
                elif status.startswith("M"):
                    git_symbol = "[bold yellow]M[/]"
                    hash_color = "[bold yellow]"
                elif status.startswith("A"):
                    git_symbol = "[bold green]A[/]"
                    hash_color = "[bold green]"
                elif status.startswith("D"):
                    git_symbol = "[bold red]D[/]"
                    hash_color = "[bold red]"
                elif status.startswith("R"):
                    git_symbol = "[bold cyan]R[/]"
                    hash_color = "[bold cyan]"
                elif status.startswith("U"):
                    git_symbol = "[bold magenta]U[/]"
                    hash_color = "[bold magenta]"
                else:
                    git_symbol = "[bold white]·[/]"
                    hash_color = "[bold white]"

                # 构建 Git 部分
                git_part = f"Git:{git_symbol}"
                if self._short_hash:
                    git_part += f" {hash_color}<{self._short_hash}>[/]"
                parts.append(git_part)

            # --- 诊断部分：警告数量(橙色粗体) , 错误数量(红色粗体) ---
            diag_parts = []
            if warnings > 0:
                diag_parts.append(f"[bold #FFA500]{warnings}[/]")  # 使用十六进制橙色
            if errors > 0:
                diag_parts.append(f"[bold red]{errors}[/]")
            if diag_parts:
                diag_str = ", ".join(diag_parts)
                parts.append(diag_str)

            if parts:
                marker_str = "   ".join(parts)  # 用3个空格分隔Git部分和诊断部分
                # 调试输出（验证是否生效）
                print(f">>> 最终显示：'{label.plain} ({marker_str})'")
                # 保留图标，追加后缀
                label.append_text(Text.from_markup(f" ({marker_str})"))

        return label

    def filter_paths(self, paths):
        return [p for p in paths if not p.name == ".git"]