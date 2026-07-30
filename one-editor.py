import os
import re
import json
import shutil
import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, TextArea, Button, Static, Input, Label,
    DirectoryTree, OptionList, Select, Checkbox, ListItem, ListView
)
from textual.widgets.option_list import Option
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual import events
from textual.widgets.tree import TreeNode
from textual.geometry import Offset
from textual import on
from textual.reactive import reactive

# ---------- LSP 模块 ----------
from lsp import LspClient, LANG_SERVERS, path_to_uri, uri_to_path

# ---------- 配置 ----------
CONFIG_DIR = Path.home() / ".one-editor"
CONFIG_FILE = CONFIG_DIR / "state.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
PLUGIN_CONFIG_FILE = CONFIG_DIR / "plugins.json"
CLIPBOARD = {"path": None, "is_cut": False}

# ---------- 语言映射 ----------
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".md": "markdown",
    ".sh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".txt": None,
}

def detect_language(path):
    ext = Path(path).suffix.lower()
    return LANGUAGE_MAP.get(ext)

def safe_read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None

# ---------- 辅助屏幕 ----------
class InputScreen(Screen):
    def __init__(self, prompt: str, callback):
        super().__init__()
        self.prompt = prompt
        self.callback = callback

    def compose(self) -> ComposeResult:
        yield Label(self.prompt)
        yield Input(placeholder="输入路径...")
        yield Static("按 Enter 确认，按 Esc 取消")

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()
        elif event.key == "enter":
            input_widget = self.query_one(Input)
            value = input_widget.value
            if value:
                self.callback(value)
                self.dismiss()


class ConfirmScreen(Screen):
    def __init__(self, message: str, callback):
        super().__init__()
        self.message = message
        self.callback = callback

    def compose(self) -> ComposeResult:
        yield Label(self.message)
        yield Static("按 y 确认，按 n 取消")

    def on_key(self, event):
        if event.key == "y":
            self.callback(True)
            self.dismiss()
        elif event.key in ("n", "escape"):
            self.callback(False)
            self.dismiss()


class ExternalChangeScreen(ModalScreen):
    """文件被外部修改时的提示"""
    CSS = """
    ExternalChangeScreen {
        background: rgba(0,0,0,0.6);
        align: center middle;
    }
    #container {
        background: $surface;
        padding: 2 3;
        border: tall $primary;
        width: 50;
        height: auto;
    }
    #container > Button {
        margin: 1 1;
        width: 1fr;
    }
    """
    def __init__(self, filepath, callback):
        super().__init__()
        self.filepath = filepath
        self.callback = callback

    def compose(self):
        with Container(id="container"):
            yield Label(f"文件 {Path(self.filepath).name} 已被外部修改", id="msg")
            yield Label("是否重新加载？")
            with Horizontal():
                yield Button("重新加载", variant="primary", id="reload")
                yield Button("忽略", id="ignore")

    def on_button_pressed(self, event):
        if event.button.id == "reload":
            self.callback(True)
        else:
            self.callback(False)
        self.dismiss()


# ---------- 统一风格的选项列表菜单（用于右键菜单、代码大纲、快速修复等） ----------
class OptionListMenu(ModalScreen):
    """通用选项列表菜单，类似于补全菜单样式"""
    CSS = """
    OptionListMenu {
        background: rgba(0,0,0,0.6);
        align: center middle;
    }
    #menu-container {
        background: $surface;
        padding: 1 2;
        border: round $accent;
        width: auto;
        min-width: 30;
        max-width: 60;
        height: auto;
        max-height: 20;
        overflow-y: auto;
    }
    .menu-item {
        width: 1fr;
        padding: 0 1;
        height: 1;
        background: $surface;
        border: none;
        text-align: left;
    }
    .menu-item:hover {
        background: $panel;
    }
    .menu-item .shortcut {
        color: $text-muted;
        margin-left: 2;
    }
    """

    def __init__(self, title: str, items: list, callback):
        """
        items: [{"label": str, "action": callable, "shortcut": str}]
        """
        super().__init__()
        self.title = title
        self.items = items
        self.callback = callback

    def compose(self):
        with Container(id="menu-container"):
            if self.title:
                yield Label(self.title, classes="title")
            for i, item in enumerate(self.items):
                label = item["label"]
                shortcut = item.get("shortcut", "")
                btn = Button(label, id=f"menu_{i}", classes="menu-item")
                if shortcut:
                    btn.label = f"{label}  ({shortcut})"
                yield btn

    def on_button_pressed(self, event):
        idx = int(event.button.id.split("_")[1])
        if idx < len(self.items):
            self.callback(self.items[idx]["action"])
        self.dismiss()


# ---------- 自定义编辑器 ----------
class AxiomEditor(TextArea):
    def on_mount(self):
        self.indent_width = 4
        self.indent_type = "spaces"
        self.tab_behavior = "indent"
        self.multicursor = True

    async def _on_key(self, event):
        # 处理补全菜单键盘导航
        if event.key in ("tab", "enter", "up", "down"):
            try:
                menu = self.app.query_one("#completion-menu")
                if menu.visible:
                    if event.key == "up":
                        menu.move_up()
                    elif event.key == "down":
                        menu.move_down()
                    elif event.key == "tab":
                        item = menu.selected_item()
                        if item:
                            self.app._insert_completion(item)
                        menu.hide()
                    elif event.key == "enter":
                        menu.hide()
                    event.prevent_default()
                    event.stop()
                    return
            except Exception:
                pass

        # 括号补全
        bracket_pairs = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
        char = event.character
        if char and char in bracket_pairs:
            start, end = self.selection
            if start != end:
                selected_text = self.text[start:end]
                new_text = char + selected_text + bracket_pairs[char]
                self.replace(new_text, start, end)
                new_cursor = start + len(char) + len(selected_text)
                self.selection = (new_cursor, new_cursor)
            else:
                row, col = self.cursor_location
                lines = self.text.split("\n")
                line = lines[row]
                new_line = line[:col] + char + bracket_pairs[char] + line[col:]
                lines[row] = new_line
                self.text = "\n".join(lines)
                self.cursor_location = (row, col + 1)
            event.prevent_default()
            event.stop()
            return

        # 自动缩进
        if not self.read_only and event.key == "enter":
            event.stop()
            event.prevent_default()
            row, col = self.cursor_location
            lines = self.text.split("\n")
            current_line = lines[row] if row < len(lines) else ""
            indent = 0
            for ch in current_line:
                if ch == " ":
                    indent += 1
                elif ch == "\t":
                    indent += self.indent_width
                else:
                    break
            text_before = current_line[:col].rstrip()
            if text_before and text_before[-1] in (":", "{", "[", "("):
                indent += self.indent_width
            start, end = self.selection
            self._replace_via_keyboard("\n" + " " * indent, start, end)
            return

        await super()._on_key(event)


# ---------- 补全菜单 ----------
class CompletionMenu(OptionList):
    DEFAULT_CSS = """
    CompletionMenu {
        layer: autocomplete;
        display: none;
        height: auto;
        max-height: 10;
        width: auto;
        min-width: 30;
        max-width: 60;
        border: round $accent;
        background: $surface;
        padding: 0;
    }
    """
    can_focus = False

    def __init__(self):
        super().__init__(id="completion-menu")
        self.items = []

    def show(self, items, offset):
        self.items = items
        self.clear_options()
        for item in items:
            self.add_option(Option(item["label"]))
        self.styles.offset = Offset(offset[0], offset[1])
        self.display = True
        self.highlighted = 0

    def hide(self):
        self.display = False
        self.items = []

    @property
    def visible(self):
        return self.display and len(self.items) > 0

    def move_up(self):
        if self.highlighted is not None and self.highlighted > 0:
            self.highlighted -= 1

    def move_down(self):
        if self.highlighted is not None and self.highlighted < self.option_count - 1:
            self.highlighted += 1

    def selected_item(self):
        idx = self.highlighted
        if idx is not None and idx < len(self.items):
            return self.items[idx]
        return None


# ---------- 查找/替换栏 ----------
class FindReplaceBar(Horizontal):
    def __init__(self, parent_app, find_callback, replace_callback):
        super().__init__()
        self.parent_app = parent_app
        self.find_callback = find_callback
        self.replace_callback = replace_callback
        self.mode = "find"
        self.case_sensitive = False
        self.use_regex = False

    def compose(self) -> ComposeResult:
        self.find_input = Input(placeholder="查找...", id="find-input")
        yield self.find_input
        self.replace_input = Input(placeholder="替换为...", id="replace-input")
        self.replace_input.display = False
        yield self.replace_input
        yield Button("Aa", id="case-btn", classes="find-btn")
        yield Button(".*", id="regex-btn", classes="find-btn")
        yield Button("查找", id="find-btn", classes="find-btn", variant="primary")
        yield Button("替换", id="replace-btn", classes="find-btn", variant="warning")
        yield Button("全部替换", id="replace-all-btn", classes="find-btn", variant="warning")
        yield Button("取消", id="cancel-btn", classes="find-btn")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "case-btn":
            self.case_sensitive = not self.case_sensitive
            event.button.label = "Aa" if self.case_sensitive else "aa"
        elif event.button.id == "regex-btn":
            self.use_regex = not self.use_regex
            event.button.label = ".*" if self.use_regex else "re"
        elif event.button.id == "find-btn":
            query = self.find_input.value
            if query:
                self.find_callback(query, self.case_sensitive, self.use_regex)
        elif event.button.id == "replace-btn":
            find_text = self.find_input.value
            replace_text = self.replace_input.value
            if find_text:
                self.replace_callback(find_text, replace_text, False, self.case_sensitive, self.use_regex)
        elif event.button.id == "replace-all-btn":
            find_text = self.find_input.value
            replace_text = self.replace_input.value
            if find_text:
                self.replace_callback(find_text, replace_text, True, self.case_sensitive, self.use_regex)
        elif event.button.id == "cancel-btn":
            self.parent_app._hide_find_replace()

    def on_key(self, event):
        if event.key == "escape":
            self.parent_app._hide_find_replace()

    def set_mode(self, mode):
        self.mode = mode
        if mode == "find":
            self.replace_input.display = False
            self.find_input.focus()
        else:
            self.replace_input.display = True
            self.replace_input.focus()


