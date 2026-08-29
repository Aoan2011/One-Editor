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
        self._try_load_repo(path)

    def _try_load_repo(self, path: str):
        try:
            self._repo = Repo(path, search_parent_directories=True)
            self.refresh_status()
        except InvalidGitRepositoryError:
            self._repo = None
            self._status_cache = {}

    def refresh_status(self):
        self._status_cache.clear()
        if not self._repo:
            return
        try:
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
            status = self.get_status(path).strip()  # <--- 关键修复！去除首尾空格！
            errors, warnings = self.get_diagnostics(path)

            # 构建标记
            parts = []
            if errors > 0 or warnings > 0:
                diag_parts = []
                if errors > 0: diag_parts.append(str(errors))
                if warnings > 0: diag_parts.append(str(warnings))
                parts.append(f"[bold red]{','.join(diag_parts)}[/]")
            
            if status:
                if status.startswith("??"):
                    parts.append("[bold green]?[/]")
                elif status.startswith("M"):
                    parts.append("[bold yellow]M[/]")
                elif status.startswith("A"):
                    parts.append("[bold green]A[/]")
                elif status.startswith("D"):
                    parts.append("[bold red]D[/]")
                elif status.startswith("R"):
                    parts.append("[bold cyan]R[/]")
                elif status.startswith("U"):
                    parts.append("[bold magenta]U[/]")

            if parts:
                marker_str = ", ".join(parts)
                # 【验证】只要这行打印了，界面上就必定显示！
                print(f">>> 最终显示：'{label.plain} ({marker_str})'")
                # 保留图标，追加后缀
                label.append_text(Text.from_markup(f" ({marker_str})"))

        return label

    def filter_paths(self, paths):
        return [p for p in paths if not p.name == ".git"]