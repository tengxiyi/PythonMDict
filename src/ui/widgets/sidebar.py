# file: src/ui/widgets/sidebar.py
# -*- coding: utf-8 -*-
"""
现代风格SVG图标侧边栏
使用QToolButton实现带图标的导航按钮，支持主题切换时自动刷新颜色
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QButtonGroup, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QByteArray, QSize, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter

from ..theme_manager import theme_manager
from .svg_utils import create_svg_icon


class Sidebar(QWidget):
    """
    现代SVG图标侧边栏
    
    包含7个功能按钮：查词、历史、单词本、词典、新闻、提词、主题
    
    Signals:
        nav_changed(str): 点击按钮发射页面名称
        page_changed(int): 点击按钮发射页面索引 (0-6)
    """
    
    page_changed = Signal(int)
    nav_changed = Signal(str)

    # 页面索引到名称的映射
    PAGE_NAMES = {
        0: 'search',
        1: 'history', 
        2: 'vocab',
        3: 'dict_manager',
        4: 'settings',   # RSS新闻源
        5: 'analyzer',   # 词频分析
        6: 'theme'
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(70)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 20, 5, 20)
        layout.setSpacing(15)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.buttons = {}  # 存储按钮引用以便后续刷新

        # SVG图标路径数据 + 中文名称
        self.icons_data = {
            0: (r"M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z", "查词"),
            1: (r"M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z", "历史"),
            2: (r"M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z", "单词本"),
            3: (r"M4 6H2v14c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6H4zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H8V4h12v12zM10 9h8v2h-8zm0 3h4v2h-4zm0-6h8v2h-8z", "词库"),
            4: (r"M6.18 15.64a2.18 2.18 0 0 1 2.18 2.18C8.36 19 7.38 20 6.18 20 5 20 4 19 4 17.82a2.18 2.18 0 0 1 2.18-2.18M4 4.44A15.56 15.56 0 0 1 19.56 20h-2.83A12.73 12.73 0 0 0 4 7.27V4.44m0 5.66a9.9 9.9 0 0 1 9.9 9.9h-2.83A7.07 7.07 0 0 0 4 12.93V10.1z", "新闻源"),
            5: (r"M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z", "提词"),
            6: (r"M12 3a9 9 0 0 0 0 18c4.97 0 9-4.03 9-9s-4.03-9-9-9zM6.5 13.5A1.5 1.5 0 1 1 8 15a1.5 1.5 0 0 1-1.5-1.5zm2.5-4A1.5 1.5 0 1 1 10.5 11 1.5 1.5 0 0 1 9 9.5zm5 0A1.5 1.5 0 1 1 15.5 11 1.5 1.5 0 0 1 14 9.5zm2.5 4A1.5 1.5 0 1 1 18 15a1.5 1.5 0 0 1-1.5-1.5z", "主题")
        }

        for i in range(7):
            self.add_btn(i)

        layout.addStretch()
        self.refresh_icons()  # 初始化时立即刷新

    def add_btn(self, idx: int):
        """创建并添加一个导航按钮"""
        path, text = self.icons_data[idx]

        btn = QToolButton()
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setText(text)
        
        # 图标在文字上方
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setFixedSize(60, 55)
        btn.setIconSize(QSize(26, 26))
        
        btn.setStyleSheet("""
            QToolButton {
                border: none; 
                border-radius: 8px; 
                padding: 4px; 
                background: transparent;
                font-size: 11px;
                font-weight: 500;
            }
        """)

        if idx == 0:
            btn.setChecked(True)  # 默认选中查词页
        
        btn.clicked.connect(lambda _, i=idx: (self.page_changed.emit(i), self.nav_changed.emit(self.PAGE_NAMES.get(i, 'search'))))

        self.layout().addWidget(btn)
        self.btn_group.addButton(btn, idx)
        self.buttons[idx] = btn

    def refresh_icons(self):
        """根据当前主题颜色刷新所有按钮的SVG图标和文字颜色"""
        from ..theme_manager import theme_manager as _tm
        if not _tm:
            return

        c = _tm.colors
        # 文字/图标用主题的 meta 或 text 色（确保在 sidebar 背景上可读）
        icon_color = c.get('meta', '#666')
        text_color = c.get('text', '#333')
        hover_bg = c.get('hover', '#e0e0e0')
        active_color = c.get('primary', '#2196F3')

        for idx, btn in self.buttons.items():
            path, _ = self.icons_data[idx]
            icon = create_svg_icon(path, icon_color)
            btn.setIcon(icon)

            btn.setStyleSheet(f"""
                QToolButton {{
                    border: none;
                    border-radius: 8px;
                    padding: 4px;
                    background: transparent;
                    font-size: 11px;
                    font-weight: 500;
                    color: {icon_color};
                }}
                QToolButton:hover {{
                    background-color: {hover_bg};
                }}
                QToolButton:checked {{
                    background-color: {active_color}22;
                    color: {active_color};
                }}
            """)

    def update_theme(self):
        """主题切换时调用 - 刷新图标和背景色"""
        self.refresh_icons()
        # 更新背景色
        from ..theme_manager import theme_manager as _tm
        if _tm:
            bg = _tm.colors.get('sidebar', '#f0f0f0')
            self.setStyleSheet(f"background-color: {bg};")

    def set_active(self, page_name: str):
        """设置当前激活的页面按钮"""
        # 反向查找索引
        name_to_idx = {v: k for k, v in self.PAGE_NAMES.items()}
        idx = name_to_idx.get(page_name, 0)
        if idx in self.buttons:
            self.buttons[idx].setChecked(True)

