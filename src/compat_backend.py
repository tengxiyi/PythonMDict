# -*- coding: utf-8 -*-
"""
backend.py - 向后兼容的重导出模块

为了保持对可能的外部引用或脚本的兼容性，
将原有的 backend.py 重构为重导出模块。

新的实现代码位于 src/core/ 目录下。
"""

# 核心配置常量
from src.core.config import (
    DB_FILE,
    MDD_DB_FILE,
    EBBINGHAUS_INTERVALS,
    SEARCH_BATCH_FIRST,  # 原名: SEARCH_BATCH_FIRST (原名为BATCH_SIZE_FIRST)
    APP_NAME,
    APP_VERSION,
)

# 数据库管理器
from src.core.database import DatabaseManager

# 工作线程
from src.core.search_worker import SearchWorker
from src.core.indexer_worker import IndexerWorker
from src.core.quiz_worker import QuizWorker
from src.core.analyzer_worker import AnalyzerWorker
from src.core.news_workers import RSSTestWorker, NewsContentWorker, NewsWorker

# 工具函数
from src.core.utils import (
    fetch_url_content,       # 原名: fetch_url_content
    extract_text_from_epub,
    strip_tags as clean_html_text,
    pre_process_entry_content,
    process_entry_task,
    space_cjk,
    is_pure_english,
    clean_sentence_text,
    get_opencc,
    STOP_WORDS,
)

# 日志工具
from src.core.logger import get_logger, log_exception

# 兼容性别名（原backend.py中的全局变量）
CSS_CACHE = {}  # CSS缓存字典
IFRAME_HTML_CACHE = {}  # iframe HTML缓存
PHYSICAL_RES_INDEX = {}  # 物理资源索引

# 兼容常量别名
MAX_SEARCH_RESULTS = 50  # 默认最大搜索结果数
BATCH_SIZE_FIRST = SEARCH_BATCH_FIRST  # 别名

__all__ = [
    # 配置
    'DB_FILE', 'MDD_DB_FILE', 'EBBINGHAUS_INTERVALS',
    'MAX_SEARCH_RESULTS', 'BATCH_SIZE_FIRST', 'SEARCH_BATCH_FIRST',
    'APP_NAME', 'APP_VERSION',
    # 全局缓存
    'CSS_CACHE', 'IFRAME_HTML_CACHE', 'PHYSICAL_RES_INDEX',
    # 类
    'DatabaseManager', 'SearchWorker', 'IndexerWorker',
    'QuizWorker', 'AnalyzerWorker',
    'RSSTestWorker', 'NewsContentWorker', 'NewsWorker',
    # 函数
    'fetch_url_content', 'extract_text_from_epub',
    'clean_html_text', 'pre_process_entry_content',
    'process_entry_task', 'space_cjk', 
    'is_pure_english', 'clean_sentence_text',
    'get_opencc', 'STOP_WORDS',
    # 日志
    'get_logger', 'log_exception',
]
