# MIT License
# Copyright (c) 2026 Aoan2011
"""One-Editor 主入口。"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Footer, Header, Static

from companion import CompanionServer
from config import ConfigManager
from constants import MAX_OPEN_TABS, FileOperation
from editor_widgets import (
    AxiomEditor, CompletionMenu, FindReplaceBar, GoToLineBar, InputBar,
)
from gitstatus import GitStatusTree
from lsp import LANG_SERVERS, LspClient, path_to_uri, uri_to_path
from panels import (
    FileBrowserPanel, OllamaPanel, OutputPanel, TerminalPanel,
)
from previewer import preview_html, preview_markdown
from screens import (
    AboutScreen, CommandPalette, DiagnosticScreen, DiffScreen,
    EditorContextMenu, ExternalChangeScreen, GlobalSearchScreen,
    OptionListMenu, PluginsScreen, SaveConfirmScreen, SettingsScreen,
    SymbolListScreen,
)
from i18n import TR
from utils import (
    build_shell_command, detect_language, find_project_root,
    format_command, get_file_encoding_and_ending, get_run_command,
    safe_read,
)

CLIPBOARD = {"path": None, "is_cut": False}


class OneEditor(App):
    BINDINGS = [
        Binding("ctrl+n", "new_file", "新建", show=False),
        Binding("ctrl+o", "open_file", "打开", show=False),
        Binding("ctrl+s", "save_file", "保存", show=False),
        Binding("ctrl+shift+s", "save_as", "另存为", show=False),
        Binding("ctrl+w", "close_file", "关闭", show=False),
        Binding("ctrl+q", "quit", "退出", show=False),
        Binding("alt+up", "move_line_up", show=False),
        Binding("alt+down", "move_line_down", show=False),
        Binding("ctrl+f", "show_find", show=False),
        Binding("ctrl+h", "show_replace", show=False),
        Binding("f3", "find_next", show=False),
        Binding("ctrl+g", "goto_line", show=False),
        Binding("ctrl+b", "toggle_file_tree", show=False),
        Binding("f2", "rename_node", show=False),
        Binding("ctrl+shift+m", "move_node", show=False),
        Binding("f12", "goto_definition", show=False),
        Binding("ctrl+shift+o", "show_symbols", show=False),
        Binding("ctrl+shift+i", "show_hover", show=False),
        Binding("ctrl+shift+r", "rename_symbol", show=False),
        Binding("ctrl+shift+a", "code_action", show=False),
        Binding("ctrl+shift+f", "format_document", show=False),
        Binding("escape", "hide_find_replace", show=False),
        Binding("f5", "run", show=False),
        Binding("f6", "build", show=False),
        Binding("f7", "debug", show=False),
        Binding("ctrl+z", "undo_filetree", show=False),
        Binding("ctrl+shift+z", "redo_filetree", show=False),
        Binding("ctrl+`", "toggle_terminal", show=False),
        Binding("ctrl+l", "clear_terminal", show=False),
        Binding("ctrl+shift+p", "command_palette", show=False),
        Binding("ctrl+d", "compare_files", show=False),
        Binding("ctrl+shift+g", "global_search", show=False),
    ]

    CSS = """
    #main-layout { layout: horizontal; }
    #sidebar { width: 50; background: $surface; border-right: tall $primary;
               padding: 0 1; display: block; }
    #editor-area { width: 1fr; layers: default autocomplete overlay; }
    #menu-bar { height: 1; background: $surface; padding: 0 1;
                layout: horizontal; }
    .menu-btn { padding: 0 2; background: $surface; border: none; height: 1; }
    .menu-btn:hover { background: $panel; }
    #diag-counter { dock: right; padding: 0 2; height: 1; border: none; }
    #diag-counter:hover { background: $panel; }
    #tab-bar-container { height: 3; background: $surface; layout: horizontal;
                         border-bottom: tall $primary; }
    .tab-scroll-btn { height: 2; width: 3; border: none; }
    .tab-scroll-btn:hover { background: $panel; }
    #tab-scroll { height: 2; background: $surface; overflow-x: auto;
                  scrollbar-size: 1 1; padding: 0 1; }
    #tab-bar { width: auto; height: 2; }
    .tab-button-container { height: 2; display: block; padding: 0 1; }
    .tab-button { padding: 0 2; background: $surface; border: none; height: 2;
                  margin: 0; border-bottom: solid transparent; max-width: 15;
                  overflow: hidden; }
    .tab-button:hover { background: $panel; }
    .tab-button.active { border-bottom: solid $primary; text-style: bold; }
    .tab-close { padding: 0 1; margin: 0 1 0 0; background: transparent;
                 color: $text-muted; border: none; height: 2; min-width: 2; }
    .tab-close:hover { background: $error; color: $text; }
    #content-container { height: 1fr; }
    TextArea { border: none; background: $surface; padding: 1 2;
               scrollbar-size: 1 1; overflow-x: auto; }
    #status-bar { background: $primary; color: $text; padding: 0 1; height: 1; }
    #tree-container { height: 1fr; width: 30; min-width: 20; max-width: 60;
                      background: $surface; overflow: auto; }
    .tree-resize-handle { width: 3; background: $surface;
                          border-right: tall $primary; }
    """

    def __init__(self):
        super().__init__()
        self._settings = ConfigManager.load_settings()
        self._language = self._settings.get("language", "zh")
        self._initial_files: list[str] = []
        self._tab_data: dict = {}
        self._modified: dict[str, bool] = {}
        self._active_tab_id: str | None = None
        self._tab_counter = 0
        self._current_lang: str | None = None
        self._current_uri: str | None = None
        self._diagnostics_cache: dict[str, list] = {}
        self._file_mtime_cache: dict[str, float] = {}
        self._find_matches: list = []
        self._find_index = -1
        self._find_query = ""
        self._search_history: list[str] = []
        self._replace_history: list[str] = []
        self._file_undo_stack: list[FileOperation] = []
        self._file_redo_stack: list[FileOperation] = []
        self._tree_width = ConfigManager.load_tree_width()
        self._show_file_tree = True
        self._completion_timer = None
        self._tree_refresh_timer = None
        self._is_resizing = False
        self._resize_start_x = 0
        self._resize_start_width = 0
        self._drag_node = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False
        self._context_path = None
        self._diag_label: Button | None = None
        self._resize_handle: Static | None = None
        self.lsp = LspClient()
        self.lsp.set_diagnostics_callback(self._on_diagnostics)
        self.companion: CompanionServer | None = None

    # ========== 生命周期 ==========
    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="menu-bar"):
            yield Button(self._tr("menu_file"), id="menu_file", classes="menu-btn")
            yield Button(self._tr("menu_edit"), id="menu_edit", classes="menu-btn")
            yield Button(self._tr("menu_tools"), id="menu_tools", classes="menu-btn")
            yield Button(self._tr("menu_plugins"), id="menu_plugins", classes="menu-btn")
            yield Button(self._tr("menu_run"), id="btn_run", classes="menu-btn")
            yield Button(self._tr("menu_build"), id="btn_build", classes="menu-btn")
            yield Button(self._tr("menu_debug"), id="btn_debug", classes="menu-btn")
            self._diag_label = Button("", id="diag-counter", variant="default")
            yield self._diag_label
        with Horizontal(id="tab-bar-container"):
            yield Button("◀", id="tab-scroll-left", classes="tab-scroll-btn")
            with ScrollableContainer(id="tab-scroll"):
                self.tab_bar = Horizontal(id="tab-bar")
                yield self.tab_bar
            yield Button("▶", id="tab-scroll-right", classes="tab-scroll-btn")
        self.find_bar = FindReplaceBar(self, self._do_find, self._do_replace)
        yield self.find_bar
        self.goto_bar = GoToLineBar(self)
        yield self.goto_bar
        self.input_bar = InputBar(self)
        yield self.input_bar
        self.file_browser = FileBrowserPanel(self)
        yield self.file_browser
        with Horizontal(id="main-layout"):
            with Container(id="tree-container"):
                self.file_tree = GitStatusTree(Path(".").resolve())
                yield self.file_tree
            # 保存引用，避免 query_one 在 mount 阶段找不到节点
            self._resize_handle = Static(classes="tree-resize-handle")
            yield self._resize_handle
            with Vertical(id="editor-area"):
                self.content_container = Container(id="content-container")
                yield self.content_container
                self.completion_menu = CompletionMenu()
                yield self.completion_menu
                self.output_panel = OutputPanel()
                yield self.output_panel
                self.terminal_panel = TerminalPanel(self)
                yield self.terminal_panel
                self.ollama_panel = OllamaPanel(self)
                yield self.ollama_panel
        self.status_bar = Static(id="status-bar")
        yield self.status_bar
        yield Footer()

    def on_mount(self):
        self.theme = self._settings.get("theme", "textual-dark")
        self._indent_width = self._settings.get("indent_width", 4)
        self._show_line_numbers = self._settings.get("show_line_numbers", True)
        self._autosave_interval = self._settings.get("autosave_interval", 0)

        self._load_state()
        if not self._tab_data:
            self._create_welcome_tab()
        else:
            ids = list(self._tab_data.keys())
            self._active_tab_id = ids[0]
            self.show_tab(ids[0])

        self.file_tree.display = self._show_file_tree
        self.file_tree.set_diagnostics_provider(self._get_diagnostics_for_path)
        self._apply_tree_width()
        self.file_tree.focus()

        # 外部修改检测：set_interval（原来 set_timer 只执行一次）
        self.set_interval(2, self._check_external_changes)
        if self._autosave_interval > 0:
            self.set_interval(self._autosave_interval, self._autosave)

        self._start_companion_if_enabled()

        for fp in self._initial_files:
            p = Path(fp)
            if p.exists() and p.is_file():
                self._open_file_by_path(p)
            elif p.exists() and p.is_dir():
                self.file_tree.path = p
                self.notify(f"已切换目录: {p}", severity="information")
            else:
                self.notify(f"未找到: {fp}", severity="warning")

    # ========== 文件树刷新（节流） ==========
    def _schedule_tree_refresh(self):
        if self._tree_refresh_timer is not None:
            try:
                self._tree_refresh_timer.stop()
            except Exception:
                pass
        self._tree_refresh_timer = self.set_timer(0.5, self._refresh_tree_now)

    def _refresh_tree_now(self):
        self._tree_refresh_timer = None
        try:
            self.file_tree.refresh_status()
            self.run_worker(self.file_tree.reload(),
                            exclusive=True, group="tree-refresh")
        except Exception as e:
            self.log.warning(f"tree refresh failed: {e}")

    # ========== 设置/翻译 ==========
    def _tr(self, key: str, default: str | None = None) -> str:
        return TR.get(self._language, TR["zh"]).get(key, default or key)

    def _save_settings(self):
        ConfigManager.save_settings(self._settings)

    # ========== 状态保存/恢复 ==========
    def _load_state(self):
        state = ConfigManager.load_state()
        self._show_file_tree = state.get("show_file_tree", True)
        self._tree_width = state.get("tree_width", self._tree_width)
        for fp in state.get("open_files", []):
            if not fp:
                continue
            p = Path(fp)
            if p.exists() and p.is_file():
                enc, _ = get_file_encoding_and_ending(str(p))
                content = safe_read(str(p), encoding=enc)
                if content is not None:
                    self.add_new_tab(p.name, content, str(p.resolve()))
        if self._tab_data:
            ids = list(self._tab_data.keys())
            active = state.get("active_index", 0)
            self._active_tab_id = ids[active] if 0 <= active < len(ids) else ids[0]

    def _save_state(self):
        open_files = [
            d.get("filepath")
            for d in self._tab_data.values()
            if not d.get("is_welcome")
        ]
        ids = list(self._tab_data.keys())
        active = ids.index(self._active_tab_id) if self._active_tab_id in ids else 0
        ConfigManager.save_state({
            "open_files": open_files,
            "active_index": active,
            "show_file_tree": self.file_tree.display,
            "tree_width": self._tree_width,
        })

    # ========== 树宽 ==========
    def _apply_tree_width(self):
        try:
            self.query_one("#tree-container").styles.width = self._tree_width
        except Exception:
            pass  # 尚未 mount 或正在销毁

    # ========== 标签管理 ==========
    def add_new_tab(self, title, content="", filepath=None):
        tid = f"tab_{self._tab_counter}"
        self._tab_counter += 1
        container = Horizontal(classes="tab-button-container")
        btn = Button(title, id=tid, classes="tab-button")
        close = Button("×", id=f"close_{tid}", classes="tab-close")
        self.tab_bar.mount(container)
        container.mount(btn, close)
        ta = AxiomEditor(content,
                         show_line_numbers=self._show_line_numbers,
                         language="python")
        ta.wrap = self._settings.get("wrap", True)
        ta.indent_width = self._indent_width
        ta.id = f"textarea_{tid}"
        ta.display = False
        self.content_container.mount(ta)
        self._tab_data[tid] = {
            "title": title, "filepath": filepath, "textarea": ta,
            "button": btn, "close_button": close, "container": container,
            "encoding": "UTF-8", "line_ending": "LF", "is_welcome": False,
        }
        self._modified[tid] = False
        if filepath and Path(filepath).exists():
            self._file_mtime_cache[filepath] = Path(filepath).stat().st_mtime
        if len(self._tab_data) > MAX_OPEN_TABS:
            self.remove_tab(next(iter(self._tab_data)))
        return tid

    def remove_tab(self, tid):
        # 允许关闭最后一个标签，自动新建欢迎页
        if tid not in self._tab_data:
            return
        data = self._tab_data[tid]
        data["container"].remove()
        data["textarea"].remove()
        del self._tab_data[tid]
        del self._modified[tid]
        if self._active_tab_id == tid:
            remaining = list(self._tab_data.keys())
            if remaining:
                self.show_tab(remaining[0])
            else:
                self._create_welcome_tab()
        else:
            self._update_tab_styles()
        self.update_status_bar()
        self._save_state()

    def _create_welcome_tab(self):
        tid = self.add_new_tab("欢迎", "", None)
        self._tab_data[tid]["textarea"].text = self._get_welcome_text()
        self._tab_data[tid]["textarea"].read_only = True
        self._tab_data[tid]["is_welcome"] = True
        self.show_tab(tid)

    def show_tab(self, tid):
        if tid not in self._tab_data:
            return
        for d in self._tab_data.values():
            d["textarea"].display = False
        data = self._tab_data[tid]
        data["textarea"].display = True
        self._active_tab_id = tid
        self._update_tab_styles()
        data["textarea"].focus()
        self._find_matches = []
        self._find_index = -1
        self._hide_find_replace()
        self._schedule_tree_refresh()
        self.update_status_bar()

        fp = data.get("filepath")
        if fp and Path(fp).exists():
            self.terminal_panel.set_cwd(Path(fp).parent)
            if self._diag_label is not None:
                self._diag_label.label = "⚪ 不支持"
            self._start_lsp_for_file(fp, data["textarea"].text)
            self._expand_to_file(fp)
        elif data.get("is_welcome"):
            data["textarea"].text = self._get_welcome_text()

        self._save_state()

    def _update_tab_styles(self):
        for tid, d in self._tab_data.items():
            if tid == self._active_tab_id:
                d["button"].add_class("active")
            else:
                d["button"].remove_class("active")

    def update_tab_modified(self, tid):
        d = self._tab_data.get(tid)
        if not d or d.get("is_welcome"):
            return
        prefix = "● " if self._modified.get(tid) else ""
        d["button"].label = f"{prefix}{d['title']}"

    # ========== 状态栏 ==========
    def update_status_bar(self):
        tid = self._active_tab_id
        if not tid or tid not in self._tab_data:
            return
        d = self._tab_data[tid]
        ta = d["textarea"]
        row, col = ta.selection.start
        total = len(ta.text.splitlines())
        mod_mark = self._tr("status_modified") if self._modified.get(tid) else ""
        sel = ta.selected_text
        sel_info = f" 已选 {len(sel)}" if sel else ""
        lang = ta.language or "plain"
        enc = d.get("encoding", "UTF-8")
        le = d.get("line_ending", "LF")
        size = ""
        fp = d.get("filepath")
        if fp and Path(fp).exists():
            try:
                s = Path(fp).stat().st_size
                size = f" {s}B" if s < 1024 else (
                    f" {s/1024:.1f}KB" if s < 1024 * 1024
                    else f" {s/1024/1024:.1f}MB"
                )
            except Exception:
                pass
        lsp_status = "LSP: 不支持"
        if self._current_lang:
            name = self._get_lsp_server_name(self._current_lang)
            state = (self._tr("status_lsp_connected") if self.lsp.running
                     else self._tr("status_lsp_disconnected"))
            lsp_status = f"LSP: {name} ({state})"
        extra = ""
        if self._find_matches and self._find_index >= 0:
            extra = f" | 匹配 {self._find_index+1}/{len(self._find_matches)}"
        self.status_bar.update(
            f"{d['title']} {mod_mark}  [{lang}] {enc} {le}{size}  "
            f"{self._tr('status_line')} {row+1}/{total}  "
            f"{self._tr('status_col')} {col+1}{sel_info}  |  {lsp_status}{extra}"
        )

    def _get_lsp_server_name(self, lang: str) -> str:
        cmd = LANG_SERVERS.get(lang)
        return cmd[0] if cmd else ""

    def focus_editor(self):
        ed = self.get_current_text_area()
        if ed:
            ed.focus()

    def get_current_tab_id(self):
        return self._active_tab_id

    def get_current_text_area(self):
        if self._active_tab_id and self._active_tab_id in self._tab_data:
            return self._tab_data[self._active_tab_id]["textarea"]
        return None

    def get_current_dir(self) -> str:
        tid = self._active_tab_id
        if tid and tid in self._tab_data:
            fp = self._tab_data[tid].get("filepath")
            if fp and Path(fp).exists():
                return str(Path(fp).parent)
        return str(Path.cwd())

    # ========== 诊断 ==========
    def _get_diagnostics_for_path(self, path):
        try:
            abs_path = str(Path(path).resolve())
            diags = self._diagnostics_cache.get(abs_path, [])
            errors = sum(1 for d in diags if d.get("severity", 1) <= 1)
            warnings = sum(1 for d in diags if d.get("severity", 1) == 2)
            return errors, warnings
        except Exception:
            return 0, 0

    def _on_diagnostics(self, uri: str, diagnostics: list):
        try:
            abs_path = str(Path(uri_to_path(uri)).resolve())
        except Exception:
            abs_path = uri
        self._diagnostics_cache[abs_path] = diagnostics
        if uri != self._current_uri:
            self._schedule_tree_refresh()
            return
        errors = sum(1 for d in diagnostics if d.get("severity", 1) <= 1)
        warnings = sum(1 for d in diagnostics if d.get("severity", 1) == 2)
        if self._diag_label is not None:
            self._diag_label.label = (
                "✓ 🟢" if errors + warnings == 0 else f"🔴:{errors} 🟡:{warnings}"
            )
        ed = self.get_current_text_area()
        if ed and hasattr(ed, "apply_diagnostics"):
            ed.apply_diagnostics(diagnostics)
        self.update_status_bar()
        self._schedule_tree_refresh()

    # ========== LSP ==========
    def _start_lsp_for_file(self, filepath, content):
        lang = detect_language(filepath)
        if not lang or lang not in LANG_SERVERS:
            if self.lsp.running:
                self.run_worker(self.lsp.stop(), exclusive=True, group="lsp")
            self._current_lang = None
            self._current_uri = None
            self._diagnostics_cache.clear()
            if self._diag_label is not None:
                self._diag_label.label = "⚪ 不支持"
            return
        self._current_uri = path_to_uri(filepath)
        if lang != self._current_lang:
            self.run_worker(self._swap_lsp(lang, filepath, content),
                            exclusive=True, group="lsp")
        elif self.lsp.running:
            self.lsp.did_open(filepath, content)

    async def _swap_lsp(self, lang, filepath, content):
        await self.lsp.stop()
        root = os.path.dirname(filepath) or "."
        if await self.lsp.start(lang, root):
            self._current_lang = lang
            self.lsp.did_open(filepath, content)
            if self._diag_label is not None:
                self._diag_label.label = "✓ 🟢"
            self.notify(self._tr("lsp_started").format(lang=lang),
                        severity="information")
        else:
            self._current_lang = None
            self._diagnostics_cache.clear()
            if self._diag_label is not None:
                self._diag_label.label = "⚪ 不支持"
            self.notify(self._tr("lsp_failed").format(lang=lang),
                        severity="error")

    # ========== 文件操作 ==========
    def _open_file_by_path(self, path):
        abs_path = str(Path(path).resolve())
        for tid, d in self._tab_data.items():
            if d.get("filepath") == abs_path:
                self.show_tab(tid)
                return
        if len(self._tab_data) >= MAX_OPEN_TABS:
            self.notify(f"最多同时打开 {MAX_OPEN_TABS} 个文件", severity="error")
            return
        enc, le = get_file_encoding_and_ending(abs_path)
        try:
            content = Path(abs_path).read_text(enc)
        except UnicodeDecodeError:
            content = Path(abs_path).read_text("utf-8", errors="ignore")
        lang = detect_language(abs_path)
        tid = self.add_new_tab(Path(abs_path).name, content, abs_path)
        if lang:
            try:
                self._tab_data[tid]["textarea"].language = lang
            except Exception:
                pass
        self._tab_data[tid]["encoding"] = enc
        self._tab_data[tid]["line_ending"] = le
        self._start_lsp_for_file(abs_path, content)
        self.show_tab(tid)

    def _expand_to_file(self, filepath):
        try:
            self.file_tree.root.expand()
        except Exception:
            pass

    def action_new_file(self):
        if len(self._tab_data) >= MAX_OPEN_TABS:
            self.notify(f"最多同时打开 {MAX_OPEN_TABS} 个文件", severity="error")
            return
        n = sum(1 for d in self._tab_data.values()
                if d["title"].startswith("未命名")) + 1
        self.show_tab(self.add_new_tab(f"未命名 {n}"))

    def action_open_file(self):
        self.file_browser.mode = "open"
        self.file_browser.callback = self._open_file_callback
        current = self._tab_data.get(self._active_tab_id, {}).get("filepath")
        self.file_browser.show(start_path=current)

    def _open_file_callback(self, p):
        if Path(p).is_file():
            self._open_file_by_path(Path(p))
        else:
            self.notify("不是有效文件", severity="error")

    def action_save_as(self):
        self.file_browser.mode = "save"
        self.file_browser.callback = self._save_as_callback
        current = self._tab_data.get(self._active_tab_id, {}).get("filepath")
        self.file_browser.show(start_path=current)

    def _save_as_callback(self, dest_str):
        dest = Path(dest_str)
        tid = self._active_tab_id
        d = self._tab_data.get(tid)
        if not d:
            return
        enc = d.get("encoding", "utf-8")
        try:
            dest.write_text(d["textarea"].text, encoding=enc)
            d["filepath"] = str(dest.resolve())
            d["title"] = dest.name
            d["button"].label = dest.name
            self._modified[tid] = False
            enc2, le = get_file_encoding_and_ending(str(dest))
            d["encoding"] = enc2
            d["line_ending"] = le
            self.update_status_bar()
            self.notify(self._tr("save_success").format(name=dest.name),
                        severity="information")
        except Exception as e:
            self.notify(self._tr("save_fail").format(error=e), severity="error")

    def action_save_file(self, tid=None):
        tid = tid or self._active_tab_id
        d = self._tab_data.get(tid) if tid else None
        if not d:
            return
        if d.get("is_welcome"):
            self.notify("欢迎页不可保存", severity="warning")
            return
        fp = d.get("filepath")
        if not fp:
            return self.action_save_as()
        try:
            Path(fp).write_text(d["textarea"].text,
                                encoding=d.get("encoding", "utf-8"))
            self._modified[tid] = False
            self.update_tab_modified(tid)
            enc, le = get_file_encoding_and_ending(fp)
            d["encoding"] = enc
            d["line_ending"] = le
            self.update_status_bar()
            self.notify(self._tr("save_success").format(name=Path(fp).name),
                        severity="information")
        except Exception as e:
            self.notify(self._tr("save_fail").format(error=e), severity="error")

    def action_close_file(self, tid=None):
        tid = tid or self._active_tab_id
        if self._modified.get(tid):
            def cb(choice):
                if choice == "save":
                    self.action_save_file(tid)
                    self.remove_tab(tid)
                elif choice == "nosave":
                    self.remove_tab(tid)
            self.push_screen(SaveConfirmScreen(self._tr("unsaved"), cb))
        else:
            self.remove_tab(tid)

    def action_quit(self):
        self._save_state()
        if self.lsp.running:
            self.run_worker(self.lsp.stop(), exclusive=True, group="lsp")
        self._stop_companion()
        modified = [(tid, d["title"]) for tid, d in self._tab_data.items()
                    if self._modified.get(tid)]
        if modified:
            def cb(choice):
                if choice == "save":
                    for tid, _ in modified:
                        self.action_save_file(tid)
                    self.exit()
                elif choice == "nosave":
                    self.exit()
            self.push_screen(SaveConfirmScreen(
                self._tr("unsaved_quit").format(
                    files="\n".join(t for _, t in modified)),
                cb,
            ))
        else:
            self.exit()

    def action_move_line_up(self):
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        lines = ed.text.splitlines()
        if len(lines) < 2:
            self.notify(self._tr("need_two_lines"), severity="warning")
            return
        row, col = ed.selection.start
        if row <= 0:
            self.notify(self._tr("first_line"), severity="warning")
            return
        lines[row], lines[row - 1] = lines[row - 1], lines[row]
        ed.text = "\n".join(lines)
        ed.cursor_location = (row - 1, min(col, len(lines[row - 1])))
        self._mark_modified()

    def action_move_line_down(self):
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        lines = ed.text.splitlines()
        if len(lines) < 2:
            self.notify(self._tr("need_two_lines"), severity="warning")
            return
        row, col = ed.selection.start
        if row >= len(lines) - 1:
            self.notify(self._tr("last_line"), severity="warning")
            return
        lines[row], lines[row + 1] = lines[row + 1], lines[row]
        ed.text = "\n".join(lines)
        ed.cursor_location = (row + 1, min(col, len(lines[row + 1])))
        self._mark_modified()

    def _mark_modified(self):
        tid = self._active_tab_id
        if tid:
            self._modified[tid] = True
            self.update_tab_modified(tid)
            self.update_status_bar()

    # ========== 查找/替换 ==========
    def _show_find_replace(self, mode="find"):
        self.find_bar.display = True
        self.find_bar.set_mode(mode)

    def _hide_find_replace(self):
        self.find_bar.display = False
        self.focus_editor()

    def action_show_find(self):
        self._show_find_replace("find")

    def action_show_replace(self):
        self._show_find_replace("replace")

    def action_hide_find_replace(self):
        self._hide_find_replace()

    def action_find_next(self):
        if not self._find_matches:
            self.notify("请先执行查找", severity="warning")
            return
        self._find_index = (self._find_index + 1) % len(self._find_matches)
        self._goto_match(self._find_index)

    def _do_find(self, query, case_sensitive, use_regex):
        if query and (not self._search_history or self._search_history[-1] != query):
            self._search_history.append(query)
        self._find_query = query
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            self.notify("只读文件不可查找", severity="warning")
            return
        matches = self._find_all(query, case_sensitive, use_regex)
        self._find_matches = matches
        if not matches:
            self.notify(self._tr("no_match"), severity="warning")
            self._find_index = -1
        else:
            self._find_index = 0
            self._goto_match(0)
            self.notify(self._tr("match_count").format(count=len(matches)),
                        severity="information")
        self.update_status_bar()

    def _find_all(self, query, case_sensitive, use_regex):
        ed = self.get_current_text_area()
        if not ed:
            return []
        lines = ed.text.splitlines()
        matches = []
        if use_regex:
            try:
                pattern = re.compile(
                    query, 0 if case_sensitive else re.IGNORECASE
                )
            except re.error:
                self.notify("无效正则", severity="error")
                return []
            for row, line in enumerate(lines):
                for m in pattern.finditer(line):
                    matches.append((row, m.start(), m.end()))
        else:
            for row, line in enumerate(lines):
                pos = 0
                while True:
                    idx = line.find(query, pos)
                    if idx == -1:
                        break
                    matches.append((row, idx, idx + len(query)))
                    pos = idx + 1
        return matches

    def _goto_match(self, idx):
        if not self._find_matches or not (0 <= idx < len(self._find_matches)):
            return
        ed = self.get_current_text_area()
        row, start, end = self._find_matches[idx]
        ed.selection = ((row, start), (row, end))
        ed.scroll_to((row, 0), animate=False)
        self._find_index = idx
        self.update_status_bar()

    def _do_replace(self, find_text, replace_text, replace_all, cs, ur):
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            self.notify("只读文件不可替换", severity="warning")
            return
        if replace_all:
            matches = self._find_all(find_text, cs, ur)
            if not matches:
                self.notify(self._tr("no_match"), severity="warning")
                return
            lines = ed.text.splitlines()
            new_lines = lines[:]
            cnt = 0
            if ur:
                try:
                    pat = re.compile(find_text, 0 if cs else re.IGNORECASE)
                except re.error:
                    self.notify("无效正则", severity="error")
                    return
                for i, line in enumerate(new_lines):
                    nl, c = pat.subn(replace_text, line)
                    if c:
                        new_lines[i] = nl
                        cnt += c
            else:
                for i, line in enumerate(new_lines):
                    if find_text in line:
                        cnt += line.count(find_text)
                        new_lines[i] = line.replace(find_text, replace_text)
            if cnt:
                ed.text = "\n".join(new_lines)
                self._mark_modified()
                self.notify(f"替换了 {cnt} 处", severity="information")
                self._find_matches = []
                self._find_index = -1
                self.update_status_bar()
        else:
            if not self._find_matches or self._find_index < 0:
                self.notify("请先执行查找", severity="warning")
                return
            row, start, end = self._find_matches[self._find_index]
            lines = ed.text.splitlines()
            line = lines[row]
            lines[row] = line[:start] + replace_text + line[end:]
            ed.text = "\n".join(lines)
            self._find_matches = self._find_all(find_text, cs, ur)
            self._find_index = 0 if self._find_matches else -1
            if self._find_matches:
                self._goto_match(0)
            self._mark_modified()

    # ========== 转到行 ==========
    def action_goto_line(self):
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            self.notify("没有可用的编辑器", severity="warning")
            return
        total = len(ed.text.splitlines())
        self.goto_bar.input.placeholder = self._tr(
            "goto_line_prompt").format(total=total)
        self.goto_bar.display = True
        self.goto_bar.input.value = ""
        self.goto_bar.input.focus()

    def _do_goto_line(self, text: str):
        try:
            n = int(text.strip())
        except ValueError:
            self.notify(self._tr("invalid_line"), severity="error")
            return
        ed = self.get_current_text_area()
        if not ed:
            return
        total = len(ed.text.splitlines())
        if not (1 <= n <= total):
            self.notify(self._tr("line_out_of_range").format(total=total),
                        severity="warning")
            return
        ed.cursor_location = (n - 1, 0)
        ed.scroll_to((n - 1, 0), animate=False)
        self._hide_goto_bar()

    def _hide_goto_bar(self):
        self.goto_bar.display = False
        self.focus_editor()

    # ========== 菜单回调 ==========
    def on_button_pressed(self, event):
        bid = event.button.id
        if bid and bid.startswith("close_"):
            tid = bid.replace("close_", "")
            if tid in self._tab_data:
                self.action_close_file(tid)
                return
        if bid and bid in self._tab_data:
            self.show_tab(bid)
            return
        if bid == "tab-scroll-left":
            try:
                sb = self.query_one("#tab-scroll")
                sb.scroll_to(sb.scroll_offset.x - 50, 0, animate=True)
            except Exception:
                pass
        elif bid == "tab-scroll-right":
            try:
                sb = self.query_one("#tab-scroll")
                sb.scroll_to(sb.scroll_offset.x + 50, 0, animate=True)
            except Exception:
                pass
        elif bid == "menu_file":
            self._show_file_menu()
        elif bid == "menu_edit":
            self._show_edit_menu()
        elif bid == "menu_tools":
            self._show_tools_menu()
        elif bid == "menu_plugins":
            self.push_screen(PluginsScreen(self))
        elif bid == "btn_run":
            self.action_run()
        elif bid == "btn_build":
            self.action_build()
        elif bid == "btn_debug":
            self.action_debug()
        elif bid == "diag-counter":
            self.action_show_diagnostics()

    def _show_file_menu(self):
        items = [
            {"label": self._tr("new"), "action": "new"},
            {"label": self._tr("open"), "action": "open"},
            {"label": self._tr("save"), "action": "save"},
            {"label": self._tr("save_as"), "action": "save_as"},
            {"label": self._tr("close"), "action": "close"},
            {"label": self._tr("quit"), "action": "quit"},
        ]
        actions = {
            "new": self.action_new_file, "open": self.action_open_file,
            "save": self.action_save_file, "save_as": self.action_save_as,
            "close": self.action_close_file, "quit": self.action_quit,
        }
        self.push_screen(OptionListMenu(self._tr("menu_file"), items,
                                        lambda a: actions[a]()))

    def _show_edit_menu(self):
        items = [
            {"label": self._tr("find"), "action": "find"},
            {"label": self._tr("replace"), "action": "replace"},
            {"label": self._tr("goto"), "action": "goto"},
            {"label": self._tr("format"), "action": "format"},
        ]
        actions = {
            "find": self.action_show_find, "replace": self.action_show_replace,
            "goto": self.action_goto_line, "format": self.action_format_document,
        }
        self.push_screen(OptionListMenu(self._tr("menu_edit"), items,
                                        lambda a: actions[a]()))

    def _show_tools_menu(self):
        items = [
            {"label": self._tr("settings"), "action": "settings"},
            {"label": self._tr("about"), "action": "about"},
            {"label": self._tr("global_search"), "action": "search"},
            {"label": self._tr("terminal"), "action": "terminal"},
            {"label": self._tr("command_palette"), "action": "palette"},
            {"label": self._tr("compare_files"), "action": "diff"},
        ]
        actions = {
            "settings": lambda: self.push_screen(SettingsScreen(self)),
            "about": lambda: self.push_screen(AboutScreen()),
            "search": self.action_global_search,
            "terminal": self.action_toggle_terminal,
            "palette": self.action_command_palette,
            "diff": self.action_compare_files,
        }
        self.push_screen(OptionListMenu(self._tr("menu_tools"), items,
                                        lambda a: actions[a]()))

    # ========== 命令面板 / 截图 / 全局搜索 ==========
    def _get_commands(self) -> dict:
        cmds = {}
        for b in self.BINDINGS:
            if b.description and b.action:
                cmds.setdefault(b.action, f"{b.key}   {b.description}")
        cmds.setdefault("compare_files", self._tr("compare_files"))
        cmds.setdefault("screenshot", "📸 截图")
        cmds.setdefault("change_theme", "🎨 切换主题")
        return cmds

    def action_command_palette(self):
        def cb(a):
            if a == "change_theme":
                themes = ["textual-dark", "textual-light", "dracula", "nord"]
                try:
                    idx = themes.index(self.theme)
                    nt = themes[(idx + 1) % len(themes)]
                except Exception:
                    nt = themes[0]
                self.theme = nt
                self._settings["theme"] = nt
                self._save_settings()
                self.notify(self._tr("theme_changed").format(theme=nt),
                            severity="information")
                return
            if hasattr(self, f"action_{a}"):
                getattr(self, f"action_{a}")()
            else:
                self.notify(f"未知命令: {a}", severity="warning")
        self.push_screen(CommandPalette(self._get_commands(), cb))

    def action_screenshot(self):
        try:
            path = Path.home() / (
                f"one_editor_screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
            )
            self.save_screenshot(str(path))
            self.notify(self._tr("screenshot_saved").format(path=path),
                        severity="information")
        except Exception as e:
            self.notify(f"截图失败: {e}", severity="error")

    def action_compare_files(self):
        tabs = [d for d in self._tab_data.values() if not d.get("is_welcome")]
        if len(tabs) < 2:
            self.notify(self._tr("no_diff_tabs"), severity="warning")
            return
        self.push_screen(DiffScreen(tabs[0]["textarea"].text,
                                    tabs[1]["textarea"].text,
                                    tabs[0]["title"], tabs[1]["title"]))

    def action_global_search(self):
        root = self.get_current_dir()

        def cb(path, line):
            self._open_file_by_path(Path(path))

            def jump():
                ed = self.get_current_text_area()
                if ed:
                    ed.cursor_location = (line - 1, 0)
                    ed.focus()
            self.call_after_refresh(jump)

        self.push_screen(GlobalSearchScreen(root, cb))

    # ========== LSP 操作 ==========
    def action_show_symbols(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"), severity="warning")
            return
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        self.lsp.did_change(ed.text)
        self.run_worker(self._fetch_symbols(), exclusive=True, group="symbols")

    async def _fetch_symbols(self):
        symbols = await self.lsp.document_symbol()
        if not symbols:
            self.notify(self._tr("no_symbols"), severity="warning")
            return
        self.push_screen(SymbolListScreen(symbols, self))

    def _jump_to_symbol(self, line, col):
        ed = self.get_current_text_area()
        if ed:
            ed.cursor_location = (line, col)
            ed.focus()

    def action_show_hover(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"), severity="warning")
            return
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        row, col = ed.cursor_location
        self.lsp.did_change(ed.text)
        self.run_worker(self._fetch_hover(row, col), exclusive=True, group="hover")

    async def _fetch_hover(self, row, col):
        result = await self.lsp.hover(row, col)
        if result:
            self.notify(f"📖 {result}", severity="information", timeout=5)
        else:
            self.notify(self._tr("no_hover"), severity="warning")

    def action_show_diagnostics(self):
        if not self.lsp.running:
            self.notify("LSP 未运行", severity="warning")
            return
        diags = self._diagnostics_cache.get(self._current_uri or "", [])
        if not diags and self._current_uri:
            try:
                abs_path = str(Path(uri_to_path(self._current_uri)).resolve())
                diags = self._diagnostics_cache.get(abs_path, [])
            except Exception:
                pass
        if not diags:
            self.notify("当前文件没有诊断信息", severity="information")
        else:
            self.push_screen(DiagnosticScreen(diags, self))

    def action_goto_definition(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"), severity="warning")
            return
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        self.lsp.did_change(ed.text)
        row, col = ed.cursor_location
        self.run_worker(self._do_goto_definition(row, col),
                        exclusive=True, group="goto-def")

    async def _do_goto_definition(self, row, col):
        result = await self.lsp.goto_definition(row, col)
        if not result:
            self.notify(self._tr("goto_def_fail"), severity="warning")
            return
        self._open_file_by_path(Path(uri_to_path(result["uri"])))

        def jump():
            ed = self.get_current_text_area()
            if ed:
                ed.cursor_location = (result["line"], result["col"])
                ed.focus()
        self.call_after_refresh(jump)

    def action_rename_symbol(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"), severity="warning")
            return
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        row, col = ed.cursor_location
        self.lsp.did_change(ed.text)
        self.show_input_bar(
            self._tr("rename_prompt"),
            lambda n: self.run_worker(self._do_rename(row, col, n),
                                      exclusive=True, group="rename"),
        )

    async def _do_rename(self, row, col, new_name):
        result = await self.lsp.rename(row, col, new_name)
        if not result:
            self.notify(self._tr("rename_fail"), severity="error")
            return
        ed = self.get_current_text_area()
        if not ed:
            return
        if "changes" in result and self._current_uri in result["changes"]:
            for edit in reversed(result["changes"][self._current_uri]):
                r = edit.get("range", {})
                s, e = r.get("start", {}), r.get("end", {})
                ed.replace(edit.get("newText", ""),
                           (s.get("line", 0), s.get("character", 0)),
                           (e.get("line", 0), e.get("character", 0)))
            self.notify(self._tr("rename_success"), severity="information")
        elif "documentChanges" in result:
            for ch in result["documentChanges"]:
                if ch.get("textDocument", {}).get("uri") == self._current_uri:
                    for edit in reversed(ch.get("edits", [])):
                        r = edit.get("range", {})
                        s, e = r.get("start", {}), r.get("end", {})
                        ed.replace(edit.get("newText", ""),
                                   (s.get("line", 0), s.get("character", 0)),
                                   (e.get("line", 0), e.get("character", 0)))
                    self.notify(self._tr("rename_success"),
                                severity="information")
                    return
        else:
            self.notify("重命名未在当前文件内生效", severity="warning")

    def action_code_action(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"), severity="warning")
            return
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        row, col = ed.cursor_location
        self.lsp.did_change(ed.text)
        self.run_worker(self._fetch_code_actions(row, col),
                        exclusive=True, group="code-action")

    async def _fetch_code_actions(self, row, col):
        actions = await self.lsp.code_action(row, col)
        if not actions:
            self.notify("没有可用的代码操作", severity="information")
            return
        items = [
            {"label": a.get("title") if isinstance(a, dict) else str(a),
             "action": a}
            for a in actions
        ]
        self.push_screen(OptionListMenu(self._tr("code_action"), items,
                                        self._apply_code_action))

    def _apply_code_action(self, action):
        if not isinstance(action, dict):
            self.notify("未包含可执行的修改内容", severity="warning")
            return
        ed = self.get_current_text_area()
        if not ed:
            return
        edits = []
        edit = action.get("edit") or {}
        if "changes" in edit:
            for uri, tedits in edit["changes"].items():
                if uri == self._current_uri:
                    edits.extend(tedits)
        if "documentChanges" in edit:
            for ch in edit["documentChanges"]:
                if ch.get("textDocument", {}).get("uri") == self._current_uri:
                    edits.extend(ch.get("edits", []))
        if edits:
            for edit in reversed(edits):
                r = edit.get("range", {})
                s, e = r.get("start", {}), r.get("end", {})
                ed.replace(edit.get("newText", ""),
                           (s.get("line", 0), s.get("character", 0)),
                           (e.get("line", 0), e.get("character", 0)))
            self.notify("已应用快速修复", severity="information")
            return
        if "command" in action and self.lsp.running:
            cmd = action["command"]
            args = action.get("arguments", [])

            async def run():
                await self.lsp.execute_command(cmd, args)
                self.notify("修复命令已执行", severity="information")
            self.run_worker(run())
        else:
            self.notify("该操作需服务器支持，已跳过", severity="warning")

    def action_format_document(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"), severity="warning")
            return
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        self.lsp.did_change(ed.text)
        self.run_worker(self._do_format(), exclusive=True, group="format")

    async def _do_format(self):
        result = await self.lsp.format_document()
        if not result:
            self.notify(self._tr("format_fail"), severity="warning")
            return
        ed = self.get_current_text_area()
        if not ed:
            return
        # 逆序应用，避免偏移错乱
        for edit in reversed(result):
            r = edit.get("range", {})
            s, e = r.get("start", {}), r.get("end", {})
            ed.replace(edit.get("newText", ""),
                       (s.get("line", 0), s.get("character", 0)),
                       (e.get("line", 0), e.get("character", 0)))
        self.notify(self._tr("format_success"), severity="information")

    # ========== 补全 ==========
    def on_text_area_changed(self, event):
        if event.text_area is self.get_current_text_area():
            tid = self._active_tab_id
            if tid and not self._tab_data[tid].get("is_welcome"):
                self._modified[tid] = True
                self.update_tab_modified(tid)
            self._schedule_completion()

    def _schedule_completion(self):
        if self._completion_timer:
            try:
                self._completion_timer.stop()
            except Exception:
                pass
        self._completion_timer = self.set_timer(0.1, self._trigger_completion)

    def _trigger_completion(self):
        if not self.lsp.running:
            return
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        fp = self._tab_data.get(self._active_tab_id, {}).get("filepath")
        if not fp or detect_language(fp) != self._current_lang:
            return
        self.lsp.did_change(ed.text)
        row, col = ed.cursor_location
        lines = ed.text.splitlines()
        if row < len(lines) and col > 0:
            ch = lines[row][col - 1]
            if ch.isalnum() or ch in "_.":
                self.run_worker(self._fetch_completions(row, col),
                                exclusive=True, group="completion")

    async def _fetch_completions(self, row, col):
        items = await self.lsp.complete(row, col)
        if not items:
            self.completion_menu.hide()
            return
        ed = self.get_current_text_area()
        if not ed:
            return
        # 光标屏幕坐标：不同 Textual 版本 API 不同，统一兜底
        try:
            co = ed.cursor_screen_offset
            ar = self.query_one("#editor-area").region
            self.completion_menu.show(items, (co.x - ar.x, co.y - ar.y + 1))
        except Exception:
            self.completion_menu.show(items, (0, 0))

    def _insert_completion(self, item):
        ed = self.get_current_text_area()
        if not ed or ed.read_only:
            return
        self.completion_menu.hide()
        for edit in reversed(item.get("additionalTextEdits", [])):
            r = edit.get("range", {})
            s, e = r.get("start", {}), r.get("end", {})
            ed.replace(edit.get("newText", ""),
                       (s.get("line", 0), s.get("character", 0)),
                       (e.get("line", 0), e.get("character", 0)))
        insert = item.get("insertText") or item["label"]
        row, col = ed.cursor_location
        lines = ed.text.splitlines()
        line = lines[row] if row < len(lines) else ""
        ws = col
        while ws > 0 and (line[ws - 1].isalnum() or line[ws - 1] == "_"):
            ws -= 1
        clean = insert.split("(")[0] if "(" in insert else insert
        ed.replace(clean, (row, ws), (row, col))
        ed.focus()

    # ========== 文件树交互 ==========
    def on_directory_tree_file_selected(self, event):
        if event.path.is_file():
            self._open_file_by_path(event.path)

    def action_toggle_file_tree(self):
        self.file_tree.display = not self.file_tree.display
        self._show_file_tree = self.file_tree.display
        self.notify(self._tr("tree_show") if self.file_tree.display
                    else self._tr("tree_hide"),
                    severity="information")

    def action_rename_node(self):
        node = self.file_tree.cursor_node
        if node is None or node.data is None:
            self.notify("请先在文件树中选中节点", severity="warning")
            return
        p = getattr(node.data, "path", None) or str(node.data)
        self._context_path = Path(p)
        self._filetree_menu_callback("rename")

    def action_move_node(self):
        node = self.file_tree.cursor_node
        if node is None or node.data is None:
            self.notify("请先在文件树中选中节点", severity="warning")
            return
        p = getattr(node.data, "path", None) or str(node.data)
        self._context_path = Path(p)
        self._filetree_menu_callback("move_to")

    def _refresh_file_tree(self):
        try:
            self.file_tree.refresh_status()
        except Exception:
            pass
        self._schedule_tree_refresh()
        self.refresh()

    # ---- 文件操作撤销栈 ----
    def _push_file_operation(self, op):
        self._file_undo_stack.append(op)
        self._file_redo_stack.clear()

    def _apply_file_operation(self, op, undo):
        """undo=True 还原；undo=False 重做（继续执行）。"""
        try:
            if op.op_type == "create":
                if undo:
                    if op.path.is_file():
                        op.path.unlink()
                    elif op.path.is_dir():
                        shutil.rmtree(op.path)
                else:
                    if op.path.suffix:
                        op.path.touch()
                    else:
                        op.path.mkdir(exist_ok=True)
            elif op.op_type == "delete":
                if undo:
                    if op.old_data is not None:
                        op.path.write_text(op.old_data, "utf-8")
                    else:
                        op.path.mkdir(exist_ok=True)
                else:
                    if op.path.is_file():
                        op.path.unlink()
                    elif op.path.is_dir():
                        shutil.rmtree(op.path)
            elif op.op_type == "rename":
                src, dst = (op.path, op.old_path) if undo else (op.old_path, op.path)
                src.rename(dst)
            elif op.op_type == "move":
                src, dst = (op.path, op.old_path) if undo else (op.old_path, op.path)
                shutil.move(str(src), str(dst))
        except Exception as e:
            self.notify(f"操作失败: {e}", severity="error")

    def action_undo_filetree(self):
        if not self._file_undo_stack:
            self.notify(self._tr("no_undo"), severity="information")
            return
        op = self._file_undo_stack.pop()
        self._file_redo_stack.append(op)
        self._apply_file_operation(op, True)
        self._refresh_file_tree()

    def action_redo_filetree(self):
        if not self._file_redo_stack:
            self.notify(self._tr("no_redo"), severity="information")
            return
        op = self._file_redo_stack.pop()
        self._file_undo_stack.append(op)
        self._apply_file_operation(op, False)
        self._refresh_file_tree()

    def _filetree_menu_callback(self, action):
        global CLIPBOARD
        p = self._context_path
        if p is None:
            return

        def do_create(is_folder):
            def cb(name):
                if not name:
                    return
                np = p / name
                if np.exists():
                    self.notify(self._tr("file_exists"), severity="error")
                    return
                (np.mkdir() if is_folder else np.touch())
                self._push_file_operation(FileOperation("create", np))
                self._refresh_file_tree()
                if not is_folder:
                    self._open_file_by_path(np)
            self.show_input_bar(
                "输入文件夹名:" if is_folder else "输入文件名:", cb
            )

        if action == "new_file":
            do_create(False)
        elif action == "new_folder":
            do_create(True)
        elif action == "open" and p.is_file():
            self._open_file_by_path(p)
        elif action == "open_dir" and p.is_dir():
            self.file_tree.path = p
            self._refresh_file_tree()
        elif action == "rename":
            def cb(name):
                if not name:
                    return
                np = p.parent / name
                if np.exists():
                    self.notify(self._tr("file_exists"), severity="error")
                    return
                old = p
                p.rename(np)
                self._push_file_operation(
                    FileOperation("rename", np, old_path=old))
                self._refresh_file_tree()
                abs_old = str(old.resolve())
                abs_new = str(np.resolve())
                for tid, d in self._tab_data.items():
                    if d.get("filepath") == abs_old:
                        d["filepath"] = abs_new
                        d["title"] = np.name
                        d["button"].label = np.name
                        break
                self.update_status_bar()
            self.show_input_bar("输入新名称:", cb)
        elif action == "move_to":
            def cb(target):
                td = Path(target.strip())
                if not td.is_dir():
                    self.notify("目标目录不存在", severity="error")
                    return
                dest = td / p.name
                if dest.exists():
                    self.notify("目标已存在", severity="error")
                    return
                old = p
                shutil.move(str(p), str(dest))
                self._push_file_operation(
                    FileOperation("move", dest, old_path=old))
                self._refresh_file_tree()
                abs_old = str(old.resolve())
                abs_new = str(dest.resolve())
                for tid, d in self._tab_data.items():
                    if d.get("filepath") == abs_old:
                        d["filepath"] = abs_new
                        d["title"] = dest.name
                        d["button"].label = dest.name
                        break
                self.update_status_bar()
            self.show_input_bar("输入目标目录路径:", cb)
        elif action == "copy":
            CLIPBOARD["path"] = p
            CLIPBOARD["is_cut"] = False
            self.notify(f"已复制: {p.name}", severity="information")
        elif action == "paste":
            src = CLIPBOARD.get("path")
            if not src or not src.exists():
                self.notify("剪贴板为空", severity="warning")
                return
            dest = p / src.name
            if dest.exists():
                self.notify("目标已存在", severity="error")
                return
            try:
                if src.is_file():
                    shutil.copy2(str(src), str(dest))
                else:
                    shutil.copytree(str(src), str(dest))
                self.notify(f"已粘贴: {dest.name}", severity="information")
                self._refresh_file_tree()
            except Exception as e:
                self.notify(f"粘贴失败: {e}", severity="error")
        elif action == "delete":
            def confirm(ok):
                if not ok:
                    return
                try:
                    old_data = (p.read_text("utf-8", errors="ignore")
                                if p.is_file() else None)
                    (p.unlink() if p.is_file() else shutil.rmtree(p))
                    self._push_file_operation(
                        FileOperation("delete", p, old_data=old_data))
                    self._refresh_file_tree()
                    abs_p = str(p.resolve())
                    for tid, d in list(self._tab_data.items()):
                        if d.get("filepath") == abs_p:
                            self.remove_tab(tid)
                except Exception as e:
                    self.notify(f"删除失败: {e}", severity="error")
            self.push_screen(SaveConfirmScreen(f"确定删除 {p.name} 吗？", confirm))

    # ========== 运行 / 构建 / 调试 ==========
    def action_run(self):
        tid = self._active_tab_id
        if not tid:
            return
        d = self._tab_data[tid]
        if d.get("is_welcome") or not d.get("filepath"):
            self.notify(self._tr("no_file"), severity="warning")
            return
        fp = d["filepath"]
        self.action_save_file(tid)

        cfg = ConfigManager.load_plugin_config()
        lang = detect_language(fp)
        if lang and lang in cfg and cfg[lang].get("run_cmd"):
            cmd = format_command(cfg[lang]["run_cmd"], fp)
            self.output_panel.display = True
            self.output_panel.set_command(cmd)
            self.output_panel.clear()
            self.run_worker(self._run_process(cmd, fp, shell=True),
                            exclusive=True, group="run")
            return

        ext = Path(fp).suffix.lower()
        if ext in (".md", ".markdown"):
            try:
                preview_markdown(fp)
                self.notify("Markdown 预览已打开", severity="information")
            except Exception as e:
                self.notify(f"预览失败: {e}", severity="error")
            return
        if ext in (".html", ".htm"):
            try:
                preview_html(fp)
            except Exception as e:
                self.notify(f"预览失败: {e}", severity="error")
            return

        cmd = get_run_command(fp)
        if not cmd:
            self.notify(self._tr("unsupported_lang"), severity="warning")
            return
        shell = any(x in cmd for x in ("&&", "||", "|", ">", "<"))
        self.output_panel.display = True
        self.output_panel.set_command(cmd)
        self.output_panel.clear()
        self.run_worker(self._run_process(cmd, fp, shell=shell),
                        exclusive=True, group="run")

    def action_build(self):
        tid = self._active_tab_id
        if not tid:
            return
        d = self._tab_data[tid]
        if d.get("is_welcome") or not d.get("filepath"):
            self.notify(self._tr("no_file"), severity="warning")
            return
        fp = d["filepath"]

        cfg = ConfigManager.load_plugin_config()
        lang = detect_language(fp)
        if lang and lang in cfg and cfg[lang].get("compile_cmd"):
            cmd = format_command(cfg[lang]["compile_cmd"], fp)
            self.output_panel.display = True
            self.output_panel.set_command(cmd)
            self.output_panel.clear()
            self.run_worker(self._run_process(cmd, shell=True),
                            exclusive=True, group="build")
            return

        root = find_project_root(Path(fp).parent)
        if not root:
            self.notify(self._tr("no_project"), severity="warning")
            return
        cwd, cmds = root, None
        if (root / "CMakeLists.txt").exists():
            b = root / "build"
            b.mkdir(exist_ok=True)
            cmds, cwd = ["cmake", "..", "&&", "cmake", "--build", "."], b
        elif (root / "package.json").exists():
            cmds = ["npm", "install", "&&", "npm", "run", "build"]
        elif (root / "Cargo.toml").exists():
            cmds = ["cargo", "build"]
        elif (root / "go.mod").exists():
            cmds = ["go", "build"]
        else:
            self.notify(self._tr("no_build_system"), severity="warning")
            return
        self.output_panel.display = True
        self.output_panel.set_command(cmds)
        self.output_panel.clear()
        self.run_worker(self._run_process(cmds, cwd=cwd, shell=True),
                        exclusive=True, group="build")

    def action_debug(self):
        tid = self._active_tab_id
        if not tid:
            return
        d = self._tab_data[tid]
        if d.get("is_welcome") or not d.get("filepath"):
            self.notify(self._tr("no_file"), severity="warning")
            return
        fp = d["filepath"]
        if Path(fp).suffix.lower() != ".py":
            self.notify(self._tr("debug_py_only"), severity="information")
            return
        try:
            if os.name == "nt":
                subprocess.Popen(
                    ["start", "cmd", "/k", "python", "-m", "pdb", fp],
                    shell=True)
            else:
                subprocess.Popen(["xterm", "-e", "python", "-m", "pdb", fp])
            self.notify("调试器已启动", severity="information")
        except Exception as e:
            self.notify(f"启动失败: {e}", severity="error")

    async def _run_process(self, cmd, cwd=None, shell=False):
        # 修复：显式判断 cwd，避免 `cwd or ... if ... else ...` 优先级错误
        if isinstance(cmd, str):
            actual_cmd = cmd
        elif shell:
            actual_cmd = build_shell_command(cmd)
        else:
            actual_cmd = cmd

        if cwd:
            if Path(str(cwd)).is_file():
                actual_cwd = str(Path(str(cwd)).parent)
            else:
                actual_cwd = str(cwd)
        elif isinstance(cmd, list) and cmd and os.path.isfile(cmd[-1]):
            actual_cwd = os.path.dirname(cmd[-1])
        else:
            actual_cwd = os.getcwd()

        try:
            if shell:
                proc = await asyncio.create_subprocess_shell(
                    actual_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=actual_cwd,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *actual_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=actual_cwd,
                )
        except Exception as e:
            self.output_panel.output_area.text += f"\n[启动失败] {e}\n"
            return

        async def pump(stream):
            while True:
                line = await stream.readline()
                if not line:
                    break
                for enc in ("utf-8", "gbk"):
                    try:
                        text = line.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    text = line.decode("utf-8", errors="replace")
                self.output_panel.output_area.text += text
                self.output_panel._scroll_to_bottom()

        await asyncio.gather(pump(proc.stdout), pump(proc.stderr),
                             return_exceptions=True)
        await proc.wait()
        self.notify(self._tr("run_success").format(code=proc.returncode),
                    severity="information")

    # ========== 终端 / Ollama ==========
    def action_toggle_terminal(self):
        if self.terminal_panel.display:
            self.terminal_panel.display = False
            self.terminal_panel.input.blur()
        else:
            self.terminal_panel.display = True
            self.terminal_panel.input.focus()
        self.refresh()

    def action_clear_terminal(self):
        if self.terminal_panel.display:
            self.terminal_panel.clear()

    def action_toggle_ollama(self):
        if self.ollama_panel.display:
            self.ollama_panel.display = False
        else:
            self.ollama_panel.display = True
            self.ollama_panel.input.focus()
        self.refresh()

    # ========== 自动保存 / 外部修改检测 ==========
    def _autosave(self):
        for tid, d in self._tab_data.items():
            if self._modified.get(tid) and d.get("filepath"):
                self.action_save_file(tid)

    def _check_external_changes(self):
        for tid, d in self._tab_data.items():
            fp = d.get("filepath")
            if not fp or not Path(fp).exists():
                continue
            mtime = Path(fp).stat().st_mtime
            cached = self._file_mtime_cache.get(fp)
            if cached is not None and cached != mtime:
                self._handle_external_change(fp, tid)
            self._file_mtime_cache[fp] = mtime

    def _handle_external_change(self, filepath, tid):
        def cb(reload):
            if not reload:
                return
            enc, _ = get_file_encoding_and_ending(filepath)
            content = safe_read(filepath, encoding=enc)
            if content is None:
                self.notify("重新加载失败", severity="error")
                return
            self._tab_data[tid]["textarea"].text = content
            self._modified[tid] = False
            self.update_status_bar()
            self.notify("文件已重新加载", severity="information")

        if self._modified.get(tid):
            self.push_screen(ExternalChangeScreen(filepath, cb))
        else:
            cb(True)

    # ========== 文件树拖动 / 树宽调整 ==========
    def on_mouse_down(self, event):
        # 树宽调整：用已保存的引用，避免 query_one 找不到节点
        try:
            handle_region = self._resize_handle.region
        except Exception:
            handle_region = None
        if handle_region and handle_region.contains(event.x, event.y):
            self._is_resizing = True
            self._resize_start_x = event.x
            self._resize_start_width = self._tree_width
            event.prevent_default()
            event.stop()
            return

        if event.button == 3:
            ta = self.get_current_text_area()
            if ta and ta.region.contains(event.x, event.y):
                self.push_screen(EditorContextMenu(ta))
                return
            if self.file_tree.region.contains(event.x, event.y):
                node = self.file_tree.cursor_node
                if node is None or node.data is None:
                    self.notify("请先选中一个节点", severity="warning")
                    return
                p = getattr(node.data, "path", None) or str(node.data)
                self._context_path = Path(p)
                self._show_filetree_context(Path(p))
                return

    def _show_filetree_context(self, path):
        from screens import FileTreeContextMenu
        self.push_screen(FileTreeContextMenu(path, path.is_file()))

    def _git_action(self, action: str):
        from git import Repo, InvalidGitRepositoryError
        path = str(self._context_path)
        try:
            repo = Repo(path, search_parent_directories=True)
        except InvalidGitRepositoryError:
            self.notify("不在 Git 仓库中", severity="warning")
            return
        try:
            if action == "git_stage":
                repo.git.add(path)
                self.notify(f"已暂存: {Path(path).name}",
                            severity="information")
            elif action == "git_checkout":
                repo.git.checkout("--", path)
                self.notify(f"已还原: {Path(path).name}",
                            severity="information")
            elif action == "git_commit":
                def cb(msg):
                    if not msg.strip():
                        return
                    repo.git.add(A=True)
                    repo.index.commit(msg.strip())
                    self.notify("提交成功", severity="information")
                    self._refresh_file_tree()
                self.show_input_bar("输入 Commit message:", cb)
                return
            elif action == "git_status":
                status = repo.git.status()
                self.push_screen(DiffScreen(status, ""))
                return
            self._refresh_file_tree()
        except Exception as e:
            self.notify(f"Git 操作失败: {e}", severity="error")

    def on_mouse_move(self, event):
        if self._is_resizing:
            delta = event.x - self._resize_start_x
            self._tree_width = max(15, min(60, self._resize_start_width + delta))
            self._apply_tree_width()
            ConfigManager.save_tree_width(self._tree_width)
            event.prevent_default()
            event.stop()

    def on_mouse_up(self, event):
        if self._is_resizing:
            self._is_resizing = False
            event.prevent_default()
            event.stop()

    # ========== 输入栏 ==========
    def show_input_bar(self, prompt: str, callback):
        self.input_bar.show(prompt, callback)

    # ========== 欢迎页文本 ==========
    def _get_welcome_text(self) -> str:
        lang = self._current_lang or "未知"
        state = (self._tr("status_lsp_connected") if self.lsp.running
                 else self._tr("status_lsp_disconnected"))
        return (
            f"/**\n * {self._tr('welcome_title')}\n"
            f" * {self._tr('welcome_subtitle')}\n * \n"
            f" * {self._tr('welcome_tips')}\n * \n"
            f" * {self._tr('welcome_placeholder').format(lang=lang, status=state)}\n */\n"
            f"\n// 按 Ctrl+N 新建文件\n// 按 Ctrl+O 打开文件\n"
            f"// 按 Ctrl+Shift+P 打开命令面板\n"
        )

    # ========== Companion ==========
    def _start_companion_if_enabled(self):
        cfg = ConfigManager.load_plugin_config()
        if cfg.get("competitive-companion", {}).get("enabled"):
            self._start_companion()

    def _start_companion(self):
        if self.companion is not None:
            return
        try:
            self.companion = CompanionServer(self._companion_callback)
            self.companion.start()
            self.notify("Companion 已启动 (10045)", severity="information")
        except Exception as e:
            self.notify(f"Companion 启动失败: {e}", severity="error")

    def _stop_companion(self):
        if self.companion:
            self.companion.stop()
            self.companion = None

    def _companion_callback(self, data):
        name = data.get("name", "problem")
        lang = data.get("language", "python")
        template = data.get("code", "")
        tests = data.get("tests", [])
        ext_map = {
            "python": ".py", "cpp": ".cpp", "c": ".c", "java": ".java",
            "javascript": ".js", "rust": ".rs", "go": ".go",
        }
        ext = ext_map.get(lang, ".txt")
        base = Path(self._settings.get("default_dir", str(Path.cwd())))
        f = base / f"{name}{ext}"
        try:
            f.write_text(template, encoding="utf-8")
            self._open_file_by_path(f)
            if tests:
                (base / f"{name}_tests.json").write_text(
                    json.dumps(tests, indent=2), "utf-8")
            self.notify(f"已创建: {f.name}", severity="information")
        except Exception as e:
            self.notify(f"创建失败: {e}", severity="error")


if __name__ == "__main__":
    app = OneEditor()
    app._initial_files = sys.argv[1:]
    app.run()