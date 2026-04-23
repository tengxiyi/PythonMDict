# file: src/ui/handlers/mdict_handler.py
# -*- coding: utf-8 -*-
"""
MDict 自定义URL协议处理器 (mdict://)
负责处理词典资源加载（CSS、图片、音频、字体等）
支持：
- CSS智能路由（物理文件优先，数据库回退）
- 字体特殊处理（金山音标字体）
- MDD数据库模糊查找
- 物理文件回退（同目录扫描）
- Googleapis.css 安静降级
- iframe HTML缓存机制
"""
import os
import re
import sqlite3
import hashlib
import tempfile
import threading
import urllib.parse

from PySide6.QtCore import (
    QBuffer, QByteArray, QIODevice, QUrl
)
from PySide6.QtWebEngineCore import (
    QWebEngineUrlRequestJob, QWebEngineUrlSchemeHandler
)
from PySide6.QtGui import QDesktopServices

from ...core.config import DB_FILE
from ...core.logger import logger
from ..widgets.mdd_cache import MDDCacheManager


# ========== 全局缓存 ==========
IFRAME_HTML_CACHE: dict[str, bytes] = {}
IFRAME_HTML_LOCK = threading.Lock()

DICT_DIR_CACHE: dict[int, str] = {}
DICT_DIR_CACHE_LOCK = threading.Lock()

PHYSICAL_RES_INDEX: dict[str, dict] = {}
PHYSICAL_RES_INDEX_LOCK = threading.Lock()


def _get_dict_dir(dict_id: int) -> str | None:
    """从dict_info获取词典所在目录（带缓存）"""
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
    except Exception as e:
        logger.debug(f"获取词典目录失败(did={dict_id}): {e}")
        return None


def _build_physical_res_index(dict_dir: str) -> dict:
    """扫描词典目录建立 basename -> fullpath 的映射"""
    from ...core.config import RESOURCE_ALLOW_EXTS
    
    idx = {}
    try:
        for root, _dirs, files in os.walk(dict_dir):
            for fn in files:
                low = fn.lower()
                if not low.endswith(RESOURCE_ALLOW_EXTS):
                    continue
                key = fn.upper()
                if key not in idx:  # 避免同名覆盖
                    idx[key] = os.path.join(root, fn)
    except Exception as e:
        logger.debug(f"构建物理资源索引失败({dict_dir}): {e}")
    return idx


def _get_physical_resource_path(dict_id: int, rel_path: str) -> str | None:
    """优先精确路径，其次按文件名在词典目录内回退查找"""
    dict_dir = _get_dict_dir(dict_id)
    if not dict_dir:
        return None

    try:
        # 精确路径匹配
        file_path = os.path.normpath(os.path.join(dict_dir, rel_path))
        if os.path.commonpath([dict_dir, file_path]).startswith(os.path.normpath(dict_dir)):
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return file_path
    except Exception:
        pass

    # 按文件名索引回退
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
            if (os.path.commonpath([dict_dir, hit]).startswith(os.path.normpath(dict_dir))
                    and os.path.exists(hit) and os.path.isfile(hit)):
                return hit
    except Exception:
        pass

    return None


def _expand_resource_candidates(rel_path: str) -> list[str]:
    """
    扩展资源路径候选列表
    处理编码差异、simplified前缀、_simplified后缀等情况
    """
    if not rel_path:
        return []

    p0 = rel_path.replace('\\', '/').lstrip('/')
    
    # 基础候选
    base_candidates = [p0]
    
    # 处理 # 编码变体 (%23 / %2523)
    try:
        low = p0.lower()
        if '#' in p0:
            base_candidates.append(p0.replace('#', '%23'))
            base_candidates.append(p0.replace('#', '%2523'))
        if '%2523' in low:
            base_candidates.append(re.sub(r'(?i)%2523', '%23', p0))
            base_candidates.append(re.sub(r'(?i)%2523', '#', p0))
        if '%23' in low:
            base_candidates.append(re.sub(r'(?i)%23', '#', p0))
    except Exception:
        pass

    candidates = []
    for p in base_candidates:
        candidates.append(p)
        
        # simplified/ 前缀去除
        parts = p.split('/')
        if parts and parts[0].lower() == 'simplified' and len(parts) > 1:
            candidates.append('/'.join(parts[1:]))

        # 中间含 simplified 去除
        if any(seg.lower() == 'simplified' for seg in parts):
            try:
                idx = [seg.lower() for seg in parts].index('simplified')
                if -1 < idx + 1 < len(parts):
                    candidates.append('/'.join(parts[:idx] + parts[idx + 1:]))
            except Exception:
                pass

        # _simplified 后缀去除
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


