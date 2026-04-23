# -*- coding: utf-8 -*-
"""
查词历史页面 - 显示用户的查词记录，支持关键词搜索、时间筛选、导出等
"""

import sqlite3
import time
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QGroupBox, QMessageBox,
    QAbstractItemView,
    QApplication, QMenu, QComboBox
)
from PySide6.QtCore import Qt, Signal, QTimer

from src.core.logger import get_logger
from src.core.config import DB_FILE

logger = get_logger(__name__)


class HistoryPage(QWidget):
    """
    查词历史页面
    
    功能：
    - 显示最近500条查词记录（按时间倒序）
    - 关键词实时过滤搜索
    - 时间范围筛选
    - 双击单词跳转到查词页
    - 导出历史为CSV / 清空历史
    """

    word_selected = Signal(str)  # 双击历史记录时发射（通知搜索页）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cached_all_data = []  # 缓存全部数据用于客户端过滤
        self._init_ui()
        logger.info("查词历史页面初始化完成")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ===== 标题区 =====
        header = QHBoxLayout()
        title = QLabel("📋 查词历史")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        self.stats_label = QLabel("共 0 条记录")
        self.stats_label.setStyleSheet("color: #888; font-size: 13px;")
        header.addWidget(self.stats_label)
        layout.addLayout(header)

        # ===== 筛选工具栏 =====
        filter_bar = QHBoxLayout()
        
        filter_bar.addWidget(QLabel("🔍"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索历史记录...")
        self.search_input.setFixedHeight(32)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._do_filter)
        filter_bar.addWidget(self.search_input, stretch=1)

        # 排序方式
        filter_bar.addWidget(QLabel("排序:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["最近查询", "查询最多", "按字母 A-Z"])
        self.sort_combo.currentIndexChanged.connect(self._do_filter)
        filter_bar.addWidget(self.sort_combo)

        # 快捷时间筛选
        self.btn_today = QPushButton("今日")
        self.btn_today.setCheckable(True)
        self.btn_today.clicked.connect(lambda: self._quick_filter('today'))
        self.btn_week = QPushButton("近7天")
        self.btn_week.setCheckable(True)
        self.btn_week.clicked.connect(lambda: self._quick_filter('week'))
        self.btn_all = QPushButton("全部")
        self.btn_all.setCheckable(True)
        self.btn_all.setChecked(True)  # 默认全选
        self.btn_all.clicked.connect(lambda: self._quick_filter('all'))

        time_btns = [self.btn_today, self.btn_week, self.btn_all]
        for btn in time_btns:
            btn.setFixedSize(60, 30)

        filter_bar.addSpacing(10)
        filter_bar.addWidget(self.btn_today)
        filter_bar.addWidget(self.btn_week)
        filter_bar.addWidget(self.btn_all)

        layout.addLayout(filter_bar)

        # ===== 历史表格 =====
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(3)
        self.history_table.setHorizontalHeaderLabels(["查询单词", "最近查询时间", "次数"])
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.history_table.setColumnWidth(1, 160)
        self.history_table.setColumnWidth(1, 160)
        self.history_table.setColumnWidth(2, 70)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.doubleClicked.connect(self._on_row_double_clicked)
        # 右键菜单
        self.history_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.history_table)

        # ===== 底部操作栏 =====
        bottom_bar = QHBoxLayout()

        self.btn_clear = QPushButton("🗑 清空历史")
        self.btn_clear.clicked.connect(self.clear_history)
        bottom_bar.addWidget(self.btn_clear)

        self.btn_export = QPushButton("📤 导出CSV")
        self.btn_export.clicked.connect(self.export_history)
        bottom_bar.addWidget(self.btn_export)

        self.btn_delete_selected = QPushButton("删除选中项")
        self.btn_delete_selected.clicked.connect(self._delete_selected_rows)
        bottom_bar.addWidget(self.btn_delete_selected)

        bottom_bar.addStretch()

        # 提示
        tip = QLabel("💡 双击单词可跳转查词 | 右键可删除单条")
        tip.setStyleSheet("color: #aaa; font-size: 11px;")
        bottom_bar.addWidget(tip)

        layout.addLayout(bottom_bar)

        # 初始加载
        QTimer.singleShot(100, self.load_history)

    # ========== 数据加载与过滤 ==========

    def load_history(self):
        """从数据库加载全部历史记录到缓存"""
        try:
            with sqlite3.connect(DB_FILE) as conn:
                rows = conn.execute("""
                    SELECT word, last_access_time, search_count
                    FROM search_history
                    ORDER BY last_access_time DESC
                    LIMIT 500
                """).fetchall()

            self._cached_all_data = list(rows)
            logger.debug(f"加载历史记录 {len(rows)} 条")
            self._do_filter()

        except Exception as e:
            logger.error(f"加载历史记录失败: {e}", exc_info=True)

    def _on_search_text_changed(self, text: str):
        """搜索框文字变化 -> 延迟300ms后自动筛选（防抖）"""
        if hasattr(self, '_filter_timer'):
            self._filter_timer.stop()
        self._filter_timer = QTimer.singleShot(300, self._do_filter)

    def _quick_filter(self, mode: str):
        """快捷时间按钮互斥选择 + 筛选"""
        # 互斥：只允许一个被选中
        self.btn_today.setChecked(mode == 'today')
        self.btn_week.setChecked(mode == 'week')
        self.btn_all.setChecked(mode == 'all')
        self._do_filter()

    def _get_time_threshold(self) -> float | None:
        """根据当前快捷按钮获取时间阈值"""
        if self.btn_today.isChecked():
            now = time.time()
            # 今天0点的时间戳
            today_start = now - (now % 86400)
            return today_start
        elif self.btn_week.isChecked():
            return time.time() - 7 * 86400
        return None  # 全部

    def _do_filter(self):
        """根据所有筛选条件过滤并显示数据（纯客户端过滤，无需再查DB）"""
        keyword = self.search_input.text().strip().lower()
        sort_mode = self.sort_combo.currentIndex()  # 0=最近 1=最多次 2=字母
        time_thresh = self._get_time_threshold()

        # 过滤
        filtered = []
        for word, qtime, count in self._cached_all_data:
            # 关键词匹配
            if keyword and keyword not in word.lower():
                continue
            # 时间范围
            if time_thresh and qtime < time_thresh:
                continue
            filtered.append((word, qtime, count or 0))

        # 排序
        if sort_mode == 0:       # 最近查询
            filtered.sort(key=lambda x: (-x[1], x[0]))
        elif sort_mode == 1:     # 查询最多
            filtered.sort(key=lambda x: (-x[2], -x[1]))
        else:                   # 字母 A-Z
            filtered.sort(key=lambda x: (x[0].lower(), ))

        # 渲染表格
        self._update_table(filtered)

    def _update_table(self, data: list):
        """渲染表格数据"""
        self.history_table.setRowCount(len(data))
        for row, (word, qtime, count) in enumerate(data):
            try:
                time_str = datetime.fromtimestamp(qtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                time_str = str(qtime)

            item_word = QTableWidgetItem(word)
            item_word.setData(Qt.UserRole, word)  # 存储原始值供右键使用

            self.history_table.setItem(row, 0, item_word)
            self.history_table.setItem(row, 1, QTableWidgetItem(time_str))
            self.history_table.setItem(row, 2, QTableWidgetItem(str(count)))

        total = len(self._cached_all_data)
        shown = len(data)
        self.stats_label.setText(f"共 {total} 条记录（当前显示 {shown}）")

    # ========== 用户交互 ==========

    def _on_row_double_clicked(self, index):
        """双击行 -> 跳转到搜索页查词"""
        row = index.row()
        item = self.history_table.item(row, 0)
        if item:
            word = item.text()
            logger.debug(f"用户从历史中选择: {word}")
            self.word_selected.emit(word)

    def _show_context_menu(self, pos):
        """右键菜单"""
        item = self.history_table.itemAt(pos)
        if not item:
            return

        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        row = item.row()
        word_item = self.history_table.item(row, 0)
        word = word_item.text() if word_item else ""

        act_jump = menu.addAction("🔍 跳转查词")
        act_jump.triggered.connect(lambda: self.word_selected.emit(word))
        act_copy = menu.addAction("📋 复制单词")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(word))
        act_del = menu.addAction("🗑 删除此条")
        act_del.triggered.connect(lambda: self._delete_row_by_word(word))

        menu.exec(self.history_table.viewport().mapToGlobal(pos))

    def _delete_row_by_word(self, word: str):
        """删除指定单词的历史记录"""
        reply = QMessageBox.question(
            self, "确认删除",
            f'确定要删除 "{word}" 的查词记录吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("DELETE FROM search_history WHERE word=?", (word,))
                conn.commit()
            # 从缓存中移除并刷新
            self._cached_all_data = [
                r for r in self._cached_all_data if r[0] != word
            ]
            self._do_filter()
            logger.info(f"已删除历史记录: {word}")
        except Exception as e:
            logger.error(f"删除失败: {e}")

    def _delete_selected_rows(self):
        """删除选中的多行记录"""
        selected = self.history_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "提示", "请先选中要删除的行")
            return

        words = set()
        for item in selected:
            row = item.row()
            wi = self.history_table.item(row, 0)
            if wi:
                words.add(wi.text())

        reply = QMessageBox.question(
            self, "确认删除",
            f'确定要删除选中的 {len(words)} 条记录吗？\n{chr(10).join(sorted(words)[:10])}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with sqlite3.connect(DB_FILE) as conn:
                for w in words:
                    conn.execute("DELETE FROM search_history WHERE word=?", (w,))
                conn.commit()
            self.load_history()  # 重新加载
            logger.info(f"已批量删除 {len(words)} 条历史记录")
        except Exception as e:
            logger.error(f"批量删除失败: {e}")

    def clear_history(self):
        """清空全部历史"""
        reply = QMessageBox.warning(
            self, "⚠️ 确认清空",
            "确定要清空所有查词历史吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("DELETE FROM search_history")
                conn.commit()
            self._cached_all_data = []
            self._update_table([])
            logger.info("已清空全部历史记录")
        except Exception as e:
            logger.error(f"清空失败: {e}", exc_info=True)

    def export_history(self):
        """导出为CSV文件"""
        import csv
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(
            self, "导出查词历史", "search_history.csv", "CSV文件 (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['单词', '最近查询时间', '查询次数'])
                for word, qtime, count in self._cached_all_data:
                    try:
                        ts = datetime.fromtimestamp(qtime).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        ts = str(qtime)
                    writer.writerow([word, ts, count or 0])

            QMessageBox.information(
                self, "导出成功",
                f'历史记录已导出到:\n{path}\n\n共 {len(self._cached_all_data)} 条'
            )
            logger.info(f"历史记录已导出: {path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            logger.error(f"导出历史失败: {e}", exc_info=True)
