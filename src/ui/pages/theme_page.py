# file: src/ui/pages/theme_page.py
# -*- coding: utf-8 -*-
"""
主题选择页面 (ThemePage)
提供10种预设主题的可视化选择和预览功能

修复：
1. 主题名后的乱码数字 → 使用 ✅ Unicode 字符替代 HTML 实体
2. 主题名字颜色 → 统一使用深色文字（不依赖当前主题色）
3. UI优化：更大卡片、描述信息、更好的视觉层次
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QFrame
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor, QPalette

from ..theme_manager import theme_manager
from ..widgets.color_preview import ColorPreviewWidget, _is_light
from ...core.logger import logger

# 主题描述文案
THEME_DESCRIPTIONS = {
    "Light (Default)": "经典白色背景，清晰明亮",
    "Dark (Default)": "护眼暗色调，适合夜间使用",
    "Sepia (Reading)": "暖褐色调，长时间阅读更舒适",
    "Nord (Arctic)": "北极光冷色系，简约优雅",
    "Dracula (Vampire)": "经典程序员配色，粉紫霓虹",
    "Forest (Green)": "森林绿色系，自然清新",
    "Ocean (Deep Blue)": "深海蓝色系，沉稳深邃",
    "Solarized Light": "Solarized 经典浅色方案",
    "Cyberpunk (Neon)": "赛博朋克霓虹风格",
    "High Contrast": "高对比度黑白配色",
}


class ThemePage(QWidget):
    """主题选择页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self._setup_ui()
        self._apply_theme_colors()

    def _get_c(self) -> dict:
        """快捷获取当前主题颜色"""
        from ..theme_manager import theme_manager as _tm
        if _tm:
            return _tm.colors
        return {}

    def _is_dark(self) -> bool:
        """当前是否为深色主题"""
        c = self._get_c()
        bg = (c.get('bg', '#fff')).lstrip('#')
        try:
            r, g, b = tuple(int(bg[i:i + 2], 16) for i in (0, 2, 4))
            return (r * 0.299 + g * 0.587 + b * 0.114) < 128
        except Exception:
            return False

    def _apply_theme_colors(self):
        """根据当前主题动态设置所有UI元素的颜色"""
        c = self._get_c()
        dark = self._is_dark()

        # 文字色：直接用主题定义的 text 色（深色主题下是浅字，浅色主题下是深字）
        text_color = c.get('text', '#333' if not dark else '#eee')
        meta_color = c.get('meta', '#888' if not dark else '#aaa')
        bg_color = c.get('bg', '#ffffff')

        # 标题区
        self.title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {text_color};")
        self.subtitle.setStyleSheet(f"font-size: 14px; color: {meta_color}; margin-bottom: 4px;")

        # 列表样式 —— 背景透明融入页面，卡片自适应
        card_bg = c.get('card', '#ffffff' if not dark else '#3c3c3c')
        border_color = c.get('border', '#e0e0e0' if not dark else '#555555')
        hover_color = c.get('hover', '#f5f7fa' if not dark else '#4a4a4a')
        primary_color = c.get('primary', '#2196F3')
        selected_bg = primary_color + "22"   # 13% opacity
        selected_border = primary_color

        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
                padding: 4px;
            }}
            QListWidget::item {{
                background-color: {card_bg};
                border: 1px solid {border_color};
                border-radius: 10px;
                padding: 2px;
                margin: 2px 0;
            }}
            QListWidget::item:selected {{
                background-color: {selected_bg};
                border: 2px solid {selected_border};
            }}
            QListWidget::item:hover {{
                background-color: {hover_color};
            }}
        """)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(20)

        # 标题区
        self.title = QLabel("🎨 选择皮肤主题")
        layout.addWidget(self.title)

        self.subtitle = QLabel("选择一个配色方案来个性化你的界面")
        layout.addWidget(self.subtitle)

        # 主题列表
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(8)
        self.list_widget.setCursor(Qt.PointingHandCursor)

        self.populate_themes()
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        layout.addWidget(self.list_widget)

    def populate_themes(self):
        """填充主题列表项（带预览色块和描述）"""
        from ..theme_manager import theme_manager as _tm
        if not _tm:
            return
        presets = _tm.PRESETS

        # 当前页面的文字颜色（跟随当前主题）
        c = self._get_c()
        dark = self._is_dark()
        text_color = c.get('text', '#333' if not dark else '#eee')
        meta_color = c.get('meta', '#888' if not dark else '#aaa')

        for name, colors in presets.items():
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 68))
            item.setData(Qt.UserRole, name)
            self.list_widget.addItem(item)

            container = QFrame()
            container.setStyleSheet("QFrame { background-color: transparent; }")
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(18, 8, 16, 8)
            h_layout.setSpacing(14)

            # 左侧：名称 + 描述 + 当前标记
            v_info = QVBoxLayout()
            v_info.setSpacing(2)
            v_info.setContentsMargins(0, 0, 0, 0)

            # 主题名称 —— 使用当前主题的文字色
            lbl_name = QLabel(name)
            lbl_name.setStyleSheet(
                f"font-size: 15px; font-weight: bold; color: {text_color};"
            )

            # 描述文字
            desc = THEME_DESCRIPTIONS.get(name, "")
            lbl_desc = QLabel(desc)
            lbl_desc.setStyleSheet(f"font-size: 12px; color: {meta_color};")

            v_info.addWidget(lbl_name)
            v_info.addWidget(lbl_desc)
            h_layout.addLayout(v_info, stretch=1)

            # 当前使用标记
            is_current = (name == _tm.current_theme_name)
            if is_current:
                badge = QLabel("✅ 当前")
                badge.setStyleSheet("""
                    font-size: 11px; font-weight: bold;
                    color: #fff; background-color: #4CAF50;
                    padding: 3px 10px; border-radius: 10px;
                """)
                h_layout.addWidget(badge)

            # 右侧：颜色预览条
            palette_preview = ColorPreviewWidget(colors)
            h_layout.addWidget(palette_preview)

            self.list_widget.setItemWidget(item, container)

            if is_current:
                self.list_widget.setCurrentItem(item)

    def on_item_clicked(self, item: QListWidgetItem):
        """主题项点击 -> 切换主题"""
        from ..theme_manager import theme_manager as _tm
        if not _tm:
            return
        theme_name = item.data(Qt.UserRole)
        if theme_name:
            try:
                _tm.set_theme(theme_name)
                self.main.reload_theme()

                # 保持滚动位置并刷新
                scroll_val = self.list_widget.verticalScrollBar().value()
                row = self.list_widget.row(item)

                # 先应用新主题颜色到页面元素（标题/列表样式）
                self._apply_theme_colors()

                self.list_widget.clear()
                self.populate_themes()
                self.list_widget.setCurrentRow(row)
                self.list_widget.verticalScrollBar().setValue(scroll_val)

                logger.info(f"用户切换主题: {theme_name}")
            except Exception as e:
                logger.error(f"切换主题失败: {e}", exc_info=True)
