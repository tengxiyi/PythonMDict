# file: src/core/config.py
# -*- coding: utf-8 -*-
"""
全局配置常量
集中管理所有配置项，避免全局状态散落各处
"""
import os

# 应用信息
APP_NAME = "极客词典Pro"
APP_VERSION = "3.0.0"

# 数据库文件路径
DB_FILE = "dict_cache.db"
MDD_DB_FILE = "mdd_cache.db"

# 艾宾浩斯复习间隔（秒）- 7级间隔算法
EBBINGHAUS_INTERVALS = [300, 1800, 43200, 86400, 172800, 345600, 604800, 1296000]

# 主题配置文件路径
THEME_CONFIG_FILE = "theme_config.json"

# 剪贴板监听文本长度限制
CLIPBOARD_MIN_LEN = 2
CLIPBOARD_MAX_LEN = 40

# 搜索结果批次大小
SEARCH_BATCH_FIRST = 3  # 首批返回数量（快速响应）

# 索引批处理大小
INDEXER_BATCH_SIZE_STD = 2000  # 词条批量写入大小
INDEXER_BATCH_SIZE_MDD = 500    # MDD资源批量写入大小

# 分析器限制
ANALYZER_MAX_RESULTS = 1000      # 最大返回结果数
ANALYZER_CHUNK_SIZE = 900         # 数据库查询分块大小

# 测验配置
QUIZ_MIN_WORD_LEN = 2
QUIZ_MAX_WORD_LEN = 20
QUIZ_MAX_ATTEMPTS = 20
QUIZ_SENTENCE_MIN_LEN = 20
QUIZ_SENTENCE_MAX_LEN = 200
QUIZ_ENG_RATIO_THRESHOLD = 0.7   # 英文字符占比阈值

# 物理资源扫描允许的扩展名
RESOURCE_ALLOW_EXTS = (
    '.css', '.js',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
    '.mp3', '.wav', '.ogg', '.spx',
    '.ttf', '.otf', '.woff', '.woff2', '.eot'
)
