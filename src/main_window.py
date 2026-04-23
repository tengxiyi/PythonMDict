# -*- coding: utf-8 -*-
"""
极客词典Pro - 主窗口
从 main.py 的 ModernMainWindow 类拆分，组装所有UI组件

这是应用程序的主窗口类，负责：
1. 组装所有页面组件
2. 管理页面导航
3. 协调各组件之间的通信
4. 初始化全局状态
"""

import os
import sys
import logging
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QApplication, QStatusBar, QMenuBar, QMenu
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QAction

# 导入核心模块
from src.core.config import APP_NAME, APP_VERSION
from src.core.database import DatabaseManager
from src.core.logger import get_logger

# 导入UI组件
from src.ui.theme_manager import ThemeManager, theme_manager as _theme_manager_ref
from src.ui.widgets.sidebar import Sidebar
from src.ui.widgets.mdd_cache import MDDCacheManager

# 导入协议处理器
from src.ui.handlers.mdict_handler import MdictSchemeHandler
from src.ui.handlers.web_pages import DictWebPage, NewsWebPage

# 导入功能页面
from src.ui.pages.search_page import SearchSplitPage
from src.ui.pages.vocab_page import VocabPage
from src.ui.pages.settings_page import SettingsPage
from src.ui.pages.theme_page import ThemePage
from src.ui.pages.dict_manager_page import DictManagerPage
from src.ui.pages.history_page import HistoryPage
from src.ui.pages.text_analyzer_page import TextAnalyzerPage

logger = get_logger(__name__)


