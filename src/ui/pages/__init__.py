# -*- coding: utf-8 -*-
"""
src.ui.pages - 功能页面模块包

包含所有功能页面组件：
- search_page.py: 查词主页面
- vocab_page.py: 单词本/闪卡学习页面
- settings_page.py: RSS新闻源设置页面
- theme_page.py: 主题选择页面
- dict_manager_page.py: 词典管理页面
- history_page.py: 查词历史页面
- text_analyzer_page.py: 词频分析页面
"""

from src.ui.pages.search_page import SearchSplitPage
from src.ui.pages.vocab_page import VocabPage
from src.ui.pages.settings_page import SettingsPage
from src.ui.pages.theme_page import ThemePage
from src.ui.pages.dict_manager_page import DictManagerPage
from src.ui.pages.history_page import HistoryPage
from src.ui.pages.text_analyzer_page import TextAnalyzerPage

__all__ = [
    'SearchSplitPage',
    'VocabPage', 
    'SettingsPage',
    'ThemePage',
    'DictManagerPage',
    'HistoryPage',
    'TextAnalyzerPage',
]