def _fetch_resource_bytes(dict_id: int, rel_path: str) -> bytes | None:
    """优先读物理文件，否则读MDD缓存"""
    candidates = _expand_resource_candidates(rel_path)
    if not candidates:
        return None

    # 尝试物理文件
    try:
        for cand in candidates:
            fp = _get_physical_resource_path(dict_id, cand)
            if fp:
                with open(fp, "rb") as f:
                    return f.read()
    except Exception as e:
        logger.debug(f"读取物理资源失败(did={dict_id}, path={rel_path}): {e}")

    # 回退MDD数据库
    try:
        for cand in candidates:
            data = MDDCacheManager.get_resource_fuzzy(dict_id, cand)
            if data:
                return data
    except Exception as e:
        logger.debug(f"MDD查询失败(did={dict_id}, path={rel_path}): {e}")

    return None


def play_audio_from_mdict(play_url: str) -> bool:
    """
    从mdict:// 协议播放音频文件
    
    Args:
        play_url: mdict:// 格式的音频URL
        
    Returns:
        是否成功播放
    """
    if not play_url.startswith("mdict://"):
        return False

    path_part = play_url.split("mdict://", 1)[1]
    if "/" not in path_part:
        return False

    dict_id_str, raw_res_path = path_part.split("/", 1)

    # root / 0.0.0.x 视为全库查找
    if dict_id_str == "root" or dict_id_str.startswith("0.0.0."):
        try:
            with sqlite3.connect(DB_FILE) as conn:
                target_ids = [
                    r[0] for r in
                    conn.execute("SELECT id FROM dict_info ORDER BY priority ASC").fetchall()
                ]
        except Exception as e:
            logger.error(f"获取词典ID列表失败: {e}")
            target_ids = []
    else:
        dict_id = _parse_dict_id_str(dict_id_str)
        if dict_id is None:
            return False
        target_ids = [dict_id]

    # 解码路径（支持多次编码）
    raw_res_path = raw_res_path.split('?', 1)[0].split('#', 1)[0]
    
    decoded_path = raw_res_path
    try:
        for _ in range(3):
            new_p = urllib.parse.unquote(decoded_path)
            if new_p == decoded_path:
                break
            decoded_path = new_p
    except Exception:
        decoded_path = urllib.parse.unquote(raw_res_path)

    decoded_path = decoded_path.replace('\\', '/')
    decoded_path = os.path.normpath(decoded_path).replace('\\', '/')
    decoded_path = decoded_path.lstrip('/')

    # 同时保留原始编码态
    raw_path_norm = raw_res_path.replace('\\', '/')
    raw_path_norm = os.path.normpath(raw_path_norm).replace('\\', '/')
    raw_path_norm = raw_path_norm.lstrip('/')

    # 查找资源数据
    data = None
    hit_dict_id = None

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
        logger.debug(
            f"[audio] not found: dict_id={dict_id_str} "
            f"path={decoded_path} raw={raw_path_norm} targets={target_ids}"
        )
        return False

    # 写入临时文件并用系统播放器打开
    ext = os.path.splitext(decoded_path)[1].lower() or os.path.splitext(raw_path_norm)[1].lower() or ".spx"
    h = hashlib.md5(play_url.encode('utf-8')).hexdigest()[:10]
    tmp_path = os.path.join(tempfile.gettempdir(), f"geekdict_{hit_dict_id or 'x'}_{h}{ext}")
    
    if not os.path.exists(tmp_path):
        with open(tmp_path, "wb") as f:
            f.write(data)

    logger.info(f"[audio] open: {tmp_path} bytes={len(data)}")
    QDesktopServices.openUrl(QUrl.fromLocalFile(tmp_path))
    return True


