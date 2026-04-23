# file: backend.py
import html  # <--- [新增] 用于解码 &nbsp; 等
import random
import sqlite3
import zlib
import re
import os
import time
import urllib.parse
import urllib.request
import gzip
# [优化] 移除顶层重型库导入 (ssl, xml, opencc, readmdict)
# 这些库将被移到函数内部按需导入

# 线程池保持全局，因为它初始化开销很小且复用价值高
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QThread, Signal

# --- 全局配置 ---
DB_FILE = "dict_cache.db"
MDD_DB_FILE = "mdd_cache.db"
EBBINGHAUS_INTERVALS = [300, 1800, 43200, 86400, 172800, 345600, 604800, 1296000]
CSS_CACHE = {}

# 全局线程池
_max_workers = (os.cpu_count() or 4) + 2
GLOBAL_EXECUTOR = ThreadPoolExecutor(max_workers=_max_workers)

RE_HTML_TAG = re.compile(r'<[^>]+>')
RE_WHITESPACE = re.compile(r'\s+')
RE_CJK = re.compile(r'([\u4e00-\u9fa5])')
RE_SRC = re.compile(r'(src=)(["\'])(.*?)(["\'])', re.IGNORECASE)
RE_HREF = re.compile(r'(href=)(["\'])(.*?)(["\'])', re.IGNORECASE)

# --- [优化] OpenCC 单例懒加载 ---
_opencc_s2t = None
_opencc_t2s = None
_has_opencc = None


def get_opencc(direction='s2t'):
    """按需加载 OpenCC，避免启动时耗时"""
    global _opencc_s2t, _opencc_t2s, _has_opencc

    if _has_opencc is False:
        return None

    if _has_opencc is None:
        try:
            import opencc
            _opencc_s2t = opencc.OpenCC('s2t')
            _opencc_t2s = opencc.OpenCC('t2s')
            _has_opencc = True
        except ImportError:
            _has_opencc = False
            return None

    return _opencc_s2t if direction == 's2t' else _opencc_t2s


def pre_process_entry_content(content_bytes, dict_id):
    """
    索引时预处理
    """
    try:
        html = content_bytes.decode('utf-8').strip()
    except UnicodeDecodeError:
        try:
            html = content_bytes.decode('gbk', 'ignore').strip()
        except:
            html = content_bytes.decode('utf-8', 'ignore').strip()

    html = html.replace('\x00', '').replace('\x1e', '').replace('\x1f', '')

    def repl(m):
        prefix, quote, path, suffix = m.groups()
        if path.startswith(('http', 'https', 'data:', 'javascript:', '#', 'entry:', 'mdict:', 'file:')):
            return m.group(0)

        # oaldpe: sound://xxx.mp3
        try:
            low = path.lower()
            if low.startswith("sound://"):
                path = path.split("//", 1)[1]
            elif low.startswith("sound:"):
                path = path.split(":", 1)[1]
        except:
            pass

        clean_path = path.lstrip('/\\').replace('\\', '/')
        clean_path = urllib.parse.quote(clean_path)
        return f'{prefix}{quote}mdict://{dict_id}/{clean_path}{quote}'

    html = RE_SRC.sub(repl, html)
    html = RE_HREF.sub(repl, html)


    return zlib.compress(html.encode('utf-8'))


def space_cjk(text):
    if not text: return ""
    return RE_CJK.sub(r' \1 ', text)


# --- 通用网络请求函数 ---
def fetch_url_content(url, timeout=5):
    """通用下载函数"""
    # [优化] 按需导入 ssl 和 gzip
    import ssl
    import gzip

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        try:
            req = urllib.request.Request(url, headers=headers)
        except ValueError:
            return None

        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            data = response.read()
            if response.info().get('Content-Encoding') == 'gzip':
                try:
                    data = gzip.decompress(data)
                except:
                    pass
            return data

    except Exception as e:
        return None


