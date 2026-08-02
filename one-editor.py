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
import os, re, json, shutil, asyncio, subprocess, difflib, traceback
from pathlib import Path
from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, TextArea, Button, Static, Input, Label, DirectoryTree, OptionList, Select, Checkbox
from textual.widgets.option_list import Option
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual import events
from textual.geometry import Offset
from lsp import LspClient, LANG_SERVERS, path_to_uri, uri_to_path
from companion import CompanionServer

VERSION = "1.0.1-alpha.1"
CONFIG_DIR = Path.home() / ".one-editor"
CONFIG_FILE = CONFIG_DIR / "state.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
PLUGIN_CONFIG_FILE = CONFIG_DIR / "plugins.json"
CLIPBOARD = {"path": None, "is_cut": False}
DEFAULT_SETTINGS = {
    "theme": "textual-dark", "indent_width": 4, "show_line_numbers": True,
    "autosave_interval": 0, "tab_width": 4, "font_size": 12,
    "language": "zh", "wrap": True, "indent_type": "spaces",
    "default_dir": str(Path.home()), "ollama_url": "http://localhost:11434",
    "ollama_model": "llama2",
}
TR = {"zh": {"menu_file": "文件", "menu_edit": "编辑", "menu_tools": "工具", "menu_plugins": "插件", "menu_run": "▶ 运行", "menu_build": "🔧 构建", "menu_debug": "🐞 调试", "settings": "设置", "about": "关于", "save": "保存", "save_as": "另存为", "close": "关闭", "quit": "退出", "new": "新建", "open": "打开...", "find": "查找", "replace": "替换", "goto": "转到行", "format": "格式化文档", "theme": "主题", "indent": "缩进空格数", "autosave": "自动保存间隔(秒)", "line_numbers": "显示行号", "language_label": "语言 / Language", "language_zh": "中文", "language_en": "English", "about_title": "One Editor", "about_version": f"版本 {VERSION}", "about_desc": "基于 Textual 的轻量级编辑器", "about_features": "支持 LSP, 多标签, 文件树", "about_close": "关闭", "save_settings": "保存设置", "cancel": "取消", "yes": "是", "no": "否", "confirm": "确认", "search_placeholder": "查找...", "replace_placeholder": "替换为...", "find_btn": "查找", "replace_btn": "替换", "replace_all_btn": "全部替换", "cancel_find": "取消", "case_sensitive": "Aa", "regex": ".*", "no_match": "未找到匹配", "match_count": "找到 {count} 个匹配", "file_exists": "文件已存在", "file_not_exists": "文件不存在", "save_success": "已保存: {name}", "save_fail": "保存失败: {error}", "file_tree": "文件树", "new_file": "新建文件", "new_folder": "新建文件夹", "rename": "重命名", "move_to": "移动至...", "copy": "复制", "paste": "粘贴", "delete": "删除", "open_dir": "打开文件夹", "input_prompt": "输入路径...", "input_enter": "按 Enter 确认，按 Esc 取消", "unsaved": "文件已修改，是否保存？", "unsaved_quit": "以下文件未保存：\n{files}\n\n是否保存？", "save_btn": "保存", "nosave_btn": "不保存", "cancel_btn": "取消", "overwrite": "{dest} 已存在，覆盖？", "goto_line_prompt": "输入行号 (1-{total})", "invalid_line": "请输入有效的行号", "line_out_of_range": "只有 {total} 行", "move_up": "上移行", "move_down": "下移行", "first_line": "已经是第一行", "last_line": "已经是最后一行", "need_two_lines": "至少两行才能移动", "run_success": "运行完成，退出码 {code}", "build_success": "构建完成", "debug_start": "调试启动", "debug_stop": "调试结束", "no_file": "请先保存文件", "unsupported_lang": "不支持运行该类型文件", "no_project": "未找到项目文件", "no_build_system": "没有支持的构建系统", "debug_py_only": "调试功能仅支持 Python 当前", "lsp_started": "LSP 已启动 ({lang})", "lsp_failed": "LSP 启动失败 ({lang})，请检查服务器安装", "lsp_stopped": "LSP 已停止", "lsp_not_running": "LSP 未运行", "no_symbols": "没有符号", "no_hover": "无悬停信息", "no_diagnostics": "没有诊断信息", "format_success": "文档已格式化", "format_fail": "格式化失败", "rename_success": "重命名成功", "rename_fail": "重命名失败", "rename_prompt": "输入新名称:", "code_action": "快速修复", "goto_def_fail": "未找到定义", "completion_trigger": "触发补全", "tree_show": "文件树已显示", "tree_hide": "文件树已隐藏", "plugin_enable": "✅ 已启用", "plugin_disable": "❌ 已禁用", "plugin_save": "插件配置已保存", "plugin_competitive": "竞品 Companion", "plugin_external": "外部工具", "plugin_install": "未安装", "plugin_features": "功能", "plugin_actions": "操作", "plugin_toggle": "启用/禁用", "plugin_desc": "Competitive Companion 集成", "toggle": "切换", "status_lsp": "LSP: {status}", "status_lsp_connected": "已连接", "status_lsp_disconnected": "未连接", "status_modified": "●", "status_col": "列", "status_line": "行", "undo": "撤销", "redo": "重做", "cut": "剪切", "copy": "复制", "paste": "粘贴", "select_all": "全选", "close_tab": "关闭标签", "terminal": "终端", "clear_terminal": "清空终端", "command_palette": "命令面板", "compare_files": "文件对比", "diff_title": "文件差异", "diff_close": "关闭", "no_diff_tabs": "至少需要两个打开的标签进行对比", "no_undo": "没有可撤销的操作", "no_redo": "没有可重做的操作", "default_dir": "默认项目目录", "indent_type_label": "缩进类型", "spaces": "空格", "tabs": "制表符", "font_size_label": "字体大小", "wrap_label": "自动换行", "language_server": "语言服务器", "compile_cmd": "编译命令", "run_cmd": "运行命令", "ollama": "Ollama 对话", "ollama_toggle": "Ollama 面板", "ollama_input": "输入提问...", "ollama_clear": "清空对话", "ollama_insert": "插入代码", "ollama_panel": "Ollama", "welcome_title": "欢迎使用 One-Editor", "welcome_subtitle": "轻量级编辑器，内置 LSP 支持", "welcome_recent": "最近打开的文件", "welcome_new_file": "新建文件", "welcome_open_folder": "打开文件夹", "welcome_tips": "提示：按 Ctrl+Shift+P 打开命令面板", "welcome_placeholder": "欢迎使用 One-Editor，键入以关闭这条信息，当前语言: {lang}，LSP: {status}", "screenshot_saved": "截图已保存到 {path}", "theme_changed": "主题已切换为 {theme}", "rainbow_brackets": "彩虹括号", "error_lens": "错误透镜",},
    "en": {"menu_file": "File", "menu_edit": "Edit", "menu_tools": "Tools", "menu_plugins": "Plugins", "menu_run": "▶ Run", "menu_build": "🔧 Build", "menu_debug": "🐞 Debug", "settings": "Settings", "about": "About", "save": "Save", "save_as": "Save As...", "close": "Close", "quit": "Quit", "new": "New", "open": "Open...", "find": "Find", "replace": "Replace", "goto": "Go to Line", "format": "Format Document", "theme": "Theme", "indent": "Indent Width", "autosave": "Autosave Interval (s)", "line_numbers": "Show Line Numbers", "language_label": "Language / 语言", "language_zh": "中文", "language_en": "English", "about_title": "One Editor", "about_version": f"Version {VERSION}", "about_desc": "Lightweight editor based on Textual", "about_features": "Supports LSP, tabs, file tree", "about_close": "Close", "save_settings": "Save Settings", "cancel": "Cancel", "yes": "Yes", "no": "No", "confirm": "Confirm", "search_placeholder": "Find...", "replace_placeholder": "Replace with...", "find_btn": "Find", "replace_btn": "Replace", "replace_all_btn": "Replace All", "cancel_find": "Cancel", "case_sensitive": "Aa", "regex": ".*", "no_match": "No matches found", "match_count": "Found {count} matches", "file_exists": "File already exists", "file_not_exists": "File does not exist", "save_success": "Saved: {name}", "save_fail": "Save failed: {error}", "file_tree": "File Tree", "new_file": "New File", "new_folder": "New Folder", "rename": "Rename", "move_to": "Move to...", "copy": "Copy", "paste": "Paste", "delete": "Delete", "open_dir": "Open Folder", "input_prompt": "Enter path...", "input_enter": "Press Enter to confirm, Esc to cancel", "unsaved": "File modified, save?", "unsaved_quit": "Unsaved files:\n{files}\n\nSave?", "save_btn": "Save", "nosave_btn": "Don't Save", "cancel_btn": "Cancel", "overwrite": "{dest} exists, overwrite?", "goto_line_prompt": "Enter line number (1-{total})", "invalid_line": "Enter a valid line number", "line_out_of_range": "Only {total} lines", "move_up": "Move line up", "move_down": "Move line down", "first_line": "Already at first line", "last_line": "Already at last line", "need_two_lines": "At least two lines to move", "run_success": "Run finished, exit code {code}", "build_success": "Build finished", "debug_start": "Debug started", "debug_stop": "Debug stopped", "no_file": "Please save file first", "unsupported_lang": "Unsupported file type for run", "no_project": "No project found", "no_build_system": "No build system supported", "debug_py_only": "Debug currently only supports Python", "lsp_started": "LSP started ({lang})", "lsp_failed": "LSP failed ({lang}), check server installation", "lsp_stopped": "LSP stopped", "lsp_not_running": "LSP is not running", "no_symbols": "No symbols", "no_hover": "No hover info", "no_diagnostics": "No diagnostics", "format_success": "Document formatted", "format_fail": "Format failed", "rename_success": "Rename succeeded", "rename_fail": "Rename failed", "rename_prompt": "Enter new name:", "code_action": "Code Action", "goto_def_fail": "Definition not found", "completion_trigger": "Trigger completion", "tree_show": "File tree shown", "tree_hide": "File tree hidden", "plugin_enable": "✅ Enabled", "plugin_disable": "❌ Disabled", "plugin_save": "Plugin config saved", "plugin_competitive": "Competitive Companion", "plugin_external": "External Tool", "plugin_install": "Not installed", "plugin_features": "Features", "plugin_actions": "Actions", "plugin_toggle": "Toggle", "plugin_desc": "Competitive Companion integration", "toggle": "Toggle", "status_lsp": "LSP: {status}", "status_lsp_connected": "Connected", "status_lsp_disconnected": "Disconnected", "status_modified": "●", "status_col": "Col", "status_line": "Line", "undo": "Undo", "redo": "Redo", "cut": "Cut", "copy": "Copy", "paste": "Paste", "select_all": "Select All", "close_tab": "Close Tab", "terminal": "Terminal", "clear_terminal": "Clear Terminal", "command_palette": "Command Palette", "compare_files": "Compare Files", "diff_title": "File Differences", "diff_close": "Close", "no_diff_tabs": "Need at least two open tabs to compare", "no_undo": "No undo operations", "no_redo": "No redo operations", "default_dir": "Default Project Directory", "indent_type_label": "Indent Type", "spaces": "Spaces", "tabs": "Tabs", "font_size_label": "Font Size", "wrap_label": "Wrap Lines", "language_server": "Language Server", "compile_cmd": "Compile Command", "run_cmd": "Run Command", "ollama": "Ollama Chat", "ollama_toggle": "Ollama Panel", "ollama_input": "Ask something...", "ollama_clear": "Clear Chat", "ollama_insert": "Insert Code", "ollama_panel": "Ollama", "welcome_title": "Welcome to One-Editor", "welcome_subtitle": "Lightweight editor with built-in LSP", "welcome_recent": "Recent Files", "welcome_new_file": "New File", "welcome_open_folder": "Open Folder", "welcome_tips": "Tip: Press Ctrl+Shift+P for command palette", "welcome_placeholder": "Welcome to One-Editor, type to dismiss this message, Language: {lang}, LSP: {status}", "screenshot_saved": "Screenshot saved to {path}", "theme_changed": "Theme switched to {theme}", "rainbow_brackets": "Rainbow Brackets", "error_lens": "Error Lens",}
}
LANGUAGE_MAP = {".py":"python", ".js":"javascript", ".ts":"typescript", ".jsx":"javascript", ".tsx":"typescript", ".html":"html", ".htm":"html", ".css":"css", ".scss":"scss", ".json":"json", ".md":"markdown", ".sh":"bash", ".bash":"bash", ".sql":"sql", ".java":"java", ".c":"c", ".cpp":"cpp", ".h":"c", ".hpp":"cpp", ".cs":"csharp", ".go":"go", ".rs":"rust", ".rb":"ruby", ".php":"php", ".swift":"swift", ".kt":"kotlin", ".xml":"xml", ".yaml":"yaml", ".yml":"yaml", ".toml":"toml", ".ini":"ini", ".txt":None}
def detect_language(path): return LANGUAGE_MAP.get(Path(path).suffix.lower())
def safe_read(path, encoding='utf-8'):
    try:
        with open(path,"r",encoding=encoding) as f:
            return f.read()
    except:
        return None
class FileOperation:
    def __init__(self,op_type,path,old_data=None,new_data=None,old_path=None):
        self.op_type=op_type; self.path=path; self.old_data=old_data; self.new_data=new_data; self.old_path=old_path
class InputScreen(Screen):
    def __init__(self,prompt,callback): super().__init__(); self.prompt=prompt; self.callback=callback
    def compose(self):
        try:
            yield Label(self.prompt)
            self.input=Input(placeholder=self.app._tr("input_prompt"))
            yield self.input
            yield Static(self.app._tr("input_enter"))
        except Exception as e:
            yield Label(f"错误: {e}")
            yield Button("关闭", id="input-error-close")
    def on_input_submitted(self,event):
        v = event.value.strip()
        if v:
            try:
                self.callback(v)
            except Exception as e:
                self.app.notify(f"输入处理失败: {e}", severity="error")
                traceback.print_exc()
        self.dismiss()
    def on_key(self,event):
        if event.key=="escape":
            self.dismiss()
    def on_button_pressed(self,event):
        if event.button.id=="input-error-close":
            self.dismiss()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()
class SaveConfirmScreen(ModalScreen):
    CSS = """SaveConfirmScreen{align:center middle;background:rgba(0,0,0,0.6);}#save-box{background:$surface;padding:2 3;border:round $border;width:40;height:auto;}#save-box>Label{text-align:center;margin:1 0;}#save-box>Horizontal{height:3;margin:1 0;}#save-box>Button{margin:0 1;width:1fr;}"""
    def __init__(self,message,callback): super().__init__(); self.message=message; self.callback=callback
    def compose(self):
        with Container(id="save-box"):
            yield Label(self.message)
            with Horizontal():
                yield Button(self.app._tr("save_btn"),id="save",variant="primary")
                yield Button(self.app._tr("nosave_btn"),id="nosave",variant="warning")
                yield Button(self.app._tr("cancel_btn"),id="cancel")
    def on_button_pressed(self,event):
        if event.button.id in ("save","nosave","cancel"): self.callback(event.button.id); self.dismiss()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()
class ExternalChangeScreen(ModalScreen):
    CSS = """ExternalChangeScreen{background:rgba(0,0,0,0.6);align:center middle;}#container{background:$surface;padding:2 3;border:round $border;width:50;height:auto;}#container>Button{margin:1 1;width:1fr;}"""
    def __init__(self,filepath,callback): super().__init__(); self.filepath=filepath; self.callback=callback
    def compose(self):
        with Container(id="container"):
            yield Label(f"文件 {Path(self.filepath).name} 已被外部修改",id="msg")
            yield Label("是否重新加载？")
            with Horizontal():
                yield Button(self.app._tr("yes"),variant="primary",id="reload")
                yield Button(self.app._tr("no"),id="ignore")
    def on_button_pressed(self,event):
        if event.button.id=="reload": self.callback(True)
        else: self.callback(False)
        self.dismiss()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()
class OptionListMenu(ModalScreen):
    CSS = """OptionListMenu{background:rgba(0,0,0,0.6);align:center middle;}#menu-container{background:$surface;padding:1 2;border:round $border;width:auto;min-width:30;max-width:60;height:auto;max-height:20;overflow-y:auto;}.menu-item{width:1fr;padding:0 1;height:1;background:$surface;border:none;text-align:left;}.menu-item:hover{background:$panel;}.menu-item .shortcut{color:$text-muted;margin-left:2;}"""
    def __init__(self, title, items, callback):
        super().__init__()
        self.title = title
        self.items = items
        self.callback = callback
        self._dismissed = False
    def compose(self):
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
                btn = Button(label, id=f"menu_{i}", classes="menu-item")
                if shortcut:
                    btn.label = f"{label}  ({shortcut})"
                yield btn
            yield Button(self.app._tr("cancel"), id="menu_cancel", classes="menu-item")
    def on_button_pressed(self, event):
        if self._dismissed:
            return
        self._dismissed = True
        self.dismiss()
        if event.button.id == "menu_cancel":
            return
        try:
            idx = int(event.button.id.split("_")[1])
            if idx < len(self.items):
                item = self.items[idx]
                if isinstance(item, dict):
                    action = item.get("action")
                    if action is None:
                        action = item.get("label")
                else:
                    action = item
                if action is None:
                    action = str(item)
                try:
                    self.callback(action)
                except Exception as e:
                    self.app.notify(f"操作失败: {e}", severity="error", timeout=5)
                    traceback.print_exc()
        except Exception as e:
            self.app.notify(f"菜单执行错误: {e}", severity="error", timeout=5)
            traceback.print_exc()
    def on_key(self, event):
        if event.key == "escape" and not self._dismissed:
            self._dismissed = True
            self.dismiss()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()
