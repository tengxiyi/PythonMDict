# file: src/ui/widgets/mastery_ring.py
# -*- coding: utf-8 -*-
"""
环形进度条控件（掌握度环）
用于闪卡学习界面展示复习进度（艾宾浩斯阶段可视化）
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen


class MasteryRing(QWidget):
    """
    环形进度条控件
    
    显示当前复习阶段的完成度（0-100%），支持平滑过渡动画。
    颜色根据进度自动渐变：红色(0%) -> 黄色(50%) -> 绿色(100%)
    
    Args:
        parent: 父控件
        size: 控件尺寸（正方形边长，像素）
        stroke_width: 圆环线条宽度（像素）
    """
    
    def __init__(self, parent=None, size: int = 60, stroke_width: int = 6):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.percent = 0.0
        self.stroke_width = stroke_width
        self.target_percent = 0.0

        # 平滑动画定时器（约60FPS）
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._update_step)

    def set_mastery(self, stage: int, max_stage: int = 7):
        """
        设置掌握度并启动平滑动画
        
        Args:
            stage: 当前复习阶段（0 ~ max_stage-1）
            max_stage: 最大阶段数（默认7级艾宾浩斯间隔）
        """
        self.target_percent = min(1.0, max(0.0, stage / float(max_stage)))
        self.anim.start(15)  # 约60 FPS

    def _update_step(self):
        """动画更新回调：逐步逼近目标值"""
        diff = self.target_percent - self.percent
        if abs(diff) < 0.01:
            self.percent = self.target_percent
            self.anim.stop()
        else:
            self.percent += diff * 0.1  # Ease-out缓动
        self.update()  # 触发重绘

    def _get_color(self) -> QColor:
        """根据当前百分比计算渐变色"""
        p = self.percent
        if p < 0.5:
            # 红到黄
            return QColor(255, int(255 * (p * 2)), 0)
        else:
            # 黄到绿
            return QColor(int(255 * (1 - (p - 0.5) * 2)), 200, 0)

    def paintEvent(self, event):
        """绘制环形进度条"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 计算绘制区域（留出stroke宽度边距）
        rect = self.rect().adjusted(
            self.stroke_width, self.stroke_width,
            -self.stroke_width, -self.stroke_width
        )

        # 1. 背景环（灰色）
        pen_bg = QPen(QColor("#E0E0E0"), self.stroke_width)
        pen_bg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawEllipse(rect)

        # 2. 进度环（彩色，仅在 > 0 时绘制）
        if self.percent > 0:
            pen_prog = QPen(self._get_color(), self.stroke_width)
            pen_prog.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_prog)
            
            # drawArc使用 1/16度单位，从12点钟位置顺时针绘制
            span = -int(self.percent * 360 * 16)
            painter.drawArc(rect, 90 * 16, span)

        # 3. 中心文字（百分比）
        from ..theme_manager import theme_manager
        painter.setPen(theme_manager.colors['text'])
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(int(self.height() * 0.25))
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, f"{int(self.percent * 100)}%")
