# file: inspect_mdd.py
import os
from readmdict import MDD


def inspect_mdd():
    # 让用户输入 mdd 路径
    mdd_path = input("请输入 .mdd 文件的完整路径 (例如 D:\\dict\\test.mdd): ").strip().strip('"')

    if not os.path.exists(mdd_path):
        print(f"❌ 文件不存在: {mdd_path}")
        return

    print("-" * 60)
    print(f"🔍 正在侦查: {os.path.basename(mdd_path)}")
    print("-" * 60)

    try:
        mdd = MDD(mdd_path)
        count = 0
        for k_bytes, _ in mdd.items():
            count += 1
            if count > 20: break  # 只看前20个，避免刷屏

            print(f"[{count}] 原始 Bytes: {k_bytes}")

            # 尝试 UTF-8
            try:
                u_str = k_bytes.decode('utf-8')
                print(f"    ✅ UTF-8 解码: {u_str}")
            except:
                print(f"    ❌ UTF-8 失败")

            # 尝试 GBK (关键！)
            try:
                g_str = k_bytes.decode('gbk')
                print(f"    ✅ GBK   解码: {g_str}")
            except:
                print(f"    ❌ GBK   失败")

            # 尝试 UTF-16 (少见但存在)
            try:
                u16_str = k_bytes.decode('utf-16')
                print(f"    ✅ UTF-16 解码: {u16_str}")
            except:
                pass

            print("-" * 20)

    except Exception as e:
        print(f"❌ 读取错误: {e}")


if __name__ == "__main__":
    inspect_mdd()