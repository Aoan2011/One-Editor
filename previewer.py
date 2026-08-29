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
import webbrowser
import tempfile
from pathlib import Path

# 内置一套好看的 Markdown CSS 样式（可以直接改）
CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       max-width: 800px; margin: 0 auto; padding: 2rem; line-height: 1.6; color: #24292e; }
h1, h2, h3 { border-bottom: 1px solid #eaecef; padding-bottom: .3em; }
pre { background: #f6f8fa; padding: 16px; border-radius: 6px; overflow: auto; }
code { background: #f6f8fa; padding: .2em .4em; border-radius: 3px; }
table { border-collapse: collapse; }
th, td { border: 1px solid #dfe2e5; padding: 6px 13px; }
blockquote { border-left: 4px solid #dfe2e5; color: #6a737d; padding-left: 1em; margin-left: 0; }
"""

def _create_html_with_style(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>One-Editor 预览</title>
    <style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>"""

def preview_markdown(path):
    """将 Markdown 转为 HTML 并在浏览器打开"""
    try:
        import markdown
    except ImportError:
        raise ImportError("请先安装 markdown 库: pip install markdown")

    # 读取文件内容
    text = Path(path).read_text(encoding='utf-8')
    
    # 转换 Markdown 为 HTML，并开启表格、代码块等扩展
    html_body = markdown.markdown(text, extensions=['tables', 'fenced_code', 'codehilite'])
    full_html = _create_html_with_style(html_body)

    # 创建临时 HTML 文件（不会污染原目录，每次预览也是新的）
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
        f.write(full_html)
        temp_path = f.name

    # 用系统默认浏览器打开
    webbrowser.open(Path(temp_path).resolve().as_uri())
    print(f"Markdown 预览已打开: {temp_path}")

def preview_html(path):
    """直接打开 HTML 文件"""
    full_path = Path(path).resolve()
    webbrowser.open(full_path.as_uri())

def preview_file(path):
    """统一入口：根据后缀自动选择处理方式"""
    ext = Path(path).suffix.lower()
    if ext in ['.md', '.markdown']:
        preview_markdown(path)
    elif ext in ['.html', '.htm']:
        preview_html(path)
    else:
        raise ValueError("暂不支持该文件格式的预览")