class OutputPanel(Vertical):
    DEFAULT_CSS = """OutputPanel{height:10;background:$surface;border:round $border;display:none;padding:0 1;margin:0;}OutputPanel>TextArea{border:none;background:$surface;height:1fr;}"""
    def compose(self):
        self.output_area=TextArea(read_only=True,language=None,id="output-area")
        yield self.output_area
    def clear(self):
        self.output_area.text=""

class TerminalPanel(Vertical):
    DEFAULT_CSS = """TerminalPanel{height:12;background:$surface;border:round $border;display:none;padding:0 1;margin:0;}TerminalPanel>TextArea{border:none;background:$surface;height:1fr;scrollbar-size:1 1;}TerminalPanel>Horizontal{height:3;margin:0 0 1 0;}TerminalPanel>Horizontal>Input{width:1fr;margin:0 1;}TerminalPanel>Horizontal>Button{margin:0 1;height:1;}"""
    def __init__(self,app):
        super().__init__()
        self.app_ref=app
        self.process=None
        self.current_dir=Path.cwd()
        self._history=[]
        self._history_index=0
    def compose(self):
        self.output_area=TextArea(read_only=True,language=None,id="terminal-output")
        yield self.output_area
        with Horizontal():
            self.input=Input(placeholder="输入命令...",id="terminal-input")
            yield self.input
            yield Button("清空",id="terminal-clear",variant="default")
            yield Button("关闭",id="terminal-close",variant="default")
    def on_input_submitted(self,event):
        cmd=event.value.strip()
        if not cmd:
            return
        if not self._history or self._history[-1]!=cmd:
            self._history.append(cmd)
        self._history_index=len(self._history)
        event.input.value=""
        self.output_area.text+=f"\n$ {cmd}\n"
        self._scroll_to_bottom()
        self.app_ref.run_worker(self._run_command(cmd))
    def on_button_pressed(self,event):
        if event.button.id=="terminal-clear":
            self.clear()
        elif event.button.id=="terminal-close":
            self.app_ref.action_toggle_terminal()
    def on_key(self,event):
        if event.key=="ctrl+c" and self.process:
            try:
                self.process.terminate()
            except:
                pass
            event.prevent_default()
            event.stop()
            return
        if event.key=="up" and self.input.has_focus:
            if self._history_index>0:
                self._history_index-=1
                self.input.value=self._history[self._history_index]
                event.prevent_default()
                event.stop()
        elif event.key=="down" and self.input.has_focus:
            if self._history_index<len(self._history):
                self._history_index+=1
                if self._history_index<len(self._history):
                    self.input.value=self._history[self._history_index]
                else:
                    self.input.value=""
                event.prevent_default()
                event.stop()
    async def _run_command(self,cmd):
        try:
            if self.process:
                self.output_area.text+="\n[上一个进程仍在运行，请先按 Ctrl+C 终止]\n"
                return
            creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess,'CREATE_NO_WINDOW') else 0
            process=await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=str(self.current_dir), creationflags=creationflags)
            self.process=process
            async def read_stream(stream):
                while True:
                    line=await stream.readline()
                    if not line:
                        break
                    try:
                        self.output_area.text+=line.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            self.output_area.text+=line.decode('gbk')
                        except:
                            self.output_area.text+=line.decode('utf-8',errors='replace')
                    self._scroll_to_bottom()
            await asyncio.gather(read_stream(process.stdout), read_stream(process.stderr), return_exceptions=True)
            await process.wait()
            if process.returncode is not None:
                self.output_area.text+=f"\n[进程结束，退出码 {process.returncode}]\n"
                self._scroll_to_bottom()
            self.process=None
        except asyncio.CancelledError:
            if self.process:
                try:
                    self.process.terminate()
                    await self.process.wait()
                except:
                    pass
                self.output_area.text+="\n[进程已终止]\n"
                self._scroll_to_bottom()
                self.process=None
            raise
        except Exception as e:
            self.output_area.text+=f"\n错误: {e}\n"
            self._scroll_to_bottom()
    def clear(self):
        self.output_area.text=""
    def set_cwd(self,path):
        self.current_dir=Path(path).resolve()
    def _scroll_to_bottom(self):
        lines=len(self.output_area.text.splitlines())
        if lines>0:
            self.call_after_refresh(lambda: self.output_area.scroll_to((lines-1,0),animate=False))

class DiagnosticScreen(Screen):
    CSS = """DiagnosticScreen{background:rgba(0,0,0,0.6);align:center middle;}#diag-container{background:$surface;padding:1 2;border:round $border;width:70;height:30;overflow-y:auto;}.diag-item{margin:0 0 1 0;padding:0 1;width:1fr;border:none;text-align:left;}.diag-item:hover{background:$panel;}.diag-error{color:$error;}.diag-warning{color:$warning;}#diag-header{height:1;background:$surface;margin-bottom:1;}#diag-close{width:1fr;border:none;background:$surface;color:$text;dock:right;}#diag-close:hover{background:$error;color:$text;}"""
    def __init__(self,diagnostics,app):
        super().__init__()
        self.diagnostics=diagnostics
        self.app_ref=app
    def compose(self):
        with Container(id="diag-container"):
            with Horizontal(id="diag-header"):
                yield Label(f"诊断信息 ({len(self.diagnostics)})",id="diag-title")
                yield Button("✕",id="diag-close",variant="default")
            if not self.diagnostics:
                yield Label("没有诊断信息")
            else:
                for idx,diag in enumerate(self.diagnostics):
                    sev=diag.get("severity",1)
                    msg=diag.get("message","")
                    r=diag.get("range",{})
                    s=r.get("start",{})
                    line=s.get("line",0)
                    col=s.get("character",0)
                    cls="diag-error" if sev<=1 else "diag-warning"
                    btn=Button(f"[{'ERROR' if sev<=1 else 'WARNING'}] L{line+1}:{col+1} {msg}", id=f"diag_jump_{idx}", classes=f"diag-item {cls}", variant="default")
                    btn._jump_line=line
                    btn._jump_col=col
                    yield btn
    def on_button_pressed(self,event):
        if event.button.id=="diag-close":
            self.dismiss()
        elif event.button.id.startswith("diag_jump_"):
            line=getattr(event.button,"_jump_line",0)
            col=getattr(event.button,"_jump_col",0)
            self.dismiss()
            editor=self.app_ref.get_current_text_area()
            if editor:
                editor.cursor_location=(line,col)
                editor.focus()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()

class DiffScreen(Screen):
    CSS = """DiffScreen{background:rgba(0,0,0,0.6);align:center middle;}#diff-container{background:$surface;padding:1 2;border:round $border;width:90;height:80%;overflow-y:auto;}#diff-area{height:1fr;border:none;}#diff-close{margin-top:1;width:1fr;}"""
    def __init__(self,left_text,right_text,left_title="旧",right_title="新"):
        super().__init__()
        self.left_text=left_text or ""
        self.right_text=right_text or ""
        self.left_title=left_title
        self.right_title=right_title
    def compose(self):
        try:
            left_lines = self.left_text.splitlines() if self.left_text else [""]
            right_lines = self.right_text.splitlines() if self.right_text else [""]
            diff = difflib.unified_diff(left_lines, right_lines, fromfile=self.left_title, tofile=self.right_title, lineterm='')
            diff_text = '\n'.join(diff) or "(无差异)"
            with Container(id="diff-container"):
                yield Label(self.app._tr("diff_title"),id="diff-title")
                yield TextArea(diff_text,read_only=True,language=None,id="diff-area")
                yield Button(self.app._tr("diff_close"),id="diff-close",variant="primary")
        except Exception as e:
            yield Label(f"对比失败: {e}")
            yield Button("关闭", id="diff-error-close")
    def on_button_pressed(self,event):
        if event.button.id=="diff-close" or event.button.id=="diff-error-close":
            self.dismiss()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()

class AboutScreen(Screen):
    CSS = """AboutScreen{background:rgba(0,0,0,0.6);align:center middle;}#about-container{background:$surface;padding:2 3;border:round $border;width:45;height:auto;}#about-ascii{text-align:center;color:$primary;font-family:monospace;margin:0 0 1 0;}#about-title{text-style:bold;text-align:center;margin:1 0;color:$primary;}#about-version{text-align:center;color:$text;margin:1 0 0 0;}#about-latest{text-align:center;color:$success;margin:0 0 1 0;}#about-desc,#about-features{text-align:center;margin:1 0;}#about-divider{text-align:center;color:$text-muted;margin:1 0;}#about-close{margin-top:2;width:1fr;}"""
    def compose(self):
        try:
            with Container(id="about-container"):
                yield Label(r"""
  ___                  _____    _ _ _            
 / _ \ _ __   ___     | ____|__| (_) |_ ___  _ __ 
| | | | '_ \ / _ \    |  _| / _` | | __/ _ \| '__|
| |_| | | | |  __/    | |__| (_| | | || (_) | |   
 \___/|_| |_|\___|    |_____\__,_|_|\__\___/|_|   
""", id="about-ascii")
                yield Label(self.app._tr("about_title"), id="about-title")
                yield Label("══════════════════════", id="about-divider")
                yield Label(f"本地版本: {VERSION}", id="about-version")
                self.latest_version_label = Label("最新版本: 正在检查...", id="about-latest")
                yield self.latest_version_label
                yield Label(self.app._tr("about_desc"), id="about-desc")
                yield Label(self.app._tr("about_features"), id="about-features")
                yield Button(self.app._tr("about_close"), id="about-close-btn", variant="primary")
                self.app.run_worker(self._fetch_latest_version(), exclusive=True)
        except Exception as e:
            yield Label(f"关于加载失败: {e}")
            yield Button("关闭", id="about-error-close")

    async def _fetch_latest_version(self):
        import re
        try:
            import aiohttp
        except ImportError:
            self.latest_version_label.update("最新版本: 请安装 aiohttp")
            return
        url = "https://github.com/Aoan2011/One-Editor/releases"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        self.latest_version_label.update(f"最新版本: 获取失败 (HTTP {resp.status})")
                        return
                    html = await resp.text()
            pattern = r'/Aoan2011/One-Editor/releases/tag/v?([\d.]+(?:-alpha\.\d+)?(?:-beta\.\d+)?)'
            matches = re.findall(pattern, html)
            if matches:
                latest = matches[0]
                if latest != VERSION:
                    self.latest_version_label.update(f"最新版本: v{latest} 🆕")
                else:
                    self.latest_version_label.update(f"最新版本: v{latest} ✅")
            else:
                self.latest_version_label.update("最新版本: 未找到")
        except asyncio.TimeoutError:
            self.latest_version_label.update("最新版本: 请求超时")
        except aiohttp.ClientError:
            self.latest_version_label.update("最新版本: 网络错误")
        except Exception as e:
            self.latest_version_label.update("最新版本: 解析失败")
            traceback.print_exc()

    def on_button_pressed(self, event):
        if event.button.id == "about-close-btn" or event.button.id == "about-error-close":
            self.dismiss()

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()

    def on_unmount(self):
        if self.app:
            self.app.focus_editor()

class CommandPalette(OptionListMenu):
    def __init__(self,commands,callback):
        items=[{"label":desc,"action":action} for action,desc in commands.items()]
        super().__init__("命令面板",items,callback)

