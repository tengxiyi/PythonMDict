# -*- coding: utf-8 -*-
"""
文本词频分析页面 - 分析文本中的词汇频率
从 main.py 的 TextAnalyzerPage 类拆分
"""

import logging
from collections import Counter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QSpinBox, QComboBox, QFileDialog, QProgressBar,
    QMessageBox, QSplitter, QAbstractItemView, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QColor, QBrush

from src.core.logger import get_logger
from src.core.config import DB_FILE
from src.core.analyzer_worker import AnalyzerWorker
from src.core.utils import extract_text_from_epub

logger = get_logger(__name__)

# 词性标注颜色映射
_POS_COLOR = {
    '名词': QColor('#2E7D32'),      # 绿
    '名词复': QColor('#388E3C'),
    '动词原形': QColor('#1565C0'),   # 蓝
    '动词过去': QColor('#1976D2'),
    '动名词': QColor('#0D47A1'),
    '三单现': QColor('#1565C0'),
    '过去分词': QColor('#1565C0'),
    '非三人称': QColor('#1976D2'),
    '形容词': QColor('#E65100'),     # 橙
    '比较级': QColor('#EF6C00'),
    '最高级': QColor('#F57C00'),
    '副词': QColor('#7B1FA2'),       # 紫
    '介词': QColor('#455A64'),       # 灰蓝
    '连词': QColor('#546E7F'),
    '代词': QColor('#00796B'),        # 青绿
    '情态动词': QColor('#283593'),
    '功能词': QColor('#9E9E9E'),      # 灰
    '-': QColor('#999'),
}