# --- RSS 源测试线程 ---
class RSSTestWorker(QThread):
    test_result = Signal(bool, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        # [优化] 按需导入 xml
        import xml.etree.ElementTree as ET

        if not self.url.startswith("http"):
            self.test_result.emit(False, "URL must start with http/https")
            return

        data = fetch_url_content(self.url, timeout=8)
        if not data:
            self.test_result.emit(False, "Connection Failed or Timeout")
            return

        try:
            try:
                xml_str = data.decode('utf-8', 'ignore').strip()
            except:
                xml_str = data.decode('gbk', 'ignore').strip()

            if not xml_str.startswith('<'):
                self.test_result.emit(False, "Invalid format (Not XML)")
                return

            root = ET.fromstring(xml_str)
            items = root.findall('./channel/item')
            if not items:
                items = root.findall('item')

            count = len(items)
            if count > 0:
                title = "Unknown"
                t_node = root.find('./channel/title')
                if t_node is not None and t_node.text:
                    title = t_node.text
                self.test_result.emit(True, f"Success! Found {count} items. \nFeed: {title}")
            else:
                self.test_result.emit(False, "XML parsed but no news items found.")
        except Exception as e:
            self.test_result.emit(False, f"Parse Error: {str(e)}")


# --- 新闻内容提取线程 ---
class NewsContentWorker(QThread):
    content_ready = Signal(str, str, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        if not self.url:
            self.content_ready.emit("Error", "<p>Invalid URL</p>", self.url)
            return

        try:
            data = fetch_url_content(self.url, timeout=15)
            if not data:
                raise Exception("Download failed")

            try:
                html = data.decode('utf-8', 'ignore')
            except:
                html = data.decode('gbk', 'ignore')

            # 简单的清洗逻辑 (无需额外重型库)
            html = re.sub(r'<script[^>]*?>.*?</script>', '', html, flags=re.IGNORECASE | re.DOTALL)
            html = re.sub(r'<style[^>]*?>.*?</style>', '', html, flags=re.IGNORECASE | re.DOTALL)
            html = re.sub(r'<(svg|nav|footer|header|aside|noscript|iframe)[^>]*>.*?</\1>', '', html,
                          flags=re.IGNORECASE | re.DOTALL)

            title = "No Title"
            t_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            if t_match:
                title = t_match.group(1).strip().split(" - ")[0].split(" | ")[0]

            clean_paragraphs = []
            p_matches = re.findall(r'<p[^>]*>(.*?)</p>', html, flags=re.DOTALL | re.IGNORECASE)
            for p in p_matches:
                text = re.sub(r'<[^>]+>', '', p).strip()
                if len(text) > 30:
                    clean_paragraphs.append(f"<p>{text}</p>")

            if not clean_paragraphs:
                divs = re.findall(r'<div[^>]*>(.*?)</div>', html, flags=re.DOTALL | re.IGNORECASE)
                for d in divs:
                    text = re.sub(r'<[^>]+>', '', d).strip()
                    if len(text) > 150:
                        clean_paragraphs.append(f"<p>{text[:1000]}...</p>")

            if not clean_paragraphs:
                body_html = f"<div style='text-align:center;margin-top:50px;'><h3>Unable to extract text.</h3><p><a href='{self.url}'>Open in browser</a></p></div>"
            else:
                body_html = "\n".join(clean_paragraphs[:100])

            self.content_ready.emit(title, body_html, self.url)

        except Exception as e:
            self.content_ready.emit("Load Failed", f"<p>Error: {str(e)}</p>", self.url)


# --- NewsWorker: 动态从数据库读取源 ---
class NewsWorker(QThread):
    news_ready = Signal(list, str)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        # [优化] 按需导入 xml
        import xml.etree.ElementTree as ET

        if not self.query:
            self.news_ready.emit([], "")
            return

        results = []
        seen_links = set()
        query_lower = self.query.lower().strip()

        sources = []
        with sqlite3.connect(DB_FILE) as conn:
            try:
                cursor = conn.execute("SELECT name, url FROM rss_sources WHERE enabled=1")
                sources = [{"name": r[0], "url": r[1]} for r in cursor.fetchall()]
            except sqlite3.OperationalError:
                sources = [{"name": "China Daily", "url": "http://www.chinadaily.com.cn/rss/world_rss.xml"}]

        if not sources:
            self.news_ready.emit([], self.query)
            return

        for src in sources:
            data = fetch_url_content(src['url'])
            if not data: continue

            try:
                try:
                    xml_str = data.decode('utf-8', 'ignore').strip()
                except:
                    xml_str = data.decode('gbk', 'ignore').strip()

                if not xml_str.startswith('<'): continue

                root = ET.fromstring(xml_str)
                items = root.findall('./channel/item')
                if not items: items = root.findall('item')

                for item in items:
                    link_node = item.find('link')
                    if link_node is None or not link_node.text: continue
                    link = link_node.text.strip()
                    if not link or link in seen_links: continue

                    title_node = item.find('title')
                    desc_node = item.find('description')
                    date_node = item.find('pubDate')

                    title = title_node.text if (title_node is not None and title_node.text) else "No Title"
                    raw_body = desc_node.text if (desc_node is not None and desc_node.text) else ""
                    pub_date = date_node.text if (date_node is not None and date_node.text) else ""

                    body_text = re.sub(r'<[^>]+>', '', raw_body).strip()
                    if len(pub_date) > 16: pub_date = pub_date[:16]

                    if query_lower in title.lower() or query_lower in body_text.lower():
                        seen_links.add(link)
                        results.append({
                            "title": title,
                            "body": body_text[:200] + "..." if len(body_text) > 200 else body_text,
                            "source": src['name'],
                            "date": pub_date,
                            "url": link
                        })
            except Exception as e:
                # print(f"Parse Error {src['name']}: {e}")
                continue

        self.news_ready.emit(results, self.query)


# --- 词条渲染任务 ---
# [backend.py] 找到这个函数并完全替换
def process_entry_task(args):
    r_word, r_blob, d_id, r_score, d_info = args
    try:
        content = zlib.decompress(r_blob).decode('utf-8', 'ignore') if isinstance(r_blob, bytes) else r_blob
    except Exception as e:
        content = f"Decode Error: {e}"

    # === [核心修复] 运行时链接重写 ===
    # 既然 JS 拦截会被词典脚本阻断，我们在发给浏览器前，
    # 直接把 "跳转链接" 改写为 entry:// 协议。
    # 这样浏览器就会直接发起标准导航，谁也拦不住。

    def fix_link_handler(match):
        # match.group(0) 是完整的 href="mdict://..."
        quote = match.group(1)  # 引号 " 或 '
        url = match.group(2)  # mdict://1/Apple

        # 1. 资源文件白名单 (保持 mdict:// 不变)
        lower = url.lower()
        # 常见图片、样式、脚本、音频后缀
        res_exts = ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.bmp',
                    '.ico', '.svg', '.ttf', '.woff', '.mp3', '.wav', '.ogg', '.spx')

        # 如果是资源文件，或者是 css/theme 系统目录，直接原样返回
        if lower.split('?')[0].endswith(res_exts) or "mdict://css/" in lower or "mdict://theme/" in lower:
            return match.group(0)

        # 2. 剩下的通常就是单词跳转了！
        try:
            # 提取路径: mdict://1/Word -> 1/Word
            if "mdict://" in url:
                path = url.split("mdict://", 1)[1]
                if "/" in path:
                    # 提取 Word
                    word_part = path.split("/", 1)[1]
                    # 构造无敌的 entry 协议链接
                    # entry://query/Word
                    return f'href={quote}entry://query/{word_part}{quote}'
        except:
            pass

        return match.group(0)

    # 使用正则查找所有 mdict 链接并进行清洗
    # 匹配模式: href="mdict://..." 或 href='mdict://...'
    try:
        content = re.sub(r'href=(["\'])(mdict://.*?)\1', fix_link_handler, content, flags=re.IGNORECASE)
    except Exception as e:
        print(f"Link Fix Error: {e}")
    # ==========================================

    return {
        "word": r_word,
        "content": content,
        "dict_name": d_info['name'],
        "rank": r_score,
        "dict_id": d_id,
        "dict_path": d_info['path']
    }


# --- 数据库管理 ---
class DatabaseManager:
    @staticmethod
    def init_db():
        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dict_info (
                    id INTEGER PRIMARY KEY, path TEXT UNIQUE, name TEXT, mdd_path TEXT, priority INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS standard_entries (
                    word TEXT, content BLOB, dict_id INTEGER, length INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_word ON standard_entries(word COLLATE NOCASE)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dict ON standard_entries(dict_id)")
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS fts_entries USING fts5(word, content_text, dict_id UNINDEXED)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS vocabulary (
                    word TEXT PRIMARY KEY, 
                    added_time REAL, 
                    review_stage INTEGER DEFAULT 0, 
                    next_review_time REAL DEFAULT 0,
                    context TEXT, 
                    source TEXT
                    xp INTEGER DEFAULT 0  -- [NEW] Add XP column
                )
            """)

            try:
                conn.execute("ALTER TABLE vocabulary ADD COLUMN xp INTEGER DEFAULT 0")
            except:
                pass
            try:
                conn.execute("ALTER TABLE vocabulary ADD COLUMN source TEXT")
            except:
                pass

            conn.execute("""
                        CREATE TABLE IF NOT EXISTS search_history (
                            word TEXT PRIMARY KEY, 
                            last_access_time REAL,
                            search_count INTEGER DEFAULT 1
                        )
                    """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS rss_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    url TEXT UNIQUE,
                    enabled INTEGER DEFAULT 1
                )
            """)

            cur = conn.execute("SELECT count(*) FROM rss_sources")
            if cur.fetchone()[0] == 0:
                defaults = [
                    ("China Daily (World)", "http://www.chinadaily.com.cn/rss/world_rss.xml"),
                    ("China Daily (Biz)", "http://www.chinadaily.com.cn/rss/bizchina_rss.xml"),
                ]
                conn.executemany("INSERT INTO rss_sources (name, url) VALUES (?, ?)", defaults)
                conn.commit()

        with sqlite3.connect(MDD_DB_FILE, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS resources (dict_id INTEGER, norm_key TEXT, data BLOB, PRIMARY KEY (dict_id, norm_key))")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cached_dicts (dict_id INTEGER PRIMARY KEY, mdd_path TEXT, cached_time REAL)")


# --- IndexerWorker ---
class IndexerWorker(QThread):
    progress_sig = Signal(str)
    finished_sig = Signal()

    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def run(self):
        # [优化] 按需导入 readmdict
        try:
            from readmdict import MDX
        except ImportError:
            self.progress_sig.emit("错误: 缺少 readmdict 库！")
            return

        with sqlite3.connect(DB_FILE, timeout=30) as conn:
            res = conn.execute("SELECT MAX(priority) FROM dict_info").fetchone()
            pri = (res[0] if res[0] else 0) + 1

        total_files = len(self.paths)

        for i, p in enumerate(self.paths):
            try:
                name = os.path.basename(p)[:-4]
                self.progress_sig.emit(f"[{i + 1}/{total_files}] 处理中: {name}")

                # 兼容：同目录可能有多个 .mdd（例如图片一个、音频一个），需要一起导入
                mdd_paths = []
                try:
                    mdx_dir = os.path.dirname(p)
                    mdx_base = os.path.basename(p)[:-4]
                    primary_mdd = p[:-4] + ".mdd"
                    if os.path.exists(primary_mdd):
                        mdd_paths.append(primary_mdd)

                    if mdx_dir and os.path.isdir(mdx_dir):
                        for fn in os.listdir(mdx_dir):
                            low = fn.lower()
                            if not low.endswith('.mdd'):
                                continue
                            # 仅收集同前缀的 mdd：例如 oaldpe*.mdd
                            if not low.startswith(mdx_base.lower()):
                                continue
                            full = os.path.join(mdx_dir, fn)
                            if os.path.normcase(full) == os.path.normcase(primary_mdd):
                                continue
                            if os.path.exists(full) and os.path.isfile(full):
                                mdd_paths.append(full)
                except:
                    pass

                if mdd_paths:
                    # 保存在 dict_info 里便于后续排查（分号分隔）
                    mdd_path = ";".join(mdd_paths)
                else:
                    mdd_path = None

                with sqlite3.connect(DB_FILE, timeout=30) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM dict_info WHERE path=?", (p,))
                    if cur.fetchone():
                        self.progress_sig.emit(f"♻️ {name} 已存在")
                        continue

                    cur.execute("INSERT INTO dict_info (path, name, mdd_path, priority) VALUES (?, ?, ?, ?)",
                                (p, name, mdd_path, pri))
                    did = cur.lastrowid
                    conn.commit()

                # 为了代码复用，这里 process_mdx 内部也需要确保 MDX 可用
                # 但由于我们在 run 开头已经导入了，所以这里直接传 class 引用或者让实例方法内部导入
                # 简单起见，我们把 import 放在 process_mdx 内部
                self.process_mdx(p, did, name)
                if mdd_path:
                    self.process_mdd(mdd_path, did, name)


                pri += 1
                self.progress_sig.emit(f"✅ {name} 完成！")

            except Exception as e:
                self.progress_sig.emit(f"❌ 错误: {str(e)}")

        self.finished_sig.emit()

    def process_mdx(self, path, did, name):
        try:
            from readmdict import MDX  # 内联导入
            mdx = MDX(path)
        except Exception as e:
            self.progress_sig.emit(f"❌ 解析 MDX 失败 ({name}): {str(e)}")
            return

        batch_std = []
        batch_fts = []
        count = 0

        try:
            with sqlite3.connect(DB_FILE, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=OFF;")
                conn.execute("BEGIN TRANSACTION")

                try:
                    iterator = mdx.items()
                except Exception as e:
                    self.progress_sig.emit(f"❌ 读取 MDX 内容失败: {str(e)}")
                    return

                for k_bytes, v_bytes in iterator:
                    try:
                        k_s = k_bytes.decode('utf-8').strip()
                    except:
                        try:
                            k_s = k_bytes.decode('gbk', 'ignore').strip()
                        except:
                            continue

                    if not k_s: continue

                    try:
                        v_c = pre_process_entry_content(v_bytes, did)

                        try:
                            content_str = v_bytes.decode('utf-8')[:2000]
                        except:
                            content_str = v_bytes.decode('utf-8', 'ignore')[:2000]

                        if content_str:
                            plain_text = RE_WHITESPACE.sub(' ', space_cjk(RE_HTML_TAG.sub(' ', content_str))).strip()
                            if plain_text:
                                batch_fts.append((k_s, plain_text, did))

                        batch_std.append((k_s, v_c, did, len(k_s)))
                    except Exception as inner_e:
                        continue

                    if len(batch_std) >= 2000:
                        try:
                            conn.executemany("INSERT INTO standard_entries VALUES (?,?,?,?)", batch_std)
                            conn.executemany("INSERT INTO fts_entries(word, content_text, dict_id) VALUES (?,?,?)",
                                             batch_fts)
                            conn.commit()
                            conn.execute("BEGIN TRANSACTION")
                            batch_std = []
                            batch_fts = []
                            count += 2000
                            self.progress_sig.emit(f"📖 {name}: {count} 条...")
                        except sqlite3.OperationalError as db_e:
                            time.sleep(1)
                            continue

                if batch_std:
                    conn.executemany("INSERT INTO standard_entries VALUES (?,?,?,?)", batch_std)
                    conn.executemany("INSERT INTO fts_entries(word, content_text, dict_id) VALUES (?,?,?)", batch_fts)
                    conn.commit()

        except Exception as e:
            self.progress_sig.emit(f"❌ 错误: {str(e)}")

    def process_mdd(self, path, did, name):
        # 允许传入单个 mdd_path 或用分号拼接的多个 mdd_path
        try:
            raw = path or ""
            if isinstance(raw, str):
                mdd_paths = [p.strip() for p in raw.split(";") if p.strip()]
            else:
                mdd_paths = list(raw)
        except:
            mdd_paths = [path]

        if not mdd_paths:
            return

        self.progress_sig.emit(f"🗂️ 正在导入资源: {name}... (mdd x{len(mdd_paths)})")

        batch = []
        count = 0
        BATCH_SIZE = 500

        try:
            from readmdict import MDD  # 内联导入
        except Exception as e:
            self.progress_sig.emit(f"❌ 缺少 readmdict 库，无法导入 MDD: {str(e)}")
            return

        try:
            with sqlite3.connect(MDD_DB_FILE, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=OFF;")
                conn.execute("BEGIN TRANSACTION")

                # 多个 MDD 合并导入：只清一次表
                conn.execute("DELETE FROM resources WHERE dict_id=?", (did,))

                for one_path in mdd_paths:
                    try:
                        mdd = MDD(one_path)
                    except Exception as e:
                        self.progress_sig.emit(f"❌ 无法加载 MDD: {os.path.basename(str(one_path))} ({str(e)})")
                        continue

                    for k_bytes, v_bytes in mdd.items():
                        try:
                            try:
                                k_str = k_bytes.decode('utf-8')
                            except UnicodeDecodeError:
                                try:
                                    k_str = k_bytes.decode('gbk')
                                except UnicodeDecodeError:
                                    k_str = k_bytes.decode('utf-8', 'ignore')

                            norm_key = k_str.replace('/', '\\').upper().strip()
                            norm_key = '\\' + norm_key.lstrip('\\')
                            norm_key = norm_key.replace('\x00', '')
                            batch.append((did, norm_key, v_bytes))
                        except:
                            continue

                        if len(batch) >= BATCH_SIZE:
                            conn.executemany("INSERT OR IGNORE INTO resources VALUES (?,?,?)", batch)
                            batch = []
                            count += BATCH_SIZE
                            if count % 2000 == 0:
                                self.progress_sig.emit(f"🗂️ {name}: 已存 {count} 条资源...")

                if batch:
                    conn.executemany("INSERT OR IGNORE INTO resources VALUES (?,?,?)", batch)

                # 记录导入来源（用于排查/复用）
                conn.execute("INSERT OR REPLACE INTO cached_dicts VALUES (?,?,?)", (did, ';'.join(mdd_paths), time.time()))
                conn.commit()

        except Exception as e:
            self.progress_sig.emit(f"❌ MDD 导入错误: {str(e)}")



# --- SearchWorker ---
# [包含 Optimization 2 的内容 + Optimization 3 的 Lazy OpenCC]
class SearchWorker(QThread):
    results_ready = Signal(str, list, list)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        q = self.query.strip()
        if not q:
            self.results_ready.emit(q, [], [])
            return

        raw_candidates = []
        # 仅当包含中文时，保留现有“全文检索/例句命中”等逻辑；英文则只做词头精确匹配并大小写不敏感。
        has_cjk = any('\u4e00' <= c <= '\u9fff' for c in q)

        with sqlite3.connect(DB_FILE, timeout=10) as conn:
            conn.execute("PRAGMA query_only=1;")
            conn.execute("PRAGMA mmap_size = 536870912;")
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT id, name, priority, path FROM dict_info ORDER BY priority ASC")
                dict_map = {d[0]: {'name': d[1], 'pri': d[2], 'path': d[3]} for d in cursor.fetchall()}

                # 1) 英文/非中文：仅精确匹配（大小写不敏感）
                if not has_cjk:
                    cursor.execute(
                        "SELECT word, NULL, dict_id, 1 FROM standard_entries WHERE word = ? COLLATE NOCASE",
                        (q,)
                    )
                    raw_candidates.extend(cursor.fetchall())
                else:
                    # 2) 中文：保留现有逻辑（含简繁转换 + fts）
                    cursor.execute("SELECT word, NULL, dict_id, 1 FROM standard_entries WHERE word = ?", (q,))
                    raw_candidates.extend(cursor.fetchall())

                    search_terms = {q}
                    # [优化] 使用懒加载的 get_opencc()
                    s2t = get_opencc('s2t')
                    t2s = get_opencc('t2s')

                    if s2t:
                        try:
                            search_terms.add(s2t.convert(q))
                            if t2s:
                                search_terms.add(t2s.convert(q))
                        except:
                            pass

                    fts_query_parts = []
                    for t in search_terms:
                        cleaned = space_cjk(t).strip()
                        if not cleaned:
                            continue
                        fts_query_parts.append(f'"{cleaned}"')

                    if fts_query_parts:
                        fts_q_str = " OR ".join(fts_query_parts)
                        try:
                            cursor.execute(
                                "SELECT word, dict_id, content_text FROM fts_entries WHERE fts_entries MATCH ? LIMIT 50",
                                (fts_q_str,))
                            for r_word, r_did, r_text in cursor.fetchall():
                                if any(x[0] == r_word and x[2] == r_did for x in raw_candidates):
                                    continue
                                len_score = len(r_word) / 100.0
                                raw_candidates.append((r_word, None, r_did, 3.0 + len_score))
                        except:
                            # 中文模式下 fts 不可用就算了，仍然用精确匹配结果
                            pass
            except sqlite3.OperationalError:
                pass


            # 排序 & 截断
            raw_candidates.sort(key=lambda x: (x[3], dict_map.get(x[2], {}).get('pri', 999), len(x[0])))
            final_candidates = raw_candidates[:30]

            tasks_data = []
            seen = set()

            # 按需读取 Content
            for item in final_candidates:
                r_word, r_blob, d_id, r_score = item
                key = f"{r_word}_{d_id}"
                if key in seen: continue
                seen.add(key)

                if r_blob is None:
                    row = conn.execute("SELECT content FROM standard_entries WHERE word=? AND dict_id=?",
                                       (r_word, d_id)).fetchone()
                    if row:
                        r_blob = row[0]
                    else:
                        continue

                d_info = dict_map.get(d_id, {'name': '未知', 'path': None})
                tasks_data.append((r_word, r_blob, d_id, r_score, d_info))

        if tasks_data:
            try:
                batch_size = 3
                batch_1 = tasks_data[:batch_size]
                batch_2 = tasks_data[batch_size:]

                results_1 = list(GLOBAL_EXECUTOR.map(process_entry_task, batch_1))
                if results_1:
                    self.results_ready.emit(q, results_1, [])

                if batch_2:
                    results_2 = list(GLOBAL_EXECUTOR.map(process_entry_task, batch_2))
                    full_results = results_1 + results_2
                    self.results_ready.emit(q, full_results, [])

            except Exception as e:
                self.results_ready.emit(q, [], [])
        else:
            suggestions = []
            if len(q) > 2 and not has_cjk:
                try:
                    with sqlite3.connect(DB_FILE) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT word FROM standard_entries WHERE word LIKE ? COLLATE NOCASE LIMIT 5",
                            (f"{q[:2]}%",)
                        )
                        suggestions = [r[0] for r in cursor.fetchall()]
                except:
                    pass
            self.results_ready.emit(q, [], suggestions)


def strip_tags(html):
    """移除 HTML 标签获取纯文本"""
    if not html: return ""
    return re.sub(r'<[^>]+>', '', html)

def is_pure_english(text):
    """判断是否为纯英文单词（允许少量连字符或空格）"""
    try:
        # ASCII 范围判断，且不包含数字
        return all(ord(c) < 128 for c in text) and not any(c.isdigit() for c in text)
    except:
        return False

def clean_sentence_text(text):
    """深度清洗句子文本"""
    if not text: return ""

    # 1. HTML 解码 (&nbsp; -> 空格)
    text = html.unescape(text)

    # 2. 去除 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)

    # 3. [关键] 去除方头括号 【...】 和普通中括号 [...] 及其内容
    # 很多词典用这些标注语法，如 【搭配模式】
    text = re.sub(r'【.*?】', '', text)
    text = re.sub(r'\[.*?\]', '', text)

    # 4. 去除常见的非句子干扰词 (Style tags)
    # 比如 "STYLE标签", "INFORMAL" 等全大写或特殊前缀
    text = re.sub(r'\b[A-Z]{2,}\b', '', text)  # 去除全大写单词(往往是标签)

    # 5. 压缩空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_random_words(count=3, exclude_word="", target_is_english=True):
    """
    从数据库随机获取干扰项
    增加了语言检测：如果学的是英文，干扰项也必须是英文
    """
    candidates = []
    attempts = 0
    max_attempts = 20  # 防止死循环

    try:
        with sqlite3.connect(DB_FILE) as conn:
            while len(candidates) < count and attempts < max_attempts:
                # 每次多取几个备选
                cursor = conn.execute(
                    "SELECT word FROM standard_entries WHERE word != ? ORDER BY RANDOM() LIMIT 10",
                    (exclude_word,)
                )
                rows = cursor.fetchall()

                for r in rows:
                    w = r[0]
                    # 过滤逻辑：
                    # 1. 如果目标是英文，干扰项必须是纯英文
                    # 2. 长度不能太夸张 (>20 通常是词组或脏数据)
                    # 3. 长度不能太短 (<2)
                    if len(w) > 20 or len(w) < 2: continue

                    if target_is_english:
                        if is_pure_english(w):
                            if w not in candidates: candidates.append(w)
                    else:
                        # 如果目标本身就是中文，那干扰项随意
                        if w not in candidates: candidates.append(w)

                    if len(candidates) >= count: break

                attempts += 1

        # 如果实在找不到，用备用词
        if len(candidates) < count:
            backups = ["Apple", "Banana", "Cherry", "Date", "Elderberry"]
            for b in backups:
                if b not in candidates and b != exclude_word:
                    candidates.append(b)
                if len(candidates) >= count: break

        return candidates[:count]
    except:
        return ["Option A", "Option B", "Option C"]


def generate_quiz_data(args):
    """
    生成测验数据的任务函数
    args: (word, content_blob)
    """
    target_word, content = args
    if isinstance(content, bytes):
        try:
            content = zlib.decompress(content).decode('utf-8', 'ignore')
        except:
            return None

    # 判断目标词是否为英文
    target_is_eng = is_pure_english(target_word)

    # 1. 深度清洗
    # 我们先保留 content 中的句子结构，然后再清洗
    # 更好的策略是：先用正则提取句子，再对句子进行清洗

    # 移除 HTML 标签，但保留一些结构以便断句
    raw_text = html.unescape(content)
    raw_text = re.sub(r'<[^>]+>', ' ', raw_text)  # 标签换空格，防止粘连

    # 2. 断句
    # 针对截图中的问题，很多例句混杂在中文解释里
    # 我们尝试提取 "英文句子 + 中文翻译" 结构中的英文部分

    sentences = re.split(r'(?<=[.!?])\s+', raw_text)

    valid_sentences = []
    # 正则：匹配目标词
    pattern = re.compile(r'\b' + re.escape(target_word) + r'[a-z]*\b', re.IGNORECASE)

    for s in sentences:
        clean_s = clean_sentence_text(s)

        # 严格筛选逻辑：
        # 1. 包含目标词
        # 2. 长度适中
        # 3. [关键] 如果是英文测验，句子必须主要由英文字符组成
        #    防止提取到 "INFORMAL 非正式" 这种片段
        if 20 < len(clean_s) < 200:
            if pattern.search(clean_s):
                # 计算英文字符占比，如果包含大量中文(说明没清洗干净或是双语对照)，尝试只提取英文部分
                eng_chars = sum(1 for c in clean_s if 'a' <= c.lower() <= 'z' or c == ' ')
                ratio = eng_chars / len(clean_s)

                if ratio > 0.7:  # 70% 以上是英文，认为是好句子
                    valid_sentences.append(clean_s)
                else:
                    # 尝试再次清洗，提取前半部分的英文 (很多词典是 English Sentence. 中文翻译。)
                    # 这是一个简单的启发式规则
                    split_by_dot = clean_s.split('.')
                    if len(split_by_dot) > 1:
                        potential = split_by_dot[0] + "."
                        if pattern.search(potential) and len(potential) > 20:
                            valid_sentences.append(potential)

    if not valid_sentences:
        return None

    # 4. 随机选一句并挖空
    # 优先选短一点的句子，长句子容易包含乱码
    valid_sentences.sort(key=len)
    chosen_sentence = valid_sentences[0] if len(valid_sentences) < 3 else random.choice(valid_sentences[:3])

    masked_sentence = pattern.sub("________", chosen_sentence)

    # 5. 获取干扰项 (传入 target_is_eng 标记)
    options = get_random_words(3, target_word, target_is_english=target_is_eng)
    options.append(target_word)
    random.shuffle(options)

    return {
        "type": "quiz",
        "question": masked_sentence,
        "options": options,
        "answer": target_word,
        "origin": chosen_sentence
    }

class QuizWorker(QThread):
    data_ready = Signal(object)  # 发送字典数据

    def __init__(self, word, dict_id=None):
        super().__init__()
        self.word = word
        self.dict_id = dict_id

    def run(self):
        # 1. 先尝试获取单词内容
        content = None
        with sqlite3.connect(DB_FILE) as conn:
            if self.dict_id:
                row = conn.execute("SELECT content FROM standard_entries WHERE word=? AND dict_id=?",
                                   (self.word, self.dict_id)).fetchone()
            else:
                row = conn.execute("SELECT content FROM standard_entries WHERE word=? LIMIT 1",
                                   (self.word,)).fetchone()

            if row:
                content = row[0]

        if not content:
            self.data_ready.emit(None)
            return

        # 2. 在后台生成题目
        try:
            # 现在 generate_quiz_data 是全局函数，可以直接调用了
            result = generate_quiz_data((self.word, content))
            self.data_ready.emit(result)
        except Exception as e:
            print(f"Quiz Gen Error: {e}")
            self.data_ready.emit(None)


# file: backend.py (Append to end)

# --- 极简停用词表 (Top 150 Common English Words) ---
# 过滤掉这些词，剩下的往往是有学习价值的“实词”
STOP_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
    "or", "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "when", "make", "can", "like", "time", "no", "just", "him", "know", "take",
    "people", "into", "year", "your", "good", "some", "could", "them", "see", "other",
    "than", "then", "now", "look", "only", "come", "its", "over", "think", "also",
    "back", "after", "use", "two", "how", "our", "work", "first", "well", "way",
    "even", "new", "want", "because", "any", "these", "give", "day", "most", "us",
    "is", "are", "was", "were", "been", "has", "had", "did", "does", "am"
}


# 找到 backend.py 中的 class AnalyzerWorker，完全替换为以下代码：

# [backend.py] 替换 AnalyzerWorker 类

class AnalyzerWorker(QThread):
    analysis_ready = Signal(list)  # [(word, count), ...]

    def __init__(self, text, is_html=False):
        super().__init__()
        self.text = text
        self.is_html = is_html

    def run(self):
        text = self.text
        if not text:
            self.analysis_ready.emit([])
            return

        # 1. 简单清洗
        if self.is_html:
            text = re.sub(r'<[^>]+>', ' ', text)

        # 2. 正则分词
        # 只要3个字母以上的纯英文单词
        raw_words = re.findall(r'\b[a-z]{3,}\b', text.lower())

        # 3. 统计词频
        from collections import Counter
        counter = Counter(raw_words)

        # 4. 过滤停用词
        candidates = [w for w in counter.keys() if w not in STOP_WORDS]

        valid_results = []

        # === [修复] 检查是否有词典数据 ===
        # 如果没有词典，数据库验证会把所有词都过滤掉，导致结果为空。
        # 策略：如果有词典，严格验证；如果没有，直接通过。
        has_dictionary = False
        try:
            with sqlite3.connect(DB_FILE, timeout=10) as conn:
                # 检查 standard_entries 表是否有数据
                check = conn.execute("SELECT 1 FROM standard_entries LIMIT 1").fetchone()
                if check:
                    has_dictionary = True
        except:
            pass  # 数据库出错当作没有词典处理

        if not has_dictionary:
            # [Fallback模式] 没有导入词典时，直接根据频率返回，不查数据库
            # 按频率降序
            sorted_candidates = sorted(candidates, key=lambda w: counter[w], reverse=True)
            # 构造结果 [(word, count), ...]
            valid_results = [(w, counter[w]) for w in sorted_candidates]

        else:
            # [正常模式] 有词典，进行数据库验证
            chunk_size = 900
            try:
                with sqlite3.connect(DB_FILE, timeout=10) as conn:
                    cursor = conn.cursor()
                    for i in range(0, len(candidates), chunk_size):
                        batch = candidates[i:i + chunk_size]
                        if not batch: break

                        placeholders = ",".join("?" * len(batch))
                        sql = f"SELECT word FROM standard_entries WHERE word IN ({placeholders}) COLLATE NOCASE"

                        try:
                            cursor.execute(sql, batch)
                            db_words = {r[0].lower() for r in cursor.fetchall()}
                            for w in batch:
                                if w in db_words:
                                    valid_results.append((w, counter[w]))
                        except Exception as e:
                            print(f"Batch query error: {e}")
            except Exception as e:
                print(f"DB Connection error: {e}")

            # 数据库验证后的结果可能乱序了，重新按频率排序
            valid_results.sort(key=lambda x: x[1], reverse=True)

        # 5. 截断结果
        limit = 1000
        self.analysis_ready.emit(valid_results[:limit])


# 简单的 EPUB 文本提取器 (无需第三方库)
import zipfile


def extract_text_from_epub(epub_path):
    """
    极简 EPUB 解析：解压 -> 遍历 .html/.xhtml -> 提取文本
    """
    full_text = []
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            for name in z.namelist():
                if name.endswith(('.html', '.xhtml', '.htm')):
                    with z.open(name) as f:
                        try:
                            content = f.read().decode('utf-8', 'ignore')
                            # 简单去标签
                            text = re.sub(r'<[^>]+>', ' ', content)
                            full_text.append(text)
                        except:
                            pass
    except Exception as e:
        return f"Error reading EPUB: {str(e)}"

    return "\n".join(full_text)