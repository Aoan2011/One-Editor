# MIT License (同原文件)
"""底部 / 侧边面板：输出、终端、Ollama、文件浏览器。"""
import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DirectoryTree, Input, Label, Select, Static

from editor_widgets import ReadOnlyTextArea


class ScrollToBottomMixin:
    """抽取 _scroll_to_bottom，供多个面板复用。"""
    output_area: ReadOnlyTextArea

    def _scroll_to_bottom(self):
        try:
            lines = len(self.output_area.text.splitlines())
            if lines > 0:
                self.call_after_refresh(
                    lambda: self.output_area.scroll_to((lines - 1, 0), animate=False)
                )
        except Exception:
            pass


class OutputPanel(Vertical, ScrollToBottomMixin):
    DEFAULT_CSS = """
    OutputPanel { height: 10; background: $surface; border: tall $primary;
                  display: none; padding: 0 1; margin: 0; }
    OutputPanel > Horizontal#output-header { height: 3; background: $surface;
                  border-bottom: tall $primary; align: left middle; }
    #output-title { width: 1fr; padding: 0 1; text-style: bold; }
    #output-close { dock: right; background: $error; color: $text;
                    border: none; height: 3; min-width: 4;
                    content-align: center middle; }
    OutputPanel > TextArea { border: none; background: $surface; height: 1fr; }
    """

    def __init__(self):
        super().__init__()
        self.output_title: Optional[Label] = None
        self.output_area: Optional[ReadOnlyTextArea] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="output-header"):
            self.output_title = Label("输出", id="output-title")
            yield self.output_title
            yield Button("✕", id="output-close", variant="error")
        self.output_area = ReadOnlyTextArea(language=None, id="output-area")
        yield self.output_area

    def set_command(self, cmd):
        if isinstance(cmd, list):
            cmd = " ".join(str(x) for x in cmd)
        self.output_title.update(f"运行中: {cmd}")

    def clear(self):
        self.output_area.text = ""

    def on_button_pressed(self, event):
        if event.button.id == "output-close":
            self.display = False
            self.clear()


class TerminalPanel(Vertical, ScrollToBottomMixin):
    DEFAULT_CSS = """
    TerminalPanel { height: 12; background: $surface; border: tall $primary;
                    display: none; padding: 0 1; margin: 0; }
    TerminalPanel > TextArea { border: none; background: $surface; height: 1fr; }
    TerminalPanel > Horizontal { height: 3; margin: 0 0 1 0; }
    TerminalPanel > Horizontal > Input { width: 1fr; margin: 0 1; }
    TerminalPanel > Horizontal > Button { margin: 0 1; height: 3; }
    """

    def __init__(self, app):
        super().__init__()
        self.app_ref = app
        self.process = None
        self.current_dir = Path.cwd()
        self._history: list[str] = []
        self._history_index = 0
        self.output_area: Optional[ReadOnlyTextArea] = None
        self.input: Optional[Input] = None

    def compose(self) -> ComposeResult:
        self.output_area = ReadOnlyTextArea(language=None, id="terminal-output")
        yield self.output_area
        with Horizontal(id="terminal-buttons"):
            self.input = Input(placeholder="输入命令...", id="terminal-input")
            yield self.input
            yield Button("清空", id="terminal-clear")
            yield Button("关闭", id="terminal-close")

    def on_input_submitted(self, event):
        cmd = event.value.strip()
        if not cmd:
            return
        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
        self._history_index = len(self._history)
        event.input.value = ""
        self.output_area.text += f"\n$ {cmd}\n"
        self._scroll_to_bottom()
        self.app_ref.run_worker(self._run_command(cmd))

    def on_button_pressed(self, event):
        if event.button.id == "terminal-clear":
            self.clear()
        elif event.button.id == "terminal-close":
            self.app_ref.action_toggle_terminal()

    def on_key(self, event):
        if event.key == "ctrl+c" and self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
            event.prevent_default()
            event.stop()
            return
        if not self.input.has_focus:
            return
        if event.key == "up" and self._history_index > 0:
            self._history_index -= 1
            self.input.value = self._history[self._history_index]
            event.prevent_default()
            event.stop()
        elif event.key == "down" and self._history_index < len(self._history):
            self._history_index += 1
            if self._history_index < len(self._history):
                self.input.value = self._history[self._history_index]
            else:
                self.input.value = ""
            event.prevent_default()
            event.stop()

    async def _run_command(self, cmd: str):
        if self.process:
            self.output_area.text += "\n[上一个进程仍在运行，请先按 Ctrl+C 终止]\n"
            return
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.current_dir),
                creationflags=flags,
            )
        except Exception as e:
            self.output_area.text += f"\n[启动失败] {e}\n"
            self._scroll_to_bottom()
            self.process = None
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
                self.output_area.text += text
                self._scroll_to_bottom()

        try:
            await asyncio.gather(
                pump(self.process.stdout),
                pump(self.process.stderr),
                return_exceptions=True,
            )
            await self.process.wait()
            self.output_area.text += f"\n[进程结束，退出码 {self.process.returncode}]\n"
            self._scroll_to_bottom()
        except asyncio.CancelledError:
            if self.process:
                try:
                    self.process.terminate()
                    await self.process.wait()
                except Exception:
                    pass
            self.output_area.text += "\n[进程已终止]\n"
            self._scroll_to_bottom()
            raise
        finally:
            self.process = None

    def clear(self):
        self.output_area.text = ""

    def set_cwd(self, path):
        self.current_dir = Path(path).resolve()


