# file: src/ui/handlers/web_pages.py
# -*- coding: utf-8 -*-
"""
WebEngine页面导航拦截处理器
实现 entry:// 协议查词、internal:// 内部命令、音频播放拦截等功能
"""
import urllib.parse

from PySide6.QtCore import Signal, QUrl, QTimer, QUrlQuery
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage

from ..handlers.mdict_handler import play_audio_from_mdict
from ...core.logger import logger


class DictWebPage(QWebEnginePage):
    """
    词典页面导航拦截器
    
    功能:
    - entry://query/{word}?context={text} -> 触发查词信号
    - internal://import -> 导航到词典导入页
    - internal://play?src={url} -> 播放音频
    - http(s) 外部链接 -> 用系统浏览器打开
    - 音频文件(.mp3/.wav/.ogg/.spx) -> 阻止默认行为
    
    Signals:
        word_lookup_requested(str, str): (单词, 上下文) 查词请求
        import_requested(): 用户点击了导入按钮
    """
    
    word_lookup_requested = Signal(str, str)
    import_requested = Signal()

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        """将 QWebEngine JS 控制台输出转发到 Python 日志"""
        prefix = f"[JS:{lineNumber}]"
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
            logger.info(f"{prefix} {message}")
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            logger.warning(f"{prefix} {message}")
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            logger.error(f"{prefix} {message}")
        else:
            logger.debug(f"{prefix} {message}")

    def createWindow(self, _type):
        """拦截 target="_blank" 在当前窗口打开"""
        return self

    def acceptNavigationRequest(self, url: QUrl, _type, isMainFrame):
        u = url.toString()
        scheme = url.scheme()

        # 放行JS交互和锚点
        if scheme == "javascript":
            return True
        if "#" in u and scheme not in ["http", "https", "entry"]:
            return True

        # 拦截导入操作
        if u == "internal://import":
            self.import_requested.emit()
            return False

        # 音频播放拦截
        if u.startswith("internal://play"):
            try:
                q = QUrlQuery(url)
                src = q.queryItemValue("src")
                if src:
                    play_audio_from_mdict(src)
            except Exception as e:
                logger.debug(f"音频播放失败: {e}")
            return False

        # 直接阻止音频文件导航
        if u.lower().endswith(('.mp3', '.wav', '.ogg', '.spx')):
            return False

        # 查词请求 (entry 协议)
        if scheme == "entry":
            if "query/" in u:
                try:
                    parts = u.split("query/", 1)[1].split("?")
                    w = urllib.parse.unquote(parts[0])
                    c = ""
                    if len(parts) > 1:
                        q = QUrlQuery("?" + parts[1])
                        c = q.queryItemValue("context")
                    if w:
                        self.word_lookup_requested.emit(w, c)
                except Exception as e:
                    logger.debug(f"entry协议解析失败: {e}")
            return False

        # 外部链接用系统浏览器打开
        if scheme in ["http", "https"]:
            QDesktopServices.openUrl(url)
            return False

        return True


class NewsWebPage(QWebEnginePage):
    """
    新闻阅读页面导航拦截器
    
    功能:
    - entry:// 双击查词
    - internal://back 返回新闻列表
    - http(s) 新闻链接点击后进入阅读模式
    
    Signals:
        news_clicked(str): 点击的新闻URL或"internal://back"
        word_lookup_requested(str, str): (单词, 上下文) 查词请求
    """
    
    news_clicked = Signal(str)
    word_lookup_requested = Signal(str, str)

    def acceptNavigationRequest(self, url: QUrl, _type, isMainFrame):
        u = url.toString()

        # 双击查词 (entry:// 协议)
        if url.scheme() == "entry":
            if "query/" in u:
                parts = u.split("query/", 1)[1].split("?")
                w = urllib.parse.unquote(parts[0])
                c = ""
                if len(parts) > 1:
                    q = QUrlQuery("?" + parts[1])
                    c = q.queryItemValue("context")
                if w:
                    self.word_lookup_requested.emit(w, c)
            return False

        # 返回按钮
        if u == "internal://back":
            QTimer.singleShot(10, lambda: self.news_clicked.emit(u))
            return False
        
        # 新闻链接 -> 进入阅读模式
        if url.scheme() in ["http", "https"]:
            QTimer.singleShot(10, lambda: self.news_clicked.emit(u))
            return False
        
        return True
