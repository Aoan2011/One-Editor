# MIT License
# Copyright (c) 2026 Aoan2011
"""编辑器控件：ReadOnlyTextArea / AxiomEditor / CompletionMenu / Bars。"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, Label, OptionList, TextArea
from textual.widgets.option_list import Option
from textual.geometry import Offset


class ReadOnlyTextArea(TextArea):
    """只读文本框，用于输出 / 终端 / Ollama / diff。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_only = True


class AxiomEditor(TextArea):
    """编辑器控件：修复所有不存在的 API，去掉 multicursor / fold / get_cursor_at。"""

    def __init__(self, *args, show_line_numbers=True, language=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.show_line_numbers = show_line_numbers
        self.language = language
        self.read_only = False
        self._hover_timer = None
        self._hover_pos = None

    def on_mount(self) -> None:
        # 从 app 读取缩进配置，避免硬编码
        self.indent_width = getattr(self.app, "_indent_width", 4)
        self.indent_type = getattr(self.app, "_settings", {}).get(
            "indent_type", "spaces"
        )
        self.tab_behavior = "indent"

    # ---- 光标所在行的括号匹配提示 ----
    def _highlight_brackets(self):
        try:
            row, col = self.cursor_location
            lines = self.text.splitlines()
            if row >= len(lines):
                return self.app.update_status_bar()
            line = lines[row]
            if col == 0:
                return self.app.update_status_bar()
            ch = line[col - 1]
            if ch in "([{":
                stack = []
                for i, c in enumerate(line):
                    if c in "([{":
                        stack.append((c, i))
                    elif c in ")]}":
                        if stack and self._match(stack[-1][0], c):
                            stack.pop()
                        else:
                            break
                if stack and stack[-1][1] != col - 1:
                    self.app.status_bar.update(
                        f"🔗 匹配括号: 列 {stack[-1][1] + 1}"
                    )
                else:
                    self.app.update_status_bar()
            else:
                self.app.update_status_bar()
        except Exception:
            self.app.update_status_bar()

    @staticmethod
    def _match(open_c: str, close_c: str) -> bool:
        return (open_c, close_c) in (("(", ")"), ("[", "]"), ("{", "}"))

    def apply_diagnostics(self, diagnostics):
        try:
            row, _ = self.cursor_location
            errors, warnings = [], []
            for diag in diagnostics:
                r = diag.get("range", {})
                s = r.get("start", {})
                if s.get("line", -1) == row:
                    msg = diag.get("message", "")
                    if diag.get("severity", 1) <= 1:
                        errors.append(msg)
                    else:
                        warnings.append(msg)
            if errors:
                self.app.status_bar.update(f"🔴: {'; '.join(errors)}")
            elif warnings:
                self.app.status_bar.update(f"🟡: {'; '.join(warnings)}")
            else:
                self.app.update_status_bar()
        except Exception:
            self.app.update_status_bar()

    # ---- 按键处理 ----
    async def _on_key(self, event):
        key = event.key

        shortcut_map = {
            "ctrl+s": "action_save_file",
            "ctrl+o": "action_open_file",
            "ctrl+n": "action_new_file",
            "ctrl+w": "action_close_file",
            "ctrl+q": "action_quit",
            "ctrl+f": "action_show_find",
            "ctrl+h": "action_show_replace",
            "ctrl+g": "action_goto_line",
            "ctrl+b": "action_toggle_file_tree",
            "f5": "action_run",
            "f6": "action_build",
            "f7": "action_debug",
            "ctrl+`": "action_toggle_terminal",
            "ctrl+shift+p": "action_command_palette",
            "ctrl+d": "action_compare_files",
            "ctrl+k": "action_screenshot",
        }
        if key in shortcut_map:
            getattr(self.app, shortcut_map[key])()
            event.prevent_default()
            event.stop()
            return

        if key == "ctrl+a":
            self.select_all()
            event.prevent_default()
            event.stop()
            return

        # 补全菜单导航
        if key in ("tab", "enter", "up", "down"):
            try:
                menu = self.app.query_one("#completion-menu")
                if getattr(menu, "visible", False):
                    if key == "up":
                        menu.move_up()
                    elif key == "down":
                        menu.move_down()
                    elif key == "tab":
                        item = menu.selected_item()
                        if item:
                            self.app._insert_completion(item)
                        menu.hide()
                    elif key == "enter":
                        menu.hide()
                    event.prevent_default()
                    event.stop()
                    return
            except Exception:
                pass

        # 括号自动补全
        pairs = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
        char = event.character
        if char and char in pairs and not self.read_only:
            start, end = self.selection
            if start != end:
                sel = self.text[start:end]
                self.replace(char + sel + pairs[char], start, end)
                new_cursor = (start[0], start[1] + len(char) + len(sel))
                self.selection = (new_cursor, new_cursor)
            else:
                row, col = self.cursor_location
                lines = self.text.split("\n")
                line = lines[row]
                lines[row] = line[:col] + char + pairs[char] + line[col:]
                self.text = "\n".join(lines)
                self.cursor_location = (row, col + 1)
            self._highlight_brackets()
            event.prevent_default()
            event.stop()
            return

        # Enter 自动缩进
        if not self.read_only and key == "enter":
            event.stop()
            event.prevent_default()
            row, col = self.cursor_location
            lines = self.text.split("\n")
            current = lines[row] if row < len(lines) else ""
            indent = 0
            for c in current:
                if c == " ":
                    indent += 1
                elif c == "\t":
                    indent += self.indent_width
                else:
                    break
            if current[:col].rstrip() and current[:col].rstrip()[-1] in ":{[(":
                indent += self.indent_width
            insertion = "\n" + " " * indent
            start, end = self.selection
            self.replace(insertion, start, end)
            self.cursor_location = (row + 1, indent)
            return

        await super()._on_key(event)


class CompletionMenu(OptionList):
    DEFAULT_CSS = """
    CompletionMenu {
        layer: autocomplete; display: none; height: auto; max-height: 10;
        width: auto; min-width: 30; max-width: 60;
        border: round $accent; background: $surface; padding: 0;
    }
    """
    can_focus = False

    def __init__(self):
        super().__init__(id="completion-menu")
        self.items = []

    def show(self, items, offset):
        self.items = items
        self.clear_options()
        for it in items:
            self.add_option(Option(it["label"]))
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


class FindReplaceBar(Horizontal):
    """查找/替换栏（修复：大小写按钮 label 区分）。"""
    DEFAULT_CSS = """
    FindReplaceBar { height: 3; background: $surface; padding: 0 1; display: none; }
    FindReplaceBar > Input { width: 1fr; margin: 0 1; }
    FindReplaceBar > Button { margin: 0 1; height: 3; }
    .find-btn { padding: 0 1; background: $surface; color: $text; border: none;
                height: 3; }
    .find-btn:hover { background: $panel; }
    """

    def __init__(self, parent_app, find_callback, replace_callback):
        super().__init__()
        self.parent_app = parent_app
        self.find_callback = find_callback
        self.replace_callback = replace_callback
        self.mode = "find"
        self.case_sensitive = False
        self.use_regex = False
        self.find_input: Input | None = None
        self.replace_input: Input | None = None

    def compose(self) -> ComposeResult:
        self.find_input = Input(
            placeholder=self.app._tr("search_placeholder"), id="find-input"
        )
        yield self.find_input
        self.replace_input = Input(
            placeholder=self.app._tr("replace_placeholder"), id="replace-input"
        )
        self.replace_input.display = False
        yield self.replace_input
        yield Button("[Aa]", id="case-btn", classes="find-btn")
        yield Button(".*", id="regex-btn", classes="find-btn")
        yield Button(self.app._tr("find_btn"), id="find-btn",
                     classes="find-btn", variant="primary")
        yield Button(self.app._tr("replace_btn"), id="replace-btn",
                     classes="find-btn", variant="warning")
        yield Button(self.app._tr("replace_all_btn"), id="replace-all-btn",
                     classes="find-btn", variant="warning")
        yield Button(self.app._tr("cancel_find"), id="cancel-btn",
                     classes="find-btn")

    def on_key(self, event):
        if event.key == "escape":
            self.parent_app._hide_find_replace()

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "case-btn":
            self.case_sensitive = not self.case_sensitive
            event.button.label = "[Aa]" if self.case_sensitive else "[aa]"
            event.button.variant = "primary" if self.case_sensitive else "default"
        elif bid == "regex-btn":
            self.use_regex = not self.use_regex
            event.button.variant = "primary" if self.use_regex else "default"
        elif bid == "find-btn":
            q = self.find_input.value
            if q:
                self.find_callback(q, self.case_sensitive, self.use_regex)
        elif bid in ("replace-btn", "replace-all-btn"):
            f = self.find_input.value
            r = self.replace_input.value
            if f:
                self.replace_callback(
                    f, r, bid == "replace-all-btn", self.case_sensitive, self.use_regex
                )
        elif bid == "cancel-btn":
            self.parent_app._hide_find_replace()

    def set_mode(self, mode: str):
        self.mode = mode
        self.replace_input.display = (mode == "replace")
        (self.replace_input if mode == "replace" else self.find_input).focus()


class InputBar(Horizontal):
    """内嵌单行输入栏（替代模态 InputScreen）。"""
    DEFAULT_CSS = """
    InputBar { height: 3; background: $surface; padding: 0 1; display: none; }
    InputBar > Label { width: auto; margin-right: 1; content-align: left middle; }
    InputBar > Input { width: 1fr; margin: 0 1; }
    InputBar > Button { margin: 0 1; height: 3; min-width: 8; }
    """

    def __init__(self, app):
        super().__init__()
        self.app_ref = app
        self._callback = None
        self._prompt_label: Label | None = None
        self.input: Input | None = None

    def compose(self) -> ComposeResult:
        self._prompt_label = Label("")
        yield self._prompt_label
        self.input = Input(id="input-bar-input")
        yield self.input
        yield Button("确认", id="input-bar-confirm", variant="primary")
        yield Button("取消", id="input-bar-cancel")

    def show(self, prompt: str, callback):
        self._prompt_label.update(prompt)
        self.input.value = ""
        self._callback = callback
        self.display = True
        self.input.focus()

    def hide(self):
        self.display = False
        self.input.value = ""
        self._callback = None
        self.app_ref.focus_editor()

    def on_input_submitted(self, event):
        value = event.value.strip()
        if value and self._callback:
            try:
                self._callback(value)
            except Exception as e:
                self.app_ref.notify(f"输入处理失败: {e}", severity="error")
        self.hide()

    def on_button_pressed(self, event):
        if event.button.id == "input-bar-confirm":
            v = self.input.value.strip()
            if v and self._callback:
                try:
                    self._callback(v)
                except Exception as e:
                    self.app_ref.notify(f"输入处理失败: {e}", severity="error")
            self.hide()
        elif event.button.id == "input-bar-cancel":
            self.hide()

    def on_key(self, event):
        if event.key == "escape":
            self.hide()
            event.prevent_default()
            event.stop()


class GoToLineBar(Horizontal):
    DEFAULT_CSS = """
    GoToLineBar { height: 3; background: $surface; padding: 0 1; display: none; }
    GoToLineBar > Input { width: 1fr; margin: 0 1; }
    GoToLineBar > Button { margin: 0 1; height: 3; min-width: 8; }
    """

    def __init__(self, app):
        super().__init__()
        self.app_ref = app
        self.input: Input | None = None

    def compose(self) -> ComposeResult:
        self.input = Input(placeholder="行号 (1-N)", id="goto-input")
        yield self.input
        yield Button("跳转", id="goto-confirm", variant="primary")
        yield Button("取消", id="goto-cancel")

    def on_input_submitted(self, event):
        self.app_ref._do_goto_line(event.value)

    def on_button_pressed(self, event):
        if event.button.id == "goto-confirm":
            self.app_ref._do_goto_line(self.input.value)
        elif event.button.id == "goto-cancel":
            self.app_ref._hide_goto_bar()

    def on_key(self, event):
        if event.key == "escape":
            self.app_ref._hide_goto_bar()