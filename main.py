import sys
import os
import time
import sqlite3
import urllib.parse
import base64
import json
import re
import threading
import ctypes
import tempfile
import hashlib
from datetime import datetime


from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QStackedWidget, QFrame, QSplitter, QButtonGroup, QAbstractItemView,
    QMessageBox, QFileDialog, QDialog, QTreeWidget, QTreeWidgetItem,
    QMenu, QStyle, QProgressDialog, QTabWidget, QGroupBox, QGridLayout,
    QRadioButton, QColorDialog, QCheckBox, QToolButton, QSizePolicy, QTreeWidgetItemIterator,
    QScrollArea, QTextEdit
)
from PySide6.QtGui import (
    QIcon, QAction, QKeySequence, QShortcut, QPalette, QColor, QPainter, QPen, QDesktopServices, QPixmap, QImage
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize, QUrl, QTimer, Signal, QPoint, QUrlQuery, QObject, QBuffer, QIODevice, QByteArray, \
    QRect, QRectF
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineUrlScheme, QWebEnginePage, QWebEngineUrlSchemeHandler, \
    QWebEngineUrlRequestJob

# --- 引入 backend ---
from backend import (
    DatabaseManager, SearchWorker, NewsWorker, NewsContentWorker,
    IndexerWorker, RSSTestWorker, process_entry_task,
    DB_FILE, MDD_DB_FILE, EBBINGHAUS_INTERVALS
)

from PySide6.QtSvg import QSvgRenderer

from backend import QuizWorker
from backend import AnalyzerWorker, extract_text_from_epub


# ==========================================
# Part 1: 辅助类
# ==========================================

THEME_CONFIG_FILE = "theme_config.json"


def resource_path(relative_path):
    """ 获取资源的绝对路径 """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的临时目录
        return os.path.join(sys._MEIPASS, relative_path)
    # 开发环境
    return os.path.join(os.path.abspath("."), relative_path)

class ThemeManager:
    # 10种精选配色方案
    PRESETS = {
        "Light (Default)": {
            "bg": "#ffffff", "card": "#ffffff", "text": "#333333",
            "primary": "#2196F3", "border": "#E0E0E0", "hover": "#F5F5F5", "meta": "#666666",
            "sidebar": "#F5F7FA"
        },
        "Dark (Default)": {
            "bg": "#2b2b2b", "card": "#3c3c3c", "text": "#ffffff",
            "primary": "#64b5f6", "border": "#555555", "hover": "#4a4a4a", "meta": "#bbbbbb",
            "sidebar": "#333333"
        },
        "Sepia (Reading)": {
            "bg": "#f4ecd8", "card": "#fdf6e3", "text": "#5b4636",
            "primary": "#d35400", "border": "#e4dcc9", "hover": "#e9e0cb", "meta": "#95a5a6",
            "sidebar": "#eee4cc"
        },
        "Nord (Arctic)": {
            "bg": "#2E3440", "card": "#434c5e", "text": "#ECEFF4",
            "primary": "#88C0D0", "border": "#4C566A", "hover": "#4C566A", "meta": "#D8DEE9",
            "sidebar": "#3b4252"
        },
        "Dracula (Vampire)": {
            "bg": "#282a36", "card": "#44475a", "text": "#f8f8f2",
            "primary": "#ff79c6", "border": "#6272a4", "hover": "#50536b", "meta": "#bd93f9",
            "sidebar": "#343746"
        },
        "Forest (Green)": {
            "bg": "#f1f8e9", "card": "#ffffff", "text": "#1b5e20",
            "primary": "#43a047", "border": "#c8e6c9", "hover": "#dcedc8", "meta": "#689f38",
            "sidebar": "#e8f5e9"
        },
        "Ocean (Deep Blue)": {
            "bg": "#0f172a", "card": "#334155", "text": "#f1f5f9",
            "primary": "#38bdf8", "border": "#475569", "hover": "#1e293b", "meta": "#cbd5e1",
            "sidebar": "#1e293b"
        },
        "Solarized Light": {
            "bg": "#fdf6e3", "card": "#eee8d5", "text": "#657b83",
            "primary": "#268bd2", "border": "#93a1a1", "hover": "#e0d7c6", "meta": "#93a1a1",
            "sidebar": "#eee8d5"
        },
        "Cyberpunk (Neon)": {
            "bg": "#1a1b26", "card": "#24283b", "text": "#c0caf5",
            "primary": "#f7768e", "border": "#414868", "hover": "#2f3549", "meta": "#7aa2f7",
            "sidebar": "#1f2335"
        },
        "High Contrast": {
            "bg": "#000000", "card": "#222222", "text": "#ffffff",
            "primary": "#FFD700", "border": "#555555", "hover": "#333333", "meta": "#aaaaaa",
            "sidebar": "#111111"
        }
    }

    def __init__(self):
        self.current_theme_name = "Light (Default)"
        self.colors = self.PRESETS[self.current_theme_name].copy()
        self.load_config()

    def load_config(self):
        if os.path.exists(THEME_CONFIG_FILE):
            try:
                with open(THEME_CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    name = data.get("theme_name", "Light (Default)")
                    if name in self.PRESETS:
                        self.current_theme_name = name
                        self.colors = self.PRESETS[name].copy()
            except:
                pass

    def set_theme(self, theme_name):
        if theme_name in self.PRESETS:
            self.current_theme_name = theme_name
            self.colors = self.PRESETS[theme_name].copy()
            self.save_config()

    def save_config(self):
        with open(THEME_CONFIG_FILE, "w") as f:
            json.dump({"theme_name": self.current_theme_name}, f)

    def get_webview_css(self):
        c = self.colors
        bg_color = c['bg'].lstrip('#')
        is_dark = False
        if len(bg_color) == 6:
            r, g, b = tuple(int(bg_color[i:i + 2], 16) for i in (0, 2, 4))
            is_dark = (r * 0.299 + g * 0.587 + b * 0.114) < 128

        # 增加 --shadow 变量，优化字体
        css = f"""
        :root {{ 
            --primary: {c['primary']}; --bg: {c['bg']}; --card: {c['card']}; 
            --text: {c['text']}; --border: {c['border']}; --meta: {c['meta']}; 
            --hover: {c['hover']}; 
            --shadow: 0 4px 12px rgba(0,0,0,0.08);
            --radius: 12px;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: var(--text);
            background-color: var(--bg);
            transition: background 0.3s ease;
        }}
        /* 滚动条美化 (Webkit) */
        ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: #ccc; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #999; }}
        """

        if is_dark:
            css += f"""
            ::-webkit-scrollbar-thumb {{ background: #555; }}
            ::-webkit-scrollbar-thumb:hover {{ background: #777; }}

            /* 就是这里！控制深色模式下词典内容的强制样式 */
            .entry-content {{ background-color: var(--card) !important; color: #e0e0e0 !important; }}

            /* ▼▼▼ 你问的那一行在这里 ▼▼▼ */
            .entry-content * {{
                background-color: transparent !important;
                color: #e0e0e0 !important; 
                border-color: {c['border']} !important;
                box-shadow: none !important;
            }}
            /* ▲▲▲▲▲▲ */

            .entry-content a {{ color: {c['primary']} !important; text-decoration: none; border-bottom: 1px dashed {c['primary']}; }}
            .entry-content img {{ background-color: #eee; border-radius: 6px; padding: 4px; margin: 5px 0; }}
            .entry-content b, .entry-content strong, .entry-content h1, .entry-content h2 {{ color: #FFD700 !important; }}
            """
        else:
            # 浅色模式下的额外优化
            css += """
            .entry-content a {{ color: var(--primary); text-decoration: none; font-weight: 500; }}
            .entry-content a:hover {{ text-decoration: underline; }}
            """
        return css


theme_manager = ThemeManager()

# 用于 iframe 词条的临时 HTML 缓存
IFRAME_HTML_CACHE = {}
IFRAME_HTML_LOCK = threading.Lock()

# 用于物理资源的按文件名索引（解决资源在子目录但 HTML 只引用文件名的情况）
DICT_DIR_CACHE = {}
DICT_DIR_CACHE_LOCK = threading.Lock()
PHYSICAL_RES_INDEX = {}
PHYSICAL_RES_INDEX_LOCK = threading.Lock()


def _get_dict_dir(dict_id: int):
    """从 dict_info 里拿到词典所在目录（缓存）。"""
    try:
        with DICT_DIR_CACHE_LOCK:
            if dict_id in DICT_DIR_CACHE:
                return DICT_DIR_CACHE[dict_id]

        with sqlite3.connect(DB_FILE, timeout=5) as conn:
            row = conn.execute("SELECT path FROM dict_info WHERE id=?", (dict_id,)).fetchone()
        dict_dir = os.path.dirname(row[0]) if row and row[0] else None
        dict_dir = os.path.normpath(dict_dir) if dict_dir else None

        with DICT_DIR_CACHE_LOCK:
            DICT_DIR_CACHE[dict_id] = dict_dir
        return dict_dir
    except:
        return None


def _build_physical_res_index(dict_dir: str):
    """扫描词典目录，建立 basename -> fullpath 的映射（只取常见资源后缀）。"""
    allow_exts = (
        '.css', '.js',
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',
        '.mp3', '.wav', '.ogg', '.spx',
        '.ttf', '.otf', '.woff', '.woff2', '.eot'
    )

    idx = {}
    try:
        for root, _dirs, files in os.walk(dict_dir):
            for fn in files:
                low = fn.lower()
                if not low.endswith(allow_exts):
                    continue
                key = fn.upper()
                # 避免同名文件覆盖（取第一次出现的即可）
                if key not in idx:
                    idx[key] = os.path.join(root, fn)
    except:
        pass
    return idx


def _get_physical_resource_path(dict_id: int, rel_path: str):
    """优先精确路径，其次按文件名在词典目录内回退查找。"""
    dict_dir = _get_dict_dir(dict_id)
    if not dict_dir:
        return None

    try:
        # 1) 精确路径：dict_dir + rel_path
        file_path = os.path.normpath(os.path.join(dict_dir, rel_path))
        if os.path.commonpath([dict_dir, file_path]).startswith(os.path.normpath(dict_dir)):
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return file_path
    except:
        pass

    # 2) 按文件名索引回退：basename
    try:
        base = os.path.basename(rel_path).upper()
        if not base:
            return None

        with PHYSICAL_RES_INDEX_LOCK:
            idx = PHYSICAL_RES_INDEX.get(dict_dir)
        if idx is None:
            idx = _build_physical_res_index(dict_dir)
            with PHYSICAL_RES_INDEX_LOCK:
                PHYSICAL_RES_INDEX[dict_dir] = idx

        hit = idx.get(base)
        if hit:
            hit = os.path.normpath(hit)
            if os.path.commonpath([dict_dir, hit]).startswith(os.path.normpath(dict_dir)):
                if os.path.exists(hit) and os.path.isfile(hit):
                    return hit
    except:
        pass

    return None


def create_svg_icon(path_data, color, size=24):
    """将 SVG 路径数据转换为 QIcon"""
    svg_content = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}"><path d="{path_data}" fill="{color}" /></svg>'
    data = QByteArray(svg_content.encode('utf-8'))
    renderer = QSvgRenderer(data)

    if not renderer.isValid():
        return QIcon()

    pixmap = QPixmap(32, 32)  # 高清渲染
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, 32, 32))
    painter.end()
    return QIcon(pixmap)


class ClipboardWatcher(QObject):
    text_copied = Signal(str)

    def __init__(self):
        super().__init__()
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.on_clipboard_change)
        self.last_text = ""

    def on_clipboard_change(self):
        try:
            mime = self.clipboard.mimeData()
            if not mime.hasText(): return
            text = mime.text().strip()
            if text == self.last_text or len(text) > 40 or len(text) < 2: return
            if not re.match(r'^[a-zA-Z\s\-\']+$', text): return
            self.last_text = text
            self.text_copied.emit(text)
        except:
            pass


