"""LSP 客户端：修复 drain、pending future 取消、进程崩溃处理。"""
import asyncio
import json
import os
import shutil
from typing import Any, Dict, List, Optional

LANG_SERVERS = {
    "python": ["pylsp"],
    "javascript": ["typescript-language-server", "--stdio"],
    "typescript": ["typescript-language-server", "--stdio"],
    "rust": ["rust-analyzer"],
    "go": ["gopls", "serve"],
    "c": ["clangd"],
    "cpp": ["clangd"],
    "java": ["jdtls"],
    "ruby": ["solargraph", "stdio"],
    "php": ["intelephense", "--stdio"],
}


def path_to_uri(path: str) -> str:
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return f"file://{p}"


def uri_to_path(uri: str) -> str:
    if not uri.startswith("file://"):
        return uri
    p = uri[len("file://"):]
    if len(p) > 2 and p[0] == "/" and p[2] == ":":
        p = p[1:]
    return p.replace("/", os.sep)


class LspClient:
    def __init__(self):
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._version = 0
        self._uri: Optional[str] = None
        self._language: Optional[str] = None
        self._diagnostics: Dict[str, List[Dict[str, Any]]] = {}
        self._diag_callback = None
        self._send_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, language: str, root_path: str) -> bool:
        cmd = LANG_SERVERS.get(language)
        if not cmd:
            return False
        exe = shutil.which(cmd[0])
        if not exe:
            return False
        try:
            self._proc = await asyncio.create_subprocess_exec(
                exe, *cmd[1:],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception:
            self._proc = None
            return False

        self._reader_task = asyncio.create_task(self._read_loop())
        self._language = language
        try:
            await self._request("initialize", {
                "processId": os.getpid(),
                "rootUri": path_to_uri(root_path),
                "capabilities": {
                    "textDocument": {
                        "completion": {
                            "completionItem": {"snippetSupport": False},
                            "additionalTextEdits": True,
                        },
                        "definition": {"dynamicRegistration": False},
                        "hover": {"dynamicRegistration": False},
                        "documentSymbol": {"dynamicRegistration": False},
                        "publishDiagnostics": {"dynamicRegistration": False},
                        "codeAction": {"dynamicRegistration": False},
                        "rename": {"dynamicRegistration": False},
                        "formatting": {"dynamicRegistration": False},
                    },
                    "workspace": {
                        "didChangeWatchedFiles": {"dynamicRegistration": False}
                    },
                },
            })
            await self._notify("initialized", {})
            return True
        except Exception:
            await self.stop()
            return False

    async def stop(self) -> None:
        if not self.running:
            self._cleanup_after_stop()
            return
        try:
            await asyncio.wait_for(self._request("shutdown", None), timeout=2)
            await self._notify("exit", None)
        except Exception:
            pass

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except Exception:
                pass
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=1)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._cleanup_after_stop()

    def _cleanup_after_stop(self) -> None:
        self._proc = None
        self._reader_task = None
        self._diagnostics.clear()
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    def did_open(self, path: str, text: str) -> None:
        self._uri = path_to_uri(path)
        self._version = 1
        self._schedule_notify("textDocument/didOpen", {
            "textDocument": {
                "uri": self._uri,
                "languageId": self._language,
                "version": self._version,
                "text": text,
            },
        })

    def did_change(self, text: str, changes: list[dict] | None = None) -> None:
        """发送文档变更。

        changes 为 LSP 增量 changes 列表；为 None 或空时发送全文。
        增量 changes 中每个元素格式：
        {"range": {"start": {"line": L, "character": C},
                   "end": {"line": L, "character": C}},
         "text": "新内容"}
        """
        if not self._uri:
            return
        self._version += 1
        content_changes = changes if changes else [{"text": text}]
        self._schedule_notify("textDocument/didChange", {
            "textDocument": {"uri": self._uri, "version": self._version},
            "contentChanges": content_changes,
        })

    def _schedule_notify(self, method: str, params: Any) -> None:
        """通知类消息异步发送，不阻塞 UI。"""
        async def _run():
            await self._notify(method, params)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run())
        except RuntimeError:
            pass

    async def complete(self, line: int, col: int) -> List[Dict[str, Any]]:
        if not self._uri or not self.running:
            return []
        try:
            result = await asyncio.wait_for(self._request(
                "textDocument/completion",
                {
                    "textDocument": {"uri": self._uri},
                    "position": {"line": line, "character": col},
                },
            ), timeout=5)
        except Exception:
            return []
        if not result:
            return []
        items = result if isinstance(result, list) else result.get("items", [])
        out = []
        for item in items:
            comp = {
                "label": item.get("label", ""),
                "insertText": item.get("insertText") or item.get("label", ""),
            }
            if "additionalTextEdits" in item:
                comp["additionalTextEdits"] = item["additionalTextEdits"]
            out.append(comp)
        return out

    async def goto_definition(self, line: int, col: int) -> Optional[Dict[str, Any]]:
        if not self._uri or not self.running:
            return None
        try:
            result = await asyncio.wait_for(self._request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": self._uri},
                    "position": {"line": line, "character": col},
                },
            ), timeout=5)
        except Exception:
            return None
        if not result:
            return None
        target = result[0] if isinstance(result, list) else result
        if "targetUri" in target:
            uri = target["targetUri"]
            pos = (target.get("targetSelectionRange")
                   or target.get("targetRange") or {}).get("start", {})
        else:
            uri = target.get("uri", "")
            pos = target.get("range", {}).get("start", {})
        return {"uri": uri, "line": pos.get("line", 0), "col": pos.get("character", 0)}

    async def hover(self, line: int, col: int) -> Optional[str]:
        if not self._uri or not self.running:
            return None
        try:
            result = await asyncio.wait_for(self._request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": self._uri},
                    "position": {"line": line, "character": col},
                },
            ), timeout=5)
        except Exception:
            return None
        if not result:
            return None
        contents = result.get("contents", {})
        if isinstance(contents, dict):
            return contents.get("value") or contents.get("kind")
        if isinstance(contents, list):
            return "\n".join(str(c) for c in contents)
        return str(contents)

    async def document_symbol(self) -> List[Dict[str, Any]]:
        if not self._uri or not self.running:
            return []
        try:
            result = await asyncio.wait_for(self._request(
                "textDocument/documentSymbol",
                {"textDocument": {"uri": self._uri}},
            ), timeout=5)
        except Exception:
            return []
        out = []
        for item in result or []:
            rng = item.get("range") or item.get("location", {}).get("range") or {}
            start = rng.get("start", {})
            out.append({
                "name": item.get("name", ""),
                "kind": item.get("kind", 0),
                "line": start.get("line", 0),
                "col": start.get("character", 0),
            })
        return out

    def get_diagnostics(self) -> List[Dict[str, Any]]:
        return self._diagnostics.get(self._uri, [])

    def set_diagnostics_callback(self, cb) -> None:
        self._diag_callback = cb

    async def references(self, line: int, col: int,
                         include_declaration: bool = True) -> list[dict]:
        """查找所有引用。返回 [{"uri", "line", "col"}, ...]"""
        if not self._uri or not self.running:
            return []
        try:
            result = await asyncio.wait_for(self._request(
                "textDocument/references",
                {
                    "textDocument": {"uri": self._uri},
                    "position": {"line": line, "character": col},
                    "context": {"includeDeclaration": include_declaration},
                },
            ), timeout=5)
        except Exception:
            return []
        if not result:
            return []
        out = []
        for item in result:
            uri = item.get("uri", "")
            start = item.get("range", {}).get("start", {})
            out.append({
                "uri": uri,
                "line": start.get("line", 0),
                "col": start.get("character", 0),
            })
        return out
    async def code_action(self, line: int, col: int) -> List[Dict[str, Any]]:
        if not self._uri or not self.running:
            return []
        try:
            result = await asyncio.wait_for(self._request(
                "textDocument/codeAction",
                {
                    "textDocument": {"uri": self._uri},
                    "range": {
                        "start": {"line": line, "character": col},
                        "end": {"line": line, "character": col},
                    },
                    "context": {"diagnostics": self._diagnostics.get(self._uri, [])},
                },
            ), timeout=5)
        except Exception:
            return []
        return result or []

    async def execute_command(self, command: str, arguments: list):
        if not self._uri or not self.running:
            return None
        try:
            return await asyncio.wait_for(self._request(
                "workspace/executeCommand",
                {"command": command, "arguments": arguments},
            ), timeout=5)
        except Exception:
            return None

    async def rename(self, line: int, col: int, new_name: str) -> Optional[Dict[str, Any]]:
        if not self._uri or not self.running:
            return None
        try:
            return await asyncio.wait_for(self._request(
                "textDocument/rename",
                {
                    "textDocument": {"uri": self._uri},
                    "position": {"line": line, "character": col},
                    "newName": new_name,
                },
            ), timeout=5)
        except Exception:
            return None

    async def format_document(self) -> List[Dict[str, Any]]:
        if not self._uri or not self.running:
            return []
        try:
            result = await asyncio.wait_for(self._request(
                "textDocument/formatting",
                {
                    "textDocument": {"uri": self._uri},
                    "options": {"tabSize": 4, "insertSpaces": True},
                },
            ), timeout=5)
        except Exception:
            return []
        return result or []

    # ---------- 底层通信 ----------
    async def _request(self, method: str, params: Any):
        self._id += 1
        rid = self._id
        future = asyncio.get_running_loop().create_future()
        self._pending[rid] = future
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return await future

    async def _notify(self, method: str, params: Any) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _send(self, msg: dict) -> None:
        if not self.running:
            return
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        async with self._send_lock:
            try:
                self._proc.stdin.write(header + body)
                await self._proc.stdin.drain()
            except Exception:
                pass

    async def _read_loop(self) -> None:
        try:
            while self.running:
                content_length = 0
                while True:
                    line = await self._proc.stdout.readline()
                    if not line:
                        return
                    line = line.decode().strip()
                    if not line:
                        break
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":", 1)[1].strip())
                if content_length == 0:
                    continue
                body = await self._proc.stdout.readexactly(content_length)
                msg = json.loads(body)
                if "method" in msg:
                    if msg["method"] == "textDocument/publishDiagnostics":
                        uri = msg["params"]["uri"]
                        self._diagnostics[uri] = msg["params"]["diagnostics"]
                        if self._diag_callback:
                            self._diag_callback(uri, msg["params"]["diagnostics"])
                    continue
                rid = msg.get("id")
                if rid is not None and rid in self._pending:
                    fut = self._pending.pop(rid)
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(Exception(
                                msg["error"].get("message", "LSP error")
                            ))
                        else:
                            fut.set_result(msg.get("result"))
        except asyncio.CancelledError:
            raise
        except asyncio.IncompleteReadError:
            # 进程崩溃
            self._proc = None
            for fut in self._pending.values():
                if not fut.done():
                    fut.cancel()
            self._pending.clear()
        except (ConnectionError, Exception):
            self._proc = None
            for fut in self._pending.values():
                if not fut.done():
                    fut.cancel()
            self._pending.clear()