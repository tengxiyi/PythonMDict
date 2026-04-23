# file: src/core/indexer_worker.py
# -*- coding: utf-8 -*-
"""
MDX/MDD 词典导入索引工作线程
负责读取MDX词典文件并将词条写入数据库
"""
import os
import sqlite3
import time

from PySide6.QtCore import QThread, Signal

from .config import DB_FILE, MDD_DB_FILE, IMPORT_MDX_BATCH_SIZE, IMPORT_MDD_BATCH_SIZE
from .utils import pre_process_entry_content, space_cjk, RE_HTML_TAG, RE_WHITESPACE, VALID_WORD
from .logger import logger
from .connection_pool import pool


class IndexerWorker(QThread):
    """
    MDX/MDD词典导入工作线程
    
    Signals:
        progress(int, int, str): 导入进度 (current, total, message)
        finished(dict):          导入完成 (result info)
        error(str):              错误信息
    """
    progress = Signal(int, int, str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, file_path: str, db_file: str, priority: int = 0):
        super().__init__()
        self.file_path = file_path
        self.db_file = db_file
        self.priority = priority

    def run(self):
        """执行单个MDX词典文件的导入"""
        p = self.file_path
        try:
            from readmdict import MDX
        except ImportError:
            self.error.emit("Error: missing readmdict library! Run: pip install readmdict")
            logger.error("Missing readmdict")
            return

        name = os.path.basename(p)[:-4]

        # 先尝试估算总词条数（用于进度条）
        self.progress.emit(0, 100, f"Loading {name}...")
        
        # 注册词典到数据库
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM dict_info WHERE path=?", (p,))
            if cur.fetchone():
                self.error.emit(f"{name} 已存在")
                return

            cur.execute(
                "INSERT INTO dict_info (path, name, mdd_path, priority) VALUES (?, ?, ?, ?)",
                (p, name, None, self.priority)
            )
            did = cur.lastrowid
            conn.commit()

        # 收集MDD资源文件
        mdd_paths = self._collect_mdd_paths(p)

        try:
            # 导入MDX词条（内部会估算总数并报告进度）
            count = self.process_mdx(p, did, name)
            
            # 导入MDD资源
            if mdd_paths:
                self.process_mdd(mdd_paths, did, name)

            # 导入完成后触发 WAL checkpoint，合并大量写入产生的 WAL 文件
            pool.checkpoint(mode="TRUNCATE")
            logger.info(f"{name}: 导入完成，WAL 已合并")

            result = {'name': name, 'count': count, 'path': p}
            self.finished.emit(result)
            
        except Exception as e:
            logger.error(f"导入词典失败 [{p}]: {e}", exc_info=True)
            self.error.emit(str(e))

    def _collect_mdd_paths(self, mdx_path: str) -> list[str]:
        """收集与MDX文件同目录且同前缀的所有MDD资源文件"""
        mdd_paths = []
        try:
            mdx_dir = os.path.dirname(mdx_path)
            mdx_base = os.path.basename(mdx_path)[:-4]
            primary_mdd = mdx_path[:-4] + ".mdd"
            
            if os.path.exists(primary_mdd):
                mdd_paths.append(primary_mdd)

            if mdx_dir and os.path.isdir(mdx_dir):
                for fn in os.listdir(mdx_dir):
                    low = fn.lower()
                    if not low.endswith('.mdd'):
                        continue
                    if not low.startswith(mdx_base.lower()):
                        continue
                    full = os.path.join(mdx_dir, fn)
                    if os.path.normcase(full) != os.path.normcase(primary_mdd):
                        if os.path.exists(full) and os.path.isfile(full):
                            mdd_paths.append(full)
        except Exception as e:
            logger.debug(f"MDD文件扫描失败: {e}")
        
        return mdd_paths

    def process_mdx(self, path: str, did: int, name: str) -> int:
        """处理单个MDX词典文件的词条导入，返回导入的词条数量"""
        try:
            from readmdict import MDX
            mdx = MDX(path)
        except Exception as e:
            logger.error(f"解析MDX失败 ({name}): {e}")
            raise

        batch_std = []
        batch_fts = []
        batch_browse = []  # 干净单词列表（用于词典浏览）
        count = 0
        total_count = 0  # 实际处理的条目数（用于进度条）
        
        # 先快速遍历一次估算总数
        self.progress.emit(0, 100, f"Estimating {name}...")
        estimated_total = 100000  # 默认预估值
        
        try:
            # 尝试获取实际条目数（readmdix MDX 对象通常有这个属性）
            if hasattr(mdx, '_nitems'):
                estimated_total = max(mdx._nitems, 1000)
                logger.info(f"{name}: 预估条目数: {estimated_total}")
        except Exception:
            pass

        try:
            with sqlite3.connect(DB_FILE, timeout=30) as conn:
                # 导入专用 PRAGMA：最大化写入吞吐量
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=OFF;")
                conn.execute("PRAGMA cache_size=-50000;")     # 导入时用 ~100MB 缓存（比读连接更大）
                conn.execute("PRAGMA mmap_size=536870912;")    # 512MB 内存映射
                conn.execute("PRAGMA temp_store=MEMORY;")      # 临时表/排序使用内存

                conn.execute("BEGIN TRANSACTION")

                try:
                    iterator = mdx.items()
                except Exception as e:
                    logger.error(f"读取MDX内容失败 ({name}): {e}")
                    raise

                for k_bytes, v_bytes in iterator:
                    try:
                        k_s = k_bytes.decode('utf-8').strip()
                    except UnicodeDecodeError:
                        try:
                            k_s = k_bytes.decode('gbk', 'ignore').strip()
                        except UnicodeDecodeError:
                            continue

                    if not k_s:
                        continue

                    try:
                        v_c = pre_process_entry_content(v_bytes, did)
                        
                        try:
                            content_str = v_bytes.decode('utf-8')[:2000]
                        except UnicodeDecodeError:
                            content_str = v_bytes.decode('utf-8', 'ignore')[:2000]

                        if content_str:
                            plain_text = RE_WHITESPACE.sub(
                                ' ', space_cjk(RE_HTML_TAG.sub(' ', content_str))
                            ).strip()
                            if plain_text:
                                batch_fts.append((k_s, plain_text, did))

                        batch_std.append((k_s, v_c, did, len(k_s)))

                        # 过滤出干净的英文单词，写入浏览专用表
                        # VALID_WORD: 函数形式，综合判断（正则 + 排除 's 所有格后缀）
                        if VALID_WORD(k_s):
                            batch_browse.append((k_s, did))

                    except Exception:
                        continue

                    total_count += 1

                    # 更频繁地报告进度（每批量写入或每1000条进度更新）
                    if len(batch_std) >= IMPORT_MDX_BATCH_SIZE or total_count % 1000 == 0:
                        try:
                            if len(batch_std) >= IMPORT_MDX_BATCH_SIZE:
                                conn.executemany(
                                    "INSERT INTO standard_entries VALUES (?,?,?,?)",
                                    batch_std
                                )
                                conn.executemany(
                                    "INSERT INTO fts_entries(word, content_text, dict_id) VALUES (?,?,?)",
                                    batch_fts
                                )
                                # 写入干净单词到浏览表（忽略重复）
                                if batch_browse:
                                    conn.executemany(
                                        "INSERT OR IGNORE INTO dict_browse_words(word, dict_id) VALUES (?,?)",
                                        batch_browse
                                    )
                                    batch_browse = []
                                conn.commit()
                                conn.execute("BEGIN TRANSACTION")
                                count += len(batch_std)
                                batch_std = []
                                batch_fts = []

                            # 计算进度百分比
                            pct = min(int(total_count / estimated_total * 100), 99)
                            self.progress.emit(total_count, estimated_total, 
                                             f"{name}: {total_count} entries ({pct}%)")
                        except sqlite3.OperationalError as db_e:
                            logger.warning(f"批量写入数据库错误: {db_e}")
                            time.sleep(1)

                # 写入剩余数据
                if batch_std:
                    conn.executemany(
                        "INSERT INTO standard_entries VALUES (?,?,?,?)",
                        batch_std
                    )
                    conn.executemany(
                        "INSERT INTO fts_entries(word, content_text, dict_id) VALUES (?,?,?)",
                        batch_fts
                    )
                    # 写入剩余的干净单词
                    if batch_browse:
                        conn.executemany(
                            "INSERT OR IGNORE INTO dict_browse_words(word, dict_id) VALUES (?,?)",
                            batch_browse
                        )
                    conn.commit()
                    count += len(batch_std)

                # 过滤复数形式（如果原形已存在，则去掉复数）
                filtered = self._filter_plural_forms(conn, did)
                if filtered:
                    logger.info(f"{name}: 过滤复数形式 {filtered} 个")

                logger.info(f"{name}: Total imported {count} entries")
                
                # 最终进度：完成
                self.progress.emit(estimated_total, estimated_total, f"{name}: Done! {count} entries")

                return count

        except Exception as e:
            logger.error(f"MDX导入异常 ({name}): {e}", exc_info=True)
            raise

    def _filter_plural_forms(self, conn: sqlite3.Connection, did: int) -> int:
        """清理浏览表中已存在原形的复数形式单词，返回删除数量"""
        rows = conn.execute(
            "SELECT word FROM dict_browse_words WHERE dict_id=? ORDER BY word", (did,)
        ).fetchall()
        if not rows:
            return 0

        word_set = {w[0].lower() for w in rows}
        to_delete = []

        for (word,) in rows:
            w = word.lower()
            singular = None
            # 优先级：ies -> es -> s，避免重叠误判
            if w.endswith('ies') and len(w) > 4:
                candidate = w[:-3] + 'y'
                if candidate in word_set:
                    singular = candidate
            elif w.endswith('es') and len(w) > 3:
                candidate = w[:-2]
                if candidate in word_set:
                    singular = candidate
            elif w.endswith('s') and len(w) > 2:
                candidate = w[:-1]
                if candidate in word_set:
                    singular = candidate

            if singular:
                to_delete.append(word)

        if to_delete:
            conn.executemany(
                "DELETE FROM dict_browse_words WHERE word=? AND dict_id=?",
                [(w, did) for w in to_delete]
            )
            conn.commit()
        return len(to_delete)

    def process_mdd(self, mdd_paths: list[str], did: int, name: str):
        """处理MDD资源文件的导入"""
        if not mdd_paths:
            return

        self.progress.emit(0, 100, f"正在导入资源: {name}... (mdd x{len(mdd_paths)})")

        batch = []
        count = 0

        try:
            from readmdict import MDD
        except ImportError as e:
            logger.error(f"缺少readmdict库，无法导入MDD: {e}")
            self.error.emit(f"缺少 readmdict 库: {e}")
            return

        try:
            with sqlite3.connect(MDD_DB_FILE, timeout=30) as conn:
                # 导入专用 PRAGMA
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=OFF;")
                conn.execute("PRAGMA temp_store=MEMORY;")

                conn.execute("BEGIN TRANSACTION")

                conn.execute("DELETE FROM resources WHERE dict_id=?", (did,))

                for one_path in mdd_paths:
                    try:
                        mdd = MDD(one_path)
                    except Exception as e:
                        logger.warning(f"无法加载MDD [{one_path}]: {e}")
                        self.error.emit(f"无法加载 MDD: {os.path.basename(one_path)}")
                        continue

                    for k_bytes, v_bytes in mdd.items():
                        try:
                            try:
                                k_str = k_bytes.decode('utf-8')
                            except UnicodeDecodeError:
                                try:
                                    k_str = k_bytes.decode('gbk')
                                except UnicodeDecodeError:
                                    k_str = k_bytes.decode('utf-8', 'ignore')

                            norm_key = k_str.replace('/', '\\').upper().strip()
                            norm_key = '\\' + norm_key.lstrip('\\')
                            norm_key = norm_key.replace('\x00', '')
                            batch.append((did, norm_key, v_bytes))
                        except Exception:
                            continue

                        if len(batch) >= IMPORT_MDD_BATCH_SIZE:
                            conn.executemany(
                                "INSERT OR IGNORE INTO resources VALUES (?,?,?)",
                                batch
                            )
                            batch = []
                            count += IMPORT_MDD_BATCH_SIZE
                            if count % 2000 == 0:
                                self.progress.emit(count, max(count, 1000), f"{name}: cached {count} resources")

                if batch:
                    conn.executemany(
                        "INSERT OR IGNORE INTO resources VALUES (?,?,?)",
                        batch
                    )

                conn.execute(
                    "INSERT OR REPLACE INTO cached_dicts VALUES (?,?,?)",
                    (did, ';'.join(mdd_paths), time.time())
                )
                conn.commit()
                logger.info(f"{name}: 共导入 {count + len(batch)} 条MDD资源")

        except Exception as e:
            logger.error(f"MDD导入异常 ({name}): {e}", exc_info=True)
            self.error.emit(f"MDD 导入错误: {str(e)}")
