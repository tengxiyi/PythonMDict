#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
极客词典Pro (GeekDictionary) v3.0 - 应用程序入口点

重构历程:
  Phase 1: 模块拆分 — 将 main.py(3507行) + backend.py(1178行) 拆分为 src/ 下 33+ 个模块
  Phase 2: 功能优化 — 每日一词重构 / 闪卡全面升级 / 例句质量修复 / 出处引用

项目结构:
├── main_new.py          # 入口文件 (本文件, ~136行)
├── backend.py           # 向后兼容的导入重导出
├── src/
│   ├── core/            # 核心业务逻辑
│   │   ├── config.py        # 配置常量 (DB_FILE, EBBINGHAUS_INTERVALS 等)
│   │   ├── logger.py        # 统一日志系统 (控制台+文件双输出)
│   │   ├── database.py      # 数据库管理 (SQLite CRUD)
│   │   ├── utils.py         # 工具集 (clean_sentence_text, STOP_WORDS, VALID_WORD 等)
│   │   ├── quiz_worker.py   # 测验生成 (干扰项筛选+例句提取+词条头过滤)
│   │   ├── search_worker.py # 搜索线程
│   │   ├── indexer_worker.py# MDX导入索引
│   │   ├── analyzer_worker.py  # 词频分析
│   │   └── news_workers.py    # RSS新闻
│   └── ui/              # UI层
│       ├── main_window.py      # 主窗口框架
│       ├── theme_manager.py    # 主题管理器
│       ├── widgets/            # 自定义控件 (sidebar, clipboard_watcher, mdd_cache 等)
│       ├── handlers/           # URL协议处理 (mdict://)
│       └── pages/              # 功能页面
│           ├── search_page.py      # 查词 + 每日一词 (含日期种子+停用词过滤)
│           ├── vocab_page.py       # 单词本 + 闪卡学习 (含出处引用+我不会按钮)
│           ├── settings_page.py    # 设置
│           ├── theme_page.py       # 主题选择
│           ├── dict_manager_page.py# 词典管理
│           ├── history_page.py     # 历史记录
│           └── text_analyzer_page.py # 词频分析
"""

import sys
import os

# ★★★ WebEngine 渲染修复：在 import Qt 之前设置环境变量 ★★★
# 禁用沙箱（Windows 下可能导致渲染崩溃）
os.environ["QT_WEBENGINE_DISABLE_SANDBOX"] = "1"

# 将项目根目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置高DPI支持
try:
    from PySide6.QtCore import Qt, QCoreApplication
    from PySide6.QtWidgets import QApplication
    
    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
except ImportError as e:
    print(f"警告: 无法加载PySide6: {e}", file=sys.stderr)
    sys.exit(1)


def setup_environment():
    """设置运行环境"""
    # Windows任务栏图标修复
    if sys.platform == 'win32':
        try:
            import ctypes
            app_id = "GeekDictionary.Pro.1.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass  # 非Windows环境或API不可用，忽略错误
    
    # 设置工作目录为脚本所在目录
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的临时目录
        os.chdir(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))


def main():
    """应用程序主函数"""
    # 先设置环境
    setup_environment()
    
    # 创建Qt应用（传入 Chromium 参数修复 GPU 渲染崩溃）
    # Compositor returned null texture / blink.mojom.Widget 错误的修复方案
    qt_argv = sys.argv + [
        "--disable-gpu",                    # 禁用GPU加速（解决合成器崩溃）
        "--disable-gpu-compositing",        # 禁用GPU合成
        "--no-sandbox",                     # 无沙箱模式
        "--enable-begin-frame-scheduling",  # 启用帧调度修复
    ]
    app = QApplication(qt_argv)
    app.setApplicationName("GeekDictionary")
    app.setOrganizationName("GeekTeam")
    
    # ★★★ 关键：必须在创建任何QWebEngineView之前注册自定义URL协议 ★★★
    # 注意：必须使用 Syntax.Path（与main.py一致），否则mdict://资源请求会全部失败导致白屏
    try:
        from PySide6.QtWebEngineCore import QWebEngineUrlScheme
        s = QWebEngineUrlScheme(b"mdict")
        s.setSyntax(QWebEngineUrlScheme.Syntax.Path)
        # 允许子资源加载（CSS/JS/字体/媒体）
        flags = QWebEngineUrlScheme.Flag.LocalScheme | QWebEngineUrlScheme.Flag.LocalAccessAllowed
        for _name in ["SecureScheme", "CorsEnabled", "ContentSecurityPolicyIgnored"]:
            try:
                if hasattr(QWebEngineUrlScheme.Flag, _name):
                    flags |= getattr(QWebEngineUrlScheme.Flag, _name)
            except:
                pass
        s.setFlags(flags)
        QWebEngineUrlScheme.registerScheme(s)
    except Exception as e:
        print(f"[WARN] URL scheme registration failed: {e}")
    
    # 初始化日志系统
    from src.core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("=" * 50)
    logger.info("极客词典Pro 启动中...")
    
    # 创建并显示主窗口
    try:
        from src.main_window import ModernMainWindow
        window = ModernMainWindow()
        window.show()
        
        logger.info("应用启动成功")
    except Exception as e:
        logger.critical(f"启动失败: {e}", exc_info=True)
        from PySide6.QtWidgets import QMessageBox
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("启动失败")
        msg_box.setText(f"无法启动应用:\n{str(e)}")
        _ = msg_box.exec()
        sys.exit(1)
    
    # 进入事件循环
    exit_code = app.exec()
    logger.info(f"应用退出，退出码: {exit_code}")

    # 退出时执行 WAL checkpoint (TRUNCATE)，将数据合并回主数据库并回收空间
    try:
        from src.core.connection_pool import pool
        pool.checkpoint(mode="TRUNCATE")
        pool.checkpoint(pool._mdd_pool._db_file, mode="TRUNCATE")
        logger.info("WAL checkpoint 完成 (TRUNCATE)")
    except Exception as e:
        logger.debug(f"退出时 checkpoint 跳过: {e}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
