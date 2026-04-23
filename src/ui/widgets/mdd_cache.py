# file: src/ui/widgets/mdd_cache.py
# -*- coding: utf-8 -*-
"""
MDD资源缓存管理器
使用线程本地存储管理MDD数据库连接，支持精确/模糊查询
"""
import sqlite3
import threading

from ...core.config import MDD_DB_FILE
from ...core.logger import logger


class MDDCacheManager:
    """
    MDD资源缓存管理器
    
    功能:
    - 线程本地连接池（每个线程独立连接）
    - 精确查找：按 dict_id + norm_key 匹配
    - 模糊查找：尝试多种路径变体进行匹配
    """
    _thread_local = threading.local()

    @staticmethod
    def get_connection() -> sqlite3.Connection:
        """获取当前线程的MDD数据库连接（懒加载）"""
        if not hasattr(MDDCacheManager._thread_local, "conn"):
            try:
                conn = sqlite3.connect(MDD_DB_FILE, check_same_thread=False, timeout=30)
                conn.execute("PRAGMA query_only = 1;")
                conn.execute("PRAGMA journal_mode = WAL;")
                MDDCacheManager._thread_local.conn = conn
                logger.debug(f"MDD新连接已创建 (thread={threading.current_thread().name})")
            except Exception as e:
                logger.error(f"创建MDB连接失败: {e}")
                raise
        
        return MDDCacheManager._thread_local.conn

    @staticmethod
    def get_resource_strict(dict_id: int, norm_key: str) -> bytes | None:
        """
        精确查找MDD资源（按dict_id + 标准化key）
        
        Args:
            dict_id: 词典ID
            norm_key: 标准化后的资源路径（大写、反斜杠分隔）
            
        Returns:
            资源字节数据或None
        """
        try:
            conn = MDDCacheManager.get_connection()
            cursor = conn.execute(
                "SELECT data FROM resources WHERE dict_id=? AND norm_key=?",
                (dict_id, norm_key)
            )
            res = cursor.fetchone()
            return res[0] if res else None
        except Exception as e:
            logger.debug(f"精确查找MDD资源失败 (did={dict_id}, key={norm_key}): {e}")
            return None

    @staticmethod
    def get_resource_fuzzy(dict_id: int, raw_path: str) -> bytes | None:
        """
        模糊查找MDD资源（尝试多种路径组合）
        
        支持的场景：
        - 绝对路径 vs 相对路径
        - ID前缀去除（如 1\\dot.gif -> \\dot.gif）
        - 纯文件名回退（如 \\images\\u\\k\\dot.gif -> \\DOT.GIF）
        - 后缀LIKE匹配（兜底方案）
        
        Args:
            dict_id: 词典ID
            raw_path: 原始路径字符串
            
        Returns:
            资源字节数据或None
        """
        # 统一反斜杠
        path = raw_path.replace('/', '\\')
        
        candidates = []
        
        # 候选1：绝对路径（确保以 \ 开头）
        base = '\\' + path.upper().lstrip('\\')
        candidates.append(base)
        
        # 候选2：去除可能的数字ID前缀
        parts = path.split('\\')
        if len(parts) > 1 and parts[0].isdigit():
            clean_path = '\\' + '\\'.join(parts[1:])
            candidates.append(clean_path.upper().lstrip('\\'))
        
        # 候选3：仅保留文件名（最强暴力回退）
        if parts:
            filename = parts[-1]
            candidates.append('\\' + filename.upper())
        
        # 按顺序尝试精确匹配
        for key in list(dict.fromkeys(candidates)):
            res = MDDCacheManager.get_resource_strict(dict_id, key)
            if res:
                return res
        
        # 兜底：后缀LIKE模糊匹配
        try:
            if parts and parts[-1]:
                conn = MDDCacheManager.get_connection()
                suffix = "\\" + parts[-1].upper()
                pat = "%" + suffix
                cur = conn.execute(
                    "SELECT data FROM resources WHERE dict_id=? AND norm_key LIKE ? LIMIT 1",
                    (dict_id, pat)
                )
                row = cur.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            logger.debug(f"后缀匹配MDD资源失败 (did={dict_id}): {e}")

        return None

    @staticmethod
    def cleanup_all():
        """清理所有线程的数据库连接（应用关闭时调用）"""
        try:
            if hasattr(MDDCacheManager._thread_local, "conn"):
                conn = getattr(MDDCacheManager._thread_local, "conn", None)
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                delattr(MDDCacheManager._thread_local, "conn")
            logger.info("MDD缓存连接已清理")
        except Exception as e:
            logger.warning(f"清理MDD连接时出错: {e}")