class TextAnalyzerPage(QWidget):
    """文本词频分析页面"""

    analysis_complete = Signal(dict)  # 分析完成信号
    word_lookup_requested = Signal(str)  # 双击单词查词信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_text = ""
        self.analysis_result = {}
        self._init_ui()
        logger.info("文本分析页面初始化完成")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题
        title = QLabel("📊 文本词频分析")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

        desc = QLabel("分析文本或EPUB电子书中的词汇频率分布")
        desc.setStyleSheet("font-size: 14px; color: #888;")
        layout.addWidget(desc)

        # 主分割区域
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：文本输入区
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        input_group = QGroupBox("输入文本")
        input_layout = QVBoxLayout(input_group)

        # 工具栏
        toolbar = QHBoxLayout()
        
        open_file_btn = QPushButton("📂 打开文件")
        open_file_btn.clicked.connect(self.open_file)
        toolbar.addWidget(open_file_btn)

        paste_btn = QPushButton("📋 粘贴")
        paste_btn.clicked.connect(self.paste_text)
        toolbar.addWidget(paste_btn)

        clear_btn = QPushButton("🗑️ 清空")
        clear_btn.clicked.connect(self.clear_text)
        toolbar.addWidget(clear_btn)

        toolbar.addStretch()
        
        word_count_label = QLabel("字数: 0")
        self.word_count_label = word_count_label
        toolbar.addWidget(word_count_label)
        
        input_layout.addLayout(toolbar)

        # 文本编辑器
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "在此输入或粘贴要分析的文本...\n\n支持直接打开 .txt 或 .epub 文件"
        )
        self.text_edit.textChanged.connect(self._on_text_changed)
        input_layout.addWidget(self.text_edit)

        left_layout.addWidget(input_group)
        splitter.addWidget(left_widget)

        # 右侧：结果显示区
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 分析设置
        settings_group = QGroupBox("分析设置")
        settings_layout = QHBoxLayout(settings_group)

        settings_layout.addWidget(QLabel("显示Top:"))
        self.top_count_spin = QSpinBox()
        self.top_count_spin.setRange(10, 1000)
        self.top_count_spin.setValue(100)
        settings_layout.addWidget(self.top_count_spin)

        settings_layout.addWidget(QLabel("最小长度:"))
        self.min_length_spin = QSpinBox()
        self.min_length_spin.setRange(1, 20)
        self.min_length_spin.setValue(2)
        settings_layout.addWidget(self.min_length_spin)

        analyze_btn = QPushButton("▶️ 开始分析")
        analyze_btn.clicked.connect(self.start_analysis)
        settings_layout.addWidget(analyze_btn)

        save_btn = QPushButton("💾 保存结果")
        save_btn.clicked.connect(self.save_results)
        settings_layout.addWidget(save_btn)

        right_layout.addWidget(settings_group)

        # 结果表格
        result_group = QGroupBox("分析结果")
        result_layout = QVBoxLayout(result_group)

        # 表格工具栏：全选 / 反选 / 加入单词本
        table_toolbar = QHBoxLayout()
        table_toolbar.setSpacing(8)

        self.select_all_btn = QPushButton("☑️ 全选")
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_all_btn.setFixedHeight(30)
        table_toolbar.addWidget(self.select_all_btn)

        self.invert_btn = QPushButton("🔄 反选")
        self.invert_btn.clicked.connect(self._invert_selection)
        self.invert_btn.setFixedHeight(30)
        table_toolbar.addWidget(self.invert_btn)

        table_toolbar.addStretch()

        self.add_vocab_btn = QPushButton("➕ 加入单词本 (0)")
        self.add_vocab_btn.clicked.connect(self.add_to_vocabulary)
        self.add_vocab_btn.setFixedHeight(32)
        self.add_vocab_btn.setStyleSheet("""
            QPushButton {
                background-color: #4A90D9;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3A7BC8;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #888;
            }
        """)
        table_toolbar.addWidget(self.add_vocab_btn)

        result_layout.addLayout(table_toolbar)

        # 表格（第0列为复选框）
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels([
            "", "单词", "出现次数", "频率占比", "词性标注", "排名"
        ])
        # 固定列宽：复选框窄，排名窄，其余自适应
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.result_table.setColumnWidth(0, 36)   # 复选框
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # 单词
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # 出现次数
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # 频率
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # 词性
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.result_table.setColumnWidth(5, 50)   # 排名
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setSortingEnabled(True)
        self.result_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.result_table.itemChanged.connect(self._on_item_changed)
        result_layout.addWidget(self.result_table)

        # 统计摘要 + 已选计数
        summary_layout = QHBoxLayout()
        self.total_words_label = QLabel("总词数: 0")
        self.unique_words_label = QLabel("不重复词: 0")
        self.coverage_label = QLabel("覆盖率: 0%")
        self.selected_count_label = QLabel("已选: <b>0</b> 个词")
        summary_layout.addWidget(self.total_words_label)
        summary_layout.addWidget(self.unique_words_label)
        summary_layout.addWidget(self.coverage_label)
        summary_layout.addStretch()
        summary_layout.addWidget(self.selected_count_label)
        result_layout.addLayout(summary_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        result_layout.addWidget(self.progress_bar)

        right_layout.addWidget(result_group)
        splitter.addWidget(right_widget)

        layout.addWidget(splitter, stretch=1)

    def _on_text_changed(self):
        """文本变化时更新字数统计"""
        text = self.text_edit.toPlainText()
        self.current_text = text
        word_count = len(text.strip().split()) if text.strip() else 0
        self.word_count_label.setText(f"字数: {word_count}")

    def open_file(self):
        """打开文本或EPUB文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "打开文件", "",
            "支持的文件 (*.txt *.epub);;文本文件 (*.txt);;EPUB电子书 (*.epub);;所有文件 (*)"
        )
        
        if not path:
            return
        
        try:
            if path.lower().endswith('.epub'):
                text = extract_text_from_epub(path)
                logger.info(f"从EPUB提取文本: {path}, 长度: {len(text)}")
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
                logger.info(f"读取文本文件: {path}")

            self.text_edit.setPlainText(text)
            self.current_text = text
        except Exception as e:
            logger.error(f"读取文件失败: {path}, 错误: {e}", exc_info=True)
            QMessageBox.warning(self, "读取失败", f"无法读取文件:\n{str(e)}")

    def paste_text(self):
        """粘贴剪贴板内容"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.text_edit.insertPlainText(text)

    def clear_text(self):
        """清空文本"""
        self.text_edit.clear()
        self.current_text = ""

    def start_analysis(self):
        """开始词频分析"""
        if not self.current_text.strip():
            QMessageBox.information(self, "提示", "请先输入或导入要分析的文本")
            return

        logger.info("开始文本词频分析...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # 安全终止可能仍在运行的前一个worker
        if hasattr(self, '_analyzer_worker') and self._analyzer_worker is not None:
            try:
                self._analyzer_worker.quit()
                self._analyzer_worker.wait(2000)
            except Exception:
                pass
            self._analyzer_worker = None

        # 启动分析线程（对齐原始backend.py的信号连接方式）
        min_length = self.min_length_spin.value()
        worker = AnalyzerWorker(self.current_text, min_length)
        self._analyzer_worker = worker  # 持有引用防止GC

        worker.progress.connect(lambda v: self.progress_bar.setValue(v))
        worker.analysis_ready.connect(self._on_analysis_complete)  # 原始: analysis_ready，不是finished！
        worker.error.connect(self._on_analysis_error)

        def _cleanup():
            self._analyzer_worker = None
        worker.finished.connect(_cleanup)

        worker.start()

    def _on_analysis_complete(self, result):
        """分析完成回调"""
        try:
            self.analysis_result = result
            top_n = self.top_count_spin.value()
            
            words_data = result.get('words', [])
            display_data = words_data[:top_n] if words_data else []
            
            total_words = result.get('total_words', 0)
            unique_words = result.get('unique_words', 0)
            
            # 阻止 itemChanged 信号在填充时触发
            self.result_table.blockSignals(True)
            self.result_table.setRowCount(len(display_data))
            
            for rank, item in enumerate(display_data, 1):
                # 兼容新旧格式: (word, count) 或 (word, count, pos)
                if len(item) >= 3:
                    word, count, pos = item[0], item[1], item[2]
                else:
                    word, count, pos = item[0], item[1], '-'
                frequency = count / total_words * 100 if total_words > 0 else 0

                row = rank - 1

                # 第0列：复选框
                chk = QTableWidgetItem()
                chk.setCheckState(Qt.Unchecked)
                chk.setTextAlignment(Qt.AlignCenter)
                self.result_table.setItem(row, 0, chk)

                # 第1列：单词（加粗）
                word_item = QTableWidgetItem(word.lower())
                word_item.setFont(QFont('', -1, QFont.Weight.Bold))
                self.result_table.setItem(row, 1, word_item)

                # 第2-5列
                self.result_table.setItem(row, 2, QTableWidgetItem(str(count)))
                self.result_table.setItem(row, 3, QTableWidgetItem(f"{frequency:.2f}%"))
                
                # 词性标注 - 加颜色标签
                pos_item = QTableWidgetItem(pos)
                color = _POS_COLOR.get(pos, QColor('#888'))
                pos_item.setForeground(QBrush(color))
                self.result_table.setItem(row, 4, pos_item)

                self.result_table.setItem(row, 5, QTableWidgetItem(str(rank)))

            self.result_table.blockSignals(False)

            # 更新统计和选择计数
            self.total_words_label.setText(f"总词数: {total_words}")
            self.unique_words_label.setText(f"不重复词: {unique_words}")
            coverage = len([w for w in display_data]) / unique_words * 100 if unique_words > 0 else 0
            self.coverage_label.setText(f"覆盖率: {coverage:.1f}%")
            self._update_selected_count()

            self.analysis_complete.emit(result)
            logger.info(f"分析完成，总词数: {total_words}, 不重复词: {unique_words}")
        except Exception as e:
            logger.error(f"处理分析结果失败: {e}", exc_info=True)

        self.progress_bar.setVisible(False)

    def _on_analysis_error(self, error_msg):
        """分析错误回调"""
        logger.error(f"词频分析失败: {error_msg}")
        QMessageBox.critical(self, "分析失败", f"分析过程中出错:\n{error_msg}")
        self.progress_bar.setVisible(False)

    def _on_cell_double_clicked(self, row: int, col: int):
        """双击表格单元格 - 跳转查词"""
        # 单词在第1列（复选框后）
        if col == 0:
            # 点击复选框列时切换选中状态
            item = self.result_table.item(row, 0)
            if item:
                new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                item.setCheckState(new_state)
            return
        word_item = self.result_table.item(row, 1)
        if word_item:
            word = word_item.text().strip()
            if word:
                logger.info(f"双击查词: {word}")
                self.word_lookup_requested.emit(word)

    def _on_item_changed(self, item):
        """复选框状态变化时更新计数"""
        if item.column() == 0:
            self._update_selected_count()
            self._highlight_selected_row(item.row())

    def _highlight_selected_row(self, row):
        """根据复选框状态高亮/取消高亮行"""
        chk = self.result_table.item(row, 0)
        is_checked = chk and chk.checkState() == Qt.Checked
        color = QColor('#E8F0FE') if is_checked else QColor('transparent')
        for col in range(self.result_table.columnCount()):
            table_item = self.result_table.item(row, col)
            if table_item and col != 0:
                table_item.setBackground(QBrush(color))

    def _update_selected_count(self):
        """更新已选单词计数和按钮文字"""
        count = 0
        total = self.result_table.rowCount()
        for row in range(total):
            item = self.result_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                count += 1
        self.selected_count_label.setText(f"已选: <b>{count}</b> 个词")
        self.add_vocab_btn.setText(f"➕ 加入单词本 ({count})")
        self.add_vocab_btn.setEnabled(count > 0)

    def _select_all(self):
        """全选所有行"""
        self.result_table.blockSignals(True)
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
                self._highlight_selected_row(row)
        self.result_table.blockSignals(False)
        self._update_selected_count()

    def _invert_selection(self):
        """反选"""
        self.result_table.blockSignals(True)
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 0)
            if item:
                new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                item.setCheckState(new_state)
                self._highlight_selected_row(row)
        self.result_table.blockSignals(False)
        self._update_selected_count()

    def _get_checked_words(self) -> list[str]:
        """获取所有勾选的单词列表"""
        words = []
        for row in range(self.result_table.rowCount()):
            chk = self.result_table.item(row, 0)
            if chk and chk.checkState() == Qt.Checked:
                word_item = self.result_table.item(row, 1)  # 第1列是单词
                if word_item:
                    words.append(word_item.text())
        return words

    def save_results(self):
        """保存分析结果"""
        if not self.analysis_result:
            QMessageBox.warning(self, "提示", "没有可保存的分析结果")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "保存结果", "analysis_result.csv", "CSV文件 (*.csv)"
        )
        
        if not path:
            return
        
        try:
            import csv
            words_data = self.analysis_result.get('words', [])
            
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['单词', '出现次数', '词性'])
                for item in words_data:
                    if len(item) >= 3:
                        writer.writerow([item[0], item[1], item[2]])
                    else:
                        writer.writerow([item[0], item[1], '-'])
            
            logger.info(f"分析结果已保存到: {path}")
            QMessageBox.information(self, "保存成功", f"结果已保存到:\n{path}")
        except Exception as e:
            logger.error(f"保存结果失败: {e}", exc_info=True)
            QMessageBox.critical(self, "保存失败", f"无法保存:\n{str(e)}")

    def add_to_vocabulary(self):
        """将勾选的单词添加到单词本"""
        words_to_add = self._get_checked_words()
        
        if not words_to_add:
            QMessageBox.information(self, "提示", "请先勾选要添加到单词本的词汇")
            return

        import sqlite3
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                
                added_count = 0
                skipped = []
                for word in words_to_add:
                    cursor.execute(
                        "INSERT OR IGNORE INTO vocabulary (word) VALUES (?)",
                        (word,)
                    )
                    if cursor.rowcount > 0:
                        added_count += 1
                    else:
                        skipped.append(word)
                
                conn.commit()
            
            # 成功后取消勾选
            self.result_table.blockSignals(True)
            for row in range(self.result_table.rowCount()):
                item = self.result_table.item(row, 0)
                if item and item.checkState() == Qt.Checked:
                    word_item = self.result_table.item(row, 1)
                    if word_item and word_item.text() not in skipped:
                        item.setCheckState(Qt.Unchecked)
                        self._highlight_selected_row(row)
            self.result_table.blockSignals(False)
            self._update_selected_count()

            logger.info(f"添加了 {added_count} 个单词到单词本")
            msg = f"成功将 {added_count} 个单词添加到单词本！"
            if skipped:
                msg += f"\n\n以下 {len(skipped)} 个词已存在：{', '.join(skipped[:10])}"
            QMessageBox.information(self, "成功", msg)
        except Exception as e:
            logger.error(f"添加到单词本失败: {e}", exc_info=True)
            QMessageBox.critical(self, "操作失败", str(e))