def _parse_dict_id_str(dict_id_str: str) -> int | None:
    """解析字典ID字符串（支持浮点格式如 "0.0.0.2"）"""
    try:
        if "." in dict_id_str:
            dict_id_str = dict_id_str.split('.')[-1]
        return int(float(dict_id_str))
    except Exception:
        return None


def _guess_mime(path_lower: str) -> bytes:
    """根据文件扩展名猜测MIME类型"""
    mime_map = {
        ('.jpg', '.jpeg'): b"image/jpeg",
        '.png': b"image/png",
        '.gif': b"image/gif",
        '.bmp': b"image/bmp",
        '.ico': b"image/x-icon",
        '.webp': b"image/webp",
        '.svg': b"image/svg+xml",
        '.css': b"text/css",
        '.js': b"text/javascript",
        '.ttf': b"font/ttf",
        '.otf': b"font/otf",
        '.woff': b"font/woff",
        '.woff2': b"font/woff2",
        '.eot': b"application/vnd.ms-fontobject",
        '.mp3': b"audio/mpeg",
        '.wav': b"audio/wav",
        '.ogg': b"audio/ogg",
        '.spx': b"audio/ogg",
    }
    
    for exts, mime in mime_map.items():
        if isinstance(exts, tuple):
            if path_lower.lower().endswith(exts):
                return mime
        elif path_lower.lower().endswith(exts):
            return mime
    
    return b"application/octet-stream"


