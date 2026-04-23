# core package - 核心业务逻辑
"""
包含:
- config: 全局配置常量
- logger: 日志系统
- database: 数据库管理
- search: 搜索功能
- indexer: MDX/MDD导入索引
- quiz: 测验生成
- analyzer: 词频分析
- news: RSS新闻
- utils: 工具函数
"""

from .config import DB_FILE, MDD_DB_FILE, EBBINGHAUS_INTERVALS
