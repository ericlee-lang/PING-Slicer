# -*- coding: utf-8 -*-
"""產生 PING 床貼圖（SVG）＋更新 logo 裁切閘門的墨跡 fixture。

起因＝回報中心 #112「拉大看模型時底圖 LOGO 邊緣不銳利」，Eric 2026-09-07 裁「甲」。

**為什麼是 SVG**：查下來不是原圖解析度不夠（舊 PNG 3192×3191、墨跡帶 2297×489，
放大三倍邊緣仍銳利），而是點陣圖在 3D 視角拉近時本來就會被放大。引擎支援 SVG
（`3DBed.cpp:501` 走 `load_from_svg_file(..., max_tex_size)`，另有 `svg_source` uniform）
⇒ 換向量後縮放不再受解析度限制。而且這張貼圖**整張只有 LOGO**（其餘全透明）、
純平色無漸層，天生就適合向量。

🔴 **CIS 鐵則：Logo 不可 AI 生成或重畫。** 本工具**完全不碰路徑資料**，只做三件確定性的事：
  ① 把 `resources/images/OrcaSlicer.svg` 的內容原封搬進新畫布（外包一層 transform 縮放置中）
  ② 換畫布尺寸／viewBox（沿用舊 PNG 的 3192×3191，讓 UV 映射不變）
  ③ 顏色校正到 CIS 正色——舊資產三種橘（床 #E2532E／SVG 原檔 #d24d21）沒有一個是正色

關門版＝主版**只改垂直位移**（Eric 2026-08-11 裁「只平移不重畫」，17mm ≒ 217px）。
以前是 `make_closeddoor_texture.py` 用 PIL 搬像素，改 SVG 之後只要改 transform 的 ty，
更精確也更簡單 ⇒ 那支已標示退役。

**墨跡 fixture**：`verify_profiles.py` 的 logo 裁切閘門吃 `bed_texture_ink_extents.json`。
本工具寫入的 `ink_hull_uv` 是**墨跡的外接矩形四角**，不是真實凸包——
外接矩形 ⊇ 真實凸包 ⇒ 只會**更嚴**、不會更鬆，對安全閘門是正確的方向。
（原本用真實凸包是為了精確；這裡用保守超集是刻意的取捨，因為 CI 沒有 SVG 點陣化能力。）

用法：python tools/ping/make_bed_texture_svg.py [--check]
      --check ＝只驗現況與本工具產出一致（不寫檔），給收工自檢用。
"""
import argparse, hashlib, io, json, os, re, sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SRC = os.path.join(REPO, "resources", "images", "OrcaSlicer.svg")
PROF = os.path.join(REPO, "resources", "profiles", "PING")
FIX = os.path.join(REPO, "tools", "ping", "bed_texture_ink_extents.json")

CANVAS_W, CANVAS_H = 3192, 3191
BAND_TOP, BAND_H = 1351, 489      # 沿用舊 PNG 的墨跡帶（bbox 448,1351→2745,1840）
DOOR_DY = 217                     # 關門版下移量 ≒ 17mm（舊 PNG 1568-1351）
COLOR_FIX = {"#d24d21": "#EA4E16", "#202322": "#202221"}

TARGETS = [("ping_buildplate_texture.svg", 0, None),
           ("ping_buildplate_texture_closeddoor.svg", DOOR_DY, 17.0)]


def render_svg(dy):
    with io.open(SRC, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', src)
    if not m:
        sys.exit("來源 SVG 沒有 viewBox：" + SRC)
    vw, vh = float(m.group(1)), float(m.group(2))
    inner = src[src.index("</defs>") + len("</defs>"):src.rindex("</svg>")]
    if "<path" not in inner or "<image" in inner or "base64" in inner:
        sys.exit("來源不是純向量（含 <image> 或 base64）⇒ 中止，別把點陣圖包進 SVG")
    s = BAND_H / vh
    w = vw * s
    tx = (CANVAS_W - w) / 2.0
    ty = BAND_TOP + dy
    body = inner
    for a, b in COLOR_FIX.items():
        body = body.replace(a, b).replace(a.upper(), b)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'version="1.1" width="%d" height="%d" viewBox="0 0 %d %d">\n'
        '<!-- PING 床貼圖 — 由 tools/ping/make_bed_texture_svg.py 產生，勿手改。\n'
        '     內容＝resources/images/OrcaSlicer.svg 原封搬入（純向量），只外包 transform；\n'
        '     顏色校正到 CIS 正色。回報中心 #112・Eric 2026-09-07 裁「甲」。 -->\n'
        '<g transform="translate(%.4f,%.4f) scale(%.6f)">%s</g>\n'
        '</svg>\n' % (CANVAS_W, CANVAS_H, CANVAS_W, CANVAS_H, tx, ty, s, body)
    )
    # 墨跡外接矩形 → UV（v=0 為影像上緣）
    u0, u1 = tx / CANVAS_W, (tx + w) / CANVAS_W
    v0, v1 = ty / CANVAS_H, (ty + BAND_H) / CANVAS_H
    hull = [[round(u0, 6), round(v0, 6)], [round(u1, 6), round(v0, 6)],
            [round(u1, 6), round(v1, 6)], [round(u0, 6), round(v1, 6)]]
    return svg, hull


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只驗證，不寫檔")
    args = ap.parse_args()

    fix = json.load(io.open(FIX, encoding="utf-8")) if os.path.isfile(FIX) else {}
    drift = 0
    for name, dy, shift_mm in TARGETS:
        svg, hull = render_svg(dy)
        path = os.path.join(PROF, name)
        data = svg.encode("utf-8")
        cur = io.open(path, "rb").read() if os.path.isfile(path) else None
        if args.check:
            if cur != data:
                print("  ⚠ 與本工具產出不一致：", name); drift += 1
            else:
                print("  ✅ 一致：", name)
        else:
            io.open(path, "wb").write(data)
            print("  寫出 %-44s %d B" % (name, len(data)))
        if shift_mm is None:
            continue
        entry = {
            "_comment": ("關門專屬床貼圖的墨跡外接矩形（UV，v=0 為影像上緣＝床 +Y）。"
                         "外接矩形 ⊇ 真實凸包 ⇒ 只會更嚴不會更鬆。"
                         "重出貼圖請跑 tools/ping/make_bed_texture_svg.py，勿手改。"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": [CANVAS_W, CANVAS_H],
            "shift_mm_towards_front": shift_mm,
            "ink_hull_uv": hull,
        }
        if args.check:
            if fix.get(name) != entry:
                print("  ⚠ fixture 與本工具產出不一致：", name); drift += 1
            else:
                print("  ✅ fixture 一致：", name)
        else:
            fix.pop("ping_buildplate_texture_closeddoor.png", None)   # 舊 PNG 條目退場
            fix[name] = entry
            json.dump(fix, io.open(FIX, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print("  fixture 已更新：%s（sha %s…）" % (name, entry["sha256"][:12]))
    if args.check:
        print("漂移數 =", drift)
        sys.exit(1 if drift else 0)
    print("✅ 完成")


main()
