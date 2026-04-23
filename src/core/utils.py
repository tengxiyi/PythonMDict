# file: src/core/utils.py
# -*- coding: utf-8 -*-
"""
通用工具函数集
包含文本处理、HTML清洗、OpenCC转换等辅助功能
"""
import re
import html as html_module
import zlib
import urllib.parse
from typing import Optional

from .logger import logger


# ============== 正则表达式预编译 ==============
RE_HTML_TAG = re.compile(r'<[^>]+>')
RE_WHITESPACE = re.compile(r'\s+')
RE_CJK = re.compile(r'([\u4e00-\u9fa5])')
RE_SRC = re.compile(r'(src=)(["\'])(.*?)(["\'])', re.IGNORECASE)
RE_HREF = re.compile(r'(href=)(["\'])(.*?)(["\'])', re.IGNORECASE)


# ============== OpenCC 懒加载单例 ==============
_opencc_s2t = None
_opencc_t2s = None
_has_opencc = None


def get_opencc(direction: str = 's2t'):
    """
    按需加载 OpenCC 简繁转换器，避免启动时耗时
    
    Args:
        direction: 's2t'=简转繁, 't2s'=繁转简
        
    Returns:
        OpenCC实例或None（如果未安装）
    """
    global _opencc_s2t, _opencc_t2s, _has_opencc
    
    if _has_opencc is False:
        return None
    
    if _has_opencc is None:
        try:
            import opencc
            _opencc_s2t = opencc.OpenCC('s2t')
            _opencc_t2s = opencc.OpenCC('t2s')
            _has_opencc = True
            logger.info("OpenCC 加载成功")
        except ImportError:
            _has_opencc = False
            logger.warning("OpenCC 未安装，简繁转换功能不可用")
            return None
    
    return _opencc_s2t if direction == 's2t' else _opencc_t2s


# ============== 文本处理函数 ==============

def space_cjk(text: str) -> str:
    """在CJK字符两侧添加空格（用于FTS分词）"""
    if not text:
        return ""
    return RE_CJK.sub(r' \1 ', text)


def strip_tags(html_content: str) -> str:
    """移除HTML标签获取纯文本"""
    if not html_content:
        return ""
    return re.sub(r'<[^>]+>', '', html_content)


def is_pure_english(text: str) -> bool:
    """
    判断是否为纯英文单词（允许少量连字符或空格，不含数字）
    
    Args:
        text: 待检测文本
        
    Returns:
        True如果是纯英文
    """
    try:
        return all(ord(c) < 128 for c in text) and not any(c.isdigit() for c in text)
    except Exception:
        return False


def clean_sentence_text(text: str) -> str:
    """
    深度清洗句子文本（用于测验题目生成）
    
    处理步骤：
    1. HTML解码 (&nbsp; -> 空格)
    2. 移除HTML标签
    3. 去除【...】和[...]标注
    4. 去除全大写单词（通常是语法标签）
    5. 压缩空白
    
    Args:
        text: 待清洗的HTML/文本
        
    Returns:
        清洗后的纯文本
    """
    if not text:
        return ""

    # HTML 解码
    text = html_module.unescape(text)

    # 去除 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)

    # 去除方头括号和中括号及其内容（语法标注）
    text = re.sub(r'【.*?】', '', text)
    text = re.sub(r'\[.*?\]', '', text)

    # 去除全大写单词（语法标签如STYLE, INFORMAL等）
    text = re.sub(r'\b[A-Z]{2,}\b', '', text)

    # 压缩空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============== 词条预处理 ==============

