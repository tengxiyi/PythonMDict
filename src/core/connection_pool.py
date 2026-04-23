# file: src/core/connection_pool.py
# -*- coding: utf-8 -*-
"""
数据库连接池 — 线程本地连接复用

解决每次查询都新建SQLite连接的性能问题。
每个线程持有一个持久连接，避免重复创建的开销(5-20ms/次)。

适用场景:
  - 高频读取: 搜索、查词、闪卡、Web资源加载
不适用场景:
  - 导入索引(indexer_worker): 长事务批量写入, 需要独立控制PRAGMA
  - 数据库初始化(database.py): 一次性建表操作
"""
import sqlite3
import threading
from .config import DB_FILE, MDD_DB_FILE
from .logger import logger


class _PoolEntry:
    """单个数据库的线程本地连接缓存"""

    def __init__(self, db_file: str, read_only: bool = False,
                 timeout: int = 10, cache_size: int = -20000):
        self._db_file = db_file
        self._read_only = read_only
        self._timeout = timeout
        self._cache_size = cache_size
        self._local = threading.local()

    def get(self) -> sqlite3.Connection:
        """获取当前线程的连接(懒加载)"""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(
                self._db_file,
                timeout=self._timeout,
                check_same_thread=False,
            )
            # 读优化 PRAGMA
            if self._read_only:
                try:
                    conn.execute("PRAGMA query_only=1;")
                    conn.execute("PRAGMA mmap_size=536870912;")  # 512MB内存映射
                except Exception:
                    pass
            # WAL 模式：提高自动检查点阈值，减少阻塞频率（默认1000页≈4MB）
            try:
                conn.execute("PRAGMA wal_autocheckpoint=10000;")  # ~40MB
            except Exception:
                pass
            # 共享页面缓存 (~80MB)
            try:
                conn.execute(f"PRAGMA cache_size={self._cache_size};")
            except Exception:
                pass

            self._local.conn = conn
            logger.debug(f"[ConnectionPool] 新建连接: {self._db_file} "
                         f"(thread={threading.current_thread().name})")
        return conn

    def close(self):
        """关闭当前线程的连接"""
        conn = getattr(self._local, 'conn', None)
        if conn is not None:
            try:
                conn.close()
            except Exception as e:
                logger.debug(f"[ConnectionPool] 关闭连接异常: {e}")
            self._local.conn = None


class ConnectionPool:
    """
    全局数据库连接池管理器

    使用方式:
        from src.core.connection_pool import pool
        conn = pool.get()          # 主库只读连接
        conn_mdd = pool.get_mdd()  # MDD资源库连接
        # 用完后不需要 close, 线程退出时自动清理
    """

    def __init__(self):
        # 主库(dict_cache.db) — 只读优化连接
        self._db_pool = _PoolEntry(DB_FILE, read_only=True)
        # MDD资源库(mdd_cache.db) — 读写均可
        self._mdd_pool = _PoolEntry(MDD_DB_FILE, read_only=True)

    def get(self) -> sqlite3.Connection:
        """获取主数据库连接(读优化)"""
        return self._db_pool.get()

    def get_mdd(self) -> sqlite3.Connection:
        """获取MDD资源数据库连接"""
        return self._mdd_pool.get()

    def checkpoint(self, db_file: str = DB_FILE, mode: str = "PASSIVE") -> bool:
        """
        显式触发 WAL checkpoint，将 WAL 文件内容合并回主数据库。

        Args:
            db_file: 数据库文件路径
            mode: checkpoint 模式:
                - PASSIVE (默认): 不阻塞, 只合并已完成的帧
                - NORMAL: 合并到最新, 可能短暂阻塞写入
                - TRUNCATE: 完全合并并回收 WAL 空间 (退出时用)
                - RESTART: 阻塞所有读写直到完成

        Returns:
            是否成功执行
        """
        try:
            conn = sqlite3.connect(db_file, timeout=5)
            try:
                result = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
                logger.debug(
                    f"[Checkpoint] {db_file} mode={mode} "
                    f"checkpointed={result[0]}, backlog={result[1]}"
                )
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"[Checkpoint] 失败 ({mode}): {e}")
            return False

    def get_raw(self, db_file: str = DB_FILE,
                timeout: int = 10) -> sqlite3.Connection:
        """
        获取一个无特殊PRAGMA的原始连接
        用于需要写入的场景(如vocab_page中的INSERT/UPDATE)
        """
        local = threading.local()
        key = f"raw_{id(db_file)}"
        conn = getattr(local, key, None)
        if conn is None:
            conn = sqlite3.connect(db_file, timeout=timeout,
                                   check_same_thread=False)
            setattr(local, key, conn)
        return conn

    def close_all(self):
        """关闭当前线程的所有连接(通常在线程结束时调用)"""
        self._db_pool.close()
        self._mdd_pool.close()


# 全局单例
pool = ConnectionPool()
