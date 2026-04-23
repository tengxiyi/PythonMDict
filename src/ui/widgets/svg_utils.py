# file: src/ui/widgets/svg_utils.py
# -*- coding: utf-8 -*-
"""
SVG图标工具函数
提供SVG路径数据转换为QIcon的功能
"""
from PySide6.QtCore import QByteArray, QSize, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt

from ...core.logger import logger


def create_svg_icon(path_data: str, color: str, size: int = 24) -> QIcon:
    """
    将SVG路径数据转换为QIcon
    
    Args:
        path_data: SVG路径的d属性字符串（如 "M15.5 14h-.79..."）
        color: 填充颜色（如 "#2196F3"）
        size: 渲染尺寸
        
    Returns:
        生成的QIcon对象，如果渲染失败返回空Icon
    """
    svg_content = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 24 24" width="{size}" height="{size}">'
        f'<path d="{path_data}" fill="{color}" /></svg>'
    )
    
    data = QByteArray(svg_content.encode('utf-8'))
    renderer = QSvgRenderer(data)

    if not renderer.isValid():
        logger.warning(f"SVG渲染失败 (color={color})")
        return QIcon()

    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, 32, 32))
    painter.end()
    
    return QIcon(pixmap)
