# file: src/ui/pages/search_page.py
# -*- coding: utf-8 -*-
"""
查词主页面 (SearchSplitPage)
包含搜索框、词条列表、词典/新闻双Tab视图、工具栏等功能
这是应用最核心的页面，承载主要的用户交互逻辑
"""
import os
import re
import sqlite3
import time
import urllib.parse
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QStackedWidget, QFrame, QSplitter, QAbstractItemView,
    QToolButton, QTabWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QPoint, Signal, QSize, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPalette, QKeySequence, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineUrlScheme

from ...core.config import DB_FILE, EBBINGHAUS_INTERVALS
from ...core.search_worker import SearchWorker
from ...core.news_workers import NewsWorker, NewsContentWorker
from ...core.logger import logger

from ..theme_manager import theme_manager
from ..widgets.sidebar import create_svg_icon
from ..widgets.floating_text import FloatingText
from ..handlers.mdict_handler import (
    MdictSchemeHandler, IFRAME_HTML_CACHE, IFRAME_HTML_LOCK
)
from ..handlers.web_pages import DictWebPage, NewsWebPage


class SearchSplitPage(QWidget):
    """
    查词主页面
    
    布局:
    - 左侧面板: 工具栏 + 搜索框 + 搜索历史列表
    - 右侧Tab: 词典Web视图 / 新闻聚合Web视图
    """
    
    vocab_changed = Signal()  # 单词收藏/取消收藏时发射，通知单词本刷新
    history_updated = Signal()  # 查词后发射，通知查词历史页面刷新

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.last_dict_result = None
        self.last_loaded_news_query = ""

        # 工具栏图标SVG路径数据
        self.tool_icons = {
            'pin': r"M16,12V4H17V2H7V4H8V12L6,14V16H11.2V22H12.8V16H18V14L16,12Z",
            'monitor': r"M19,3H14.82C14.4,1.84 13.3,1 12,1C10.7,1 9.6,1.84 9.18,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M12,3A1,1 0 0,1 13,3A1,1 0 0,1 12,4A1,1 0 0,1 11,3A1,1 0 0,1 12,3M7,7H17V5H19V19H5V5H7V7Z",
            'star_off': r"M12,15.39L8.24,17.66L9.23,13.38L5.91,10.5L10.29,10.13L12,6.09L13.71,10.13L18.09,10.5L14.77,13.38L15.76,17.66M22,9.24L14.81,8.63L12,2L9.19,8.63L2,9.24L7.45,13.97L5.82,21L12,17.27L18.18,21L16.54,13.97L22,9.24Z",
            'star_on': r"M12,17.27L18.18,21L16.54,13.97L22,9.24L14.81,8.62L12,2L9.19,8.62L2,9.24L7.45,13.97L5.82,21L12,17.27Z"
        }

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # === 左侧面板 ===
        self.left_widget = QWidget()
        v_left = QVBoxLayout(self.left_widget)
        v_left.setContentsMargins(0, 0, 0, 0)
        v_left.setSpacing(0)
        self.left_widget.setStyleSheet(f"background-color: {theme_manager.colors.get('sidebar', '#f0f0f0') if theme_manager else '#f0f0f0'};")

        self.top_container = QFrame()
        v_top = QVBoxLayout(self.top_container)

        h_tools = QHBoxLayout()

        self.btn_pin = QPushButton()
        self.btn_pin.setCheckable(True)
        self.btn_pin.setFixedSize(36, 36)
        self.btn_pin.setIconSize(QSize(22, 22))
        self.btn_pin.setToolTip("窗口置顶")
        self.btn_pin.clicked.connect(self.main.toggle_always_on_top)

        self.btn_monitor = QPushButton()
        self.btn_monitor.setCheckable(True)
        self.btn_monitor.setFixedSize(36, 36)
        self.btn_monitor.setIconSize(QSize(20, 20))
        self.btn_monitor.setToolTip("剪贴板监听")

        self.btn_fav = QPushButton()
        self.btn_fav.setFixedSize(36, 36)
        self.btn_fav.setIconSize(QSize(24, 24))
        self.btn_fav.setToolTip("收藏单词")
        self.btn_fav.clicked.connect(self.toggle_fav)

        h_tools.addWidget(self.btn_pin)
        h_tools.addWidget(self.btn_monitor)
        h_tools.addStretch()
        h_tools.addWidget(self.btn_fav)

        self.entry = QLineEdit()
        self.entry.setObjectName("MainSearchEntry")
        self.entry.setPlaceholderText("Search...")
        self.entry.setFixedHeight(38)
        self.entry.returnPressed.connect(self.on_enter_pressed)

        v_top.addLayout(h_tools)
        v_top.addWidget(self.entry)

        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.itemClicked.connect(lambda i: self.do_search(i.text(), from_list=True))

        v_left.addWidget(self.top_container)
        v_left.addWidget(self.list_widget)

        # === 右侧 Tab ===
        self.right_tabs = QTabWidget()
        self.right_tabs.currentChanged.connect(self.on_tab_changed)

        # 词典 Web 视图
        self.web_dict = QWebEngineView()
        self.page_dict = DictWebPage(self.web_dict)
        self.page_dict.word_lookup_requested.connect(
            lambda w, c: self.do_search(w, context=c)
        )
        self.page_dict.import_requested.connect(lambda: self.main.switch_page(3))
        self.web_dict.setPage(self.page_dict)

        # 新闻 Web 视图
        self.web_news = QWebEngineView()
        self.page_news = NewsWebPage(self.web_news)
        self.page_news.news_clicked.connect(self.handle_news_click)
        self.page_news.word_lookup_requested.connect(self.on_news_lookup)
        self.web_news.setPage(self.page_news)

        self.right_tabs.addTab(self.web_dict, "词典")
        self.right_tabs.addTab(self.web_news, "新闻")
        
        # 新闻Tab切换时自动加载新闻
        self.right_tabs.currentChanged.connect(self._on_right_tab_changed)

        splitter.addWidget(self.left_widget)
        splitter.addWidget(self.right_tabs)
        splitter.setSizes([220, 880])
        splitter.setCollapsible(0, False)

        layout.addWidget(splitter)

        # 注册并安装 mdict:// 协议处理器
        # 注意：registerScheme 已在 main_new.py 中提前完成（必须在QWebEngineView创建之前）
        self.handler = MdictSchemeHandler()
        self.web_dict.page().profile().installUrlSchemeHandler(b"mdict", self.handler)

        self.vocab_cache = set()
        self.load_vocab_cache()
        self.current_context = ""
        self.current_source = ""
        self.is_in_reader_mode = False
        self.last_news_data = []
        self.current_news_query = ""

        self.refresh_icons()
        self.init_shortcuts()
        self.render_welcome_page()  # 初始显示欢迎页

    # ========== 辅助方法 ==========

    def get_random_word(self) -> dict | None:
        """从数据库随机获取一个单词（用于每日一词）"""
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.execute("SELECT count(*) FROM dict_info")
                if cursor.fetchone()[0] == 0:
                    return None
                
                cursor = conn.execute(
                    "SELECT word, content, dict_id FROM standard_entries ORDER BY RANDOM() LIMIT 1"
                )
                row = cursor.fetchone()
                if row:
                    return {"word": row[0], "content": row[1], "dict_id": row[2]}
        except Exception as e:
            logger.debug(f"获取随机单词失败: {e}")
        return None

    def render_welcome_page(self):
        """渲染欢迎页面（每日一词 + 快捷键提示）"""
        # 防御性获取theme_manager
        try:
            from ..theme_manager import theme_manager as _tm
            if not _tm:
                return
            c = _tm.colors
            css = _tm.get_webview_css()
        except Exception as e:
            logger.debug(f"渲染欢迎页获取主题失败: {e}")
            return

        # 时间问候
        hour = datetime.now().hour
        if 5 <= hour < 12:
            greeting = "Good Morning"
        elif 12 <= hour < 18:
            greeting = "Good Afternoon"
        else:
            greeting = "Good Evening"

        wotd_data = self.get_random_word()

        if not wotd_data:
            center_content = f"""
                <div class="empty-state">
                    <div class="icon">📚</div>
                    <h2>欢迎使用 GeekDict Pro</h2>
                    <p>您还没有导入任何 MDX 词典文件。</p>
                    <button onclick="location.href='internal://import'">立即导入词典</button>
                </div>
            """
        else:
            center_content = f"""
                <div class="wotd-card" 
                     onclick="location.href='entry://query/{urllib.parse.quote(wotd_data['word'])}'">
                    <div class="label">每日一词</div>
                    <div class="word">{wotd_data['word']}</div>
                    <div class="tip">点击获取更多信息 ➔</div>
                </div>
            """

        html = f"""
        <html>
        <head>
            <style>{css}
                body {{
                    background-color: {c['bg']};
                    display: flex; flex-direction: column; align-items: center;
                    justify-content: center; height: 95vh; margin: 0;
                    user-select: none;
                }}
                h1 {{ font-size: 2.5em; color: {c['text']}; margin-bottom: 10px; font-weight: 300; }}
                .subtitle {{ color: {c['meta']}; margin-bottom: 40px; font-size: 1.1em; }}
                .wotd-card {{
                    background: {c['card']}; border: 1px solid {c['border']};
                    border-radius: 16px; padding: 30px 50px;
                    text-align: center; cursor: pointer;
                    transition: transform 0.2s, box-shadow 0.2s;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.05);
                    min-width: 300px;
                }}
                .wotd-card:hover {{
                    transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0,0,0,0.1);
                    border-color: {c['primary']};
                }}
                .wotd-card .label {{ color: {c['primary']}; font-weight: bold; 
                                      letter-spacing: 1px; font-size: 0.8em; text-transform: uppercase; margin-bottom: 10px; }}
                .wotd-card .word {{ font-size: 2.5em; font-weight: bold; color: {c['text']}; margin: 10px 0; }}
                .wotd-card .tip {{ color: {c['meta']}; font-size: 0.9em; }}
                .shortcuts {{ margin-top: 50px; display: flex; gap: 20px; }}
                .key-item {{ display: flex; align-items: center; gap: 8px; color: {c['meta']}; font-size: 0.9em; }}
                .key {{ background: {c['card']}; border: 1px solid {c['border']};
                       padding: 4px 8px; border-radius: 6px; font-family: monospace;
                       font-weight: bold; box-shadow: 0 2px 0 {c['border']}; }}
                .empty-state {{ text-align: center; }}
                .empty-state .icon {{ font-size: 60px; margin-bottom: 20px; }}
                button {{ background: {c['primary']}; color: white; border: none; padding: 10px 20px; 
                         border-radius: 20px; font-size: 16px; cursor: pointer; margin-top: 20px; }}
                button:hover {{ opacity: 0.9; }}
            </style>
        </head>
        <body>
            <h1>{greeting}, Learner.</h1>
            <div class="subtitle">准备好拓展你的词汇了吗?</div>
            {center_content}
            <div class="shortcuts">
                <div class="key-item"><span class="key">Ctrl</span> + <span class="key">L</span> 聚焦搜索框</div>
                <div class="key-item"><span class="key">Enter</span> 搜索</div>
                <div class="key-item"><span class="key">Esc</span> 清除搜索框</div>
            </div>
            <script>
                document.body.style.opacity = 0;
                window.onload = function() {{ document.body.style.transition = 'opacity 0.5s'; document.body.style.opacity = 1; }};
            </script>
        </body></html>
        """

        self.web_dict.setHtml(html, baseUrl=QUrl("mdict://root/"))

    def refresh_icons(self):
        """刷新工具栏图标颜色"""
        from ..theme_manager import theme_manager as _tm
        if not _tm:
            return
        c = _tm.colors['meta']
        self.btn_pin.setIcon(create_svg_icon(self.tool_icons['pin'], c))
        self.btn_monitor.setIcon(create_svg_icon(self.tool_icons['monitor'], c))
        self.check_fav(self.entry.text())

    def init_shortcuts(self):
        """初始化快捷键"""
        self.shortcut_esc = QShortcut(QKeySequence("Esc"), self)
        self.shortcut_esc.activated.connect(self.on_esc_pressed)
        
        self.shortcut_focus = QShortcut(QKeySequence("Ctrl+L"), self)
        self.shortcut_focus.activated.connect(
            lambda: (self.entry.setFocus(), self.entry.selectAll())
        )
        
        self.shortcut_focus2 = QShortcut(QKeySequence("Alt+D"), self)
        self.shortcut_focus2.activated.connect(
            lambda: (self.entry.setFocus(), self.entry.selectAll())
        )

    def on_esc_pressed(self):
        """ESC清除搜索框"""
        self.entry.clear()
        self.entry.setFocus()

    def on_enter_pressed(self):
        """回车触发搜索"""
        self.do_search(self.entry.text(), update_news=True)

    def load_vocab_cache(self):
        """加载单词本缓存到内存"""
        try:
            with sqlite3.connect(DB_FILE) as conn:
                self.vocab_cache = {r[0] for r in conn.execute("SELECT word FROM vocabulary")}
        except Exception as e:
            logger.debug(f"加载单词本缓存失败: {e}")

    def highlight_text(self, text: str, keyword: str) -> str:
        """纯文本关键词高亮"""
        if not keyword or not text:
            return text
        
        pattern = re.compile(f"({re.escape(keyword)})", re.IGNORECASE)
        hl_style = (
            "background-color: #ffeb3b !important; "
            "color: #000000 !important; "
            "border-radius: 2px; padding: 0 2px;"
        )
        return pattern.sub(f"<span style='{hl_style}'>\\1</span>", text)

    def highlight_html_safe(self, html_content: str, keyword: str) -> str:
        """HTML安全的关键词高亮（不破坏标签结构）"""
        if not keyword or not html_content:
            return html_content

        hl_style = (
            "background-color: #ffeb3b !important; "
            "color: #000000 !important; "
            "border-radius: 2px; padding: 0 2px; "
            "box-shadow: 0 1px 1px rgba(0,0,0,0.1);"
        )

        tokens = re.split(r'(<[^>]+>)', html_content)
        processed = []
        kw_pattern = re.compile(f"({re.escape(keyword)})", re.IGNORECASE)

        for token in tokens:
            if token.startswith('<') and token.endswith('>'):
                processed.append(token)
            else:
                if keyword.lower() in token.lower():
                    subbed = kw_pattern.sub(f"<span style='{hl_style}'>\\1</span>", token)
                    processed.append(subbed)
                else:
                    processed.append(token)

        return "".join(processed)

    # ========== 标签页切换 ==========

    def on_tab_changed(self, index: int):
        """Tab切换回调"""
        if index == 1:
            if self.current_news_query and self.current_news_query != self.last_loaded_news_query:
                self.is_in_reader_mode = False
                # 安全终止前一个worker
                if hasattr(self, 'news_worker') and self.news_worker is not None:
                    try:
                        self.news_worker.quit()
                        self.news_worker.wait(1000)
                    except Exception:
                        pass
                    self.news_worker = None
                self.web_news.setHtml("<h3>Loading News...</h3>")
                self.news_worker = NewsWorker(self.current_news_query)
                self.news_worker.news_ready.connect(self.render_news)
                self._worker_ref = self.news_worker
                def _cleanup():
                    self._worker_ref = None
                self.news_worker.finished.connect(_cleanup)
                self.news_worker.start()

    def on_news_lookup(self, word: str, context: str):
        """新闻页面触发的查词请求"""
        self.is_in_reader_mode = False  # 退出阅读模式
        self.right_tabs.setCurrentIndex(0)
        self.do_search(word, context=context)

    def _on_right_tab_changed(self, index: int):
        """右侧Tab切换回调 - 切换到新闻Tab时自动加载"""
        if index == 1:  # 新闻Tab
            self.is_in_reader_mode = False
            query = self.current_news_query or self.entry.text().strip()
            if not query:
                query = "latest"

            # 安全终止可能仍在运行的前一个worker
            if hasattr(self, 'news_worker') and self.news_worker is not None:
                try:
                    self.news_worker.quit()
                    self.news_worker.wait(1000)
                except Exception:
                    pass
                self.news_worker = None

            self.web_news.setHtml("<h3>正在加载新闻...</h3>")
            self.news_worker = NewsWorker(query)
            self.news_worker.news_ready.connect(self.render_news)
            self._worker_ref = self.news_worker
            def _cleanup():
                self._worker_ref = None
            self.news_worker.finished.connect(_cleanup)
            self.news_worker.start()

    # ========== 搜索核心方法 ==========

    def do_search(
        self, text: str, push: bool = True, update_news: bool = False,
        context: str = "", from_list: bool = False
    ):
        """
        执行查词操作
        
        Args:
            text: 要查询的文本
            push: 是否加入搜索历史列表
            update_news: 是否同步更新新闻Tab
            context: 来源上下文
            from_list: 是否从历史列表点击触发
        """
        text = text.strip()
        if not text:
            return

        self.entry.setText(text)
        self.check_fav(text)
        self.current_context = context
        self.current_source = "News" if context else "Dict"
        self.current_news_query = text

        # 更新搜索历史列表
        if not from_list:
            if self.list_widget.count() > 0 and self.list_widget.item(0).text() == text:
                pass
            else:
                items = self.list_widget.findItems(text, Qt.MatchExactly)
                if items:
                    self.list_widget.takeItem(self.list_widget.row(items[0]))
                self.list_widget.insertItem(0, text)
            self.list_widget.setCurrentRow(0)

        # 写入搜索历史数据库
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    "INSERT INTO search_history (word, last_access_time, search_count) "
                    "VALUES (?, ?, 1) ON CONFLICT(word) DO UPDATE SET last_access_time=excluded.last_access_time",
                    (text, time.time())
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"写入搜索历史失败: {e}")

        # 通知查词历史页面刷新
        self.history_updated.emit()

        # 安全终止可能仍在运行的前一个搜索worker
        if hasattr(self, 'search_worker') and self.search_worker is not None:
            try:
                self.search_worker.quit()
                self.search_worker.wait(1000)
            except Exception:
                pass
            self.search_worker = None

        # 启动搜索线程（带生命周期管理）
        self.worker = SearchWorker(text)
        self.search_worker = self.worker  # 持有引用防止GC
        self.worker.results_ready.connect(self.render_dict)

        def _cleanup_search():
            self.search_worker = None
        self.worker.finished.connect(_cleanup_search)
        self.worker.start()

        is_news_tab_active = (self.right_tabs.currentIndex() == 1)

        if update_news or is_news_tab_active:
            if is_news_tab_active:
                self.is_in_reader_mode = False
                self.web_news.setHtml("<h3>Loading News...</h3>")
            else:
                self.right_tabs.setCurrentIndex(0)

            # 安全终止前一个worker
            if hasattr(self, 'news_worker') and self.news_worker is not None:
                try:
                    self.news_worker.quit()
                    self.news_worker.wait(1000)
                except Exception:
                    pass
                self.news_worker = None

            self.news_worker = NewsWorker(text)
            self.news_worker.news_ready.connect(self.render_news)
            self._worker_ref = self.news_worker
            def _cleanup():
                self._worker_ref = None
            self.news_worker.finished.connect(_cleanup)
            self.news_worker.start()

    def render_dict(self, q: str, rows: list, suggestions: list):
        """
        渲染词典搜索结果到 Web 视图
        这是整个项目最复杂的渲染函数，生成完整的HTML页面
        """

        # 运行时重新获取 theme_manager（解决模块级 import 绑定时值为 None 的问题）
        # 防御性处理：如果theme_manager不可用，使用默认配色确保不白屏
        try:
            from ..theme_manager import theme_manager as _tm
            if _tm:
                c = _tm.colors
                css = _tm.get_webview_css() if hasattr(_tm, 'get_webview_css') else ""
            else:
                logger.warning("[render_dict] theme_manager为None，使用默认配色")
                c = {
                    'bg': '#ffffff', 'card': '#ffffff', 'text': '#333333',
                    'primary': '#2196F3', 'border': '#E0E0E0', 'hover': '#F5F5F5',
                    'meta': '#666666', 'sidebar': '#F5F7FA'
                }
                css = ""
        except Exception as e:
            logger.error(f"[render_dict] 获取主题失败，使用默认配色: {e}")
            c = {
                'bg': '#ffffff', 'card': '#ffffff', 'text': '#333333',
                'primary': '#2196F3', 'border': '#E0E0E0', 'hover': '#F5F5F5',
                'meta': '#666666', 'sidebar': '#F5F7FA'
            }
            css = ""

        rows_list = list(rows) if rows else []
        self.last_dict_result = (q, rows_list, suggestions)

        # 判断是否需要高亮
        need_highlight = False
        if q:
            is_zh = any('\u4e00' <= char <= '\u9fff' for char in q)
            if is_zh or len(q) > 1:
                need_highlight = True

        # 无结果处理
        if not rows_list:
            sugg_html = ""
            if suggestions:
                links = [
                    f"<a href='entry://query/{urllib.parse.quote(s)}' "
                    f"style='margin:5px;display:inline-block;padding:5px;background:#eee;border-radius:4px;'>{s}</a>"
                    for s in suggestions
                ]
                sugg_html = (
                    f"<div style='text-align:center;margin-top:20px'>"
                    f"Did you mean:<br>{''.join(links)}</div>"
                )

            html_content = (
                f"<html><head><style>{css}</style></head>"
                f"<body><h3 style='text-align:center;color:#888;margin-top:50px'>"
                f"Not found: {q}</h3>{sugg_html}</body></html>"
            )
            self.web_dict.setHtml(html_content)
            return

        # ===== 构建HTML内容 =====

        action_js = """
            <script>
                (function(){
                    try {
                        if (!window.googletag) window.googletag = { cmd: [] };
                        if (!window.googletag.cmd) window.googletag.cmd = [];
                        if (typeof window.googletag.cmd.push !== 'function') {
                            window.googletag.cmd.push = function(fn){ 
                                try { if (typeof fn === 'function') fn(); } catch(e) {} 
                            };
                        }
                    } catch(e) {}
                })();

                function speak(t) {
                    try {
                        window.speechSynthesis.cancel();
                        var m = new SpeechSynthesisUtterance(t);
                        m.lang = 'en-US';
                        window.speechSynthesis.speak(m);
                    } catch (e) { console.log('speak failed', e); }
                }

                function copyText(btn, t) {
                    try {
                        const el = document.createElement('textarea');
                        el.value = t; document.body.appendChild(el);
                        el.select(); document.execCommand('copy');
                        document.body.removeChild(el);
                        if (btn) {
                            var original = btn.innerText;
                            btn.innerText = "✅ Copied";
                            setTimeout(function () { btn.innerText = original; }, 1500);
                        }
                    } catch (e) { console.log('copy failed', e); }
                }
            </script>
        """

        # 词典内容交互JS（点击拦截）
        js = """
            <script>
                // 双击查词
                document.addEventListener('dblclick', function(e){ 
                    var s = window.getSelection().toString().trim(); 
                    if(s) window.location.href = 'entry://query/' + encodeURIComponent(s); 
                });

                // 点击拦截器
                document.addEventListener('click', function(e){ 
                    var t = e.target.closest('a'); 
                    if (t) { 
                        try { if (t.closest('.action-bar')) return; } catch(ex) {}
                        var href = t.getAttribute('href'); 
                        if (!href) return;

                        if (href.startsWith('#') || href.startsWith('javascript:')) return;

                        // 音频拦截
                        var lower = href.toLowerCase(); 
                        if (lower.endsWith('.mp3') || lower.endsWith('.wav') || 
                            lower.endsWith('.spx') || lower.endsWith('.ogg')) { 
                            e.stopPropagation(); e.preventDefault();

                            var card = t.closest('.card');
                            var dictId = (window.__dictId || 
                                (card ? card.getAttribute('data-dict-id') : '1'));

                            var cleaned = href;
                            try {
                                var lowHref = (cleaned || '').toLowerCase();
                                if (lowHref.startsWith('sound://')) cleaned = cleaned.substring(8);
                                else if (lowHref.startsWith('sound:')) cleaned = cleaned.substring(6);
                            } catch(e) {}

                            try {
                                var lowClean = (cleaned || '').toLowerCase();
                                if (lowClean.startsWith('mdict://0.0.0.') || lowClean.startsWith('mdict://root/')) {
                                    var tmp = cleaned;
                                    try { if ((tmp || '').toLowerCase().startsWith('mdict://')) tmp = tmp.substring(8); } catch(e){}
                                    if (tmp.indexOf('/') > -1) tmp = tmp.substring(tmp.indexOf('/') + 1);
                                    cleaned = tmp;
                                }
                            } catch(e) {}

                            var filename = (cleaned || '').replace('mdict://', '').replace('entry://', ''); 
                            if (filename.indexOf('/') === -1) filename = dictId + '/' + filename;
                            else {
                                try {
                                    var lowFn = (filename || '').toLowerCase();
                                    if (lowFn.startsWith('0.0.0.') || lowFn.startsWith('root/'))
                                        filename = dictId + '/' + filename.substring(filename.indexOf('/') + 1);
                                } catch(e) {}
                            }

                            var playUrl = 'mdict://' + filename;
                            var playViaInternal = function() {
                                window.location.href = 'internal://play?src=' + encodeURIComponent(playUrl);
                            };
                            if (playUrl.toLowerCase().endsWith('.spx')) { playViaInternal(); return false; }
                            try {
                                var a = new Audio(playUrl);
                                var p = a.play();
                                if (p && p.catch) p.catch(function() { playViaInternal(); });
                            } catch (err) { playViaInternal(); }
                            return false; 
                        } 

                        // 资源文件白名单
                        var isResource = false;
                        var resExts = ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.ttf', '.woff'];
                        var cleanPath = href.split('?')[0].split('#')[0].toLowerCase();
                        for (var i = 0; i < resExts.length; i++) {
                            if (cleanPath.endsWith(resExts[i])) { isResource = true; break; }
                        }
                        if (cleanPath.indexOf('css/') > -1 || cleanPath.indexOf('theme/') > -1) isResource = true;

                        if (!isResource) {
                            e.stopPropagation(); e.preventDefault(); 
                            var word = href;
                            if (word.indexOf('://') > -1) {
                                var parts = word.split('://');
                                var payload = parts[1]; 
                                if (payload.indexOf('/') > -1) word = payload.substring(payload.lastIndexOf('/') + 1);
                                else word = payload;
                            }
                            try { word = decodeURIComponent(word); } catch(e) {}
                            word = word.split('#')[0];
                            if (word && word.trim() !== "") {
                                window.location.href = 'entry://query/' + encodeURIComponent(word);
                            }
                            return false;
                        }
                    } 
                }, true); 
            </script>
        """

        safe_q = q.replace("'", "\\'")

        # 操作栏CSS+HTML
        actions = f"""
            <style>.action-bar {{padding: 10px 0; margin-bottom: 15px;display:flex;gap:10px;border-bottom:1px solid var(--border);}}
            .action-btn {{background-color:var(--bg);border:1px solid var(--border);color:var(--text);padding:8px 16px;border-radius:20px;font-size:13px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px;transition:all 0.2s ease;box-shadow:0 1px 2px rgba(0,0,0,0.05);}}
            .action-btn:hover {{background-color:var(--hover);border-color:{c['primary']};color:{c['primary']};transform:translateY(-1px);box-shadow:0 3px 6px rgba(0,0,0,0.1);}}
            .action-btn:active {{transform:translateY(0);}}</style>
            <div class="action-bar">
                <button class="action-btn" onclick="speak('{safe_q}')">&#128266; Speak</button>
                <button class="action-btn" onclick="copyText(this, '{safe_q}')">&#128203; Copy</button>
                <a class="action-btn" href="https://www.google.com/search?tbm=isch&q={safe_q}">&#128444; Images</a>
                <a class="action-btn btn-google" href="https://www.google.com/search?q={safe_q}">&#127760; Google</a>
                <a class="action-btn" href="https://en.wikipedia.org/wiki/{safe_q}">&#128214; Wiki</a>
            </div>
        """

        unique_dict_ids = set()
        for r in rows_list:
            if 'dict_id' in r:
                unique_dict_ids.add(r['dict_id'])

        iframe_mode = len(unique_dict_ids) > 1
        if iframe_mode:
            with IFRAME_HTML_LOCK:
                IFRAME_HTML_CACHE.clear()

        css_links = []
        js_links = []
        if not iframe_mode:
            for did in unique_dict_ids:
                # 加载词典自带CSS（如OALDPE的按钮样式）
                css_links.append(f'<link rel="stylesheet" type="text/css" href="mdict://css/{did}">')
                # 加载jQuery依赖（如OALDPE的oaldpe-jquery.js）
                js_links.append(f'<script src="mdict://css/{did}/__jquery.js" onerror="this.remove()"><\/script>')
                # 加载词典自带JS（如OALDPE的设置按钮交互脚本）
                js_links.append(f'<script src="mdict://css/{did}/__script.js" onerror="this.remove()"><\/script>')
        css_links_html = "\n".join(css_links)
        js_links_html = "\n".join(js_links)

        iframe_css = ""
        iframe_resize_js = ""
        if iframe_mode:
            iframe_css = ".entry-frame{width:100%;border:0;display:block;overflow:visible!important;}"
            iframe_resize_js = """
                <script>window.addEventListener('message',function(e){
                    var d=e.data||{};if(d.type!=='frame-height')return;
                    var f=document.getElementById(d.id);if(f)f.style.height=d.h+'px';
                });</script>
            """

        # OALDPE等词典的兼容性脚本：确保非Eudic环境下齿轮按钮能正确注入
        oaldpe_compat_js = """
        <script>
        (function(){
          // 等待词典JS初始化完成（oaldpeInit对象创建后执行）
          function tryFixOALDPE() {
            // 检测是否是OALDPE词条
            var oaldpeEl = document.querySelector('.oaldpe');
            if (!oaldpeEl) return;
            
            // 检查齿轮按钮是否已注入
            if (document.querySelector('.oaldpe-config-gear')) return;
            
            // OALDPE JS在非Eudic环境下查找 .idm-g 元素来注入齿轮按钮
            // 但我们的渲染结构中没有 .idm-g，需要添加兼容处理
            if (!document.querySelector('.idm-g')) {
              // 找到 .oald-entry-root 作为目标容器
              var entryRoot = oaldpeEl.querySelector('.oald-entry-root, .entry, #entryContent, [class*="root"]');
              if (entryRoot && !entryRoot.classList.contains('idm-g')) {
                entryRoot.classList.add('idm-g');
                console.log('[OALDPE compat] Added .idm-g class for gear button injection');
              }
              
              // 如果还没找到，给第一个直接子元素加
              if (!document.querySelector('.idm-g')) {
                var firstChild = oaldpeEl.firstElementChild;
                while (firstChild && firstChild.nodeType === 3) firstChild = firstChild.nextSibling;
                if (firstChild) {
                  firstChild.classList.add('idm-g');
                  console.log('[OALDPE compat] Added .idm-g to first child of .oaldpe');
                }
              }
            }
          }
          
          // 多次尝试（JS加载可能有延迟）
          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() { setTimeout(tryFixOALDPE, 300); });
          } else {
            setTimeout(tryFixOALDPE, 300);
          }
          setTimeout(tryFixOALDPE, 1500);
          setTimeout(tryFixOALDPE, 3000);
        })();
        </script>
        """

        def _normalize_entry_content(d_id, html_content):
            if not html_content:
                return html_content
            try:
                html_content = re.sub(
                    r"mdict://0\.0\.0\.\d+/", f"mdict://{d_id}/",
                    html_content, flags=re.IGNORECASE
                )
                html_content = re.sub(r"(?i)sound://", f"mdict://{d_id}/", html_content)
                html_content = re.sub(r"(?i)sound:", f"mdict://{d_id}/", html_content)
            except Exception as e:
                logger.debug(f"链接标准化失败(did={d_id}): {e}")

            # 提取嵌套的<html><body>内容（如OALDPE词条自带完整HTML文档）
            # 避免<html><body>嵌套在我们的页面<body>中导致解析异常
            try:
                outer_match = re.search(
                    r'<html[^>]*>.*?<body[^>]*>(.*?)</body>\s*</html>',
                    html_content, re.IGNORECASE | re.DOTALL
                )
                if outer_match:
                    extracted = outer_match.group(1).strip()
                    # 确认提取的内容有意义（包含实质标签或足够长度）
                    if len(extracted) > 20 and ('<' in extracted):
                        html_content = extracted
                        logger.debug(f"提取嵌套HTML body内容(did={d_id})")
            except Exception as e:
                logger.debug(f"提取嵌套HTML失败(did={d_id}): {e}")

            return html_content

        # 开始构建HTML文档 — 提取CSS到独立变量避免f-string花括号冲突
        primary_color = c.get('primary', '#2196F3')
        dict_card_css = (
            "@font-face{font-family:'Kingsoft Phonetic Plain';src:url('mdict://theme/kingsoft_phonetic.ttf');}"
            + css + iframe_css +
            "body{padding:20px;max-width:900px;margin:0 auto;}"
            # 注意：不设置 img pointer-events:none，否则词典自带按钮(如OALDPE眼镜图标)无法交互
            # entry-content 和 card 必须设 overflow:visible，否则词典自带弹出面板(如设置菜单)会被裁剪
            ".entry-content{overflow:visible!important;position:relative;z-index:1;}"
            ".entry-content img{max-width:100%;height:auto;border:none!important;outline:none!important;}"
            ".card{background:var(--card);padding:25px;margin-bottom:25px;border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid var(--border);position:relative;overflow:visible!important;}"
            ".badge{background:var(--bg);color:var(--primary);border:1px solid var(--primary);padding:3px 8px;border-radius:12px;font-size:12px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;}"
            ".card-header{display:flex;align-items:center;gap:10px;margin-bottom:15px;padding-bottom:10px;border-bottom:1px dashed var(--border);}"
            ".card-word{font-size:18px;font-weight:bold;color:var(--text);flex:1;}"
        )
        html_parts = [f"""<html><head><meta charset='utf-8'>
            <style>{dict_card_css}</style>
            {action_js}{css_links_html}{js_links_html}{oaldpe_compat_js}{'' if iframe_mode else js}{iframe_resize_js}</head><body>"""]

        html_parts.append(actions)

        for idx, r in enumerate(rows_list):
            d_id = r.get('dict_id', 1)
            content = r['content']
            content = _normalize_entry_content(d_id, content)

            if need_highlight:
                content = self.highlight_html_safe(content, q)

            entry_body = f"<div class='entry-content' data-dict-id='{d_id}'>{content}</div>"

            if iframe_mode:
                frame_id = f"frame-{d_id}-{idx}"
                frame_token = f"{d_id}-{idx}-{int(time.time() * 1000)}"
                
                entry_html = f"""<html><head><meta charset='utf-8'><base href=\"mdict://{d_id}/\">
                    <style>@font-face{{font-family:'Kingsoft Phonetic Plain';src:url('mdict://theme/kingsoft_phonetic.ttf');}}{css}html,body{{margin:0;padding:0;background:transparent;overflow:visible!important;}}img{{max-width:100%;height:auto;border:none!important;outline:none!important;}}</style>
                    <link rel=\"stylesheet\" type=\"text/css\" href=\"mdict://css/{d_id}/__style.css\"><script src=\"mdict://css/{d_id}/__jquery.js\" onerror=\"this.remove()\"><\/script><script src=\"mdict://css/{d_id}/__script.js\" onerror=\"this.remove()\"><\/script>{oaldpe_compat_js}<script>window.__dictId='{d_id}';</script>
                    <script>(function(){{try{{if(!window.googletag)window.googletag={{cmd:[]}};if(!window.googletag.cmd)window.googletag.cmd=[];if(typeof window.googletag.cmd.push!=='function'){{window.googletag.cmd.push=function(fn){{try{{if(typeof fn==='function')fn();}}catch(e){{}}}};}}}}catch(e){{}})();</script>
                    {js}<script>(function(){{function send(){{var h=Math.max(document.documentElement.scrollHeight,document.body.scrollHeight);window.parent.postMessage({{type:'frame-height',id:'{frame_id}',h:h}},'*');}}var mo=new MutationObserver(function(){{send();}});mo.observe(document.documentElement,{{subtree:true,childList:true,attributes:true,characterData:true}});window.addEventListener('load',send);window.addEventListener('resize',send);setTimeout(send,50);}})();</script></head><body>{content}</body></html>"""
                
                with IFRAME_HTML_LOCK:
                    IFRAME_HTML_CACHE[frame_token] = entry_html.encode('utf-8')
                
                entry_body = (
                    f"<iframe id='{frame_id}' class='entry-frame' scrolling='no' "
                    f"src='mdict://iframe/{frame_token}'></iframe>"
                )

            html_parts.append(
                f"""<div class='card' data-dict-id='{d_id}'>
                    <div class='card-header'><span class='badge'>{r['dict_name']}</span> <span class='card-word'>{r['word']}</span></div>
                    {entry_body}</div>"""
            )

        html_parts.append("</body></html>")

        base_url = "mdict://root/"
        if (not iframe_mode) and len(unique_dict_ids) == 1:
            try:
                only_id = list(unique_dict_ids)[0]
                base_url = f"mdict://{only_id}/"
            except Exception:
                pass

        final_html = "".join(html_parts)

        self.web_dict.setHtml(final_html, baseUrl=QUrl(base_url))

    def refresh_webview(self):
        """刷新当前Web视图"""
        if self.last_dict_result:
            self.render_dict(*self.last_dict_result)
        else:
            self.render_welcome_page()

    # ========== 新闻相关方法 ==========

    def render_news(self, results: list, query: str):
        """渲染新闻聚合结果（列表模式）"""
        logger.debug(f"[render_news] 收到结果: {len(results)} 条, query='{query}'")
        self.last_loaded_news_query = query
        if self.is_in_reader_mode:
            logger.debug("[render_news] 跳过渲染(阅读模式中)")
            return
        
        self.last_news_data = results
        from ..theme_manager import theme_manager as _tm
        if not _tm:
            logger.warning("[render_news] theme_manager为空，使用默认样式")
            c = {'bg': '#ffffff', 'text': '#333333', 'meta': '#888888',
                 'border': '#e0e0e0', 'card': '#fafafa', 'primary': '#1976D2',
                 'hover': '#e0e0e0'}
            css = ""
        else:
            c = _tm.colors
            css = _tm.get_webview_css()

        is_browse = (not query or query == "latest" or len(query) <= 2)
        title_text = "Latest News" if is_browse else f'News: "{query}"'
        count_text = f"{len(results)} articles"

        items_html = ""
        if not results:
            items_html = """
                <div class='empty-state'>
                    <div style='font-size:48px;margin-bottom:12px;'>📰</div>
                    <h3>No news found</h3>
                    <p>Try a different keyword, or check your RSS sources in Settings.</p>
                </div>
            """
        else:
            for r in results:
                t_escaped = r['title'].replace("'", "\\'")
                b_text = r.get('body', '')
                src = r.get('source', '')
                date = r.get('date', '')

                # 高亮（搜索模式下）
                if not is_browse and query:
                    t_display = self.highlight_text(r['title'], query)
                    b_display = self.highlight_text(b_text[:200], query)
                else:
                    t_display = r['title']
                    b_display = b_text[:200] + ("..." if len(b_text) > 200 else "")

                # 来源标签颜色
                tag_colors = {
                    'BBC': '#b71c1c', 'Reuters': '#e65100', 'NPR': '#1565c0',
                    'TechCrunch': '#2e7d32', 'Ars Technica': '#6a1b9a',
                    'Hacker News': '#ff6f00', 'China Daily': '#00838f',
                    'VOA': '#c62828', 'Engoo': '#455a64',
                }
                tag_color = next((v for k, v in tag_colors.items() if k.lower() in src.lower()), c['primary'])

                items_html += f"""
                <div class='news-card' onclick="window.location.href='{r['url']}'" style="cursor:pointer;">
                    <div class='news-header'>
                        <span class='source-tag' style='background:{tag_color}20;color:{tag_color};'>{src}</span>
                        {f"<span class='date'>{date}</span>" if date else ""}
                    </div>
                    <div class='news-title' style="text-decoration:none;color:{c['text']};font-size:15px;font-weight:600;line-height:1.4;display:block;margin-bottom:6px;">{t_display}</div>
                    <p class='news-snippet'>{b_display}</p>
                    <div class='news-footer'>
                        <span class='read-more'>Click to read &rsaquo;</span>
                    </div>
                </div>"""

        html = f"""
        <html><head><style>{css}
        body {{ padding:16px; font-family:'Segoe UI','Microsoft YaHei',sans-serif; background:{c['bg']}; }}
        .page-header {{
            display:flex;align-items:center;justify-content:space-between;
            margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid {c['border']};
        }}
        .page-title {{ font-size:22px;font-weight:bold;color:{c['text']};margin:0; }}
        .page-count {{ font-size:13px;color:{c['meta']}; }}
        .empty-state {{ text-align:center;padding:60px 20px;color:{c['meta']}; }}
        
        /* 卡片样式 */
        .news-card {{
            padding:14px 16px;margin-bottom:10px;background:{c['card']};
            border-radius:8px;border:1px solid {c['border']};
            transition:box-shadow 0.15s;cursor:pointer;
        }}
        .news-card:hover {{
            box-shadow:0 2px 8px rgba(0,0,0,0.08);border-color:{c['primary']}30;
        }}
        .news-header {{ display:flex;align-items:center;gap:8px;margin-bottom:6px; }}
        .source-tag {{
            display:inline-block;padding:2px 8px;border-radius:4px;
            font-size:11px;font-weight:600;letter-spacing:0.3px;
        }}
        .date {{ font-size:11px;color:{c['meta']}; }}
        .news-title {{
            color:{c['text']};text-decoration:none;font-size:15px;font-weight:600;
            line-height:1.4;display:block;margin-bottom:6px;
        }}
        .news-card:hover .news-title {{ color:{c['primary']}; }}
        .news-snippet {{
            font-size:13px;color:{c['meta']};line-height:1.55;
            margin:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
        }}
        .news-footer {{ margin-top:8px; }}
        .read-more {{ font-size:11px;color:{c['primary']};font-weight:500; }}
        </style></head><body>
        <div class='page-header'>
            <h1 class='page-title'>📰 {title_text}</h1>
            <span class='page-count'>{count_text}</span>
        </div>
        {items_html}
        </body></html>"""
        self.web_news.setHtml(html)

    def handle_news_click(self, url: str):
        """新闻链接点击 -> 进入阅读模式"""
        if url == "internal://back":
            self.is_in_reader_mode = False
            self.render_news(self.last_news_data, self.current_news_query)
            return

        # 安全终止可能仍在运行的前一个内容worker
        if hasattr(self, 'news_content_worker') and self.news_content_worker is not None:
            try:
                self.news_content_worker.quit()
                self.news_content_worker.wait(2000)
            except Exception:
                pass

        self.is_in_reader_mode = True
        self.web_news.setHtml("<h3>Loading Reader Mode...</h3>")
        self.news_content_worker = NewsContentWorker(url)
        self.news_content_worker.content_ready.connect(self.render_reader)
        # 使用独立方法避免lambda闭包的引用混乱
        self._content_worker_ref = self.news_content_worker

        def _cleanup_content():
            self._content_worker_ref = None

        self.news_content_worker.finished.connect(_cleanup_content)
        self.news_content_worker.start()

    def render_reader(self, title: str, body: str, url: str):
        """渲染新闻阅读模式页面（对齐原始main.py逻辑）"""
        from ..theme_manager import theme_manager as _tm
        if not _tm:
            logger.warning("[render_reader] theme_manager为空，使用默认样式")
            c = {'bg': '#ffffff', 'text': '#333333', 'meta': '#888888',
                 'border': '#e0e0e0', 'card': '#fafafa', 'primary': '#1976D2',
                 'hover': '#e0e0e0'}
            css = ""
        else:
            c = _tm.colors
            css = _tm.get_webview_css()

        body_content = body

        # 阅读模式下高亮（仅搜索词时）
        q = self.current_news_query or ""
        if q and len(q) > 2:
            body_content = self.highlight_text(body_content, q)

        js_smart = """
        <script>
        document.addEventListener('dblclick',function(e){
            var s=window.getSelection().toString().trim();
            if(s){var ctx=window.getSelection().anchorNode.parentNode.innerText.substring(0,200);
            window.location.href='entry://query/'+encodeURIComponent(s)+'?context='+encodeURIComponent(ctx);}
        });
        </script>
        """

        html = f"""
        <html><head><style>{css}
        body {{
            max-width:720px; margin:0 auto; padding:24px 20px 60px; padding-top:70px;
            font-family:'Georgia','Noto Serif SC','Source Han Serif CN',serif;
            line-height:1.75; color:{c['text']};
        }}
        h1 {{ font-size:26px; font-family:'Segoe UI',sans-serif; font-weight:700;
             line-height:1.3; color:{c['text']}; margin-bottom:8px; }}
        .article-meta {{
            font-size:13px; color:{c['meta']}; margin-bottom:24px;
            padding-bottom:12px; border-bottom:1px solid {c['border']};
        }}
        .back-btn {{
            position:fixed;top:14px;left:14px;z-index:9999;
            display:inline-flex;align-items:center;gap:6px;
            padding:8px 18px;background:{c['card']};border-radius:20px;
            border:1px solid {c['border']};text-decoration:none;color:{c['text']};
            box-shadow:0 2px 6px rgba(0,0,0,0.06);font-family:'Segoe UI',sans-serif;
            font-size:13px;font-weight:600;cursor:pointer;
            transition:all 0.15s;
        }}
        .back-btn:hover {{ background:{c['hover']}; border-color:{c['primary']}; transform:translateY(-1px); }}
        p {{ font-size:15px; margin:14px 0; text-align:justify; }}
        </style>{js_smart}</head><body>

        <a href='internal://back' class='back-btn'>&#8592; Back to List</a>

        <h1>{title}</h1>
        <div class='article-meta'>
            Source: <a href='{url}' style='color:{c["primary"]};'>{url[:60]}{'...' if len(url)>60 else ''}</a>
        </div>
        <div id='article-body'>{body_content}</div>
        </body></html>"""
        self.web_news.setHtml(html)

    # ========== 收藏功能 ==========

    def check_fav(self, word: str):
        """检查并更新收藏按钮状态"""
        has = word in self.vocab_cache
        from ..theme_manager import theme_manager as _tm_fav
        c = _tm_fav.colors.get('meta', '#888') if _tm_fav else '#888'

        if has:
            icon = create_svg_icon(self.tool_icons['star_on'], "#fbc02d")
        else:
            icon = create_svg_icon(self.tool_icons['star_off'], c)

        self.btn_fav.setIcon(icon)
        self.btn_fav.setProperty("is_fav", has)
        self.btn_fav.style().unpolish(self.btn_fav)
        self.btn_fav.style().polish(self.btn_fav)

    def toggle_fav(self):
        """切换单词收藏状态"""
        w = self.entry.text().strip()
        if not w:
            return
        
        if w in self.vocab_cache:
            self.vocab_cache.remove(w)
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("DELETE FROM vocabulary WHERE word=?", (w,))
        else:
            self.vocab_cache.add(w)
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO vocabulary "
                    "(word, added_time, next_review_time, context, source) VALUES (?,?,?,?,?)",
                    (w, time.time(), time.time(), self.current_context, self.current_source)
                )
        
        self.check_fav(w)
        
        # 通知单词本页面刷新
        logger.debug(f"[Signal] vocab_changed.emit() - word={w}")
        self.vocab_changed.emit()
