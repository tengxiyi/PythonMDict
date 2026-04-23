# file: src/ui/widgets/clipboard_watcher.py
# -*- coding: utf-8 -*-
"""
剪贴板监听器
自动检测剪贴板文本变化并发射信号（用于划词查词功能）
"""
import re

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from ...core.config import CLIPBOARD_MIN_LEN, CLIPBOARD_MAX_LEN
from ...core.logger import logger


class ClipboardWatcher(QObject):
    """
    剪贴板变化监听器
    
    Signals:
        text_copied(str): 当检测到有效英文单词时发射信号
    """
    text_copied = Signal(str)

    def __init__(self):
        super().__init__()
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.on_clipboard_change)
        self.last_text = ""

    def on_clipboard_change(self):
        """剪贴板内容变化回调"""
        try:
            mime = self.clipboard.mimeData()
            if not mime.hasText():
                return
            
            text = mime.text().strip()
            
            # 长度过滤
            if len(text) > CLIPBOARD_MAX_LEN or len(text) < CLIPBOARD_MIN_LEN:
                return
            
            # 仅匹配纯英文单词
            if not re.match(r'^[a-zA-Z\s\-\']+$', text):
                return
            
            # 防止重复触发
            if text == self.last_text:
                return
            
            self.last_text = text
            self.text_copied.emit(text)
            
        except Exception as e:
            logger.debug(f"剪贴板监听异常: {e}")
