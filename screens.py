# MIT License
# Copyright (c) 2026 Aoan2011
"""所有 ModalScreen 集合 + 编辑器/文件树上下文菜单。

包含：
- InputScreen / SaveConfirmScreen / ExternalChangeScreen
- OptionListMenu / DiagnosticScreen / DiffScreen / AboutScreen
- GlobalSearchScreen（已修复 Windows 路径解析）
- CommandPalette / SymbolListScreen
- SettingsScreen / PluginDetailScreen / PluginsScreen / LanguageSettingsScreen
- WelcomeScreen
- EditorContextMenu / FileTreeContextMenu（从 one-editor.py 迁移）
"""
import difflib
import traceback
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, Input, Label, OptionList, Select, Static,
)
from textual.widgets.option_list import Option

from editor_widgets import ReadOnlyTextArea
from lsp import LANG_SERVERS


# ============================================================
# 基础输入 / 确认
# ============================================================
class InputScreen(ModalScreen):
    """旧式模态输入（保留兼容）。新代码请使用 InputBar。"""

    def __init__(self, prompt, callback):
        super().__init__()
        self.prompt = prompt
        self.callback = callback
        self.input: Input | None = None

    def compose(self) -> ComposeResult:
        try:
            yield Label(self.prompt)
            self.input = Input(placeholder=self.app._tr("input_prompt"))
            yield self.input
            yield Static(self.app._tr("input_enter"))
        except Exception as e:
            yield Label(f"错误: {e}")
            yield Button("关闭", id="input-error-close")

    def on_input_submitted(self, event):
        v = event.value.strip()
        if v:
            try:
                self.callback(v)
            except Exception as e:
                self.app.notify(f"输入处理失败: {e}", severity="error")
                traceback.print_exc()
        self.dismiss()

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()

    def on_button_pressed(self, event):
        if event.button.id == "input-error-close":
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


class SaveConfirmScreen(ModalScreen):
    CSS = """
    SaveConfirmScreen { align: center middle; background: rgba(0,0,0,0.6); }
    #save-box { background: $surface; padding: 2 3; border: round $accent;
                width: 40; height: auto; }
    #save-box > Label { text-align: center; margin: 1 0; }
    #save-box > Horizontal { height: 3; margin: 1 0; }
    #save-box > Button { margin: 0 1; width: 1fr; }
    """

    def __init__(self, message, callback):
        super().__init__()
        self.message = message
        self.callback = callback

    def compose(self) -> ComposeResult:
        with Container(id="save-box"):
            yield Label(self.message)
            with Horizontal():
                yield Button(self.app._tr("save_btn"), id="save", variant="primary")
                yield Button(self.app._tr("nosave_btn"), id="nosave", variant="warning")
                yield Button(self.app._tr("cancel_btn"), id="cancel")

    def on_button_pressed(self, event):
        if event.button.id in ("save", "nosave", "cancel"):
            self.callback(event.button.id)
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


class ExternalChangeScreen(ModalScreen):
    CSS = """
    ExternalChangeScreen { background: rgba(0,0,0,0.6); align: center middle; }
    #container { background: $surface; padding: 2 3; border: tall $primary;
                 width: 50; height: auto; }
    #container > Button { margin: 1 1; width: 1fr; }
    """

    def __init__(self, filepath, callback):
        super().__init__()
        self.filepath = filepath
        self.callback = callback

    def compose(self) -> ComposeResult:
        with Container(id="container"):
            yield Label(f"文件 {Path(self.filepath).name} 已被外部修改", id="msg")
            yield Label("是否重新加载？")
            with Horizontal():
                yield Button(self.app._tr("yes"), variant="primary", id="reload")
                yield Button(self.app._tr("no"), id="ignore")

    def on_button_pressed(self, event):
        self.callback(event.button.id == "reload")
        self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


# ============================================================
# 通用菜单
# ============================================================
class OptionListMenu(ModalScreen):
    CSS = """
    OptionListMenu { background: rgba(0,0,0,0.6); align: center middle; }
    #menu-container { background: $surface; padding: 1 2; border: round $accent;
                      width: auto; min-width: 30; max-width: 60;
                      height: auto; max-height: 20; overflow-y: auto; }
    .menu-item { width: 1fr; padding: 0 1; height: 1;
                 background: $surface; border: none; text-align: left; }
    .menu-item:hover { background: $panel; }
    """

    def __init__(self, title, items, callback):
        super().__init__()
        self.title = title
        self.items = items
        self.callback = callback
        self._dismissed = False

    def compose(self) -> ComposeResult:
        with Container(id="menu-container"):
            if self.title:
                yield Label(self.title, classes="title")
            for i, item in enumerate(self.items):
                if isinstance(item, dict):
                    label = item.get("label", str(item))
                    shortcut = item.get("shortcut", "")
                else:
                    label = str(item)
                    shortcut = ""
                display = f"{label}  ({shortcut})" if shortcut else label
                yield Button(display, id=f"menu_{i}", classes="menu-item")
            yield Button(self.app._tr("cancel"), id="menu_cancel",
                         classes="menu-item")

    def on_button_pressed(self, event):
        if self._dismissed:
            return
        self._dismissed = True
        action = None
        if event.button.id != "menu_cancel":
            try:
                idx = int(event.button.id.split("_")[1])
                if idx < len(self.items):
                    item = self.items[idx]
                    action = item.get("action") if isinstance(item, dict) else item
            except Exception:
                action = None
        self.dismiss()
        if action:
            try:
                self.callback(action)
            except Exception as e:
                self.app.notify(f"菜单执行错误: {e}", severity="error")
                traceback.print_exc()

    def on_key(self, event):
        if event.key == "escape" and not self._dismissed:
            self._dismissed = True
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