class ModernMainWindow(QMainWindow):
    """
    极客词典Pro主窗口
    
    职责：
    - 初始化并组装所有子组件
    - 管理侧边栏导航与页面切换
    - 协调组件间通信
    - 处理窗口级事件
    """

    def __init__(self):
        super().__init__()
        
        # 全局单例引用（修改 theme_manager.py 中的全局变量）
        import src.ui.theme_manager as _tm_module
        _tm_module.theme_manager = ThemeManager()
        self._theme_manager = _tm_module.theme_manager
        
        self._init_window()
        logger.info("主窗口初始化完成")

    def _init_window(self):
        """初始化窗口基本属性"""
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(QSize(1200, 800))
        
        # 尝试设置应用图标
        icon_path = os.path.join(os.path.dirname(__file__), '..', 'app_icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 创建中央widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局：左侧边栏 + 右侧内容区
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建侧边栏
        self.sidebar = Sidebar()
        self.sidebar.setFixedWidth(70)
        main_layout.addWidget(self.sidebar)

        # 创建页面堆栈
        self.page_stack = QStackedWidget()
        main_layout.addWidget(self.page_stack, stretch=1)

        # 初始化数据库
        try:
            DatabaseManager.init_db()
            logger.info("数据库初始化成功")
        except Exception as e:
            logger.critical(f"数据库初始化失败: {e}", exc_info=True)

        # 初始化所有页面
        self._init_pages()

        # 连接导航信号
        self.sidebar.nav_changed.connect(self._on_nav_changed)

        # 应用主题
        self._apply_theme()

        # 创建状态栏
        self._create_status_bar()

        # 创建菜单栏
        self._create_menu_bar()

        # 默认显示搜索页
        self._navigate_to('search')

    def _init_pages(self):
        """初始化所有功能页面（首页立即创建，其余延迟加载）"""
        # 搜索页面（首页）- 需要传入主窗口引用，必须立即创建
        self.search_page = SearchSplitPage(self)
        self.page_stack.addWidget(self.search_page)  # index 0

        # 其余页面延迟到首次导航时创建（显著加快启动速度）
        self._page_cache = {
            'search': self.search_page,  # 首页已创建
            'vocab': None,
            'settings': None,
            'theme': None,
            'dict_manager': None,
            'history': None,
            'analyzer': None,
        }

        # 连接跨页面信号（仅涉及已创建的搜索页）
        self._connect_page_signals()

    def _ensure_page(self, page_name: str):
        """确保指定页面已创建（懒加载）"""
        if self._page_cache.get(page_name) is not None:
            return  # 已创建

        # 延迟创建
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()  # 保持UI响应

        if page_name == 'vocab':
            from src.ui.pages.vocab_page import VocabPage
            self.vocab_page = VocabPage()
            self.page_stack.addWidget(self.vocab_page)
            self._page_cache['vocab'] = self.vocab_page
        elif page_name == 'settings':
            from src.ui.pages.settings_page import SettingsPage
            self.settings_page = SettingsPage()
            self.page_stack.addWidget(self.settings_page)
            self._page_cache['settings'] = self.settings_page
        elif page_name == 'theme':
            from src.ui.pages.theme_page import ThemePage
            self.theme_page = ThemePage(self)
            self.page_stack.addWidget(self.theme_page)
            self._page_cache['theme'] = self.theme_page
            # 补连信号
            if hasattr(self.analyzer_page, 'word_lookup_requested'):
                self.analyzer_page.word_lookup_requested.connect(
                    lambda word: self._search_word(word)
                )
        elif page_name == 'dict_manager':
            from src.ui.pages.dict_manager_page import DictManagerPage
            self.dict_manager_page = DictManagerPage()
            self.page_stack.addWidget(self.dict_manager_page)
            self._page_cache['dict_manager'] = self.dict_manager_page
            if hasattr(self.search_page, 'refresh_dict_list'):
                self.dict_manager_page.dict_imported.connect(self.search_page.refresh_dict_list)
        elif page_name == 'history':
            from src.ui.pages.history_page import HistoryPage
            self.history_page = HistoryPage()
            self.page_stack.addWidget(self.history_page)
            self._page_cache['history'] = self.history_page
            self.history_page.word_selected.connect(lambda word: self._search_word(word))
        elif page_name == 'analyzer':
            from src.ui.pages.text_analyzer_page import TextAnalyzerPage
            self.analyzer_page = TextAnalyzerPage()
            self.page_stack.addWidget(self.analyzer_page)
            self._page_cache['analyzer'] = self.analyzer_page
            if hasattr(self.theme_page, '__class__'):  # theme已创建则连接，否则等theme创建时再连
                self.analyzer_page.word_lookup_requested.connect(
                    lambda word: self._search_word(word)
                )

        logger.info(f"懒加载页面完成: {page_name}")

    def _connect_page_signals(self):
        """连接各页面之间的信号（仅连接已创建的搜索页信号）"""
        # 搜索页收藏变化 -> 自动刷新单词本
        if hasattr(self.search_page, 'vocab_changed'):
            self.search_page.vocab_changed.connect(self._on_vocab_changed)

        # 搜索页查词后 -> 自动刷新查词历史
        if hasattr(self.search_page, 'history_updated'):
            self.search_page.history_updated.connect(self._on_history_updated)

        # 注意: history_page / dict_manager_page / analyzer_page 的信号连接
        # 已移入 _ensure_page() 懒加载时处理

    def _on_vocab_changed(self):
        """槽：搜索页收藏变化时刷新单词本"""
        logger.debug("[Signal] vocab_changed 收到，触发单词本刷新")
        if hasattr(self, 'vocab_page'):
            self.vocab_page.refresh_data()

    def _on_history_updated(self):
        """槽：搜索页查词后刷新查词历史"""
        if hasattr(self, 'history_page'):
            self.history_page.load_history()

    def _search_word(self, word):
        """跳转到搜索页并查词"""
        self._navigate_to('search')
        if hasattr(self.search_page, 'search_word'):
            self.search_page.search_word(word)

    def _on_nav_changed(self, page_name):
        """处理导航切换"""
        self._navigate_to(page_name)

    def _navigate_to(self, page_name: str):
        """导航到指定页面（懒加载支持）"""
        self._ensure_page(page_name)
        widget = self._page_cache.get(page_name)
        if widget:
            self.page_stack.setCurrentWidget(widget)
        self.sidebar.set_active(page_name)
        logger.debug(f"导航到页面: {page_name}")

    def _apply_theme(self):
        """应用当前主题"""
        theme = self._theme_manager.get_current_theme()
        style_sheet = f"""
            QMainWindow {{
                background-color: {theme['bg_primary']};
                color: {theme['text_primary']};
            }}
            QStackedWidget {{
                background-color: {theme['bg_secondary']};
            }}
            QStatusBar {{
                background-color: {theme['bg_primary']};
                color: {theme['text_secondary']};
                border-top: 1px solid {theme['border_color']};
            }}
        """
        self.setStyleSheet(style_sheet)

    def _create_status_bar(self):
        """创建状态栏"""
        statusbar = QStatusBar(self)
        statusbar.showMessage("就绪")
        self.setStatusBar(statusbar)

    def _create_menu_bar(self):
        """创建菜单栏"""
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        import_action = QAction("导入词典", self)
        import_action.triggered.connect(lambda: self._navigate_to('dict_manager'))
        file_menu.addAction(import_action)
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")
        
        vocab_action = QAction("单词本", self)
        vocab_action.triggered.connect(lambda: self._navigate_to('vocab'))
        edit_menu.addAction(vocab_action)
        
        history_action = QAction("查词历史", self)
        history_action.triggered.connect(lambda: self._navigate_to('history'))
        edit_menu.addAction(history_action)

        # 工具菜单
        tools_menu = menubar.addMenu("工具(&T)")
        
        analyzer_action = QAction("词频分析", self)
        analyzer_action.triggered.connect(lambda: self._navigate_to('analyzer'))
        tools_menu.addAction(analyzer_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_about(self):
        """显示关于对话框"""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self, 
            "关于",
            f"""<h2>{APP_NAME}</h2>
            <p>版本: {APP_VERSION}</p>
            <p>一个现代化的桌面词典应用</p>
            <p>支持 MDX/MDD 格式词典</p>
            <hr/>
            <p>基于 PySide6 (Qt6) 构建</p>"""
        )

    # ========== 页面交互方法（被子页面调用）==========
    
    def toggle_always_on_top(self):
        """切换窗口置顶状态"""
        flags = self.windowFlags()
        if flags & Qt.WindowStaysOnTopHint:
            self.setWindowFlags(flags & ~ Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        self.show()

    def switch_page(self, page_name_or_index):
        """切换到指定页面（被search_page等调用）"""
        if isinstance(page_name_or_index, int):
            self.page_stack.setCurrentIndex(page_name_or_index)
        elif isinstance(page_name_or_index, str):
            self._navigate_to(page_name_or_index)

    def reload_theme(self):
        """重新加载并应用当前主题"""
        try:
            self._apply_theme()
            
            # 刷新侧边栏
            if hasattr(self, 'sidebar'):
                self.sidebar.update_theme()
            
            # 通知搜索页刷新样式（图标 + Web视图）
            if hasattr(self, 'search_page'):
                if hasattr(self.search_page, 'refresh_icons'):
                    self.search_page.refresh_icons()
                if hasattr(self.search_page, 'refresh_webview'):
                    self.search_page.refresh_webview()
                # 如果在欢迎页，也刷新欢迎页
                if hasattr(self.search_page, 'render_welcome_page'):
                    if not getattr(self.search_page, 'last_dict_result', None):
                        self.search_page.render_welcome_page()
            
            # 刷新已创建的非首页（安全访问，懒加载可能未创建）
            vocab = getattr(self, 'vocab_page', None)
            if vocab:
                vocab.refresh_data()

            logger.debug("主题已全局刷新")
        except Exception as e:
            logger.warning(f"刷新主题失败: {e}")

    def closeEvent(self, event):
        """窗口关闭事件 - 清理资源"""
        try:
            # 清理MDD缓存连接
            MDDCacheManager.cleanup_all()

            # 停止可能仍在运行的各页面worker线程
            for page_attr in ['search_page', 'analyzer_page']:
                page = getattr(self, page_attr, None)
                if page is None:
                    continue
                for worker_attr in ['search_worker', '_analyzer_worker']:
                    w = getattr(page, worker_attr, None)
                    if w is not None:
                        try:
                            w.quit()
                            w.wait(500)
                        except Exception:
                            pass

            # 保存主题配置
            self._theme_manager.save_config()

            logger.info("应用关闭，资源已清理")
        except Exception as e:
            logger.error(f"关闭清理时出错: {e}", exc_info=True)

        event.accept()




def get_main_window() -> ModernMainWindow:
    """获取主窗口实例（如果存在）"""
    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            if isinstance(widget, ModernMainWindow):
                return widget
    return None
