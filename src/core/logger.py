# file: src/core/logger.py
# -*- coding: utf-8 -*-
"""
统一日志系统
提供标准化的日志记录，替代裸except和print语句
"""
import logging
import sys
import os


def setup_logger(
    name: str = "geekdict",
    level: int = logging.INFO,
    log_file: str | None = None,
    fmt: str | None = None
) -> logging.Logger:
    """
    创建和配置logger实例
    
    Args:
        name: logger名称，默认为'geekdict'
        level: 日志级别，默认为INFO
        log_file: 可选的日志文件路径。若为None则只输出到控制台
        fmt: 自定义日志格式字符串
        
    Returns:
        配置好的Logger实例
    """
    logger = logging.getLogger(name)
    
    # 防止重复添加handler（如多次调用时）
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # 默认格式
    if fmt is None:
        fmt = "[%(asctime)s] %(name)s-%(levelname)s: %(message)s"
    
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
    
    # 控制台Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件Handler（可选）
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (OSError, PermissionError) as e:
            logger.warning(f"无法创建日志文件 {log_file}: {e}")
    
    return logger


# 创建全局默认logger
logger = setup_logger()


def get_logger(name: str = "geekdict") -> logging.Logger:
    """获取已配置的logger实例（支持子模块命名空间）"""
    return logging.getLogger(name)


class LogException:
    """上下文管理器：自动捕获并记录异常"""
    
    def __init__(self, logger: logging.Logger, msg: str = "操作失败", reraise: bool = False):
        self.logger = logger
        self.msg = msg
        self.reraise = reraise
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.logger.error(f"{self.msg}: {exc_val}", exc_info=True)
        return not self.reraise  # 返回True抑制异常，False传播异常