# ---------- 右键菜单（使用 OptionListMenu） ----------
class EditorContextMenu(OptionListMenu):
    def __init__(self, text_area):
        self.text_area = text_area
        items = [
            {"label": "撤销", "action": "undo", "shortcut": "Ctrl+Z"},
            {"label": "重做", "action": "redo", "shortcut": "Ctrl+Y"},
            {"label": "剪切", "action": "cut", "shortcut": "Ctrl+X"},
            {"label": "复制", "action": "copy", "shortcut": "Ctrl+C"},
            {"label": "粘贴", "action": "paste", "shortcut": "Ctrl+V"},
            {"label": "全选", "action": "select_all", "shortcut": "Ctrl+A"},
            {"label": "保存", "action": "save", "shortcut": "Ctrl+S"},
            {"label": "另存为...", "action": "save_as", "shortcut": "Ctrl+Shift+S"},
            {"label": "关闭标签", "action": "close", "shortcut": "Ctrl+W"},
            {"label": "格式化文档", "action": "format", "shortcut": "Ctrl+Shift+F"},
        ]
        def callback(action):
            if action == "undo":
                self.text_area.undo()
            elif action == "redo":
                self.text_area.redo()
            elif action == "cut":
                self.text_area.cut()
            elif action == "copy":
                self.text_area.copy()
            elif action == "paste":
                clipboard = self.app.clipboard
                if clipboard:
                    self.text_area.insert_text(clipboard)
            elif action == "select_all":
                self.text_area.select_all()
            elif action == "save":
                self.app.action_save_file()
            elif action == "save_as":
                self.app.action_save_as()
            elif action == "close":
                self.app.action_close_file()
            elif action == "format":
                self.app.action_format_document()
        super().__init__("编辑器", items, callback)


class FileTreeContextMenu(OptionListMenu):
    def __init__(self, path, is_file):
        self.path = path
        self.is_file = is_file
        items = [
            {"label": "新建文件", "action": "new_file"},
            {"label": "新建文件夹", "action": "new_folder"},
        ]
        if self.is_file:
            items.append({"label": "打开", "action": "open"})
        else:
            items.append({"label": "打开文件夹", "action": "open_dir"})
        items.extend([
            {"label": "重命名", "action": "rename", "shortcut": "F2"},
            {"label": "移动至...", "action": "move_to"},
            {"label": "复制", "action": "copy"},
            {"label": "粘贴", "action": "paste"},
            {"label": "删除", "action": "delete", "shortcut": "Del"},
        ])
        def callback(action):
            app = self.app
            app._context_path = self.path
            app._filetree_menu_callback(action)
        super().__init__("文件树", items, callback)


# ---------- 顶部菜单栏 ----------
class TopMenuBar(Horizontal):
    def compose(self) -> ComposeResult:
        yield Button("文件", id="menu_file", classes="menu-btn")
        yield Button("编辑", id="menu_edit", classes="menu-btn")
        yield Button("工具", id="menu_tools", classes="menu-btn")
        yield Button("插件", id="menu_plugins", classes="menu-btn")


# ---------- 代码大纲（使用 OptionListMenu） ----------
class SymbolListScreen(OptionListMenu):
    def __init__(self, symbols, app):
        self.symbols = symbols
        self.app_ref = app
        items = []
        for sym in symbols:
            items.append({
                "label": f"{sym['name']}  (行 {sym['line']+1})",
                "action": sym,
                "shortcut": ""
            })
        def callback(sym):
            app_ref._jump_to_symbol(sym["line"], sym["col"])
        super().__init__("符号列表", items, callback)


# ---------- 诊断信息（优化 UI） ----------
class DiagnosticScreen(Screen):
    CSS = """
    DiagnosticScreen {
        background: rgba(0,0,0,0.6);
        align: center middle;
    }
    #diag-container {
        background: $surface;
        padding: 1 2;
        border: round $accent;
        width: 70;
        height: 30;
        overflow-y: auto;
    }
    .diag-item {
        margin: 0 0 1 0;
        padding: 0 1;
    }
    .diag-error {
        color: $error;
    }
    .diag-warning {
        color: $warning;
    }
    #diag-header {
        height: 1;
        background: $surface;
        margin-bottom: 1;
    }
    #diag-close {
        width: 1fr;
        border: none;
        background: $surface;
        color: $text;
        dock: right;
    }
    #diag-close:hover {
        background: $error;
        color: $text;
    }
    """

    def __init__(self, diagnostics):
        super().__init__()
        self.diagnostics = diagnostics

    def compose(self) -> ComposeResult:
        with Container(id="diag-container"):
            with Horizontal(id="diag-header"):
                yield Label(f"诊断信息 ({len(self.diagnostics)})", id="diag-title")
                yield Button("✕", id="diag-close", variant="default")
            if not self.diagnostics:
                yield Label("没有诊断信息")
            else:
                for diag in self.diagnostics:
                    severity = diag.get("severity", 1)
                    msg = diag.get("message", "")
                    range_ = diag.get("range", {})
                    start = range_.get("start", {})
                    line = start.get("line", 0) + 1
                    col = start.get("character", 0) + 1
                    sev_label = "ERROR" if severity <= 1 else "WARNING"
                    cls = "diag-error" if severity <= 1 else "diag-warning"
                    yield Static(f"[{sev_label}] L{line}:{col} {msg}", classes=f"diag-item {cls}")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "diag-close":
            self.dismiss()

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()


# ---------- 嵌入式文件浏览器 ----------
class FileBrowserPanel(Vertical):
    DEFAULT_CSS = """
    FileBrowserPanel {
        height: 20;
        background: $surface;
        border: tall $primary;
        display: none;
        padding: 0 1;
    }
    #browser-layout {
        height: 1fr;
    }
    #browser-tree {
        width: 30;
        border-right: tall $primary;
        padding: 0 1;
    }
    #browser-input-area {
        width: 1fr;
        padding: 0 1;
    }
    #browser-input {
        width: 1fr;
        margin: 1 0;
    }
    #browser-buttons {
        height: 3;
        padding: 1 0;
    }
    .browser-btn {
        margin: 0 1;
    }
    """

    def __init__(self, parent_app, mode="open", callback=None):
        super().__init__()
        self.parent_app = parent_app
        self.mode = mode
        self.callback = callback
        self.current_path = Path.cwd()

    def compose(self) -> ComposeResult:
        with Horizontal(id="browser-layout"):
            self.browser_tree = DirectoryTree(self.current_path, id="browser-tree")
            yield self.browser_tree
            with Vertical(id="browser-input-area"):
                yield Label("文件名:" if self.mode == "open" else "保存为:")
                self.input = Input(placeholder="输入文件名...", id="browser-input")
                yield self.input
                yield Static("提示: 点击文件自动填入", id="browser-hint")
        with Horizontal(id="browser-buttons"):
            yield Button(self.mode.capitalize(), id="browser-confirm", variant="primary", classes="browser-btn")
            yield Button("取消", id="browser-cancel", classes="browser-btn")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        if event.path.is_file():
            self.input.value = event.path.name

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "browser-confirm":
            self._confirm()
        elif event.button.id == "browser-cancel":
            self._cancel()

    def on_key(self, event):
        if event.key == "escape":
            self._cancel()
        elif event.key == "enter":
            self._confirm()

    def _confirm(self):
        if self.mode == "open":
            path_str = self.input.value.strip()
            if not path_str:
                self.parent_app.notify("请输入文件名", severity="warning")
                return
            path = Path(path_str)
            if not path.is_absolute():
                path = self.browser_tree.path / path
            if path.is_file():
                self.callback(str(path))
                self.display = False
            else:
                self.parent_app.notify("文件不存在", severity="error")
        else:
            name = self.input.value.strip()
            if name:
                dest = self.browser_tree.path / name
                self.callback(str(dest))
                self.display = False
            else:
                self.parent_app.notify("请输入文件名", severity="warning")

    def _cancel(self):
        self.display = False
        self.parent_app.focus_editor()

    def show(self, start_path=None):
        if start_path:
            p = Path(start_path)
            if p.is_file():
                self.browser_tree.path = p.parent
            else:
                self.browser_tree.path = p
        else:
            self.browser_tree.path = Path.cwd()
        self.display = True
        self.input.focus()