# ============================================================
# 诊断 / 对比 / 关于
# ============================================================
class DiagnosticScreen(ModalScreen):
    CSS = """
    DiagnosticScreen { background: rgba(0,0,0,0.6); align: center middle; }
    #diag-container { background: $surface; padding: 1 2; border: round $accent;
                      width: 70; height: 30; overflow-y: auto; }
    .diag-item { margin: 0 0 1 0; padding: 0 1; width: 1fr;
                 border: none; text-align: left; }
    .diag-item:hover { background: $panel; }
    .diag-error { color: $error; }
    .diag-warning { color: $warning; }
    #diag-header { height: 1; background: $surface; margin-bottom: 1; }
    #diag-close { width: 1fr; border: none; background: $surface; color: $text;
                  dock: right; }
    #diag-close:hover { background: $error; color: $text; }
    """

    def __init__(self, diagnostics, app):
        super().__init__()
        self.diagnostics = diagnostics
        self.app_ref = app

    def compose(self) -> ComposeResult:
        with Container(id="diag-container"):
            with Horizontal(id="diag-header"):
                yield Label(f"诊断信息 ({len(self.diagnostics)})", id="diag-title")
                yield Button("✕", id="diag-close", variant="default")
            if not self.diagnostics:
                yield Label("没有诊断信息")
            else:
                for idx, diag in enumerate(self.diagnostics):
                    sev = diag.get("severity", 1)
                    msg = diag.get("message", "")
                    r = diag.get("range", {})
                    s = r.get("start", {})
                    line = s.get("line", 0)
                    col = s.get("character", 0)
                    cls = "diag-error" if sev <= 1 else "diag-warning"
                    tag = "ERROR" if sev <= 1 else "WARNING"
                    btn = Button(
                        f"[{tag}] L{line + 1}:{col + 1} {msg}",
                        id=f"diag_jump_{idx}",
                        classes=f"diag-item {cls}",
                        variant="default",
                    )
                    btn._jump_line = line
                    btn._jump_col = col
                    yield btn

    def on_button_pressed(self, event):
        if event.button.id == "diag-close":
            self.dismiss()
        elif event.button.id and event.button.id.startswith("diag_jump_"):
            line = getattr(event.button, "_jump_line", 0)
            col = getattr(event.button, "_jump_col", 0)
            self.dismiss()
            editor = self.app_ref.get_current_text_area()
            if editor:
                editor.cursor_location = (line, col)
                editor.focus()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


class DiffScreen(ModalScreen):
    CSS = """
    DiffScreen { background: rgba(0,0,0,0.6); align: center middle; }
    #diff-container { background: $surface; padding: 1 2; border: round $accent;
                      width: 90; height: 80%; overflow-y: auto; }
    #diff-area { height: 1fr; border: none; }
    #diff-close { margin-top: 1; width: 1fr; }
    """

    def __init__(self, left_text, right_text, left_title="旧", right_title="新"):
        super().__init__()
        self.left_text = left_text or ""
        self.right_text = right_text or ""
        self.left_title = left_title
        self.right_title = right_title

    def compose(self) -> ComposeResult:
        try:
            left_lines = self.left_text.splitlines() or [""]
            right_lines = self.right_text.splitlines() or [""]
            diff = difflib.unified_diff(
                left_lines, right_lines,
                fromfile=self.left_title, tofile=self.right_title, lineterm="",
            )
            diff_text = "\n".join(diff) or "(无差异)"
            with Container(id="diff-container"):
                yield Label(self.app._tr("diff_title"), id="diff-title")
                yield ReadOnlyTextArea(diff_text, language=None, id="diff-area")
                yield Button(self.app._tr("diff_close"), id="diff-close",
                             variant="primary")
        except Exception as e:
            yield Label(f"对比失败: {e}")
            yield Button("关闭", id="diff-error-close")

    def on_button_pressed(self, event):
        if event.button.id in ("diff-close", "diff-error-close"):
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


