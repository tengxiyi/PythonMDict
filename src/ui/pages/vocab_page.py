# -*- coding: utf-8 -*-
"""
单词本页面 (VocabPage)

功能模块：
- Tab1 列表视图：搜索/排序/统计/右键菜单/批量操作
- Tab2 闪卡学习：艾宾浩斯复习 + 会话总结

数据模型（vocabulary 表）：
  word TEXT PK          单词
  added_time REAL       添加时间戳
  next_review_time REAL 下次复习时间戳
  review_stage INTEGER  复习阶段(0=新词, 1~7=艾宾浩斯)
  xp INTEGER            经验值
  source TEXT           来源(Dict/News等)
  context TEXT          收藏时的语境
"""
import time
import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QTabWidget, QStackedWidget, QGridLayout, QMessageBox,
    QAbstractItemView, QApplication, QMenu, QComboBox,
    QGroupBox, QProgressBar
)
from PySide6.QtCore import Qt, QTimer, Signal, QPoint
from PySide6.QtGui import QColor

from ...core.config import DB_FILE, EBBINGHAUS_INTERVALS
from ...core.search_worker import SearchWorker
from ...core.quiz_worker import QuizWorker
from ...core.logger import logger

from ..widgets.mastery_ring import MasteryRing
from ..widgets.floating_text import FloatingText
from ..handlers.mdict_handler import MdictSchemeHandler


# 艾宾浩斯阶段名称映射
STAGE_NAMES = {
    0: "🌱 新词",      1: "⏰ 5分钟",
    2: "⏰ 30分钟",    3: "⏰ 12小时",
    4: "⏰ 1天",       5: "⏰ 2天",
    6: "⏰ 4天",       7: "✅ 已掌握"
}

# 阶段颜色
STAGE_COLORS = {
    0: "#FF9800", 1: "#FFB74D", 2: "#FFD54F",
    3: "#81C784", 4: "#4CAF50", 5: "#388E3C",
    6: "#1976D2", 7: "#303F9F"
}


