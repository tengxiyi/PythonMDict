# file: src/ui/pages/settings_page.py
# -*- coding: utf-8 -*-
"""
RSS新闻源设置页面 (SettingsPage)
提供新闻源的增删改查、启用/禁用切换、以及RSS源连接测试
"""
import sqlite3

from PySide6.QtCore import Qt, QThread

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QLineEdit, QGroupBox, QListWidgetItem, QMessageBox,
    QTextEdit, QDialogButtonBox, QDialog, QCheckBox
)

from ...core.config import DB_FILE
from ...core.logger import logger
from ...core.news_workers import RSSTestWorker


class SettingsPage(QWidget):
    """RSS新闻源管理页面"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # 标题
        header = QHBoxLayout()
        title_lbl = QLabel("📰 新闻源")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title_lbl)
        header.addStretch()

        tip = QLabel("💡 管理RSS订阅源 | 支持添加/删除/启用/测试")
        tip.setStyleSheet("color: #888; font-size: 12px;")
        header.addWidget(tip)
        layout.addLayout(header)

        # RSS管理分组
        grp_rss = QGroupBox("管理新闻 RSS 源")
        vl = QVBoxLayout(grp_rss)

        # 列表（带复选框）
        self.list_rss = QListWidget()
        self.list_rss.setAlternatingRowColors(True)
        vl.addWidget(self.list_rss)

        # 添加输入行
        h_add = QHBoxLayout()
        self.entry_name = QLineEdit(placeholderText="名称 (例: BBC World)")
        self.entry_url = QLineEdit(placeholderText="RSS 链接 (https://...)")
        btn_add = QPushButton("➕ 添加")
        btn_add.setFixedHeight(34)
        btn_add.clicked.connect(self.add_rss)
        h_add.addWidget(self.entry_name)
        h_add.addWidget(self.entry_url)
        h_add.addWidget(btn_add)

        # 操作按钮行
        h_btns = QHBoxLayout()
        self.btn_toggle = QPushButton("✅ 启用/禁用")
        self.btn_toggle.clicked.connect(self.toggle_rss)
        btn_del = QPushButton("🗑 删除已选")
        btn_del.clicked.connect(self.del_rss)
        btn_test = QPushButton("🔍 测试连接")
        btn_test.clicked.connect(self.test_rss)
        for b in [self.btn_toggle, btn_del, btn_test]:
            b.setFixedHeight(34)
        h_btns.addWidget(self.btn_toggle)
        h_btns.addWidget(btn_del)
        h_btns.addStretch()
        h_btns.addWidget(btn_test)

        vl.addLayout(h_add)
        vl.addLayout(h_btns)
        layout.addWidget(grp_rss)

        # 底部提示
        bottom_tip = QLabel(
            "📌 推荐源：BBC / Reuters / NPR / TechCrunch / VOA Learning English"
        )
        bottom_tip.setStyleSheet("color: #aaa; font-size: 11px; padding-top: 4px;")
        layout.addWidget(bottom_tip)

        self.refresh_rss()

    def refresh_rss(self):
        """从数据库刷新RSS源列表（含启用状态）"""
        self.list_rss.clear()
        try:
            with sqlite3.connect(DB_FILE) as conn:
                for r in conn.execute("SELECT id, name, url, enabled FROM rss_sources"):
                    rid, name, url, enabled = r[0], r[1], r[2], r[3]
                    display = f"[{'✓' if enabled else '○'}] {name}"
                    item = QListWidgetItem(display)
                    item.setData(Qt.UserRole, rid)
                    item.setData(Qt.UserRole + 1, url)   # 存URL用于测试
                    item.setData(Qt.UserRole + 2, name)    # 存名称
                    item.setData(Qt.UserRole + 3, enabled) # 存启用状态
                    # 未启用的用灰色显示
                    if not enabled:
                        item.setForeground(Qt.gray)
                    self.list_rss.addItem(item)
        except Exception as e:
            logger.error(f"刷新RSS列表失败: {e}")

    def add_rss(self):
        """添加新RSS源"""
        n, u = self.entry_name.text().strip(), self.entry_url.text().strip()
        if not n or not u:
            return
        if not u.startswith("http"):
            QMessageBox.warning(self, "提示", "请输入有效的 http/https URL")
            return
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO rss_sources (name, url, enabled) VALUES (?, ?, 1)",
                    (n, u)
                )
            logger.info(f"已添加RSS源: {n}")
            self.entry_name.clear()
            self.entry_url.clear()
            self.refresh_rss()
        except Exception as e:
            logger.warning(f"添加RSS失败: {e}")

    def del_rss(self):
        """删除选中的RSS源"""
        item = self.list_rss.currentItem()
        if not item:
            return
        rid = item.data(Qt.UserRole)
        name = item.data(Qt.UserRole + 2)
        reply = QMessageBox.question(
            self, "确认删除",
            f'确定要删除 RSS 源 "{name}" 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("DELETE FROM rss_sources WHERE id=?", (rid,))
            logger.info(f"已删除RSS源: {name} ({rid})")
            self.refresh_rss()
        except Exception as e:
            logger.error(f"删除RSS失败: {e}")

    def toggle_rss(self):
        """切换选中RSS源的启用/禁用状态"""
        item = self.list_rss.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选择一个RSS源")
            return
        rid = item.data(Qt.UserRole)
        current_enabled = item.data(Qt.UserRole + 3)
        new_state = 0 if current_enabled else 1
        name = item.data(Qt.UserRole + 2)
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("UPDATE rss_sources SET enabled=? WHERE id=?", (new_state, rid))
            logger.info(f"RSS源 [{name}] -> {'已启用' if new_state else '已禁用'}")
            self.refresh_rss()
        except Exception as e:
            logger.error(f"切换RSS状态失败: {e}")

    def test_rss(self):
        """测试选中RSS源的连接"""
        item = self.list_rss.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选择一个RSS源")
            return

        url = item.data(Qt.UserRole + 1)
        name = item.data(Qt.UserRole + 2)

        if not url:
            QMessageBox.warning(self, "错误", "无法获取RSS链接地址")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"测试 RSS 源: {name}")
        dlg.setFixedSize(520, 280)
        dl = QVBoxLayout(dlg)

        dl.addWidget(QLabel(f"<b>URL:</b> {url}"))

        result_text = QTextEdit()
        result_text.setReadOnly(True)
        result_text.setText("⏳ 正在连接，请稍候...")
        dl.addWidget(result_text)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.close)
        dl.addWidget(bb)

        # 保存引用，防止GC回收导致崩溃
        self._test_dlg = dlg

        worker = RSSTestWorker(url)
        self._test_worker = worker  # 关键：持有worker引用，防止线程运行时被GC

        def on_result(success, msg):
            if success:
                result_text.setText(f"✅ 连接成功！\n\n{msg}")
                result_text.setStyleSheet("color: #2e7d32; font-size: 13px;")
            else:
                result_text.setText(f"❌ 连接失败\n\n{msg}")
                result_text.setStyleSheet("color: #c62828; font-size: 13px;")

        def _cleanup():
            """线程完全结束后才清理引用"""
            self._test_worker = None

        worker.test_result.connect(on_result)
        worker.finished.connect(_cleanup)  # 等线程真正结束再释放
        dlg.show()
        worker.start()
