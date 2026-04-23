# file: src/core/analyzer_worker.py
# -*- coding: utf-8 -*-
"""
词频分析工作线程
支持文本/HTML输入，提取高频词汇并过滤停用词，附带词性标注
"""
import re
import sqlite3
from collections import Counter

from PySide6.QtCore import QThread, Signal

from .config import DB_FILE
from .utils import STOP_WORDS
from .logger import logger

# 词性标签中文映射 (NLTK Penn Treebank -> 中文)
POS_TAG_MAP = {
    'CC': '连词',     # coordinating conjunction
    'CD': '数词',     # cardinal number
    'DT': '限定词',   # determiner
    'EX': '存在词',   # existential there
    'FW': '外来词',   # foreign word
    'IN': '介词',     # preposition/subordinating conjunction
    'JJ': '形容词',   # adjective
    'JJR': '比较级',  # adjective, comparative
    'JJS': '最高级',  # adjective, superlative
    'LS': '列表符',  # list item marker
    'MD': '情态动词', # modal
    'NN': '名词',     # noun, singular
    'NNS': '名词复',  # noun plural
    'NP': '专有名词',  # proper noun, singular
    'NPS': '专有复',  # proper noun plural
    'PDT': '前指定语', # predeterminer
    'POS': '所有格结尾', # possessive ending
    'PRP': '代词',    # personal pronoun
    'PRP$': '物主代', # possessive pronoun
    'RB': '副词',     # adverb
    'RBR': '副比较',  # adverb, comparative
    'RBS': '副最高',  # adverb, superlative
    'RP': '小品词',  # particle
    'SYM': '符号',    # symbol
    'TO': 'to',       # to
    'UH': '感叹词',   # interjection
    'VB': '动词原形', # verb, base form
    'VBD': '动词过去', # verb, past tense
    'VBG': '动名词',  # verb, gerund/present participle
    'VBN': '过去分词', # verb, past participle
    'VBP': '非三人称', # verb, non-3rd person singular present
    'VBZ': '三单现',  # verb, 3rd person singular present
    'WDT': 'Wh限定词', # wh-determiner
    'WP': 'Wh代词',   # wh-pronoun
    'WP$': 'Wh物主',  # possessive wh-pronoun
    'WRB': 'Wh副词',  # wh-adverb
}

# 后缀启发式规则 (按优先级从高到低)
_SUFFIX_RULES = [
    # 动词变形（最高优先级）
    ('ing$', '动名词'),
    ('ied$', '动词过去'),
    ('ize$', '动词原形'),
    ('ise$', '动词原形'),
    ('ify$', '动词原形'),
    # 副词
    ('ly$', '副词'),
    # 形容词比较/最高级
    ('iest$', '最高级'),
    ('ier$', '比较级'),
    ('est$', '最高级'),
    ('er$', '比较级'),
    ('ish$', '形容词'),
    ('ous$', '形容词'),
    ('ive$', '形容词'),
    ('able$', '形容词'),
    ('ible$', '形容词'),
    ('al$', '形容词'),
    ('ial$', '形容词'),
    ('ful$', '形容词'),
    ('less$', '形容词'),
    ('ent$', '形容词'),
    ('ant$', '形容词'),
    # 名词复数
    ('ses$', '名词复'),
    ('xes$', '名词复'),
    ('zes$', '名词复'),
    ('ches$', '名词复'),
    ('shes$', '名词复'),
    ('men$', '名词复'),
    ('ies$', '名词复'),
    ('ves$', '名词复'),
    ('s$', '名词复'),
    # 名词后缀
    ('ment$', '名词'),
    ('ness$', '名词'),
    ('tion$', '名词'),
    ('sion$', '名词'),
    ('dom$', '名词'),
    ('ity$', '名词'),
    ('ance$', '名词'),
    ('ence$', '名词'),
    ('ship$', '名词'),
    ('hood$', '名词'),
    ('ism$', '名词'),
    ('ist$', '名词'),
    # 名词/动词歧义 - 长度较短的默认为名词
]