class VocabPage(QWidget):
    """单词本页面：单词管理 + 闪卡复习"""

    def __init__(self):
        super().__init__()
        self._cached_data = []  # 全部数据缓存
        self._init_ui()
        logger.info("单词本页面初始化完成")

    # ==================== UI 构建 ====================

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(10)

        # ===== 顶部标题栏 =====
        header = QHBoxLayout()
        title = QLabel("📚 单词本")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #888; font-size: 13px;")
        header.addWidget(self.stats_label)
        layout.addLayout(header)

        # ===== Tab容器 =====
        self.tabs = QTabWidget()

        # Tab 1: 列表视图
        list_tab = QWidget()
        list_layout = QVBoxLayout(list_tab)
        list_layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("🔍"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索单词...")
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self._do_filter)
        toolbar.addWidget(self.search_input, stretch=1)

        toolbar.addWidget(QLabel("排序:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["最近添加", "按字母A-Z", "复习阶段", "经验值"])
        self.sort_combo.currentIndexChanged.connect(self._do_filter)
        toolbar.addWidget(self.sort_combo)

        toolbar.addSpacing(10)
        btn_del_selected = QPushButton("删除选中")
        btn_del_selected.clicked.connect(self._delete_selected)
        toolbar.addWidget(btn_del_selected)

        list_layout.addLayout(toolbar)

        # 数据表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["单词", "阶段", "来源", "XP", "添加时间"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 50)
        self.table.setColumnWidth(4, 130)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        list_layout.addWidget(self.table)

        # 底部操作栏
        bottom = QHBoxLayout()
        self.btn_export = QPushButton("📤 导出Anki")
        self.btn_export.clicked.connect(self.export_anki)
        bottom.addWidget(self.btn_export)
        bottom.addStretch()
        tip = QLabel("💡 双击查词 | 右键管理")
        tip.setStyleSheet("color: #aaa; font-size: 11px;")
        bottom.addWidget(tip)
        list_layout.addLayout(bottom)

        self.tabs.addTab(list_tab, "📋 列表")

        # Tab 2: 闪卡学习
        self.flashcard_widget = self._create_flashcard_ui()
        self.tabs.addTab(self.flashcard_widget, "🎴 闪卡")

        layout.addWidget(self.tabs)

        # Tab切换信号
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # 加载数据
        QTimer.singleShot(100, self.refresh_data)

    # ==================== Tab 1: 列表视图 ====================

    def refresh_data(self):
        """从数据库加载全部单词到缓存并刷新表格（与history_page.load_history保持一致的模式）"""
        try:
            with sqlite3.connect(DB_FILE) as conn:
                rows = conn.execute("""
                    SELECT word, review_stage, source, context, xp, added_time, next_review_time
                    FROM vocabulary ORDER BY added_time DESC
                """).fetchall()

            # 直接存为元组列表（和 history_page 完全一致）
            self._cached_data = list(rows)
            logger.info(f"单词本refresh_data: 从DB加载 {len(rows)} 条记录")

            self._update_stats()
            self._do_filter()
        except Exception as e:
            logger.error(f"加载单词本失败: {e}")

    def _update_stats(self):
        """更新顶部统计信息"""
        now = time.time()
        total = len(self._cached_data)
        due = sum(1 for r in self._cached_data if r[6] < now or r[1] == 0)
        mastered = sum(1 for r in self._cached_data if r[1] >= len(EBBINGHAUS_INTERVALS) - 1)
        total_xp = sum(r[4] or 0 for r in self._cached_data)

        text = f"共 {total} 词 | 待复习 {due} | 已掌握 {mastered} | 总XP {total_xp}"
        self.stats_label.setText(text)

    def _on_search_changed(self, text: str):
        """搜索框变化 -> 防抖300ms"""
        if hasattr(self, '_filter_timer'):
            self._filter_timer.stop()
        self._filter_timer = QTimer.singleShot(300, self._do_filter)

    def _do_filter(self):
        """客户端过滤+排序+渲染（与history_page一致的简洁模式）"""
        keyword = self.search_input.text().strip().lower()
        sort_mode = self.sort_combo.currentIndex()

        # 过滤
        filtered = []
        for r in self._cached_data:
            word = r[0]
            if keyword and keyword not in word.lower():
                continue
            filtered.append(r)

        # 排序
        if sort_mode == 0:
            filtered.sort(key=lambda x: -(x[5] or 0))
        elif sort_mode == 1:
            filtered.sort(key=lambda x: x[0].lower())
        elif sort_mode == 2:
            filtered.sort(key=lambda x: (-x[1] or 0, x[0]))
        else:
            filtered.sort(key=lambda x: -(x[4] or 0))

        # 渲染（与 history_page._update_table 完全一致）
        self.table.setRowCount(len(filtered))
        for row_idx, r in enumerate(filtered):
            w_str = str(r[0]) if r[0] else ""
            s_val = r[1] if r[1] is not None else 0

            self.table.setItem(row_idx, 0, QTableWidgetItem(w_str))

            color_hex = STAGE_COLORS.get(s_val, "#000000")
            it_s = QTableWidgetItem(STAGE_NAMES.get(s_val, str(s_val)))
            it_s.setForeground(QColor(color_hex))
            self.table.setItem(row_idx, 1, it_s)

            self.table.setItem(row_idx, 2, QTableWidgetItem(str(r[2]) if r[2] else ""))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(r[4] or 0)))
            try:
                ts = datetime.fromtimestamp(r[5]).strftime("%m-%d %H:%M") if r[5] else ""
            except Exception:
                ts = ""
            self.table.setItem(row_idx, 4, QTableWidgetItem(ts))

    def _on_row_double_clicked(self, index):
        """双击行 -> 跳转查词"""
        row = index.row()
        item = self.table.item(row, 0)
        if item and hasattr(self.window(), 'switch_to_search'):
            self.window().switch_to_search(item.text())

    def _show_context_menu(self, pos):
        """右键菜单"""
        item = self.table.itemAt(pos)
        if not item:
            return

        row = item.row()
        word_item = self.table.item(row, 0)
        word = word_item.text() if word_item else ""

        menu = QMenu(self)
        act_jump = menu.addAction("🔍 查询此词")
        act_jump.triggered.connect(lambda: self.window().switch_to_search(word))
        
        act_copy = menu.addAction("📋 复制单词")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(word))
        
        menu.addSeparator()
        act_del = menu.addAction("🗑 取消收藏")
        act_del.triggered.connect(lambda: self._unfavorite_word(word))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _unfavorite_word(self, word: str):
        """取消收藏单个单词"""
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("DELETE FROM vocabulary WHERE word=?", (word,))
                conn.commit()
            self._cached_data = [r for r in self._cached_data if r[0] != word]
            self._do_filter()
            self._update_stats()
            logger.info(f"已取消收藏: {word}")
        except Exception as e:
            logger.error(f"取消收藏失败({word}): {e}")

    def _delete_selected(self):
        """批量删除选中项"""
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.information(self, "提示", "请先选中要删除的行")
            return

        words = set()
        for item in selected:
            wi = self.table.item(item.row(), 0)
            if wi:
                words.add(wi.text())

        reply = QMessageBox.question(
            self, "确认删除",
            f'确定要删除选中的 {len(words)} 个单词吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with sqlite3.connect(DB_FILE) as conn:
                for w in words:
                    conn.execute("DELETE FROM vocabulary WHERE word=?", (w,))
                conn.commit()
            self._cached_data = [r for r in self._cached_data if r[0] not in words]
            self._do_filter()
            self._update_stats()
            logger.info(f"批量删除了 {len(words)} 个单词")
        except Exception as e:
            logger.error(f"批量删除失败: {e}")

    def export_anki(self):
        """导出为Anki TSV格式"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出Anki卡片", "geek_vocab.txt", "Text文件 (*.txt)"
        )
        if not path:
            return

        data_to_use = []  # 使用当前过滤后的数据或全部数据
        for row in range(self.table.rowCount()):
            wi = self.table.item(row, 0)
            ci = self.table.item(row, 3)  # context column
            si = self.table.item(row, 2)  # source column
            if wi:
                word = wi.text()
                back = ci.text() if ci else ""
                src = si.text() if si else ""
                data_to_use.append((word, back, src))

        if not data_to_use:
            QMessageBox.information(self, "提示", "没有可导出的数据")
            return

        try:
            with open(path, 'w', encoding='utf-8') as f:
                for word, ctx, src in data_to_use:
                    back = ctx or "(无备注)"
                    if src:
                        back += f"<br><small>来自: {src}</small>"
                    f.write(f"{word}\t{back}\n")

            QMessageBox.information(
                self, "导出成功",
                f'已导出 {len(data_to_use)} 个单词到:\n{path}'
            )
            logger.info(f"单词本已导出: {path} ({len(data_to_use)} 条)")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ==================== Tab 2: 闪卡学习 ====================

    def on_tab_changed(self, index: int):
        """Tab切换回调"""
        if index == 1:
            self.load_cards()
        elif index == 0:
            self.refresh_data()

    def _create_flashcard_ui(self) -> QWidget:
        """创建闪卡学习界面"""
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(10, 10, 10, 10)

        # === 顶部状态栏 ===
        top_bar = QHBoxLayout()

        self.mastery_ring = MasteryRing(w, size=48)
        top_bar.addWidget(self.mastery_ring)

        self.lbl_session_info = QLabel("点击「开始学习」开始复习")
        self.lbl_session_info.setStyleSheet(
            "font-size:14px;font-weight:bold;color:var(--text);margin-left:8px;"
        )
        top_bar.addWidget(self.lbl_session_info)
        top_bar.addStretch()

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m")
        top_bar.addWidget(self.progress_bar)

        l.addLayout(top_bar)

        # === 主内容区 (Stack) ===
        self.fc_stack = QStackedWidget()

        # Page 0: 空状态 / 开始按钮
        pg_start = QWidget()
        sl = QVBoxLayout(pg_start)
        sl.setAlignment(Qt.AlignCenter)

        lbl_icon = QLabel("📖")
        lbl_icon.setStyleSheet("font-size:64px;")
        lbl_icon.setAlignment(Qt.AlignCenter)
        sl.addWidget(lbl_icon)

        self.lbl_due_count = QLabel("")
        self.lbl_due_count.setStyleSheet("font-size:18px;color:#666;")
        self.lbl_due_count.setAlignment(Qt.AlignCenter)
        sl.addWidget(self.lbl_due_count)

        self.btn_start_session = QPushButton("🎯 开始学习")
        self.btn_start_session.setFixedSize(180, 48)
        self.btn_start_session.setCursor(Qt.PointingHandCursor)
        self.btn_start_session.setStyleSheet("""
            QPushButton {
                font-size: 16px; font-weight: bold; border-radius: 24px;
                background-color: #2196F3; color: white; border: none;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        self.btn_start_session.clicked.connect(self.start_session)
        sl.addWidget(self.btn_start_session)

        self.fc_stack.addWidget(pg_start)

        # Page 1: 测验面 (Quiz/Front)
        pg_quiz = QWidget()
        ql = QVBoxLayout(pg_quiz)
        ql.setSpacing(16)
        ql.addStretch()

        self.lbl_fc_word = QLabel("")
        self.lbl_fc_word.setAlignment(Qt.AlignCenter)
        self.lbl_fc_word.setStyleSheet("font-size:28px;font-weight:bold;color:var(--primary);")
        ql.addWidget(self.lbl_fc_word)

        self.lbl_sentence = QLabel("Loading...")
        self.lbl_sentence.setWordWrap(True)
        self.lbl_sentence.setAlignment(Qt.AlignCenter)
        self.lbl_sentence.setStyleSheet(
            "font-size:18px;font-style:italic;color:var(--text);padding:16px;"
        )
        ql.addWidget(self.lbl_sentence)

        self.grid_options = QGridLayout()
        self.option_btns = []
        for i in range(4):
            btn = QPushButton("")
            btn.setFixedHeight(56)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self.check_answer(idx))
            self.grid_options.addWidget(btn, i // 2, i % 2)
            self.option_btns.append(btn)
        ql.addLayout(self.grid_options)

        h_actions = QHBoxLayout()
        self.btn_show_answer = QPushButton("💡 我不会 / 显示释义")
        self.btn_show_answer.setFlat(True)
        self.btn_show_answer.clicked.connect(lambda: self.reveal_answer(False))
        h_actions.addWidget(self.btn_show_answer)

        self.btn_skip = QPushButton("⏭️ 跳过此词")
        self.btn_skip.setFlat(True)
        self.btn_skip.clicked.connect(self.skip_card)
        h_actions.addWidget(self.btn_skip)
        ql.addLayout(h_actions)

        ql.addStretch()
        self.fc_stack.addWidget(pg_quiz)

        # Page 2: 释义面 (Back/Detail)
        pg_back = QWidget()
        bl = QVBoxLayout(pg_back)

        self.lbl_result = QLabel("")
        self.lbl_result.setAlignment(Qt.AlignCenter)
        self.lbl_result.setStyleSheet("font-size:18px;font-weight:bold;margin-bottom:8px;")
        bl.addWidget(self.lbl_result)

        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineUrlScheme

        # registerScheme 已在 main_new.py 中提前完成
        self.web_fc = QWebEngineView()
        self.web_fc.page().profile().installUrlSchemeHandler(b"mdict", MdictSchemeHandler())
        bl.addWidget(self.web_fc)

        # 评分按钮
        h_rate = QHBoxLayout()
        btn_forget = QPushButton("❌ 忘记了 (重置)")
        btn_forget.setObjectName("BtnForget")
        btn_hard = QPushButton("😅 记得模糊")
        btn_hard.setObjectName("BtnHard")
        btn_good = QPushButton("✅ 记住了")
        btn_good.setObjectName("BtnGood")
        for btn in [btn_forget, btn_hard, btn_good]:
            btn.setFixedHeight(44)
            btn.setCursor(Qt.PointingHandCursor)
        btn_forget.clicked.connect(lambda: self.rate_card('forget'))
        btn_hard.clicked.connect(lambda: self.rate_card('hard'))
        btn_good.clicked.connect(lambda: self.rate_card('good'))
        h_rate.addWidget(btn_forget)
        h_rate.addWidget(btn_hard)
        h_rate.addWidget(btn_good)
        bl.addLayout(h_rate)

        self.fc_stack.addWidget(pg_back)

        # Page 3: 会话总结
        pg_summary = QWidget()
        sml = QVBoxLayout(pg_summary)
        sml.setAlignment(Qt.AlignCenter)

        self.lbl_summary_title = QLabel("🎉 学习完成!")
        self.lbl_summary_title.setStyleSheet("font-size:24px;font-weight:bold;")
        self.lbl_summary_title.setAlignment(Qt.AlignCenter)
        sml.addWidget(self.lbl_summary_title)

        self.lbl_summary_detail = QLabel("")
        self.lbl_summary_detail.setStyleSheet("font-size:15px;color:#555;padding:16px;")
        self.lbl_summary_detail.setAlignment(Qt.AlignCenter)
        self.lbl_summary_detail.setWordWrap(True)
        sml.addWidget(self.lbl_summary_detail)

        self.btn_restart = QPushButton("🔄 再来一轮")
        self.btn_restart.setCursor(Qt.PointingHandCursor)
        self.btn_restart.clicked.connect(self.start_session)
        sml.addWidget(self.btn_restart)

        self.fc_stack.addWidget(pg_summary)

        l.addWidget(self.fc_stack)

        # 状态变量
        self.card_queue = []
        self.current_card = None
        self.current_quiz_data = None
        self.session_results = {"correct": 0, "wrong": 0, "skipped": 0}

        return w

    # ---------- 闪卡逻辑 ----------

    def start_session(self):
        """开始新一轮学习"""
        self.load_cards()
        if not self.card_queue:
            return
        self.session_results = {"correct": 0, "wrong": 0, "skipped": 0}
        total = len(self.card_queue)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.next_card()

    def load_cards(self):
        """加载待复习的卡片队列"""
        now = time.time()
        try:
            with sqlite3.connect(DB_FILE) as conn:
                rows = conn.execute("""
                    SELECT word, review_stage, xp FROM vocabulary
                    WHERE next_review_time < ? OR review_stage = 0
                    ORDER BY next_review_time ASC LIMIT 30
                """, (now + 60,)).fetchall()
            self.card_queue = list(rows)
        except Exception as e:
            logger.error(f"加载复习卡片失败: {e}")
            self.card_queue = []

        due_count = len(self.card_queue)
        self.lbl_due_count.setText(f"当前有 {due_count} 张待复习卡片")

        if not self.card_queue:
            self.fc_stack.setCurrentIndex(0)  # 空状态页
            self.lbl_session_info.setText("暂无待复习卡片 🎉")

    def next_card(self):
        """显示下一张卡片"""
        if not self.card_queue:
            self._show_session_summary()
            return

        self.current_card = self.card_queue.pop(0)
        word, stage, xp_val = self.current_card

        # 更新进度
        reviewed = sum(self.session_results.values())
        remaining = len(self.card_queue) + 1
        self.progress_bar.setMaximum(reviewed + remaining)
        self.progress_bar.setValue(reviewed)
        self.lbl_session_info.setText(f"第 {reviewed + 1}/{reviewed + remaining} 张")

        # 更新掌握度环
        self.mastery_ring.set_mastery(stage)

        # 重置UI
        self.lbl_fc_word.setText(word)
        self.lbl_sentence.setText("正在生成题目...")
        self.fc_stack.setCurrentIndex(1)  # Quiz页

        for btn in self.option_btns:
            btn.setEnabled(False)
            btn.setText("...")
            btn.setStyleSheet("")
            btn.setVisible(True)

        # 启动测验题目生成
        self.quiz_worker = QuizWorker(word)
        self.quiz_worker.data_ready.connect(self.on_quiz_ready)
        self.quiz_worker.start()

        # 同时预加载释义
        self.worker = SearchWorker(word)
        self.worker.results_ready.connect(self.render_fc_back)
        self.worker.start()

    def on_quiz_ready(self, data: dict | None):
        """测验题目就绪"""
        self.current_quiz_data = data

        if data:
            self.lbl_sentence.setText(data['question'])
            self.lbl_fc_word.setVisible(False)
            options = data['options']
            for i, btn in enumerate(self.option_btns):
                btn.setText(options[i])
                btn.setEnabled(True)
                btn.setProperty("is_correct", options[i] == data['answer'])
            self.btn_show_answer.setText("💡 我不会 / 显示释义")
        else:
            self.lbl_sentence.setText("(未找到语境语句)")
            self.lbl_fc_word.setVisible(True)
            for btn in self.option_btns:
                btn.setVisible(False)
            self.btn_show_answer.setText("💡 显示释义")

    def check_answer(self, idx: int):
        """检查答案"""
        btn = self.option_btns[idx]
        is_correct = btn.property("is_correct")

        if is_correct:
            btn.setStyleSheet(
                "background-color:#a5d6a7;color:#1b5e20;border:2px solid #2e7d32;"
            )
            FloatingText(self, text="+50 XP", color="#2e7d32",
                         pos=btn.mapTo(self, QPoint(btn.width() // 2, 0)))
            self.session_results["correct"] += 1
            QTimer.singleShot(700, lambda: self.reveal_answer(True))
        else:
            btn.setStyleSheet("background-color:#ef9a9a;color:#b71c1c;")
            btn.setEnabled(False)
            FloatingText(self, text="再想想", color="#c62828",
                         pos=btn.mapTo(self, QPoint(btn.width() // 2, 0)))

    def reveal_answer(self, was_correct: bool):
        """展示释义（切到背面）"""
        self.fc_stack.setCurrentIndex(2)
        if was_correct:
            self.lbl_result.setText("✅ 回答正确！")
            self.lbl_result.setStyleSheet("color:#2e7d32;font-size:18px;font-weight:bold;")
        else:
            self.lbl_result.setText("查看释义 👇")
            self.lbl_result.setStyleSheet("color:var(--text);font-size:18px;")

    def skip_card(self):
        """跳过当前卡片"""
        self.session_results["skipped"] += 1
        self.next_card()

    def rate_card(self, rating: str):
        """
        根据用户评分更新艾宾浩斯间隔
        
        rating: 'forget'=重置到阶段0, 'hard'=不升级, 'good'=升一级
        """
        if not self.current_card:
            return

        w, stage, current_xp = self.current_card
        num_stages = len(EBBINGHAUS_INTERVALS) - 1

        if rating == 'forget':
            new_stage = 0
            xp_gain = 1
        elif rating == 'hard':
            new_stage = min(stage, num_stages)
            xp_gain = 5
        else:  # good
            new_stage = min(stage + 1, num_stages)
            xp_gain = 10 * max(new_stage, 1)

        new_xp = (current_xp or 0) + xp_gain
        next_t = time.time() + EBBINGHAUS_INTERVALS[new_stage]

        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    "UPDATE vocabulary SET review_stage=?, next_review_time=?, xp=? WHERE word=?",
                    (new_stage, next_t, new_xp, w)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"更新复习状态失败({w}): {e}")

        if rating != 'forget':
            self.session_results["correct"] += 1 if rating == 'good' else 0
        else:
            self.session_results["wrong"] += 1

        self.next_card()

    def render_fc_back(self, q: str, rows: list, suggestions: list):
        """渲染卡片背面的词典释义"""
        from ..theme_manager import theme_manager as _tm
        if not _tm:
            return
        css = _tm.get_webview_css()

        html_head = f"""
        <html><head><style>{css}
        body{{padding:15px;font-family:'Segoe UI',sans-serif;}}
        .dict-card{{border-bottom:1px solid var(--border);margin-bottom:16px;padding-bottom:12px;}}
        .dict-name{{color:var(--meta);font-size:11px;font-weight:bold;text-transform:uppercase;
                     margin-bottom:6px;display:block;}}
        </style></head><body>
        """

        if not rows:
            body = f"<h3>No definition found: {q}</h3>"
        else:
            parts = []
            for r in rows:
                parts.append(
                    f"<div class='dict-card'>"
                    f"<span class='dict-name'>{r['dict_name']}</span>"
                    f"<div class='entry-content'>{r['content']}</div></div>"
                )
            body = "".join(parts)

        html_end = "</body></html>"

        from PySide6.QtCore import QUrl
        self.web_fc.setHtml(html_head + body + html_end, baseUrl=QUrl("mdict://root/"))

    def _show_session_summary(self):
        """显示本次学习会话总结"""
        self.fc_stack.setCurrentIndex(3)  # 总结页
        c = self.session_results["correct"]
        w_ = self.session_results["wrong"]
        s = self.session_results["skipped"]
        total = c + w_ + s

        detail_lines = [
            f"本轮共复习 {total} 张卡片",
            f"",
            f"✅ 正确/记住: {c}",
            f"❌ 忘记/重置: {w_}",
            f"⏭️ 跳过: {s}",
        ]

        if c > 0:
            xp_total = c * 50  # 每个正确+50XP
            detail_lines.append(f"", f"🎯 获得 XP: +{xp_total}")

        self.lbl_summary_detail.setText("\n".join(detail_lines))
        self.lbl_session_info.setText("本轮结束 🏁")