def pre_process_entry_content(content_bytes: bytes, dict_id: int) -> bytes:
    """
    索引时预处理词条内容：
    1. 解码（UTF-8/GBK兼容）
    2. 清理控制字符
    3. 重写资源链接为 mdict:// 协议
    
    Args:
        content_bytes: 原始词条字节数据
        dict_id: 词典ID
        
    Returns:
        zlib压缩后的处理结果
    """
    try:
        html_str = content_bytes.decode('utf-8').strip()
    except UnicodeDecodeError:
        try:
            html_str = content_bytes.decode('gbk', 'ignore').strip()
        except Exception as e:
            logger.warning(f"词条编码解码失败(dict_id={dict_id}): {e}")
            html_str = content_bytes.decode('utf-8', 'ignore').strip()

    # 清理控制字符
    html_str = html_str.replace('\x00', '').replace('\x1e', '').replace('\x1f', '')

    def repl(m):
        """URL路径重写回调函数"""
        prefix, quote, path, suffix = m.groups()
        
        # 跳过特殊协议
        if path.startswith(('http', 'https', 'data:', 'javascript:', '#', 'entry:', 'mdict:', 'file:')):
            return m.group(0)
        
        # 处理 sound:// 协议
        try:
            low = path.lower()
            if low.startswith("sound://"):
                path = path.split("//", 1)[1]
            elif low.startswith("sound:"):
                path = path.split(":", 1)[1]
        except Exception:
            pass
        
        clean_path = path.lstrip('/\\').replace('\\', '/')
        clean_path = urllib.parse.quote(clean_path)
        return f'{prefix}{quote}mdict://{dict_id}/{clean_path}{quote}'

    html_str = RE_SRC.sub(repl, html_str)
    html_str = RE_HREF.sub(repl, html_str)

    return zlib.compress(html_str.encode('utf-8'))


# ============== 词条渲染任务 ==============

def process_entry_task(args: tuple) -> dict:
    """
    搜索结果的词条渲染任务（在线程池中执行）
    
    Args:
        args: (word, blob, dict_id, score, dict_info) 元组
        
    Returns:
        包含渲染后词条信息的字典
    """
    r_word, r_blob, d_id, r_score, d_info = args
    
    try:
        content = zlib.decompress(r_blob).decode('utf-8', 'ignore') if isinstance(r_blob, bytes) else r_blob
    except Exception as e:
        logger.warning(f"词条解压失败({r_word}): {e}")
        content = f"Decode Error: {e}"

    # 运行时链接重写：将 mdict:// 资源链接中的单词跳转改为 entry:// 协议
    def fix_link_handler(match):
        quote = match.group(1)
        url = match.group(2)
        
        lower = url.lower()
        # 资源文件白名单 - 保持原样
        res_exts = ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.bmp',
                    '.ico', '.svg', '.ttf', '.woff', '.mp3', '.wav', '.ogg', '.spx')
        
        if lower.split('?')[0].endswith(res_exts) or "mdict://css/" in lower or "mdict://theme/" in lower:
            return match.group(0)
        
        # 提取单词并构造 entry 协议链接
        try:
            if "mdict://" in url:
                path = url.split("mdict://", 1)[1]
                if "/" in path:
                    word_part = path.split("/", 1)[1]
                    return f'href={quote}entry://query/{word_part}{quote}'
        except Exception:
            pass
        
        return match.group(0)

    try:
        content = re.sub(
            r'href=(["\'])(mdict://.*?)\1',
            fix_link_handler,
            content,
            flags=re.IGNORECASE
        )
    except Exception as e:
        logger.debug(f"链接重写失败: {e}")

    return {
        "word": r_word,
        "content": content,
        "dict_name": d_info['name'],
        "rank": r_score,
        "dict_id": d_id,
        "dict_path": d_info['path']
    }


# ============== 网络请求 ==============

def fetch_url_content(url: str, timeout: int = 5) -> Optional[bytes]:
    """
    通用HTTP下载函数（支持SSL和gzip解压）
    
    Args:
        url: 目标URL
        timeout: 超时时间(秒)
        
    Returns:
        下载的字节数据或None
    """
    import ssl
    import gzip
    
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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
                except Exception:
                    pass
            return data

    except Exception as e:
        logger.debug(f"下载失败 [{url}]: {e}")
        return None


# ============== EPUB 解析 ==============

import zipfile


def extract_text_from_epub(epub_path: str) -> str:
    """
    极简EPUB解析：解压 -> 遍历 .html/.xhtml -> 提取文本
    
    Args:
        epub_path: EPUB文件路径
        
    Returns:
        提取的全部文本，或错误信息字符串
    """
    full_text = []
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            for name in z.namelist():
                if name.endswith(('.html', '.xhtml', '.htm')):
                    with z.open(name) as f:
                        try:
                            content = f.read().decode('utf-8', 'ignore')
                            text = re.sub(r'<[^>]+>', ' ', content)
                            full_text.append(text)
                        except Exception:
                            pass
    except Exception as e:
        logger.error(f"EPUB解析失败 [{epub_path}]: {e}")
        return f"Error reading EPUB: {str(e)}"

    return "\n".join(full_text)


# ============== 停用词表 ==============

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
"""Top 150 常见英文停用词 - 过滤后剩下的往往是学习价值高的实词"""
