# file: src/ui/theme_manager.py
# -*- coding: utf-8 -*-
"""
主题管理器
负责10种预设主题的加载、保存、切换，以及生成WebView CSS样式
"""
import os
import json
import logging

from PySide6.QtGui import QColor

from ..core.config import THEME_CONFIG_FILE
from ..core.logger import logger


class ThemeManager:
    """
    主题管理器类
    管理10种预设配色方案，支持JSON持久化和WebView CSS生成
    """
    
    # 10种精选配色方案
    PRESETS = {
        "Light (Default)": {
            "bg": "#ffffff", "card": "#ffffff", "text": "#333333",
            "primary": "#2196F3", "border": "#E0E0E0", "hover": "#F5F5F5",
            "meta": "#666666", "sidebar": "#F5F7FA"
        },
        "Dark (Default)": {
            "bg": "#2b2b2b", "card": "#3c3c3c", "text": "#ffffff",
            "primary": "#64b5f6", "border": "#555555", "hover": "#4a4a4a",
            "meta": "#bbbbbb", "sidebar": "#333333"
        },
        "Sepia (Reading)": {
            "bg": "#f4ecd8", "card": "#fdf6e3", "text": "#5b4636",
            "primary": "#d35400", "border": "#e4dcc9", "hover": "#e9e0cb",
            "meta": "#95a5a6", "sidebar": "#eee4cc"
        },
        "Nord (Arctic)": {
            "bg": "#2E3440", "card": "#434c5e", "text": "#ECEFF4",
            "primary": "#88C0D0", "border": "#4C566A", "hover": "#4C566A",
            "meta": "#D8DEE9", "sidebar": "#3b4252"
        },
        "Dracula (Vampire)": {
            "bg": "#282a36", "card": "#44475a", "text": "#f8f8f2",
            "primary": "#ff79c6", "border": "#6272a4", "hover": "#50536b",
            "meta": "#bd93f9", "sidebar": "#343746"
        },
        "Forest (Green)": {
            "bg": "#f1f8e9", "card": "#ffffff", "text": "#1b5e20",
            "primary": "#43a047", "border": "#c8e6c9", "hover": "#dcedc8",
            "meta": "#689f38", "sidebar": "#e8f5e9"
        },
        "Ocean (Deep Blue)": {
            "bg": "#0f172a", "card": "#334155", "text": "#f1f5f9",
            "primary": "#38bdf8", "border": "#475569", "hover": "#1e293b",
            "meta": "#cbd5e1", "sidebar": "#1e293b"
        },
        "Solarized Light": {
            "bg": "#fdf6e3", "card": "#eee8d5", "text": "#2c3e50",
            "primary": "#268bd2", "border": "#93a1a1", "hover": "#e0d7c6",
            "meta": "#586e75", "sidebar": "#eee8d5"
        },
        "Cyberpunk (Neon)": {
            "bg": "#1a1b26", "card": "#24283b", "text": "#c0caf5",
            "primary": "#f7768e", "border": "#414868", "hover": "#2f3549",
            "meta": "#7aa2f7", "sidebar": "#1f2335"
        },
        "High Contrast": {
            "bg": "#000000", "card": "#222222", "text": "#ffffff",
            "primary": "#FFD700", "border": "#555555", "hover": "#333333",
            "meta": "#aaaaaa", "sidebar": "#111111"
        }
    }

    def __init__(self):
        self.current_theme_name = "Light (Default)"
        self.colors = self.PRESETS[self.current_theme_name].copy()
        self.load_config()

    def load_config(self):
        """从JSON文件加载用户选择的主题"""
        if os.path.exists(THEME_CONFIG_FILE):
            try:
                with open(THEME_CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    name = data.get("theme_name", "Light (Default)")
                    if name in self.PRESETS:
                        self.current_theme_name = name
                        self.colors = self.PRESETS[name].copy()
                        logger.info(f"已加载主题配置: {name}")
            except Exception as e:
                logger.warning(f"加载主题配置失败: {e}")

    def set_theme(self, theme_name: str):
        """切换到指定主题"""
        if theme_name in self.PRESETS:
            self.current_theme_name = theme_name
            self.colors = self.PRESETS[theme_name].copy()
            self.save_config()
            logger.info(f"切换主题: {theme_name}")

    def get_current_theme(self) -> dict:
        """返回当前主题的颜色字典（供主窗口样式使用）"""
        c = self.colors
        return {
            'bg_primary': c.get('bg', '#ffffff'),
            'text_primary': c.get('text', '#333333'),
            'text_secondary': c.get('meta', '#888888'),
            'bg_secondary': c.get('card', '#f5f5f5'),
            'border_color': c.get('border', '#e0e0e0'),
            'sidebar_bg': c.get('sidebar', '#f0f0f0'),
        }

    def save_config(self):
        """将当前主题名称持久化到JSON文件"""
        try:
            with open(THEME_CONFIG_FILE, "w") as f:
                json.dump({"theme_name": self.current_theme_name}, f)
        except Exception as e:
            logger.error(f"保存主题配置失败: {e}")

    def get_webview_css(self) -> str:
        """
        生成适用于QWebEngineView的CSS样式字符串
        包含CSS变量定义、深浅色模式适配、滚动条美化等
        """
        c = self.colors
        bg_color = c['bg'].lstrip('#')
        
        # 判断是否为深色模式（基于亮度计算）
        is_dark = False
        if len(bg_color) == 6:
            r, g, b = tuple(int(bg_color[i:i + 2], 16) for i in (0, 2, 4))
            is_dark = (r * 0.299 + g * 0.587 + b * 0.114) < 128

        css = f"""
        :root {{ 
            --primary: {c['primary']}; --bg: {c['bg']}; --card: {c['card']}; 
            --text: {c['text']}; --border: {c['border']}; --meta: {c['meta']}; 
            --hover: {c['hover']}; 
            --shadow: 0 4px 12px rgba(0,0,0,0.08);
            --radius: 12px;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: var(--text);
            background-color: var(--bg);
            transition: background 0.3s ease;
        }}
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: #ccc; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #999; }}
        """

        # 深色模式额外样式（强制词典内容颜色）
        if is_dark:
            css += f"""
            ::-webkit-scrollbar-thumb {{ background: #555; }}
            ::-webkit-scrollbar-thumb:hover {{ background: #777; }}

            .entry-content {{ background-color: var(--card) !important; color: #e0e0e0 !important; }}

            .entry-content * {{
                background-color: transparent !important;
                color: #e0e0e0 !important; 
                border-color: {c['border']} !important;
                box-shadow: none !important;
            }}

            .entry-content a {{ color: {c['primary']} !important; text-decoration: none; border-bottom: 1px dashed {c['primary']}; }}
            .entry-content img {{ background-color: #eee; border-radius: 6px; padding: 4px; margin: 5px 0; }}
            .entry-content b, .entry-content strong, .entry-content h1, .entry-content h2 {{ color: #FFD700 !important; }}
            """
        else:
            # 浅色模式的链接样式优化
            css += """
            .entry-content a {{ color: var(--primary); text-decoration: none; font-weight: 500; }}
            .entry-content a:hover {{ text-decoration: underline; }}
            """

        return css


# 全局单例实例（保持向后兼容）
# 注意：实际初始化在 main_window.py 的 __init__ 中完成
theme_manager: ThemeManager = None