class AxiomEditor(TextArea):
    def on_mount(self):
        self.indent_width=4
        self.indent_type="spaces"
        self.tab_behavior="indent"
        self.multicursor=True
        self._hover_timer=None
        self._hover_pos=None
    def _highlight_brackets(self):
        try:
            row,col=self.cursor_location
            lines=self.text.splitlines()
            if row>=len(lines):
                return
            line=lines[row]
            if col==0:
                self.app.update_status_bar()
                return
            char=line[col-1]
            if char in '([{':
                stack=[]
                for i,ch in enumerate(line):
                    if ch in '([{':
                        stack.append((ch,i))
                    elif ch in ')]}':
                        if stack and ((stack[-1][0]=='(' and ch==')') or (stack[-1][0]=='[' and ch==']') or (stack[-1][0]=='{' and ch=='}')):
                            stack.pop()
                        else:
                            break
                if stack and stack[-1][1]!=col-1:
                    self.app.status_bar.update(f"🔗 匹配括号: 列 {stack[-1][1]+1}")
                else:
                    self.app.update_status_bar()
            elif char in ')]}':
                stack=[]
                for i in range(len(line)-1,-1,-1):
                    ch=line[i]
                    if ch in ')]}':
                        stack.append((ch,i))
                    elif ch in '([{':
                        if stack and ((stack[-1][0]==')' and ch=='(') or (stack[-1][0]==']' and ch=='[') or (stack[-1][0]=='}' and ch=='{')):
                            stack.pop()
                        else:
                            break
                if stack and stack[-1][1]!=col-1:
                    self.app.status_bar.update(f"🔗 匹配括号: 列 {stack[-1][1]+1}")
                else:
                    self.app.update_status_bar()
            else:
                self.app.update_status_bar()
        except:
            self.app.update_status_bar()
    def apply_diagnostics(self,diagnostics):
        try:
            row,_=self.cursor_location
            errors=[]
            warnings=[]
            for diag in diagnostics:
                r=diag.get('range',{})
                s=r.get('start',{})
                line=s.get('line',-1)
                if line==row:
                    msg=diag.get('message','')
                    sev=diag.get('severity',1)
                    if sev<=1:
                        errors.append(msg)
                    else:
                        warnings.append(msg)
            if errors:
                self.app.status_bar.update(f"❌ 错误: {'; '.join(errors)}")
            elif warnings:
                self.app.status_bar.update(f"⚠️ 警告: {'; '.join(warnings)}")
            else:
                self.app.update_status_bar()
        except:
            self.app.update_status_bar()
    async def _on_key(self,event):
        if event.key == "ctrl+s":
            self.app.action_save_file()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+o":
            self.app.action_open_file()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+n":
            self.app.action_new_file()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+w":
            self.app.action_close_file()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+q":
            self.app.action_quit()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+f":
            self.app.action_show_find()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+h":
            self.app.action_show_replace()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+g":
            self.app.action_goto_line()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+b":
            self.app.action_toggle_file_tree()
            event.prevent_default()
            event.stop()
            return
        if event.key == "f5":
            self.app.action_run()
            event.prevent_default()
            event.stop()
            return
        if event.key == "f6":
            self.app.action_build()
            event.prevent_default()
            event.stop()
            return
        if event.key == "f7":
            self.app.action_debug()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+`":
            self.app.action_toggle_terminal()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+shift+p":
            self.app.action_command_palette()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+d":
            self.app.action_compare_files()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+k":
            self.app.action_screenshot()
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+a":
            self.select_all()
            event.prevent_default()
            event.stop()
            return
        if event.key in ("tab","enter","up","down"):
            try:
                menu=self.app.query_one("#completion-menu")
                if menu.visible:
                    if event.key=="up":
                        menu.move_up()
                    elif event.key=="down":
                        menu.move_down()
                    elif event.key=="tab":
                        item=menu.selected_item()
                        if item:
                            self.app._insert_completion(item)
                        menu.hide()
                    elif event.key=="enter":
                        menu.hide()
                    event.prevent_default()
                    event.stop()
                    return
            except:
                pass
        bracket_pairs={"(":")","[":"]","{":"}","\"":"\"","'":"'"}
        char=event.character
        if char and char in bracket_pairs:
            start,end=self.selection
            if start!=end:
                sel=self.text[start:end]
                new=char+sel+bracket_pairs[char]
                self.replace(new,start,end)
                new_cursor=start+len(char)+len(sel)
                self.selection=(new_cursor,new_cursor)
            else:
                row,col=self.cursor_location
                lines=self.text.split("\n")
                line=lines[row]
                lines[row]=line[:col]+char+bracket_pairs[char]+line[col:]
                self.text="\n".join(lines)
                self.cursor_location=(row,col+1)
            self._highlight_brackets()
            event.prevent_default()
            event.stop()
            return
        if not self.read_only and event.key=="enter":
            event.stop()
            event.prevent_default()
            row,col=self.cursor_location
            lines=self.text.split("\n")
            current_line=lines[row] if row<len(lines) else ""
            indent=0
            for ch in current_line:
                if ch==" ":
                    indent+=1
                elif ch=="\t":
                    indent+=self.indent_width
                else:
                    break
            if current_line[:col].rstrip() and current_line[:col].rstrip()[-1] in (":","{","[","("):
                indent+=self.indent_width
            start,end=self.selection
            self._replace_via_keyboard("\n"+" "*indent,start,end)
            return
        await super()._on_key(event)
    def on_mouse_move(self,event):
        if not self.region.contains(event.x,event.y):
            return
        try:
            row,col=self.get_cursor_at(event.x,event.y)
        except:
            row,col=self.cursor_location
        if (row,col)!=self._hover_pos:
            self._hover_pos=(row,col)
            if self._hover_timer:
                self._hover_timer.stop()
                self._hover_timer=None
            if self.text.strip():
                self._hover_timer=self.set_timer(3.0,self._show_hover)
    def _show_hover(self):
        if not self._hover_pos:
            return
        app=self.app
        if not app.lsp.running:
            return
        row,col=self._hover_pos
        app.lsp.did_change(self.text)
        app.run_worker(self._fetch_hover_auto(row,col), exclusive=True, group="hover-auto")
    async def _fetch_hover_auto(self,row,col):
        result=await self.app.lsp.hover(row,col)
        if result:
            self.app.notify(f"📖 {result}",severity="information",timeout=5)

class CompletionMenu(OptionList):
    DEFAULT_CSS = """CompletionMenu{layer:overlay;display:none;height:auto;max-height:10;width:auto;min-width:30;max-width:60;border:round $border;background:$surface;padding:0;}"""
    can_focus=False
    def __init__(self):
        super().__init__(id="completion-menu")
        self.items=[]
    def show(self,items,offset):
        self.items=items
        self.clear_options()
        for item in items:
            self.add_option(Option(item["label"]))
        self.styles.offset=Offset(offset[0],offset[1])
        self.display=True
        self.highlighted=0
    def hide(self):
        self.display=False
        self.items=[]
    @property
    def visible(self):
        return self.display and len(self.items)>0
    def move_up(self):
        if self.highlighted is not None and self.highlighted>0:
            self.highlighted-=1
    def move_down(self):
        if self.highlighted is not None and self.highlighted<self.option_count-1:
            self.highlighted+=1
    def selected_item(self):
        idx=self.highlighted
        if idx is not None and idx<len(self.items):
            return self.items[idx]
        return None

class FindReplaceBar(Horizontal):
    def __init__(self,parent_app,find_callback,replace_callback,goto_callback):
        super().__init__()
        self.parent_app=parent_app
        self.find_callback=find_callback
        self.replace_callback=replace_callback
        self.goto_callback=goto_callback
        self.mode="find"
        self.case_sensitive=False
        self.use_regex=False
    def compose(self):
        # 查找输入
        self.find_input=Input(placeholder=self.app._tr("search_placeholder"),id="find-input")
        yield self.find_input
        # 替换输入
        self.replace_input=Input(placeholder=self.app._tr("replace_placeholder"),id="replace-input")
        self.replace_input.display=False
        yield self.replace_input
        # 转到行输入
        self.goto_input=Input(placeholder="输入行号...",id="goto-input")
        self.goto_input.display=False
        yield self.goto_input
        # 按钮
        self.case_btn=Button(self.app._tr("case_sensitive"),id="case-btn",classes="find-btn")
        yield self.case_btn
        self.regex_btn=Button(self.app._tr("regex"),id="regex-btn",classes="find-btn")
        yield self.regex_btn
        self.find_btn=Button(self.app._tr("find_btn"),id="find-btn",classes="find-btn",variant="primary")
        yield self.find_btn
        self.replace_btn=Button(self.app._tr("replace_btn"),id="replace-btn",classes="find-btn",variant="warning")
        self.replace_btn.display=False
        yield self.replace_btn
        self.replace_all_btn=Button(self.app._tr("replace_all_btn"),id="replace-all-btn",classes="find-btn",variant="warning")
        self.replace_all_btn.display=False
        yield self.replace_all_btn
        self.goto_btn=Button("转到",id="goto-btn",classes="find-btn",variant="primary")
        self.goto_btn.display=False
        yield self.goto_btn
        self.cancel_btn=Button(self.app._tr("cancel_find"),id="cancel-btn",classes="find-btn")
        yield self.cancel_btn
    def _cycle_history(self,input_widget,history_list,index_attr,direction):
        history=getattr(self.parent_app,history_list)
        if not history:
            return
        current=getattr(self.parent_app,index_attr)
        new=current+direction
        if new<0:
            new=0
        elif new>=len(history):
            new=len(history)-1
        setattr(self.parent_app,index_attr,new)
        input_widget.value=history[new]
    def on_key(self,event):
        if event.key=="escape":
            self.parent_app._hide_find_replace()
            return
        if self.find_input.display and self.find_input.has_focus:
            if event.key=="up":
                self._cycle_history(self.find_input,'_search_history','_search_index',-1)
                event.prevent_default()
                event.stop()
            elif event.key=="down":
                self._cycle_history(self.find_input,'_search_history','_search_index',1)
                event.prevent_default()
                event.stop()
        elif self.replace_input.display and self.replace_input.has_focus:
            if event.key=="up":
                self._cycle_history(self.replace_input,'_replace_history','_replace_index',-1)
                event.prevent_default()
                event.stop()
            elif event.key=="down":
                self._cycle_history(self.replace_input,'_replace_history','_replace_index',1)
                event.prevent_default()
                event.stop()
        elif self.goto_input.display and self.goto_input.has_focus:
            if event.key=="enter":
                self._do_goto()
                event.prevent_default()
                event.stop()
    def on_input_submitted(self,event):
        if event.input.id == "goto-input":
            self._do_goto()
            return
        if self.mode=="find":
            q=self.find_input.value
            if q:
                self.find_callback(q,self.case_sensitive,self.use_regex)
        elif self.mode=="replace":
            f=self.find_input.value
            r=self.replace_input.value
            if f:
                self.replace_callback(f,r,False,self.case_sensitive,self.use_regex)
    def on_button_pressed(self,event):
        btn_id=event.button.id
        if btn_id=="case-btn":
            self.case_sensitive=not self.case_sensitive
            event.button.label=self.app._tr("case_sensitive") if self.case_sensitive else "aa"
        elif btn_id=="regex-btn":
            self.use_regex=not self.use_regex
            event.button.label=self.app._tr("regex") if self.use_regex else "re"
        elif btn_id=="find-btn":
            q=self.find_input.value
            if q:
                self.find_callback(q,self.case_sensitive,self.use_regex)
        elif btn_id=="replace-btn":
            f=self.find_input.value
            r=self.replace_input.value
            if f:
                self.replace_callback(f,r,False,self.case_sensitive,self.use_regex)
        elif btn_id=="replace-all-btn":
            f=self.find_input.value
            r=self.replace_input.value
            if f:
                self.replace_callback(f,r,True,self.case_sensitive,self.use_regex)
        elif btn_id=="goto-btn":
            self._do_goto()
        elif btn_id=="cancel-btn":
            self.parent_app._hide_find_replace()
    def set_mode(self,mode):
        self.mode=mode
        # 隐藏所有输入和按钮
        self.find_input.display=False
        self.replace_input.display=False
        self.goto_input.display=False
        self.find_btn.display=False
        self.replace_btn.display=False
        self.replace_all_btn.display=False
        self.goto_btn.display=False
        # 显示对应模式
        if mode=="find":
            self.find_input.display=True
            self.find_btn.display=True
            self.find_input.focus()
        elif mode=="replace":
            self.find_input.display=True
            self.replace_input.display=True
            self.find_btn.display=True
            self.replace_btn.display=True
            self.replace_all_btn.display=True
            self.replace_input.focus()
        elif mode=="goto":
            self.goto_input.display=True
            self.goto_btn.display=True
            self.goto_input.focus()
        # 取消按钮总是显示
        self.cancel_btn.display=True
    def show_goto(self):
        self.set_mode("goto")
        self.display=True
    def _do_goto(self):
        try:
            n=int(self.goto_input.value.strip())
        except ValueError:
            self.parent_app.notify("请输入有效的行号", severity="error")
            return
        ta=self.parent_app.get_current_text_area()
        if not ta:
            return
        total=len(ta.text.splitlines())
        if n<1 or n>total:
            self.parent_app.notify(f"只有 {total} 行", severity="warning")
            return
        ta.cursor_location=(n-1,0)
        ta.scroll_to((n-1,0),animate=False)
        self.parent_app.update_status_bar()
        self.parent_app._hide_find_replace()

class EditorContextMenu(OptionListMenu):
    def __init__(self,text_area):
        self.text_area=text_area
        items=[
            {"label":"撤销","action":"undo"},
            {"label":"重做","action":"redo"},
            {"label":"剪切","action":"cut"},
            {"label":"复制","action":"copy"},
            {"label":"粘贴","action":"paste"},
            {"label":"全选","action":"select_all","shortcut":"Ctrl+A"},
            {"label":"保存","action":"save"},
            {"label":"另存为...","action":"save_as"},
            {"label":"关闭标签","action":"close"},
            {"label":"格式化文档","action":"format"},
            {"label":"代码大纲","action":"symbols"},
            {"label":"悬停提示","action":"hover"},
            {"label":"快速修复","action":"code_action"},
            {"label":"重命名符号","action":"rename_symbol"},
        ]
        def cb(action):
            app=self.app
            try:
                if action=="undo":
                    self.text_area.undo()
                elif action=="redo":
                    self.text_area.redo()
                elif action=="cut":
                    self.text_area.cut()
                elif action=="copy":
                    self.text_area.copy()
                elif action=="paste":
                    clipboard=self.app.clipboard
                    if clipboard:
                        self.text_area.insert_text(clipboard)
                elif action=="select_all":
                    self.text_area.select_all()
                elif action=="save":
                    app.action_save_file()
                elif action=="save_as":
                    app.action_save_as()
                elif action=="close":
                    app.action_close_file()
                elif action=="format":
                    app.action_format_document()
                elif action=="symbols":
                    app.action_show_symbols()
                elif action=="hover":
                    app.action_show_hover()
                elif action=="code_action":
                    app.action_code_action()
                elif action=="rename_symbol":
                    app.action_rename_symbol()
            except Exception as e:
                app.notify(f"操作失败: {e}", severity="error", timeout=5)
        super().__init__("编辑器",items,cb)

class FileTreeContextMenu(OptionListMenu):
    def __init__(self,path,is_file):
        self.path=path
        self.is_file=is_file
        items=[
            {"label":"新建文件","action":"new_file"},
            {"label":"新建文件夹","action":"new_folder"},
        ]
        if is_file:
            items.append({"label":"打开","action":"open"})
        else:
            items.append({"label":"打开文件夹","action":"open_dir"})
        items.extend([
            {"label":"重命名","action":"rename"},
            {"label":"移动至...","action":"move_to"},
            {"label":"复制","action":"copy"},
            {"label":"粘贴","action":"paste"},
            {"label":"删除","action":"delete"},
        ])
        def cb(action):
            app=self.app
            try:
                app._context_path=self.path
                app._filetree_menu_callback(action)
            except Exception as e:
                app.notify(f"文件树操作失败: {e}", severity="error", timeout=5)
        super().__init__("文件树",items,cb)

class TopMenuBar(Horizontal):
    def compose(self):
        yield Button(self.app._tr("menu_file"),id="menu_file",classes="menu-btn")
        yield Button(self.app._tr("menu_edit"),id="menu_edit",classes="menu-btn")
        yield Button(self.app._tr("menu_tools"),id="menu_tools",classes="menu-btn")
        yield Button(self.app._tr("menu_plugins"),id="menu_plugins",classes="menu-btn")
        yield Button(self.app._tr("menu_run"),id="btn_run",classes="menu-btn")
        yield Button(self.app._tr("menu_build"),id="btn_build",classes="menu-btn")
        yield Button(self.app._tr("menu_debug"),id="btn_debug",classes="menu-btn")
        self.diag_label=Button("",id="diag-counter",classes="menu-btn",variant="default")
        yield self.diag_label
    def update_diagnostics(self,error_count,warning_count):
        total=error_count+warning_count
        self.diag_label.label="✓ 无错误" if total==0 else f"⚠ 错误:{error_count} 警告:{warning_count}"

class SymbolListScreen(OptionListMenu):
    def __init__(self,symbols,app):
        self.symbols=symbols
        self.app_ref=app
        items=[{"label":f"{sym['name']}  (行 {sym['line']+1})","action":sym} for sym in symbols]
        def cb(sym):
            app_ref._jump_to_symbol(sym["line"],sym["col"])
        super().__init__("符号列表",items,cb)

class FileBrowserPanel(Vertical):
    DEFAULT_CSS = """FileBrowserPanel{height:20;background:$surface;border:round $border;display:none;padding:0 1;}#browser-layout{height:1fr;}#browser-tree{width:30;border-right:round $border;padding:0 1;}#browser-input-area{width:1fr;padding:0 1;}#browser-input{width:1fr;margin:1 0;}#browser-buttons{height:3;padding:1 0;}.browser-btn{margin:0 1;}"""
    def __init__(self,parent_app,mode="open",callback=None):
        super().__init__()
        self.parent_app=parent_app
        self.mode=mode
        self.callback=callback
        self.current_path=Path.cwd()
    def compose(self):
        with Horizontal(id="browser-layout"):
            self.browser_tree=DirectoryTree(self.current_path,id="browser-tree")
            yield self.browser_tree
        with Vertical(id="browser-input-area"):
            yield Label("文件名:" if self.mode=="open" else "保存为:")
            self.input=Input(placeholder="输入文件名...",id="browser-input")
            yield self.input
            yield Static("提示: 点击文件自动填入",id="browser-hint")
        with Horizontal(id="browser-buttons"):
            yield Button(self.mode.capitalize(),id="browser-confirm",variant="primary",classes="browser-btn")
            yield Button(self.app._tr("cancel"),id="browser-cancel",classes="browser-btn")
    def on_directory_tree_file_selected(self,event):
        if event.path.is_file():
            self.input.value=event.path.name
    def on_button_pressed(self,event):
        if event.button.id=="browser-confirm":
            self._confirm()
        elif event.button.id=="browser-cancel":
            self._cancel()
    def on_key(self,event):
        if event.key=="escape":
            self._cancel()
        elif event.key=="enter":
            self._confirm()
    def _confirm(self):
        if self.mode=="open":
            s=self.input.value.strip()
            if not s:
                self.parent_app.notify("请输入文件名",severity="warning")
                return
            path=Path(s)
            if not path.is_absolute():
                path=self.browser_tree.path/path
            if path.is_file():
                self.callback(str(path))
                self.display=False
            else:
                self.parent_app.notify("文件不存在",severity="error")
        else:
            name=self.input.value.strip()
            if name:
                dest=self.browser_tree.path/name
                self.callback(str(dest))
                self.display=False
            else:
                self.parent_app.notify("请输入文件名",severity="warning")
    def _cancel(self):
        self.display=False
        self.parent_app.focus_editor()
    def show(self,start_path=None):
        if start_path:
            p=Path(start_path)
            self.browser_tree.path=p.parent if p.is_file() else p
        else:
            self.browser_tree.path=Path.cwd()
        self.display=True
        self.input.focus()

# ---------- 设置页面 ----------
class SettingsScreen(Screen):
    CSS = """SettingsScreen{background:rgba(0,0,0,0.6);align:center middle;}#settings-container{background:$surface;padding:2 3;border:round $border;width:50;height:auto;max-height:80%;overflow-y:auto;}#settings-title{text-style:bold;color:$primary;margin:0 0 1 0;}.settings-group{margin:1 0;}.settings-group Label{margin:1 0 0 0;}.settings-group > Horizontal{width:1fr;}.settings-group > Horizontal > * {width:1fr;margin:0 1;}"""
    def __init__(self,app):
        super().__init__()
        self.app_ref=app
        self._settings=app._settings
    def compose(self):
        try:
            with Container(id="settings-container"):
                yield Label(self.app._tr("settings"),id="settings-title")
                with Container(classes="settings-group"):
                    yield Label(self.app._tr("theme")+":")
                    theme = str(self._settings.get("theme", "textual-dark"))
                    themes = ["textual-dark", "textual-light", "dracula", "nord", "ansi-dark", "ansi-light"]
                    if theme not in themes:
                        theme = themes[0]
                    self.theme_select = Select([(t, t) for t in themes], value=theme, allow_blank=False)
                    yield self.theme_select
                    yield Label(self.app._tr("language_label")+":")
                    lang = str(self._settings.get("language", "zh"))
                    langs = ["zh", "en"]
                    if lang not in langs:
                        lang = langs[0]
                    self.lang_select = Select([(self.app._tr("language_zh"), "zh"), (self.app._tr("language_en"), "en")], value=lang, allow_blank=False)
                    yield self.lang_select
                with Container(classes="settings-group"):
                    with Horizontal():
                        with Vertical():
                            yield Label(self.app._tr("indent")+":")
                            self.indent_input=Input(value=str(self._settings.get("indent_width",4)),type="integer")
                            yield self.indent_input
                        with Vertical():
                            yield Label(self.app._tr("indent_type_label")+":")
                            itype = str(self._settings.get("indent_type", "spaces"))
                            itypes = ["spaces", "tabs"]
                            if itype not in itypes:
                                itype = itypes[0]
                            self.indent_type = Select([(self.app._tr("spaces"), "spaces"), (self.app._tr("tabs"), "tabs")], value=itype, allow_blank=False)
                            yield self.indent_type
                with Container(classes="settings-group"):
                    with Horizontal():
                        with Vertical():
                            yield Label(self.app._tr("font_size_label")+":")
                            self.font_input=Input(value=str(self._settings.get("font_size",12)),type="integer")
                            yield self.font_input
                        with Vertical():
                            yield Label(self.app._tr("autosave")+":")
                            self.autosave_input=Input(value=str(self._settings.get("autosave_interval",0)),type="integer")
                            yield self.autosave_input
                with Container(classes="settings-group"):
                    self.line_numbers_check=Checkbox(self.app._tr("line_numbers"),value=self._settings.get("show_line_numbers",True))
                    yield self.line_numbers_check
                    self.wrap_check=Checkbox(self.app._tr("wrap_label"),value=self._settings.get("wrap",True))
                    yield self.wrap_check
                with Container(classes="settings-group"):
                    yield Label(self.app._tr("default_dir")+":")
                    self.dir_input=Input(value=self._settings.get("default_dir",str(Path.home())),id="dir-input")
                    yield self.dir_input
                with Horizontal():
                    yield Button(self.app._tr("save_settings"),variant="primary",id="save-settings")
                    yield Button(self.app._tr("cancel"),id="cancel-settings")
        except Exception as e:
            yield Label(f"设置加载失败: {e}")
            yield Button("关闭", id="settings-error-close")
            traceback.print_exc()
    def on_button_pressed(self,event):
        if event.button.id == "settings-error-close":
            self.dismiss()
            return
        if event.button.id=="save-settings":
            try:
                if self.theme_select.value:
                    self._settings["theme"]=self.theme_select.value
                    self.app_ref.theme=self.theme_select.value
                try:
                    indent=int(self.indent_input.value)
                except:
                    indent=0
                if indent>0:
                    self._settings["indent_width"]=indent
                    self.app_ref._indent_width=indent
                    for d in self.app_ref._tab_data.values():
                        d["textarea"].indent_width=indent
                try:
                    interval=int(self.autosave_input.value)
                    self._settings["autosave_interval"]=interval
                    self.app_ref._autosave_interval=interval
                except:
                    pass
                show=self.line_numbers_check.value
                self._settings["show_line_numbers"]=show
                self.app_ref._show_line_numbers=show
                for d in self.app_ref._tab_data.values():
                    d["textarea"].show_line_numbers=show
                self._settings["default_dir"]=self.dir_input.value
                self._settings["indent_type"]=self.indent_type.value
                self._settings["font_size"]=int(self.font_input.value) if self.font_input.value else 12
                self._settings["wrap"]=self.wrap_check.value
                for d in self.app_ref._tab_data.values():
                    d["textarea"].wrap=self._settings["wrap"]
                if self.lang_select.value:
                    self._settings["language"]=self.lang_select.value
                    self.app_ref._language=self.lang_select.value
                self.app_ref._save_settings()
                self.dismiss()
                self.app_ref.notify(self.app._tr("save_settings")+" "+self.app._tr("save_success").format(name=""),severity="information")
            except Exception as e:
                self.app_ref.notify(f"保存设置失败: {e}",severity="error")
                traceback.print_exc()
        else:
            self.dismiss()
    def on_key(self,event):
        if event.key=="escape":
            self.dismiss()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()

# ---------- 插件页面 ----------
class PluginsScreen(Screen):
    CSS = """PluginsScreen{background:rgba(0,0,0,0.6);align:center middle;}#plugins-container{background:$surface;padding:2 3;border:round $border;width:70;height:auto;max-height:80%;overflow-y:auto;overflow-x:auto;}.plugin-header{height:2;background:$panel;text-style:bold;padding:0 1;}.plugin-row{height:3;padding:0 1;margin:0 0 1 0;background:$surface;border:round $border;}.plugin-row:hover{background:$panel;}.plugin-name{width:12;}.plugin-server{width:20;}.plugin-status{width:10;}.plugin-actions{width:1fr;}.toggle-btn{width:10;border:none;background:$primary;color:$surface;}.toggle-btn.off{background:$surface;color:$text;border:round $border;}.settings-btn{width:8;border:none;background:$secondary;color:$surface;}.settings-btn:hover{background:$primary;}#plugins-close{dock:right;border:none;background:$surface;color:$text;}#plugins-close:hover{background:$error;color:$text;}"""
    def __init__(self,app):
        super().__init__()
        self.app_ref=app
        self.plugin_config=self._load_config()
    def _load_config(self):
        default={}
        for lang in LANG_SERVERS.keys():
            default[lang]={"enabled":True,"features":{"completion":True,"definition":True,"hover":True,"diagnostics":True,"rename":True,"code_action":True,"formatting":True},"compile_cmd":"","run_cmd":""}
        default["competitive-companion"]={"enabled":False,"features":{"problem_parsing":False,"test_runner":False},"description":self.app._tr("plugin_desc")}
        if PLUGIN_CONFIG_FILE.exists():
            try:
                cfg=json.load(open(PLUGIN_CONFIG_FILE,"r",encoding="utf-8"))
                for lang in default:
                    if lang in cfg:
                        default[lang].update(cfg[lang])
            except:
                pass
        return default
    def _save_config(self):
        try:
            CONFIG_DIR.mkdir(parents=True,exist_ok=True)
            json.dump(self.plugin_config,open(PLUGIN_CONFIG_FILE,"w",encoding="utf-8"),indent=2)
        except:
            pass
    def compose(self):
        import shutil
        with Container(id="plugins-container"):
            yield Horizontal(Label(self.app._tr("menu_plugins"),id="plugins-title"),Button("✕",id="plugins-close"),classes="plugin-header")
            yield Horizontal(Label("名称",classes="plugin-name"),Label("服务器/状态",classes="plugin-server"),Label("状态",classes="plugin-status"),Label("操作",classes="plugin-actions"),classes="plugin-header")
            for name,config in self.plugin_config.items():
                if name=="competitive-companion":
                    status=self.app._tr("plugin_enable") if config.get("enabled",True) else self.app._tr("plugin_disable")
                    with Container(classes="plugin-row"):
                        yield Horizontal(Label(self.app._tr("plugin_competitive"),classes="plugin-name"),Label(self.app._tr("plugin_external"),classes="plugin-server"),Label(status,classes="plugin-status"),Button(self.app._tr("plugin_toggle"),id=f"toggle_{name}",classes="toggle-btn"))
                else:
                    server=LANG_SERVERS.get(name,["未安装"])
                    installed=shutil.which(server[0]) is not None if server else False
                    status=self.app._tr("plugin_enable") if config.get("enabled",True) else self.app._tr("plugin_disable")
                    with Container(classes="plugin-row"):
                        yield Horizontal(Label(name,classes="plugin-name"),Label(server[0] if installed else self.app._tr("plugin_install"),classes="plugin-server"),Label(status,classes="plugin-status"),Button(self.app._tr("plugin_toggle"),id=f"toggle_{name}",classes="toggle-btn"),Button("设置",id=f"settings_{name}",classes="settings-btn"))
            yield Button(self.app._tr("plugin_save"),variant="primary",id="save-plugins")
            yield Button(self.app._tr("cancel"),id="cancel-plugins")
    def on_button_pressed(self,event):
        if event.button.id in ("plugins-close","cancel-plugins"):
            self.dismiss()
        elif event.button.id.startswith("toggle_"):
            name=event.button.id.split("_")[1]
            self.plugin_config[name]["enabled"]=not self.plugin_config[name]["enabled"]
            self._save_config()
            if name=="competitive-companion":
                if self.plugin_config[name]["enabled"]:
                    self.app_ref._start_companion()
                else:
                    self.app_ref._stop_companion()
            self.dismiss()
            self.app_ref.push_screen(PluginsScreen(self.app_ref))
        elif event.button.id.startswith("settings_"):
            name=event.button.id.split("_")[1]
            self.app_ref.push_screen(LanguageSettingsScreen(name,self.plugin_config[name],self))
        elif event.button.id=="save-plugins":
            self._save_config()
            self.dismiss()
            self.app_ref.notify(self.app._tr("plugin_save"),severity="information")
    def on_key(self,event):
        if event.key=="escape":
            self.dismiss()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()

class LanguageSettingsScreen(Screen):
    CSS = """LanguageSettingsScreen{background:rgba(0,0,0,0.6);align:center middle;}#lang-settings-container{background:$surface;padding:2 3;border:round $border;width:60;height:auto;max-height:80%;overflow-y:auto;}#lang-settings-container>Label{margin:1 0;}#lang-settings-container>Input{margin:0 0 1 0;}"""
    def __init__(self,lang,config,parent_screen):
        super().__init__()
        self.lang=lang
        self.config=config
        self.parent_screen=parent_screen
    def compose(self):
        with Container(id="lang-settings-container"):
            yield Label(f"{self.lang} 设置",classes="title")
            yield Label(self.app._tr("compile_cmd")+":")
            self.compile_input=Input(value=self.config.get("compile_cmd",""),id="compile-cmd")
            yield self.compile_input
            yield Label(self.app._tr("run_cmd")+":")
            self.run_input=Input(value=self.config.get("run_cmd",""),id="run-cmd")
            yield self.run_input
            yield Label(" ")
            yield Button("保存",variant="primary",id="save-lang-settings")
            yield Button(self.app._tr("cancel"),id="cancel-lang-settings")
    def on_button_pressed(self,event):
        if event.button.id=="save-lang-settings":
            self.config["compile_cmd"]=self.compile_input.value
            self.config["run_cmd"]=self.run_input.value
            self.parent_screen._save_config()
            self.dismiss()
            self.app.notify(f"{self.lang} 设置已保存",severity="information")
        elif event.button.id=="cancel-lang-settings":
            self.dismiss()
    def on_key(self,event):
        if event.key=="escape":
            self.dismiss()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()

class OllamaPanel(Vertical):
    DEFAULT_CSS = """OllamaPanel{height:14;background:$surface;border:round $border;display:none;padding:0 1;margin:0;}OllamaPanel>TextArea{border:none;background:$surface;height:1fr;scrollbar-size:1 1;}OllamaPanel>Horizontal{height:3;margin:0 0 1 0;}OllamaPanel>Horizontal>Input{width:1fr;margin:0 1;}OllamaPanel>Horizontal>Button{margin:0 1;height:1;}"""
    def __init__(self,app):
        super().__init__()
        self.app_ref=app
        self._history=[]
        self._history_index=0
        self._conversation=[]
        self._ollama_url="http://localhost:11434"
        self._ollama_model="llama2"
        self._is_loading=False
    def on_mount(self):
        self._ollama_url=self.app_ref._settings.get("ollama_url","http://localhost:11434")
        self._ollama_model=self.app_ref._settings.get("ollama_model","llama2")
        self.output_area.text="💬 Ollama 对话面板\n输入问题并按 Enter 开始对话"
    def compose(self):
        self.output_area=TextArea(read_only=True,language=None,id="ollama-output")
        yield self.output_area
        with Horizontal():
            self.input=Input(placeholder=self.app._tr("ollama_input"),id="ollama-input")
            yield self.input
            yield Button(self.app._tr("ollama_insert"),id="ollama-insert",variant="primary")
            yield Button(self.app._tr("ollama_clear"),id="ollama-clear",variant="default")
            yield Button(self.app._tr("close"),id="ollama-close",variant="default")
    def on_input_submitted(self,event):
        msg=event.value.strip()
        if not msg or self._is_loading:
            return
        event.input.value=""
        self._history.append(msg)
        self._history_index=len(self._history)
        if self.output_area.text.startswith("💬"):
            self.output_area.text=""
        self.output_area.text+=f"\n🧑 你: {msg}\n"
        self._scroll_to_bottom()
        self.app_ref.run_worker(self._send_ollama(msg))
    def on_button_pressed(self,event):
        if event.button.id=="ollama-insert":
            self._insert_code()
        elif event.button.id=="ollama-clear":
            self.clear()
        elif event.button.id=="ollama-close":
            self.app_ref.action_toggle_ollama()
    def on_key(self,event):
        if event.key=="up" and self.input.has_focus:
            if self._history_index>0:
                self._history_index-=1
                self.input.value=self._history[self._history_index]
                event.prevent_default()
                event.stop()
        elif event.key=="down" and self.input.has_focus:
            if self._history_index<len(self._history):
                self._history_index+=1
                if self._history_index<len(self._history):
                    self.input.value=self._history[self._history_index]
                else:
                    self.input.value=""
                event.prevent_default()
                event.stop()
        elif event.key=="enter" and not self.input.has_focus:
            self.input.focus()
    async def _send_ollama(self,msg):
        if self._is_loading:
            return
        self._is_loading=True
        self.output_area.text+="\n🤖 Ollama: "
        self._scroll_to_bottom()
        try:
            import aiohttp
            payload={"model":self._ollama_model,"messages":self._conversation+[{"role":"user","content":msg}],"stream":True}
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self._ollama_url}/api/chat",json=payload) as resp:
                    if resp.status!=200:
                        self.output_area.text+=f"\n[错误] HTTP {resp.status}，请确认 Ollama 服务已启动\n"
                        return
                    full=""
                    async for line in resp.content:
                        if line:
                            try:
                                data=json.loads(line)
                                if "message" in data and "content" in data["message"]:
                                    chunk=data["message"]["content"]
                                    full+=chunk
                                    self.output_area.text+=chunk
                                    self._scroll_to_bottom()
                                if data.get("done",False):
                                    break
                            except:
                                pass
                    self.output_area.text+="\n"
                    self._conversation.append({"role":"user","content":msg})
                    self._conversation.append({"role":"assistant","content":full})
                    self._scroll_to_bottom()
        except ImportError:
            self.output_area.text+="\n[错误] 请安装 aiohttp: pip install aiohttp\n"
        except Exception as e:
            self.output_area.text+=f"\n[错误] {e}\n"
        finally:
            self._is_loading=False
            self._scroll_to_bottom()
    def _insert_code(self):
        text=self.output_area.text
        blocks=re.findall(r'```(\w*)\n(.*?)```',text,re.DOTALL)
        if blocks:
            code=blocks[-1][1].strip()
            if code:
                editor=self.app_ref.get_current_text_area()
                if editor:
                    row,col=editor.cursor_location
                    indent_type=self.app_ref._settings.get("indent_type","spaces")
                    if indent_type=="spaces":
                        lines=code.splitlines()
                        indented="\n".join("    "+line if line.strip() else line for line in lines)
                    else:
                        indented=code
                    editor.replace(indented,(row,col),(row,col))
                    self.app_ref.notify("已插入代码",severity="information")
                    return
        editor=self.app_ref.get_current_text_area()
        if editor:
            editor.replace(text,editor.cursor_location,editor.cursor_location)
    def clear(self):
        self.output_area.text="💬 Ollama 对话面板\n输入问题并按 Enter 开始对话"
        self._conversation=[]
    def _scroll_to_bottom(self):
        lines=len(self.output_area.text.splitlines())
        if lines>0:
            self.call_after_refresh(lambda: self.output_area.scroll_to((lines-1,0),animate=False))

class WelcomeScreen(Screen):
    CSS = """WelcomeScreen{background:$surface;}#welcome-container{align:center middle;width:100%;height:100%;background:$surface;}#welcome-box{width:60;height:auto;background:$surface;border:round $border;padding:2 4;}#welcome-title{text-style:bold;font-size:20;text-align:center;color:$primary;}#welcome-subtitle{text-align:center;color:$text-muted;margin:1 0;}#welcome-actions{margin:2 0;layout:vertical;align:center middle;}.welcome-btn{width:30;margin:0 1;padding:0 2;text-align:center;}#welcome-tips{text-align:center;color:$text-muted;margin-top:2;}"""
    def compose(self):
        with Container(id="welcome-container"):
            with Container(id="welcome-box"):
                yield Label("🚀 "+self.app._tr("welcome_title"),id="welcome-title")
                yield Label(self.app._tr("welcome_subtitle"),id="welcome-subtitle")
                with Vertical(id="welcome-actions"):
                    yield Button(self.app._tr("new"),id="welcome-new",classes="welcome-btn",variant="primary")
                    yield Button(self.app._tr("open"),id="welcome-open",classes="welcome-btn",variant="default")
                yield Label(self.app._tr("welcome_tips"),id="welcome-tips")
    def on_button_pressed(self,event):
        if event.button.id=="welcome-new":
            self.app.action_new_file()
            self.dismiss()
        elif event.button.id=="welcome-open":
            self.app.action_open_file()
            self.dismiss()
    def on_key(self,event):
        if event.key=="escape":
            self.dismiss()
    def on_unmount(self):
        if self.app:
            self.app.focus_editor()

class OneEditor(App):
    def __init__(self):
        super().__init__()
        self._language="zh"
        self._settings=self._load_settings()
    # Tokyo Night 主题配色（默认）
    CSS = """
    $background: #1a1b26;
    $surface: #1e212b;
    $panel: #2a2c3a;
    $text: #c0caf5;
    $text-muted: #565f89;
    $primary: #7aa2f7;
    $secondary: #9d7cd8;
    $accent: #f38ba8;
    $success: #9ece6a;
    $error: #f7768e;
    $warning: #e0af68;
    $border: #3b4261;

    #main-layout{layout:horizontal;}
    #sidebar{width:30;background:$surface;border-right:round $border;padding:0 1;display:block;}
    #editor-area{width:1fr;layers:default overlay;}
    #menu-bar{height:1;background:$surface;padding:0 1;layout:horizontal;}
    .menu-btn{padding:0 1;background:$surface;color:$text;border:none;height:1;}
    .menu-btn:hover{background:$panel;}
    #diag-counter{dock:right;padding:0 1;background:$surface;color:$text;height:1;border:none;}
    #diag-counter:hover{background:$panel;}
    #tab-bar-container{height:3;background:$surface;layout:horizontal;border-bottom:round $border;}
    .tab-scroll-btn{height:2;width:3;background:$surface;border:none;color:$text;}
    .tab-scroll-btn:hover{background:$panel;}
    #tab-scroll{height:2;background:$surface;overflow-x:auto;scrollbar-size:1 1;padding:0 1;}
    #tab-bar{width:auto;height:2;background:$surface;}
    .tab-button-container{height:2;display:block;padding:0 1;}
    .tab-button{background:transparent;color:$text-muted;border:none;border-bottom:round transparent;height:2;padding:0 1;margin:0;}
    .tab-button:hover{background:$panel;color:$text;}
    .tab-button.active{color:$text;border-bottom:round $primary;}
    .tab-close{background:transparent;color:$text-muted;border:none;height:2;min-width:2;padding:0 1;display:block;}
    .tab-close:hover{background:$error;color:$text;}
    #content-container{height:1fr;}
    TextArea{border:none;background:$surface;}
    #status-bar{background:$surface;color:$text;padding:0 1;height:1;layout:horizontal;border-top:round $border;}
    #status-left{width:12;padding:0 1;height:1;text-style:bold;}
    #status-center{width:1fr;padding:0 1;height:1;}
    #status-right{width:auto;padding:0 1;height:1;dock:right;}
    #find-replace-bar{height:3;background:$surface;padding:0 1;display:none;}
    #find-replace-bar>Input{width:1fr;margin:0 1;border:none;border-bottom:round $border;}
    #find-replace-bar>Button{margin:0 1;height:1;}
    .find-btn{padding:0 1;background:transparent;color:$text;border:round $border;height:1;}
    .find-btn:hover{border:round $primary;}
    #file-browser{height:20;background:$surface;border:round $border;display:none;padding:0 1;}
    #browser-layout{height:1fr;}
    #browser-tree{width:30;border-right:round $border;padding:0 1;}
    #browser-input-area{width:1fr;padding:0 1;}
    #browser-input{width:1fr;margin:1 0;border:none;border-bottom:round $border;}
    #browser-buttons{height:3;padding:1 0;}
    .browser-btn{margin:0 1;}
    #completion-menu{layer:overlay;display:none;height:auto;max-height:10;width:auto;min-width:30;max-width:60;border:round $border;background:$surface;padding:0;}
    .tree-resize-handle{width:3;background:$surface;border-right:round $border;}
    #tree-container{height:1fr;width:30;background:$surface;}
    .tree-node.drag-target{background:$accent 50%;}
    DirectoryTree > .tree--node{height:1;padding:0 1;}
    DirectoryTree > .tree--node.highlight{background:$panel;}
    DirectoryTree > .tree--node .tree--file{color:$text;}
    DirectoryTree > .tree--node .tree--directory{color:$primary;}
    Input{border:none;border-bottom:round $border;background:transparent;color:$text;}
    Select{background:$surface;color:$text;border:round $border;}
    Checkbox{color:$primary;}
    Button{border:round $border;background:transparent;color:$text;}
    Button.variant-primary{background:$primary;color:$background;border:round $primary;}
    Button.variant-warning{background:$warning;color:$background;border:round $warning;}
    Button.variant-error{background:$error;color:$background;border:round $error;}
    Button:hover{background:$panel;border:round $primary;}
    .welcome-placeholder{color:$text-muted;text-align:center;padding:4;}
    """
    BINDINGS = [
        Binding("ctrl+n","new_file","新建",show=False),
        Binding("ctrl+o","open_file","打开",show=False),
        Binding("ctrl+s","save_file","保存",show=False),
        Binding("ctrl+shift+s","save_as","另存为",show=False),
        Binding("ctrl+w","close_file","关闭",show=False),
        Binding("ctrl+q","quit","退出",show=False),
        Binding("alt+up","move_line_up","上移行",show=False),
        Binding("alt+down","move_line_down","下移行",show=False),
        Binding("ctrl+f","show_find","查找",show=False),
        Binding("ctrl+h","show_replace","替换",show=False),
        Binding("f3","find_next","下一个",show=False),
        Binding("ctrl+g","goto_line","转到行",show=False),
        Binding("ctrl+b","toggle_file_tree","文件树",show=False),
        Binding("f2","rename_node","重命名",show=False),
        Binding("ctrl+shift+m","move_node","移动",show=False),
        Binding("f12","goto_definition","跳转定义",show=False),
        Binding("ctrl+shift+o","show_symbols","代码大纲",show=False),
        Binding("ctrl+shift+i","show_hover","悬停提示",show=False),
        Binding("ctrl+shift+r","rename_symbol","重命名符号",show=False),
        Binding("ctrl+shift+a","code_action","快速修复",show=False),
        Binding("ctrl+shift+f","format_document","格式化文档",show=False),
        Binding("escape","hide_find_replace","隐藏查找栏",show=False),
        Binding("ctrl+a","select_all","全选",show=False),
        Binding("f5","run","运行",show=False),
        Binding("f6","build","构建",show=False),
        Binding("f7","debug","调试",show=False),
        Binding("ctrl+z","undo_filetree","撤销文件树",show=False),
        Binding("ctrl+shift+z","redo_filetree","重做文件树",show=False),
        Binding("ctrl+`","toggle_terminal","终端",show=False),
        Binding("ctrl+l","clear_terminal","清空终端",show=False),
        Binding("ctrl+shift+p","command_palette","命令面板",show=False),
        Binding("ctrl+d","compare_files","文件对比",show=False),
        Binding("ctrl+shift+o","toggle_ollama","Ollama对话",show=False),
        Binding("ctrl+k","screenshot","截图",show=False),
    ]
    def compose(self):
        yield Header()
        yield TopMenuBar(id="menu-bar")
        with Horizontal(id="tab-bar-container"):
            yield Button("◀",id="tab-scroll-left",classes="tab-scroll-btn")
            with ScrollableContainer(id="tab-scroll"):
                self.tab_bar=Horizontal(id="tab-bar")
                yield self.tab_bar
            yield Button("▶",id="tab-scroll-right",classes="tab-scroll-btn")
        self.find_bar=FindReplaceBar(self,self._do_find,self._do_replace,self._do_goto)
        self.find_bar.id="find-replace-bar"
        yield self.find_bar
        self.file_browser=FileBrowserPanel(parent_app=self,mode="open")
        self.file_browser.id="file-browser"
        yield self.file_browser
        with Horizontal(id="main-layout"):
            with Container(id="tree-container"):
                self.file_tree=DirectoryTree(Path(".").resolve())
                self.file_tree.id="sidebar"
                yield self.file_tree
            self.resize_handle=Static(classes="tree-resize-handle")
            yield self.resize_handle
            with Vertical(id="editor-area"):
                self.content_container=Container(id="content-container")
                yield self.content_container
                self.completion_menu=CompletionMenu()
                yield self.completion_menu
                self.output_panel=OutputPanel()
                yield self.output_panel
                self.terminal_panel=TerminalPanel(self)
                yield self.terminal_panel
                self.ollama_panel=OllamaPanel(self)
                yield self.ollama_panel
        # 状态栏
        self.status_left = Static(id="status-left")
        self.status_center = Static(id="status-center")
        self.status_right = Static(id="status-right")
        with Horizontal(id="status-bar"):
            yield self.status_left
            yield self.status_center
            yield self.status_right
        yield Footer()
    def on_mount(self):
        self._tab_data={}
        self._modified={}
        self._active_tab_id=None
        self._tab_counter=0
        self._find_matches=[]
        self._find_index=-1
        self._find_query=""
        self._context_path=None
        self._drag_node=None
        self._drag_start_x=0
        self._drag_start_y=0
        self._is_dragging=False
        self._drag_target_node=None
        self._show_file_tree=True
        self._search_history=[]
        self._replace_history=[]
        self._search_index=-1
        self._replace_index=-1
        self._find_visible=False
        self._current_lang=None
        self._completion_timer=None
        self._diagnostics_cache={}
        self._current_uri=None
        self._file_mtime_cache={}
        self._tree_width=30
        self._load_tree_width()
        self._is_resizing=False
        self._file_undo_stack=[]
        self._file_redo_stack=[]
        self.lsp=LspClient()
        self.lsp.set_diagnostics_callback(self._on_diagnostics)
        self._indent_width=self._settings.get("indent_width",4)
        self._show_line_numbers=self._settings.get("show_line_numbers",True)
        self._autosave_interval=self._settings.get("autosave_interval",0)
        self.theme=self._settings.get("theme","textual-dark")
        self._language=self._settings.get("language","zh")
        self.companion=None
        self._start_companion_if_enabled()
        self._load_state()
        if not self._tab_data:
            welcome_tab_id=self.add_new_tab("欢迎","",None)
            self._tab_data[welcome_tab_id]["textarea"].text=self._get_welcome_text()
            self._tab_data[welcome_tab_id]["textarea"].read_only=True
            self._tab_data[welcome_tab_id]["is_welcome"]=True
            self.show_tab(welcome_tab_id)
        else:
            if self._active_tab_id and self._active_tab_id in self._tab_data:
                self.show_tab(self._active_tab_id)
            else:
                self.show_tab(next(iter(self._tab_data.keys())))
        self.file_tree.display=self._show_file_tree
        self.file_tree.focus()
        self._apply_tree_width()
        if self._autosave_interval>0:
            self.set_timer(self._autosave_interval,self._autosave)
        self.set_timer(2,self._check_external_changes)
        self.notify(f"欢迎使用 One-Editor {self._tr('about_version')}", severity="information", timeout=3)
    def _get_welcome_text(self):
        lang=self._current_lang or "未知"
        status=self._tr("status_lsp_connected") if self.lsp.running else self._tr("status_lsp_disconnected")
        return f"""/**\n * {self._tr('welcome_title')}\n * {self._tr('welcome_subtitle')}\n * \n * {self._tr('welcome_tips')}\n * \n * {self._tr('welcome_placeholder').format(lang=lang, status=status)}\n */\n\n// 按 Ctrl+N 新建文件\n// 按 Ctrl+O 打开文件\n// 按 Ctrl+Shift+P 打开命令面板\n"""
    def _tr(self,key,default=None):
        return TR.get(self._language,TR["zh"]).get(key,default or key)
    def _start_companion_if_enabled(self):
        cfg=self._load_plugin_config()
        if cfg.get("competitive-companion",{}).get("enabled",False):
            self._start_companion()
        else:
            self._stop_companion()
    def _start_companion(self):
        if self.companion is not None:
            return
        self.companion=CompanionServer(self._companion_callback)
        self.companion.start()
        self.notify("Companion 服务器已启动 (端口 10045)",severity="information")
    def _stop_companion(self):
        if self.companion:
            self.companion.stop()
            self.companion=None
            self.notify("Companion 服务器已停止",severity="information")
    def _companion_callback(self,data):
        name=data.get('name','problem')
        lang=data.get('language','python')
        template=data.get('code','')
        tests=data.get('tests',[])
        ext_map={'python':'.py','cpp':'.cpp','c':'.c','java':'.java','javascript':'.js','rust':'.rs','go':'.go','ruby':'.rb','php':'.php'}
        ext=ext_map.get(lang,'.txt')
        base_dir=Path(self._settings.get("default_dir",str(Path.cwd())))
        filename=base_dir/f"{name}{ext}"
        try:
            filename.write_text(template,encoding='utf-8')
            self.notify(f"已创建题目文件: {filename.name}",severity="information")
            self._open_file_by_path(filename)
            if tests:
                (base_dir/f"{name}_tests.json").write_text(json.dumps(tests,indent=2),encoding='utf-8')
        except Exception as e:
            self.notify(f"创建文件失败: {e}",severity="error")
    def _load_plugin_config(self):
        if PLUGIN_CONFIG_FILE.exists():
            try:
                return json.load(open(PLUGIN_CONFIG_FILE,"r",encoding="utf-8"))
            except:
                pass
        return {}
    def _load_settings(self):
        if CONFIG_FILE.exists():
            try:
                state=json.load(open(CONFIG_FILE,"r",encoding="utf-8"))
                settings=state.get("settings",{})
                for k,v in DEFAULT_SETTINGS.items():
                    if k not in settings:
                        settings[k]=v
                return settings
            except:
                pass
        return DEFAULT_SETTINGS.copy()
    def _save_settings(self):
        try:
            state={}
            if CONFIG_FILE.exists():
                try:
                    state=json.load(open(CONFIG_FILE,"r",encoding="utf-8"))
                except:
                    pass
            state["settings"]=self._settings
            CONFIG_DIR.mkdir(parents=True,exist_ok=True)
            json.dump(state,open(CONFIG_FILE,"w",encoding="utf-8"),indent=2)
        except:
            pass
    def _autosave(self):
        for tid,data in self._tab_data.items():
            if self._modified.get(tid,False) and data.get("filepath"):
                self.action_save_file(tid)
        if self._autosave_interval>0:
            self.set_timer(self._autosave_interval,self._autosave)
    def _load_tree_width(self):
        if CONFIG_FILE.exists():
            try:
                cfg=json.load(open(CONFIG_FILE,"r",encoding="utf-8"))
                if "tree_width" in cfg:
                    self._tree_width=cfg["tree_width"]
            except:
                pass
    def _save_tree_width(self):
        try:
            with open(CONFIG_FILE,"r+",encoding="utf-8") as f:
                cfg=json.load(f)
                cfg["tree_width"]=self._tree_width
                f.seek(0)
                json.dump(cfg,f,indent=2)
                f.truncate()
        except:
            pass
    def _apply_tree_width(self):
        self.query_one("#tree-container").styles.width=self._tree_width
    def _get_file_encoding_and_ending(self,filepath):
        encoding="UTF-8"
        line_ending="LF"
        if filepath and Path(filepath).exists():
            try:
                with open(filepath,"rb") as f:
                    raw=f.read()
                    if raw.startswith(b'\xef\xbb\xbf'):
                        encoding="UTF-8-BOM"
                    elif raw.startswith(b'\xff\xfe'):
                        encoding="UTF-16-LE"
                    elif raw.startswith(b'\xfe\xff'):
                        encoding="UTF-16-BE"
                    else:
                        try:
                            raw.decode('utf-8')
                            encoding="UTF-8"
                        except:
                            encoding="GBK"
                    line_ending="CRLF" if b'\r\n' in raw else "LF"
            except:
                pass
        return encoding,line_ending
    def on_mouse_down(self,event):
        if self.resize_handle.region.contains(event.x,event.y):
            self._is_resizing=True
            self._resize_start_x=event.x
            self._resize_start_width=self._tree_width
            event.prevent_default()
            event.stop()
            return
        if event.button==3:
            ta=self.get_current_text_area()
            if ta and ta.region.contains(event.x,event.y):
                self.push_screen(EditorContextMenu(ta))
                return
            if self.file_tree.region.contains(event.x,event.y):
                node=self.file_tree.cursor_node
                if node is None:
                    self.notify("请先选中一个节点",severity="warning")
                    return
                data=node.data
                if data is None:
                    return
                path=Path(data.path) if hasattr(data,"path") else Path(str(data))
                self._context_path=path
                is_file=path.is_file()
                self.push_screen(FileTreeContextMenu(path,is_file))
                return
    def on_mouse_move(self,event):
        if getattr(self,"_is_resizing",False):
            delta=event.x-self._resize_start_x
            new_width=max(15,min(60,self._resize_start_width+delta))
            self._tree_width=new_width
            self._apply_tree_width()
            self._save_tree_width()
            event.prevent_default()
            event.stop()
            return
    def on_mouse_up(self,event):
        if getattr(self,"_is_resizing",False):
            self._is_resizing=False
            event.prevent_default()
            event.stop()
            return
    def _do_move(self,src,dest):
        try:
            shutil.move(str(src),str(dest))
            self._refresh_file_tree()
            self.notify(f"已移动: {src.name} -> {dest.parent}",severity="information")
            abs_dest=str(dest.resolve())
            for tid,data in self._tab_data.items():
                if data.get("filepath")==str(src.resolve()):
                    data["filepath"]=abs_dest
                    data["title"]=dest.name
                    data["button"].label=dest.name
                    self.update_status_bar()
                    break
        except Exception as e:
            self.notify(f"移动失败: {e}",severity="error")
    def _check_external_changes(self):
        for tid,data in self._tab_data.items():
            fp=data.get("filepath")
            if fp and Path(fp).exists():
                mtime=Path(fp).stat().st_mtime
                cached=self._file_mtime_cache.get(fp)
                if cached is not None and cached!=mtime:
                    self._handle_external_change(fp,tid)
                self._file_mtime_cache[fp]=mtime
    def _handle_external_change(self,filepath,tab_id):
        def cb(reload):
            if reload:
                enc, _ = self._get_file_encoding_and_ending(filepath)
                content=safe_read(filepath, encoding=enc)
                if content is not None:
                    self._tab_data[tab_id]["textarea"].text=content
                    self._modified[tab_id]=False
                    self.update_status_bar()
                    self.notify("文件已重新加载",severity="information")
                else:
                    self.notify("重新加载失败",severity="error")
        if self._modified.get(tab_id,False):
            self.push_screen(ExternalChangeScreen(filepath,cb))
        else:
            cb(True)
    def _expand_to_file(self,filepath):
        if not filepath or not Path(filepath).exists():
            return
        tree=self.file_tree
        root_path=tree.path
        try:
            rel=Path(filepath).relative_to(root_path)
        except:
            return
        def find(node,parts,idx=0):
            if idx>=len(parts):
                return node
            part=parts[idx]
            for child in node.children:
                if child.data is None:
                    continue
                cd=child.data
                cp=Path(cd.path) if hasattr(cd,"path") else Path(str(cd))
                if cp.name==part:
                    if idx==len(parts)-1:
                        if child.parent:
                            child.parent.expand()
                        return child
                    else:
                        child.expand()
                        return find(child,parts,idx+1)
            return None
        root=tree.root
        if root:
            root.expand()
            find(root,rel.parts,0)
            if tree.cursor_node:
                tree.scroll_to_node(tree.cursor_node)
    def add_new_tab(self,title,content="",filepath=None):
        tid=f"tab_{self._tab_counter}"
        self._tab_counter+=1
        container=Horizontal(classes="tab-button-container")
        btn=Button(title,id=tid,classes="tab-button")
        close=Button("×",id=f"close_{tid}",classes="tab-close")
        self.tab_bar.mount(container)
        container.mount(btn,close)
        ta=AxiomEditor(content,show_line_numbers=self._show_line_numbers,language="python")
        ta.wrap=self._settings.get("wrap",True)
        ta.fold=True
        ta.indent_width=self._indent_width
        ta.id=f"textarea_{tid}"
        ta.display=False
        self.content_container.mount(ta)
        self._tab_data[tid]={"title":title,"filepath":filepath,"textarea":ta,"button":btn,"close_button":close,"container":container,"encoding":"UTF-8","line_ending":"LF","is_welcome":False}
        self._modified[tid]=False
        if filepath:
            self._file_mtime_cache[filepath]=Path(filepath).stat().st_mtime if Path(filepath).exists() else None
        if len(self._tab_data)>9:
            self.remove_tab(next(iter(self._tab_data)))
        return tid
    def remove_tab(self,tid):
        if len(self._tab_data)<=1:
            self.notify("至少保留一个标签",severity="warning")
            return
        data=self._tab_data[tid]
        data["container"].remove()
        data["textarea"].remove()
        del self._tab_data[tid]
        del self._modified[tid]
        if self._active_tab_id==tid:
            remaining=list(self._tab_data.keys())
            if remaining:
                self.show_tab(remaining[0])
            else:
                new_id=self.add_new_tab("欢迎","",None)
                self._tab_data[new_id]["textarea"].text=self._get_welcome_text()
                self._tab_data[new_id]["textarea"].read_only=True
                self._tab_data[new_id]["is_welcome"]=True
                self.show_tab(new_id)
        else:
            self._update_tab_styles()
        self.update_status_bar()
        self._save_state()
        if not self._tab_data:
            self.run_worker(self.lsp.stop(), exclusive=True, group="lsp")
    def show_tab(self,tid):
        if tid not in self._tab_data:
            return
        for d in self._tab_data.values():
            d["textarea"].display=False
        data=self._tab_data[tid]
        data["textarea"].display=True
        self._active_tab_id=tid
        self._update_tab_styles()
        self.update_status_bar()
        data["textarea"].focus()
        self._find_matches=[]
        self._find_index=-1
        self._hide_find_replace()
        self._save_state()
        container=data.get("container")
        if container and container.parent:
            container.scroll_visible()
        fp=data.get("filepath")
        if fp and Path(fp).exists():
            self.terminal_panel.set_cwd(Path(fp).parent)
            self._start_lsp_for_file(fp,data["textarea"].text)
            self._expand_to_file(fp)
        else:
            if data.get("is_welcome",False):
                data["textarea"].text=self._get_welcome_text()
    def _update_tab_styles(self):
        for tid,d in self._tab_data.items():
            if tid==self._active_tab_id:
                d["button"].add_class("active")
            else:
                d["button"].remove_class("active")
    def update_tab_modified(self,tid):
        d=self._tab_data.get(tid)
        if not d or d.get("is_welcome",False):
            return
        d["button"].label=f"● {d['title']}" if self._modified.get(tid,False) else d["title"]
    def on_button_pressed(self,event):
        btn_id=event.button.id
        if btn_id.startswith("close_"):
            tid=btn_id.replace("close_","")
            if tid in self._tab_data:
                self.action_close_file(tid)
                return
        if btn_id in self._tab_data:
            self.show_tab(btn_id)
            return
        if btn_id=="tab-scroll-left":
            tab_scroll=self.query_one("#tab-scroll")
            tab_scroll.scroll_to((tab_scroll.scroll_offset.x-50,0),animate=True)
            return
        elif btn_id=="tab-scroll-right":
            tab_scroll=self.query_one("#tab-scroll")
            tab_scroll.scroll_to((tab_scroll.scroll_offset.x+50,0),animate=True)
            return
        if btn_id=="menu_file":
            self._show_file_menu()
        elif btn_id=="menu_edit":
            self._show_edit_menu()
        elif btn_id=="menu_tools":
            self._show_tools_menu()
        elif btn_id=="menu_plugins":
            self._show_plugins_menu()
        elif btn_id=="btn_run":
            self.action_run()
        elif btn_id=="btn_build":
            self.action_build()
        elif btn_id=="btn_debug":
            self.action_debug()
        elif btn_id=="diag-counter":
            self.action_show_diagnostics()
    def _show_file_menu(self):
        items=[{"label":self._tr("new"),"action":"new"},{"label":self._tr("open"),"action":"open"},{"label":self._tr("save"),"action":"save"},{"label":self._tr("save_as"),"action":"save_as"},{"label":self._tr("close"),"action":"close"},{"label":self._tr("quit"),"action":"quit"}]
        def cb(a):
            try:
                if a=="new":
                    self.action_new_file()
                elif a=="open":
                    self.action_open_file()
                elif a=="save":
                    self.action_save_file()
                elif a=="save_as":
                    self.action_save_as()
                elif a=="close":
                    self.action_close_file()
                elif a=="quit":
                    self.action_quit()
            except Exception as e:
                self.notify(f"文件菜单操作失败: {e}", severity="error")
        self.push_screen(OptionListMenu(self._tr("menu_file"),items,cb))
    def _show_edit_menu(self):
        items=[{"label":self._tr("find"),"action":"find"},{"label":self._tr("replace"),"action":"replace"},{"label":self._tr("goto"),"action":"goto"},{"label":self._tr("format"),"action":"format"}]
        def cb(a):
            try:
                if a=="find":
                    self.action_show_find()
                elif a=="replace":
                    self.action_show_replace()
                elif a=="goto":
                    self.action_goto_line()
                elif a=="format":
                    self.action_format_document()
            except Exception as e:
                self.notify(f"编辑菜单操作失败: {e}", severity="error")
        self.push_screen(OptionListMenu(self._tr("menu_edit"),items,cb))
    def _show_tools_menu(self):
        items=[{"label":self._tr("settings"),"action":"settings"},{"label":self._tr("about"),"action":"about"},{"label":self._tr("terminal"),"action":"toggle_terminal"},{"label":self._tr("command_palette"),"action":"command_palette"},{"label":self._tr("compare_files"),"action":"compare_files"}]
        def cb(a):
            try:
                if a=="settings":
                    self._show_settings()
                elif a=="about":
                    self._show_about()
                elif a=="toggle_terminal":
                    self.action_toggle_terminal()
                elif a=="command_palette":
                    self.action_command_palette()
                elif a=="compare_files":
                    self.action_compare_files()
            except Exception as e:
                self.notify(f"工具菜单操作失败: {e}", severity="error")
        self.push_screen(OptionListMenu(self._tr("menu_tools"),items,cb))
    def _show_plugins_menu(self):
        try:
            self.push_screen(PluginsScreen(self))
        except Exception as e:
            self.notify(f"打开插件管理失败: {e}", severity="error")
            traceback.print_exc()
    def _show_settings(self):
        try:
            self.push_screen(SettingsScreen(self))
        except Exception as e:
            self.notify(f"打开设置失败: {e}", severity="error", timeout=5)
            traceback.print_exc()
    def _show_about(self):
        try:
            self.push_screen(AboutScreen())
        except Exception as e:
            self.notify(f"打开关于失败: {e}", severity="error")
            traceback.print_exc()
    def update_status_bar(self):
        tid=self.get_current_tab_id()
        if not tid or tid not in self._tab_data:
            return
        d=self._tab_data[tid]
        ta=d["textarea"]
        mod=self._modified.get(tid,False)

        # 确定模式及颜色（使用硬编码十六进制）
        mode_color_map = {
            "NORMAL": "#7aa2f7",
            "MODIFIED": "#f38ba8",
            "INSERT": "#9ece6a",
            "VISUAL": "#e0af68",
        }
        if mod:
            mode_text = "MODIFIED"
        else:
            mode_text = "NORMAL"
        mode_color = mode_color_map.get(mode_text, "#7aa2f7")

        # 左侧：模式（带颜色）
        self.status_left.styles.background = mode_color
        self.status_left.styles.color = "#1a1b26"  # $background
        self.status_left.update(f" {mode_text} ")

        # 中间：路径 + LSP
        fp=d.get("filepath","")
        if fp:
            path_str=os.path.basename(fp)
            dir_str=os.path.dirname(fp)
            if len(dir_str)>25:
                dir_str="…"+dir_str[-22:]
            middle_text=f"{dir_str}/{path_str}"
        else:
            middle_text=d["title"]

        if self.lsp.running and self._current_lang:
            lsp_status=f"󰣇 {self._current_lang}"
        else:
            lsp_status="󰅙"

        self.status_center.styles.background = "$surface"
        self.status_center.styles.color = "$text"
        # 添加三角形分隔符（通过边框）
        self.status_left.styles.border_right = ("round", mode_color)
        self.status_center.styles.border_left = ("round", mode_color)
        self.status_center.update(f" {middle_text}  {lsp_status} ")

        # 右侧：时钟 + 编码 + 行列 + 语言
        now=datetime.now().strftime("%H:%M")
        cursor=ta.selection.start
        row,col=cursor
        total=len(ta.text.splitlines())
        lang=ta.language or "plain"
        enc=d.get("encoding","UTF-8")
        right_text=f" 󰅐 {now}  󰓤 {enc}   {row+1}:{col+1}   {lang} "
        self.status_right.styles.background = "$surface"
        self.status_right.styles.color = "$text"
        self.status_right.update(right_text)

    def _load_state(self):
        if not CONFIG_FILE.exists():
            return
        try:
            state=json.load(open(CONFIG_FILE,"r",encoding="utf-8"))
        except:
            return
        for fp in state.get("open_files",[]):
            if fp is None:
                continue
            p=Path(fp)
            if p.exists() and p.is_file():
                enc, _ = self._get_file_encoding_and_ending(str(p))
                content=safe_read(str(p), encoding=enc)
                if content is not None:
                    self.add_new_tab(p.name,content,str(p.resolve()))
        if not self._tab_data:
            return
        ids=list(self._tab_data.keys())
        active=state.get("active_index",0)
        self._active_tab_id=ids[active] if active<len(ids) else ids[0]
    def _save_state(self):
        open_files=[]
        for tid,d in self._tab_data.items():
            if d.get("is_welcome",False):
                continue
            open_files.append(d.get("filepath"))
        ids=list(self._tab_data.keys())
        active=0
        if self._active_tab_id in ids:
            active=ids.index(self._active_tab_id)
        state={"open_files":open_files,"active_index":active,"show_file_tree":self.file_tree.display,"tree_width":self._tree_width}
        CONFIG_DIR.mkdir(parents=True,exist_ok=True)
        json.dump(state,open(CONFIG_FILE,"w",encoding="utf-8"),indent=2)
        self._save_settings()
    def _do_find(self,query,case_sensitive,use_regex):
        self._add_search_history(query)
        self._find_query=query
        ta=self.get_current_text_area()
        if ta.read_only:
            self.notify("只读文件不可查找",severity="warning")
            return
        matches=[]
        if use_regex:
            flags=0 if case_sensitive else re.IGNORECASE
            try:
                pattern=re.compile(query,flags)
            except:
                self.notify("无效的正则表达式",severity="error")
                return
            for row,line in enumerate(ta.text.splitlines()):
                for m in pattern.finditer(line):
                    matches.append((row,m.start(),m.end()))
        else:
            for row,line in enumerate(ta.text.splitlines()):
                pos=0
                while True:
                    idx=line.find(query,pos)
                    if idx==-1:
                        break
                    matches.append((row,idx,idx+len(query)))
                    pos=idx+1
        self._find_matches=matches
        if not matches:
            self.notify(self._tr("no_match"),severity="warning")
            self._find_index=-1
        else:
            self._find_index=0
            self._goto_match(0)
            self.notify(self._tr("match_count").format(count=len(matches)),severity="information")
        self.update_status_bar()
    def _do_replace(self,find_text,replace_text,replace_all,case_sensitive,use_regex):
        self._add_search_history(find_text)
        self._add_replace_history(replace_text)
        ta=self.get_current_text_area()
        if ta.read_only:
            self.notify("只读文件不可替换",severity="warning")
            return
        tid=self.get_current_tab_id()
        if replace_all:
            matches=self._find_all(find_text,case_sensitive,use_regex)
            if not matches:
                self.notify(self._tr("no_match"),severity="warning")
                return
            try:
                pattern=re.compile(find_text, flags=(0 if case_sensitive else re.IGNORECASE)) if use_regex else None
            except:
                self.notify("无效的正则",severity="error")
                return
            lines=ta.text.splitlines()
            new_lines=lines[:]
            cnt=0
            for i,line in enumerate(new_lines):
                if use_regex:
                    nl,cnt2=pattern.subn(replace_text,line)
                else:
                    nl=line.replace(find_text,replace_text)
                    cnt2=line.count(find_text)
                if cnt2:
                    new_lines[i]=nl
                    cnt+=cnt2
            if cnt:
                ta.text="\n".join(new_lines)
                self._modified[tid]=True
                self.update_tab_modified(tid)
                self.notify(f"替换了 {cnt} 处",severity="information")
                self._find_matches=[]
                self._find_index=-1
                self.update_status_bar()
            else:
                self.notify(self._tr("no_match"),severity="warning")
        else:
            if not self._find_matches:
                self.notify("请先执行查找",severity="warning")
                return
            if self._find_index<0 or self._find_index>=len(self._find_matches):
                return
            row,start,end=self._find_matches[self._find_index]
            lines=ta.text.splitlines()
            old=lines[row]
            lines[row]=old[:start]+replace_text+old[end:]
            ta.text="\n".join(lines)
            self._find_matches=self._find_all(find_text,case_sensitive,use_regex)
            if not self._find_matches:
                self._find_index=-1
            else:
                self._find_index=0
                self._goto_match(0)
            self._modified[tid]=True
            self.update_tab_modified(tid)
            self.update_status_bar()
    def _find_all(self,query,case_sensitive,use_regex):
        ta=self.get_current_text_area()
        lines=ta.text.splitlines()
        matches=[]
        if use_regex:
            try:
                pattern=re.compile(query, flags=(0 if case_sensitive else re.IGNORECASE))
            except:
                return []
            for row,line in enumerate(lines):
                for m in pattern.finditer(line):
                    matches.append((row,m.start(),m.end()))
        else:
            for row,line in enumerate(lines):
                pos=0
                while True:
                    idx=line.find(query,pos)
                    if idx==-1:
                        break
                    matches.append((row,idx,idx+len(query)))
                    pos=idx+1
        return matches
    def _goto_match(self,index):
        if not self._find_matches or index<0 or index>=len(self._find_matches):
            return
        ta=self.get_current_text_area()
        row,start,end=self._find_matches[index]
        ta.selection=((row,start),(row,end))
        ta.scroll_to((row,0),animate=False)
        self._find_index=index
        self.update_status_bar()
    def _show_find_replace(self,mode="find"):
        self.find_bar.display=True
        self.find_bar.set_mode(mode)
        self._find_visible=True
    def _hide_find_replace(self):
        self.find_bar.display=False
        self._find_visible=False
        self.focus_editor()
    def action_show_find(self):
        self._show_find_replace("find")
    def action_show_replace(self):
        self._show_find_replace("replace")
    def action_hide_find_replace(self):
        self._hide_find_replace()
    def action_find_next(self):
        if not self._find_matches:
            self.notify("请先执行查找",severity="warning")
            return
        self._find_index=(self._find_index+1)%len(self._find_matches)
        self._goto_match(self._find_index)
    def _add_search_history(self,q):
        if q and (not self._search_history or self._search_history[-1]!=q):
            self._search_history.append(q)
            if len(self._search_history)>20:
                self._search_history=self._search_history[-20:]
            self._search_index=len(self._search_history)-1
    def _add_replace_history(self,q):
        if q and (not self._replace_history or self._replace_history[-1]!=q):
            self._replace_history.append(q)
            if len(self._replace_history)>20:
                self._replace_history=self._replace_history[-20:]
            self._replace_index=len(self._replace_history)-1
    def action_new_file(self):
        if len(self._tab_data)>=9:
            self.notify("最多同时打开 9 个文件",severity="error")
            return
        unnamed=sum(1 for d in self._tab_data.values() if d["title"].startswith("未命名"))
        self.show_tab(self.add_new_tab(f"未命名 {unnamed+1}"))
    def action_open_file(self):
        self.file_browser.mode="open"
        self.file_browser.callback=self._open_file_callback
        current=self._tab_data.get(self._active_tab_id,{}).get("filepath")
        self.file_browser.show(start_path=current if current else None)
    def _open_file_callback(self,p):
        path=Path(p)
        if path.is_file():
            self._open_file_by_path(path)
        else:
            self.notify("不是有效文件",severity="error")
    def action_save_as(self):
        self.file_browser.mode="save"
        self.file_browser.callback=self._save_as_callback
        current=self._tab_data.get(self._active_tab_id,{}).get("filepath")
        self.file_browser.show(start_path=current if current else None)
        if current:
            self.file_browser.input.value=Path(current).name
    def _save_as_callback(self,dest_str):
        dest=Path(dest_str)
        ta=self.get_current_text_area()
        tid=self.get_current_tab_id()
        d=self._tab_data[tid]
        enc=d.get("encoding","utf-8")
        try:
            if enc=="UTF-8-BOM":
                dest.write_text(ta.text,encoding="utf-8-sig")
            else:
                dest.write_text(ta.text,encoding=enc)
            d["filepath"]=str(dest.resolve())
            d["title"]=dest.name
            d["button"].label=dest.name
            self._modified[tid]=False
            self.update_tab_modified(tid)
            enc2,le=self._get_file_encoding_and_ending(str(dest))
            d["encoding"]=enc2
            d["line_ending"]=le
            self.update_status_bar()
            self.notify(self._tr("save_success").format(name=dest.name),severity="information")
        except UnicodeEncodeError:
            dest.write_text(ta.text,encoding="utf-8")
            d["encoding"]="utf-8"
            self.notify("编码回退为 UTF-8",severity="warning")
        except Exception as e:
            self.notify(self._tr("save_fail").format(error=e),severity="error")
    def action_save_file(self,tid=None):
        if tid is None:
            tid=self.get_current_tab_id()
        if not tid:
            return
        d=self._tab_data.get(tid)
        if not d:
            return
        if d.get("is_welcome",False):
            self.notify("欢迎页不可保存",severity="warning")
            return
        ta=d["textarea"]
        fp=d.get("filepath")
        if fp:
            enc=d.get("encoding","utf-8")
            try:
                if enc=="UTF-8-BOM":
                    open(fp,"w",encoding="utf-8-sig").write(ta.text)
                else:
                    open(fp,"w",encoding=enc).write(ta.text)
                self._modified[tid]=False
                self.update_tab_modified(tid)
                enc2,le=self._get_file_encoding_and_ending(fp)
                d["encoding"]=enc2
                d["line_ending"]=le
                self.update_status_bar()
                self.notify(self._tr("save_success").format(name=Path(fp).name),severity="information")
            except UnicodeEncodeError:
                open(fp,"w",encoding="utf-8").write(ta.text)
                d["encoding"]="utf-8"
                self.notify("编码回退为 UTF-8",severity="warning")
            except Exception as e:
                self.notify(self._tr("save_fail").format(error=e),severity="error")
        else:
            self.action_save_as()
    def action_close_file(self,tid=None):
        if tid is None:
            tid=self.get_current_tab_id()
        if self._modified.get(tid,False):
            def cb(choice):
                if choice=="save":
                    self.action_save_file(tid)
                    self.remove_tab(tid)
                elif choice=="nosave":
                    self.remove_tab(tid)
            self.push_screen(SaveConfirmScreen(self._tr("unsaved"),cb))
        else:
            self.remove_tab(tid)
    def action_quit(self):
        self._save_state()
        if self.lsp.running:
            self.run_worker(self.lsp.stop(), exclusive=True, group="lsp")
        self._stop_companion()
        modified=[(tid,d["title"]) for tid,d in self._tab_data.items() if self._modified.get(tid,False)]
        if modified:
            def cb(choice):
                if choice=="save":
                    for tid,_ in modified:
                        self.action_save_file(tid)
                    self.exit()
                elif choice=="nosave":
                    self.exit()
            self.push_screen(SaveConfirmScreen(self._tr("unsaved_quit").format(files="\n".join([t for _,t in modified])),cb))
        else:
            self.exit()
    def action_move_line_up(self):
        ta=self.get_current_text_area()
        if ta.read_only:
            return
        lines=ta.text.splitlines()
        if len(lines)<2:
            self.notify(self._tr("need_two_lines"),severity="warning")
            return
        row,col=ta.selection.start
        if row<=0:
            self.notify(self._tr("first_line"),severity="warning")
            return
        lines[row],lines[row-1]=lines[row-1],lines[row]
        ta.text="\n".join(lines)
        ta.cursor_location=(row-1,min(col,len(lines[row-1])))
        self._modified[self.get_current_tab_id()]=True
        self.update_tab_modified(self.get_current_tab_id())
        self.update_status_bar()
    def action_move_line_down(self):
        ta=self.get_current_text_area()
        if ta.read_only:
            return
        lines=ta.text.splitlines()
        if len(lines)<2:
            self.notify(self._tr("need_two_lines"),severity="warning")
            return
        row,col=ta.selection.start
        if row>=len(lines)-1:
            self.notify(self._tr("last_line"),severity="warning")
            return
        lines[row],lines[row+1]=lines[row+1],lines[row]
        ta.text="\n".join(lines)
        ta.cursor_location=(row+1,min(col,len(lines[row+1])))
        self._modified[self.get_current_tab_id()]=True
        self.update_tab_modified(self.get_current_tab_id())
        self.update_status_bar()
    def action_goto_line(self):
        ta=self.get_current_text_area()
        if not ta or ta.read_only:
            self.notify("没有可用的编辑器", severity="warning")
            return
        self._show_find_replace("goto")
    def _do_goto(self, line_num=None):
        # 由 FindReplaceBar 的 _do_goto 调用
        pass
    def on_directory_tree_file_selected(self,event):
        if event.path.is_file():
            self._open_file_by_path(event.path)
    def _push_file_operation(self,op):
        self._file_undo_stack.append(op)
        self._file_redo_stack.clear()
    def _apply_file_operation(self,op,undo):
        try:
            if op.op_type=='create':
                if undo:
                    if op.path.is_file():
                        op.path.unlink()
                    else:
                        shutil.rmtree(op.path)
                else:
                    if not op.path.exists():
                        op.path.touch() if op.path.suffix else op.path.mkdir()
            elif op.op_type=='delete':
                if undo:
                    if op.old_data is not None:
                        op.path.write_text(op.old_data,encoding='utf-8')
                    else:
                        op.path.mkdir()
                else:
                    if op.path.is_file():
                        op.path.unlink()
                    else:
                        shutil.rmtree(op.path)
            elif op.op_type=='rename':
                if undo:
                    op.path.rename(op.old_path)
                else:
                    # 重做时，把当前路径（即 new path）重命名回旧路径？但重命名操作应记住新旧名称，我们暂时简化，忽略重做
                    pass
            elif op.op_type=='move':
                if undo:
                    shutil.move(str(op.path),str(op.old_path))
                else:
                    shutil.move(str(op.old_path),str(op.path))
            elif op.op_type=='copy':
                if undo:
                    if op.path.is_file():
                        op.path.unlink()
                    else:
                        shutil.rmtree(op.path)
                else:
                    # 重做复制较复杂，暂忽略
                    pass
        except Exception as e:
            self.notify(f"操作失败: {e}",severity="error")
    def action_undo_filetree(self):
        if not self._file_undo_stack:
            self.notify(self._tr("no_undo"),severity="information")
            return
        op=self._file_undo_stack.pop()
        self._file_redo_stack.append(op)
        self._apply_file_operation(op,undo=True)
        self._refresh_file_tree()
    def action_redo_filetree(self):
        if not self._file_redo_stack:
            self.notify(self._tr("no_redo"),severity="information")
            return
        op=self._file_redo_stack.pop()
        self._file_undo_stack.append(op)
        self._apply_file_operation(op,undo=False)
        self._refresh_file_tree()
    def _filetree_menu_callback(self,action):
        global CLIPBOARD
        try:
            if action is None or not hasattr(self,"_context_path"):
                return
            path=self._context_path
            if action=="new_file":
                def cb(fn):
                    np=path/fn
                    if np.exists():
                        self.notify(self._tr("file_exists"),severity="error")
                        return
                    np.touch()
                    self._push_file_operation(FileOperation('create',np))
                    self._refresh_file_tree()
                    self._open_file_by_path(np)
                self.push_screen(InputScreen("输入文件名:",cb))
            elif action=="new_folder":
                def cb(fn):
                    np=path/fn
                    if np.exists():
                        self.notify(self._tr("file_exists"),severity="error")
                        return
                    np.mkdir()
                    self._push_file_operation(FileOperation('create',np))
                    self._refresh_file_tree()
                self.push_screen(InputScreen("输入文件夹名:",cb))
            elif action=="open":
                self._open_file_by_path(path)
            elif action=="open_dir":
                self.file_tree.path=path
                self.notify(f"切换到 {path}",severity="information")
                self.refresh()
            elif action=="rename":
                def cb(newname):
                    np=path.parent/newname
                    if np.exists():
                        self.notify(self._tr("file_exists"),severity="error")
                        return
                    try:
                        old_path=path
                        path.rename(np)
                        self._push_file_operation(FileOperation('rename',np,old_data=None,new_data=None,old_path=old_path))
                        self._refresh_file_tree()
                        self.notify(f"已重命名: {old_path.name} -> {newname}",severity="information")
                        abs_new=str(np.resolve())
                        for tid,d in self._tab_data.items():
                            if d.get("filepath")==str(old_path.resolve()):
                                d["filepath"]=abs_new
                                d["title"]=np.name
                                d["button"].label=np.name
                                self.update_status_bar()
                                break
                    except Exception as e:
                        self.notify(f"重命名失败: {e}",severity="error")
                self.push_screen(InputScreen("输入新名称:",cb))
            elif action=="move_to":
                def cb(target):
                    td=Path(target.strip())
                    if not td.exists() or not td.is_dir():
                        self.notify("目标目录不存在或不是目录",severity="error")
                        return
                    if td==path.parent:
                        self.notify("已在目标目录",severity="warning")
                        return
                    dest=td/path.name
                    if dest.exists():
                        def confirm(ok):
                            if ok:
                                self._do_move(path,dest)
                        self.push_screen(SaveConfirmScreen(self._tr("overwrite").format(dest=dest),confirm))
                    else:
                        self._do_move(path,dest)
                self.push_screen(InputScreen("输入目标目录路径:",cb))
            elif action=="copy":
                CLIPBOARD["path"]=path
                CLIPBOARD["is_cut"]=False
                self.notify(f"已复制: {path.name}",severity="information")
            elif action=="paste":
                if CLIPBOARD["path"] is None:
                    self.notify("剪贴板为空",severity="warning")
                    return
                src=CLIPBOARD["path"]
                if not src.exists():
                    self.notify("源文件已不存在",severity="error")
                    CLIPBOARD["path"]=None
                    return
                dest=path/src.name
                if dest.exists():
                    def confirm(ok):
                        if ok:
                            self._do_copy(src,dest,CLIPBOARD["is_cut"])
                    self.push_screen(SaveConfirmScreen(self._tr("overwrite").format(dest=dest),confirm))
                else:
                    self._do_copy(src,dest,CLIPBOARD["is_cut"])
                if CLIPBOARD["is_cut"]:
                    CLIPBOARD["path"]=None
                    CLIPBOARD["is_cut"]=False
            elif action=="delete":
                self._delete_node(path)
        except Exception as e:
            self.notify(f"文件树操作异常: {e}",severity="error")
    def _do_copy(self,src,dest,is_cut):
        try:
            if is_cut:
                shutil.move(str(src),str(dest))
                self._push_file_operation(FileOperation('move',dest,old_path=src))
                self.notify(f"已移动: {src.name} -> {dest.parent}",severity="information")
            else:
                if src.is_file():
                    shutil.copy2(str(src),str(dest))
                else:
                    shutil.copytree(str(src),str(dest))
                self._push_file_operation(FileOperation('copy',dest,old_path=src))
                self.notify(f"已复制: {src.name} -> {dest.parent}",severity="information")
            self._refresh_file_tree()
            if is_cut:
                abs_dest=str(dest.resolve())
                for tid,d in self._tab_data.items():
                    if d.get("filepath")==str(src.resolve()):
                        d["filepath"]=abs_dest
                        d["title"]=dest.name
                        d["button"].label=dest.name
                        self.update_status_bar()
                        break
        except Exception as e:
            self.notify(f"操作失败: {e}",severity="error")
    def _delete_node(self,path):
        content=None
        if path.is_file():
            try:
                content=path.read_text(encoding='utf-8',errors='ignore')
            except:
                pass
        def confirm(ok):
            if ok:
                try:
                    if path.is_file():
                        path.unlink()
                    else:
                        shutil.rmtree(path)
                    self._push_file_operation(FileOperation('delete',path,old_data=content))
                    self._refresh_file_tree()
                    self.notify(f"已删除: {path.name}",severity="information")
                    abs_path=str(path.resolve())
                    for tid,d in list(self._tab_data.items()):
                        if d.get("filepath")==abs_path:
                            self.remove_tab(tid)
                            break
                except Exception as e:
                    self.notify(f"删除失败: {e}",severity="error")
        self.push_screen(SaveConfirmScreen(f"确定删除 {path.name} 吗？",confirm))
    def action_rename_node(self):
        tree=self.file_tree
        node=tree.cursor_node
        if node is None:
            self.notify("请先在文件树中选中一个节点",severity="warning")
            return
        data=node.data
        if data is None:
            return
        path=Path(data.path) if hasattr(data,"path") else Path(str(data))
        self._context_path=path
        self._filetree_menu_callback("rename")
    def action_move_node(self):
        tree=self.file_tree
        node=tree.cursor_node
        if node is None:
            self.notify("请先在文件树中选中一个节点",severity="warning")
            return
        data=node.data
        if data is None:
            return
        path=Path(data.path) if hasattr(data,"path") else Path(str(data))
        self._context_path=path
        self._filetree_menu_callback("move_to")
    def _refresh_file_tree(self):
        try:
            self.file_tree.reload()
        except:
            self.file_tree.path=self.file_tree.path
        self.refresh()
    def _open_file_by_path(self,path):
        abs_path=str(path.resolve())
        for tid,d in self._tab_data.items():
            if d.get("filepath")==abs_path:
                self.show_tab(tid)
                return
        if len(self._tab_data)>=9:
            self.notify("最多同时打开 9 个文件",severity="error")
            return
        enc, le = self._get_file_encoding_and_ending(abs_path)
        try:
            with open(abs_path, "r", encoding=enc) as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        if content is None:
            self.notify(f"无法读取文件: {path}",severity="error")
            return
        lang=detect_language(abs_path)
        tid=self.add_new_tab(path.name,content,abs_path)
        ta=self._tab_data[tid]["textarea"]
        if lang is not None:
            try:
                ta.language=lang
            except:
                pass
        self._tab_data[tid]["encoding"]=enc
        self._tab_data[tid]["line_ending"]=le
        self._start_lsp_for_file(abs_path,content)
        self.show_tab(tid)
    def action_toggle_file_tree(self):
        self.file_tree.display=not self.file_tree.display
        self._show_file_tree=self.file_tree.display
        self.notify(self._tr("tree_show") if self.file_tree.display else self._tr("tree_hide"),severity="information")
        self.refresh()
    def action_screenshot(self):
        try:
            path=Path.home()/f"one_editor_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            self.save_screenshot(str(path))
            self.notify(self._tr("screenshot_saved").format(path=path),severity="information")
        except Exception as e:
            self.notify(f"截图失败: {e}",severity="error")
    def _start_lsp_for_file(self,filepath,content):
        lang=detect_language(filepath)
        if not lang or lang not in LANG_SERVERS:
            if self.lsp.running:
                self.run_worker(self.lsp.stop(), exclusive=True, group="lsp")
                self._current_lang=None
            return
        self._current_uri=path_to_uri(filepath)
        if lang!=self._current_lang:
            self.run_worker(self._swap_lsp(lang,filepath,content), exclusive=True, group="lsp")
        elif self.lsp.running:
            self.lsp.did_open(filepath,content)
            self.notify(self._tr("lsp_started").format(lang=lang),severity="information")
    async def _swap_lsp(self,lang,filepath,content):
        await self.lsp.stop()
        root=os.path.dirname(filepath) or "."
        ok=await self.lsp.start(lang,root)
        if ok:
            self._current_lang=lang
            self.lsp.did_open(filepath,content)
            self.notify(self._tr("lsp_started").format(lang=lang),severity="information")
        else:
            self._current_lang=None
            self.notify(self._tr("lsp_failed").format(lang=lang),severity="error")
    def on_text_area_changed(self,event):
        if event.text_area is self.get_current_text_area():
            tid=self.get_current_tab_id()
            if tid and not self._tab_data[tid].get("is_welcome",False):
                self._modified[tid]=True
                self.update_tab_modified(tid)
            self._schedule_completion()
    def _schedule_completion(self):
        if self._completion_timer:
            self._completion_timer.stop()
        self._completion_timer=self.set_timer(0.1,self._trigger_completion)
    def _trigger_completion(self):
        if not self.lsp.running:
            return
        ed=self.get_current_text_area()
        if not ed or ed.read_only:
            return
        fp=self._tab_data.get(self._active_tab_id,{}).get("filepath")
        if not fp:
            return
        lang=detect_language(fp)
        if lang!=self._current_lang:
            return
        self.lsp.did_change(ed.text)
        row,col=ed.cursor_location
        lines=ed.text.splitlines()
        if row<len(lines) and col>0:
            ch=lines[row][col-1]
            if ch.isalnum() or ch=="_" or ch==".":
                self.run_worker(self._fetch_completions(row,col), exclusive=True, group="completion")
                return
        menu=self.query_one("#completion-menu")
        if menu.visible:
            menu.hide()
    async def _fetch_completions(self,row,col):
        items=await self.lsp.complete(row,col)
        menu=self.query_one("#completion-menu")
        if not items:
            menu.hide()
            return
        ed=self.get_current_text_area()
        if not ed:
            return
        co=ed.cursor_screen_offset
        ar=self.query_one("#editor-area").region
        x=co.x-ar.x
        y=co.y-ar.y+1
        menu.show(items,(x,y))
    def _insert_completion(self,item):
        ed=self.get_current_text_area()
        if not ed or ed.read_only:
            return
        menu=self.query_one("#completion-menu")
        menu.hide()
        additional=item.get("additionalTextEdits")
        if additional:
            for edit in reversed(additional):
                r=edit.get("range",{})
                s=r.get("start",{})
                e=r.get("end",{})
                ed.replace(edit.get("newText",""), (s.get("line",0),s.get("character",0)), (e.get("line",0),e.get("character",0)))
        insert=item.get("insertText") or item["label"]
        row,col=ed.cursor_location
        lines=ed.text.splitlines()
        line=lines[row] if row<len(lines) else ""
        ws=col
        while ws>0 and (line[ws-1].isalnum() or line[ws-1]=="_"):
            ws-=1
        clean=insert.split("(")[0] if "(" in insert else insert
        ed.replace(clean,(row,ws),(row,col))
        ed.focus()
    def on_key(self,event):
        menu=self.query_one("#completion-menu")
        if not menu.visible:
            return
        if event.key=="up":
            menu.move_up()
            event.prevent_default()
            event.stop()
        elif event.key=="down":
            menu.move_down()
            event.prevent_default()
            event.stop()
        elif event.key=="tab":
            item=menu.selected_item()
            if item:
                self._insert_completion(item)
            menu.hide()
            event.prevent_default()
            event.stop()
        elif event.key=="enter":
            menu.hide()
            event.prevent_default()
            event.stop()
    def _on_diagnostics(self,uri,diagnostics):
        self._diagnostics_cache[uri]=diagnostics
        if uri==self._current_uri:
            self.update_status_bar()
            error_count=sum(1 for d in diagnostics if d.get("severity",1)<=1)
            warning_count=sum(1 for d in diagnostics if d.get("severity",1)==2)
            self.query_one(TopMenuBar).update_diagnostics(error_count,warning_count)
            ed=self.get_current_text_area()
            if ed and hasattr(ed,'apply_diagnostics'):
                ed.apply_diagnostics(diagnostics)
    def action_show_symbols(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"),severity="warning")
            return
        ed=self.get_current_text_area()
        if not ed or ed.read_only:
            return
        self.lsp.did_change(ed.text)
        self.run_worker(self._fetch_symbols(), exclusive=True, group="symbols")
    async def _fetch_symbols(self):
        symbols=await self.lsp.document_symbol()
        if not symbols:
            self.notify(self._tr("no_symbols"),severity="warning")
            return
        self.push_screen(SymbolListScreen(symbols,self))
    def _jump_to_symbol(self,line,col):
        ed=self.get_current_text_area()
        if ed:
            ed.cursor_location=(line,col)
            ed.focus()
    def action_show_hover(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"),severity="warning")
            return
        ed=self.get_current_text_area()
        if not ed or ed.read_only:
            return
        row,col=ed.cursor_location
        self.lsp.did_change(ed.text)
        self.run_worker(self._fetch_hover(row,col), exclusive=True, group="hover")
    async def _fetch_hover(self,row,col):
        result=await self.lsp.hover(row,col)
        if result:
            self.notify(f"📖 {result}",severity="information",timeout=5)
        else:
            self.notify(self._tr("no_hover"),severity="warning")
    def action_show_diagnostics(self):
        if not self.lsp.running:
            self.notify("LSP 未运行，无法获取诊断",severity="warning",timeout=3)
            return
        diags=self._diagnostics_cache.get(self._current_uri,[])
        if not diags:
            self.notify("当前文件没有诊断信息",severity="information",timeout=3)
        else:
            self.push_screen(DiagnosticScreen(diags,self))
    def action_goto_definition(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"),severity="warning")
            return
        ed=self.get_current_text_area()
        if not ed or ed.read_only:
            return
        self.lsp.did_change(ed.text)
        row,col=ed.cursor_location
        self.run_worker(self._do_goto_definition(row,col), exclusive=True, group="goto-def")
    async def _do_goto_definition(self,row,col):
        result=await self.lsp.goto_definition(row,col)
        if not result:
            self.notify(self._tr("goto_def_fail"),severity="warning")
            return
        target_path=uri_to_path(result["uri"])
        target_line=result["line"]
        target_col=result["col"]
        self._open_file_by_path(Path(target_path))
        def jump():
            ed=self.get_current_text_area()
            if ed:
                ed.cursor_location=(target_line,target_col)
                ed.focus()
        self.call_after_refresh(jump)
    def action_rename_symbol(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"),severity="warning")
            return
        ed=self.get_current_text_area()
        if not ed or ed.read_only:
            self.notify("没有可用的编辑器", severity="warning")
            return
        row,col=ed.cursor_location
        self.lsp.did_change(ed.text)
        def cb(n):
            if not n:
                return
            self.run_worker(self._do_rename(row,col,n), exclusive=True, group="rename")
        try:
            self.push_screen(InputScreen(self._tr("rename_prompt"),cb))
        except Exception as e:
            self.notify(f"打开重命名符号失败: {e}", severity="error")
            traceback.print_exc()
    async def _do_rename(self,row,col,new_name):
        result=await self.lsp.rename(row,col,new_name)
        if not result:
            self.notify(self._tr("rename_fail")+"：服务器无响应或语言不支持",severity="error")
            return
        ed=self.get_current_text_area()
        if not ed:
            return
        if "changes" in result:
            for uri,edits in result["changes"].items():
                if uri==self._current_uri:
                    for edit in reversed(edits):
                        r=edit.get("range",{})
                        s=r.get("start",{})
                        e=r.get("end",{})
                        ed.replace(edit.get("newText",""), (s.get("line",0),s.get("character",0)), (e.get("line",0),e.get("character",0)))
                    self.notify(self._tr("rename_success"),severity="information")
                    return
            self.notify("重命名成功但不在当前文件内",severity="information")
        elif "documentChanges" in result:
            for change in result["documentChanges"]:
                if change.get("textDocument",{}).get("uri")==self._current_uri:
                    for edit in reversed(change.get("edits",[])):
                        r=edit.get("range",{})
                        s=r.get("start",{})
                        e=r.get("end",{})
                        ed.replace(edit.get("newText",""), (s.get("line",0),s.get("character",0)), (e.get("line",0),e.get("character",0)))
                    self.notify(self._tr("rename_success"),severity="information")
                    return
        else:
            self.notify(self._tr("rename_fail")+"：无法解析服务器响应",severity="error")
    def action_code_action(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"),severity="warning")
            return
        ed=self.get_current_text_area()
        if not ed or ed.read_only:
            return
        row,col=ed.cursor_location
        self.lsp.did_change(ed.text)
        self.run_worker(self._fetch_code_actions(row,col), exclusive=True, group="code-action")
    async def _fetch_code_actions(self,row,col):
        actions=await self.lsp.code_action(row,col)
        if not actions:
            self.notify("没有可用的代码操作",severity="information")
            return
        items=[{"label":a.get("title","操作"),"action":a} for a in actions]
        def cb(a):
            self._apply_code_action(a)
        self.push_screen(OptionListMenu(self._tr("code_action"),items,cb))
    def _apply_code_action(self,action):
        try:
            if "edit" in action:
                edits=action["edit"]
                ed=self.get_current_text_area()
                if ed and isinstance(edits, dict):
                    if "changes" in edits and isinstance(edits["changes"], dict):
                        for uri, edit_list in edits["changes"].items():
                            if uri == self._current_uri and isinstance(edit_list, list):
                                for edit in reversed(edit_list):
                                    if isinstance(edit, dict):
                                        r = edit.get("range", {})
                                        s = r.get("start", {}) if isinstance(r, dict) else {}
                                        e = r.get("end", {}) if isinstance(r, dict) else {}
                                        ed.replace(
                                            edit.get("newText", ""),
                                            (s.get("line", 0), s.get("character", 0)),
                                            (e.get("line", 0), e.get("character", 0))
                                        )
                    elif "documentChanges" in edits and isinstance(edits["documentChanges"], list):
                        for change in edits["documentChanges"]:
                            if isinstance(change, dict) and change.get("textDocument", {}).get("uri") == self._current_uri:
                                for edit in reversed(change.get("edits", [])):
                                    if isinstance(edit, dict):
                                        r = edit.get("range", {})
                                        s = r.get("start", {}) if isinstance(r, dict) else {}
                                        e = r.get("end", {}) if isinstance(r, dict) else {}
                                        ed.replace(
                                            edit.get("newText", ""),
                                            (s.get("line", 0), s.get("character", 0)),
                                            (e.get("line", 0), e.get("character", 0))
                                        )
            if "command" in action:
                self.notify(f"执行命令: {action['command']['title']}", severity="information")
        except Exception as e:
            self.notify(f"应用代码操作失败: {e}", severity="error")
            traceback.print_exc()
    def action_format_document(self):
        if not self.lsp.running:
            self.notify(self._tr("lsp_not_running"),severity="warning")
            return
        ed=self.get_current_text_area()
        if not ed or ed.read_only:
            return
        self.lsp.did_change(ed.text)
        self.run_worker(self._do_format(), exclusive=True, group="format")
    async def _do_format(self):
        result=await self.lsp.format_document()
        if result:
            ed=self.get_current_text_area()
            if ed:
                for edit in result:
                    r=edit.get("range",{})
                    s=r.get("start",{})
                    e=r.get("end",{})
                    ed.replace(edit.get("newText",""), (s.get("line",0),s.get("character",0)), (e.get("line",0),e.get("character",0)))
                self.notify(self._tr("format_success"),severity="information")
        else:
            self.notify(self._tr("format_fail"),severity="warning")
    def action_select_all(self):
        ed=self.get_current_text_area()
        if ed:
            ed.select_all()
    def _get_run_command(self,filepath):
        ext=Path(filepath).suffix.lower()
        if ext=='.py':
            return ['python',filepath]
        elif ext=='.js':
            return ['node',filepath]
        elif ext=='.c':
            out=Path(filepath).with_suffix('.exe' if os.name=='nt' else '')
            return ['gcc',filepath,'-o',str(out),'&&',str(out)]
        elif ext=='.cpp':
            out=Path(filepath).with_suffix('.exe' if os.name=='nt' else '')
            return ['g++',filepath,'-o',str(out),'&&',str(out)]
        elif ext=='.go':
            return ['go','run',filepath]
        elif ext=='.rs':
            return ['cargo','run','--',filepath]
        elif ext=='.rb':
            return ['ruby',filepath]
        elif ext=='.php':
            return ['php',filepath]
        elif ext=='.sh':
            return ['bash',filepath]
        else:
            return None
    def _find_project_root(self,path):
        for p in [path]+list(path.parents):
            if (p/'CMakeLists.txt').exists():
                return p
            if (p/'package.json').exists():
                return p
            if (p/'Cargo.toml').exists():
                return p
            if (p/'go.mod').exists():
                return p
        return None
    def action_run(self):
        tid=self.get_current_tab_id()
        if not tid:
            return
        d=self._tab_data[tid]
        if d.get("is_welcome",False):
            self.notify("欢迎页不可运行",severity="warning")
            return
        fp=d.get("filepath")
        if not fp:
            self.notify(self._tr("no_file"),severity="warning")
            return
        self.action_save_file(tid)
        cmd=self._get_run_command(fp)
        if not cmd:
            self.notify(self._tr("unsupported_lang"),severity="warning")
            return
        shell=any(x in cmd for x in ['&&','||','|','>','<']) if isinstance(cmd,list) else False
        self.output_panel.display=True
        self.output_panel.clear()
        self.run_worker(self._run_process(cmd,fp,shell=shell), exclusive=True, group="run")
    def action_build(self):
        tid=self.get_current_tab_id()
        if not tid:
            return
        d=self._tab_data[tid]
        if d.get("is_welcome",False):
            self.notify("欢迎页不可构建",severity="warning")
            return
        fp=d.get("filepath")
        if not fp:
            self.notify(self._tr("no_file"),severity="warning")
            return
        root=self._find_project_root(Path(fp).parent)
        if not root:
            self.notify(self._tr("no_project"),severity="warning")
            return
        cmds=[]
        cwd=None
        if (root/'CMakeLists.txt').exists():
            build_dir=root/'build'
            build_dir.mkdir(exist_ok=True)
            cmds=['cmake','..','&&','cmake','--build','.']
            cwd=build_dir
        elif (root/'package.json').exists():
            cmds=['npm','install','&&','npm','run','build']
            cwd=root
        elif (root/'Cargo.toml').exists():
            cmds=['cargo','build']
            cwd=root
        elif (root/'go.mod').exists():
            cmds=['go','build']
            cwd=root
        else:
            self.notify(self._tr("no_build_system"),severity="warning")
            return
        self.output_panel.display=True
        self.output_panel.clear()
        self.run_worker(self._run_process(cmds,cwd=cwd,shell=True), exclusive=True, group="build")
    def action_debug(self):
        tid=self.get_current_tab_id()
        if not tid:
            return
        d=self._tab_data[tid]
        if d.get("is_welcome",False):
            self.notify("欢迎页不可调试",severity="warning")
            return
        fp=d.get("filepath")
        if not fp:
            self.notify(self._tr("no_file"),severity="warning")
            return
        if Path(fp).suffix.lower()=='.py':
            try:
                if os.name == 'nt':
                    subprocess.Popen(['start', 'cmd', '/k', 'python', '-m', 'pdb', fp], shell=True)
                else:
                    subprocess.Popen(['xterm', '-e', 'python', '-m', 'pdb', fp])
                self.notify("调试器已在外部终端启动", severity="information")
            except Exception as e:
                self.notify(f"启动调试失败: {e}", severity="error")
        else:
            self.notify(self._tr("debug_py_only"), severity="information")
    async def _run_process(self,cmd,cwd=None,shell=False):
        if cwd and Path(cwd).is_file():
            cwd=str(Path(cwd).parent)
        if shell:
            cmd_str=' '.join(cmd) if isinstance(cmd,list) else cmd
            proc=await asyncio.create_subprocess_shell(cmd_str, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd or os.getcwd())
        else:
            proc=await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd or os.path.dirname(cmd[-1]) if os.path.isfile(cmd[-1]) else os.getcwd())
        while True:
            line=await proc.stdout.readline()
            if not line:
                break
            try:
                self.output_panel.output_area.text+=line.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    self.output_panel.output_area.text+=line.decode('gbk')
                except:
                    self.output_panel.output_area.text+=line.decode('utf-8',errors='replace')
        while True:
            line=await proc.stderr.readline()
            if not line:
                break
            try:
                self.output_panel.output_area.text+=line.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    self.output_panel.output_area.text+=line.decode('gbk')
                except:
                    self.output_panel.output_area.text+=line.decode('utf-8',errors='replace')
        await proc.wait()
        self.notify(self._tr("run_success").format(code=proc.returncode),severity="information")
    def action_toggle_terminal(self):
        if self.terminal_panel.display:
            self.terminal_panel.display=False
            self.terminal_panel.input.blur()
        else:
            self.terminal_panel.display=True
            self.terminal_panel.input.focus()
        self.refresh()
    def action_clear_terminal(self):
        if self.terminal_panel.display:
            self.terminal_panel.clear()
    def action_toggle_ollama(self):
        if self.ollama_panel.display:
            self.ollama_panel.display=False
        else:
            self.ollama_panel.display=True
            self.ollama_panel.input.focus()
        self.refresh()
    def _get_commands(self):
        cmds={}
        for b in self.BINDINGS:
            if b.description and b.action:
                cmds[b.action]=f"{b.key}   {b.description}"
        cmds["compare_files"]=self._tr("compare_files")
        cmds["screenshot"]="📸 截图"
        cmds["change_theme"]="🎨 切换主题"
        return cmds
    def action_command_palette(self):
        cmds=self._get_commands()
        def cb(a):
            if a=="command_palette":
                return
            if a=="change_theme":
                themes=["textual-dark","textual-light","dracula","nord"]
                try:
                    idx=themes.index(self.theme)
                    next_theme=themes[(idx+1)%len(themes)]
                except:
                    next_theme=themes[0]
                self.theme=next_theme
                self._settings["theme"]=next_theme
                self._save_settings()
                self.notify(self._tr("theme_changed").format(theme=next_theme),severity="information")
                return
            if hasattr(self,f"action_{a}"):
                getattr(self,f"action_{a}")()
            else:
                self.notify(f"未知命令: {a}",severity="warning")
        try:
            self.push_screen(CommandPalette(cmds,cb))
        except Exception as e:
            self.notify(f"打开命令面板失败: {e}", severity="error")
            traceback.print_exc()
    def action_compare_files(self):
        tabs=[d for d in self._tab_data.values() if not d.get("is_welcome",False)]
        if len(tabs)>=2:
            try:
                self.push_screen(DiffScreen(tabs[0]["textarea"].text, tabs[1]["textarea"].text, tabs[0]["title"], tabs[1]["title"]))
            except Exception as e:
                self.notify(f"文件对比失败: {e}", severity="error")
                traceback.print_exc()
        else:
            self.notify(self._tr("no_diff_tabs"),severity="warning")
    def focus_editor(self):
        ed=self.get_current_text_area()
        if ed:
            ed.focus()
    def get_current_tab_id(self):
        return self._active_tab_id
    def get_current_text_area(self):
        if self._active_tab_id and self._active_tab_id in self._tab_data:
            return self._tab_data[self._active_tab_id]["textarea"]
        return None
    def get_current_dir(self):
        tid=self.get_current_tab_id()
        if tid and tid in self._tab_data:
            fp=self._tab_data[tid].get("filepath")
            if fp and Path(fp).exists():
                return str(Path(fp).parent)
        return str(Path.cwd())

if __name__=="__main__":
    OneEditor().run()