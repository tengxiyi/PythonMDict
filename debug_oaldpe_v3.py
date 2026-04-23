# -*- coding: utf-8 -*-
"""
深度诊断脚本：分析OALDPE按钮不工作的根本原因
1. 正确解压数据库中的词条内容
2. 分析oaldpe.js的齿轮按钮注入机制  
3. 检查CSS样式是否被正确应用
4. 生成独立测试HTML文件供浏览器验证
"""
import os, sys, sqlite3, zlib, re, html as html_lib

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(PROJECT_ROOT, "dict_cache.db")
os.chdir(PROJECT_ROOT)


def get_dict_info(did=4):
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute("SELECT id, name, path FROM dict_info WHERE id=?", (did,)).fetchone()
    conn.close()
    return row


def get_entry_raw(dict_id, word=None):
    """获取原始词条（可能是压缩的bytes）"""
    conn = sqlite3.connect(DB_FILE)
    if word:
        row = conn.execute("SELECT word, content FROM standard_entries WHERE dict_id=? AND word=?", (dict_id, word)).fetchone()
    else:
        row = conn.execute("SELECT word, content FROM standard_entries WHERE dict_id=? LIMIT 1", (dict_id,)).fetchone()
    conn.close()
    return row


def try_decompress(data):
    """尝试多种方式解压/解码数据"""
    results = {}
    
    # 方式1: 直接是zlib压缩
    try:
        dec = zlib.decompress(data).decode('utf-8', 'ignore')
        if len(dec) > 20:
            results['zlib'] = dec
    except Exception as e:
        results['zlib_error'] = str(e)
    
    # 方式2: 可能是gzip
    import gzip
    try:
        dec = gzip.decompress(data).decode('utf-8', 'ignore')
        if len(dec) > 20:
            results['gzip'] = dec
    except:
        pass
    
    # 方式3: 已经是文本
    try:
        text = data.decode('utf-8', 'ignore')
        if '<' in text or '>' in text or '{' in text:
            results['text_utf8'] = text
    except:
        pass
    
    try:
        text = data.decode('gbk', 'ignore')
        if '<' in text or '>' in text:
            results['text_gbk'] = text
    except:
        pass
    
    return results


def analyze_js(js_path):
    """分析JS中齿轮按钮相关逻辑"""
    print("\n" + "=" * 70)
    print(f"JS文件分析: {os.path.basename(js_path)}")
    print("=" * 70)
    
    with open(js_path, 'r', encoding='utf-8', errors='ignore') as f:
        js_content = f.read()
    
    print(f"总大小: {len(js_content)} 字符")
    
    # 搜索齿轮按钮相关代码
    patterns = [
        ('config-gear|config_gear|gear.*button|gear.*click', '齿轮按钮创建/绑定'),
        ('hover|mouseenter|mouseover', '鼠标悬停事件'),
        ('\.body|__body|popup|panel|menu', '弹出面板'),
        ('\$\(|jQuery|document\.ready|DOMContentLoaded', 'DOM就绪/jQuery初始化'),
        ('createElement|innerHTML|append|insertBefore|prepend', 'DOM操作(动态注入)'),
        ('visibility|display|show|hide|toggle', '显示隐藏控制'),
        ('pron|audio|speak|发音', '发音功能'),
        ('traditional|simplified|简繁', '简繁转换'),
        (':hover', 'CSS hover引用'),
    ]
    
    all_found = []
    for regex, desc in patterns:
        matches = list(re.finditer(regex, js_content, re.I))
        if matches:
            all_found.append((desc, len(matches)))
            print(f"\n--- {desc} ({len(matches)}处) ---")
            for m in matches[:5]:
                start = max(0, m.start() - 100)
                end = min(len(js_content), m.end() + 100)
                context = js_content[start:end].replace('\n', '\\n')
                print(f"  ...{context}...")
    
    # 搜索完整的齿轮按钮创建函数（更大上下文）
    gear_creations = list(re.finditer(r'.{0,300}config.?gear.{0,300}', js_content, re.I))
    if gear_creations:
        print(f"\n{'='*50}")
        print("齿轮按钮完整创建代码片段:")
        print('='*50)
        for i, gc in enumerate(gear_creations[:3]):
            print(f"\n--- 片段[{i}] ---")
            print(js_content[gc.start():gc.end()])
    
    return js_content