class AboutScreen(ModalScreen):
    CSS = """
    AboutScreen { background: rgba(0,0,0,0.6); align: center middle; }
    #about-container { background: $surface; padding: 2 3; border: round $accent;
                       width: 55; height: auto; }
    #about-title { text-style: bold; text-align: center; margin: 1 0; }
    #about-version { text-align: center; color: $text-muted; }
    #about-close { margin-top: 2; width: 1fr; }
    #ascii-art { text-align: center; text-style: bold; margin: 1 0; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="about-container"):
            yield Static(
                """  ___                  _____    _ _ _
 / _ \\ _ __   ___     | ____|__| (_) |_ ___  _ __
| | | | '_ \\ / _ \\    |  _| / _` | | __/ _ \\| '__|
| |_| | | | |  __/    | |__| (_| | | || (_) | |
 \\___/|_| |_|\\___|    |_____\\__,_|_|\\__\\___/|_|   """,
                id="ascii-art",
            )
            yield Label(self.app._tr("about_title"), id="about-title")
            yield Label(self.app._tr("about_version"), id="about-version")
            yield Label(self.app._tr("about_desc"), id="about-desc")
            yield Label(self.app._tr("about_features"), id="about-features")
            yield Label("", id="update-info")
            yield Button("检查更新", id="check-update", variant="default")
            yield Button(self.app._tr("about_close"), id="about-close-btn",
                         variant="primary")

    def on_button_pressed(self, event):
        if event.button.id == "about-close-btn":
            self.dismiss()
        elif event.button.id == "check-update":
            self.run_worker(self._check_update())

    async def _check_update(self):
        import aiohttp
        label = self.query_one("#update-info")
        label.update("正在检查...")
        try:
            async with aiohttp.ClientSession() as session:
                url = ("https://api.github.com/repos/Aoan2011/"
                       "One-Editor/releases/latest")
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        latest = data.get("tag_name", "未知")
                        label.update(f"✅ 最新版本: {latest}")
                    elif resp.status == 404:
                        label.update("⚠️ 该仓库暂无发布版本")
                    else:
                        label.update(f"❌ 检查失败 (HTTP {resp.status})")
        except Exception as e:
            label.update(f"❌ 错误: {e}")

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


# ============================================================
# 全局搜索（修复：rsplit 兼容 Windows）
# ============================================================
class GlobalSearchScreen(ModalScreen):
    CSS = """
    GlobalSearchScreen { background: rgba(0,0,0,0.6); align: center middle; }
    #global-search-container { background: $surface; padding: 1 2;
        border: round $accent; width: 80; height: 60%; overflow-y: auto; }
    #global-search-header { height: 3; }
    #global-search-input { width: 1fr; margin-right: 1; }
    #global-search-count { color: $text-muted; margin-left: 1; }
    #global-search-results { height: 1fr; }
    """

    def __init__(self, root_path: str, callback):
        super().__init__()
        self.root_path = root_path
        self.callback = callback
        self._results: list[tuple[str, int, str]] = []
        self._search_input: Input | None = None
        self._results_list: OptionList | None = None

    def compose(self) -> ComposeResult:
        with Container(id="global-search-container"):
            with Horizontal(id="global-search-header"):
                self._search_input = Input(
                    placeholder=self.app._tr("global_search_placeholder"),
                    id="global-search-input",
                )
                yield self._search_input
                yield Button("搜索", id="global-search-btn", variant="primary")
            yield Static("", id="global-search-count")
            self._results_list = OptionList(id="global-search-results")
            yield self._results_list
            yield Button(self.app._tr("cancel"), id="global-search-close")

    def on_input_submitted(self, event):
        self._perform_search(event.value)

    def on_button_pressed(self, event):
        if event.button.id == "global-search-btn":
            self._perform_search(self._search_input.value)
        elif event.button.id == "global-search-close":
            self.dismiss()

    def _perform_search(self, query: str):
        if not query.strip():
            return
        lines: list[str] = []
        try:
            import subprocess
            proc = subprocess.run(
                ["rg", "--line-number", "--no-heading", "--hidden",
                 "-g", "!.git", query, self.root_path],
                capture_output=True, text=True, timeout=10,
            )
            lines = proc.stdout.splitlines()
        except FileNotFoundError:
            for path in Path(self.root_path).rglob("*"):
                if path.is_file() and not path.name.startswith("."):
                    try:
                        with path.open("r", encoding="utf-8", errors="ignore") as f:
                            for i, line in enumerate(f, 1):
                                if query in line:
                                    lines.append(f"{path}:{i}:{line.rstrip()}")
                    except Exception:
                        pass
        except Exception:
            pass

        self._results = []
        for line in lines:
            # 修复：从右切两刀，兼容 Windows 盘符 C:\...
            parts = line.rsplit(":", 2)
            if len(parts) == 3:
                try:
                    self._results.append((parts[0], int(parts[1]), parts[2]))
                except ValueError:
                    continue
        self._update_display()

    def _update_display(self):
        self._results_list.clear_options()
        if not self._results:
            self.query_one("#global-search-count").update(
                self.app._tr("global_search_no_results")
            )
            return
        self.query_one("#global-search-count").update(
            self.app._tr("global_search_results").format(count=len(self._results))
        )
        for idx, (path, line, content) in enumerate(self._results):
            label = f"{path}:{line}  {content.strip()[:80]}"
            self._results_list.add_option(Option(label, id=f"result_{idx}"))

    def on_option_list_option_selected(self, event):
        opt = event.option
        if opt.id and opt.id.startswith("result_"):
            idx = int(opt.id.split("_")[1])
            self._select_result(idx)

    def _select_result(self, idx):
        if 0 <= idx < len(self._results):
            path, line, _ = self._results[idx]
            self.dismiss()
            self.callback(path, line)

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()


# ============================================================
# 命令面板
# ============================================================
class CommandPalette(ModalScreen):
    CSS = """
    CommandPalette { background: rgba(0,0,0,0.6); align: center middle; }
    #cmd-palette { background: $surface; padding: 1 2; border: round $accent;
                   width: 60; height: auto; max-height: 60%; overflow-y: auto; }
    #cmd-input { width: 1fr; margin-bottom: 1; }
    #cmd-list { height: 1fr; }
    """

    def __init__(self, commands: dict, callback):
        super().__init__()
        self.commands = commands
        self.callback = callback
        self._filtered: list[tuple[str, str]] = []
        self._input: Input | None = None
        self._list: OptionList | None = None

    def compose(self) -> ComposeResult:
        with Container(id="cmd-palette"):
            self._input = Input(placeholder="输入命令...", id="cmd-input")
            yield self._input
            self._list = OptionList(id="cmd-list")
            yield self._list
            yield Button(self.app._tr("cancel"), id="cmd-cancel")

    def on_mount(self):
        self._update_list("")

    def on_input_changed(self, event):
        self._update_list(event.value)

    def on_input_submitted(self, event):
        if self._list.highlighted is not None:
            self._select(self._list.highlighted)

    def _update_list(self, query: str):
        self._list.clear_options()
        q = query.lower()
        self._filtered = [
            (a, d) for a, d in self.commands.items()
            if q in a.lower() or q in d.lower()
        ]
        for idx, (action, desc) in enumerate(self._filtered):
            self._list.add_option(Option(f"{desc}   ({action})", id=f"cmd_{idx}"))

    def on_option_list_option_selected(self, event):
        idx = int(event.option.id.split("_")[1])
        self._select(idx)

    def _select(self, idx):
        if 0 <= idx < len(self._filtered):
            action, _ = self._filtered[idx]
            self.dismiss()
            self.callback(action)

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()


# ============================================================
# 符号列表
# ============================================================
class SymbolListScreen(OptionListMenu):
    def __init__(self, symbols, app):
        self.symbols = symbols
        self.app_ref = app
        items = [
            {"label": f"{s['name']}  (行 {s['line'] + 1})", "action": s}
            for s in symbols
        ]

        def cb(sym):
            app_ref._jump_to_symbol(sym["line"], sym["col"])

        super().__init__("符号列表", items, cb)


# ============================================================
# 设置
# ============================================================
class SettingsScreen(ModalScreen):
    CSS = """
    SettingsScreen { background: rgba(0,0,0,0.6); align: center middle; }
    #settings-container { background: $surface; padding: 2 3; border: round $accent;
                          width: 60; height: auto; max-height: 80%; overflow-y: auto; }
    #settings-container > Label { margin: 1 0; }
    #settings-container > Select, #settings-container > Input,
    #settings-container > Checkbox { margin: 0 0 1 0; }
    """

    def __init__(self, app):
        super().__init__()
        self.app_ref = app
        self._settings = app._settings
        self.theme_select: Select | None = None
        self.indent_input: Input | None = None
        self.autosave_input: Input | None = None
        self.line_numbers_check: Checkbox | None = None
        self.dir_input: Input | None = None
        self.indent_type: Select | None = None
        self.font_input: Input | None = None
        self.wrap_check: Checkbox | None = None
        self.lang_select: Select | None = None

    def compose(self) -> ComposeResult:
        try:
            with Container(id="settings-container"):
                yield Label(self.app._tr("settings"), classes="title",
                            id="settings-title")
                yield Label(self.app._tr("theme") + ":")
                themes = ["textual-dark", "textual-light", "dracula", "nord",
                          "ansi-dark", "ansi-light"]
                cur_theme = str(self._settings.get("theme", themes[0]))
                if cur_theme not in themes:
                    cur_theme = themes[0]
                self.theme_select = Select(
                    [(t, t) for t in themes], value=cur_theme, allow_blank=False
                )
                yield self.theme_select

                yield Label(self.app._tr("indent") + ":")
                self.indent_input = Input(
                    value=str(self._settings.get("indent_width", 4)),
                    type="integer",
                )
                yield self.indent_input

                yield Label(self.app._tr("autosave") + ":")
                self.autosave_input = Input(
                    value=str(self._settings.get("autosave_interval", 0)),
                    type="integer",
                )
                yield self.autosave_input

                self.line_numbers_check = Checkbox(
                    self.app._tr("line_numbers"),
                    value=self._settings.get("show_line_numbers", True),
                )
                yield self.line_numbers_check

                yield Label(self.app._tr("default_dir") + ":")
                self.dir_input = Input(
                    value=self._settings.get("default_dir", str(Path.home())),
                    id="dir-input",
                )
                yield self.dir_input

                yield Label(self.app._tr("indent_type_label") + ":")
                itype = str(self._settings.get("indent_type", "spaces"))
                if itype not in ("spaces", "tabs"):
                    itype = "spaces"
                self.indent_type = Select(
                    [(self.app._tr("spaces"), "spaces"),
                     (self.app._tr("tabs"), "tabs")],
                    value=itype, allow_blank=False,
                )
                yield self.indent_type

                yield Label(self.app._tr("font_size_label") + ":")
                self.font_input = Input(
                    value=str(self._settings.get("font_size", 12)),
                    type="integer",
                )
                yield self.font_input

                self.wrap_check = Checkbox(
                    self.app._tr("wrap_label"),
                    value=self._settings.get("wrap", True),
                )
                yield self.wrap_check

                yield Label(self.app._tr("language_label") + ":")
                lang = str(self._settings.get("language", "zh"))
                if lang not in ("zh", "en"):
                    lang = "zh"
                self.lang_select = Select(
                    [(self.app._tr("language_zh"), "zh"),
                     (self.app._tr("language_en"), "en")],
                    value=lang, allow_blank=False,
                )
                yield self.lang_select

                yield Label(" ")
                yield Button(self.app._tr("save_settings"),
                             variant="primary", id="save-settings")
                yield Button(self.app._tr("cancel"), id="cancel-settings")
        except Exception as e:
            yield Label(f"设置加载失败: {e}")
            yield Button("关闭", id="settings-error-close")
            traceback.print_exc()

    def on_button_pressed(self, event):
        if event.button.id == "settings-error-close":
            self.dismiss()
            return
        if event.button.id != "save-settings":
            self.dismiss()
            return
        try:
            if self.theme_select.value:
                self._settings["theme"] = self.theme_select.value
                self.app_ref.theme = self.theme_select.value
            try:
                indent = int(self.indent_input.value)
                if indent > 0:
                    self._settings["indent_width"] = indent
                    self.app_ref._indent_width = indent
                    for d in self.app_ref._tab_data.values():
                        d["textarea"].indent_width = indent
            except Exception:
                pass
            try:
                interval = int(self.autosave_input.value)
                self._settings["autosave_interval"] = interval
                self.app_ref._autosave_interval = interval
            except Exception:
                pass
            show = self.line_numbers_check.value
            self._settings["show_line_numbers"] = show
            self.app_ref._show_line_numbers = show
            for d in self.app_ref._tab_data.values():
                d["textarea"].show_line_numbers = show
            self._settings["default_dir"] = self.dir_input.value
            self._settings["indent_type"] = self.indent_type.value
            try:
                self._settings["font_size"] = int(self.font_input.value)
            except Exception:
                self._settings["font_size"] = 12
            self._settings["wrap"] = self.wrap_check.value
            for d in self.app_ref._tab_data.values():
                d["textarea"].wrap = self.wrap_check.value
            if self.lang_select.value:
                self._settings["language"] = self.lang_select.value
                self.app_ref._language = self.lang_select.value
            self.app_ref._save_settings()
            self.dismiss()
            self.app_ref.notify(self.app._tr("save_settings"), severity="information")
        except Exception as e:
            self.app_ref.notify(f"保存设置失败: {e}", severity="error")
            traceback.print_exc()

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


# ============================================================
# 插件
# ============================================================
class PluginDetailScreen(ModalScreen):
    CSS = """
    PluginDetailScreen { background: rgba(0,0,0,0.6); align: center middle; }
    #plugin-detail-box { background: $surface; padding: 2 3;
                         border: round $accent; width: 60; height: auto;
                         max-height: 80%; overflow-y: auto; }
    #plugin-detail-box > Label { margin: 1 0; }
    #plugin-detail-box > Label.title { text-style: bold; margin-bottom: 2; }
    #plugin-detail-box > Label.author { color: $text-muted; margin-bottom: 2; }
    #plugin-detail-box > Button { width: 100%; margin-top: 1; }
    """

    def __init__(self, name, desc, is_builtin=True, settings_format=""):
        super().__init__()
        self.plugin_name = name
        self.desc = desc
        self.is_builtin = is_builtin
        self.settings_format = settings_format

    def compose(self) -> ComposeResult:
        with Container(id="plugin-detail-box"):
            yield Label(f"插件名称: {self.plugin_name}", classes="title")
            yield Label(f"类型: {'内置' if self.is_builtin else '外部'}")
            yield Label(f"介绍: {self.desc}")
            yield Label(f"设置格式: {self.settings_format}")
            yield Label("作者: @Aoan2011", classes="author")
            yield Button("关闭", id="close")

    def on_button_pressed(self, event):
        self.dismiss()


class PluginsScreen(ModalScreen):
    CSS = """
    PluginsScreen { background: rgba(0,0,0,0.6); align: center middle; }
    #plugins-container { background: $surface; padding: 2 3;
        border: round $accent; width: 80; height: auto; max-height: 80%;
        overflow-y: auto; overflow-x: auto; min-width: 0; }
    .plugin-header { height: 2; background: $panel; text-style: bold; padding: 0 1; }
    .plugin-row { height: auto; min-height: 4; padding: 0 1; margin: 0 0 1 0;
                  background: $surface; border: none; min-width: 100%; }
    .plugin-row:hover { background: $panel; }
    .plugin-name { width: 12; }
    .plugin-server { width: 20; }
    .plugin-status { width: 10; }
    .plugin-features { width: 1fr; }
    .toggle-btn { width: auto; min-width: 12; height: 3; border: none;
                  background: $primary; color: $text; padding: 0 2; }
    .toggle-btn.off { background: $surface; color: $text-muted; }
    .settings-btn { width: auto; min-width: 8; height: 3; border: none;
                    background: $accent; color: $text; padding: 0 2; }
    .settings-btn:hover { background: $primary; }
    #plugins-close { dock: right; border: none; background: $surface;
                     color: $text; }
    #plugins-close:hover { background: $error; color: $text; }
    .feature-row { height: auto; min-height: 2; padding: 0 1; min-width: 100%; }
    """

    def __init__(self, app):
        super().__init__()
        self.app_ref = app
        self.plugin_config = self._load_config()

    def _load_config(self):
        from config import ConfigManager
        default = {}
        for lang in LANG_SERVERS.keys():
            default[lang] = {
                "enabled": True,
                "features": {
                    "completion": True, "definition": True, "hover": True,
                    "diagnostics": True, "rename": True, "code_action": True,
                    "formatting": True,
                },
                "compile_cmd": "",
                "run_cmd": "",
            }
        default["competitive-companion"] = {
            "enabled": False,
            "features": {"problem_parsing": False, "test_runner": False},
            "description": self.app._tr("plugin_desc"),
        }
        default["git"] = {
            "enabled": True,
            "features": {"status": True, "stage": True, "commit": True},
            "description": "Git 集成",
        }
        default["ollama"] = {
            "enabled": True,
            "features": {"chat": True, "insert": True},
            "description": "Ollama 对话",
        }
        saved = ConfigManager.load_plugin_config()
        for k, v in saved.items():
            if k in default:
                default[k].update(v)
        return default

    def _save_config(self):
        from config import ConfigManager
        ConfigManager.save_plugin_config(self.plugin_config)

    def compose(self) -> ComposeResult:
        import shutil
        with Container(id="plugins-container"):
            yield Horizontal(
                Label(self.app._tr("menu_plugins"), id="plugins-title"),
                Button("✕", id="plugins-close"),
                classes="plugin-header",
            )
            yield Horizontal(
                Label("名称", classes="plugin-name"),
                Label("服务器/状态", classes="plugin-server"),
                Label("状态", classes="plugin-status"),
                Label(self.app._tr("plugin_features"), classes="plugin-features"),
                Label("操作", classes="plugin-actions"),
                classes="plugin-header",
            )
            for name, cfg in self.plugin_config.items():
                if name in ("competitive-companion", "git", "ollama"):
                    status = (self.app._tr("plugin_enable") if cfg.get("enabled", True)
                              else self.app._tr("plugin_disable"))
                    desc = cfg.get("description", "")
                    with Container(classes="plugin-row"):
                        yield Horizontal(
                            Label(name, classes="plugin-name"),
                            Label("built-in", classes="plugin-server"),
                            Label(status, classes="plugin-status"),
                            Label(desc, classes="plugin-features"),
                            Button(self.app._tr("plugin_toggle"),
                                   id=f"toggle_{name}", classes="toggle-btn"),
                            Button("详情", id=f"detail_{name}",
                                   classes="settings-btn"),
                        )
                        cbs = [
                            Checkbox(f, value=enabled,
                                     id=f"feature_{name}_{f}")
                            for f, enabled in cfg.get("features", {}).items()
                        ]
                        if cbs:
                            yield Horizontal(*cbs, classes="feature-row")
                else:
                    server = LANG_SERVERS.get(name, ["未安装"])
                    installed = shutil.which(server[0]) is not None if server else False
                    status = (self.app._tr("plugin_enable") if cfg.get("enabled", True)
                              else self.app._tr("plugin_disable"))
                    with Container(classes="plugin-row"):
                        yield Horizontal(
                            Label(name, classes="plugin-name"),
                            Label(server[0] if installed
                                  else self.app._tr("plugin_install"),
                                  classes="plugin-server"),
                            Label(status, classes="plugin-status"),
                            Label(" ", classes="plugin-features"),
                            Button(self.app._tr("plugin_toggle"),
                                   id=f"toggle_{name}", classes="toggle-btn"),
                            Button("设置", id=f"settings_{name}",
                                   classes="settings-btn"),
                        )
                        cbs = [
                            Checkbox(f, value=enabled,
                                     id=f"feature_{name}_{f}")
                            for f, enabled in cfg.get("features", {}).items()
                        ]
                        if cbs:
                            yield Horizontal(*cbs, classes="feature-row")
            yield Button(self.app._tr("plugin_save"),
                         variant="primary", id="save-plugins")
            yield Button(self.app._tr("cancel"), id="cancel-plugins")

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid in ("plugins-close", "cancel-plugins"):
            self.dismiss()
        elif bid and bid.startswith("toggle_"):
            name = bid.split("_", 1)[1]
            self.plugin_config[name]["enabled"] = not self.plugin_config[name]["enabled"]
            self._save_config()
            if name == "competitive-companion":
                if self.plugin_config[name]["enabled"]:
                    self.app_ref._start_companion()
                else:
                    self.app_ref._stop_companion()
            self.dismiss()
            self.app_ref.push_screen(PluginsScreen(self.app_ref))
        elif bid and bid.startswith("detail_"):
            name = bid.split("_", 1)[1]
            desc = self.plugin_config[name].get("description", "")
            fmt = ""
            if name == "git":
                fmt = '{"git": {"enabled": true}}'
            elif name == "ollama":
                fmt = '{"ollama": {"enabled": true, "model": "..."}}'
            self.app.push_screen(PluginDetailScreen(name, desc, True, fmt))
        elif bid and bid.startswith("settings_"):
            name = bid.split("_", 1)[1]
            self.app_ref.push_screen(
                LanguageSettingsScreen(name, self.plugin_config[name], self)
            )
        elif bid == "save-plugins":
            for name in self.plugin_config:
                for f in self.plugin_config[name].get("features", {}):
                    try:
                        self.plugin_config[name]["features"][f] = (
                            self.query_one(f"#feature_{name}_{f}", Checkbox).value
                        )
                    except Exception:
                        pass
            self._save_config()
            self.dismiss()
            self.app_ref.notify(self.app._tr("plugin_save"),
                                severity="information")

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


class LanguageSettingsScreen(ModalScreen):
    CSS = """
    LanguageSettingsScreen { background: rgba(0,0,0,0.6); align: center middle; }
    #lang-settings-container { background: $surface; padding: 2 3;
        border: round $accent; width: 60; height: auto; max-height: 80%;
        overflow-y: auto; }
    #lang-settings-container > Label { margin: 1 0; }
    #lang-settings-container > Input { margin: 0 0 1 0; }
    """

    def __init__(self, lang, config, parent_screen):
        super().__init__()
        self.lang = lang
        self.config = config
        self.parent_screen = parent_screen
        self.compile_input: Input | None = None
        self.run_input: Input | None = None

    def compose(self) -> ComposeResult:
        with Container(id="lang-settings-container"):
            yield Label(f"{self.lang} 设置", classes="title")
            yield Label(self.app._tr("compile_cmd") + ":")
            self.compile_input = Input(
                value=self.config.get("compile_cmd", ""), id="compile-cmd"
            )
            yield self.compile_input
            yield Label(self.app._tr("run_cmd") + ":")
            self.run_input = Input(
                value=self.config.get("run_cmd", ""), id="run-cmd"
            )
            yield self.run_input
            yield Label(
                "支持变量: {FilePath}, \n{FilePathWithNoExtension}, \n"
                "{FileName}, \n{FileNameWithNoExtension}, \n{DirPath}",
                classes="hint",
            )
            yield Label(" ")
            yield Button("保存", variant="primary", id="save-lang-settings")
            yield Button(self.app._tr("cancel"), id="cancel-lang-settings")

    def on_button_pressed(self, event):
        if event.button.id == "save-lang-settings":
            self.config["compile_cmd"] = self.compile_input.value
            self.config["run_cmd"] = self.run_input.value
            self.parent_screen._save_config()
            self.dismiss()
            self.app.notify(f"{self.lang} 设置已保存", severity="information")
        elif event.button.id == "cancel-lang-settings":
            self.dismiss()

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


# ============================================================
# 欢迎页
# ============================================================
class WelcomeScreen(ModalScreen):
    CSS = """
    WelcomeScreen { background: $surface; }
    #welcome-container { align: center middle; width: 100%; height: 100%;
                         background: $surface; }
    #welcome-box { width: 60; height: auto; background: $surface;
                   border: round $primary; padding: 2 4; }
    #welcome-title { text-style: bold; font-size: 20; text-align: center;
                     color: $primary; }
    #welcome-subtitle { text-align: center; color: $text-muted; margin: 1 0; }
    #welcome-actions { margin: 2 0; layout: vertical; align: center middle; }
    .welcome-btn { width: 30; margin: 0 1; padding: 0 2; text-align: center; }
    #welcome-tips { text-align: center; color: $text-muted; margin-top: 2; }
    """

    def compose(self) -> ComposeResult:
        with Container(id="welcome-container"):
            with Container(id="welcome-box"):
                yield Label("🚀 " + self.app._tr("welcome_title"),
                            id="welcome-title")
                yield Label(self.app._tr("welcome_subtitle"), id="welcome-subtitle")
                with Vertical(id="welcome-actions"):
                    yield Button(self.app._tr("new"), id="welcome-new",
                                 classes="welcome-btn", variant="primary")
                    yield Button(self.app._tr("open"), id="welcome-open",
                                 classes="welcome-btn", variant="default")
                yield Label(self.app._tr("welcome_tips"), id="welcome-tips")

    def on_button_pressed(self, event):
        if event.button.id == "welcome-new":
            self.app.action_new_file()
            self.dismiss()
        elif event.button.id == "welcome-open":
            self.app.action_open_file()
            self.dismiss()

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()


# ============================================================
# 编辑器 / 文件树上下文菜单
# ============================================================
class EditorContextMenu(OptionListMenu):
    def __init__(self, text_area):
        self.text_area = text_area
        items = [
            {"label": "撤销", "action": "undo"},
            {"label": "重做", "action": "redo"},
            {"label": "剪切", "action": "cut"},
            {"label": "复制", "action": "copy"},
            {"label": "粘贴", "action": "paste"},
            {"label": "全选", "action": "select_all", "shortcut": "Ctrl+A"},
            {"label": "保存", "action": "save"},
            {"label": "另存为...", "action": "save_as"},
            {"label": "关闭标签", "action": "close"},
            {"label": "格式化文档", "action": "format"},
            {"label": "代码大纲", "action": "symbols"},
            {"label": "悬停提示", "action": "hover"},
            {"label": "快速修复", "action": "code_action"},
            {"label": "重命名符号", "action": "rename_symbol"},
        ]

        def cb(action):
            app = self.app
            try:
                if action == "undo":
                    self.text_area.undo()
                elif action == "redo":
                    self.text_area.redo()
                elif action == "cut":
                    self.text_area.cut()
                elif action == "copy":
                    self.text_area.copy()
                elif action == "paste":
                    # 修复：使用 TextArea 内置 paste（读取系统剪贴板）
                    self.text_area.paste()
                elif action == "select_all":
                    self.text_area.select_all()
                elif action == "save":
                    app.action_save_file()
                elif action == "save_as":
                    app.action_save_as()
                elif action == "close":
                    app.action_close_file()
                elif action == "format":
                    app.action_format_document()
                elif action == "symbols":
                    app.action_show_symbols()
                elif action == "hover":
                    app.action_show_hover()
                elif action == "code_action":
                    app.action_code_action()
                elif action == "rename_symbol":
                    app.action_rename_symbol()
            except Exception as e:
                app.notify(f"操作失败: {e}", severity="error", timeout=5)

        super().__init__("编辑器", items, cb)


class FileTreeContextMenu(OptionListMenu):
    def __init__(self, path, is_file):
        from git import Repo, InvalidGitRepositoryError
        self.path = path
        self.is_file = is_file

        items = [
            {"label": "新建文件", "action": "new_file"},
            {"label": "新建文件夹", "action": "new_folder"},
            {"label": "打开" if is_file else "打开文件夹",
             "action": "open" if is_file else "open_dir"},
            {"label": "重命名", "action": "rename"},
            {"label": "移动至...", "action": "move_to"},
            {"label": "复制", "action": "copy"},
            {"label": "粘贴", "action": "paste"},
            {"label": "删除", "action": "delete"},
        ]
        try:
            Repo(path, search_parent_directories=True)
            items += [
                {"label": "--- Git ---", "action": None},
                {"label": "Git 提交...", "action": "git_commit"},
                {"label": "Git 状态", "action": "git_status"},
                {"label": "Git 暂存当前文件", "action": "git_stage"},
                {"label": "Git 撤销修改", "action": "git_checkout"},
            ]
        except InvalidGitRepositoryError:
            pass

        def cb(action):
            app = self.app
            try:
                app._context_path = self.path
                if action is None:
                    return
                if isinstance(action, str) and action.startswith("git_"):
                    app._git_action(action)
                else:
                    app._filetree_menu_callback(action)
            except Exception as e:
                app.notify(f"文件树操作失败: {e}", severity="error", timeout=5)

        super().__init__("文件树", items, cb)