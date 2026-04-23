#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
最小化 QWebEngineView 渲染测试
用于诊断 WebEngine 是否能正常渲染 HTML
"""
import sys
import os

# 设置环境变量（与 main_new.py 一致）
os.environ["QT_WEBENGINE_DISABLE_SANDBOX"] = "1"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineUrlScheme

# 注册 mdict scheme
try:
    mdict_scheme = QWebEngineUrlScheme(b"mdict")
    mdict_scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort)
    mdict_scheme.setDefaultPort(0)
    QWebEngineUrlScheme.registerScheme(mdict_scheme)
except Exception as e:
    print(f"[WARN] Scheme注册失败: {e}")

app = QApplication(sys.argv + ["--disable-gpu", "--no-sandbox"])

window = QMainWindow()
window.setWindowTitle("QWebEngineView 渲染测试")
window.setGeometry(100, 100, 1200, 800)

central = QWidget()
layout = QVBoxLayout(central)

# 标签
label = QLabel("等待测试...")
label.setStyleSheet("font-size:16px;padding:10px;")
layout.addWidget(label)

# Web视图
web = QWebEngineView()
layout.addWidget(web)

window.setCentralWidget(window)
window.setCentralWidget(central)

test_results = []

def run_test_1():
    """测试1: 最简单 HTML"""
    label.setText("测试1: 最简单 HTML...")
    print("[TEST1] 设置最简单 HTML...", file=sys.stderr)
    web.setHtml("<html><body style='background:white;padding:20px;'><h1>TEST 1 PASSED</h1><p>最简单的HTML</p></body></html>")
    test_results.append("Test1: setHtml called")
    
    # 2秒后运行测试2
    QTimer.singleShot(2000, run_test_2)

def run_test_2():
    """测试2: 带CSS的复杂HTML"""
    label.setText("测试2: 带 CSS 的 HTML...")
    print("[TEST2] 设置带CSS的 HTML...", file=sys.stderr)
    complex_html = """
    <html>
    <head>
        <style>
            :root { --bg:#f5f7fa; --primary:#2196F3; --text:#333; }
            body { font-family:sans-serif; padding:20px; background:var(--bg); color:var(--text); }
            .card { background:white; padding:25px; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.08); margin-bottom:15px; }
            h2 { color:var(--primary); }
            a { color:var(--primary); text-decoration:none; }
            ::-webkit-scrollbar { width:8px; }
        </style>
    </head>
    <body>
        <div class='card'>
            <h2>TEST 2 PASSED - Complex CSS</h2>
            <p>This tests complex CSS with variables and shadows.</p>
            <a href='#'>Link Test</a>
        </div>
        <div class='card'>
            <h3>Card 2</h3>
            <p>Multiple cards test layout.</p>
        </div>
    </body>
    </html>
    """
    web.setHtml(complex_html)
    test_results.append("Test2: complex HTML called")
    
    # 3秒后运行测试3
    QTimer.singleShot(3000, run_test_3)

def run_test_3():
    """测试3: 带JS和mdict链接的HTML（模拟真实词典）"""
    label.setText("测试3: 模拟真实词典 HTML...")
    print("[TEST3] 设置模拟词典 HTML...", file=sys.stderr)
    dict_html = """
    <html>
    <head>
        <meta charset='utf-8'>
        <style>@font-face{font-family:'Kingsoft Phonetic Plain';src:url('mdict://theme/kingsoft_phonetic.ttf');}
        :root { --primary: #43a047; --bg: #f1f8e9; --card: #ffffff; --text: #1b5e20; --border: #c8e6c9; }
        body { font-family:-apple-system,sans-serif; line-height:1.6; color:var(--text); background-color:var(--bg); padding:20px; max-width:900px;margin:0 auto; }
        .entry-content{overflow:visible!important;}
        .card{background:var(--card);padding:25px;margin-bottom:25px;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.08);border:1px solid var(--border);}
        .badge{background:var(--bg);color:var(--primary);border:1px solid var(--primary);padding:3px 8px;border-radius:12px;font-size:12px;}
        </style>
        <script>function speak(t){ try{ window.speechSynthesis.speak(new SpeechSynthesisUtterance(t)); }catch(e){} }</script>
    </head>
    <body>
        <div class="action-bar">
            <button onclick="speak('car')">🔊 Speak</button>
            <button onclick="alert('Copy!')">📋 Copy</button>
            <a href="https://google.com">🌐 Google</a>
        </div>
        <div class='card' data-dict-id='4'>
            <div class='card-header'><span class='badge'>oaldpe</span> car</div>
            <div class='entry-content'><p><b>car</b> /kɑːr/ noun. A road vehicle with four wheels.</p><p>Example: I drove my <b>car</b> to work.</p></div>
        </div>
        <div class='card' data-dict-id='3'>
            <div class='card-header'><span class='badge'>Vocab</span> car</div>
            <div class='entry-content'><p>A motor vehicle used for transportation.</p></div>
        </div>
    </body>
    </html>
    """
    web.setHtml(dict_html, baseUrl=QUrl("mdict://root/"))
    test_results.append("Test3: dict-like HTML called")
    
    # 3秒后总结
    QTimer.singleShot(3000, show_summary)

def show_summary():
    label.setText(f"所有测试完成！共执行 {len(test_results)} 个测试")
    print("=" * 50, file=sys.stderr)
    print("测试结果:", file=sys.stderr)
    for r in test_results:
        print(f"  ✓ {r}", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print("\n请检查窗口中是否能看到每个测试的内容！", file=sys.stderr)

# 启动测试序列
window.show()
QTimer.singleShot(500, run_test_1)

exit_code = app.exec()
sys.exit(exit_code)