# 常见非词汇停用词（纯功能词）
_FUNCTION_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'not', 'no',
    'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'shall',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
    'my', 'your', 'his', 'its', 'our', 'their', 'this', 'that', 'these', 'those',
    'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how',
    'if', 'then', 'than', 'too', 'very', 'just', 'also', 'only',
    'about', 'above', 'after', 'again', 'all', 'am', 'any', 'because',
    'before', 'below', 'between', 'both', 'each', 'few', 'for', 'from',
    'into', 'more', 'most', 'other', 'out', 'over', 'own', 'same', 'so',
    'some', 'such', 'through', 'under', 'until', 'up', 'while',
}

# 常见动词原型（高置信度）
_COMMON_VERBS = {
    'get', 'got', 'make', 'made', 'take', 'took', 'come', 'came', 'go', 'went',
    'see', 'saw', 'know', 'knew', 'think', 'thought', 'want', 'give', 'gave',
    'find', 'found', 'tell', 'told', 'ask', 'work', 'seem', 'feel', 'felt',
    'try', 'leave', 'left', 'call', 'keep', 'kept', 'let', 'begin', 'began',
    'show', 'hear', 'heard', 'play', 'run', 'ran', 'move', 'live', 'believe',
    'hold', 'held', 'bring', 'brought', 'happen', 'write', 'wrote', 'provide',
    'sit', 'sat', 'stand', 'stood', 'lose', 'lost', 'pay', 'paid', 'meet', 'met',
    'include', 'continue', 'set', 'learn', 'change', 'lead', 'led', 'understand',
    'watch', 'follow', 'stop', 'create', 'speak', 'spoke', 'read', 'allow',
    'add', 'spend', 'spent', 'grow', 'grew', 'open', 'walk', 'win', 'won',
    'offer', 'remember', 'love', 'consider', 'appear', 'buy', 'bought', 'wait',
    'serve', 'die', 'died', 'send', 'sent', 'expect', 'build', 'built', 'stay',
    'fall', 'fell', 'cut', 'reach', 'kill', 'remain', 'suggest', 'raise',
    'pass', 'sell', 'sold', 'require', 'report', 'decide', 'pull', 'break',
    'broke',
}


def _pos_by_suffix(word: str) -> str:
    """基于英语后缀规则的启发式词性标注（零依赖回退方案）"""
    w = word.lower()
    if not w or len(w) < 2:
        return '-'

    if w in _FUNCTION_WORDS:
        return '功能词'

    if w in _COMMON_VERBS:
        return '动词'

    for pattern, pos in _SUFFIX_RULES:
        if re.search(pattern, w):
            return pos

    # 无匹配后缀时，根据长度和首字母等特征做简单判断
    # 短词(2-3字母)且元音开头的多为介词/限定词
    if len(w) <= 3 and w[0] in 'aeiou':
        return '名词'
    
    # 默认返回名词（英语中最常见的词性）
    return '名词'


