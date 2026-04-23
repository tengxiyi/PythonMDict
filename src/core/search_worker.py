# file: src/core/search_worker.py
# -*- coding: utf-8 -*-
"""
搜索工作线程
负责词典搜索的异步执行，支持中英文混合搜索、FTS全文检索、简繁转换
"""
import sqlite3
import time

from PySide6.QtCore import QThread, Signal

from .config import DB_FILE
from .utils import process_entry_task, space_cjk, get_opencc
from .logger import logger
from .connection_pool import pool
from concurrent.futures import ThreadPoolExecutor

# 全局线程池复用
_max_workers = (__import__('os').cpu_count() or 4) + 2
GLOBAL_EXECUTOR = ThreadPoolExecutor(max_workers=_max_workers)


class SearchWorker(QThread):
    """
    查词异步工作线程
    
    Signals:
        results_ready(str, list, list): 发射 (查询词, 结果列表, 建议列表)
    """
    results_ready = Signal(str, list, list)

    def __init__(self, query: str):
        super().__init__()
        self.query = query

    def run(self):
        q = self.query.strip()

        if not q:
            self.results_ready.emit(q, [], [])
            return

        raw_candidates = []

        # 根据是否包含中文选择不同的搜索策略
        has_cjk = any('\u4e00' <= c <= '\u9fff' for c in q)

        try:
            # 使用连接池复用线程本地连接（避免每次搜索都新建连接 ~5-20ms）
            conn = pool.get()
            cursor = conn.cursor()

            # 获取词典映射
            cursor.execute("SELECT id, name, priority, path FROM dict_info ORDER BY priority DESC")
            dict_map = {d[0]: {'name': d[1], 'pri': d[2], 'path': d[3]} for d in cursor.fetchall()}

            # 英文：仅精确匹配（大小写不敏感）
            if not has_cjk:
                cursor.execute(
                    "SELECT word, NULL, dict_id, 1 FROM standard_entries WHERE word = ? COLLATE NOCASE",
                    (q,)
                )
                raw_candidates.extend(cursor.fetchall())
            else:
                    # 中文：精确 + FTS全文检索 + 简繁转换
                    cursor.execute("SELECT word, NULL, dict_id, 1 FROM standard_entries WHERE word = ?", (q,))
                    raw_candidates.extend(cursor.fetchall())

                    search_terms = {q}
                    
                    # 尝试简繁转换扩展搜索词
                    s2t = get_opencc('s2t')
                    t2s = get_opencc('t2s')

                    if s2t:
                        try:
                            search_terms.add(s2t.convert(q))
                            if t2s:
                                search_terms.add(t2s.convert(q))
                        except Exception:
                            pass

                    # FTS5 全文检索
                    fts_query_parts = []
                    for t in search_terms:
                        cleaned = space_cjk(t).strip()
                        if not cleaned:
                            continue
                        fts_query_parts.append(f'"{cleaned}"')

                    if fts_query_parts:
                        fts_q_str = " OR ".join(fts_query_parts)
                        try:
                            cursor.execute(
                                "SELECT word, dict_id, content_text FROM fts_entries WHERE fts_entries MATCH ? LIMIT 50",
                                (fts_q_str,)
                            )
                            for r_word, r_did, r_text in cursor.fetchall():
                                if any(x[0] == r_word and x[2] == r_did for x in raw_candidates):
                                    continue
                                len_score = len(r_word) / 100.0
                                raw_candidates.append((r_word, None, r_did, 3.0 + len_score))
                        except Exception as e:
                            logger.debug(f"FTS查询失败: {e}")

        except sqlite3.OperationalError as e:
            logger.error(f"搜索数据库错误: {e}")

        # 排序 & 截断
        # 排序：按分数升序 + 优先级降序（取负值使高优先级排在前面）
        raw_candidates.sort(key=lambda x: (x[3], -dict_map.get(x[2], {}).get('pri', 0), len(x[0])))
        final_candidates = raw_candidates[:30]

        # 准备渲染数据
        tasks_data = []
        seen = set()

        for item in final_candidates:
            r_word, r_blob, d_id, r_score = item
            key = f"{r_word}_{d_id}"
            if key in seen:
                continue
            seen.add(key)

            if r_blob is None:
                try:
                    # 复用同一连接，无需新建（消除第二次连接开销）
                    row = conn.execute(
                        "SELECT content FROM standard_entries WHERE word=? AND dict_id=?",
                        (r_word, d_id)
                    ).fetchone()
                    if row:
                        r_blob = row[0]
                    else:
                        continue
                except Exception as e:
                    logger.debug(f"读取词条失败({r_word}, did={d_id}): {e}")
                    continue

            d_info = dict_map.get(d_id, {'name': '未知', 'path': None})
            tasks_data.append((r_word, r_blob, d_id, r_score, d_info))

        # 分批返回（首批快速响应）
        if tasks_data:
            try:
                batch_size = 3
                batch_1 = tasks_data[:batch_size]
                batch_2 = tasks_data[batch_size:]

                results_1 = list(GLOBAL_EXECUTOR.map(process_entry_task, batch_1))
                if results_1:
                    self.results_ready.emit(q, results_1, [])

                if batch_2:
                    results_2 = list(GLOBAL_EXECUTOR.map(process_entry_task, batch_2))
                    full_results = results_1 + results_2
                    self.results_ready.emit(q, full_results, [])

            except Exception as e:
                logger.error(f"搜索结果渲染失败: {e}")
                self.results_ready.emit(q, [], [])
        else:
            # 无结果时提供拼写建议
            suggestions = self._get_suggestions(q, has_cjk)
            self.results_ready.emit(q, [], suggestions)

    def _get_suggestions(self, query: str, has_cjk: bool) -> list:
        """获取搜索建议词"""
        if len(query) > 2 and not has_cjk:
            try:
                conn = pool.get()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT word FROM standard_entries WHERE word LIKE ? COLLATE NOCASE LIMIT 5",
                    (f"{query[:2]}%",)
                )
                return [r[0] for r in cursor.fetchall()]
            except Exception as e:
                logger.debug(f"获取建议词失败: {e}")
        return []