# ---------- 设置页面（完善） ----------
class SettingsScreen(Screen):
    CSS = """
    SettingsScreen {
        background: rgba(0,0,0,0.6);
        align: center middle;
    }
    #settings-container {
        background: $surface;
        padding: 1 2;
        border: round $accent;
        width: 60;
        height: auto;
        max-height: 80%;
        overflow-y: auto;
    }
    #settings-container > Label {
        margin: 1 0;
    }
    #settings-container > Select, #settings-container > Input, #settings-container > Checkbox {
        margin: 0 0 1 0;
    }
    .settings-row {
        height: 3;
        padding: 0 1;
    }
    """
    def __init__(self, app):
        super().__init__()
        self.app_ref = app

    def compose(self):
        with Container(id="settings-container"):
            yield Label("设置", classes="title")
            yield Label("主题:")
            self.theme_select = Select(
                [("textual-dark", "textual-dark"), ("textual-light", "textual-light"),
                 ("dracula", "dracula"), ("nord", "nord")],
                prompt="选择主题",
                value=self.app_ref.theme
            )
            yield self.theme_select
            yield Label("缩进空格数:")
            self.indent_input = Input(value=str(self.app_ref._indent_width or 4), type="integer")
            yield self.indent_input
            yield Label("自动保存间隔(秒):")
            self.autosave_input = Input(value=str(getattr(self.app_ref, "_autosave_interval", 0)), type="integer")
            yield self.autosave_input
            yield Checkbox("显示行号", value=self.app_ref._show_line_numbers)
            yield Label("保存设置:")
            yield Button("保存", variant="primary", id="save-settings")
            yield Button("取消", id="cancel-settings")

    def on_button_pressed(self, event):
        if event.button.id == "save-settings":
            # 保存主题
            new_theme = self.theme_select.value
            if new_theme:
                self.app_ref.theme = new_theme
            # 缩进
            try:
                indent = int(self.indent_input.value)
                if indent > 0:
                    self.app_ref._indent_width = indent
                    for data in self.app_ref._tab_data.values():
                        data["textarea"].indent_width = indent
            except ValueError:
                pass
            # 自动保存
            try:
                interval = int(self.autosave_input.value)
                self.app_ref._autosave_interval = interval
            except ValueError:
                pass
            # 行号
            show_line_numbers = self.query_one(Checkbox).value
            self.app_ref._show_line_numbers = show_line_numbers
            for data in self.app_ref._tab_data.values():
                data["textarea"].show_line_numbers = show_line_numbers
            self.dismiss()
        else:
            self.dismiss()

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()


