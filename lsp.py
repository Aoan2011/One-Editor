import asyncio
import json
import os
import subprocess
from typing import Optional, List, Dict, Any

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
    path = os.path.abspath(path).replace("\\", "/")
    if not path.startswith("/"):
        path = "/" + path
    return f"file://{path}"

def uri_to_path(uri: str) -> str:
    if not uri.startswith("file://"):
        return uri
    path = uri[len("file://"):]
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path.replace("/", os.sep)

class LspClient:
    def __init__(self):
        self._proc = None
        self._id = 0
        self._pending = {}
        self._reader_task = None
        self._version = 0
        self._uri = None
        self._language = None
        self._diagnostics = {}
        self._diag_callback = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, language: str, root_path: str) -> bool:
        cmd = LANG_SERVERS.get(language)
        if not cmd:
            return False
        import shutil
        exe = shutil.which(cmd[0])
        if not exe:
            return False
        try:
            self._proc = await asyncio.create_subprocess_exec(
                exe,
                *cmd[1:],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception:
            return False
        self._reader_task = asyncio.create_task(self._read_loop())
        self._language = language
        await self._request("initialize", {
            "processId": os.getpid(),
            "rootUri": path_to_uri(root_path),
            "capabilities": {
                "textDocument": {
                    "completion": {
                        "completionItem": {"snippetSupport": False},
                        "additionalTextEdits": True,  # 支持自动添加头文件
                    },
                    "definition": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False},
                    "documentSymbol": {"dynamicRegistration": False},
                    "publishDiagnostics": {"dynamicRegistration": False},
                },
                "workspace": {"didChangeWatchedFiles": {"dynamicRegistration": False}},
            },
        })
        self._notify("initialized", {})
        return True

    async def stop(self):
        if not self.running:
            return
        try:
            await asyncio.wait_for(self._request("shutdown", None), timeout=2)
            self._notify("exit", None)
        except Exception:
            pass
        if self._reader_task:
            self._reader_task.cancel()
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
        self._proc = None
        self._pending.clear()
        self._diagnostics.clear()

    def did_open(self, path: str, text: str):
        self._uri = path_to_uri(path)
        self._version = 1
        self._notify("textDocument/didOpen", {
            "textDocument": {"uri": self._uri, "languageId": self._language, "version": self._version, "text": text},
        })

    def did_change(self, text: str):
        if not self._uri:
            return
        self._version += 1
        self._notify("textDocument/didChange", {
            "textDocument": {"uri": self._uri, "version": self._version},
            "contentChanges": [{"text": text}],
        })

    async def complete(self, line: int, col: int) -> List[Dict[str, Any]]:
        if not self._uri or not self.running:
            return []
        try:
            result = await asyncio.wait_for(
                self._request("textDocument/completion", {
                    "textDocument": {"uri": self._uri},
                    "position": {"line": line, "character": col},
                }),
                timeout=5,
            )
        except Exception:
            return []
        if not result:
            return []
        items = result if isinstance(result, list) else result.get("items", [])
        completions = []
        for item in items:
            comp = {
                "label": item.get("label", ""),
                "insertText": item.get("insertText") or item.get("label", ""),
            }
            # 如果有 additionalTextEdits，一并返回
            if "additionalTextEdits" in item:
                comp["additionalTextEdits"] = item["additionalTextEdits"]
            completions.append(comp)
        return completions

    async def goto_definition(self, line: int, col: int) -> Optional[Dict[str, Any]]:
        if not self._uri or not self.running:
            return None
        try:
            result = await asyncio.wait_for(
                self._request("textDocument/definition", {
                    "textDocument": {"uri": self._uri},
                    "position": {"line": line, "character": col},
                }),
                timeout=5,
            )
        except Exception:
            return None
        if not result:
            return None
        target = result[0] if isinstance(result, list) else result
        if "targetUri" in target:
            uri = target["targetUri"]
            pos = target.get("targetSelectionRange", target.get("targetRange", {})).get("start", {"line": 0, "character": 0})
        else:
            uri = target.get("uri", "")
            pos = target.get("range", {}).get("start", {"line": 0, "character": 0})
        return {"uri": uri, "line": pos.get("line", 0), "col": pos.get("character", 0)}

    async def hover(self, line: int, col: int) -> Optional[str]:
        if not self._uri or not self.running:
            return None
        try:
            result = await asyncio.wait_for(
                self._request("textDocument/hover", {
                    "textDocument": {"uri": self._uri},
                    "position": {"line": line, "character": col},
                }),
                timeout=5,
            )
        except Exception:
            return None
        if not result:
            return None
        contents = result.get("contents", {})
        if isinstance(contents, dict):
            return contents.get("value") or contents.get("kind")
        elif isinstance(contents, list):
            return "\n".join(str(c) for c in contents)
        return str(contents)

    async def document_symbol(self) -> List[Dict[str, Any]]:
        if not self._uri or not self.running:
            return []
        try:
            result = await asyncio.wait_for(
                self._request("textDocument/documentSymbol", {
                    "textDocument": {"uri": self._uri},
                }),
                timeout=5,
            )
        except Exception:
            return []
        if not result:
            return []
        symbols = []
        for item in result:
            if "range" in item:
                name = item.get("name", "")
                kind = item.get("kind", 0)
                range_ = item.get("range", {}).get("start", {})
                line = range_.get("line", 0)
                col = range_.get("character", 0)
                symbols.append({"name": name, "kind": kind, "line": line, "col": col})
            else:
                name = item.get("name", "")
                kind = item.get("kind", 0)
                location = item.get("location", {})
                range_ = location.get("range", {}).get("start", {})
                line = range_.get("line", 0)
                col = range_.get("character", 0)
                symbols.append({"name": name, "kind": kind, "line": line, "col": col})
        return symbols

    def get_diagnostics(self) -> List[Dict[str, Any]]:
        return self._diagnostics.get(self._uri, [])

    def set_diagnostics_callback(self, callback):
        self._diag_callback = callback

    async def _request(self, method: str, params: Any):
        self._id += 1
        rid = self._id
        future = asyncio.get_event_loop().create_future()
        self._pending[rid] = future
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        return await future

    def _notify(self, method: str, params: Any):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, msg: dict):
        if not self.running:
            return
        body = json.dumps(msg).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        self._proc.stdin.write(header + body)

    async def _read_loop(self):
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
                        content_length = int(line.split(":")[1].strip())
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
                    future = self._pending.pop(rid)
                    if not future.done():
                        if "error" in msg:
                            future.set_exception(Exception(msg["error"].get("message", "LSP error")))
                        else:
                            future.set_result(msg.get("result"))
        except (asyncio.CancelledError, ConnectionError):
            pass
        except Exception:
            pass