class MDDCacheManager:
    _thread_local = threading.local()

    @staticmethod
    def get_connection():
        if not hasattr(MDDCacheManager._thread_local, "conn"):
            conn = sqlite3.connect(MDD_DB_FILE, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA query_only = 1;")
            conn.execute("PRAGMA journal_mode = WAL;")
            MDDCacheManager._thread_local.conn = conn
        return MDDCacheManager._thread_local.conn

    @staticmethod
    def get_resource_strict(dict_id, norm_key):
        try:
            conn = MDDCacheManager.get_connection()
            cursor = conn.execute("SELECT data FROM resources WHERE dict_id=? AND norm_key=?", (dict_id, norm_key))
            res = cursor.fetchone()
            return res[0] if res else None
        except Exception:
            return None

    @staticmethod
    def get_resource_fuzzy(dict_id, raw_path):
        """
        [终极修复] 暴力尝试各种路径组合，兼容简明英汉等怪异路径
        """
        # 1. 基础清理：统一反斜杠
        path = raw_path.replace('/', '\\')

        candidates = []

        # 候选 1: 绝对路径 (确保以 \ 开头) -> \DOT.GIF
        # 这里的 lstrip('\\') 再加 '\\' 是为了防止 raw_path 本身就是 \dot.gif 导致变成 \\dot.gif
        base = '\\' + path.upper().lstrip('\\')
        candidates.append(base)

        # 候选 2: 尝试去除可能的 ID 前缀 (例如 1\dot.gif -> \dot.gif)
        parts = path.split('\\')
        if len(parts) > 1 and parts[0].isdigit():
            clean_path = '\\' + '\\'.join(parts[1:])
            candidates.append(clean_path.upper().lstrip('\\'))  # 确保只有1个斜杠

        # 候选 3: [最强暴力] 忽略所有目录，只找文件名
        # 例如: \images\u\k\dot.gif -> \DOT.GIF
        if parts:
            filename = parts[-1]
            candidates.append('\\' + filename.upper())

        # 去重并开始查找
        for key in list(dict.fromkeys(candidates)):  # 保持顺序去重
            # print(f"Trying: {key}") # 调试用
            res = MDDCacheManager.get_resource_strict(dict_id, key)
            if res:
                return res

        # 兜底：suffix 匹配（解决资源实际存为 \AUDIO\XX.MP3 但请求为 XX.MP3）
        try:
            if parts and parts[-1]:
                conn = MDDCacheManager.get_connection()
                suffix = "\\" + parts[-1].upper()
                pat = "%" + suffix
                cur = conn.execute("SELECT data FROM resources WHERE dict_id=? AND norm_key LIKE ? LIMIT 1", (dict_id, pat))
                row = cur.fetchone()
                if row:
                    return row[0]
        except:
            pass

        return None





def _parse_dict_id_str(dict_id_str):
    try:
        if "." in dict_id_str:
            dict_id_str = dict_id_str.split('.')[-1]
        return int(float(dict_id_str))
    except:
        return None


def _expand_resource_candidates(rel_path: str):
    if not rel_path:
        return []

    p0 = rel_path.replace('\\', '/').lstrip('/')

    # 兼容 oaldpe：文件名里可能包含被编码的 #（%23 / %2523）
    base_candidates = [p0]
    try:
        low = p0.lower()
        if '# ' in low:
            pass
        if '#' in p0:
            base_candidates.append(p0.replace('#', '%23'))
            base_candidates.append(p0.replace('#', '%2523'))
        if '%2523' in low:
            base_candidates.append(re.sub(r'(?i)%2523', '%23', p0))
            base_candidates.append(re.sub(r'(?i)%2523', '#', p0))
        if '%23' in low:
            base_candidates.append(re.sub(r'(?i)%23', '#', p0))
    except:
        pass

    candidates = []
    for p in base_candidates:
        candidates.append(p)

        # simplified/ 前缀
        parts = p.split('/')
        if parts and parts[0].lower() == 'simplified' and len(parts) > 1:
            candidates.append('/'.join(parts[1:]))

        # 中间包含 /simplified/
        if any(seg.lower() == 'simplified' for seg in parts):
            try:
                idx = [seg.lower() for seg in parts].index('simplified')
                if idx > -1 and idx + 1 < len(parts):
                    candidates.append('/'.join(parts[:idx] + parts[idx + 1:]))
            except:
                pass

        # 去掉 _simplified 后缀
        base = os.path.basename(p)
        if '_simplified' in base.lower():
            base2 = re.sub(r'(?i)_simplified', '', base)
            dirp = os.path.dirname(p)
            candidates.append((dirp + '/' + base2) if dirp else base2)

    # 去重保持顺序
    seen = set()
    out = []
    for c in candidates:
        c2 = c.replace('\\', '/').lstrip('/')
        if c2 and c2 not in seen:
            seen.add(c2)
            out.append(c2)
    return out



def _fetch_resource_bytes(dict_id, rel_path):
    """优先读物理文件（支持子目录按文件名回退），否则读 MDD 缓存。"""
    candidates = _expand_resource_candidates(rel_path)
    if not candidates:
        return None

    try:
        for cand in candidates:
            fp = _get_physical_resource_path(dict_id, cand)
            if fp:
                with open(fp, "rb") as f:
                    return f.read()
    except:
        pass

    try:
        for cand in candidates:
            data = MDDCacheManager.get_resource_fuzzy(dict_id, cand)
            if data:
                return data
    except:
        return None

    return None




def play_audio_from_mdict(play_url):
    if not play_url.startswith("mdict://"):
        return False

    path_part = play_url.split("mdict://", 1)[1]
    if "/" not in path_part:
        return False

    dict_id_str, raw_res_path = path_part.split("/", 1)

    # 与 MdictSchemeHandler 保持一致：root / 0.0.0.x 视为“全库查找”
    if dict_id_str == "root" or dict_id_str.startswith("0.0.0."):
        try:
            with sqlite3.connect(DB_FILE) as conn:
                target_ids = [r[0] for r in conn.execute("SELECT id FROM dict_info ORDER BY priority ASC").fetchall()]
        except:
            target_ids = []
    else:
        dict_id = _parse_dict_id_str(dict_id_str)
        if dict_id is None:
            return False
        target_ids = [dict_id]

    # 先去掉真正的 query/fragment（避免把文件名里的 %23 解码成 # 后被误截断）
    raw_res_path = raw_res_path.split('?', 1)[0].split('#', 1)[0]

    # 兼容二次编码（%2523 -> %23 -> #）
    decoded_path = raw_res_path
    try:
        for _ in range(3):
            new_p = urllib.parse.unquote(decoded_path)
            if new_p == decoded_path:
                break
            decoded_path = new_p
    except:
        decoded_path = urllib.parse.unquote(raw_res_path)

    decoded_path = decoded_path.replace('\\', '/')
    decoded_path = os.path.normpath(decoded_path).replace('\\', '/')
    decoded_path = decoded_path.lstrip('/')

    # 同时保留“原始编码态”用于候选（有些资源键名会存成 %23/%2523，而不是 #）
    raw_path_norm = raw_res_path.replace('\\', '/')
    raw_path_norm = os.path.normpath(raw_path_norm).replace('\\', '/')
    raw_path_norm = raw_path_norm.lstrip('/')

    data = None
    hit_dict_id = None

    # 先尝试 decoded_path，再尝试 raw_path_norm（两条路径都走候选扩展）
    for did in target_ids:
        data = _fetch_resource_bytes(did, decoded_path)
        if data:
            hit_dict_id = did
            break
        if raw_path_norm and raw_path_norm != decoded_path:
            data = _fetch_resource_bytes(did, raw_path_norm)
            if data:
                hit_dict_id = did
                break

    if not data:
        try:
            print(f"[audio] not found: dict_id={dict_id_str} path={decoded_path} raw={raw_path_norm} targets={target_ids}")
        except:
            pass
        return False

    ext = os.path.splitext(decoded_path)[1].lower() or os.path.splitext(raw_path_norm)[1].lower() or ".spx"
    h = hashlib.md5(play_url.encode('utf-8')).hexdigest()[:10]
    tmp_path = os.path.join(tempfile.gettempdir(), f"geekdict_{hit_dict_id or 'x'}_{h}{ext}")
    if not os.path.exists(tmp_path):
        with open(tmp_path, "wb") as f:
            f.write(data)

    try:
        print(f"[audio] open: {tmp_path} bytes={len(data)}")
    except:
        pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(tmp_path))
    return True




# 修复说明：
# 1. 移除了导致崩溃的 print(Emoji) 语句
# 2. 增加了全局异常捕获，防止任何错误导致 Fast Fail
# 3. 优化了资源查找逻辑

# ==========================================
# 核心类 1: 资源加载器 (集成防崩溃逻辑)
# ==========================================
# [main.py] 替换 MdictSchemeHandler 类
# [main.py] 修复后的 MdictSchemeHandler 类
class MdictSchemeHandler(QWebEngineUrlSchemeHandler):
    def requestStarted(self, job: QWebEngineUrlRequestJob):
        # 辅助函数：返回数据
        def reply_data(mime, data):
            buf = QBuffer(parent=job)
            buf.setData(QByteArray(data))
            buf.open(QIODevice.ReadOnly)
            job.reply(mime, buf)

        # 辅助函数：返回空数据
        def reply_empty(mime):
            buf = QBuffer(parent=job)
            buf.open(QIODevice.ReadOnly)
            job.reply(mime, buf)

        try:
            url = job.requestUrl().toString()

            # === 0. iframe HTML 缓存 ===
            if url.startswith("mdict://iframe/"):
                token = url.split("mdict://iframe/", 1)[1].split("?", 1)[0].split("#", 1)[0]
                with IFRAME_HTML_LOCK:
                    data = IFRAME_HTML_CACHE.get(token)
                if data:
                    reply_data(b"text/html", data)
                else:
                    job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return

            # === 1. CSS 智能路由 (修复版) ===
            # 逻辑：优先找本地物理 CSS 文件，找不到则降级去数据库找
            if "mdict://css/" in url:
                try:
                    payload = url.split("mdict://css/", 1)[1]

                    if payload.isdigit():
                        # 情况 A: 纯数字 ID (例如 mdict://css/1)
                        dict_id = int(payload)
                        css_path = None
                        with sqlite3.connect(DB_FILE, timeout=5) as conn:
                            row = conn.execute("SELECT path FROM dict_info WHERE id=?", (dict_id,)).fetchone()
                            if row and row[0]: css_path = row[0][:-4] + ".css"

                        # [关键修改] 只有当物理文件存在时才直接返回
                        if css_path and os.path.exists(css_path):
                            with open(css_path, "rb") as f:
                                reply_data(b"text/css", f.read())
                            return

                    else:
                        parts = payload.split("/", 1)
                        if len(parts) == 2 and parts[0].isdigit():
                            dict_id = int(parts[0])
                            rest = parts[1]
                            if rest == "__style.css":
                                css_path = None
                                with sqlite3.connect(DB_FILE, timeout=5) as conn:
                                    row = conn.execute("SELECT path FROM dict_info WHERE id=?", (dict_id,)).fetchone()
                                    if row and row[0]: css_path = row[0][:-4] + ".css"
                                if css_path and os.path.exists(css_path):
                                    with open(css_path, "rb") as f:
                                        reply_data(b"text/css", f.read())
                                    return
                                reply_empty(b"text/css")
                                return
                            else:
                                url = f"mdict://{dict_id}/{rest}"
                        else:
                            # 情况 B: 不是数字 (如 mdict://css/images/bg.png)
                            # 说明是 CSS 内部引用的资源，浏览器错误地拼到了 css/ 目录下
                            # 策略：去掉 css/ 前缀，重定向到 root，让后续逻辑去数据库找
                            url = url.replace("mdict://css/", "mdict://root/", 1)
                        # 注意：不 return，让代码继续向下流转

                except Exception as e:
                    print(f"CSS Handler Error: {e}")
                    # 出错也不要死，继续尝试下面的逻辑




            # === 2. 字体特殊处理 ===
            # 只处理内置的金山音标字体；不要劫持其它词典自带的 .ttf，否则会导致字体/图标错乱
            try:
                low_url = url.lower()
            except:
                low_url = url

            if ("kingsoft_phonetic" in low_url) or low_url.endswith("kingsoft_phonetic.ttf") or low_url.endswith("kingsoft phonetic plain.ttf"):
                font_path = os.path.join("fonts", "Kingsoft Phonetic Plain.ttf")
                if os.path.exists(font_path):
                    with open(font_path, "rb") as f:
                        reply_data(b"font/ttf", f.read())
                    return
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return


            # === 3. 标准 MDD 资源查找 (数据库查找) ===
            if not url.startswith("mdict://"):
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return

            try:
                # 解析路径
                path_part = url.split("mdict://", 1)[1]

                # 二次清洗：防止依然带有 css/ 前缀
                if path_part.startswith("css/"):
                    path_part = path_part.replace("css/", "root/", 1)

                if "/" not in path_part:
                    path_part = "root/" + path_part

                dict_id_str, raw_res_path = path_part.split("/", 1)

                # 先去掉真正的 query/fragment（只处理 URL 中的字面字符 ?/#，不要误伤文件名里编码出来的 %23/#）
                raw_res_path = raw_res_path.split('?', 1)[0].split('#', 1)[0]

                # oaldpe 常见：路径被二次编码（%2523 -> %23 -> #），需要多次解码直到稳定
                decoded_path = raw_res_path
                try:
                    for _ in range(3):
                        new_p = urllib.parse.unquote(decoded_path)
                        if new_p == decoded_path:
                            break
                        decoded_path = new_p
                except:
                    decoded_path = urllib.parse.unquote(raw_res_path)

                decoded_path = decoded_path.replace('\\', '/')
                decoded_path = os.path.normpath(decoded_path).replace('\\', '/')
                decoded_path = decoded_path.lstrip('/')


                # 修复异常路径：例如 simplified/mdict://1/xxx.png
                try:
                    low_dp = decoded_path.lower()
                    pos = low_dp.rfind("mdict://")
                    if pos == -1:
                        pos = low_dp.rfind("mdict:/")
                        if pos != -1:
                            decoded_path = decoded_path[pos + 7:]
                    else:
                        decoded_path = decoded_path[pos + 8:]

                    decoded_path = decoded_path.lstrip('/')
                    if "/" in decoded_path:
                        maybe_id, rest = decoded_path.split("/", 1)
                        if maybe_id.replace(".", "").isdigit():
                            decoded_path = rest
                except:
                    pass

                # 安静兜底：某些词典会引用不存在的 googleapis.css（多为广告/字体相关），不影响释义
                # 为避免刷屏 not found，遇到该资源直接返回空 CSS。
                try:
                    if decoded_path.lower().endswith("googleapis.css"):
                        reply_empty(b"text/css")
                        return
                except:
                    pass


            except:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return



            # [关键修复] 健壮的 ID 解析 (防止 0.0.0.2 崩溃)
            target_ids = []
            if dict_id_str == "root" or dict_id_str.startswith("0.0.0."):
                with sqlite3.connect(DB_FILE) as conn:
                    target_ids = [r[0] for r in
                                  conn.execute("SELECT id FROM dict_info ORDER BY priority ASC").fetchall()]
            else:
                try:
                    # 如果有多个点 (0.0.0.2)，取最后一个部分 (2)
                    if "." in dict_id_str:
                        clean_id = dict_id_str.split('.')[-1]
                    else:
                        clean_id = dict_id_str

                    if clean_id.isdigit():
                        target_ids = [int(clean_id)]
                    else:
                        # 尝试 float 容错 (1.2 -> 1)
                        target_ids = [int(float(clean_id))]
                except:
                    # ID 解析失败，降级为全库搜索
                    with sqlite3.connect(DB_FILE) as conn:
                        target_ids = [r[0] for r in
                                      conn.execute("SELECT id FROM dict_info ORDER BY priority ASC").fetchall()]


            # 4. 物理文件回退查找（支持同目录的 .css/.js 等资源）
            def guess_mime(path_lower: str):
                if path_lower.endswith(('.jpg', '.jpeg')):
                    return b"image/jpeg"
                if path_lower.endswith('.png'):
                    return b"image/png"
                if path_lower.endswith('.gif'):
                    return b"image/gif"
                if path_lower.endswith('.bmp'):
                    return b"image/bmp"
                if path_lower.endswith('.ico'):
                    return b"image/x-icon"
                if path_lower.endswith('.webp'):
                    return b"image/webp"
                if path_lower.endswith('.svg'):
                    return b"image/svg+xml"
                if path_lower.endswith('.css'):
                    return b"text/css"
                if path_lower.endswith('.js'):
                    return b"text/javascript"
                if path_lower.endswith('.ttf'):
                    return b"font/ttf"
                if path_lower.endswith('.otf'):
                    return b"font/otf"
                if path_lower.endswith('.woff'):
                    return b"font/woff"
                if path_lower.endswith('.woff2'):
                    return b"font/woff2"
                if path_lower.endswith('.eot'):
                    return b"application/vnd.ms-fontobject"
                if path_lower.endswith('.mp3'):
                    return b"audio/mpeg"
                if path_lower.endswith('.wav'):
                    return b"audio/wav"
                if path_lower.endswith('.ogg'):
                    return b"audio/ogg"
                if path_lower.endswith('.spx'):
                    return b"audio/ogg"
                return b"application/octet-stream"


            rel_path = decoded_path.lstrip('/\\').replace('\\', '/')
            candidates = _expand_resource_candidates(rel_path)

            # 兼容二次编码：有些词典会把 % 也编码（%2523），所以再补一份原始路径的候选
            try:
                raw_rel = raw_res_path.lstrip('/\\').replace('\\', '/')
                for c in _expand_resource_candidates(raw_rel):
                    if c not in candidates:
                        candidates.append(c)
            except:
                pass


            # 4. 物理文件回退查找（支持同目录的 .css/.js 等资源）
            for cand in candidates:
                for did in target_ids:
                    try:
                        with sqlite3.connect(DB_FILE) as conn:
                            row = conn.execute("SELECT path FROM dict_info WHERE id=?", (did,)).fetchone()
                        if not row or not row[0]:
                            continue
                        dict_dir = os.path.dirname(row[0])
                        if not dict_dir:
                            continue
                        fp = _get_physical_resource_path(did, cand)
                        if fp:
                            with open(fp, "rb") as f:
                                reply_data(guess_mime(fp.lower()), f.read())
                            return
                    except Exception as e:
                        print(f"Physical resource error: {e}")

            # 5. 遍历查找（MDD 资源）
            for cand in candidates:
                for did in target_ids:
                    data = MDDCacheManager.get_resource_fuzzy(did, cand)
                    if data:
                        reply_data(guess_mime(cand.lower()), data)
                        return



            # 没找到资源
            try:
                low = decoded_path.lower()
                if low.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.ico',
                                 '.mp3', '.wav', '.ogg', '.spx', '.css', '.js',
                                 '.ttf', '.otf', '.woff', '.woff2', '.eot')):
                    print(f"[mdict] not found: url={url} dict_id={dict_id_str} path={decoded_path} target_ids={target_ids}")
            except:
                pass
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)


        except Exception as e:
            print(f"Handler Critical Error: {e}")
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)