# ---------- 插件页面 ----------
class PluginsScreen(Screen):
    CSS = """
    PluginsScreen {
        background: rgba(0,0,0,0.6);
        align: center middle;
    }
    #plugins-container {
        background: $surface;
        padding: 1 2;
        border: round $accent;
        width: 70;
        height: auto;
        max-height: 80%;
        overflow-y: auto;
    }
    .plugin-item {
        height: 3;
        padding: 0 1;
        margin: 0 0 1 0;
        background: $panel;
        border: none;
    }
    .plugin-item:hover {
        background: $surface;
    }
    .plugin-name {
        width: 15;
        text-style: bold;
    }
    .plugin-status {
        width: 10;
    }
    .plugin-features {
        width: 1fr;
    }
    .toggle-btn {
        width: 10;
        border: none;
        background: $primary;
        color: $text;
    }
    .toggle-btn.off {
        background: $surface;
        color: $text-muted;
    }
    #plugins-close {
        dock: right;
        border: none;
        background: $surface;
        color: $text;
    }
    #plugins-close:hover {
        background: $error;
        color: $text;
    }
    """
    def __init__(self, app):
        super().__init__()
        self.app_ref = app
        self.plugin_config = self._load_config()

    def _load_config(self):
        default_config = {}
        for lang in LANG_SERVERS.keys():
            default_config[lang] = {
                "enabled": True,
                "features": {
                    "completion": True,
                    "definition": True,
                    "hover": True,
                    "diagnostics": True,
                    "rename": True,
                    "code_action": True,
                }
            }
        if PLUGIN_CONFIG_FILE.exists():
            try:
                with open(PLUGIN_CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    # 合并默认值
                    for lang in default_config:
                        if lang in config:
                            default_config[lang].update(config[lang])
                    return default_config
            except:
                pass
        return default_config

    def _save_config(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(PLUGIN_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.plugin_config, f, indent=2)
        except:
            pass

    def compose(self):
        with Container(id="plugins-container"):
            yield Horizontal(
                Label("插件管理", id="plugins-title"),
                Button("✕", id="plugins-close")
            )
            for lang, config in self.plugin_config.items():
                server = LANG_SERVERS.get(lang, ["未安装"])
                installed = shutil.which(server[0]) is not None if server else False
                features = config.get("features", {})
                status = "✅ 已启用" if config.get("enabled", True) else "❌ 已禁用"
                with Container(classes="plugin-item"):
                    yield Horizontal(
                        Label(lang, classes="plugin-name"),
                        Label(status, classes="plugin-status"),
                        Label(f"服务器: {server[0]}", classes="plugin-features"),
                        Button("启用/禁用", id=f"toggle_{lang}", classes="toggle-btn"),
                    )
                    # 显示功能开关
                    with Horizontal(classes="feature-row"):
                        for feature, enabled in features.items():
                            yield Checkbox(feature, value=enabled, id=f"feature_{lang}_{feature}")
            yield Button("保存插件配置", variant="primary", id="save-plugins")
            yield Button("取消", id="cancel-plugins")

    def on_button_pressed(self, event):
        if event.button.id == "plugins-close" or event.button.id == "cancel-plugins":
            self.dismiss()
        elif event.button.id.startswith("toggle_"):
            lang = event.button.id.split("_")[1]
            self.plugin_config[lang]["enabled"] = not self.plugin_config[lang]["enabled"]
            self.dismiss()
            self.push_screen(PluginsScreen(self.app_ref))
        elif event.button.id == "save-plugins":
            # 收集所有复选框状态
            for lang in self.plugin_config:
                for feature in self.plugin_config[lang].get("features", {}):
                    checkbox_id = f"feature_{lang}_{feature}"
                    try:
                        checkbox = self.query_one(f"#{checkbox_id}", Checkbox)
                        self.plugin_config[lang]["features"][feature] = checkbox.value
                    except:
                        pass
            self._save_config()
            self.dismiss()
            self.app_ref.notify("插件配置已保存", severity="information")


# ---------- 主编辑器 ----------
class OneEditor(App):
    BINDINGS = [
        Binding("ctrl+n", "new_file", "新建", show=True),
        Binding("ctrl+o", "open_file", "打开", show=True),
        Binding("ctrl+s", "save_file", "保存", show=True),
        Binding("ctrl+shift+s", "save_as", "另存为", show=True),
        Binding("ctrl+w", "close_file", "关闭", show=True),
        Binding("ctrl+q", "quit", "退出", show=True),
        Binding("alt+up", "move_line_up", "上移行", show=True),
        Binding("alt+down", "move_line_down", "下移行", show=True),
        Binding("ctrl+f", "show_find", "查找", show=True),
        Binding("ctrl+h", "show_replace", "替换", show=True),
        Binding("f3", "find_next", "下一个", show=True),
        Binding("ctrl+g", "goto_line", "转到行", show=True),
        Binding("ctrl+b", "toggle_file_tree", "文件树", show=True),
        Binding("f2", "rename_node", "重命名", show=True),
        Binding("ctrl+shift+m", "move_node", "移动", show=True),
        Binding("f12", "goto_definition", "跳转定义", show=True),
        Binding("ctrl+shift+o", "show_symbols", "代码大纲", show=True),
        Binding("ctrl+shift+i", "show_hover", "悬停提示", show=True),
        Binding("ctrl+shift+e", "show_diagnostics", "诊断信息", show=True),
        Binding("ctrl+shift+r", "rename_symbol", "重命名符号", show=True),
        Binding("ctrl+shift+a", "code_action", "快速修复", show=True),
        Binding("ctrl+shift+f", "format_document", "格式化文档", show=True),
        Binding("escape", "hide_find_replace", "隐藏查找栏", show=False),
    ]

    CSS = """
    #main-layout {
        layout: horizontal;
    }
    #sidebar {
        width: 30;
        background: $surface;
        border-right: tall $primary;
        padding: 0 1;
        display: block;
    }
    #editor-area {
        width: 1fr;
        layers: default autocomplete overlay;
    }
    #menu-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    .menu-btn {
        padding: 0 2;
        background: $surface;
        color: $text;
        border: none;
        height: 1;
    }
    .menu-btn:hover {
        background: $panel;
    }
    #tab-scroll {
        height: 2;
        background: $surface;
        padding: 0 1;
        overflow-x: auto;
    }
    #tab-bar {
        width: auto;
        height: 1;
        background: $surface;
    }
    .tab-button-container {
        height: 1;
    }
    .tab-button {
        padding: 0 2 0 4;
        background: $surface;
        color: $text;
        border: none;
        height: 1;
        margin: 0;
    }
    .tab-button:hover {
        background: $panel;
    }
    .tab-button.active {
        background: $primary;
        color: $text;
        text-style: bold;
    }
    .tab-close {
        padding: 0 1;
        margin: 0 1 0 0;
        background: $surface;
        color: $text;
        border: none;
        height: 1;
        min-width: 1;
        display: none;
    }
    .tab-button-container:hover .tab-close {
        display: block;
    }
    .tab-close:hover {
        background: $error;
        color: $text;
    }
    #content-container {
        height: 1fr;
    }
    TextArea {
        border: none;
        background: $surface;
    }
    #status-bar {
        background: $primary;
        color: $text;
        padding: 0 1;
        height: 1;
    }
    #find-replace-bar {
        height: 3;
        background: $surface;
        padding: 0 1;
        display: none;
    }
    #find-replace-bar > Input {
        width: 1fr;
        margin: 0 1;
    }
    #find-replace-bar > Button {
        margin: 0 1;
        height: 1;
    }
    .find-btn {
        padding: 0 1;
        background: $surface;
        color: $text;
        border: none;
        height: 1;
    }
    .find-btn:hover {
        background: $panel;
    }
    #file-browser {
        height: 20;
        background: $surface;
        border: tall $primary;
        display: none;
        padding: 0 1;
    }
    #browser-layout {
        height: 1fr;
    }
    #browser-tree {
        width: 30;
        border-right: tall $primary;
        padding: 0 1;
    }
    #browser-input-area {
        width: 1fr;
        padding: 0 1;
    }
    #browser-input {
        width: 1fr;
        margin: 1 0;
    }
    #browser-buttons {
        height: 3;
        padding: 1 0;
    }
    .browser-btn {
        margin: 0 1;
    }
    #completion-menu {
        layer: autocomplete;
        display: none;
        height: auto;
        max-height: 10;
        width: auto;
        min-width: 30;
        max-width: 60;
        border: round $accent;
        background: $surface;
        padding: 0;
    }
    .tree-resize-handle {
        width: 3;
        background: $surface;
        border-right: tall $primary;
    }
    #tree-container {
        height: 1fr;
        width: 30;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield TopMenuBar(id="menu-bar")
        with ScrollableContainer(id="tab-scroll"):
            self.tab_bar = Horizontal(id="tab-bar")
            yield self.tab_bar
        self.find_bar = FindReplaceBar(self, self._do_find, self._do_replace)
        self.find_bar.id = "find-replace-bar"
        yield self.find_bar
        self.file_browser = FileBrowserPanel(parent_app=self, mode="open")
        self.file_browser.id = "file-browser"
        yield self.file_browser
        with Horizontal(id="main-layout"):
            with Container(id="tree-container"):
                self.file_tree = DirectoryTree(Path(".").resolve())
                self.file_tree.id = "sidebar"
                yield self.file_tree
            self.resize_handle = Static(classes="tree-resize-handle")
            yield self.resize_handle
            with Vertical(id="editor-area"):
                self.content_container = Container(id="content-container")
                yield self.content_container
                self.completion_menu = CompletionMenu()
                yield self.completion_menu
        self.status_bar = Static(id="status-bar")
        yield self.status_bar
        yield Footer()

    def on_mount(self):
        self._tab_data = {}
        self._modified = {}
        self._active_tab_id = None
        self._tab_counter = 0
        self._find_matches = []
        self._find_index = -1
        self._find_query = ""
        self._context_path = None
        self._drag_node = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False
        self._show_file_tree = True
        self._search_history = self._load_history()
        self._find_visible = False
        self._current_lang = None
        self._completion_timer = None
        self._indent_width = 4
        self._show_line_numbers = True
        self._autosave_interval = 0
        self._diagnostics_cache = {}
        self._current_uri = None
        self._file_mtime_cache = {}
        self._tree_width = 30
        self._load_tree_width()
        self._is_resizing = False
        self.lsp = LspClient()
        self.lsp.set_diagnostics_callback(self._on_diagnostics)

        self._load_state()

        if not self._tab_data:
            self.add_new_tab("未命名 1")
            self.show_tab("tab_0")
        else:
            if self._active_tab_id and self._active_tab_id in self._tab_data:
                self.show_tab(self._active_tab_id)
            else:
                first_id = next(iter(self._tab_data))
                self.show_tab(first_id)

        self.file_tree.display = self._show_file_tree
        self.file_tree.focus()
        self._apply_tree_width()

        if self._autosave_interval > 0:
            self.set_timer(self._autosave_interval, self._autosave)
        self.set_timer(2, self._check_external_changes)

    # ---------- 自动保存 ----------
    def _autosave(self):
        for tid, data in self._tab_data.items():
            if self._modified.get(tid, False) and data.get("filepath"):
                self.action_save_file()
        if self._autosave_interval > 0:
            self.set_timer(self._autosave_interval, self._autosave)

    # ---------- 文件树宽度 ----------
    def _load_tree_width(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    if "tree_width" in config:
                        self._tree_width = config["tree_width"]
            except:
                pass

    def _save_tree_width(self):
        try:
            with open(CONFIG_FILE, "r+", encoding="utf-8") as f:
                config = json.load(f)
                config["tree_width"] = self._tree_width
                f.seek(0)
                json.dump(config, f, indent=2)
                f.truncate()
        except:
            pass

    def _apply_tree_width(self):
        tree_container = self.query_one("#tree-container")
        tree_container.styles.width = self._tree_width

    def on_mouse_down(self, event: events.MouseDown):
        if self.resize_handle.region.contains(event.x, event.y):
            self._is_resizing = True
            self._resize_start_x = event.x
            self._resize_start_width = self._tree_width
            event.prevent_default()
            event.stop()
            return
        if event.button == 3:
            current_text_area = self.get_current_text_area()
            if current_text_area and current_text_area.region.contains(event.x, event.y):
                self.push_screen(EditorContextMenu(current_text_area))
                return
            if self.file_tree.region.contains(event.x, event.y):
                node = self.file_tree.cursor_node
                if node is None:
                    self.notify("请先选中一个节点", severity="warning")
                    return
                data = node.data
                if data is None:
                    return
                if hasattr(data, "path"):
                    path = Path(data.path)
                else:
                    path = Path(str(data))
                self._context_path = path
                is_file = path.is_file()
                self.push_screen(FileTreeContextMenu(path, is_file))
                return
        elif event.button == 1:
            if self.file_tree.region.contains(event.x, event.y):
                node = self.file_tree.cursor_node
                if node is not None:
                    self._drag_node = node
                    self._drag_start_x = event.x
                    self._drag_start_y = event.y
                    self._is_dragging = False
            else:
                self._drag_node = None

    def on_mouse_move(self, event: events.MouseMove):
        if getattr(self, "_is_resizing", False):
            delta = event.x - self._resize_start_x
            new_width = max(15, min(60, self._resize_start_width + delta))
            self._tree_width = new_width
            self._apply_tree_width()
            self._save_tree_width()
            event.prevent_default()
            event.stop()
            return
        if self._drag_node is not None:
            dx = event.x - self._drag_start_x
            dy = event.y - self._drag_start_y
            if (dx * dx + dy * dy) > 25:
                self._is_dragging = True

    def on_mouse_up(self, event: events.MouseUp):
        if getattr(self, "_is_resizing", False):
            self._is_resizing = False
            event.prevent_default()
            event.stop()
            return
        if self._drag_node is None or event.button != 1:
            self._drag_node = None
            self._is_dragging = False
            return
        if not self._is_dragging:
            self._drag_node = None
            return
        tree = self.file_tree
        if not tree.region.contains(event.x, event.y):
            self._drag_node = None
            self._is_dragging = False
            return
        target_node = tree.cursor_node
        if target_node is None:
            target_node = tree.root
            if target_node is None:
                self._drag_node = None
                self._is_dragging = False
                return
        if target_node is self._drag_node:
            self._drag_node = None
            self._is_dragging = False
            return
        target_data = target_node.data
        if target_data is None:
            self._drag_node = None
            self._is_dragging = False
            return
        if hasattr(target_data, "path"):
            target_path = Path(target_data.path)
        else:
            target_path = Path(str(target_data))
        if target_path.is_file():
            target_path = target_path.parent
        src_data = self._drag_node.data
        if hasattr(src_data, "path"):
            src = Path(src_data.path)
        else:
            src = Path(str(src_data))
        if not src.exists():
            self._drag_node = None
            self._is_dragging = False
            return
        if src == target_path or target_path.is_relative_to(src):
            self.notify("不能移动到自身或子目录", severity="warning")
            self._drag_node = None
            self._is_dragging = False
            return
        dest = target_path / src.name
        if dest.exists():
            def confirm_overwrite(ok: bool):
                if ok:
                    self._do_move(src, dest)
            self.push_screen(ConfirmScreen(f"{dest} 已存在，覆盖？", callback=confirm_overwrite))
        else:
            self._do_move(src, dest)
        self._drag_node = None
        self._is_dragging = False

    def _do_move(self, src: Path, dest: Path):
        try:
            shutil.move(str(src), str(dest))
            self._refresh_file_tree()
            self.notify(f"已移动: {src.name} -> {dest.parent}", severity="information")
            abs_dest = str(dest.resolve())
            for tid, data in self._tab_data.items():
                if data.get("filepath") == str(src.resolve()):
                    data["filepath"] = abs_dest
                    data["title"] = dest.name
                    data["button"].label = dest.name
                    self.update_status_bar()
                    break
        except Exception as e:
            self.notify(f"移动失败: {e}", severity="error")

    # ---------- 外部文件修改 ----------
    def _check_external_changes(self):
        for tid, data in self._tab_data.items():
            filepath = data.get("filepath")
            if filepath and Path(filepath).exists():
                current_mtime = Path(filepath).stat().st_mtime
                cached_mtime = self._file_mtime_cache.get(filepath)
                if cached_mtime is not None and cached_mtime != current_mtime:
                    self._handle_external_change(filepath, tid)
                self._file_mtime_cache[filepath] = current_mtime

    def _handle_external_change(self, filepath, tab_id):
        def callback(reload: bool):
            if reload:
                content = safe_read(filepath)
                if content is not None:
                    self._tab_data[tab_id]["textarea"].text = content
                    self._modified[tab_id] = False
                    self.update_status_bar()
                    self.notify("文件已重新加载", severity="information")
                else:
                    self.notify("重新加载失败", severity="error")
        if self._modified.get(tab_id, False):
            self.push_screen(ExternalChangeScreen(filepath, callback))
        else:
            callback(True)

    # ---------- 文件树展开 ----------
    def _expand_to_file(self, filepath):
        tree = self.file_tree
        root_path = tree.path
        try:
            rel_path = Path(filepath).relative_to(root_path)
        except ValueError:
            return
        def find_and_expand(node, parts, idx=0):
            if idx >= len(parts):
                return node
            part = parts[idx]
            for child in node.children:
                if child.data and child.data.name == part:
                    if idx == len(parts) - 1:
                        if child.parent:
                            child.parent.expand()
                        return child
                    else:
                        child.expand()
                        return find_and_expand(child, parts, idx+1)
            return None
        root = tree.root
        if root:
            root.expand()
            find_and_expand(root, rel_path.parts, 0)
            tree.scroll_to_node(tree.cursor_node)

    # ---------- 标签管理 ----------
    def add_new_tab(self, title: str, content: str = "", filepath: str = None) -> str:
        tab_id = f"tab_{self._tab_counter}"
        self._tab_counter += 1
        button_container = Horizontal(classes="tab-button-container")
        tab_button = Button(title, id=tab_id, classes="tab-button")
        close_button = Button("×", id=f"close_{tab_id}", classes="tab-close")
        self.tab_bar.mount(button_container)
        button_container.mount(tab_button, close_button)
        text_area = AxiomEditor(content, show_line_numbers=self._show_line_numbers, language="python")
        text_area.wrap = True
        text_area.fold = True
        text_area.indent_width = self._indent_width
        text_area.id = f"textarea_{tab_id}"
        text_area.display = False
        self.content_container.mount(text_area)
        self._tab_data[tab_id] = {
            "title": title,
            "filepath": filepath,
            "textarea": text_area,
            "button": tab_button,
            "close_button": close_button,
            "container": button_container,
            "encoding": "UTF-8",
            "line_ending": "LF",
        }
        self._modified[tab_id] = False
        if filepath:
            self._file_mtime_cache[filepath] = Path(filepath).stat().st_mtime if Path(filepath).exists() else None
        if len(self._tab_data) > 9:
            first_id = next(iter(self._tab_data))
            self.remove_tab(first_id)
        return tab_id

    def remove_tab(self, tab_id: str):
        if len(self._tab_data) <= 1:
            self.notify("至少保留一个标签", severity="warning")
            return
        data = self._tab_data[tab_id]
        data["container"].remove()
        data["textarea"].remove()
        del self._tab_data[tab_id]
        del self._modified[tab_id]
        if self._active_tab_id == tab_id:
            remaining = list(self._tab_data.keys())
            if remaining:
                self.show_tab(remaining[0])
        else:
            self._update_tab_styles()
        self.update_status_bar()
        self._save_state()
        if not self._tab_data:
            self.run_worker(self.lsp.stop(), exclusive=True, group="lsp")

    def show_tab(self, tab_id: str):
        if tab_id not in self._tab_data:
            return
        for data in self._tab_data.values():
            data["textarea"].display = False
        self._tab_data[tab_id]["textarea"].display = True
        self._active_tab_id = tab_id
        self._update_tab_styles()
        self.update_status_bar()
        self._tab_data[tab_id]["textarea"].focus()
        self._find_matches = []
        self._find_index = -1
        self._hide_find_replace()
        self._save_state()
        container = self._tab_data[tab_id]["container"]
        container.scroll_visible()
        filepath = self._tab_data[tab_id].get("filepath")
        if filepath:
            self._start_lsp_for_file(filepath, self._tab_data[tab_id]["textarea"].text)
            self._expand_to_file(filepath)

    def _update_tab_styles(self):
        for tid, data in self._tab_data.items():
            button = data["button"]
            if tid == self._active_tab_id:
                button.add_class("active")
            else:
                button.remove_class("active")

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id
        if btn_id.startswith("close_"):
            tab_id = btn_id.replace("close_", "")
            if tab_id in self._tab_data:
                self.action_close_file(tab_id)
            return
        if btn_id in self._tab_data:
            self.show_tab(btn_id)
            return
        if btn_id == "menu_file":
            self._show_file_menu()
        elif btn_id == "menu_edit":
            self._show_edit_menu()
        elif btn_id == "menu_tools":
            self._show_tools_menu()
        elif btn_id == "menu_plugins":
            self._show_plugins_menu()

    # ---------- 菜单 ----------
    def _show_file_menu(self):
        items = [
            {"label": "新建", "action": "new", "shortcut": "Ctrl+N"},
            {"label": "打开...", "action": "open", "shortcut": "Ctrl+O"},
            {"label": "保存", "action": "save", "shortcut": "Ctrl+S"},
            {"label": "另存为...", "action": "save_as", "shortcut": "Ctrl+Shift+S"},
            {"label": "关闭", "action": "close", "shortcut": "Ctrl+W"},
            {"label": "退出", "action": "quit", "shortcut": "Ctrl+Q"},
        ]
        def callback(action):
            if action == "new":
                self.action_new_file()
            elif action == "open":
                self.action_open_file()
            elif action == "save":
                self.action_save_file()
            elif action == "save_as":
                self.action_save_as()
            elif action == "close":
                self.action_close_file()
            elif action == "quit":
                self.action_quit()
        self.push_screen(OptionListMenu("文件", items, callback))

    def _show_edit_menu(self):
        items = [
            {"label": "查找", "action": "find", "shortcut": "Ctrl+F"},
            {"label": "替换", "action": "replace", "shortcut": "Ctrl+H"},
            {"label": "转到行", "action": "goto", "shortcut": "Ctrl+G"},
            {"label": "格式化文档", "action": "format", "shortcut": "Ctrl+Shift+F"},
        ]
        def callback(action):
            if action == "find":
                self.action_show_find()
            elif action == "replace":
                self.action_show_replace()
            elif action == "goto":
                self.action_goto_line()
            elif action == "format":
                self.action_format_document()
        self.push_screen(OptionListMenu("编辑", items, callback))

    def _show_tools_menu(self):
        items = [
            {"label": "设置", "action": "settings"},
        ]
        def callback(action):
            if action == "settings":
                self._show_settings()
        self.push_screen(OptionListMenu("工具", items, callback))

    def _show_plugins_menu(self):
        self.push_screen(PluginsScreen(self))

    def _show_settings(self):
        self.push_screen(SettingsScreen(self))

    # ---------- 状态栏 ----------
    def update_status_bar(self):
        tab_id = self.get_current_tab_id()
        if not tab_id or tab_id not in self._tab_data:
            return
        data = self._tab_data[tab_id]
        text_area = data["textarea"]
        title = data["title"]
        modified = self._modified.get(tab_id, False)
        modified_mark = "●" if modified else ""
        cursor = text_area.selection.start
        row, col = cursor
        total_lines = len(text_area.text.splitlines())
        selected_text = text_area.selected_text
        sel_len = len(selected_text) if selected_text else 0
        sel_info = f" 已选 {sel_len}" if sel_len > 0 else ""
        lang = text_area.language or "plain"
        filepath = data.get("filepath")
        size_str = ""
        if filepath:
            try:
                size = Path(filepath).stat().st_size
                if size < 1024:
                    size_str = f" {size}B"
                elif size < 1024*1024:
                    size_str = f" {size/1024:.1f}KB"
                else:
                    size_str = f" {size/(1024*1024):.1f}MB"
            except:
                pass
        encoding = data.get("encoding", "UTF-8")
        line_ending = data.get("line_ending", "LF")
        current_uri = self._current_uri
        diag_count = len(self._diagnostics_cache.get(current_uri, [])) if current_uri else 0
        diag_info = f" ⚠{diag_count}" if diag_count > 0 else ""
        extra = ""
        if self._find_matches and self._find_index >= 0:
            extra = f" | 匹配 {self._find_index+1}/{len(self._find_matches)}"
        self.status_bar.update(
            f"{title} {modified_mark}  [{lang}] {encoding} {line_ending}{size_str} 行 {row+1}/{total_lines} 列 {col+1}{sel_info}{diag_info}{extra}"
        )

    # ---------- 持久化 ----------
    def _load_state(self):
        if not CONFIG_FILE.exists():
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except:
            return
        open_files = state.get("open_files", [])
        active_index = state.get("active_index", 0)
        self._show_file_tree = state.get("show_file_tree", True)
        self._indent_width = state.get("indent_width", 4)
        self._show_line_numbers = state.get("show_line_numbers", True)
        self._autosave_interval = state.get("autosave_interval", 0)
        for filepath in open_files:
            if filepath is None:
                continue
            path = Path(filepath)
            if path.exists() and path.is_file():
                content = safe_read(filepath)
                if content is not None:
                    title = path.name
                    self.add_new_tab(title, content, str(path.resolve()))
        if not self._tab_data:
            return
        tab_ids = list(self._tab_data.keys())
        if active_index < len(tab_ids):
            self._active_tab_id = tab_ids[active_index]
        else:
            self._active_tab_id = tab_ids[0]

    def _save_state(self):
        open_files = []
        for tid, data in self._tab_data.items():
            open_files.append(data.get("filepath"))
        tab_ids = list(self._tab_data.keys())
        active_index = 0
        if self._active_tab_id in tab_ids:
            active_index = tab_ids.index(self._active_tab_id)
        state = {
            "open_files": open_files,
            "active_index": active_index,
            "show_file_tree": self.file_tree.display,
            "tree_width": self._tree_width,
            "indent_width": self._indent_width,
            "show_line_numbers": self._show_line_numbers,
            "autosave_interval": self._autosave_interval,
        }
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    # ---------- 查找/替换 ----------
    def _do_find(self, query, case_sensitive, use_regex):
        self._add_history(query)
        self._find_query = query
        text_area = self.get_current_text_area()
        matches = []
        if use_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                pattern = re.compile(query, flags)
            except re.error:
                self.notify("无效的正则表达式", severity="error")
                return
            for row, line in enumerate(text_area.text.splitlines()):
                for m in pattern.finditer(line):
                    matches.append((row, m.start(), m.end()))
        else:
            for row, line in enumerate(text_area.text.splitlines()):
                pos = 0
                while True:
                    idx = line.find(query, pos)
                    if idx == -1:
                        break
                    matches.append((row, idx, idx + len(query)))
                    pos = idx + 1
        self._find_matches = matches
        if not self._find_matches:
            self.notify("未找到匹配", severity="warning")
            self._find_index = -1
        else:
            self._find_index = 0
            self._goto_match(0)
            self.notify(f"找到 {len(self._find_matches)} 个匹配", severity="information")
        self.update_status_bar()

    def _do_replace(self, find_text, replace_text, replace_all, case_sensitive, use_regex):
        text_area = self.get_current_text_area()
        tab_id = self.get_current_tab_id()
        if replace_all:
            matches = self._find_all(find_text, case_sensitive, use_regex)
            if not matches:
                self.notify("未找到匹配", severity="warning")
                return
            try:
                if use_regex:
                    flags = 0 if case_sensitive else re.IGNORECASE
                    pattern = re.compile(find_text, flags)
                else:
                    pattern = None
            except re.error:
                self.notify("无效的正则", severity="error")
                return
            lines = text_area.text.splitlines()
            new_lines = lines[:]
            replaced_count = 0
            for i, line in enumerate(new_lines):
                if use_regex:
                    new_line, count = pattern.subn(replace_text, line)
                else:
                    new_line = line.replace(find_text, replace_text)
                    count = line.count(find_text)
                if count > 0:
                    new_lines[i] = new_line
                    replaced_count += count
            if replaced_count > 0:
                text_area.text = "\n".join(new_lines)
                self._modified[tab_id] = True
                self.notify(f"替换了 {replaced_count} 处", severity="information")
                self._find_matches = []
                self._find_index = -1
                self.update_status_bar()
            else:
                self.notify("未找到匹配", severity="warning")
        else:
            if not self._find_matches:
                self.notify("请先执行查找", severity="warning")
                return
            if self._find_index < 0 or self._find_index >= len(self._find_matches):
                return
            row, start, end = self._find_matches[self._find_index]
            lines = text_area.text.splitlines()
            old_line = lines[row]
            new_line = old_line[:start] + replace_text + old_line[end:]
            lines[row] = new_line
            text_area.text = "\n".join(lines)
            self._find_matches = self._find_all(find_text, case_sensitive, use_regex)
            if not self._find_matches:
                self._find_index = -1
            else:
                self._find_index = 0
                self._goto_match(0)
            self._modified[tab_id] = True
            self.update_status_bar()

    def _find_all(self, query, case_sensitive, use_regex):
        text_area = self.get_current_text_area()
        lines = text_area.text.splitlines()
        matches = []
        if use_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                pattern = re.compile(query, flags)
            except re.error:
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

    def _goto_match(self, index):
        if not self._find_matches or index < 0 or index >= len(self._find_matches):
            return
        text_area = self.get_current_text_area()
        row, start, end = self._find_matches[index]
        text_area.selection = ((row, start), (row, end))
        text_area.scroll_to((row, 0), animate=False)
        self._find_index = index
        self.update_status_bar()

    def _show_find_replace(self, mode="find"):
        self.find_bar.display = True
        self.find_bar.set_mode(mode)
        self._find_visible = True

    def _hide_find_replace(self):
        self.find_bar.display = False
        self._find_visible = False
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

    # ---------- 文件操作 ----------
    def action_new_file(self):
        if len(self._tab_data) >= 9:
            self.notify("最多同时打开 9 个文件", severity="error")
            return
        unnamed_count = sum(1 for data in self._tab_data.values() if data["title"].startswith("未命名"))
        title = f"未命名 {unnamed_count + 1}"
        tab_id = self.add_new_tab(title)
        self.show_tab(tab_id)

    def action_open_file(self):
        self.file_browser.mode = "open"
        self.file_browser.callback = self._open_file_callback
        current = self._tab_data.get(self._active_tab_id, {}).get("filepath")
        self.file_browser.show(start_path=current if current else None)

    def _open_file_callback(self, path_str):
        path = Path(path_str)
        if path.is_file():
            self._open_file_by_path(path)
        else:
            self.notify("不是有效文件", severity="error")

    def action_save_as(self):
        self.file_browser.mode = "save"
        self.file_browser.callback = self._save_as_callback
        current = self._tab_data.get(self._active_tab_id, {}).get("filepath")
        self.file_browser.show(start_path=current if current else None)
        if current:
            self.file_browser.input.value = Path(current).name

    def _save_as_callback(self, dest_str):
        dest = Path(dest_str)
        text_area = self.get_current_text_area()
        try:
            dest.write_text(text_area.text, encoding="utf-8")
            tab_id = self.get_current_tab_id()
            data = self._tab_data[tab_id]
            data["filepath"] = str(dest.resolve())
            data["title"] = dest.name
            data["button"].label = dest.name
            self._modified[tab_id] = False
            enc, le = self._get_file_encoding_and_ending(str(dest))
            data["encoding"] = enc
            data["line_ending"] = le
            self.update_status_bar()
            self.notify(f"已保存: {dest.name}", severity="information")
        except Exception as e:
            self.notify(f"保存失败: {e}", severity="error")

    def action_save_file(self):
        tab_id = self.get_current_tab_id()
        data = self._tab_data[tab_id]
        text_area = data["textarea"]
        filepath = data.get("filepath")
        if filepath:
            Path(filepath).write_text(text_area.text, encoding="utf-8")
            self._modified[tab_id] = False
            enc, le = self._get_file_encoding_and_ending(filepath)
            data["encoding"] = enc
            data["line_ending"] = le
            self.update_status_bar()
            self.notify(f"已保存: {Path(filepath).name}", severity="information")
        else:
            self.action_save_as()

    def action_close_file(self, tab_id=None):
        if tab_id is None:
            tab_id = self.get_current_tab_id()
        if self._modified.get(tab_id, False):
            def confirm(ok: bool):
                if ok:
                    self.remove_tab(tab_id)
            self.push_screen(ConfirmScreen("文件已修改，确定关闭吗？", callback=confirm))
        else:
            self.remove_tab(tab_id)

    def action_quit(self):
        self._save_state()
        if self.lsp.running:
            self.run_worker(self.lsp.stop(), exclusive=True, group="lsp")
        modified_tabs = [data["title"] for tid, data in self._tab_data.items() if self._modified.get(tid, False)]
        if modified_tabs:
            def confirm_quit(ok: bool):
                if ok:
                    self.exit()
            self.push_screen(ConfirmScreen(
                f"以下文件未保存：{', '.join(modified_tabs)}\n确定退出吗？",
                callback=confirm_quit
            ))
        else:
            self.exit()

    # ---------- 行移动 ----------
    def action_move_line_up(self):
        text_area = self.get_current_text_area()
        lines = text_area.text.splitlines()
        if len(lines) < 2:
            self.notify("至少两行才能移动", severity="warning")
            return
        row, col = text_area.selection.start
        if row <= 0:
            self.notify("已经是第一行", severity="warning")
            return
        lines[row], lines[row-1] = lines[row-1], lines[row]
        new_text = "\n".join(lines)
        text_area.text = new_text
        new_row = row - 1
        new_col = min(col, len(lines[new_row]))
        text_area.cursor_location = (new_row, new_col)
        tab_id = self.get_current_tab_id()
        self._modified[tab_id] = True
        self.update_status_bar()

    def action_move_line_down(self):
        text_area = self.get_current_text_area()
        lines = text_area.text.splitlines()
        if len(lines) < 2:
            self.notify("至少两行才能移动", severity="warning")
            return
        row, col = text_area.selection.start
        if row >= len(lines) - 1:
            self.notify("已经是最后一行", severity="warning")
            return
        lines[row], lines[row+1] = lines[row+1], lines[row]
        new_text = "\n".join(lines)
        text_area.text = new_text
        new_row = row + 1
        new_col = min(col, len(lines[new_row]))
        text_area.cursor_location = (new_row, new_col)
        tab_id = self.get_current_tab_id()
        self._modified[tab_id] = True
        self.update_status_bar()

    def action_goto_line(self):
        def do_goto(line_str: str):
            try:
                line_num = int(line_str.strip())
            except ValueError:
                self.notify("请输入有效的行号", severity="error")
                return
            if line_num < 1:
                self.notify("行号必须大于0", severity="error")
                return
            text_area = self.get_current_text_area()
            lines = text_area.text.splitlines()
            total = len(lines)
            if line_num > total:
                self.notify(f"只有 {total} 行", severity="warning")
                return
            target_row = line_num - 1
            text_area.cursor_location = (target_row, 0)
            text_area.scroll_to((target_row, 0), animate=False)
            self.update_status_bar()

        input_screen = InputScreen("输入行号 (1-{})".format(
            len(self.get_current_text_area().text.splitlines())
        ), callback=do_goto)
        self.push_screen(input_screen)

    # ---------- 文件树 ----------
    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        path = event.path
        if path.is_file():
            self._open_file_by_path(path)

    # ---------- 文件树操作回调 ----------
    def _filetree_menu_callback(self, action: str):
        global CLIPBOARD
        if action is None or not hasattr(self, "_context_path"):
            return
        path = self._context_path

        if action == "new_file":
            def create_file(filename: str):
                new_path = path / filename
                if new_path.exists():
                    self.notify("文件已存在", severity="error")
                    return
                new_path.touch()
                self._refresh_file_tree()
                self._open_file_by_path(new_path)
            self.push_screen(InputScreen("输入文件名:", callback=create_file))

        elif action == "new_folder":
            def create_folder(foldername: str):
                new_path = path / foldername
                if new_path.exists():
                    self.notify("文件夹已存在", severity="error")
                    return
                new_path.mkdir()
                self._refresh_file_tree()
            self.push_screen(InputScreen("输入文件夹名:", callback=create_folder))

        elif action == "open":
            self._open_file_by_path(path)

        elif action == "open_dir":
            self.file_tree.path = path
            self.notify(f"切换到 {path}", severity="information")
            self.refresh()

        elif action == "rename":
            def rename_node(new_name: str):
                new_path = path.parent / new_name
                if new_path.exists():
                    self.notify("目标已存在", severity="error")
                    return
                try:
                    path.rename(new_path)
                    self._refresh_file_tree()
                    self.notify(f"已重命名: {path.name} -> {new_name}", severity="information")
                    abs_new = str(new_path.resolve())
                    for tid, data in self._tab_data.items():
                        if data.get("filepath") == str(path.resolve()):
                            data["filepath"] = abs_new
                            data["title"] = new_path.name
                            data["button"].label = new_path.name
                            self.update_status_bar()
                            break
                except Exception as e:
                    self.notify(f"重命名失败: {e}", severity="error")
            self.push_screen(InputScreen("输入新名称:", callback=rename_node))

        elif action == "move_to":
            def move_to_node(target_dir_str: str):
                target_dir = Path(target_dir_str.strip())
                if not target_dir.exists() or not target_dir.is_dir():
                    self.notify("目标目录不存在或不是目录", severity="error")
                    return
                if target_dir == path.parent:
                    self.notify("已在目标目录", severity="warning")
                    return
                dest = target_dir / path.name
                if dest.exists():
                    def confirm_overwrite(ok: bool):
                        if ok:
                            self._do_move(path, dest)
                    self.push_screen(ConfirmScreen(f"{dest} 已存在，覆盖？", callback=confirm_overwrite))
                else:
                    self._do_move(path, dest)
            self.push_screen(InputScreen("输入目标目录路径:", callback=move_to_node))

        elif action == "copy":
            CLIPBOARD["path"] = path
            CLIPBOARD["is_cut"] = False
            self.notify(f"已复制: {path.name}", severity="information")

        elif action == "paste":
            if CLIPBOARD["path"] is None:
                self.notify("剪贴板为空", severity="warning")
                return
            src = CLIPBOARD["path"]
            if not src.exists():
                self.notify("源文件已不存在", severity="error")
                CLIPBOARD["path"] = None
                return
            dest = path / src.name
            if dest.exists():
                def confirm_overwrite(ok: bool):
                    if ok:
                        self._do_copy(src, dest, CLIPBOARD["is_cut"])
                self.push_screen(ConfirmScreen(f"{dest} 已存在，覆盖？", callback=confirm_overwrite))
            else:
                self._do_copy(src, dest, CLIPBOARD["is_cut"])
            if CLIPBOARD["is_cut"]:
                CLIPBOARD["path"] = None
                CLIPBOARD["is_cut"] = False

        elif action == "delete":
            self._delete_node(path)

    def _do_copy(self, src: Path, dest: Path, is_cut=False):
        try:
            if is_cut:
                shutil.move(str(src), str(dest))
                self.notify(f"已移动: {src.name} -> {dest.parent}", severity="information")
            else:
                if src.is_file():
                    shutil.copy2(str(src), str(dest))
                else:
                    shutil.copytree(str(src), str(dest))
                self.notify(f"已复制: {src.name} -> {dest.parent}", severity="information")
            self._refresh_file_tree()
            if is_cut:
                abs_dest = str(dest.resolve())
                for tid, data in self._tab_data.items():
                    if data.get("filepath") == str(src.resolve()):
                        data["filepath"] = abs_dest
                        data["title"] = dest.name
                        data["button"].label = dest.name
                        self.update_status_bar()
                        break
        except Exception as e:
            self.notify(f"操作失败: {e}", severity="error")

    def _delete_node(self, path: Path):
        def confirm_delete(ok: bool):
            if ok:
                try:
                    if path.is_file():
                        path.unlink()
                    else:
                        shutil.rmtree(path)
                    self._refresh_file_tree()
                    self.notify(f"已删除: {path.name}", severity="information")
                    abs_path = str(path.resolve())
                    for tid, data in list(self._tab_data.items()):
                        if data.get("filepath") == abs_path:
                            self.remove_tab(tid)
                            break
                except Exception as e:
                    self.notify(f"删除失败: {e}", severity="error")
        self.push_screen(ConfirmScreen(f"确定删除 {path.name} 吗？", callback=confirm_delete))

    # ---------- 键盘快捷键 ----------
    def action_rename_node(self):
        tree = self.file_tree
        node = tree.cursor_node
        if node is None:
            self.notify("请先在文件树中选中一个节点", severity="warning")
            return
        data = node.data
        if data is None:
            return
        if hasattr(data, "path"):
            path = Path(data.path)
        else:
            path = Path(str(data))
        self._context_path = path
        self._filetree_menu_callback("rename")

    def action_move_node(self):
        tree = self.file_tree
        node = tree.cursor_node
        if node is None:
            self.notify("请先在文件树中选中一个节点", severity="warning")
            return
        data = node.data
        if data is None:
            return
        if hasattr(data, "path"):
            path = Path(data.path)
        else:
            path = Path(str(data))
        self._context_path = path
        self._filetree_menu_callback("move_to")

    # ---------- 文件树刷新 ----------
    def _refresh_file_tree(self):
        try:
            self.file_tree.reload()
        except AttributeError:
            current_path = self.file_tree.path
            self.file_tree.path = current_path
        self.refresh()

    # ---------- 打开文件 ----------
    def _open_file_by_path(self, path: Path):
        abs_path = str(path.resolve())
        for tid, data in self._tab_data.items():
            if data.get("filepath") == abs_path:
                self.show_tab(tid)
                return
        if len(self._tab_data) >= 9:
            self.notify("最多同时打开 9 个文件", severity="error")
            return
        content = safe_read(abs_path)
        if content is None:
            self.notify(f"无法读取文件: {path}", severity="error")
            return
        title = path.name
        ext = path.suffix.lower()
        lang = detect_language(abs_path)
        tab_id = self.add_new_tab(title, content, abs_path)
        text_area = self._tab_data[tab_id]["textarea"]
        if lang is not None:
            try:
                text_area.language = lang
            except Exception:
                pass
        enc, le = self._get_file_encoding_and_ending(abs_path)
        self._tab_data[tab_id]["encoding"] = enc
        self._tab_data[tab_id]["line_ending"] = le
        self._start_lsp_for_file(abs_path, content)
        self.show_tab(tab_id)

    # ---------- 切换文件树 ----------
    def action_toggle_file_tree(self):
        self.file_tree.display = not self.file_tree.display
        self._show_file_tree = self.file_tree.display
        self.notify("文件树已显示" if self.file_tree.display else "文件树已隐藏", severity="information")
        self.refresh()

    # ---------- LSP 相关 ----------
    def _start_lsp_for_file(self, filepath: str, content: str):
        lang = detect_language(filepath)
        if not lang or lang not in LANG_SERVERS:
            if self.lsp.running:
                self.run_worker(self.lsp.stop(), exclusive=True, group="lsp")
                self._current_lang = None
            self.notify(f"不支持的语言: {lang or '未知'}", severity="warning")
            return
        self._current_uri = path_to_uri(filepath)
        if lang != self._current_lang:
            self.run_worker(self._swap_lsp(lang, filepath, content), exclusive=True, group="lsp")
        elif self.lsp.running:
            self.lsp.did_open(filepath, content)
            self.notify(f"LSP 已连接 ({lang})", severity="information")

    async def _swap_lsp(self, lang, filepath, content):
        await self.lsp.stop()
        root = os.path.dirname(filepath) or "."
        ok = await self.lsp.start(lang, root)
        if ok:
            self._current_lang = lang
            self.lsp.did_open(filepath, content)
            self.notify(f"LSP 已启动 ({lang})", severity="information")
        else:
            self._current_lang = None
            self.notify(f"LSP 启动失败 ({lang})，请检查服务器安装", severity="error")

    # ---------- 补全核心 ----------
    def on_text_area_changed(self, event: TextArea.Changed):
        if event.text_area is self.get_current_text_area():
            self._schedule_completion()

    def _schedule_completion(self):
        if self._completion_timer:
            self._completion_timer.stop()
        self._completion_timer = self.set_timer(0.1, self._trigger_completion)

    def _trigger_completion(self):
        if not self.lsp.running:
            return
        editor = self.get_current_text_area()
        if not editor:
            return
        filepath = self._tab_data.get(self._active_tab_id, {}).get("filepath")
        if not filepath:
            return
        lang = detect_language(filepath)
        if lang != self._current_lang:
            return
        self.lsp.did_change(editor.text)
        row, col = editor.cursor_location
        lines = editor.text.split("\n")
        if row < len(lines) and col > 0:
            ch = lines[row][col - 1]
            if ch.isalnum() or ch == "_" or ch == ".":
                self.run_worker(self._fetch_completions(row, col), exclusive=True, group="completion")
                return
        menu = self.query_one("#completion-menu")
        if menu.visible:
            menu.hide()

    async def _fetch_completions(self, row, col):
        items = await self.lsp.complete(row, col)
        menu = self.query_one("#completion-menu")
        if not items:
            menu.hide()
            return
        editor = self.get_current_text_area()
        if not editor:
            return
        cursor_offset = editor.cursor_screen_offset
        area_region = self.query_one("#editor-area").region
        x = cursor_offset.x - area_region.x
        y = cursor_offset.y - area_region.y + 1
        menu.show(items, (x, y))

    def _insert_completion(self, item):
        editor = self.get_current_text_area()
        if not editor:
            return
        menu = self.query_one("#completion-menu")
        menu.hide()
        additional_edits = item.get("additionalTextEdits")
        if additional_edits:
            for edit in reversed(additional_edits):
                range_ = edit.get("range", {})
                start = range_.get("start", {})
                end = range_.get("end", {})
                start_row = start.get("line", 0)
                start_col = start.get("character", 0)
                end_row = end.get("line", 0)
                end_col = end.get("character", 0)
                new_text = edit.get("newText", "")
                editor.replace(new_text, (start_row, start_col), (end_row, end_col))
        insert_text = item.get("insertText") or item["label"]
        row, col = editor.cursor_location
        lines = editor.text.split("\n")
        line = lines[row] if row < len(lines) else ""
        word_start = col
        while word_start > 0 and (line[word_start - 1].isalnum() or line[word_start - 1] == "_"):
            word_start -= 1
        clean = insert_text.split("(")[0] if "(" in insert_text else insert_text
        editor.replace(clean, (row, word_start), (row, col))
        editor.focus()

    def on_key(self, event):
        menu = self.query_one("#completion-menu")
        if not menu.visible:
            return
        if event.key == "up":
            menu.move_up()
            event.prevent_default()
            event.stop()
        elif event.key == "down":
            menu.move_down()
            event.prevent_default()
            event.stop()
        elif event.key == "tab":
            item = menu.selected_item()
            if item:
                self._insert_completion(item)
            menu.hide()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            menu.hide()
            event.prevent_default()
            event.stop()

    # ---------- LSP 高级功能 ----------
    def _on_diagnostics(self, uri, diagnostics):
        self._diagnostics_cache[uri] = diagnostics
        if uri == self._current_uri:
            self.update_status_bar()

    def action_show_symbols(self):
        if not self.lsp.running:
            self.notify("LSP 未运行", severity="warning")
            return
        editor = self.get_current_text_area()
        if not editor:
            return
        self.lsp.did_change(editor.text)
        self.run_worker(self._fetch_symbols(), exclusive=True, group="symbols")

    async def _fetch_symbols(self):
        symbols = await self.lsp.document_symbol()
        if not symbols:
            self.notify("没有符号", severity="warning")
            return
        self.push_screen(SymbolListScreen(symbols, self))

    def _jump_to_symbol(self, line, col):
        editor = self.get_current_text_area()
        if editor:
            editor.cursor_location = (line, col)
            editor.focus()

    def action_show_hover(self):
        if not self.lsp.running:
            self.notify("LSP 未运行", severity="warning")
            return
        editor = self.get_current_text_area()
        if not editor:
            return
        row, col = editor.cursor_location
        self.lsp.did_change(editor.text)
        self.run_worker(self._fetch_hover(row, col), exclusive=True, group="hover")

    async def _fetch_hover(self, row, col):
        result = await self.lsp.hover(row, col)
        if result:
            self.notify(f"📖 {result}", severity="information", timeout=5)
        else:
            self.notify("无悬停信息", severity="warning")

    def action_show_diagnostics(self):
        current_uri = self._current_uri
        diags = self._diagnostics_cache.get(current_uri, [])
        if not diags:
            self.notify("没有诊断信息", severity="information")
        else:
            self.push_screen(DiagnosticScreen(diags))

    def action_goto_definition(self):
        if not self.lsp.running:
            self.notify("没有运行的语言服务器", severity="warning")
            return
        editor = self.get_current_text_area()
        if not editor:
            return
        self.lsp.did_change(editor.text)
        row, col = editor.cursor_location
        self.run_worker(self._do_goto_definition(row, col), exclusive=True, group="goto-def")

    async def _do_goto_definition(self, row, col):
        result = await self.lsp.goto_definition(row, col)
        if not result:
            self.notify("未找到定义", severity="warning")
            return
        target_path = uri_to_path(result["uri"])
        target_line = result["line"]
        target_col = result["col"]
        self._open_file_by_path(Path(target_path))
        def _jump():
            editor = self.get_current_text_area()
            if editor:
                editor.cursor_location = (target_line, target_col)
                editor.focus()
        self.call_after_refresh(_jump)

    def action_rename_symbol(self):
        if not self.lsp.running:
            self.notify("LSP 未运行", severity="warning")
            return
        editor = self.get_current_text_area()
        if not editor:
            return
        row, col = editor.cursor_location
        self.lsp.did_change(editor.text)
        def do_rename(new_name: str):
            if not new_name:
                return
            self.run_worker(self._do_rename(row, col, new_name), exclusive=True, group="rename")
        self.push_screen(InputScreen("输入新名称:", callback=do_rename))

    async def _do_rename(self, row, col, new_name):
        result = await self.lsp.rename(row, col, new_name)
        if result:
            editor = self.get_current_text_area()
            if editor and "changes" in result:
                changes = result["changes"]
                for uri, edits in changes.items():
                    if uri == self._current_uri:
                        for edit in reversed(edits):
                            range_ = edit.get("range", {})
                            start = range_.get("start", {})
                            end = range_.get("end", {})
                            start_row = start.get("line", 0)
                            start_col = start.get("character", 0)
                            end_row = end.get("line", 0)
                            end_col = end.get("character", 0)
                            new_text = edit.get("newText", "")
                            editor.replace(new_text, (start_row, start_col), (end_row, end_col))
                self.notify("重命名成功", severity="information")
            else:
                self.notify("重命名失败", severity="error")

    def action_code_action(self):
        if not self.lsp.running:
            self.notify("LSP 未运行", severity="warning")
            return
        editor = self.get_current_text_area()
        if not editor:
            return
        row, col = editor.cursor_location
        self.lsp.did_change(editor.text)
        self.run_worker(self._fetch_code_actions(row, col), exclusive=True, group="code-action")

    async def _fetch_code_actions(self, row, col):
        actions = await self.lsp.code_action(row, col)
        if not actions:
            self.notify("没有可用的代码操作", severity="information")
            return
        items = []
        for action in actions:
            title = action.get("title", "操作")
            items.append({"label": title, "action": action, "shortcut": ""})
        def callback(action):
            self._apply_code_action(action)
        self.push_screen(OptionListMenu("代码操作", items, callback))

    def _apply_code_action(self, action):
        if "edit" in action:
            edits = action["edit"]
            editor = self.get_current_text_area()
            if editor and "changes" in edits:
                for uri, edit_list in edits["changes"].items():
                    if uri == self._current_uri:
                        for edit in reversed(edit_list):
                            range_ = edit.get("range", {})
                            start = range_.get("start", {})
                            end = range_.get("end", {})
                            start_row = start.get("line", 0)
                            start_col = start.get("character", 0)
                            end_row = end.get("line", 0)
                            end_col = end.get("character", 0)
                            new_text = edit.get("newText", "")
                            editor.replace(new_text, (start_row, start_col), (end_row, end_col))
        if "command" in action:
            self.notify(f"执行命令: {action['command']['title']}", severity="information")

    def action_format_document(self):
        if not self.lsp.running:
            self.notify("LSP 未运行", severity="warning")
            return
        editor = self.get_current_text_area()
        if not editor:
            return
        self.lsp.did_change(editor.text)
        self.run_worker(self._do_format(), exclusive=True, group="format")

    async def _do_format(self):
        result = await self.lsp.format_document()
        if result:
            editor = self.get_current_text_area()
            if editor:
                # 应用格式编辑（通常只有一个 TextEdit）
                for edit in result:
                    range_ = edit.get("range", {})
                    start = range_.get("start", {})
                    end = range_.get("end", {})
                    start_row = start.get("line", 0)
                    start_col = start.get("character", 0)
                    end_row = end.get("line", 0)
                    end_col = end.get("character", 0)
                    new_text = edit.get("newText", "")
                    editor.replace(new_text, (start_row, start_col), (end_row, end_col))
                self.notify("文档已格式化", severity="information")
        else:
            self.notify("格式化失败", severity="warning")

    # ---------- 工具 ----------
    def focus_editor(self):
        editor = self.get_current_text_area()
        if editor:
            editor.focus()

    def get_current_tab_id(self) -> str:
        return self._active_tab_id

    def get_current_text_area(self) -> TextArea:
        if self._active_tab_id and self._active_tab_id in self._tab_data:
            return self._tab_data[self._active_tab_id]["textarea"]
        return None

    def _load_history(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return []

    def _save_history(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._search_history[-20:], f)
        except:
            pass

    def _add_history(self, query):
        if query and query not in self._search_history:
            self._search_history.append(query)
            self._save_history()


if __name__ == "__main__":
    OneEditor().run()