"""工具函数：安全读文件、语言检测、编码探测、运行命令生成。"""
import os
import shlex
from pathlib import Path
from typing import List, Optional, Tuple

from constants import LANGUAGE_MAP


def detect_language(path: str) -> Optional[str]:
    return LANGUAGE_MAP.get(Path(path).suffix.lower())


def safe_read(path: str, encoding: str = "utf-8") -> Optional[str]:
    try:
        return Path(path).read_text(encoding=encoding)
    except Exception:
        return None


def get_file_encoding_and_ending(filepath: str) -> Tuple[str, str]:
    """返回 (编码名, 换行符)。尽力探测，失败时返回 UTF-8/LF。"""
    if not filepath or not Path(filepath).exists():
        return "UTF-8", "LF"

    try:
        raw = Path(filepath).read_bytes()
    except Exception:
        return "UTF-8", "LF"

    if raw.startswith(b"\xef\xbb\xbf"):
        return "UTF-8-BOM", ("CRLF" if b"\r\n" in raw else "LF")
    if raw.startswith(b"\xff\xfe"):
        return "UTF-16-LE", ("CRLF" if b"\r\n" in raw else "LF")
    if raw.startswith(b"\xfe\xff"):
        return "UTF-16-BE", ("CRLF" if b"\r\n" in raw else "LF")

    line_ending = "CRLF" if b"\r\n" in raw else "LF"

    # 尝试用 charset_normalizer 做更准确的探测
    try:
        from charset_normalizer import from_bytes
        result = from_bytes(raw).best()
        if result is not None and result.encoding:
            enc = result.encoding.upper()
            if enc in ("UTF-8", "ASCII"):
                return "UTF-8", line_ending
            return enc, line_ending
    except ImportError:
        pass

    # 回退
    try:
        raw.decode("utf-8")
        return "UTF-8", line_ending
    except UnicodeDecodeError:
        return "GBK", line_ending  # 保守回退


def format_command(cmd: str, filepath: str) -> str:
    """替换插件设置中的占位符。"""
    fp = Path(filepath)
    return (
        cmd.replace("{FilePath}", str(fp))
        .replace("{FilePathWithNoExtension}", str(fp.with_suffix("")))
        .replace("{FileName}", fp.name)
        .replace("{FileNameWithNoExtension}", fp.stem)
        .replace("{DirPath}", str(fp.parent))
    )


def get_run_command(filepath: str) -> Optional[List[str]]:
    ext = Path(filepath).suffix.lower()
    if ext == ".py":
        return ["python", filepath]
    if ext == ".js":
        return ["node", filepath]
    if ext in (".c", ".cpp"):
        compiler = "gcc" if ext == ".c" else "g++"
        out = Path(filepath).with_suffix(".exe" if os.name == "nt" else "")
        return [compiler, filepath, "-o", str(out), "&&", str(out)]
    if ext == ".go":
        return ["go", "run", filepath]
    if ext == ".rs":
        return ["cargo", "run", "--", filepath]
    if ext == ".rb":
        return ["ruby", filepath]
    if ext == ".php":
        return ["php", filepath]
    if ext == ".sh":
        return ["bash", filepath]
    return None


def build_shell_command(cmd) -> str:
    """把 list 拼成安全的 shell 命令（对含空格路径加引号）。"""
    if isinstance(cmd, str):
        return cmd
    return " ".join(shlex.quote(str(x)) for x in cmd)


def find_project_root(path: Path) -> Optional[Path]:
    markers = ("CMakeLists.txt", "package.json", "Cargo.toml", "go.mod")
    for p in [path] + list(path.parents):
        if any((p / m).exists() for m in markers):
            return p
    return None