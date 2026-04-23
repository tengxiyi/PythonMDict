import React, { useEffect, useState, useRef } from 'react';
import './HomePage.css';

type Word = { id: string; text: string };
type Definition = { word: string; pos?: string; meanings: string[]; examples?: string[] };

// Seed hot words used for initial render
const seedHotWords: Word[] = [
  { id: 'w1', text: 'apple' },
  { id: 'w2', text: 'book' },
  { id: 'w3', text: 'dictionary' },
  { id: 'w4', text: 'grammar' },
  { id: 'w5', text: 'language' },
];

// Mock definition fetcher (replace with real API/backend in production)
function fetchDefinition(word: string): Promise<Definition> {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        word,
        pos: 'n./v.',
        meanings: [`Definition of ${word} - meaning 1`, `Definition of ${word} - meaning 2`],
        examples: [`This is an example sentence with ${word}.`],
      });
    }, 350);
  });
}

const HomePage: React.FC = () => {
  const [isLoading, setLoading] = useState(true);
  const [hotWords, setHotWords] = useState<Word[]>([]);
  const [selectedWord, setSelectedWord] = useState<Word | null>(null);
  const [definitions, setDefinitions] = useState<Definition | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const searchRef = useRef<HTMLInputElement | null>(null);

  // Initialization: seed data and first definition
  useEffect(() => {
    // Skeleton loading state while seed data renders
    setLoading(true);
    // Load seed words (could be replaced by API fetch)
    setHotWords(seedHotWords);
    const first = seedHotWords[0] ?? null;
    setSelectedWord(first);
    if (first) {
      fetchDefinition(first.text).then((def) => {
        setDefinitions(def);
        setLoading(false);
      });
    } else {
      setLoading(false);
    }

    // Restore recent searches from localStorage
    try {
      const r = localStorage.getItem('gd_recent') ?? '[]';
      setRecent(JSON.parse(r));
    } catch {
      setRecent([]);
    }

    // Quick search focus on '/'
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && (document.activeElement as HTMLElement)?.tagName !== 'INPUT') {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // When selected word changes, fetch its definition and update recent list
  useEffect(() => {
    if (!selectedWord) return;
    const w = selectedWord.text;
    // update recent list
    const nextRecent = [w, ...recent.filter((x) => x !== w)].slice(0, 8);
    setRecent(nextRecent);
    try {
      localStorage.setItem('gd_recent', JSON.stringify(nextRecent));
    } catch {
      // ignore storage errors
    }
    // load definition
    setLoading(true);
    fetchDefinition(w).then((def) => {
      setDefinitions(def);
      setLoading(false);
    });
  }, [selectedWord?.text]);

  const onChooseWord = (w: Word) => setSelectedWord(w);

  const onSearchSubmit = (text: string) => {
    const found = hotWords.find((w) => w.text.toLowerCase() === text.toLowerCase());
    if (found) {
      setSelectedWord(found);
    } else {
      const newWord: Word = { id: `custom-${text}`, text };
      setHotWords([newWord, ...hotWords]);
      setSelectedWord(newWord);
    }
  };

  return (
    <div className="gd-home-root" aria-label="GeekDictionary 首页">
      <div className="gd-home-layout">
        {/* 左侧：词条列表与快速搜索 */}
        <aside className="gd-home-list" aria-label="词条列表">
          <div className="gd-home-list__toolbar">
            <input
              ref={searchRef}
              className="gd-home-search"
              placeholder="搜索一个单词，按 Enter 确认"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onSearchSubmit((e.target as HTMLInputElement).value);
                  (e.target as HTMLInputElement).value = '';
                }
              }}
            />
          </div>
          <div className="gd-home-list__body">
            {hotWords.length === 0 && isLoading ? (
              <div className="gd-skeleton-list" aria-label="加载中">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="gd-skeleton-item" />
                ))}
              </div>
            ) : (
              <ul className="gd-word-items" role="listbox" aria-label="热门词汇">
                {hotWords.map((w) => (
                  <li
                    key={w.id}
                    className={selectedWord?.id === w.id ? 'gd-word-item gd-word-item--selected' : 'gd-word-item'}
                    onClick={() => onChooseWord(w)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') onChooseWord(w);
                    }}
                  >
                    {w.text}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="gd-home-empty" style={{ display: hotWords.length ? 'none' : 'block' }}>
            <p>空状态：输入一个词汇开始搜索。</p>
            <button onClick={() => setHotWords(seedHotWords)}>加载示例词</button>
          </div>
        </aside>

        {/* 右侧：释义区域与最近搜索 */}
        <section className="gd-home-definition" aria-label="释义区域">
          <div className="gd-definition-header">
            {selectedWord ? `释义：${selectedWord.text}` : '请选择一个词条查看释义'}
          </div>
          {isLoading || !definitions ? (
            <div className="gd-skeleton-definition" />
          ) : (
            <div className="gd-definition-content">
              <div className="gd-definition-pos">{definitions.pos ?? ''}</div>
              <ul className="gd-definition-meanings">
                {definitions.meanings.map((m, idx) => (
                  <li key={idx}>{m}</li>
                ))}
              </ul>
              {definitions.examples?.length ? (
                <div className="gd-definition-examples">
                  <strong>例句:</strong>
                  <ul>
                    {definitions.examples!.map((ex, i) => (
                      <li key={i}>{ex}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
          <div className="gd-definition-recent" aria-label="最近搜索">
            <h4>最近搜索</h4>
            {recent.length === 0 ? (
              <p>无最近记录</p>
            ) : (
              <div className="gd-chips">
                {recent.map((r, i) => (
                  <button key={i} className="gd-chip" onClick={() => setSelectedWord({ id: `recent-${i}`, text: r })}>
                    {r}
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default HomePage;