def analyze_css(css_path):
    """分析CSS中齿轮按钮相关样式"""
    print("\n" + "=" * 70)
    print(f"CSS文件分析: {os.path.basename(css_path)}")
    print("=" * 70)
    
    with open(css_path, 'r', encoding='utf-8', errors='ignore') as f:
        css_content = f.read()
    
    print(f"总大小: {len(css_content)} 字符")
    
    # 查找所有与齿轮相关的完整规则块
    print(f"\n--- 齿轮按钮完整CSS规则 ---")
    # 匹配包含 config-gear 的整个CSS规则
    gear_rules = re.findall(
        r'[^{}]*config.gear[^{]*\{[^}]+\}',
        css_content, re.I | re.DOTALL
    )
    for i, rule in enumerate(gear_rules):
        print(f"\n规则[{i}] ({len(rule)}字符):")
        print(rule.strip())
    
    if not gear_rules:
        # 尝试更宽松匹配
        gear_rules2 = re.findall(
            r'[^{}]*\boaldpe\b.{0,200}\{[^}]+\}',
            css_content, re.I | re.DOTALL
        )
        print(f"  未找到config-gear规则，尝试oaldpe相关规则({len(gear_rules2)}个)")
        for r in gear_rules2[:10]:
            print(f"\n{r.strip()[:300]}...")
    
    # 检查 :hover 相关
    hovers = re.findall(r'.{0,80}:hover.{0,150}\{[^}]+\}', css_content, re.DOTALL | re.I)
    gear_hovers = [h for h in hovers if 'gear' in h.lower() or 'config' in h.lower()]
    print(f"\n--- 齿轮相关的:hover 规则 ({len(gear_hovers)}) ---")
    for h in gear_hovers:
        print(h.strip())
    
    return css_content


def generate_test_html(oaldpe_css, oaldpe_js, jq_js, entry_html, output_path):
    """
    生成独立的测试HTML文件，可以在浏览器中直接打开验证
    """
    test_html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>OALDPE Button Test</title>
