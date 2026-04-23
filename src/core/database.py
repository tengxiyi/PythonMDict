# file: src/core/database.py
# -*- coding: utf-8 -*-
"""
数据库管理模块
负责SQLite数据库的初始化、表结构管理
"""
import sqlite3
import logging

from .config import DB_FILE, MDD_DB_FILE
from .logger import logger


class DatabaseManager:
    """数据库初始化和表结构管理"""
    
    @staticmethod
    def init_db():
        """初始化所有数据库表结构"""
        logger.info("正在初始化数据库...")
        
        try:
            DatabaseManager._init_dict_db()
            DatabaseManager._init_mdd_db()
            logger.info("数据库初始化完成")
        except Exception as e:
            logger.critical(f"数据库初始化失败: {e}", exc_info=True)
            raise
    
    @staticmethod
    def _init_dict_db():
        """初始化主数据库 (dict_cache.db)"""
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            
            # 词典信息表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dict_info (
                    id INTEGER PRIMARY KEY, 
                    path TEXT UNIQUE, 
                    name TEXT, 
                    mdd_path TEXT, 
                    priority INTEGER DEFAULT 0
                )
            """)
            
            # 标准词条表（内容zlib压缩）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS standard_entries (
                    word TEXT, 
                    content BLOB, 
                    dict_id INTEGER, 
                    length INTEGER
                )
            """)
            # 单列索引（向后兼容）
            conn.execute("CREATE INDEX IF NOT EXISTS idx_word ON standard_entries(word COLLATE NOCASE)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dict ON standard_entries(dict_id)")

            # 复合索引：覆盖高频查询 WHERE word=? AND dict_id=?
            # 同时可服务于 word 单列查询（前缀匹配）和 LIKE 前缀扫描
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_word_dict "
                "ON standard_entries(word COLLATE NOCASE, dict_id)"
            )
            
            # FTS5 全文检索表
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS fts_entries USING fts5(word, content_text, dict_id UNINDEXED)"
            )
            
            # 单词本（含艾宾浩斯复习算法）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vocabulary (
                    word TEXT PRIMARY KEY, 
                    added_time REAL, 
                    review_stage INTEGER DEFAULT 0, 
                    next_review_time REAL DEFAULT 0,
                    context TEXT, 
                    source TEXT,
                    xp INTEGER DEFAULT 0
                )
            """)
            
            # 兼容性：为旧版本添加列
            try:
                conn.execute("ALTER TABLE vocabulary ADD COLUMN xp INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # 列已存在
            try:
                conn.execute("ALTER TABLE vocabulary ADD COLUMN source TEXT")
            except sqlite3.OperationalError:
                pass
            
            # 搜索历史
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    word TEXT PRIMARY KEY, 
                    last_access_time REAL,
                    search_count INTEGER DEFAULT 1
                )
            """)
            
            # RSS新闻源配置
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rss_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    url TEXT UNIQUE,
                    enabled INTEGER DEFAULT 1
                )
            """)
            
            # 填充默认RSS源
            cur = conn.execute("SELECT count(*) FROM rss_sources")
            if cur.fetchone()[0] == 0:
                defaults = [
                    ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
                    ("NPR News", "https://feeds.npr.org/1001/rss.xml"),
                    ("TechCrunch", "https://techcrunch.com/feed/"),
                    ("China Daily World", "http://www.chinadaily.com.cn/rss/world_rss.xml"),
                ]
                conn.executemany("INSERT INTO rss_sources (name, url) VALUES (?, ?)", defaults)
                conn.commit()
    
    @staticmethod
    def _init_mdd_db():
        """初始化MDD资源缓存数据库"""
        with sqlite3.connect(MDD_DB_FILE, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            
            # MDD资源缓存表
            conn.execute(
                """CREATE TABLE IF NOT EXISTS resources 
                   (dict_id INTEGER, norm_key TEXT, data BLOB, 
                    PRIMARY KEY (dict_id, norm_key))"""
            )
            
            # 导入记录表
            conn.execute(
                """CREATE TABLE IF NOT EXISTS cached_dicts 
                   (dict_id INTEGER PRIMARY KEY, mdd_path TEXT, cached_time REAL)"""
            )


def get_connection(db_file: str = DB_FILE, **kwargs) -> sqlite3.Connection:
    """
    获取数据库连接的便捷函数
    
    Args:
        db_file: 数据库文件路径
        **kwargs: 传递给sqlite3.connect的额外参数
        
    Returns:
        数据库连接对象
    """
    return sqlite3.connect(db_file, **kwargs)
