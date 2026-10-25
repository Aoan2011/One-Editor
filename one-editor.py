# MIT License
# Copyright (c) 2026 Aoan2011
"""CLI 入口。真正的实现见 one_editor.py。"""
import sys
from one_editor import OneEditor

if __name__ == "__main__":
    app = OneEditor()
    app._initial_files = sys.argv[1:]
    app.run()