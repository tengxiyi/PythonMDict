# file: src/core/quiz_worker.py
# -*- coding: utf-8 -*-
"""
测验生成工作线程
从词典例句中自动生成填空选择题
"""
import random
import re
import sqlite3
import html as html_module
import zlib

from PySide6.QtCore import QThread, Signal

from .config import DB_FILE
from .utils import (
    clean_sentence_text, is_pure_english,
    STOP_WORDS
)
from .logger import logger
from .connection_pool import pool


class QuizWorker(QThread):
    """
    测验题目生成工作线程
    
    Signals:
        data_ready(object): 发送生成的测验数据字典或None
    """
    data_ready = Signal(object)

    def __init__(self, word: str, dict_id: int = None):
        super().__init__()
        self.word = word
        self.dict_id = dict_id

    def run(self):
        # 获取单词内容 + 词典名称
        content = None
        dict_name = None
        try:
            conn = pool.get()
            if self.dict_id:
                row = conn.execute(
                    "SELECT content, d.name FROM standard_entries e "
                    "JOIN dict_info d ON e.dict_id = d.id "
                    "WHERE e.word=? AND e.dict_id=?",
                    (self.word, self.dict_id)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT content, d.name FROM standard_entries e "
                    "JOIN dict_info d ON e.dict_id = d.id "
                    "WHERE e.word=? LIMIT 1",
                    (self.word,)
                ).fetchone()

            if row:
                content = row[0]
                dict_name = row[1]
        except Exception as e:
            logger.error(f"获取测验词条失败({self.word}): {e}")

        if not content:
            self.data_ready.emit(None)
            return

        # 生成测验
        try:
            result = generate_quiz_data(
                (self.word, content), dict_id=self.dict_id, dict_name=dict_name
            )
            self.data_ready.emit(result)
        except Exception as e:
            logger.error(f"测验生成失败({self.word}): {e}", exc_info=True)
            self.data_ready.emit(None)


def get_random_words(count: int = 3, exclude_word: str = "",
                     target_is_english: bool = True,
                     target_len: int = 0) -> list[str]:
    """
    从数据库获取高质量干扰项单词（改进版）

    过滤条件：
    - 长度 2~20 字符，与目标词长度相差不超过4
    - 纯英文字母（排除撇号、连字符、数字等）
    - 全小写或首字母大写（排除全大写缩写/专有名词）
    - 非停用词
    - 不与目标词重复（忽略大小写）

    Args:
        count: 需要的干扰项数量
        exclude_word: 要排除的目标单词
        target_is_english: 是否需要纯英文干扰项
        target_len: 目标词长度，用于长度相似性筛选

    Returns:
        干扰项单词列表
    """
    import re
    # 合法单词模式：纯字母，全小写 或 仅首字母大写
    VALID_WORD = re.compile(r'^[a-z]+$|^[A-Z][a-z]+$')
    exclude_lower = exclude_word.lower()

    candidates = []
    attempts = 0
    max_attempts = 30  # 增加尝试次数以提高质量

    try:
        conn = pool.get()
        while len(candidates) < count and attempts < max_attempts:
                # SQL 层面预过滤：长度范围 + 英文字母开头
                min_len = max(2, target_len - 4) if target_len else 2
                max_len = min(20, target_len + 4) if target_len else 20
                cursor = conn.execute(
                    """SELECT word FROM standard_entries 
                       WHERE word != ? 
                         AND length(word) BETWEEN ? AND ?
                         AND word GLOB '[a-zA-Z]*'
                       ORDER BY RANDOM() LIMIT 15""",
                    (exclude_word, min_len, max_len)
                )
                rows = cursor.fetchall()

                for r in rows:
                    w = r[0]
                    w_lower = w.lower()

                    # 跳过已选中的
                    if w_lower in {c.lower() for c in candidates}:
                        continue

                    # 跳过目标词（大小写不敏感）
                    if w_lower == exclude_lower:
                        continue

                    # 过滤1：纯字母 + 规范大小写
                    if not VALID_WORD.match(w):
                        continue

                    # 过滤2：非停用词
                    if w_lower in STOP_WORDS:
                        continue

                    # 过滤3：英文模式下必须是纯英文
                    if target_is_english and not is_pure_english(w):
                        continue

                    candidates.append(w)
                    if len(candidates) >= count:
                        break

                attempts += 1

        # 兜底备用词（通用常见词，风格更一致）
        if len(candidates) < count:
            backups = [
                "example", "method", "result", "system",
                "important", "process", "available", "different"
            ]
            for b in backups:
                if b.lower() not in {c.lower() for c in candidates} \
                        and b.lower() != exclude_lower:
                    candidates.append(b)
                if len(candidates) >= count:
                    break

        return candidates[:count]

    except Exception as e:
        logger.warning(f"获取随机单词失败: {e}")
        return ["example", "method", "result"][:count]


