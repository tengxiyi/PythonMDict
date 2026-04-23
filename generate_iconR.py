from PIL import Image, ImageDraw, ImageFont
import os


def create_pro_icon():
    # 画布大小
    W, H = 256, 256
    size = (W, H)

    # 1. 创建背景 (透明)
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 2. 绘制圆角矩形 (背景)
    margin = 0
    rect_coords = [margin, margin, W - margin, H - margin]

    # 圆角半径
    radius = 55
    # 修改为绿色背景：推荐使用 (46, 139, 87) 森林绿 或 (39, 174, 96) 翡翠绿
    primary_color = (39, 174, 96, 255)

    draw.rounded_rectangle(rect_coords, radius=radius, fill=primary_color)

    # 3. 绘制文字 "D"
    try:
        # 使用粗体 Arial
        font_path = "arialbd.ttf"
        font = ImageFont.truetype(font_path, 200)  # D 字母较宽，建议比 G 略小一点点防止顶格
    except:
        font = ImageFont.load_default()

    text = "D"

    # 获取文字大小
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_width = right - left
    text_height = bottom - top

    # 居中计算
    x = (W - text_width) / 2

    # 垂直修正：D 的结构比较稳重，垂直修正设为 -25 即可达到视觉居中
    y = (H - text_height) / 2 - 25

    # 绘制文字阴影 (淡淡的深绿阴影)
    draw.text((x + 4, y + 4), text, font=font, fill=(0, 60, 30, 60))
    # 绘制文字主体 (白色)
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    # 4. 保存
    img.save("app_icon.png")
    # ICO 会自动包含多种尺寸，方便 Windows 系统在不同视图下调用
    img.save("app_icon.ico", format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

    print("✅ 绿色版 D 图标已生成: app_icon.png 和 app_icon.ico")


if __name__ == "__main__":
    create_pro_icon()