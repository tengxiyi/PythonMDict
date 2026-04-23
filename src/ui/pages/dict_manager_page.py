# -*- coding: utf-8 -*-
"""
词典管理页面 - 词典导入/管理界面
从 main.py 的 DictManagerPage 类拆分
"""

import logging
import sqlite3

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QMessageBox, QFileDialog, QSpinBox, QGroupBox,
    QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QThread

from src.core.logger import get_logger
from src.core.config import DB_FILE
from src.core.indexer_worker import IndexerWorker

logger = get_logger(__name__)


class DictManagerPage(QWidget):
    """词典管理页面"""

    dict_imported = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        logger.info("词典管理页面初始化完成")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题
        title = QLabel("📚 词典管理")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

        desc = QLabel("导入和管理 MDX/MDD 格式词典文件")
        desc.setStyleSheet("font-size: 14px; color: #888;")
        layout.addWidget(desc)

        # 操作区域
        op_group = QGroupBox("操作")
        op_layout = QHBoxLayout(op_group)

        self.import_btn = QPushButton("📥 导入词典")
        self.import_btn.clicked.connect(self._import_dict)
        op_layout.addWidget(self.import_btn)

        op_layout.addStretch()
        
        # 优先级设置
        priority_label = QLabel("优先级:")
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(0, 100)
        self.priority_spin.setValue(50)
        op_layout.addWidget(priority_label)
        op_layout.addWidget(self.priority_spin)

        layout.addWidget(op_group)

        # 词典列表
        list_group = QGroupBox("已导入词典")
        list_layout = QVBoxLayout(list_group)

        self.dict_table = QTableWidget()
        self.dict_table.setColumnCount(5)
        self.dict_table.setHorizontalHeaderLabels(["词典名称", "路径", "词条数", "排名", "操作"])
        self.dict_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.dict_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.dict_table.setColumnWidth(2, 80)
        self.dict_table.setColumnWidth(3, 70)
        self.dict_table.setColumnWidth(4, 140)
        self.dict_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dict_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dict_table.setAlternatingRowColors(True)
        list_layout.addWidget(self.dict_table)

        # 排序/操作按钮行
        btn_layout = QHBoxLayout()
        
        self.btn_move_up = QPushButton("↑ 上移")
        self.btn_move_up.clicked.connect(self._move_dict_up)
        btn_layout.addWidget(self.btn_move_up)
        
        self.btn_move_down = QPushButton("↓ 下移")
        self.btn_move_down.clicked.connect(self._move_dict_down)
        btn_layout.addWidget(self.btn_move_down)
        
        btn_layout.addStretch()
        
        refresh_btn = QPushButton("🔄 刷新列表")
        refresh_btn.clicked.connect(self.refresh_dict_list)
        btn_layout.addWidget(refresh_btn)
        
        list_layout.addLayout(btn_layout)

        layout.addWidget(list_group)

        # 导入进度
        progress_group = QGroupBox("导入状态")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("就绪")
        progress_layout.addWidget(self.status_label)

        layout.addWidget(progress_group)

        layout.addStretch()

        # 加载已有词典
        self.refresh_dict_list()

    def _import_dict(self):
        """选择并导入词典文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择MDX词典文件", "", "MDX词典 (*.mdx);;所有文件 (*)"
        )
        
        if not file_path:
            return
        
        logger.info(f"开始导入词典: {file_path}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在导入...")
        self.import_btn.setEnabled(False)

        # 启动导入线程（保存为实例变量防止被GC回收）
        priority = self.priority_spin.value()
        self._import_worker = IndexerWorker(file_path, DB_FILE, priority)
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.start()

    def _on_import_progress(self, current, total, msg):
        """导入进度回调"""
        percentage = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(percentage)
        self.status_label.setText(msg or f"处理中... {percentage}%")

    def _on_import_finished(self, result):
        """导入完成回调"""
        try:
            count = result.get('count', 0) if result else 0
            self.status_label.setText(f"OK! Imported {count} entries")
            logger.info(f"Dict import done, entries: {count}")
            self.dict_imported.emit()
            self.refresh_dict_list()
        except Exception as e:
            logger.error(f"处理导入结果失败: {e}", exc_info=True)
            self.status_label.setText("⚠️ 导入完成但更新显示失败")

        self.progress_bar.setVisible(False)
        self.import_btn.setEnabled(True)

    def _on_import_error(self, error_msg):
        """导入错误回调"""
        logger.error(f"词典导入失败: {error_msg}")
        QMessageBox.critical(self, "Import Error", f"Error: {error_msg}", QMessageBox.StandardButton.Ok)
        self.status_label.setText("Import failed")
        self.progress_bar.setVisible(False)
        self.import_btn.setEnabled(True)

    def refresh_dict_list(self):
        """刷新词典列表，并自动按当前顺序重算排名（确保优先级不重复）"""
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, name, path, priority,
                       (SELECT COUNT(*) FROM standard_entries WHERE dict_id=dict_info.id) as cnt
                FROM dict_info 
                ORDER BY priority DESC, id ASC
            """)
            
            dicts = cursor.fetchall()
            
            # 自动重算优先级：第1名=100, 第2名=90, 第3名=80...（永不重复）
            total = len(dicts)
            if total > 0:
                step = max(5, 100 // total)
                for row_idx, d in enumerate(dicts):
                    did = d[0]
                    new_pri = 100 - (row_idx * step)
                    if d[2] != new_pri:  # 只有值变了才写
                        cursor.execute("UPDATE dict_info SET priority=? WHERE id=?", (new_pri, did))
                conn.commit()
                
                # 重新查询获取更新后的数据
                cursor.execute("""
                    SELECT id, name, path, priority,
                           (SELECT COUNT(*) FROM standard_entries WHERE dict_id=dict_info.id) as cnt
                    FROM dict_info 
                    ORDER BY priority DESC, id ASC
                """)
                dicts = cursor.fetchall()
            
            self.dict_table.setRowCount(len(dicts))
            
            for row, d in enumerate(dicts):
                did, name, path, priority, count = d
                self.dict_table.setItem(row, 0, QTableWidgetItem(name))
                self.dict_table.setItem(row, 1, QTableWidgetItem(path))
                self.dict_table.setItem(row, 2, QTableWidgetItem(str(count)))
                
                # 显示排名（只读），不再用可编辑SpinBox
                rank_label = QLabel(f"#{row + 1}")
                rank_label.setAlignment(Qt.AlignCenter)
                rank_label.setStyleSheet("font-weight:bold;color:#2196F3;font-size:13px;")
                self.dict_table.setCellWidget(row, 3, rank_label)
                # 将dict_id存到rank_label上以便排序时使用
                rank_label.setProperty("dict_id", did)
                
                # 操作按钮
                btn_del_row = QPushButton("删除")
                btn_del_row.setFixedWidth(60)
                btn_del_row.setProperty("dict_id", did)
                btn_del_row.setProperty("row", row)
                btn_del_row.clicked.connect(lambda checked, id=did: self._delete_single(id))
                self.dict_table.setCellWidget(row, 4, btn_del_row)

            conn.close()
            logger.debug(f"刷新词典列表完成，共 {len(dicts)} 个词典，已重排优先级")
        except Exception as e:
            logger.error(f"刷新词典列表失败: {e}", exc_info=True)
            self.status_label.setText("⚠️ 刷新列表失败")

    def _move_dict_up(self):
        """将选中词典上移（提高优先级）"""
        row = self.dict_table.currentRow()
        if row < 1 or row >= self.dict_table.rowCount():
            return
        self._swap_priority(row, row - 1)

    def _move_dict_down(self):
        """将选中词典下移（降低优先级）"""
        row = self.dict_table.currentRow()
        if row < 0 or row >= self.dict_table.rowCount() - 1:
            return
        self._swap_priority(row, row + 1)

    def _swap_priority(self, row_a: int, row_b: int):
        """交换两个词典的位置（通过调整优先级实现）
        
        row_a: 被选中要移动的那一行
        row_b: 目标位置的那一行
        """
        try:
            # 从 rank_label (column 3) 获取 dict_id
            widget_a = self.dict_table.cellWidget(row_a, 3)
            widget_b = self.dict_table.cellWidget(row_b, 3)
            if not widget_a or not widget_b:
                return
            
            did_a = widget_a.property("dict_id")
            did_b = widget_b.property("dict_id")
            if did_a is None or did_b is None:
                return

            with sqlite3.connect(DB_FILE) as conn:
                # 读取两者的当前优先级，然后互换
                cur_pri_a = conn.execute("SELECT priority FROM dict_info WHERE id=?", (did_a,)).fetchone()[0]
                cur_pri_b = conn.execute("SELECT priority FROM dict_info WHERE id=?", (did_b,)).fetchone()[0]
                
                # 互换优先级值
                conn.execute("UPDATE dict_info SET priority=? WHERE id=?", (cur_pri_b, did_a))
                conn.execute("UPDATE dict_info SET priority=? WHERE id=?", (cur_pri_a, did_b))
                conn.commit()

            # 刷新列表（自动重算所有排名）
            self.refresh_dict_list()

            # 找到被移动词典的新位置并选中它
            target_row = self._find_row_by_dict_id(did_a)
            if target_row >= 0:
                self.dict_table.selectRow(target_row)

        except Exception as e:
            logger.error(f"交换词典顺序失败: {e}")

    def _find_row_by_dict_id(self, dict_id: int) -> int:
        """根据dict_id在当前表格中查找行号"""
        for row in range(self.dict_table.rowCount()):
            spin = self.dict_table.cellWidget(row, 3)
            if spin and spin.property("dict_id") == dict_id:
                return row
        return -1

    def _delete_single(self, dict_id: int):
        """删除单个词典及其词条"""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这个词典吗？\n所有关联的词条数据也将被删除！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("DELETE FROM standard_entries WHERE dict_id=?", (dict_id,))
                conn.execute("DELETE FROM dict_info WHERE id=?", (dict_id,))
                conn.commit()
            logger.info(f"已删除词典 ID={dict_id}")
            self.status_label.setText("✅ 词典已删除")
            self.refresh_dict_list()
            self.dict_imported.emit()  # 通知搜索页刷新
        except Exception as e:
            logger.error(f"删除词典失败: {e}")
            QMessageBox.critical(self, "Error", f"删除失败: {e}")
