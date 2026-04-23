# file: src/core/news_workers.py
# -*- coding: utf-8 -*-
"""
RSS新闻相关的工作线程
包含RSS源测试、新闻内容提取、新闻聚合搜索等功能
"""
import re
import sqlite3
import xml.etree.ElementTree as ET

from PySide6.QtCore import QThread, Signal

from .config import DB_FILE
from .utils import fetch_url_content
from .logger import logger


class RSSTestWorker(QThread):
    """
    RSS源测试工作线程 - 验证RSS源是否可用
    
    Signals:
        test_result(bool, str): (是否成功, 结果信息)
    """
    test_result = Signal(bool, str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        if not self.url.startswith("http"):
            self.test_result.emit(False, "URL must start with http/https")
            return

        # 自带详细错误信息的HTTP下载（独立于fetch_url_content，便于调试）
        import ssl
        import gzip
        import urllib.request
        import urllib.error
        import socket

        data = None
        err_detail = ""
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml, */*',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            req = urllib.request.Request(self.url, headers=headers)

            resp = urllib.request.urlopen(req, timeout=15, context=ctx)
            data = resp.read()
            if resp.info().get('Content-Encoding') == 'gzip':
                try:
                    data = gzip.decompress(data)
                except Exception:
                    pass

        except urllib.error.HTTPError as e:
            err_detail = f"HTTP {e.code}: {e.reason}"
            logger.warning(f"RSS测试HTTP错误 [{self.url}]: {err_detail}")
            self.test_result.emit(False, f"HTTP Error\n{err_detail}")
            return
        except urllib.error.URLError as e:
            reason = str(e.reason)
            if isinstance(e.reason, ssl.SSLError):
                err_detail = f"SSL Error: {reason}"
            elif isinstance(e.reason, socket.gaierror):
                err_detail = f"DNS解析失败 (无法解析域名)\n{reason}"
            elif isinstance(e.reason, socket.timeout) or "timed out" in reason.lower():
                err_detail = f"连接超时 ({15}秒内无响应)\n请检查网络或尝试其他源"
            elif "connection refused" in reason.lower():
                err_detail = f"连接被拒绝\n服务器可能不可用"
            else:
                err_detail = f"连接失败\n{reason}"
            logger.warning(f"RSS测试URL错误 [{self.url}]: {err_detail}")
            self.test_result.emit(False, err_detail)
            return
        except socket.timeout:
            err_detail = "连接超时 (15秒无响应)"
            logger.warning(f"RSS测试超时 [{self.url}]")
            self.test_result.emit(False, err_detail)
            return
        except Exception as e:
            err_detail = f"{type(e).__name__}: {str(e)}"
            logger.error(f"RSS测试异常 [{self.url}]: {err_detail}", exc_info=True)
            self.test_result.emit(False, f"未知错误\n{err_detail}")
            return

        if not data:
            self.test_result.emit(False, "下载数据为空 (Empty Response)")
            return

        try:
            try:
                xml_str = data.decode('utf-8', 'ignore').strip()
            except UnicodeDecodeError:
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
                logger.info(f"RSS源测试成功 [{self.url}]: 找到{count}条")
            else:
                self.test_result.emit(False, "XML parsed but no news items found.")

        except Exception as e:
            logger.error(f"RSS解析失败 [{self.url}]: {e}")
            self.test_result.emit(False, f"Parse Error: {str(e)}")


class NewsContentWorker(QThread):
    """
    新闻内容提取工作线程 - 从URL提取文章正文
    
    Signals:
        content_ready(str, str, str): (标题, 正文HTML, 原始URL)
    """
    content_ready = Signal(str, str, str)

    def __init__(self, url: str):
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
            except UnicodeDecodeError:
                html = data.decode('gbk', 'ignore')

            # HTML清洗：移除脚本、样式、无关标签
            html = re.sub(
                r'<script[^>]*?>.*?</script>', '', 
                html, flags=re.IGNORECASE | re.DOTALL
            )
            html = re.sub(
                r'<style[^>]*?>.*?</style>', '', 
                html, flags=re.IGNORECASE | re.DOTALL
            )
            html = re.sub(
                r'<(svg|nav|footer|header|aside|noscript|iframe)[^>]*>.*?</\1>',
                '', html, flags=re.IGNORECASE | re.DOTALL
            )

            # 提取标题
            title = "No Title"
            t_match = re.search(r'<title>(.*?)</title>', html, flags=re.IGNORECASE)
            if t_match:
                title = t_match.group(1).strip().split(" - ")[0].split(" | ")[0]

            # 提取正文段落
            clean_paragraphs = []
            
            # 优先提取 <p> 标签
            p_matches = re.findall(r'<p[^>]*>(.*?)</p>', html, flags=re.DOTALL | re.IGNORECASE)
            for p in p_matches:
                text = re.sub(r'<[^>]+>', '', p).strip()
                if len(text) > 30:
                    clean_paragraphs.append(f"<p>{text}</p>")

            # 兜底：尝试 <div>
            if not clean_paragraphs:
                divs = re.findall(r'<div[^>]*>(.*?)</div>', html, flags=re.DOTALL | re.IGNORECASE)
                for d in divs:
                    text = re.sub(r'<[^>]+>', '', d).strip()
                    if len(text) > 150:
                        clean_paragraphs.append(f"<p>{text[:1000]}...</p>")

            if not clean_paragraphs:
                body_html = (
                    "<div style='text-align:center;margin-top:50px;'>"
                    "<h3>Unable to extract text.</h3>"
                    f"<p><a href='{self.url}'>Open in browser</a></p></div>"
                )
            else:
                body_html = "\n".join(clean_paragraphs[:100])

            self.content_ready.emit(title, body_html, self.url)
            logger.info(f"新闻内容提取完成: {title[:30]}...")

        except Exception as e:
            logger.error(f"新闻内容提取失败 [{self.url}]: {e}", exc_info=True)
            self.content_ready.emit("Load Failed", f"<p>Error: {str(e)}</p>", self.url)


class NewsWorker(QThread):
    """
    新闻聚合搜索工作线程
    
    优化：使用线程池并行下载RSS源，添加总超时保护，避免打包版本长时间卡死
    
    Signals:
        news_ready(list, str): (搜索结果列表, 查询关键词)
    """

    news_ready = Signal(list, str)

    def __init__(self, query: str):
        super().__init__()
        self.query = query
        # 超时配置（打包后网络较慢，需要合理超时）
        self._per_source_timeout = 6   # 单个RSS源超时（秒）
        self._total_timeout = 20       # 整体最大等待时间（秒）

    def _fetch_single_source(self, src: dict) -> list:
        """获取单个RSS源的结果（在线程池中并行执行）"""

        try:
            data = fetch_url_content(src['url'], timeout=self._per_source_timeout)
            if not data:
                logger.warning(f"RSS源 [{src['name']}] 下载返回空数据")
                return []

            try:
                xml_str = data.decode('utf-8', 'ignore').strip()
            except Exception:
                xml_str = data.decode('gbk', 'ignore').strip()

            if not xml_str.startswith('<'):
                logger.warning(f"RSS源 [{src['name']}] 返回非XML数据 (前50字符: {xml_str[:50]})")
                return []

            root = ET.fromstring(xml_str)
            items = root.findall('./channel/item')
            if not items:
                items = root.findall('item')

            results = []
            seen_in_source = set()
            query_lower = self.query.lower().strip()
            
            # 判断是否为浏览模式（无特定搜索词）
            # 浏览模式: query为空、'latest'、或长度<=2的短词 -> 返回所有新闻
            is_browse_mode = (not query_lower or query_lower == 'latest' 
                              or len(query_lower) <= 2)

            for item in items:
                link_node = item.find('link')
                if link_node is None or not link_node.text:
                    continue
                link = link_node.text.strip()
                if not link or link in seen_in_source:
                    continue

                title_node = item.find('title')
                desc_node = item.find('description')
                date_node = item.find('pubDate')

                title = title_node.text if (
                    title_node is not None and title_node.text
                ) else "No Title"
                raw_body = desc_node.text if (
                    desc_node is not None and desc_node.text
                ) else ""
                pub_date = date_node.text if (
                    date_node is not None and date_node.text
                ) else ""

                body_text = re.sub(r'<[^>]+>', '', raw_body).strip()
                if len(pub_date) > 16:
                    pub_date = pub_date[:16]

                # 浏览模式：返回所有新闻；搜索模式：子串匹配
                if is_browse_mode or (query_lower in title.lower()
                        or query_lower in body_text.lower()):
                    seen_in_source.add(link)
                    results.append({
                        "title": title,
                        "body": (body_text[:200] + "... "
                                if len(body_text) > 200 else body_text),
                        "source": src['name'],
                        "date": pub_date,
                        "url": link,
                    })

            logger.info(f"RSS源 [{src['name']}] 获取到 {len(results)} 条"
                       f"(共{len(items)}条, 模式={'浏览' if is_browse_mode else '搜索'})")
            return results

        except Exception as e:
            import traceback
            logger.error(f"RSS源下载失败 [{src.get('name', '?')}]: "
                       f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            return []

    def run(self):
        """使用线程池并行获取所有RSS源，带总超时保护"""
        import concurrent.futures

        if not self.query:
            self.news_ready.emit([], "")
            return

        # 从数据库获取启用的RSS源
        sources = []
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cur = conn.execute("SELECT name, url FROM rss_sources WHERE enabled=1")
                sources = [{"name": r[0], "url": r[1]} for r in cur.fetchall()]
        except sqlite3.OperationalError:
            sources = [{"name": "China Daily",
                        "url": "http://www.chinadaily.com.cn/rss/world_rss.xml"}]
        except Exception as e:
            logger.error(f"获取RSS源失败: {e}")

        if not sources:
            self.news_ready.emit([], self.query)
            return

        all_results = []
        seen_links = set()

        # 使用线程池并行下载所有RSS源（关键优化！）
        # 打包版本中每个源可能很慢（SSL握手慢），串行会导致长时间卡顿
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(sources), 5),
            thread_name_prefix="rss_fetch"
        ) as executor:
            future_to_src = {
                executor.submit(self._fetch_single_source, src): src
                for src in sources
            }

            # 带总超时的等待
            done_futures = set()
            try:
                done_futures, _ = concurrent.futures.wait(
                    future_to_src.keys(),
                    timeout=self._total_timeout
                )
            except Exception:
                pass

            # 收集已完成任务的结果
            for future in done_futures:
                try:
                    source_results = future.result(timeout=1)
                    for r in source_results:
                        if r['url'] not in seen_links:
                            seen_links.add(r['url'])
                            all_results.append(r)
                except Exception:
                    pass

            # 记录超时的源
            remaining = set(future_to_src.keys()) - done_futures
            if remaining:
                src_names = [future_to_src[f].get('name', '?') for f in remaining]
                logger.warning(f"有{len(remaining)}个RSS源超时未完成: {src_names}")

        logger.info(f"新闻搜索完成: query='{self.query}', 共获取 {len(all_results)} 条结果")
        self.news_ready.emit(all_results, self.query)
