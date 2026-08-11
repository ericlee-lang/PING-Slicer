# -*- coding: utf-8 -*-
"""關門專屬床貼圖：把 logo 往床前緣（-Y）平移，讓它完全落進圓角三角形內。

CIS 鐵則：**只對原檔做確定性平移，不重畫 logo**。
UV 對應（3DBed.cpp:49-67 init_model_from_poly）：
    u = (x - min_x)/size_x                     → 影像左→右 對應 床 -X→+X
    v_raw = -(y - min_y)/size_y ，GL_REPEAT 取模 → v_eff = 1 - (y-min_y)/size_y
    ⇒ v_eff=0（影像最上緣）對應床 **+Y（後方）**；影像往下 = 床往前。
"""
import hashlib, io, json, math, os, sys
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PING = os.path.join(REPO, 'resources', 'profiles', 'PING')
SRC = os.path.join(PING, 'ping_buildplate_texture.png')
DST = os.path.join(PING, 'ping_buildplate_texture_closeddoor.png')
FIX = os.path.join(REPO, 'tools', 'ping', 'bed_texture_ink_extents.json')

MARGIN = 3.0        # mm，離邊界至少留這麼多
R_IN, R_OUT = 100.0, 150.0
APEX = 90.0


def area_pts():
    """與 embed_params.rounded_triangle_area() 同一組幾何（此處只需邊界判定用的解析式）。"""
    a = math.degrees(math.acos(R_IN / R_OUT))
    out = []
    for c in (APEX, APEX + 120.0, APEX + 240.0):
        s, e = c - (60.0 - a), c + (60.0 - a)
        n = max(2, int(round((e - s) / 2.0)) + 1)
        for i in range(n):
            t = math.radians(s + (e - s) * i / (n - 1))
            out.append((R_OUT * math.cos(t), R_OUT * math.sin(t)))
    return out


PTS = area_pts()
BX0, BX1 = min(p[0] for p in PTS), max(p[0] for p in PTS)
BY0, BY1 = min(p[1] for p in PTS), max(p[1] for p in PTS)
SX, SY = BX1 - BX0, BY1 - BY0


def clearance(x, y):
    """點到床形邊界的最小內側距離（負＝在外面）。三直邊各距床心 100、三圓弧在 R=150。"""
    d = min(R_IN - (x * math.cos(math.radians(n)) + y * math.sin(math.radians(n)))
            for n in (270.0, 30.0, 150.0))
    return min(d, R_OUT - math.hypot(x, y))


def ink_extremes(img):
    """每列取最左/最右不透明像素（會violate 邊界的一定在這些點上）。回傳 [(col,row)]。"""
    w, h = img.size
    a = img.getchannel('A').load()
    out = []
    for r in range(h):
        lo = hi = -1
        for c in range(w):
            if a[c, r]:
                lo = c
                break
        if lo < 0:
            continue
        for c in range(w - 1, -1, -1):
            if a[c, r]:
                hi = c
                break
        out.append((lo, r))
        if hi != lo:
            out.append((hi, r))
    return out


def hull(points):
    """單調鏈凸包。可印區是凸的 ⇒ 墨跡是否越界、越界多少，只由墨跡凸包的頂點決定
    ⇒ 存凸包＝精確，不是抽樣近似（抽樣會漏掉真正最糟的點，0811 實測踩過）。"""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts
    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2:
                (ax, ay), (bx, by) = out[-2], out[-1]
                if (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax) > 0:
                    break
                out.pop()
            out.append(p)
        return out
    return half(pts)[:-1] + half(reversed(pts))[:-1]


def to_world(col, row, w, h, dy_mm=0.0):
    u = (col + 0.5) / w
    v = (row + 0.5) / h                 # v_eff：0＝影像上緣＝床 +Y
    x = BX0 + u * SX
    y = BY0 + (1.0 - v) * SY + dy_mm
    return x, y


src = Image.open(SRC).convert('RGBA')
w, h = src.size
ext = hull(ink_extremes(src))
print('原圖 %dx%d，墨跡凸包頂點 %d（精確，非抽樣）' % (w, h, len(ext)))

worst = min(clearance(*to_world(c, r, w, h)) for c, r in ext)
print('未平移時：墨跡離邊界最小距離 = %+.2f mm（負＝被切）' % worst)

# 二分找最小下移量（下移＝床 -Y）
lo, hi = 0.0, 120.0
for _ in range(40):
    mid = (lo + hi) / 2
    if min(clearance(*to_world(c, r, w, h, -mid)) for c, r in ext) >= MARGIN:
        hi = mid
    else:
        lo = mid
need = hi
print('要完全落進三角形且留 %.0fmm 餘裕，最少下移 %.2f mm' % (MARGIN, need))

SHIFT_MM = float(sys.argv[1]) if len(sys.argv) > 1 else math.ceil(need)
px = int(round(SHIFT_MM / SY * h))
print('採用下移 %.1f mm ＝ 影像往下 %d px（1mm = %.3f px）' % (SHIFT_MM, px, h / SY))

after = min(clearance(*to_world(c, r, w, h, -SHIFT_MM)) for c, r in ext)
print('平移後：墨跡離邊界最小距離 = %+.2f mm' % after)
assert after >= MARGIN, '餘裕不足，別出圖'

# 產圖：透明底貼上平移後的原圖（不 wrap、不縮放、不重畫）
dst = Image.new('RGBA', (w, h), (0, 0, 0, 0))
dst.paste(src, (0, px))
dst.save(DST, optimize=True)
print('已寫出 %s（%d bytes）' % (os.path.basename(DST), os.path.getsize(DST)))

# 產 fixture（給 verify 用，免得 CI 要裝 PIL）：抽樣墨跡極值 + 檔案 SHA
dst_ext = hull(ink_extremes(Image.open(DST).convert('RGBA')))
uv = [[round((c + 0.5) / w, 6), round((r + 0.5) / h, 6)] for c, r in dst_ext]
sha = hashlib.sha256(open(DST, 'rb').read()).hexdigest()
fx = {}
if os.path.exists(FIX):
    fx = json.load(io.open(FIX, encoding='utf-8'))
fx[os.path.basename(DST)] = {
    '_comment': ('關門專屬床貼圖的墨跡凸包（UV，v=0 為影像上緣＝床 +Y）。'
                 '（凸包＝精確，因可印區為凸多邊形）verify 用它驗證 logo 完全落在 printable_area 內；'
                 '重出貼圖必須重跑 tools/ping/make_closeddoor_texture.py 更新本檔。'),
    'sha256': sha,
    'size': [w, h],
    'shift_mm_towards_front': SHIFT_MM,
    'ink_hull_uv': uv,
}
io.open(FIX, 'w', encoding='utf-8').write(json.dumps(fx, ensure_ascii=False, indent=2))
print('fixture 已更新：%s（凸包 %d 頂點＝精確，SHA %s…）' % (os.path.basename(FIX), len(uv), sha[:16]))