def generate_quiz_data(args: tuple, dict_id: int = None, dict_name: str = None) -> dict | None:
    """
    生成测验数据的任务函数
    
    Args:
        args: (word, content_blob) 元组
        dict_id: 词典ID
        dict_name: 词典名称
        
    Returns:
        包含测验题目的字典，格式：
        {
            "type": "quiz",
            "question": "挖空后的句子",
            "options": [选项A, 选项B, 选项C, 选项D],
            "answer": "正确答案",
            "origin": "原始完整句子",
            "dict_name": "词典名称"
        }
        如果无法生成则返回None
    """
    target_word, content = args
    
    # 解压内容
    if isinstance(content, bytes):
        try:
            content = zlib.decompress(content).decode('utf-8', 'ignore')
        except Exception as e:
            logger.debug(f"解压测验内容失败: {e}")
            return None

    # 判断目标词是否英文
    target_is_eng = is_pure_english(target_word)

    # 清洗HTML并提取纯文本
    raw_text = html_module.unescape(content)
    raw_text = re.sub(r'<[^>]+>', ' ', raw_text)

    # 断句
    sentences = re.split(r'(?<=[.!?])\s+', raw_text)

    valid_sentences = []
    pattern = re.compile(r'\b' + re.escape(target_word) + r'[a-z]*\b', re.IGNORECASE)
    
    # 词典词条头特征模式（精确匹配，避免误杀正常句子中的斜杠等）
    DICT_HEADER_PATTERNS = [
        r'[①②③④⑤⑥⑦⑧⑨⑩]',   # 圈号义项标记
        r'[\^⁰¹²³⁴⁵⁶⁷⁸⁹]',     # ASCII/Unicode上标数字 ( ^1 或 ¹ )
        r'\b(adj|adv|n|v|prep|conj|pron|art|det)\.\s',  # 词性缩写+空格
        r'=\s*$',                # 以等号结尾（释义格式）
        r'/\s*[^\s/]{2,}\s*/',   # IPA斜杠音标 (允许内部空格)
        r'\[\s*[^\s\]]{2,}\s*\]',# 方括号音标 (允许内部空格)
        r"\bnoun\b.*?\bverb\b|\bverb\b.*?\bnoun\b|\badj\b.*?\badv\b",  # 多词性连排
        r"'[a-z]+\s+(noun|verb|adj|adv)\b",   # 引号单词+词性 'computer noun
    ]
    combined_header_re = re.compile('|'.join(DICT_HEADER_PATTERNS))

    for s in sentences:
        clean_s = clean_sentence_text(s)

        # === 基础过滤 ===
        # 1. 长度适中 (15-300字符)
        if len(clean_s) < 15 or len(clean_s) > 300:
            continue

        # 2. 必须包含目标词
        if not pattern.search(clean_s):
            continue

        # 3. 排除词典词条头
        if combined_header_re.search(clean_s):
            logger.debug(f"[{target_word}] 词条头排除: {clean_s[:60]}")
            continue

        # 4. 至少包含3个单词
        words = clean_s.split()
        if len(words) < 3:
            logger.debug(f"[{target_word}] 词数不足({len(words)}): {clean_s[:60]}")
            continue

        # 5. 英文字符占比检查 — 英文模式 >50%
        eng_chars = sum(1 for c in clean_s if 'a' <= c.lower() <= 'z' or c == ' ')
        ratio = eng_chars / len(clean_s)
        
        if target_is_eng and ratio < 0.50:
            logger.debug(f"[{target_word}] 英文比例低({ratio:.2f}): {clean_s[:60]}")
            split_by_dot = clean_s.split('.')
            if len(split_by_dot) > 1:
                potential = split_by_dot[0] + "."
                if pattern.search(potential) and len(potential) >= 15:
                    p_words = potential.split()
                    if len(p_words) >= 3:
                        valid_sentences.append(potential)
            continue

        valid_sentences.append(clean_s)

    if not valid_sentences:
        logger.debug(f"无法为 '{target_word}' 生成有效句子 (共扫描 {len(sentences)} 段)")
        return None

    # 选择最短的有效句子（通常更清晰）
    valid_sentences.sort(key=len)
    chosen_sentence = valid_sentences[0] if len(valid_sentences) < 3 else random.choice(valid_sentences[:3])

    # 挖空目标词
    masked_sentence = pattern.sub("________", chosen_sentence)

    # 获取干扰项（传入目标词长度用于长度相似性筛选）
    options = get_random_words(
        3, target_word, target_is_english=target_is_eng, target_len=len(target_word)
    )
    options.append(target_word)
    random.shuffle(options)

    return {
        "type": "quiz",
        "question": masked_sentence,
        "options": options,
        "answer": target_word,
        "origin": chosen_sentence,
        "dict_name": dict_name or "未知词典"
    }
