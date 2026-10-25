# MIT License
# Copyright (c) 2026 Aoan2011
"""Markdown 实时预览侧栏。"""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

try:
    from rich.markdown import Markdown as RichMarkdown
    _RICH_MD_AVAILABLE = True
except ImportError:
    _RICH_MD_AVAILABLE = False


class MarkdownPreview(Vertical):
    """Markdown 实时预览。挂在 #editor-area 右侧，默认隐藏。"""

    DEFAULT_CSS = """
    MarkdownPreview {
        width: 45%;
        min-width: 30;
        max-width: 70%;
        height: 1fr;
        background: $surface;
        border-left: tall $primary;
        display: none;
    }
    MarkdownPreview > #preview-title {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    MarkdownPreview > #preview-body {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    """

    def __init__(self):
        super().__init__()
        self._body: Static | None = None
        self._last_text: str = ""

    def compose(self) -> ComposeResult:
        yield Static("Markdown 预览", id="preview-title")
        self._body = Static("", id="preview-body")
        yield self._body

    def update_content(self, text: str) -> None:
        """渲染 markdown 文本。重复内容不重渲染。"""
        if not self._body:
            return
        if text == self._last_text:
            return
        self._last_text = text
        if not _RICH_MD_AVAILABLE:
            self._body.update("[yellow]请安装 rich 以启用 Markdown 预览[/]")
            return
        try:
            self._body.update(RichMarkdown(text))
        except Exception as e:
            self._body.update(f"[red]渲染失败: {e}[/]")

    def clear(self) -> None:
        self._last_text = ""
        if self._body:
            self._body.update("")