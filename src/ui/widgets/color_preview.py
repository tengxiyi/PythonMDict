# -*- coding: utf-8 -*-
"""
颜色预览控件 - 显示主题配色预览条（圆角胶囊样式）
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QFrame, QToolTip
from PySide6.QtCore import Qt


class ColorPreviewWidget(QWidget):
    """显示一组颜色的圆角预览条"""

    def __init__(self, colors: dict, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(3)
        self.setFixedHeight(28)

        # 主要颜色预览块：带圆角和微边框
        main_colors = ['bg', 'card', 'primary', 'text', 'border']
        color_names = {'bg': '背景', 'card': '卡片', 'primary': '强调',
                       'text': '文字', 'border': '边框'}
        for key in main_colors:
            if key in colors:
                color = QFrame()
                val = colors[key]
                # 根据亮度选边框色
                border_color = "#ccc" if _is_light(val) else "#555"
                color.setStyleSheet(
                    f"background-color: {val}; "
                    f"border: 1px solid {border_color}; "
                    f"border-radius: 5px;"
                )
                color.setFixedSize(32, 20)
                color.setToolTip(f"{color_names.get(key, key)}: {val}")
                layout.addWidget(color)


def _is_light(hex_color: str) -> bool:
    """判断颜色是否为浅色"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return True
    r, g, b = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (r * 0.299 + g * 0.587 + b * 0.114) / 255
    return luminance > 0.5