<style>
/* 基础容器样式（模拟app环境） */
body {{ margin: 20px; font-family: 'Segoe UI', sans-serif; background: #f5f5f5; }}
.entry-content {{ 
    background: white; 
    padding: 25px; 
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    max-width: 800px;
    margin: 20px auto;
    overflow: visible !important;  /* 关键：不能hidden */
    position: relative;
}}
/* ====== OALDPE原始CSS ====== */
{oaldpe_css}
</style>

<!-- 先加载jQuery -->
<script>
{jq_js}
</script>

<!-- 再加载OALDPE JS -->
<script>
{oaldpe_js}
</script>
</head><body>
<h2>测试：OALDPE齿轮按钮</h2>
<p>如果齿轮按钮出现并能正常悬停弹出面板，说明CSS/JS本身没问题。</p>
<p>如果不能，需要进一步排查。</p>

<!-- 词条内容 -->
<div class="entry-content">
{entry_html}
</div>

<!-- 调试信息 -->
<div id="debug" style="margin-top:30px;padding:15px;background:#fff;border-radius:8px;">
    <h3>调试信息</h3>
    <pre id="debug-output">加载中...</pre>
</div>

<script>
// 调试：检测齿轮按钮是否存在
setTimeout(function() {{
    var info = [];
    
    // 检测jQuery
    info.push('jQuery存在: ' + (typeof jQuery !== 'undefined'));
    
    // 检测齿轮按钮元素
    var gears = document.querySelectorAll('[class*="gear"], [class*="config"]');
    info.push('齿轮相关元素数量: ' + gears.length);
    gears.forEach(function(el, i) {{
        info.push('  ['+i+'] tag='+el.tagName+' class='+el.className+' visible='+window.getComputedStyle(el).display);
    }});
    
    // 检测oaldpe容器
    var oaldpes = document.querySelectorAll('.oaldpe');
    info.push('.oaldpe容器: ' + oaldpes.length);
    
    // 检查img
    var imgs = document.querySelectorAll('img');
    info.push('图片数量: ' + imgs.length);
    
    document.getElementById('debug-output').textContent = info.join('\\n');
}}, 1500);
</script>
</body></html>'''
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(test_html)
    print(f"\n测试HTML已生成: {output_path}")
    print(f"请用浏览器打开此文件验证按钮是否工作！")


def main():
    print("=" * 70)
    print("  OALDPE 深度诊断 v3")
    print("=" * 70)
    
    info = get_dict_info(4)  # oaldpe
    did, dname, path = info
    print(f"\n词典: {dname} (id={did})")
    print(f"路径: {path}")
    
    base = os.path.splitext(path)[0]
    css_file = base + ".css"
    js_file = base + ".js"
    jq_file = base + "-jquery.js"
    
    # 1. 分析JS
    oaldpe_js = ""
    if os.path.exists(js_file):
        oaldpe_js = analyze_js(js_file)
    else:
        print(f"\n!!! JS文件不存在: {js_file}")
    
    # 2. 分析CSS
    oaldpe_css = ""
    if os.path.exists(css_file):
        oaldpe_css = analyze_css(css_file)
    else:
        print(f"\n!!! CSS文件不存在: {css_file}")
    
    # 3. 正确解压一个词条
    print(f"\n{'#'*70}")
    print("# 词条内容解压分析")
    print('#'*70)
    
    for w in ['hello', 'the', 'a']:
        entry = get_entry_raw(did, w)
        if entry:
            word = entry[0]
            raw_content = entry[1]
            print(f"\n词条: '{word}' (raw type={type(raw_content).__name__}, size={len(raw_content) if raw_content else 0})")
            
            if raw_content:
                results = try_decompress(raw_content)
                for method, content in results.items():
                    if isinstance(content, str) and len(content) > 10:
                        print(f"\n  [{method}] 解码成功! 长度={len(content)}")
                        # 显示前2000字符
                        print(f"  内容预览:\n{content[:2000]}")
                        
                        # 检查是否包含齿轮/oaldpe相关标记
                        if 'oaldpe' in content.lower():
                            print(f"  *** 包含'oaldpe'标记! ***")
                        if 'config-gear' in content.lower():
                            print(f"  *** 包含'config-gear'标记! ***")
                        if 'gear' in content.lower():
                            print(f"  *** 包含'gear'标记! ***")
                    elif isinstance(content, str):
                        print(f"  [{method}] 结果太短或为空")
                    else:
                        print(f"  [{method}] 错误: {content}")
                
                if not results.get('zlib') and not results.get('text_utf8'):
                    # 显示原始字节的前200字符（hex）
                    raw_preview = raw_content[:100]
                    print(f"  所有解码方式均失败!")
                    print(f"  前100字节(hex): {raw_preview.hex()}")
                    print(f"  前100字节(raw): {raw_preview}")
            
            break
    
    # 4. 读取jQuery
    jq_content = ""
    if os.path.exists(jq_file):
        with open(jq_file, 'r', encoding='utf-8', errors='ignore') as f:
            jq_content = f.read()
        print(f"\njQuery文件: {os.path.basename(jq_file)} ({len(jq_content)}字符)")
        # 确认是真正的jQuery
        if 'jQuery' in jq_content or '$' in jq_content[:500]:
            print("  确认: 是jQuery库")
        else:
            print("  !!! 警告: 可能不是标准jQuery !!!")
            print(f"  前500字符:\n{jq_content[:500]}")
    else:
        print(f"\n!!! jQuery文件不存在: {jq_file}")
    
    # 5. 生成测试HTML（如果有足够的内容）
    test_output = os.path.join(PROJECT_ROOT, "_test_oaldpe_button.html")
    
    # 获取一个解压后的条目作为示例
    sample_entry = "<p>Sample entry content here</p>"
    for w in ['hello', 'test']:
        entry = get_entry_raw(did, w)
        if entry and entry[1]:
            results = try_decompress(entry[1])
            for k, v in results.items():
                if isinstance(v, str) and len(v) > 10 and '<' in v:
                    sample_entry = v
                    break
            if sample_entry != "<p>Sample entry content here</p>":
                break
    
    if oaldpe_css and oaldpe_js:
        # 截取前部分避免文件过大
        css_for_test = oaldpe_css
        js_for_test = oaldpe_js
        jq_for_test = jq_content
        
        # 如果文件太大，截断
        MAX_CSS = 500000
        MAX_JS = 300000
        if len(css_for_test) > MAX_CSS:
            css_for_test = css_for_test[:MAX_CSS] + "\n/* truncated */"
        if len(js_for_test) > MAX_JS:
            js_for_test = js_for_test[:MAX_JS] + "\n// truncated"
        
        generate_test_html(css_for_test, js_for_test, jq_for_test, sample_entry, test_output)
    else:
        print(f"\n无法生成测试HTML（缺少CSS或JS文件）")


if __name__ == "__main__":
    main()
