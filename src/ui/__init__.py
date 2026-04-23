# file: src/ui/__init__.py
# -*- coding: utf-8 -*-
"""
UI表现层包
包含主题管理、自定义控件、功能页面、协议处理器等
"""

# 导入主要组件以便于外部使用
from .theme_manager import ThemeManager
from ..core.config import THEME_CONFIG_FILE

__all__ = ['ThemeManager']
