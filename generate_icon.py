# file: generate_icon.py
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os


def create_pro_icon():
    # 画布大小
    W, H = 256, 256
    size = (W, H)

    # 1. 创建背景 (透明)
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 2. 绘制圆角矩形 (背景)
    # 撑满画布，不留边距
    margin = 0
    rect_coords = [margin, margin, W - margin, H - margin]

    # 圆角半径
    radius = 55
    primary_color = (0, 120, 215, 255)  # 极客蓝

    draw.rounded_rectangle(rect_coords, radius=radius, fill=primary_color)

    # 3. 绘制文字 "G"
    try:
        # [修改 1] 字号加大：从 200 -> 220
        # 这会让 G 显得非常有张力
        font_path = "arialbd.ttf"
        font = ImageFont.truetype(font_path, 220)
    except:
        font = ImageFont.load_default()

    text = "G"

    # 获取文字大小
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_width = right - left
    text_height = bottom - top

    # 居中计算
    x = (W - text_width) / 2

    # [修改 2] 垂直修正
    # 字体变大后，物理高度变高，计算出的 y 会自动变小(更靠上)。
    # 结合之前觉得"偏靠下"的问题，我们维持 -35 的修正，这会把 G 字再往上提一点，
    # 抵消大写字母 G 视觉重心偏低的问题。
    y = (H - text_height) / 2 - 35

    # 绘制文字阴影
    draw.text((x + 5, y + 5), text, font=font, fill=(0, 0, 0, 40))
    # 绘制文字主体 (白色)
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    # 4. 保存
    img.save("app_icon.png")
    img.save("app_icon.ico", format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

    print("✅ 最终版图标已生成 (Size 220): app_icon.png 和 app_icon.ico")


if __name__ == "__main__":
    create_pro_icon()