# file: src/ui/widgets/floating_text.py
# -*- coding: utf-8 -*-
"""
飘字动画效果控件
用于显示XP奖励等临时提示信息（如 "+50 XP"、"Try Again"）
"""
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QPoint, QPropertyAnimation, QEasingCurve


class FloatingText(QLabel):
    """
    飘字动画控件
    
    创建后会自动执行上飘+淡出动画，动画结束后自动销毁。
    典型用途：显示测验得分反馈（+50 XP）、操作提示等。
    
    Args:
        parent: 父控件
        text: 显示文本
        color: 文本颜色（十六进制格式）
        pos: 初始位置坐标
    """
    
    def __init__(self, parent, text: str = "+10 XP", color: str = "#4CAF50", pos: QPoint = None):
        super().__init__(parent)
        self.setText(text)
        self.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 18px; background: transparent;"
        )
        self.adjustSize()
        
        if pos is None:
            pos = QPoint(0, 0)
        self.move(pos)
        self.show()

        # 上飘动画：从当前位置向上移动50像素
        self.anim_geo = QPropertyAnimation(self, b"pos")
        self.anim_geo.setDuration(1000)
        self.anim_geo.setStartValue(pos)
        self.anim_geo.setEndValue(QPoint(pos.x(), pos.y() - 50))
        self.anim_geo.setEasingCurve(QEasingCurve.OutQuad)
        
        # 动画结束后销毁控件
        self.anim_geo.finished.connect(self.deleteLater)
        self.anim_geo.start()
