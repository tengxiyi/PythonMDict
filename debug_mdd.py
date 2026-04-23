import os
import sys

try:
    from readmdict import MDD
except ImportError:
    print("❌ 请先安装依赖: pip install readmdict")
    sys.exit(1)


def inspect_mdd(mdd_path):
    if not os.path.exists(mdd_path):
        print(f"❌ 文件不存在: {mdd_path}")
        return

    print(f"\n🔍 正在分析: {os.path.basename(mdd_path)} ...")

    try:
        head_mdd = MDD(mdd_path)
        print(f"✅ 读取成功! 共包含 {len(head_mdd)} 个资源文件。")

        print("\n--- 🕵️‍♂️ 抽样前 50 个 Key (内部路径) ---")
        # readmdict 的 key 通常是 bytes，我们需要解码看看
        count = 0
        sample_keys = []
        for key in head_mdd.keys():
            try:
                # 尝试解码，通常是 utf-8 或 gbk，readmdict 默认处理 bytes
                key_str = key.decode('utf-8', 'ignore')
            except:
                key_str = str(key)

            print(f"[{count + 1}] Raw: {key}  |  Decoded: {key_str}")
            sample_keys.append(key)

            count += 1
            if count >= 50:
                break

        print("\n--- 🧪 模拟匹配测试 ---")
        while True:
            user_input = input("\n请输入一个你在 HTML 源码中看到的图片路径 (输入 q 退出): ").strip()
            if user_input.lower() == 'q':
                break

            # 模拟我们在 main.py 中的几种猜测逻辑
            candidates = [
                user_input,
                user_input.replace('/', '\\'),  # 换成反斜杠
                '\\' + user_input.replace('/', '\\'),  # 加根反斜杠
                user_input.strip('/\\'),  # 去头去尾
                user_input.lower(),  # 全小写
            ]

            found = False
            for cand in candidates:
                # readmdict 接受 bytes 或 str 作为 key
                # 我们尝试把猜测的路径转为 bytes 查找
                cand_bytes = cand.encode('utf-8')

                if cand_bytes in head_mdd:
                    print(f"✅ 匹配成功! 对应 Key 为: {cand_bytes}")
                    found = True
                    break

                # 有些老词典可能是 gbk
                try:
                    cand_gbk = cand.encode('gbk')
                    if cand_gbk in head_mdd:
                        print(f"✅ 匹配成功 (GBK)! 对应 Key 为: {cand_gbk}")
                        found = True
                        break
                except:
                    pass

            if not found:
                print("❌ 未找到。请对比上面的 Sample Keys，看看斜杠方向或大小写有什么区别。")

    except Exception as e:
        print(f"❌ 读取出错: {e}")


if __name__ == "__main__":
    # 让用户选择文件
    import tkinter as tk
    from tkinter import filedialog

    print("请在弹出的窗口中选择一个 .mdd 文件...")
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(filetypes=[("MDD Files", "*.mdd")])

    if file_path:
        inspect_mdd(file_path)
    else:
        print("未选择文件。")