class OllamaPanel(Vertical, ScrollToBottomMixin):
    """Ollama 对话面板（修复：动态拉取模型列表）。"""
    DEFAULT_CSS = """
    OllamaPanel { height: 16; background: $surface; border: tall $primary;
                  display: none; padding: 0 1; margin: 0;
                  overflow-x: auto; overflow-y: auto; }
    OllamaPanel > TextArea { border: none; background: $surface; height: 1fr;
                             scrollbar-size: 1 1; overflow-x: auto; }
    OllamaPanel > Horizontal.controls { height: 3; margin: 0 0 1 0;
                  align: center middle; overflow-x: auto; }
    OllamaPanel > Horizontal.controls > Select { width: 30; margin: 0 1; }
    OllamaPanel > Horizontal.controls > Button { width: auto; min-width: 10;
                  padding: 0 2; height: 3; margin: 0 1; }
    OllamaPanel > Input { width: 1fr; margin: 0 1 1 1; height: 3; }
    """

    WELCOME = (
        "💬 Ollama 对话面板\n"
        "输入问题并按 Enter 开始对话\n"
        "支持选择模型、中途停止、智能插入代码。"
    )

    def __init__(self, app):
        super().__init__()
        self.app_ref = app
        self.output_area: Optional[ReadOnlyTextArea] = None
        self.model_select: Optional[Select] = None
        self.input: Optional[Input] = None
        self.stop_btn: Optional[Button] = None
        self._history: list[str] = []
        self._history_index = 0
        self._conversation: list[dict] = []
        self._ollama_url = "http://localhost:11434"
        self._ollama_model = "gpt-oss:20b-cloud"
        self._is_loading = False
        self._stop_flag = False

    def compose(self) -> ComposeResult:
        self.output_area = ReadOnlyTextArea(language=None, id="ollama-output")
        yield self.output_area
        with Horizontal(classes="controls"):
            yield Label("模型:")
            self.model_select = Select(
                options=[("加载中...", "loading")], allow_blank=False
            )
            yield self.model_select
            self.stop_btn = Button("停止生成", id="ollama-stop",
                                   variant="error", disabled=True)
            yield self.stop_btn
            yield Button("复制回复", id="ollama-copy")
            yield Button("插入代码", id="ollama-insert", variant="primary")
            yield Button("清空对话", id="ollama-clear")
            yield Button("关闭", id="ollama-close")
        self.input = Input(placeholder=self.app_ref._tr("ollama_input"),
                           id="ollama-input")
        yield self.input

    def on_mount(self):
        self._ollama_url = self.app_ref._settings.get(
            "ollama_url", "http://localhost:11434"
        )
        self._ollama_model = self.app_ref._settings.get(
            "ollama_model", "gpt-oss:20b-cloud"
        )
        self.output_area.text = self.WELCOME
        self.run_worker(self._load_models(), exclusive=True, group="ollama-models")

    async def _load_models(self):
        """动态拉取 /api/tags。失败则回退到默认模型。"""
        import urllib.request
        try:
            url = self._ollama_url.rstrip("/") + "/api/tags"
            data = await asyncio.to_thread(
                lambda: urllib.request.urlopen(url, timeout=5).read()
            )
            names = [m["name"] for m in json.loads(data).get("models", [])]
        except Exception:
            names = []
        if not names:
            names = [self._ollama_model]
        options = [(n, n) for n in names]
        self.model_select.set_options(options)
        if self._ollama_model in names:
            self.model_select.value = self._ollama_model
        else:
            self.model_select.value = names[0]

    def on_input_submitted(self, event):
        msg = event.value.strip()
        if not msg or self._is_loading:
            return
        event.input.value = ""
        self._history.append(msg)
        self._history_index = len(self._history)
        if self.output_area.text.startswith("💬"):
            self.output_area.text = ""
        self.output_area.text += f"\n🧑 你: {msg}\n"
        self._scroll_to_bottom()
        self.run_worker(self._send_ollama(msg))

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "ollama-stop":
            self._stop_flag = True
            self.notify("正在停止生成...", severity="warning")
        elif bid == "ollama-copy":
            if hasattr(self.app, "copy_to_clipboard"):
                self.app.copy_to_clipboard(self.output_area.text)
                self.notify("回复已复制到剪贴板", severity="information")
            else:
                self.notify("请手动复制文本", severity="warning")
        elif bid == "ollama-insert":
            self._insert_code()
        elif bid == "ollama-clear":
            self.clear()
        elif bid == "ollama-close":
            self.app_ref.action_toggle_ollama()

    def on_key(self, event):
        if event.key == "up" and self.input.has_focus:
            if self._history_index > 0:
                self._history_index -= 1
                self.input.value = self._history[self._history_index]
                event.prevent_default()
                event.stop()
        elif event.key == "down" and self.input.has_focus:
            if self._history_index < len(self._history):
                self._history_index += 1
                if self._history_index < len(self._history):
                    self.input.value = self._history[self._history_index]
                else:
                    self.input.value = ""
                event.prevent_default()
                event.stop()

    async def _send_ollama(self, msg: str):
        if self._is_loading:
            return
        self._is_loading = True
        self._stop_flag = False
        if self.stop_btn:
            self.stop_btn.disabled = False
        if self.model_select:
            self.model_select.disabled = True
        self.output_area.text += "\n🤖 Ollama: "
        self._scroll_to_bottom()

        import urllib.request
        if self.model_select and self.model_select.value:
            self._ollama_model = self.model_select.value
        payload = json.dumps({
            "model": self._ollama_model,
            "messages": self._conversation + [{"role": "user", "content": msg}],
            "stream": True,
        }).encode()
        req = urllib.request.Request(
            self._ollama_url.rstrip("/") + "/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        full = ""

        def run():
            nonlocal full
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    for line in resp:
                        if self._stop_flag:
                            break
                        s = line.decode("utf-8").strip()
                        if not s:
                            continue
                        try:
                            chunk = json.loads(s)
                            piece = chunk.get("message", {}).get("content", "")
                            if piece:
                                full += piece
                                self.call_after_refresh(
                                    self._append_text, piece
                                )
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                self.call_after_refresh(
                    self._append_text, f"\n[错误] {e}\n"
                )

        try:
            await asyncio.to_thread(run)
            if self._stop_flag:
                self.output_area.text += "\n[已停止生成]\n"
            else:
                self.output_area.text += "\n"
                self._conversation.append({"role": "user", "content": msg})
                self._conversation.append({"role": "assistant", "content": full})
        finally:
            self._is_loading = False
            self._stop_flag = False
            if self.stop_btn:
                self.stop_btn.disabled = True
            if self.model_select:
                self.model_select.disabled = False
            self._scroll_to_bottom()

    def _append_text(self, piece: str):
        self.output_area.text += piece
        self._scroll_to_bottom()

    def _insert_code(self):
        text = self.output_area.text
        blocks = re.findall(r"```(\w*)\n(.*?)```", text, re.DOTALL)
        editor = self.app_ref.get_current_text_area()
        if not editor:
            return
        if blocks:
            code = blocks[-1][1].strip()
            if code:
                row, col = editor.cursor_location
                lines = editor.text.splitlines()
                indent = ""
                if row < len(lines):
                    line = lines[row]
                    indent = line[: len(line) - len(line.lstrip())]
                indented = "\n".join(
                    indent + l if l.strip() else "" for l in code.splitlines()
                )
                editor.replace(indented, (row, col), (row, col))
                self.app_ref.notify("已插入代码", severity="information")
                return
        editor.replace(text, editor.cursor_location, editor.cursor_location)

    def clear(self):
        self.output_area.text = self.WELCOME
        self._conversation = []


class FileBrowserPanel(Vertical):
    """文件浏览器（修复：用 query_one 而非 self.browser_tree 访问）。"""
    DEFAULT_CSS = """
    FileBrowserPanel { height: auto; max-height: 40; background: $surface;
                       border: tall $primary; display: none; padding: 0 1;
                       margin: 0; overflow-y: auto; }
    #browser-layout { height: auto; min-height: 20; max-height: 30;
                      overflow-x: auto; overflow-y: auto; }
    #browser-tree { width: 30; border-right: tall $primary; padding: 0 1;
                    overflow-y: auto; height: auto; }
    #browser-input-area { width: 1fr; padding: 0 1; height: auto; }
    #browser-input { width: 1fr; margin: 1 0; }
    #browser-buttons { height: auto; padding: 0 1; align: center middle;
                       margin-top: 1; }
    .browser-btn { margin: 0 1; width: auto; min-width: 12; height: 3;
                   padding: 0 2; content-align: center middle; }
    """

    def __init__(self, parent_app, mode="open", callback=None):
        super().__init__()
        self.parent_app = parent_app
        self.mode = mode
        self.callback = callback
        self.current_path = Path.cwd()
        self.input: Optional[Input] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="browser-layout"):
            yield DirectoryTree(self.current_path, id="browser-tree")
        with Vertical(id="browser-input-area"):
            yield Label("文件名:" if self.mode == "open" else "保存为:")
            self.input = Input(placeholder="输入文件名...", id="browser-input")
            yield self.input
            yield Static("提示: 点击文件自动填入", id="browser-hint")
        with Horizontal(id="browser-buttons"):
            yield Button("确认", id="browser-confirm",
                         variant="primary", classes="browser-btn")
            yield Button("取消", id="browser-cancel", classes="browser-btn")

    def _tree(self) -> DirectoryTree:
        return self.query_one("#browser-tree", DirectoryTree)

    def on_directory_tree_file_selected(self, event):
        if event.path.is_file():
            self.input.value = event.path.name

    def on_button_pressed(self, event):
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
        tree = self._tree()
        s = self.input.value.strip()
        if self.mode == "open":
            if not s:
                self.parent_app.notify("请输入文件名", severity="warning")
                return
            path = Path(s)
            if not path.is_absolute():
                path = tree.path / path
            if path.is_file():
                self.callback(str(path))
                self.display = False
            else:
                self.parent_app.notify("文件不存在", severity="error")
        else:
            if s:
                dest = tree.path / s
                self.callback(str(dest))
                self.display = False
            else:
                self.parent_app.notify("请输入文件名", severity="warning")

    def _cancel(self):
        self.display = False
        self.parent_app.focus_editor()

    def show(self, start_path=None):
        tree = self._tree()
        if start_path:
            p = Path(start_path)
            tree.path = p.parent if p.is_file() else p
        else:
            tree.path = Path.cwd()
        self.display = True
        self.input.focus()