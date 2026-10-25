"""Markdown/HTML 预览：临时文件自动清理，最多保留 5 个。"""
import atexit
import tempfile
import webbrowser
from collections import deque
from pathlib import Path

CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       max-width: 800px; margin: 0 auto; padding: 2rem; line-height: 1.6; color: #24292e; }
h1, h2, h3 { border-bottom: 1px solid #eaecef; padding-bottom: .3em; }
pre { background: #f6f8fa; padding: 16px; border-radius: 6px; overflow: auto; }
code { background: #f6f8fa; padding: .2em .4em; border-radius: 3px; }
table { border-collapse: collapse; }
th, td { border: 1px solid #dfe2e5; padding: 6px 13px; }
blockquote { border-left: 4px solid #dfe2e5; color: #6a737d; padding-left: 1em; margin-left: 0; }
"""

_TEMP_FILES: deque = deque(maxlen=5)


def _cleanup() -> None:
    while _TEMP_FILES:
        p = _TEMP_FILES.popleft()
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass


atexit.register(_cleanup)


def _create_html_with_style(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8">
<title>One-Editor 预览</title><style>{CSS}</style></head>
<body>{body}</body></html>"""


def preview_markdown(path) -> None:
    try:
        import markdown
    except ImportError:
        raise ImportError("请先安装 markdown 库: pip install markdown")

    text = Path(path).read_text(encoding="utf-8")
    html_body = markdown.markdown(
        text, extensions=["tables", "fenced_code", "codehilite"]
    )
    full_html = _create_html_with_style(html_body)

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".html", mode="w", encoding="utf-8"
    ) as f:
        f.write(full_html)
        temp_path = f.name
    _TEMP_FILES.append(temp_path)
    webbrowser.open(Path(temp_path).resolve().as_uri())


def preview_html(path) -> None:
    webbrowser.open(Path(path).resolve().as_uri())


def preview_file(path) -> None:
    ext = Path(path).suffix.lower()
    if ext in (".md", ".markdown"):
        preview_markdown(path)
    elif ext in (".html", ".htm"):
        preview_html(path)
    else:
        raise ValueError(f"暂不支持该文件格式的预览: {ext}")