# ==========================================
# 核心类 2: 页面交互逻辑 (集成新窗口拦截)
# ==========================================
# [main.py] 找到 DictWebPage 类，用下面的代码完全替换它

class DictWebPage(QWebEnginePage):
    # === [关键修复] 必须在这里定义信号，否则下面连接时会报错 ===
    word_lookup_requested = Signal(str, str)
    import_requested = Signal()  # <--- 你之前漏掉了这一行！

    # [关键] 拦截 target="_blank"
    def createWindow(self, _type):
        return self

    def acceptNavigationRequest(self, url: QUrl, _type, isMainFrame):
        u = url.toString()
        scheme = url.scheme()

        # 1. 绝对放行：JS 交互与页面内锚点
        if scheme == "javascript": return True
        if "#" in u and scheme not in ["http", "https", "entry"]: return True

        # 2. [修复] 拦截导入按钮并发送信号
        if u == "internal://import":
            self.import_requested.emit()  # 发射信号
            return False

        if u.startswith("internal://play"):
            try:
                q = QUrlQuery(url)
                src = q.queryItemValue("src")
                if src:
                    play_audio_from_mdict(src)
            except:
                pass
            return False

            # 3. 拦截特殊功能
        if u.lower().endswith(('.mp3', '.wav', '.ogg', '.spx')): return False


        # 4. 查词请求 (entry 协议)
        if scheme == "entry":
            if "query/" in u:
                try:
                    parts = u.split("query/", 1)[1].split("?")
                    w = urllib.parse.unquote(parts[0])
                    c = ""
                    if len(parts) > 1:
                        q = QUrlQuery("?" + parts[1])
                        c = q.queryItemValue("context")
                    if w: self.word_lookup_requested.emit(w, c)
                except:
                    pass
            return False

        # 5. 外部链接
        if scheme in ["http", "https"]:
            QDesktopServices.openUrl(url)
            return False

        return True


# ==========================================
# Part 2: UI 组件
# ==========================================

class FloatingText(QLabel):
    def __init__(self, parent, text="+10 XP", color="#4CAF50", pos=QPoint(0, 0)):
        super().__init__(parent)
        self.setText(text)
        self.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 18px; background: transparent;")
        self.adjustSize()
        self.move(pos)
        self.show()

        # Animation: Move Up + Fade Out
        self.anim_group = QObject()  # Just a dummy holder or handle manually

        # 1. Float Up
        self.anim_geo = QPropertyAnimation(self, b"pos")
        self.anim_geo.setDuration(1000)
        self.anim_geo.setStartValue(pos)
        self.anim_geo.setEndValue(QPoint(pos.x(), pos.y() - 50))
        self.anim_geo.setEasingCurve(QEasingCurve.OutQuad)

        # 2. Opacity (WindowOpacity doesn't work well on child widgets, use GraphicsEffect usually,
        # but simpler is just to delete it after moving)
        self.anim_geo.finished.connect(self.deleteLater)
        self.anim_geo.start()

# Add this class to main.py (e.g., before Sidebar class)
class MasteryRing(QWidget):
    def __init__(self, parent=None, size=60, stroke_width=6):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.percent = 0.0
        self.stroke_width = stroke_width
        self.target_percent = 0.0

        # Animation for smooth progress changes
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._update_step)

    def set_mastery(self, stage, max_stage=7):
        # Calculate percentage (0.0 to 1.0)
        self.target_percent = min(1.0, stage / float(max_stage))
        if self.target_percent < 0: self.target_percent = 0
        self.anim.start(15)  # 60 FPS approx

    def _update_step(self):
        diff = self.target_percent - self.percent
        if abs(diff) < 0.01:
            self.percent = self.target_percent
            self.anim.stop()
        else:
            self.percent += diff * 0.1  # Ease out
        self.update()

    def get_color(self):
        # Red (0%) -> Yellow (50%) -> Green (100%)
        p = self.percent
        if p < 0.5:
            # Red to Yellow
            return QColor(255, int(255 * (p * 2)), 0)
        else:
            # Yellow to Green
            return QColor(int(255 * (1 - (p - 0.5) * 2)), 200, 0)  # Slightly darker green for readability

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(self.stroke_width, self.stroke_width, -self.stroke_width, -self.stroke_width)

        # 1. Draw Background Ring (Grey)
        pen_bg = QPen(QColor("#E0E0E0"), self.stroke_width)
        pen_bg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawEllipse(rect)

        # 2. Draw Progress Ring (Colored)
        if self.percent > 0:
            pen_prog = QPen(self.get_color(), self.stroke_width)
            pen_prog.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_prog)
            # drawArc uses 1/16th of a degree
            # Start at 90 degrees (12 o'clock) = 90 * 16
            # Span is negative for clockwise
            span = -int(self.percent * 360 * 16)
            painter.drawArc(rect, 90 * 16, span)

        # 3. Draw Text (Percentage)
        painter.setPen(theme_manager.colors['text'])
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(int(self.height() * 0.25))
        painter.setFont(font)
        text = f"{int(self.percent * 100)}%"
        painter.drawText(self.rect(), Qt.AlignCenter, text)


# === [优化] 现代 SVG 图标侧边栏 ===
class Sidebar(QWidget):
    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(70)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 20, 5, 20)
        layout.setSpacing(15)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.buttons = {} # [新增] 用于存储按钮引用以便后续刷新

        # 图标数据
        self.icons_data = {
            0: (r"M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z", "查词"),
            1: (r"M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z", "历史"),
            2: (r"M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z", "单词本"),
            3: (r"M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H8V4h12v12zM10 9h8v2h-8zm0 3h4v2h-4zm0-6h8v2h-8z", "词库"),
            4: (r"M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-5 14H4v-6h11v6zm0-8H4V6h11v4zm5 8h-4v-6h4v6zm0-8h-4V6h4v4z", "新闻"),
            5: (r"M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z", "提词"),
            6: (r"M12 3a9 9 0 0 0 0 18c4.97 0 9-4.03 9-9s-4.03-9-9-9zM6.5 13.5A1.5 1.5 0 1 1 8 15a1.5 1.5 0 0 1-1.5-1.5zm2.5-4A1.5 1.5 0 1 1 10.5 11 1.5 1.5 0 0 1 9 9.5zm5 0A1.5 1.5 0 1 1 15.5 11 1.5 1.5 0 0 1 14 9.5zm2.5 4A1.5 1.5 0 1 1 18 15a1.5 1.5 0 0 1-1.5-1.5z", "主题")
        }

        for i in range(7):
            self.add_btn(i)

        layout.addStretch()
        self.refresh_icons() # 初始化时立即刷新一次

    def get_svg_icon(self, path_data, color):
        # 1. 构造 SVG XML
        # 现在 path_data 是纯坐标 (M...z)，放入 d="" 中就是合法的 SVG 了
        svg_content = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><path d="{path_data}" fill="{color}" /></svg>'

        # 2. 加载数据
        data = QByteArray(svg_content.encode('utf-8'))
        renderer = QSvgRenderer(data)

        # [调试自检]
        if not renderer.isValid():
            print(f"Error: SVG Render Failed for color {color}")
            return QIcon()

        # 3. 创建画布
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)

        # 4. 绘制
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, 32, 32))
        painter.end()

        return QIcon(pixmap)

    def add_btn(self, idx):
        path, text = self.icons_data[idx]  # 获取图标路径和中文名

        # [修改] 改用 QToolButton，因为它原生支持文字在图标下方
        btn = QToolButton()
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setText(text)  # 设置中文名

        # [关键] 设置图标在文字上方
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        # 调整尺寸策略
        btn.setFixedSize(60, 55)  # 稍微调高一点以容纳文字
        btn.setIconSize(QSize(26, 26))  # 图标尺寸

        # 设置样式
        # border: none; 去掉边框
        # border-radius: 8px; 圆角
        # font-size: 11px; 文字稍小
        btn.setStyleSheet("""
            QToolButton {
                border: none; 
                border-radius: 8px; 
                padding: 4px; 
                background: transparent;
                font-size: 11px;
                font-weight: 500;
            }
        """)

        if idx == 0: btn.setChecked(True)
        btn.clicked.connect(lambda: self.page_changed.emit(idx))

        self.layout().addWidget(btn)
        self.btn_group.addButton(btn, idx)
        self.buttons[idx] = btn  # 存入字典

    # [新增] 刷新图标方法
    def refresh_icons(self):
        # 获取当前主题的 Meta 颜色
        c = theme_manager.colors['meta']
        for idx, btn in self.buttons.items():
            path, _ = self.icons_data[idx]
            # 重新生成 SVG Icon
            icon = create_svg_icon(path, c)
            btn.setIcon(icon)


class NewsWebPage(QWebEnginePage):
    news_clicked = Signal(str)
    word_lookup_requested = Signal(str, str)

    def acceptNavigationRequest(self, url: QUrl, _type, isMainFrame):
        u = url.toString()

        # 拦截 entry:// 协议实现双击查词
        if url.scheme() == "entry":
            if "query/" in u:
                parts = u.split("query/", 1)[1].split("?")
                w = urllib.parse.unquote(parts[0])
                c = ""
                if len(parts) > 1:
                    q = QUrlQuery("?" + parts[1])
                    c = q.queryItemValue("context")
                if w: self.word_lookup_requested.emit(w, c)
            return False

        if u == "internal://back":
            QTimer.singleShot(10, lambda: self.news_clicked.emit(u))
            return False
        if url.scheme() in ["http", "https"]:
            QTimer.singleShot(10, lambda: self.news_clicked.emit(u))
            return False
        return True


class SearchSplitPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        self.last_dict_result = None
        self.last_loaded_news_query = ""

        # [新增] 工具栏图标路径
        self.tool_icons = {
            'pin': r"M16,12V4H17V2H7V4H8V12L6,14V16H11.2V22H12.8V16H18V14L16,12Z",
            'monitor': r"M19,3H14.82C14.4,1.84 13.3,1 12,1C10.7,1 9.6,1.84 9.18,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M12,3A1,1 0 0,1 13,3A1,1 0 0,1 12,4A1,1 0 0,1 11,3A1,1 0 0,1 12,3M7,7H17V5H19V19H5V5H7V7Z",
            'star_off': r"M12,15.39L8.24,17.66L9.23,13.38L5.91,10.5L10.29,10.13L12,6.09L13.71,10.13L18.09,10.5L14.77,13.38L15.76,17.66M22,9.24L14.81,8.63L12,2L9.19,8.63L2,9.24L7.45,13.97L5.82,21L12,17.27L18.18,21L16.54,13.97L22,9.24Z",
            'star_on': r"M12,17.27L18.18,21L16.54,13.97L22,9.24L14.81,8.62L12,2L9.19,8.62L2,9.24L7.45,13.97L5.82,21L12,17.27Z"
        }

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        self.left_widget = QWidget()
        v_left = QVBoxLayout(self.left_widget)
        v_left.setContentsMargins(0, 0, 0, 0)
        v_left.setSpacing(0)
        self.left_widget.setStyleSheet(f"background-color: {theme_manager.colors['sidebar']};")

        self.top_container = QFrame()
        v_top = QVBoxLayout(self.top_container)

        h_tools = QHBoxLayout()

        # [修改] 使用图标而非文字
        self.btn_pin = QPushButton() # 移除文字
        self.btn_pin.setCheckable(True)
        self.btn_pin.setFixedSize(36, 36) # 稍微调大一点
        self.btn_pin.setIconSize(QSize(22, 22))
        self.btn_pin.setToolTip("窗口置顶")
        self.btn_pin.clicked.connect(self.main.toggle_always_on_top)

        self.btn_monitor = QPushButton()
        self.btn_monitor.setCheckable(True)
        self.btn_monitor.setFixedSize(36, 36)
        self.btn_monitor.setIconSize(QSize(20, 20))
        self.btn_monitor.setToolTip("剪贴板监听")

        self.btn_fav = QPushButton()
        self.btn_fav.setFixedSize(36, 36)
        self.btn_fav.setIconSize(QSize(24, 24))
        self.btn_fav.setToolTip("收藏单词")
        self.btn_fav.clicked.connect(self.toggle_fav)

        h_tools.addWidget(self.btn_pin)
        h_tools.addWidget(self.btn_monitor)
        h_tools.addStretch()
        h_tools.addWidget(self.btn_fav)

        self.entry = QLineEdit()
        self.entry.setObjectName("MainSearchEntry")
        self.entry.setPlaceholderText("Search...")
        self.entry.setFixedHeight(38)
        self.entry.returnPressed.connect(self.on_enter_pressed)

        v_top.addLayout(h_tools)
        v_top.addWidget(self.entry)

        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.itemClicked.connect(lambda i: self.do_search(i.text(), from_list=True))

        v_left.addWidget(self.top_container)
        v_left.addWidget(self.list_widget)

        self.right_tabs = QTabWidget()
        self.right_tabs.currentChanged.connect(self.on_tab_changed)

        self.web_dict = QWebEngineView()
        self.page_dict = DictWebPage(self.web_dict)
        self.page_dict.word_lookup_requested.connect(lambda w, c: self.do_search(w, context=c))
        self.page_dict.import_requested.connect(lambda: self.main.switch_page(3))
        self.web_dict.setPage(self.page_dict)

        self.web_news = QWebEngineView()
        self.page_news = NewsWebPage(self.web_news)
        self.page_news.news_clicked.connect(self.handle_news_click)
        self.page_news.word_lookup_requested.connect(self.on_news_lookup)
        self.web_news.setPage(self.page_news)

        self.right_tabs.addTab(self.web_dict, "词典")
        self.right_tabs.addTab(self.web_news, "新闻")

        splitter.addWidget(self.left_widget)
        splitter.addWidget(self.right_tabs)
        splitter.setSizes([220, 880])
        splitter.setCollapsible(0, False)

        layout.addWidget(splitter)

        self.handler = MdictSchemeHandler()
        #self.handler = SherlockHandler()
        self.web_dict.page().profile().installUrlSchemeHandler(b"mdict", self.handler)

        self.vocab_cache = set()
        self.load_vocab_cache()
        self.current_context = ""
        self.current_source = ""
        self.is_in_reader_mode = False
        self.last_news_data = []
        self.current_news_query = ""

        # [新增] 初始刷新图标
        self.refresh_icons()
        self.init_shortcuts()

    # 在 SearchSplitPage 类内部添加
    def get_random_word(self):
        """从数据库随机获取一个单词作为每日一词"""
        try:
            with sqlite3.connect(DB_FILE) as conn:
                # 检查是否有词典
                cursor = conn.execute("SELECT count(*) FROM dict_info")
                if cursor.fetchone()[0] == 0:
                    return None  # 没有词典

                # 随机取一个词
                # 优化：为了速度，不要直接 RANDOM() 全表，而是限制范围或使用采样
                # 这里用简单的方法，假设库不大。如果库很大，建议用 max_id 方法。
                cursor = conn.execute("SELECT word, content, dict_id FROM standard_entries ORDER BY RANDOM() LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return {"word": row[0], "content": row[1], "dict_id": row[2]}
        except:
            pass
        return None

    # 在 SearchSplitPage 类内部添加
    def render_welcome_page(self):
        c = theme_manager.colors
        css = theme_manager.get_webview_css()

        # 1. 获取时间问候
        hour = datetime.now().hour
        if 5 <= hour < 12:
            greeting = "Good Morning"
        elif 12 <= hour < 18:
            greeting = "Good Afternoon"
        else:
            greeting = "Good Evening"

        # 2. 获取每日一词
        wotd_data = self.get_random_word()

        # 3. 构建 HTML
        # 如果没有词典，显示引导导入的界面
        if not wotd_data:
            center_content = f"""
                <div class="empty-state">
                    <div class="icon">📚</div>
                    <h2>欢迎使用 GeekDict Pro</h2>
                    <p>您还没有导入任何 MDX 词典文件。</p>
                    <button onclick="location.href='internal://import'">立即导入词典</button>
                </div>
            """
        else:
            # 简单的清理内容，只取前200个字符做预览
            try:
                raw_preview = wotd_data['content']
                if isinstance(raw_preview, bytes):
                    # 这里假设简单的解压逻辑，或者直接忽略内容只显示词
                    # 为了不引入复杂依赖，这里只显示单词，或者简单的提示
                    preview_text = "Click to view definition"
                else:
                    preview_text = raw_preview[:100] + "..."
            except:
                preview_text = "Explore this word..."

            center_content = f"""
                <div class="wotd-card" onclick="location.href='entry://query/{urllib.parse.quote(wotd_data['word'])}'">
                    <div class="label">每日一词</div>
                    <div class="word">{wotd_data['word']}</div>
                    <div class="tip">点击获取更多信息 ➔</div>
                </div>
            """

        html = f"""
        <html>
        <head>
            <style>
                {css}
                body {{
                    background-color: {c['bg']};
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 95vh;
                    margin: 0;
                    user-select: none;
                }}
                h1 {{ font-size: 2.5em; color: {c['text']}; margin-bottom: 10px; font-weight: 300; }}
                .subtitle {{ color: {c['meta']}; margin-bottom: 40px; font-size: 1.1em; }}

                .wotd-card {{
                    background: {c['card']};
                    border: 1px solid {c['border']};
                    border-radius: 16px;
                    padding: 30px 50px;
                    text-align: center;
                    cursor: pointer;
                    transition: transform 0.2s, box-shadow 0.2s;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.05);
                    min-width: 300px;
                }}
                .wotd-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 8px 25px rgba(0,0,0,0.1);
                    border-color: {c['primary']};
                }}
                .wotd-card .label {{ color: {c['primary']}; font-weight: bold; letter-spacing: 1px; font-size: 0.8em; text-transform: uppercase; margin-bottom: 10px; }}
                .wotd-card .word {{ font-size: 2.5em; font-weight: bold; color: {c['text']}; margin: 10px 0; }}
                .wotd-card .tip {{ color: {c['meta']}; font-size: 0.9em; }}

                .shortcuts {{
                    margin-top: 50px;
                    display: flex;
                    gap: 20px;
                }}
                .key-item {{ display: flex; align-items: center; gap: 8px; color: {c['meta']}; font-size: 0.9em; }}
                .key {{ 
                    background: {c['card']}; 
                    border: 1px solid {c['border']}; 
                    padding: 4px 8px; 
                    border-radius: 6px; 
                    font-family: monospace; 
                    font-weight: bold; 
                    box-shadow: 0 2px 0 {c['border']};
                }}

                .empty-state {{ text-align: center; }}
                .empty-state .icon {{ font-size: 60px; margin-bottom: 20px; }}
                button {{ 
                    background: {c['primary']}; color: white; border: none; padding: 10px 20px; 
                    border-radius: 20px; font-size: 16px; cursor: pointer; margin-top: 20px; 
                }}
                button:hover {{ opacity: 0.9; }}
            </style>
        </head>
        <body>
            <h1>{greeting}, Learner.</h1>
            <div class="subtitle">准备好拓展你的词汇了吗?</div>

            {center_content}

            <div class="shortcuts">
                <div class="key-item"><span class="key">Ctrl</span> + <span class="key">L</span> 聚焦搜索框</div>
                <div class="key-item"><span class="key">Enter</span> 搜索</div>
                <div class="key-item"><span class="key">Esc</span> 清除搜索框</div>
            </div>

            <script>
                // 简单的防闪烁
                document.body.style.opacity = 0;
                window.onload = function() {{ document.body.style.transition = 'opacity 0.5s'; document.body.style.opacity = 1; }};
            </script>
        </body>
        </html>
        """

        # 这里的 baseUrl 很重要，让它以为是在 mdict 环境下
        self.web_dict.setHtml(html, baseUrl=QUrl("mdict://root/"))

    # [新增] 刷新工具栏图标的方法
    def refresh_icons(self):
        c = theme_manager.colors['meta']
        # Pin 和 Monitor 使用 meta 颜色
        self.btn_pin.setIcon(create_svg_icon(self.tool_icons['pin'], c))
        self.btn_monitor.setIcon(create_svg_icon(self.tool_icons['monitor'], c))
        # 刷新收藏按钮
        self.check_fav(self.entry.text())

    def init_shortcuts(self):
        self.shortcut_esc = QShortcut(QKeySequence("Esc"), self)
        self.shortcut_esc.activated.connect(self.on_esc_pressed)
        self.shortcut_focus = QShortcut(QKeySequence("Ctrl+L"), self)
        self.shortcut_focus.activated.connect(lambda: (self.entry.setFocus(), self.entry.selectAll()))
        self.shortcut_focus2 = QShortcut(QKeySequence("Alt+D"), self)
        self.shortcut_focus2.activated.connect(lambda: (self.entry.setFocus(), self.entry.selectAll()))
        self.shortcut_enter = QShortcut(QKeySequence("Return"), self)
        self.shortcut_enter.activated.connect(self.on_enter_pressed)

    def on_esc_pressed(self):
        self.entry.clear()
        self.entry.setFocus()

    def on_enter_pressed(self):
        self.do_search(self.entry.text(), update_news=True)

    def load_vocab_cache(self):
        try:
            with sqlite3.connect(DB_FILE) as conn:
                self.vocab_cache = {r[0] for r in conn.execute("SELECT word FROM vocabulary")}
        except:
            pass

    def highlight_text(self, text, keyword):
        if not keyword or not text:
            return text
        pattern = re.compile(f"({re.escape(keyword)})", re.IGNORECASE)
        # [修复] 增加 !important 以覆盖深色模式的强制样式
        hl_style = "background-color: #ffeb3b !important; color: #000000 !important; border-radius: 2px; padding: 0 2px;"
        return pattern.sub(f"<span style='{hl_style}'>\\1</span>", text)

    # === [新增] HTML 安全的高亮函数 ===
    def highlight_html_safe(self, html_content, keyword):
        if not keyword or not html_content:
            return html_content

        # [修复] 增加 !important
        # 解释: 黑色文字(#000)配黄色背景(#ffeb3b)在任何深浅模式下都是高对比度可见的
        hl_style = "background-color: #ffeb3b !important; color: #000000 !important; border-radius: 2px; padding: 0 2px; box-shadow: 0 1px 1px rgba(0,0,0,0.1);"

        tokens = re.split(r'(<[^>]+>)', html_content)
        processed = []
        kw_pattern = re.compile(f"({re.escape(keyword)})", re.IGNORECASE)

        for token in tokens:
            if token.startswith('<') and token.endswith('>'):
                processed.append(token)
            else:
                if keyword.lower() in token.lower():
                    subbed = kw_pattern.sub(f"<span style='{hl_style}'>\\1</span>", token)
                    processed.append(subbed)
                else:
                    processed.append(token)

        return "".join(processed)


    def on_tab_changed(self, index):
        if index == 1:
            if self.current_news_query and self.current_news_query != self.last_loaded_news_query:
                self.is_in_reader_mode = False
                self.web_news.setHtml("<h3>加载新闻中...</h3>")
                self.news_worker = NewsWorker(self.current_news_query)
                self.news_worker.news_ready.connect(self.render_news)
                self.news_worker.start()

    def on_news_lookup(self, word, context):
        self.right_tabs.setCurrentIndex(0)
        self.do_search(word, context=context)

    def do_search(self, text, push=True, update_news=False, context="", from_list=False):
        text = text.strip()
        if not text: return

        self.entry.setText(text)
        self.check_fav(text)
        self.current_context = context
        self.current_source = "News" if context else "Dict"

        self.current_news_query = text

        if not from_list:
            if self.list_widget.count() > 0 and self.list_widget.item(0).text() == text:
                pass
            else:
                items = self.list_widget.findItems(text, Qt.MatchExactly)
                if items: self.list_widget.takeItem(self.list_widget.row(items[0]))
                self.list_widget.insertItem(0, text)
            self.list_widget.setCurrentRow(0)

        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    "INSERT INTO search_history (word, last_access_time, search_count) VALUES (?, ?, 1) ON CONFLICT(word) DO UPDATE SET last_access_time=excluded.last_access_time",
                    (text, time.time()))
                conn.commit()
        except:
            pass

        self.worker = SearchWorker(text)
        self.worker.results_ready.connect(self.render_dict)
        self.worker.start()

        is_news_tab_active = (self.right_tabs.currentIndex() == 1)

        if update_news or is_news_tab_active:
            if is_news_tab_active:
                self.is_in_reader_mode = False
                self.web_news.setHtml("<h3>Loading News...</h3>")
            else:
                self.right_tabs.setCurrentIndex(0)

            self.news_worker = NewsWorker(text)
            self.news_worker.news_ready.connect(self.render_news)
            self.news_worker.start()

    def render_dict(self, q, rows, suggestions):
        rows_list = list(rows) if rows else []
        self.last_dict_result = (q, rows_list, suggestions)

        c = theme_manager.colors
        css = theme_manager.get_webview_css()

        # [优化] 判断是否需要高亮：
        # 1. 搜索词不为空
        # 2. 为了避免英文常用词(如 "the", "a") 满屏黄，限制英文至少2个字符，中文1个字符即可
        need_highlight = False
        if q:
            is_zh = any(u'\u4e00' <= char <= u'\u9fa5' for char in q)
            if is_zh or len(q) > 1:
                need_highlight = True

        if not rows_list:
            sugg_html = ""
            if suggestions:
                links = [
                    f"<a href='entry://query/{urllib.parse.quote(s)}' style='margin:5px;display:inline-block;padding:5px;background:#eee;border-radius:4px;'>{s}</a>"
                    for s in suggestions]
                sugg_html = f"<div style='text-align:center;margin-top:20px'>Did you mean:<br>{''.join(links)}</div>"

            html_content = f"<html><head><style>{css}</style></head><body><h3 style='text-align:center;color:#888;margin-top:50px'>Not found: {q}</h3>{sugg_html}</body></html>"
            self.web_dict.setHtml(html_content)
            return

        # 动作栏专用 JS：无论是否 iframe 模式都要注入，否则 Speak/Copy 会失效
        action_js = """
            <script>
                // 兼容：部分词典内容会引用 googletag（广告脚本），在离线环境会导致 ReferenceError
                // 这里提供一个最小空实现，避免控制台刷错，不影响正常释义渲染。
                (function(){
                    try {
                        if (!window.googletag) window.googletag = { cmd: [] };
                        if (!window.googletag.cmd) window.googletag.cmd = [];
                        if (typeof window.googletag.cmd.push !== 'function') {
                            window.googletag.cmd.push = function(fn){ try { if (typeof fn === 'function') fn(); } catch(e) {} };
                        }
                    } catch(e) {}
                })();

                function speak(t) {
                    try {
                        window.speechSynthesis.cancel();
                        var m = new SpeechSynthesisUtterance(t);
                        m.lang = 'en-US';
                        window.speechSynthesis.speak(m);
                    } catch (e) {
                        console.log('speak failed', e);
                    }
                }
                function copyText(btn, t) {
                    try {
                        const el = document.createElement('textarea');
                        el.value = t;
                        document.body.appendChild(el);
                        el.select();
                        document.execCommand('copy');
                        document.body.removeChild(el);
                        if (btn) {
                            var original = btn.innerText;
                            btn.innerText = "✅ Copied";
                            setTimeout(function() { btn.innerText = original; }, 1500);
                        }
                    } catch (e) {
                        console.log('copy failed', e);
                    }
                }
            </script>
        """


        # 词典内容交互 JS（仅在单词卡片区域启用拦截逻辑）
        js = """
            <script>
                // 双击查词
                document.addEventListener('dblclick', function(e) { 
                    var s = window.getSelection().toString().trim(); if(s) window.location.href = 'entry://query/' + encodeURIComponent(s); 
                });

                // === 捕获阶段点击拦截器（只处理词典内容里的链接） ===
                document.addEventListener('click', function(e) { 
                    var t = e.target.closest('a'); 
                    if (t) { 
                        // 放行动作栏里的链接（Images/Google/Wiki）
                        try { if (t.closest('.action-bar')) return; } catch(ex) {}

                        var href = t.getAttribute('href'); 
                        if (!href) return;


                        if (href.startsWith('#') || href.startsWith('javascript:')) {
                            return; 
                        }

                        // [修复] 音频拦截逻辑优化
                        var lower = href.toLowerCase(); 
                        if (lower.endsWith('.mp3') || lower.endsWith('.wav') || lower.endsWith('.spx') || lower.endsWith('.ogg')) { 
                            e.stopPropagation(); 
                            e.preventDefault(); 

                            var card = t.closest('.card');
                            var dictId = (window.__dictId || (card ? card.getAttribute('data-dict-id') : '1'));

                            var cleaned = href;
                            try {
                                var lowHref = (cleaned || '').toLowerCase();
                                if (lowHref.startsWith('sound://')) cleaned = cleaned.substring(8);
                                else if (lowHref.startsWith('sound:')) cleaned = cleaned.substring(6);
                            } catch(e) {}

                            // 兼容：部分词典会硬编码 mdict://0.0.0.x/ 或 mdict://root/ 作为“伪 dict_id”
                            // 这里统一映射回当前 iframe 的真实 dictId，避免 internal 播放去错词典。
                            try {
                                var lowClean = (cleaned || '').toLowerCase();
                                if (lowClean.startsWith('mdict://0.0.0.') || lowClean.startsWith('mdict://root/')) {
                                    var tmp = cleaned;
                                    try {
                                        if ((tmp || '').toLowerCase().startsWith('mdict://')) tmp = tmp.substring(8);
                                    } catch(e) {}
                                    if (tmp.indexOf('/') > -1) {
                                        tmp = tmp.substring(tmp.indexOf('/') + 1);
                                    }
                                    cleaned = tmp; // 此时 cleaned 应为相对路径
                                }
                            } catch(e) {}


                            var filename = (cleaned || '').replace('mdict://', '').replace('entry://', ''); 

                            if (filename.indexOf('/') === -1) {
                                filename = dictId + '/' + filename;
                            } else {
                                // 如果仍然带着 0.0.0.x 这样的 host，也强制改成当前 dictId
                                try {
                                    var lowFn = (filename || '').toLowerCase();
                                    if (lowFn.startsWith('0.0.0.') || lowFn.startsWith('root/')) {
                                        filename = dictId + '/' + filename.substring(filename.indexOf('/') + 1);
                                    }
                                } catch(e) {}

                            }

                            var playUrl = 'mdict://' + filename;


                            // 优先使用 HTML5 Audio（oald10 的 ogg 通常可直接播放）
                            // 如果播放失败（例如某些 QtWebEngine 构建不带 mp3 编解码），再降级走 internal://play 由系统播放器处理
                            var playViaInternal = function() {
                                window.location.href = 'internal://play?src=' + encodeURIComponent(playUrl);
                            };

                            if (playUrl.toLowerCase().endsWith('.spx')) {
                                playViaInternal();
                                return false;
                            }

                            try {
                                var a = new Audio(playUrl);
                                var p = a.play();
                                if (p && p.catch) {
                                    p.catch(function() { playViaInternal(); });
                                }
                            } catch (err) {
                                playViaInternal();
                            }
                            return false; 

                        } 

                        // ... (后续的单词跳转拦截逻辑保持不变) ...
                        
                        var isResource = false;
                        var resExts = ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.ttf', '.woff'];
                        var cleanPath = href.split('?')[0].split('#')[0].toLowerCase();

                        for (var i = 0; i < resExts.length; i++) {
                            if (cleanPath.endsWith(resExts[i])) { isResource = true; break; }
                        }
                        if (cleanPath.indexOf('css/') > -1 || cleanPath.indexOf('theme/') > -1) isResource = true;

                        if (!isResource) {
                            e.stopPropagation(); 
                            e.preventDefault(); 
                            var word = href;
                            if (word.indexOf('://') > -1) {
                                var parts = word.split('://');
                                var payload = parts[1]; 
                                if (payload.indexOf('/') > -1) {
                                    word = payload.substring(payload.lastIndexOf('/') + 1);
                                } else {
                                    word = payload;
                                }
                            }
                            try { word = decodeURIComponent(word); } catch(e) {}
                            word = word.split('#')[0];

                            if (word && word.trim() !== "") {
                                window.location.href = 'entry://query/' + encodeURIComponent(word);
                            }
                            return false;
                        }
                    } 
                }, true); 
            </script>
            """

        safe_q = q.replace("'", "\\'")

        # 美化后的操作栏 CSS
        actions = f"""
            <style>
                .action-bar {{
                    padding: 10px 0;
                    margin-bottom: 15px;
                    display: flex;
                    gap: 10px;
                    border-bottom: 1px solid var(--border);
                }}
                .action-btn {{
                    background-color: var(--bg); 
                    border: 1px solid var(--border); 
                    color: var(--text);
                    padding: 8px 16px; 
                    border-radius: 20px; 
                    font-size: 13px; 
                    cursor: pointer;
                    text-decoration: none; 
                    display: inline-flex; 
                    align-items: center; 
                    gap: 6px;
                    transition: all 0.2s ease;
                    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
                }}
                .action-btn:hover {{ 
                    background-color: var(--hover); 
                    border-color: var(--primary); 
                    color: var(--primary); 
                    transform: translateY(-1px);
                    box-shadow: 0 3px 6px rgba(0,0,0,0.1);
                }}
                .action-btn:active {{ transform: translateY(0); }}
            </style>
            <div class="action-bar">
                <button class="action-btn" onclick="speak('{safe_q}')">🔊 Speak</button>
                <button class="action-btn" onclick="copyText(this, '{safe_q}')">📋 Copy</button>
                <a class="action-btn" href="https://www.google.com/search?tbm=isch&q={safe_q}">🖼️ Images</a>
                <a class="action-btn btn-google" href="https://www.google.com/search?q={safe_q}">🌏 Google</a>
                <a class="action-btn" href="https://en.wikipedia.org/wiki/{safe_q}">📖 Wiki</a>
            </div>
            """

        unique_dict_ids = set()
        for r in rows_list:
            if 'dict_id' in r:
                unique_dict_ids.add(r['dict_id'])

        iframe_mode = len(unique_dict_ids) > 1

        if iframe_mode:
            with IFRAME_HTML_LOCK:
                IFRAME_HTML_CACHE.clear()

        css_links = []
        if not iframe_mode:
            for did in unique_dict_ids:
                css_links.append(f'<link rel="stylesheet" type="text/css" href="mdict://css/{did}">')


        css_links_html = "\n".join(css_links)

        iframe_css = ""
        iframe_resize_js = ""
        if iframe_mode:
            iframe_css = """
                    .entry-frame { width: 100%; border: 0; display: block; overflow: hidden; }
            """

            iframe_resize_js = """
                <script>
                    window.addEventListener('message', function(e) {
                        var d = e.data || {};
                        if (d.type !== 'frame-height') return;
                        var f = document.getElementById(d.id);
                        if (f) { f.style.height = d.h + 'px'; }
                    });
                </script>
            """

        def _normalize_entry_content(d_id, html_content):
            if not html_content:
                return html_content
            try:
                # 修复 mdx 内置的 mdict://0.0.0.x 绝对资源链接
                html_content = re.sub(r"mdict://0\.0\.0\.\d+/", f"mdict://{d_id}/", html_content, flags=re.IGNORECASE)
                # 兼容 sound://
                html_content = re.sub(r"(?i)sound://", f"mdict://{d_id}/", html_content)
                html_content = re.sub(r"(?i)sound:", f"mdict://{d_id}/", html_content)
            except:
                pass
            return html_content

        html = [
            f"""<html><head><meta charset='utf-8'>
                <style>
                    @font-face {{ font-family: 'Kingsoft Phonetic Plain'; src: url('mdict://theme/kingsoft_phonetic.ttf'); }}
                    {css}
                    {iframe_css}
                    body {{ padding: 20px; max-width: 900px; margin: 0 auto; }}
                    .entry-content img {{ max-width: 100%; height: auto; cursor: default; pointer-events: none; border: none !important; outline: none !important; }} 


                    /* 卡片式设计 */
                    .card {{ 
                        background: var(--card); 
                        padding: 25px; 
                        margin-bottom: 25px; 
                        border-radius: var(--radius); 
                        box-shadow: var(--shadow); 
                        border: 1px solid var(--border);
                    }} 

                    /* 词典徽章 */
                    .badge {{ 
                        background: var(--bg); 
                        color: var(--primary); 
                        border: 1px solid var(--primary);
                        padding: 3px 8px; 
                        border-radius: 12px; 
                        font-size: 12px; 
                        font-weight: 600;
                        letter-spacing: 0.5px;
                        text-transform: uppercase;
                    }} 

                    /* 标题栏 */
                    .card-header {{
                        display: flex;
                        align-items: center;
                        gap: 10px;
                        margin-bottom: 15px;
                        padding-bottom: 10px;
                        border-bottom: 1px dashed var(--border);
                    }}

                    .card-word {{ font-size: 18px; font-weight: bold; color: var(--text); }}
                    img {{ max-width: 100%; border-radius: 8px; }}
                </style>
                {action_js}
                {css_links_html} {'' if iframe_mode else js}
                {iframe_resize_js}
                </head><body>"""
        ]

        html.append(actions)

        for idx, r in enumerate(rows_list):
            d_id = r.get('dict_id', 1)
            content = r['content']
            content = _normalize_entry_content(d_id, content)

            # 高亮处理
            if need_highlight:
                content = self.highlight_html_safe(content, q)


            entry_body = f"<div class='entry-content'>{content}</div>"

            if iframe_mode:
                frame_id = f"frame-{d_id}-{idx}"
                frame_token = f"{d_id}-{idx}-{int(time.time() * 1000)}"
                entry_html = f"""<html><head><meta charset='utf-8'>
                    <base href=\"mdict://{d_id}/\">
                    <style>
                        @font-face {{ font-family: 'Kingsoft Phonetic Plain'; src: url('mdict://theme/kingsoft_phonetic.ttf'); }}
                        {css}
                        html, body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; }}
                        img {{ max-width: 100%; height: auto; cursor: default; pointer-events: none; border: none !important; outline: none !important; }}
                    </style>


                    <link rel=\"stylesheet\" type=\"text/css\" href=\"mdict://css/{d_id}/__style.css\">
                    <script>window.__dictId = '{d_id}';</script>
                    <script>
                        // 兼容：词典脚本可能依赖 googletag（广告相关），离线时会报 googletag is not defined
                        // 注意：这里处于 Python f-string 中，JS 花括号需要用 {{ / }} 转义
                        (function(){{
                            try {{
                                if (!window.googletag) window.googletag = {{ cmd: [] }};
                                if (!window.googletag.cmd) window.googletag.cmd = [];
                                if (typeof window.googletag.cmd.push !== 'function') {{
                                    window.googletag.cmd.push = function(fn){{ try {{ if (typeof fn === 'function') fn(); }} catch(e) {{}} }};
                                }}
                            }} catch(e) {{}}
                        }})();
                    </script>

                    {js}


                    <script>
                        (function() {{
                            function send() {{
                                var h = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
                                window.parent.postMessage({{type: 'frame-height', id: '{frame_id}', h: h}}, '*');
                            }}
                            var mo = new MutationObserver(function() {{ send(); }});
                            mo.observe(document.documentElement, {{subtree: true, childList: true, attributes: true, characterData: true}});
                            window.addEventListener('load', send);
                            window.addEventListener('resize', send);
                            setTimeout(send, 50);
                        }})();
                    </script>
                    </head><body>{content}</body></html>"""
                with IFRAME_HTML_LOCK:
                    IFRAME_HTML_CACHE[frame_token] = entry_html.encode('utf-8')
                entry_body = f"<iframe id='{frame_id}' class='entry-frame' scrolling='no' src='mdict://iframe/{frame_token}'></iframe>"



            # 使用新的 HTML 结构
            html.append(
                f"""
                    <div class='card' data-dict-id='{d_id}'>
                        <div class='card-header'>
                            <span class='badge'>{r['dict_name']}</span> 
                            <span class='card-word'>{r['word']}</span>
                        </div>
                        {entry_body}
                    </div>
                    """
            )


        html.append("</body></html>")

        # 单词结果页 baseUrl：如果只有一个词典，尽量用该词典自身作为 base，避免相对资源跑去 root 导致找不到/串库
        base_url = "mdict://root/"
        if (not iframe_mode) and len(unique_dict_ids) == 1:
            try:
                only_id = list(unique_dict_ids)[0]
                base_url = f"mdict://{only_id}/"
            except:
                pass

        self.web_dict.setHtml("".join(html), baseUrl=QUrl(base_url))


    def refresh_webview(self):
        if self.last_dict_result:
            self.render_dict(*self.last_dict_result)
        else:
            # [修改] 不再显示空白页，而是显示欢迎页
            self.render_welcome_page()

    def render_news(self, results, query):
        self.last_loaded_news_query = query
        if self.is_in_reader_mode: return
        self.last_news_data = results
        c = theme_manager.colors
        css = theme_manager.get_webview_css()

        html = [
            f"<html><head><style>{css} body {{ padding:15px; font-family:'Segoe UI'; }} .news-item {{ padding:15px; background:var(--card); margin-bottom:10px; border-radius:6px; border:1px solid var(--border); }} a {{ color:var(--primary); text-decoration:none; font-weight:bold; font-size:16px; display:block; margin-bottom:5px; }} .meta {{ font-size:12px; color:var(--meta); margin-bottom:8px; }} </style></head><body>"]

        if not results:
            html.append("<h3>No news found.</h3>")
        else:
            for r in results:
                t = self.highlight_text(r['title'], query)
                b = self.highlight_text(r['body'], query)
                html.append(
                    f"<div class='news-item'><a href='{r['url']}'>{t}</a><div class='meta'>{r['source']} • {r['date']}</div><p>{b}</p></div>")

        html.append("</body></html>")
        self.web_news.setHtml("".join(html))

    def handle_news_click(self, url):
        if url == "internal://back":
            self.is_in_reader_mode = False
            self.render_news(self.last_news_data, self.current_news_query)
            return

        self.is_in_reader_mode = True
        self.web_news.setHtml("<h3>Loading Reader Mode...</h3>")
        self.news_content_worker = NewsContentWorker(url)
        self.news_content_worker.content_ready.connect(self.render_reader)
        self.news_content_worker.start()

    def render_reader(self, title, body, url):
        c = theme_manager.colors
        css = theme_manager.get_webview_css()
        body = self.highlight_text(body, self.current_news_query)
        js_smart = """
        <script>
        document.addEventListener('dblclick', function(e) {
            var s = window.getSelection().toString().trim();
            if(s) { var ctx = window.getSelection().anchorNode.parentNode.innerText.substring(0, 200);
                 window.location.href = 'entry://query/' + encodeURIComponent(s) + '?context=' + encodeURIComponent(ctx); }
        });
        </script>
        """
        html = f"""
        <html><head><style>
            {css} 
            body {{ max-width:800px; margin:0 auto; padding:20px; padding-top: 70px; font-family:'Georgia'; line-height:1.6; }} 
            .back-btn {{ position: fixed; top: 15px; left: 15px; z-index: 9999; display: inline-block; padding: 10px 20px; background: #eee; border-radius: 20px; border: 1px solid #ddd; text-decoration: none; color: #333; box-shadow: 0 4px 6px rgba(0,0,0,0.1); font-family: 'Segoe UI', sans-serif; font-weight: bold; cursor: pointer; }}
            .back-btn:hover {{ background: #e0e0e0; transform: translateY(-1px); }}
        </style>{js_smart}</head><body>
        <a href='internal://back' class='back-btn'>⬅ 返回到新闻列表</a>
        <h1>{title}</h1>
        <div style='color:#888;margin-bottom:20px'>新闻源: <a href='{url}'>Link</a></div>
        <div>{body}</div>
        </body></html>
        """
        self.web_news.setHtml(html)

    # [修改] 收藏状态改为切换 SVG 图标
    def check_fav(self, word):
        has = word in self.vocab_cache
        c = theme_manager.colors['meta']

        if has:
            # 已收藏：金色实心星
            icon = create_svg_icon(self.tool_icons['star_on'], "#fbc02d")
            self.btn_fav.setIcon(icon)
            self.btn_fav.setProperty("is_fav", True)
        else:
            # 未收藏：Meta颜色空心星
            icon = create_svg_icon(self.tool_icons['star_off'], c)
            self.btn_fav.setIcon(icon)
            self.btn_fav.setProperty("is_fav", False)

        # 强制刷新样式以应用边框颜色变化
        self.btn_fav.style().unpolish(self.btn_fav)
        self.btn_fav.style().polish(self.btn_fav)

    def toggle_fav(self):
        w = self.entry.text().strip()
        if not w: return
        if w in self.vocab_cache:
            self.vocab_cache.remove(w)
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("DELETE FROM vocabulary WHERE word=?", (w,))
        else:
            self.vocab_cache.add(w)
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO vocabulary (word, added_time, next_review_time, context, source) VALUES (?,?,?,?,?)",
                    (w, time.time(), time.time(), self.current_context, self.current_source))
        self.check_fav(w)


class VocabPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel("<h2>📖 词汇本</h2>"))
        header.addStretch()
        btn_export = QPushButton("📤 导出Anki")
        btn_export.clicked.connect(self.export_anki)
        header.addWidget(btn_export)
        layout.addLayout(header)

        self.tabs = QTabWidget()

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["单词", "阶段", "来源", "语境"])
        self.tree.itemDoubleClicked.connect(lambda item, col: self.window().switch_to_search(item.text(0)))

        self.tabs.addTab(self.tree, "列表查看")

        self.flashcard_widget = self.create_flashcard_ui()
        self.tabs.addTab(self.flashcard_widget, "闪卡")

        # ==========================================
        # [修改] 1. 连接标签切换信号
        # ==========================================
        self.tabs.currentChanged.connect(self.on_tab_changed)

        layout.addWidget(self.tabs)
        self.refresh_data()

    # ==========================================
    # [修改] 2. 新增标签切换处理方法
    # ==========================================
    def on_tab_changed(self, index):
        # 如果切到了 index 1 (即 Flashcards 页面)
        if index == 1:
            self.load_cards()
        # 如果切回 index 0 (列表页)，顺便刷新一下列表数据
        elif index == 0:
            self.refresh_data()

    def refresh_data(self):
        self.tree.clear()
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute(
                "SELECT word, review_stage, source, context FROM vocabulary ORDER BY added_time DESC").fetchall()
        for r in rows:
            QTreeWidgetItem(self.tree, [r[0], str(r[1]), r[2] or "", r[3] or ""])

    def export_anki(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "geek_vocab.txt", "Text (*.txt)")
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f:
                iterator = QTreeWidgetItemIterator(self.tree)
                while iterator.value():
                    item = iterator.value()
                    front = item.text(0)
                    back = f"{item.text(3)}<br><br><small>{item.text(2)}</small>"
                    f.write(f"{front}\t{back}\n")
                    iterator += 1
            QMessageBox.information(self, "Success", "Exported successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # [修改] 重写 create_flashcard_ui 方法
    def create_flashcard_ui(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)

        # 顶部控制栏
        top_bar = QHBoxLayout()

        # [NEW] Add Mastery Ring
        self.mastery_ring = MasteryRing(self, size=50)
        top_bar.addWidget(self.mastery_ring)

        self.lbl_progress = QLabel("Ready")
        # Style the progress label to look like "Level" info
        self.lbl_progress.setStyleSheet("font-weight: bold; color: var(--meta); margin-left: 10px;")
        top_bar.addWidget(self.lbl_progress)
        l.addLayout(top_bar)

        self.fc_stack = QStackedWidget()

        # Page 0: 空状态
        pg_empty = QLabel("🎉 No cards due right now!\nTake a break.")
        pg_empty.setAlignment(Qt.AlignCenter)
        pg_empty.setStyleSheet("font-size: 18px; color: #888;")
        self.fc_stack.addWidget(pg_empty)

        # Page 1: 测验/正面 (Quiz / Front)
        self.pg_quiz = QWidget()
        self.pg_quiz.setObjectName("QuizPage")  # 用于样式
        ql = QVBoxLayout(self.pg_quiz)
        ql.setSpacing(20)
        ql.addStretch()

        # 单词显示 (初始可能隐藏，或者作为提示)
        self.lbl_fc_word = QLabel("Word")
        self.lbl_fc_word.setAlignment(Qt.AlignCenter)
        self.lbl_fc_word.setStyleSheet("font-size: 24px; font-weight: bold; color: var(--primary);")
        # 默认隐藏单词本身，让用户看句子猜，如果没句子再显示单词
        ql.addWidget(self.lbl_fc_word)

        # 句子显示区域
        self.lbl_sentence = QLabel("Loading context...")
        self.lbl_sentence.setWordWrap(True)
        self.lbl_sentence.setAlignment(Qt.AlignCenter)
        self.lbl_sentence.setStyleSheet("font-size: 20px; font-style: italic; color: var(--text); padding: 20px;")
        ql.addWidget(self.lbl_sentence)

        # 选项按钮区域 (Grid Layout)
        self.grid_options = QGridLayout()
        self.option_btns = []
        for i in range(4):
            btn = QPushButton(f"Option {i}")
            btn.setFixedHeight(60)
            btn.setCursor(Qt.PointingHandCursor)
            # 绑定点击事件，使用 closure 捕获 index
            btn.clicked.connect(lambda checked, idx=i: self.check_answer(idx))
            self.grid_options.addWidget(btn, i // 2, i % 2)
            self.option_btns.append(btn)

        ql.addLayout(self.grid_options)

        # “显示答案”按钮 (用于放弃思考或Fallback模式)
        self.btn_show_answer = QPushButton("Show Definition ⬇️")
        self.btn_show_answer.setFlat(True)
        self.btn_show_answer.clicked.connect(lambda: self.reveal_answer(False))  # False means not correct
        ql.addWidget(self.btn_show_answer)

        ql.addStretch()
        self.fc_stack.addWidget(self.pg_quiz)

        # Page 2: 背面/详情 (Back / Detail)
        pg_back = QWidget()
        bl = QVBoxLayout(pg_back)

        # 结果反馈栏
        self.lbl_result = QLabel("")
        self.lbl_result.setAlignment(Qt.AlignCenter)
        self.lbl_result.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        bl.addWidget(self.lbl_result)

        self.web_fc = QWebEngineView()
        # 记得设置 Scheme Handler
        self.web_fc.page().profile().installUrlSchemeHandler(b"mdict", MdictSchemeHandler())
        bl.addWidget(self.web_fc)

        # 评分按钮
        h_btns = QHBoxLayout()
        btn_fail = QPushButton("❌ 不记得 (重新记忆)")
        btn_pass = QPushButton("✅ 记得了(下一个)")
        btn_fail.setObjectName("BtnFail")
        btn_pass.setObjectName("BtnPass")

        btn_fail.setFixedHeight(45)
        btn_pass.setFixedHeight(45)

        btn_fail.clicked.connect(lambda: self.rate_card(False))
        btn_pass.clicked.connect(lambda: self.rate_card(True))

        h_btns.addWidget(btn_fail)
        h_btns.addWidget(btn_pass)
        bl.addLayout(h_btns)

        self.fc_stack.addWidget(pg_back)

        l.addWidget(self.fc_stack)

        self.card_queue = []
        self.current_card = None
        self.current_quiz_data = None  # 存储当前题目的答案

        return w

    def load_cards(self):
        # 简单的复习算法：取超期或新词
        with sqlite3.connect(DB_FILE) as conn:
            self.card_queue = conn.execute(
                "SELECT word, review_stage, xp FROM vocabulary WHERE next_review_time < ? OR review_stage=0 ORDER BY next_review_time ASC LIMIT 20",
                (time.time() + 60,)
            ).fetchall()

        if self.card_queue:
            self.lbl_progress.setText(f"Session: {len(self.card_queue)} cards")
            self.next_card()
        else:
            self.fc_stack.setCurrentIndex(0)

    def next_card(self):
        if not self.card_queue:
            self.fc_stack.setCurrentIndex(0)
            return

        self.current_card = self.card_queue.pop(0)
        word = self.current_card[0]
        stage = self.current_card[1]

        # [NEW] Update Ring
        self.mastery_ring.set_mastery(stage)

        # 重置 UI 状态
        self.lbl_fc_word.setText(word)
        self.lbl_sentence.setText("Analyzing context...")
        self.fc_stack.setCurrentIndex(1)

        # 禁用按钮直到题目加载完成
        for btn in self.option_btns:
            btn.setEnabled(False)
            btn.setText("...")
            btn.setStyleSheet("")  # 清除颜色

        # 启动 QuizWorker 生成题目
        self.quiz_worker = QuizWorker(word)
        self.quiz_worker.data_ready.connect(self.on_quiz_ready)
        self.quiz_worker.start()

        # 同时后台预加载释义 (SearchWorker) 用于背面显示
        self.worker = SearchWorker(word)
        self.worker.results_ready.connect(self.render_fc_back)
        self.worker.start()

    def on_quiz_ready(self, data):
        self.current_quiz_data = data

        if data:
            # === 成功生成填空题 ===
            self.lbl_sentence.setText(data['question'])
            self.lbl_fc_word.setVisible(False)  # 隐藏单词，强迫看句子

            # 设置选项
            options = data['options']
            for i, btn in enumerate(self.option_btns):
                btn.setText(options[i])
                btn.setEnabled(True)
                btn.setProperty("is_correct", options[i] == data['answer'])

            self.btn_show_answer.setText("我不会")
        else:
            # === 没有例句 (Fallback 模式) ===
            self.lbl_sentence.setText("(未找到语境语句)")
            self.lbl_fc_word.setVisible(True)  # 显示单词

            # 隐藏选项按钮，只留“显示答案”
            for btn in self.option_btns:
                btn.setVisible(False)
            self.btn_show_answer.setText("展示释义")

    def check_answer(self, idx):
        btn = self.option_btns[idx]
        is_correct = btn.property("is_correct")

        if is_correct:
            # 1. Style update
            btn.setStyleSheet("background-color: #a5d6a7; color: #1b5e20; border: 2px solid #2e7d32;")

            # 2. [NEW] Gamification - Floating Text
            # Calculate center of the button for the popup
            center_pt = btn.mapTo(self, QPoint(btn.width() // 2, 0))
            FloatingText(self, text="+50 XP", color="#2e7d32", pos=center_pt)

            # 3. [NEW] Visually update ring immediately (optimistic UI)
            # Access current stage from current_card tuple
            current_stage = self.current_card[1]
            self.mastery_ring.set_mastery(current_stage + 1)

            # 4. Proceed
            QTimer.singleShot(800, lambda: self.reveal_answer(True))
        else:
            btn.setStyleSheet("background-color: #ef9a9a; color: #b71c1c;")
            btn.setEnabled(False)

            # [NEW] Negative feedback? Optional.
            center_pt = btn.mapTo(self, QPoint(btn.width()//2, 0))
            FloatingText(self, text="Try Again", color="#c62828", pos=center_pt)

    def reveal_answer(self, was_correct):
        # 切换到背面
        self.fc_stack.setCurrentIndex(2)

        if was_correct:
            self.lbl_result.setText("🎉 回答正确")
            self.lbl_result.setStyleSheet("color: #2e7d32;")
        else:
            self.lbl_result.setText("Study the meaning:")
            self.lbl_result.setStyleSheet("color: var(--text);")

        # 恢复选项按钮可见性 (为了下一张卡)
        for btn in self.option_btns:
            btn.setVisible(True)

    def rate_card(self, known):
        # current_card is now (word, stage, xp)
        w, stage, current_xp = self.current_card

        new_stage = stage + 1 if known else 0
        new_stage = min(new_stage, len(EBBINGHAUS_INTERVALS) - 1)
        next_t = time.time() + EBBINGHAUS_INTERVALS[new_stage]

        # [NEW] XP Calculation
        # Base XP = 10. Bonus for higher stages.
        xp_gain = 10 * (new_stage if known else 1)
        new_xp = (current_xp or 0) + xp_gain if known else (current_xp or 0) + 1

        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("UPDATE vocabulary SET review_stage=?, next_review_time=?, xp=? WHERE word=?",
                         (new_stage, next_t, new_xp, w))
            conn.commit()

        self.next_card()

    def render_fc_back(self, q, rows, suggestions):
        """渲染单词卡片背面的释义内容"""
        # 获取全局 CSS 样式，确保支持深色模式
        css = theme_manager.get_webview_css()

        html_head = f"""
        <html>
        <head>
            <style>
                {css} 
                body {{ padding: 15px; font-family: 'Segoe UI', sans-serif; }}
                .dict-card {{ 
                    border-bottom: 1px solid var(--border); 
                    margin-bottom: 20px; 
                    padding-bottom: 15px; 
                }}
                .dict-name {{ 
                    color: var(--meta); 
                    font-size: 12px; 
                    font-weight: bold; 
                    text-transform: uppercase; 
                    margin-bottom: 8px;
                }}
            </style>
        </head>
        <body>
        """

        body_content = ""
        if not rows:
            body_content = f"<h3>No definition found for: {q}</h3>"
        else:
            cards = []
            for r in rows:
                # 简单清洗一下内容
                content = r['content']
                cards.append(
                    f"<div class='dict-card'>"
                    f"<div class='dict-name'>{r['dict_name']}</div>"
                    f"<div class='entry-content'>{content}</div>"
                    f"</div>"
                )
            body_content = "".join(cards)

        html_end = "</body></html>"

        # 设置 HTML 内容，baseUrl 设为 mdict://root/ 以便加载图片和 CSS
        self.web_fc.setHtml(html_head + body_content + html_end, baseUrl=QUrl("mdict://root/"))


class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # [修改] 增加大标题，与其他页面统一
        header = QHBoxLayout()
        header.addWidget(QLabel("<h2>📰 新闻源</h2>"))
        header.addStretch()
        layout.addLayout(header)

        grp_rss = QGroupBox("管理新闻RSS")
        vl = QVBoxLayout(grp_rss)
        self.list_rss = QListWidget()

        h_add = QHBoxLayout()
        self.entry_name = QLineEdit(placeholderText="名称")
        self.entry_url = QLineEdit(placeholderText="RSS链接")
        btn_add = QPushButton("添加")
        btn_add.clicked.connect(self.add_rss)
        h_add.addWidget(self.entry_name);
        h_add.addWidget(self.entry_url);
        h_add.addWidget(btn_add)

        btn_del = QPushButton("删除已选")
        btn_del.clicked.connect(self.del_rss)

        vl.addWidget(self.list_rss)
        vl.addLayout(h_add)
        vl.addWidget(btn_del)
        layout.addWidget(grp_rss)

        self.refresh_rss()

    def refresh_rss(self):
        self.list_rss.clear()
        with sqlite3.connect(DB_FILE) as conn:
            for r in conn.execute("SELECT id, name, url FROM rss_sources"):
                i = QListWidgetItem(f"{r[1]} - {r[2]}")
                i.setData(Qt.UserRole, r[0])
                self.list_rss.addItem(i)

    def add_rss(self):
        n, u = self.entry_name.text(), self.entry_url.text()
        if n and u:
            with sqlite3.connect(DB_FILE) as conn: conn.execute("INSERT INTO rss_sources (name, url) VALUES (?,?)",
                                                                (n, u))
            self.refresh_rss()

    def del_rss(self):
        item = self.list_rss.currentItem()
        if item:
            with sqlite3.connect(DB_FILE) as conn: conn.execute("DELETE FROM rss_sources WHERE id=?",
                                                                (item.data(Qt.UserRole),))
            self.refresh_rss()


class ColorPreviewWidget(QWidget):
    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.setFixedSize(120, 30)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        preview_keys = ['sidebar', 'bg', 'card', 'text', 'primary']
        w = self.width() / len(preview_keys)
        h = self.height()
        radius = 4

        for i, key in enumerate(preview_keys):
            c_str = self.colors.get(key, "#000000")
            painter.setBrush(QColor(c_str))
            rect = QRect(int(i * w), 0, int(w), int(h))

            if i == 0:
                painter.drawRoundedRect(rect, radius, radius)
                painter.drawRect(rect)
            elif i == len(preview_keys) - 1:
                painter.drawRect(rect)
            else:
                painter.drawRect(rect)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(200, 200, 200, 100), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)


class ThemePage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        title = QLabel("<h2>🎨 选择皮肤主题</h2>")
        title.setStyleSheet("color: var(--text);")
        layout.addWidget(title)

        subtitle = QLabel("请选择配色.")
        subtitle.setStyleSheet("color: var(--meta); font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(subtitle)

        self.list_widget = QListWidget()
        self.list_widget.setCursor(Qt.PointingHandCursor)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: 1px solid var(--border);
                border-radius: 8px;
                outline: none;
            }
            QListWidget::item {
                background-color: var(--card);
                border-bottom: 1px solid var(--border);
                padding: 10px;
                margin: 0px;
            }
            QListWidget::item:selected {
                background-color: var(--hover);
                border-left: 4px solid var(--primary);
            }
            QListWidget::item:hover {
                background-color: var(--hover);
            }
        """)

        self.populate_themes()
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        layout.addWidget(self.list_widget)

    def populate_themes(self):
        presets = theme_manager.PRESETS
        for name, colors in presets.items():
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 60))
            item.setData(Qt.UserRole, name)
            self.list_widget.addItem(item)

            container = QWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(20, 5, 20, 5)

            lbl_name = QLabel(name)
            lbl_name.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {theme_manager.colors['text']};")

            is_current = (name == theme_manager.current_theme_name)
            lbl_check = QLabel("✅" if is_current else "")
            lbl_check.setFixedWidth(30)

            palette_preview = ColorPreviewWidget(colors)

            h_layout.addWidget(lbl_name)
            h_layout.addWidget(lbl_check)
            h_layout.addStretch()
            h_layout.addWidget(palette_preview)

            self.list_widget.setItemWidget(item, container)

            if is_current:
                self.list_widget.setCurrentItem(item)

    def on_item_clicked(self, item):
        theme_name = item.data(Qt.UserRole)
        if theme_name:
            theme_manager.set_theme(theme_name)
            self.main.reload_theme()

            scroll_val = self.list_widget.verticalScrollBar().value()
            row = self.list_widget.row(item)
            self.list_widget.clear()
            self.populate_themes()
            self.list_widget.setCurrentRow(row)
            self.list_widget.verticalScrollBar().setValue(scroll_val)


class DictManagerPage(QWidget):
    def __init__(self):
        super().__init__()
        l = QVBoxLayout(self)
        h = QHBoxLayout()
        h.addWidget(QLabel("<h2>📚 词典文件</h2>"))
        btn = QPushButton("导入 .mdx词典")
        btn.clicked.connect(self.add)
        h.addWidget(btn)
        l.addLayout(h)

        h_tools = QHBoxLayout()
        btn_up = QPushButton("⬆ 上移");
        btn_up.clicked.connect(self.move_up)
        btn_down = QPushButton("⬇ 下移");
        btn_down.clicked.connect(self.move_down)
        btn_del = QPushButton("🗑️ 删除");
        btn_del.clicked.connect(self.delete_dict)
        h_tools.addWidget(btn_up);
        h_tools.addWidget(btn_down);
        h_tools.addWidget(btn_del);
        h_tools.addStretch()
        l.addLayout(h_tools)

        self.lst = QListWidget()
        l.addWidget(self.lst)
        self.refresh()

    def refresh(self):
        self.lst.clear()
        with sqlite3.connect(DB_FILE) as conn:
            for r in conn.execute("SELECT id, name, priority FROM dict_info ORDER BY priority"):
                item = QListWidgetItem(r[1])
                item.setData(Qt.UserRole, r[0])
                item.setData(Qt.UserRole + 1, r[2])
                self.lst.addItem(item)

    # === [修改] main.py -> DictManagerPage 类内部 ===

    def add(self):
        # 1. 改为单选 (getOpenFileName)，不再允许一次选多个
        path, _ = QFileDialog.getOpenFileName(self, "Select Dictionary", "", "MDX Files (*.mdx)")
        if not path:
            return

        # 2. 创建模态进度条对话框
        # range设为(0, 0)会显示一个"忙碌中"的动画条，适合这种无法精确预知总进度的任务
        progress = QProgressDialog("初始化中...", None, 0, 0, self)
        progress.setWindowTitle("导入词典中...")
        progress.setWindowModality(Qt.WindowModal)  # [关键] 阻塞主窗口，防止用户重复操作
        progress.setMinimumDuration(0)  # 立即显示，不等待
        progress.setCancelButton(None)  # 禁用取消按钮，防止数据库写入中途强行中断导致损坏

        # 美化一下进度条（可选，跟随你的 Fusion 风格）
        progress.setStyleSheet("""
            QProgressDialog { background-color: white; border-radius: 8px; }
            QLabel { font-size: 14px; color: #333; margin: 10px; font-weight: bold; }
            QProgressBar { border: 1px solid #bbb; border-radius: 4px; text-align: center; height: 18px; }
            QProgressBar::chunk { background-color: #2196F3; width: 10px; }
        """)

        # 3. 启动后台 Worker
        # 注意：IndexerWorker 依然接受列表参数，所以我们把单路径包在列表里传进去
        self.idx = IndexerWorker([path])

        # 4. 信号连接
        # 将 Worker 的文字进度信号连接到对话框的标签上
        self.idx.progress_sig.connect(progress.setLabelText)

        # 当 Worker 完成时：
        # 1. 关闭进度条
        self.idx.finished_sig.connect(progress.accept)
        # 2. 刷新列表
        self.idx.finished_sig.connect(self.refresh)

        # 5. 启动线程并阻塞 UI
        self.idx.start()

        # exec() 会开启一个新的事件循环并阻塞代码继续向下执行，直到 progress.accept() 被调用
        progress.exec()

        # 导入完成后的提示
        QMessageBox.information(self, "成功", f"成功导入的词典:\n{os.path.basename(path)}")

    def move_up(self):
        row = self.lst.currentRow()
        if row > 0: self.swap(row, row - 1)

    def move_down(self):
        row = self.lst.currentRow()
        if row >= 0 and row < self.lst.count() - 1: self.swap(row, row + 1)

    def swap(self, r1, r2):
        i1, i2 = self.lst.item(r1), self.lst.item(r2)
        id1, p1 = i1.data(Qt.UserRole), i1.data(Qt.UserRole + 1)
        id2, p2 = i2.data(Qt.UserRole), i2.data(Qt.UserRole + 1)
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("UPDATE dict_info SET priority=? WHERE id=?", (p2, id1))
            conn.execute("UPDATE dict_info SET priority=? WHERE id=?", (p1, id2))
            conn.commit()
        self.refresh()
        self.lst.setCurrentRow(r2)

    def delete_dict(self):
        row = self.lst.currentRow()
        if row >= 0:
            dict_id = self.lst.item(row).data(Qt.UserRole)
            if QMessageBox.question(self, "Confirm", "Delete this dictionary?") == QMessageBox.Yes:
                with sqlite3.connect(DB_FILE) as conn:
                    conn.execute("DELETE FROM dict_info WHERE id=?", (dict_id,))
                    conn.execute("DELETE FROM standard_entries WHERE dict_id=?", (dict_id,))
                    conn.commit()
                self.refresh()


class HistoryPage(QWidget):
    def __init__(self, main_win):
        super().__init__()
        self.main = main_win
        l = QVBoxLayout(self)
        l.addWidget(QLabel("<h2>🕒 搜索历史</h2>"))
        self.lst = QListWidget()
        self.lst.itemDoubleClicked.connect(lambda i: self.main.switch_to_search(i.text()))
        l.addWidget(self.lst)
        btn = QPushButton("清除搜索历史");
        btn.clicked.connect(self.clear);
        l.addWidget(btn)

    def refresh(self):
        self.lst.clear()
        with sqlite3.connect(DB_FILE) as conn:
            for r in conn.execute("SELECT word FROM search_history ORDER BY last_access_time DESC LIMIT 100"):
                self.lst.addItem(r[0])

    def clear(self):
        with sqlite3.connect(DB_FILE) as conn: conn.execute("DELETE FROM search_history")
        self.refresh()


# ==========================================
# 替换 main.py 中的 TextAnalyzerPage 类
# ==========================================

class TextAnalyzerPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main = main_window
        layout = QHBoxLayout(self)

        # === 左侧：输入区 ===
        left_panel = QWidget()
        l_layout = QVBoxLayout(left_panel)
        l_layout.setContentsMargins(0, 0, 0, 0)

        l_layout.addWidget(QLabel("<h3>📝 原始文本</h3>"))

        # 工具栏
        h_tools = QHBoxLayout()
        btn_load_txt = QPushButton("📂 导入 .txt")
        btn_load_epub = QPushButton("📖 导入 .epub")
        btn_clear = QPushButton("🗑️ 清除")

        btn_load_txt.clicked.connect(self.load_txt)
        btn_load_epub.clicked.connect(self.load_epub)
        btn_clear.clicked.connect(self.clear_text)

        h_tools.addWidget(btn_load_txt)
        h_tools.addWidget(btn_load_epub)
        h_tools.addWidget(btn_clear)
        h_tools.addStretch()
        l_layout.addLayout(h_tools)

        # 显式设置输入框样式，防止白字白底
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("在这里粘贴文本或者上传文件进行分析...")
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: var(--card);
                color: var(--text);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
            }
        """)
        l_layout.addWidget(self.text_edit)

        self.btn_analyze = QPushButton("🚀 分析和提取词汇(最多提取1000高频词)")
        self.btn_analyze.setFixedHeight(45)
        self.btn_analyze.setStyleSheet(
            "background-color: var(--primary); color: white; font-weight: bold; font-size: 14px; border-radius: 8px;")
        self.btn_analyze.clicked.connect(self.start_analysis)
        l_layout.addWidget(self.btn_analyze)

        # === 右侧：结果区 ===
        right_panel = QWidget()
        r_layout = QVBoxLayout(right_panel)
        r_layout.setContentsMargins(0, 0, 0, 0)

        r_layout.addWidget(QLabel("<h3>✨ 提取的高频词汇</h3>"))

        # 显式设置列表样式
        self.list_results = QListWidget()
        self.list_results.setSelectionMode(QAbstractItemView.SingleSelection)  # 允许单选高亮，方便视觉确认
        self.list_results.setStyleSheet("""
            QListWidget {
                background-color: var(--card);
                border: 1px solid var(--border);
                border-radius: 8px;
                outline: none;
            }
            QListWidget::item {
                padding: 0px; /* 让 ItemWidget 填满 */
                border-bottom: 1px solid var(--border);
            }
            QListWidget::item:selected {
                background-color: var(--hover); /* 选中行变色 */
            }
        """)

        # [新增] 连接行点击信号 -> 实现点击行切换 Checkbox
        self.list_results.itemClicked.connect(self.on_row_clicked)

        r_layout.addWidget(self.list_results)

        # 底部操作栏
        h_actions = QHBoxLayout()
        self.chk_select_all = QCheckBox("全选")
        self.chk_select_all.setChecked(True)  # 默认全选
        # [修改] 使用 clicked 信号，比 stateChanged 更稳定
        self.chk_select_all.clicked.connect(self.toggle_select_all)

        btn_add_vocab = QPushButton("➕ 添加选中的")
        btn_add_vocab.setStyleSheet("background-color: #2e7d32; color: white; padding: 5px 15px; border-radius: 6px;")
        btn_add_vocab.clicked.connect(self.add_to_vocab)

        h_actions.addWidget(self.chk_select_all)
        h_actions.addStretch()
        h_actions.addWidget(btn_add_vocab)
        r_layout.addLayout(h_actions)

        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([450, 350])

        layout.addWidget(splitter)

        self.current_candidates = []

    def clear_text(self):
        self.text_edit.clear()
        self.list_results.clear()

    def load_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Text File", "", "Text Files (*.txt);;All Files (*.*)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.text_edit.setPlainText(f.read())
                    FloatingText(self.text_edit, text="文件已加载!", color=theme_manager.colors['primary'],
                                 pos=QPoint(50, 50))
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法读取文件:\n{e}")

    def load_epub(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open eBook", "", "EPUB Files (*.epub)")
        if path:
            self.text_edit.setPlainText("正在处理电子书... 请稍候.")
            QApplication.processEvents()
            text = extract_text_from_epub(path)
            self.text_edit.setPlainText(text)
            FloatingText(self.text_edit, text="电子书已加载!", color=theme_manager.colors['primary'],
                         pos=QPoint(50, 50))

    def start_analysis(self):
        text = self.text_edit.toPlainText().strip()
        if not text: return

        self.btn_analyze.setText("分析中... ⏳")
        self.btn_analyze.setEnabled(False)
        self.list_results.clear()

        self.worker = AnalyzerWorker(text)
        self.worker.analysis_ready.connect(self.on_analysis_finished)
        self.worker.start()

    def on_analysis_finished(self, results):
        self.btn_analyze.setText("🚀 分析和提取词汇(1000词)")
        self.btn_analyze.setEnabled(True)
        self.current_candidates = results

        self.list_results.clear()
        if not results:
            self.list_results.addItem("没有找到有效的单词.")
            return

        # 填充列表
        for word, count in results:
            item = QListWidgetItem()
            # 强制设置 Item 高度
            item.setSizeHint(QSize(0, 50))

            # 自定义 Widget
            w = QWidget()
            # 这里的 transparent 很重要，让点击事件能穿透或者背景色能显示
            w.setStyleSheet("background: transparent;")
            hl = QHBoxLayout(w)
            hl.setContentsMargins(10, 5, 10, 5)

            # 复选框
            chk = QCheckBox(word)
            chk.setStyleSheet(f"font-weight: bold; font-size: 15px; color: var(--text);")
            chk.setChecked(True)  # 默认勾选
            # [关键] 设置 objectName 方便后续查找
            chk.setObjectName("chk_word")
            # 设为包含鼠标事件透明，这样点击复选框周围的文字也能触发 itemClicked (可选，视体验而定)
            # chk.setAttribute(Qt.WA_TransparentForMouseEvents, True) # 如果开启这行，必须通过点击行来勾选

            lbl_info = QLabel(f"{count} 次")
            lbl_info.setStyleSheet(
                "color: var(--meta); font-size: 12px; background: var(--bg); padding: 2px 6px; border-radius: 10px;")

            # 查词按钮 (小眼睛)
            btn_peek = QToolButton()
            btn_peek.setText("👁️")
            btn_peek.setToolTip("预览定义")
            btn_peek.setStyleSheet("border: none; background: transparent;")
            btn_peek.clicked.connect(lambda _, w=word: self.main.switch_to_search(w))

            hl.addWidget(chk)
            hl.addStretch()
            hl.addWidget(lbl_info)
            hl.addWidget(btn_peek)

            self.list_results.addItem(item)
            self.list_results.setItemWidget(item, w)

            # 只存字符串数据
            item.setData(Qt.UserRole, word)

        self.chk_select_all.setChecked(True)

        msg = QMessageBox(self)
        msg.setWindowTitle("完成")
        msg.setText(f"找到了 {len(results)} 个潜在生词!")
        msg.setStyleSheet(
            f"QMessageBox {{ background-color: var(--card); color: var(--text); }} QLabel {{ color: var(--text); }}")
        msg.exec()

    # [修复] 点击行切换复选框
    def on_row_clicked(self, item):
        widget = self.list_results.itemWidget(item)
        if widget:
            # 查找复选框
            chk = widget.findChild(QCheckBox, "chk_word")
            if chk:
                # 切换状态
                chk.setChecked(not chk.isChecked())

    # [修复] 全选/全不选功能
    def toggle_select_all(self):
        # 直接获取当前全选框的状态
        target_state = self.chk_select_all.isChecked()

        # 遍历所有行
        for i in range(self.list_results.count()):
            item = self.list_results.item(i)
            widget = self.list_results.itemWidget(item)
            if widget:
                # 查找这一行的复选框
                chk = widget.findChild(QCheckBox, "chk_word")
                if chk:
                    chk.setChecked(target_state)

    def add_to_vocab(self):
        words_to_add = []
        for i in range(self.list_results.count()):
            item = self.list_results.item(i)
            widget = self.list_results.itemWidget(item)
            word = item.data(Qt.UserRole)

            if widget and word:
                chk = widget.findChild(QCheckBox, "chk_word")
                if chk and chk.isChecked():
                    words_to_add.append(word)

        if not words_to_add:
            QMessageBox.information(self, "提示", "请先选择要添加的单词")
            return

        # 批量入库
        count = 0
        with sqlite3.connect(DB_FILE) as conn:
            for w in words_to_add:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO vocabulary (word, added_time, next_review_time, source) VALUES (?,?,?,?)",
                        (w, time.time(), time.time(), "Text Analysis"))
                    count += 1
                except:
                    pass

        msg = QMessageBox(self)
        msg.setWindowTitle("成功")
        msg.setText(f"成功添加 {count} 个单词到生词本!")
        msg.setStyleSheet(
            f"QMessageBox {{ background-color: var(--card); color: var(--text); }} QLabel {{ color: var(--text); }}")
        msg.exec()


# ==========================================
# Part 3: 主窗口
# ==========================================

class ModernMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("极客词典 QQ3543945893")
        self.resize(1100, 750)

        # === [修复] 使用绝对路径加载图标 ===
        # 1. 获取图片的绝对路径
        icon_path_png = resource_path("app_icon.png")
        icon_path_ico = resource_path("app_icon.ico")

        # 2. 调试打印 (打包时如果不显示console看不到，但逻辑上是有用的)
        # print(f"尝试加载图标: {icon_path_png}")

        # 3. 强制加载
        # 优先加载 PNG (清晰度高)，如果找不到再尝试 ICO
        if os.path.exists(icon_path_png):
            self.setWindowIcon(QIcon(icon_path_png))
        elif os.path.exists(icon_path_ico):
            self.setWindowIcon(QIcon(icon_path_ico))
        else:
            # 如果都找不到，打印个错误或者弹个窗提醒自己
            # 这一步能帮你确认是不是文件真的没打包进去
            print("❌ 严重错误：图标文件未找到！")

        DatabaseManager.init_db()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self.switch_page)
        main_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # === [优化 1: 懒加载初始化] ===
        # 1. 只有 Search 页是启动时必须加载的
        self.page_search = SearchSplitPage(self)
        self.stack.addWidget(self.page_search)  # Index 0

        # 2. 其他页面初始化为 None，并放入占位符以保持索引对齐
        self.page_history = None
        self.page_vocab = None
        self.page_dict = None
        self.page_settings = None
        self.page_theme = None
        self.page_analyzer = None

        # 为 Index 0-6 填充透明占位符，保证 sidebar 按钮点击时索引正确
        for _ in range(6):
            self.stack.addWidget(QWidget())

        self.watcher = ClipboardWatcher()
        self.watcher.text_copied.connect(self.on_clipboard)

        # 初始加载主题（只影响已存在的 Search 页）
        self.reload_theme()

    def switch_page(self, idx):
        # === [优化 2: 切换时才实例化] ===
        if idx == 1:
            if self.page_history is None:
                # 第一次点击：创建页面 -> 替换占位符 -> 刷新引用
                self.page_history = HistoryPage(self)
                self.replace_placeholder(1, self.page_history)
            self.page_history.refresh()  # 保持原有逻辑

        elif idx == 2:
            if self.page_vocab is None:
                # VocabPage 含 WebEngine，延迟加载效果最明显
                self.page_vocab = VocabPage()
                self.replace_placeholder(2, self.page_vocab)
            self.page_vocab.refresh_data()  # 保持原有逻辑

        elif idx == 3:
            if self.page_dict is None:
                self.page_dict = DictManagerPage()
                self.replace_placeholder(3, self.page_dict)
            self.page_dict.refresh()  # 保持原有逻辑（虽然 DictManagerPage 初始化里refresh了，多调一次无妨）

        elif idx == 4:  # Settings (News Sources)
            if self.page_settings is None:
                self.page_settings = SettingsPage()
                self.replace_placeholder(4, self.page_settings)
            self.page_settings.refresh_rss()

        elif idx == 5:
            if self.page_analyzer is None:
                self.page_analyzer = TextAnalyzerPage(self)
                self.replace_placeholder(5, self.page_analyzer)

        elif idx == 6:  # [NEW] Analyzer Page
            if self.page_theme is None:
                self.page_theme = ThemePage(self)
                self.replace_placeholder(6, self.page_theme)

        # 0 号页面始终存在
        elif idx == 0:
            self.page_search.entry.setFocus()

        # 切换显示
        self.stack.setCurrentIndex(idx)

    def replace_placeholder(self, index, widget):
        """辅助函数：移除指定索引的占位符，插入真实页面"""
        # 获取旧的占位符
        old_widget = self.stack.widget(index)
        # 移除它
        self.stack.removeWidget(old_widget)
        # 在原位置插入新页面
        self.stack.insertWidget(index, widget)
        # 销毁占位符释放内存
        old_widget.deleteLater()
        # 重新应用主题样式（因为新创建的页面可能没吃到全局样式）
        # 注意：这里不需要调 self.reload_theme()，因为 setStyleSheet 是全局生效的，
        # 新组件加入时会自动继承 QMainWindow 的样式表。

    def switch_to_search(self, word):
        self.sidebar.btn_group.button(0).setChecked(True)
        self.switch_page(0)
        self.page_search.do_search(word, from_list=False)

    def toggle_always_on_top(self):
        on = self.windowFlags() & Qt.WindowStaysOnTopHint
        self.setWindowFlag(Qt.WindowStaysOnTopHint, not on)
        self.show()

    def on_clipboard(self, text):
        if self.page_search.btn_monitor.isChecked():
            if self.isMinimized(): self.showNormal()
            self.raise_()
            self.switch_to_search(word=text)  # 修正参数名调用

    def reload_theme(self):
        c = theme_manager.colors

        # 判断深色模式
        bg_color = c['bg'].lstrip('#')
        is_dark = False
        if len(bg_color) == 6:
            r, g, b = tuple(int(bg_color[i:i + 2], 16) for i in (0, 2, 4))
            is_dark = (r * 0.299 + g * 0.587 + b * 0.114) < 128

        if is_dark:
            btn_fail_bg = "#4a2c2c"
            btn_fail_fg = "#ff8a80"
            btn_pass_bg = "#2c4a2c"
            btn_pass_fg = "#a5d6a7"
        else:
            btn_fail_bg = "#ffebee"
            btn_fail_fg = "#c62828"
            btn_pass_bg = "#e8f5e9"
            btn_pass_fg = "#2e7d32"

        qss = f"""
            /* 全局基础 */
            QMainWindow {{ background-color: {c['bg']}; }}
            QWidget {{ font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; font-size: 14px; color: {c['text']}; }}
            
            /* === [关键修复 3] 全局弹窗样式修复 === */
            QMessageBox, QDialog {{
                background-color: {c['card']};
                color: {c['text']};
            }}
            
            /* 强制弹窗内的标签颜色 */
            QMessageBox QLabel, QDialog QLabel {{
                color: {c['text']};
            }}
            
            /* 弹窗内的按钮 */
            QMessageBox QPushButton, QDialog QPushButton {{
                background-color: {c['bg']};
                border: 1px solid {c['border']};
                padding: 5px 15px;
                border-radius: 5px;
                color: {c['text']};
            }}
            QMessageBox QPushButton:hover {{
                background-color: {c['primary']};
                color: white;
            }}

            /* [修改] 强制纯黑背景 Tooltip，防止在浅色主题下看不清 */
            QToolTip {{
                background-color: #000000; 
                color: #ffffff; 
                border: 1px solid #ffffff;
                padding: 6px 10px; 
                border-radius: 4px; 
                opacity: 255;
            }}

            /* 列表与表头 */
            QTreeWidget {{
                background-color: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px; outline: none;
            }}
            QTreeWidget::item {{ padding: 8px; border-bottom: 1px solid {c['border']}; }}
            QTreeWidget::item:selected {{ background-color: {c['hover']}; color: {c['primary']}; border-left: 3px solid {c['primary']}; }}
            QTreeWidget::item:hover {{ background-color: {c['hover']}; }}

            QHeaderView::section {{
                background-color: {c['sidebar']}; color: {c['meta']}; padding: 6px; border: none; border-bottom: 1px solid {c['border']}; font-weight: bold;
            }}

            /* 单词本卡片 */
            QFrame#FlashcardFront {{ background-color: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
            QLabel#FlashcardWord {{ font-size: 32px; font-weight: bold; color: {c['primary']}; }}

            QPushButton#BtnFail {{ background-color: {btn_fail_bg}; color: {btn_fail_fg}; border: none; font-weight: bold; }}
            QPushButton#BtnPass {{ background-color: {btn_pass_bg}; color: {btn_pass_fg}; border: none; font-weight: bold; }}

            /* 侧边栏 */
            QWidget#Sidebar {{ background-color: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
            /* 侧边栏按钮 - [修改] 适配 QToolButton */
            QWidget#Sidebar QToolButton {{ 
                color: {c['meta']}; 
                border: none; 
                border-radius: 8px; 
                background-color: transparent; 
                padding: 4px;
                margin: 2px 5px;
            }}
            QWidget#Sidebar QToolButton:hover {{ 
                background-color: {c['hover']}; 
                color: {c['text']};
            }}
            QWidget#Sidebar QToolButton:checked {{ 
                background-color: {c['bg']}; 
                color: {c['primary']}; 
                font-weight: bold;
                /* 左侧指示条需要调整一下位置，因为按钮变高了 */
                border-left: 3px solid {c['primary']}; 
                border-radius: 4px 8px 8px 4px;      
            }}

            /* [修改] 搜索框：边框常驻，不再是 transparent */
            QLineEdit#MainSearchEntry {{ 
                border: 2px solid {c['border']}; /* 默认显示边框 */
                border-radius: 12px; 
                padding: 8px 15px; 
                background: {c['card']}; 
                color: {c['text']}; 
                font-size: 16px; 
                selection-background-color: {c['primary']}; 
            }}
            QLineEdit#MainSearchEntry:focus {{ 
                border: 2px solid {c['primary']}; /* 聚焦时变为主色 */
                background: {c['bg']}; 
            }}

            /* 通用输入框 */
            QLineEdit {{
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 6px;
                background-color: {c['card']};
                color: {c['text']};
            }}
            QLineEdit:focus {{ border: 1px solid {c['primary']}; }}

            /* 左侧列表 */
            QListWidget {{ background-color: {c['sidebar']}; border: none; outline: none; }}
            QListWidget::item {{ padding: 10px 15px; border-bottom: 1px solid {c['border']}; margin: 0; }}
            QListWidget::item:selected {{ background-color: {c['card']}; color: {c['primary']}; border-left: 3px solid {c['primary']}; font-weight: bold; }}
            QListWidget::item:hover {{ background-color: {c['hover']}; }}

            /* 选项卡 */
            QTabWidget::pane {{ border: none; background: {c['bg']}; }}
            QTabWidget::tab-bar {{ alignment: left; }}
            QTabBar::tab {{ background: transparent; padding: 10px 20px; margin-right: 5px; color: {c['meta']}; font-weight: 500; border-bottom: 3px solid transparent; }}
            QTabBar::tab:hover {{ color: {c['text']}; background: {c['hover']}; }}
            QTabBar::tab:selected {{ color: {c['primary']}; border-bottom: 3px solid {c['primary']}; font-weight: bold; }}

            /* 顶部工具按钮 (Pin/Monitor/Fav) */
            QPushButton {{ border: 1px solid {c['border']}; border-radius: 6px; padding: 5px; background-color: {c['card']}; color: {c['text']}; }}
            QPushButton:hover {{ background-color: {c['hover']}; border-color: {c['primary']}; color: {c['primary']}; }}
            QPushButton:checked {{ background-color: {c['primary']}; color: #ffffff; border: 1px solid {c['primary']}; }}
            QPushButton:pressed {{ background-color: {c['border']}; }}

            /* 收藏按钮特例：已收藏时边框变金，但背景不变色(由SVG控制) */
            QPushButton[is_fav="true"] {{ border-color: #fbc02d; }}

            /* 分组框 */
            QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 10px; padding-top: 10px; color: {c['text']}; }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; color: {c['primary']}; font-weight: bold; }}

            QWidget#QuizPage QPushButton {{
                font-size: 16px;
                font-weight: 500;
                text-align: left;
                padding: 15px 20px;
                border: 1px solid {c['border']};
                border-radius: 10px;
                background-color: {c['card']};
                color: {c['text']};
                margin: 5px;
            }}
            
            /* 单词尖刺卡片 */
            QWidget#QuizPage QPushButton:hover {{
                background-color: {c['hover']};
                border-color: {c['primary']};
                color: {c['primary']};
            }}

            QWidget#QuizPage QPushButton#BtnShowAnswer {{
                background-color: transparent;
                border: none;
                color: {c['meta']};
                text-align: center;
            }}
            
            /* 滚动条 */
            QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0px 4px 0px 0px; }}
            QScrollBar::handle:vertical {{ background: {c['meta']}; border-radius: 4px; min-height: 30px; opacity: 0.5; }}
            QScrollBar::handle:vertical:hover {{ background: {c['text']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
            
            
        """
        self.setStyleSheet(qss)

        # 刷新侧边栏背景
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setStyleSheet(
            f"#Sidebar {{ background-color: {c['sidebar']}; border-right: 1px solid {c['border']}; }}")

        if self.page_search:
            self.page_search.left_widget.setStyleSheet(f"background-color: {c['sidebar']};")
            self.page_search.refresh_webview()

        # [修改] 关键步骤：调用刷新图标的方法，确保图标颜色跟随主题
        self.sidebar.refresh_icons()
        if self.page_search:
            self.page_search.refresh_icons()

# 全局异常钩子
def exception_hook(exctype, value, traceback):
    import traceback as tb
    err_msg = "".join(tb.format_exception(exctype, value, traceback))
    print(err_msg)
    # 尝试弹窗显示错误（如果 QApplication 还在运行）
    try:
        QMessageBox.critical(None, "Critical Error", f"程序发生严重错误:\n{value}")
    except:
        pass
    sys.exit(1)


if __name__ == "__main__":
    # 1. 设置 App ID (Windows 任务栏图标修复)
    if sys.platform == 'win32':
        myappid = 'geek.dict.flutter.pro.v6'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # === [关键修正] Scheme 注册必须在 QApplication 创建之前 ===
    # 这一步如果不做，或者放在后面，WebEngine 进程初始化时会崩导致退出代码 -1
    try:
        s = QWebEngineUrlScheme(b"mdict")
        s.setSyntax(QWebEngineUrlScheme.Syntax.Path)
        # 允许子资源加载（CSS/JS/字体/媒体）。不同 PySide6 版本的 Flag 名称可能不全，做一层兼容。
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
        print(f"Scheme registration warning: {e}")

    # 2. 创建 QApplication
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 3. 初始化主窗口 (DatabaseManager.init_db() 在这里面被调用)
    # 注意：确保 ModernMainWindow 的 __init__ 里删除了刚才剪切走的 Scheme 代码！
    win = ModernMainWindow()
    win.show()

    # 4. 进入事件循环
    sys.exit(app.exec())