# -*- coding: utf-8 -*-
"""把單一尺寸的 .ico 補成 Windows 標準多尺寸 .ico（回報中心 #43・icon 畫質）。

為什麼需要：
    Windows 在開始選單／工作列／檔案總管顯示 16～48px 的圖示。若 .ico 內只有
    一張 256×256，系統得自己即時降階，小尺寸就會出現鋸齒與糊邊——這正是
    回報中心 #43 反映的「icon 畫質不佳」。標準做法是把各尺寸預先算好放進 .ico。

紀律（CIS）：
    只做「同一張圖的等比縮放」，用 Pillow 的 LANCZOS 確定性重取樣，
    **不重畫、不生成、不改色**。圖案本身要換是另一件事，不在本工具範圍。

用法：
    python tools/ping/make_multisize_ico.py                # 處理預設清單
    python tools/ping/make_multisize_ico.py <ico> [<ico>…]  # 指定檔案
"""
import os
import sys

from PIL import Image

# Windows 標準圖示尺寸（含高 DPI 會用到的 40/64/96）
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_TARGETS = [
    os.path.join(REPO, "resources", "images", "OrcaSlicer.ico"),       # exe 內嵌（OrcaSlicer.rc.in:24）
    os.path.join(REPO, "resources", "images", "OrcaSlicerTitle.ico"),  # 對話框標題列圖示
]


def rebuild(path):
    im = Image.open(path)
    src = im.convert("RGBA")
    if src.size[0] != src.size[1]:
        raise SystemExit("來源不是正方形：%s %s" % (path, src.size))
    if src.size[0] < max(SIZES):
        raise SystemExit("來源解析度不足 %dpx：%s %s" % (max(SIZES), path, src.size))

    frames = [src.resize((s, s), Image.LANCZOS) for s in SIZES if s < src.size[0]]
    before = os.path.getsize(path)
    # append_images 讓每個尺寸都是我們算好的圖，而不是交給 Pillow 自己縮
    src.save(path, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames)
    after = os.path.getsize(path)
    print("%-24s %s -> %d 種尺寸 %s  (%d KB -> %d KB)"
          % (os.path.basename(path), src.size, len(SIZES), SIZES, before // 1024, after // 1024))


if __name__ == "__main__":
    targets = sys.argv[1:] or DEFAULT_TARGETS
    for t in targets:
        rebuild(t)