class MdictSchemeHandler(QWebEngineUrlSchemeHandler):
    """
    MDict自定义URL协议处理器 (mdict://)
    
    处理所有以 mdict:// 开头的资源请求，包括：
    - CSS样式表路由
    - 金山音标字体提供
    - 图片/音频/MDD资源加载
    - iframe HTML缓存
    - 物理文件回退
    """
    
    def requestStarted(self, job: QWebEngineUrlRequestJob):
        # 辅助函数：返回数据
        def reply_data(mime: bytes, data: bytes | str):
            buf = QBuffer(parent=job)
            buf.setData(QByteArray(data))
            buf.open(QIODevice.ReadOnly)
            job.reply(mime, buf)

        # 辅助函数：返回空数据
        def reply_empty(mime: bytes):
            buf = QBuffer(parent=job)
            buf.open(QIODevice.ReadOnly)
            job.reply(mime, buf)

        try:
            url = job.requestUrl().toString()

            # === 0. iframe HTML 缓存 ===
            if url.startswith("mdict://iframe/"):
                token = url.split("mdict://iframe/", 1)[1].split("?", 1)[0].split("#", 1)[0]
                with IFRAME_HTML_LOCK:
                    cached_data = IFRAME_HTML_CACHE.get(token)
                if cached_data:
                    reply_data(b"text/html", cached_data)
                else:
                    job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return

            # === 1. CSS 智能路由 ===
            if "mdict://css/" in url:
                try:
                    payload = url.split("mdict://css/", 1)[1]

                    if payload.isdigit():
                        # 纯数字ID: 查找同名CSS物理文件
                        dict_id = int(payload)
                        css_path = None
                        with sqlite3.connect(DB_FILE, timeout=5) as conn:
                            row = conn.execute(
                                "SELECT path FROM dict_info WHERE id=?",
                                (dict_id,)
                            ).fetchone()
                            if row and row[0]:
                                css_path = row[0][:-4] + ".css"

                        if css_path and os.path.exists(css_path):
                            with open(css_path, "rb") as f:
                                reply_data(b"text/css", f.read())
                            return
                    else:
                        # 带子路径: mdict://{id}/__style.css
                        parts = payload.split("/", 1)
                        if len(parts) == 2 and parts[0].isdigit():
                            dict_id = int(parts[0])
                            rest = parts[1]
                            if rest == "__style.css":
                                css_path = None
                                with sqlite3.connect(DB_FILE, timeout=5) as conn:
                                    row = conn.execute(
                                        "SELECT path FROM dict_info WHERE id=?",
                                        (dict_id,)
                                    ).fetchone()
                                    if row and row[0]:
                                        css_path = row[0][:-4] + ".css"
                                
                                if css_path and os.path.exists(css_path):
                                    with open(css_path, "rb") as f:
                                        reply_data(b"text/css", f.read())
                                    return
                                
                                reply_empty(b"text/css")
                                return

                            elif rest == "__script.js":
                                # 加载词典自带JS文件（如OALDPE设置按钮交互脚本）
                                js_path = None
                                with sqlite3.connect(DB_FILE, timeout=5) as conn:
                                    row = conn.execute(
                                        "SELECT path FROM dict_info WHERE id=?",
                                        (dict_id,)
                                    ).fetchone()
                                    if row and row[0]:
                                        js_path = row[0][:-4] + ".js"
                                
                                if js_path and os.path.exists(js_path):
                                    with open(js_path, "rb") as f:
                                        reply_data(b"application/javascript", f.read())
                                    return
                                
                                # JS不存在则返回空，不报错（很多词典没有独立JS文件）
                                reply_empty(b"application/javascript")
                                return

                            elif rest == "__jquery.js":
                                # 加载词典自带的jQuery（如OALDPE的 oaldpe-jquery.js）
                                jq_path = None
                                with sqlite3.connect(DB_FILE, timeout=5) as conn:
                                    row = conn.execute(
                                        "SELECT path FROM dict_info WHERE id=?",
                                        (dict_id,)
                                    ).fetchone()
                                    if row and row[0]:
                                        base = os.path.splitext(row[0])[0]
                                        # 常见命名: basename-jquery.js 或 jquery.js
                                        for candidate in [base + "-jquery.js", os.path.join(os.path.dirname(base), "jquery.js")]:
                                            if os.path.exists(candidate):
                                                jq_path = candidate
                                                break
                                
                                if jq_path and os.path.exists(jq_path):
                                    with open(jq_path, "rb") as f:
                                        reply_data(b"application/javascript", f.read())
                                    return
                                
                                reply_empty(b"application/javascript")
                                return
                            else:
                                url = f"mdict://{dict_id}/{rest}"
                        else:
                            # CSS内部资源被错误拼到css/下，重定向到root
                            url = url.replace("mdict://css/", "mdict://root/", 1)
                    
                except Exception as e:
                    logger.warning(f"CSS Handler Error: {e}")

            # === 2. 字体特殊处理 ===
            try:
                low_url = url.lower()
            except Exception:
                low_url = url

            if ("kingsoft_phonetic" in low_url 
                    or low_url.endswith("kingsoft_phonetic.ttf") 
                    or low_url.endswith("kingsoft phonetic plain.ttf")):
                font_path = os.path.join("fonts", "Kingsoft Phonetic Plain.ttf")
                if os.path.exists(font_path):
                    with open(font_path, "rb") as f:
                        reply_data(b"font/ttf", f.read())
                    return
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return

            # === 3. 标准 MDD 资源查找 ===
            if not url.startswith("mdict://"):
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return

            try:
                # 解析路径
                path_part = url.split("mdict://", 1)[1]
                
                if path_part.startswith("css/"):
                    path_part = path_part.replace("css/", "root/", 1)

                if "/" not in path_part:
                    path_part = "root/" + path_part

                dict_id_str, raw_res_path = path_part.split("/", 1)

                # 移除query/fragment
                raw_res_path = raw_res_path.split('?', 1)[0].split('#', 1)[0]

                # 多次解码处理二次编码（%2523 -> %23 -> #）
                decoded_path = raw_res_path
                try:
                    for _ in range(3):
                        new_p = urllib.parse.unquote(decoded_path)
                        if new_p == decoded_path:
                            break
                        decoded_path = new_p
                except Exception:
                    decoded_path = urllib.parse.unquote(raw_res_path)

                decoded_path = decoded_path.replace('\\', '/')
                decoded_path = os.path.normpath(decoded_path).replace('\\', '/')
                decoded_path = decoded_path.lstrip('/')

                # 修复异常路径（嵌套mdict://）
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
                except Exception:
                    pass

                # 安静降级：Google广告CSS返回空内容避免刷屏
                try:
                    if decoded_path.lower().endswith("googleapis.css"):
                        reply_empty(b"text/css")
                        return
                except Exception:
                    pass
                    
            except Exception as e:
                logger.warning(f"URL解析失败 [{url}]: {e}")
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return

            # === 健壮的ID解析 ===
            target_ids = []
            if dict_id_str == "root" or dict_id_str.startswith("0.0.0."):
                try:
                    with sqlite3.connect(DB_FILE) as conn:
                        target_ids = [
                            r[0] for r in
                            conn.execute(
                                "SELECT id FROM dict_info ORDER BY priority ASC"
                            ).fetchall()
                        ]
                except Exception as e:
                    logger.error(f"获取全部词典ID失败: {e}")
            else:
                try:
                    if "." in dict_id_str:
                        clean_id = dict_id_str.split('.')[-1]
                    else:
                        clean_id = dict_id_str
                    
                    if clean_id.isdigit():
                        target_ids = [int(clean_id)]
                    else:
                        target_ids = [int(float(clean_id))]
                except Exception as e:
                    logger.warning(f"解析dict_id失败[{dict_id_str}]: {e}, 使用全库搜索")
                    try:
                        with sqlite3.connect(DB_FILE) as conn:
                            target_ids = [
                                r[0] for r in
                                conn.execute(
                                    "SELECT id FROM dict_info ORDER BY priority ASC"
                                ).fetchall()
                            ]
                    except Exception:
                        pass

            # === 4. 物理文件回退查找 ===
            rel_path = decoded_path.lstrip('/\\').replace('\\', '/')
            candidates = _expand_resource_candidates(rel_path)

            # 补充原始编码候选
            try:
                raw_rel = raw_res_path.lstrip('/\\').replace('\\', '/')
                for c in _expand_resource_candidates(raw_rel):
                    if c not in candidates:
                        candidates.append(c)
            except Exception:
                pass

            # 遍历候选路径查找物理文件
            for cand in candidates:
                for did in target_ids:
                    try:
                        fp = _get_physical_resource_path(did, cand)
                        if fp:
                            with open(fp, "rb") as f:
                                reply_data(_guess_mime(fp.lower()), f.read())
                            return
                    except Exception as e:
                        logger.debug(f"物理资源查找失败(did={did}, path={cand}): {e}")

            # === 5. MDD 数据库查找 ===
            for cand in candidates:
                for did in target_ids:
                    data = MDDCacheManager.get_resource_fuzzy(did, cand)
                    if data:
                        reply_data(_guess_mime(cand.lower()), data)
                        return

            # 资源未找到日志
            try:
                low = decoded_path.lower()
                res_exts = (
                    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg',
                    '.ico', '.mp3', '.wav', '.ogg', '.spx', '.css', '.js',
                    '.ttf', '.otf', '.woff', '.woff2', '.eot'
                )
                if low.endswith(res_exts):
                    logger.debug(
                        f"[mdict] not found: url={url} "
                        f"dict_id={dict_id_str} path={decoded_path} "
                        f"target_ids={target_ids}"
                    )
            except Exception:
                pass
            
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)

        except Exception as e:
            logger.error(f"MdictSchemeHandler Critical Error: {e}", exc_info=True)
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
