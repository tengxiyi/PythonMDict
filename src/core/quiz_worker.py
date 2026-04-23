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
        # 获取单词内容
        content = None
        try:
            with sqlite3.connect(DB_FILE) as conn:
                if self.dict_id:
                    row = conn.execute(
                        "SELECT content FROM standard_entries WHERE word=? AND dict_id=?",
                        (self.word, self.dict_id)
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT content FROM standard_entries WHERE word=? LIMIT 1",
                        (self.word,)
                    ).fetchone()
                
                if row:
                    content = row[0]
        except Exception as e:
            logger.error(f"获取测验词条失败({self.word}): {e}")

        if not content:
            self.data_ready.emit(None)
            return

        # 生成测验
        try:
            result = generate_quiz_data((self.word, content))
            self.data_ready.emit(result)
        except Exception as e:
            logger.error(f"测验生成失败({self.word}): {e}", exc_info=True)
            self.data_ready.emit(None)


def get_random_words(count: int = 3, exclude_word: str = "", target_is_english: bool = True) -> list[str]:
    """
    从数据库随机获取干扰项单词
    
    Args:
        count: 需要的干扰项数量
        exclude_word: 要排除的目标单词
        target_is_english: 是否需要纯英文干扰项（与目标词语言一致）
        
    Returns:
        干扰项单词列表
    """
    candidates = []
    attempts = 0
    max_attempts = 20

    try:
        with sqlite3.connect(DB_FILE) as conn:
            while len(candidates) < count and attempts < max_attempts:
                cursor = conn.execute(
                    "SELECT word FROM standard_entries WHERE word != ? ORDER BY RANDOM() LIMIT 10",
                    (exclude_word,)
                )
                rows = cursor.fetchall()

                for r in rows:
                    w = r[0]
                    # 过滤条件
                    if len(w) > 20 or len(w) < 2:
                        continue

                    if target_is_english:
                        if is_pure_english(w) and w not in candidates:
                            candidates.append(w)
                    else:
                        if w not in candidates:
                            candidates.append(w)

                    if len(candidates) >= count:
                        break

                attempts += 1

        # 兜底备用词
        if len(candidates) < count:
            backups = ["Apple", "Banana", "Cherry", "Date", "Elderberry"]
            for b in backups:
                if b not in candidates and b != exclude_word:
                    candidates.append(b)
                if len(candidates) >= count:
                    break

        return candidates[:count]

    except Exception as e:
        logger.warning(f"获取随机单词失败: {e}")
        return ["Option A", "Option B", "Option C"]


def generate_quiz_data(args: tuple) -> dict | None:
    """
    生成测验数据的任务函数
    
    Args:
        args: (word, content_blob) 元组
        
    Returns:
        包含测验题目的字典，格式：
        {
            "type": "quiz",
            "question": "挖空后的句子",
            "options": [选项A, 选项B, 选项C, 选项D],
            "answer": "正确答案",
            "origin": "原始完整句子"
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

    for s in sentences:
        clean_s = clean_sentence_text(s)

        # 筛选有效句子：
        # 1. 包含目标词
        # 2. 长度适中 (20-200字符)
        # 3. 主要由英文字符组成（>70%）
        if 20 < len(clean_s) < 200:
            if pattern.search(clean_s):
                eng_chars = sum(1 for c in clean_s if 'a' <= c.lower() <= 'z' or c == ' ')
                ratio = eng_chars / len(clean_s)

                if ratio > 0.7:
                    valid_sentences.append(clean_s)
                else:
                    # 尝试提取英文部分（双语对照情况）
                    split_by_dot = clean_s.split('.')
                    if len(split_by_dot) > 1:
                        potential = split_by_dot[0] + "."
                        if pattern.search(potential) and len(potential) > 20:
                            valid_sentences.append(potential)

    if not valid_sentences:
        logger.debug(f"无法为 '{target_word}' 生成有效句子")
        return None

    # 选择最短的有效句子（通常更清晰）
    valid_sentences.sort(key=len)
    chosen_sentence = valid_sentences[0] if len(valid_sentences) < 3 else random.choice(valid_sentences[:3])

    # 挖空目标词
    masked_sentence = pattern.sub("________", chosen_sentence)

    # 获取干扰项
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
