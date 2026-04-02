#!/usr/bin/env python3
"""Run game: python3 run.py  （界面在弹出的窗口里，终端一般只有启动信息）"""

import os

# 去掉 pygame 导入时打印的版本与 "Hello from the pygame community"
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from sbs.app import run

if __name__ == "__main__":
    run()