class AnalyzerWorker(QThread):
    """
    词频分析工作线程
    
    Signals:
        progress(int): 分析进度百分比 (0-100)
        analysis_ready(dict): 发送分析结果字典
        error(str): 错误信息
    """
    progress = Signal(int)
    analysis_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, text: str, min_length: int = 3, is_html: bool = False):
        super().__init__()
        self.text = text
        self.min_length = min_length
        self.is_html = is_html

    def run(self):
        text = self.text
        if not text:
            self.analysis_ready.emit({'words': [], 'total_words': 0, 'unique_words': 0})
            return

        try:
            self.progress.emit(10)

            # 清洗文本
            if self.is_html:
                text = re.sub(r'<[^>]+>', ' ', text)

            # 正则分词
            raw_words = re.findall(rf'\b[a-z]{{{self.min_length},}}\b', text.lower())
            total_words = len(raw_words)
            
            self.progress.emit(30)

            # 统计词频
            counter = Counter(raw_words)
            unique_words_before_filter = len(counter.keys())

            # 过滤停用词
            candidates = [w for w in counter.keys() if w not in STOP_WORDS]

            self.progress.emit(50)

            valid_results = []
            has_dictionary = self._check_dictionary_exists()

            if not has_dictionary:
                sorted_candidates = sorted(candidates, key=lambda w: counter[w], reverse=True)
                pos_tags = self._pos_tag_batch(sorted_candidates)
                valid_results = [(w, counter[w], pos_tags.get(w, '-')) for w in sorted_candidates]
            else:
                valid_results = self._verify_with_database(candidates, counter, total_chunks=5)

            self.progress.emit(95)

            limit = 1000
            unique_words = len(valid_results)
            logger.info(f"分析完成: 总词数={total_words}, 不重复词={unique_words}, 有效结果={len(valid_results[:limit])}")

            result_dict = {
                'words': valid_results[:limit],
                'total_words': total_words,
                'unique_words': unique_words,
            }
            self.analysis_ready.emit(result_dict)
            self.progress.emit(100)

        except Exception as e:
            logger.error(f"分析异常: {e}", exc_info=True)
            self.error.emit(f"分析失败: {str(e)}")

    def _pos_tag_batch(self, word_list: list[str]) -> dict[str, str]:
        """对单词列表批量进行词性标注，优先使用NLTK，失败时回退到后缀启发式"""
        if not word_list:
            return {}

        # 方案1: 尝试 NLTK
        try:
            import nltk
            tagged = nltk.pos_tag(word_list)
            logger.info(f"词性标注: 使用NLTK，共{len(tagged)}个词")
            return {
                word: POS_TAG_MAP.get(tag, tag)
                for word, tag in tagged
            }
        except Exception as e:
            logger.info(f"NLTK不可用({e})，回退到后缀启发式标注")

        # 方案2: 无依赖的后缀启发式标注器（基于英语构词法）
        result = {}
        for w in word_list:
            result[w] = _pos_by_suffix(w)
        logger.info(f"词性标注: 使用后缀启发式，共{len(result)}个词")
        return result

    def _check_dictionary_exists(self) -> bool:
        """检查是否有导入的词典数据"""
        try:
            with sqlite3.connect(DB_FILE, timeout=10) as conn:
                check = conn.execute("SELECT 1 FROM standard_entries LIMIT 1").fetchone()
                return check is not None
        except Exception as e:
            logger.warning(f"检查词典数据失败: {e}")
            return False

    def _verify_with_database(self, candidates: list[str], counter: Counter,
                              total_chunks: int = 5) -> list[tuple]:
        """通过数据库验证候选词汇的有效性，附带词性标注"""
        valid_results = []
        chunk_size = 900

        try:
            with sqlite3.connect(DB_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                total_batches = (len(candidates) + chunk_size - 1) // chunk_size
                processed = 0
                valid_words = []

                for i in range(0, len(candidates), chunk_size):
                    batch = candidates[i:i + chunk_size]
                    if not batch:
                        break

                    placeholders = ",".join("?" * len(batch))
                    sql = f"SELECT word FROM standard_entries WHERE word IN ({placeholders}) COLLATE NOCASE"

                    try:
                        cursor.execute(sql, batch)
                        db_words = {r[0].lower() for r in cursor.fetchall()}
                        for w in batch:
                            if w in db_words:
                                valid_words.append(w)
                    except Exception as e:
                        logger.warning(f"批量查询失败 (batch start={i}): {e}")

                    processed += 1
                    # 报告进度：50% ~ 90%
                    self.progress.emit(50 + int(40 * processed / max(total_batches, 1)))

                # 对有效词汇做词性标注
                pos_map = self._pos_tag_batch(valid_words)
                valid_results = [(w, counter[w], pos_map.get(w, '-')) for w in valid_words]

        except Exception as e:
            logger.error(f"数据库连接错误: {e}")

        valid_results.sort(key=lambda x: x[1], reverse=True)
        return valid_results
