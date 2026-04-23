# -*- coding: utf-8 -*-
"""
src.ui.handlers - URL协议处理器包

包含自定义URL协议处理器：
- mdict_handler.py: mdict:// 协议处理器
- web_pages.py: WebEngine页面拦截处理器 (DictWebPage, NewsWebPage)
"""

from src.ui.handlers.mdict_handler import MdictSchemeHandler
from src.ui.handlers.web_pages import DictWebPage, NewsWebPage

__all__ = ['MdictSchemeHandler', 'DictWebPage', 'NewsWebPage']
