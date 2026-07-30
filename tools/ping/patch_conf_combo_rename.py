# -*- coding: utf-8 -*-
"""組合製程功能歸類改名 conf 手術（0730 改名批；Codex 四輪定稿 §6）。

把 %APPDATA%\\PingSlicer\\PINGSlicer.conf 內記住的**選中製程名**由舊材料對全名換成
新功能歸類全名——**引號形 exact 全名映射**（90 條），非 substring：
user/stale 名（如「0.2mm PLA+SUP - 複製」）一律不碰。

時序（v2 §6）：新版（T015+）裝機、system 夾收編新 bundle 後、首次以新版啟動前
原子完成；app 關閉才動（守衛）；備份→改→尾行 MD5 重算→讀回復驗，失敗回滾。

⚠ conf 實際格式＝**JSON 本體 ＋ 尾行 `# MD5 checksum XXXX`**（首字是 `{`，MD5 在檔尾）。
   0730 首次對真實 conf 執行時發現初版誤設為「首行 MD5」而 json.loads 整檔炸掉
   （Codex 四輪雙審未抓到——冪等測用的是自造 conf、非真實樣本）。現沿
   `patch_conf_3in1_visible.py` 已在實機驗證兩次的做法：rfind("}") 切段＋文字手術保格式。

用法：
  python patch_conf_combo_rename.py --dry-run [--conf 路徑]   # 只列命中，不寫
  python patch_conf_combo_rename.py --apply   [--conf 路徑]   # 實套（自動備份）
冪等：實套後複跑 --apply 應零命中。
"""
import argparse
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import time

COMBO_DISPLAY = {"PLA+SUP": "易拆(Z0)", "PLA+PVA": "易拆(Z0)水溶", "ABS+SUP": "易拆(Z0)+棧板",
                 "PLA+PLA": "雙料(Z隙)", "ABS+ABS": "雙料(Z隙)+棧板"}
# 90 條 exact 映射＝6 台雙料機 × 口徑層高 × 5 token（與 embed_params 產名規則同構）
MACHINES = {  # model: [(nozzle, layer_height)]
    "FD300":      [("0.25", "0.125"), ("0.4", "0.2"), ("0.6", "0.3")],
    "FD300 Pro":  [("0.25", "0.125"), ("0.4", "0.2"), ("0.6", "0.3")],
    "FD300 關門": [("0.25", "0.125"), ("0.4", "0.2"), ("0.6", "0.3")],
    "FD450 Pro":  [("0.4", "0.2"), ("0.6", "0.3"), ("1.0", "0.5")],
    "FD600 Pro":  [("0.4", "0.2"), ("0.6", "0.3"), ("1.0", "0.5")],
    "FD800 Pro":  [("0.4", "0.2"), ("0.6", "0.3"), ("1.0", "0.5")],
}


def build_mapping():
    mp = {}
    for model, pairs in MACHINES.items():
        for nz, lh in pairs:
            for old_tok, new_tok in COMBO_DISPLAY.items():
                old = "%smm %s @%s (%s)" % (lh, old_tok, model, nz)
                new = "%smm %s @%s (%s)" % (lh, new_tok, model, nz)
                mp[old] = new
    assert len(mp) == 90, len(mp)
    return mp


def md5_of_segment(seg):
    """尾行 MD5 的算法（同 patch_conf_3in1_visible／patch_conf_tpe_visible）"""
    return hashlib.md5(seg.replace("\r\n", "\n").encode("utf-8")).hexdigest().upper()


def app_running():
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout.lower()
        return "ping-slicer.exe" in out or "pingslicer.exe" in out
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", default=os.path.join(os.environ.get("APPDATA", ""),
                                                   "PingSlicer", "PINGSlicer.conf"))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.conf):
        print("找不到 conf：%s" % a.conf)
        return 2

    # conf＝JSON 本體 ＋ 尾行「# MD5 checksum XXXX」
    t = io.open(a.conf, encoding="utf-8", newline="").read()
    last = t.rfind("}")
    if last < 0:
        print("conf 格式異常（找不到 JSON 結尾 '}'）")
        return 2
    seg, tail = t[:last + 1], t[last + 1:]
    m = re.search(r"# MD5 checksum ([0-9A-Fa-f]{32})", tail)
    cur_hash, calc = (m.group(1).upper() if m else None), md5_of_segment(seg)
    print("尾行 MD5=%s / 重算=%s / %s"
          % (cur_hash, calc, "一致 ✓" if cur_hash == calc else "不一致 ✗"))
    if cur_hash != calc:
        print("⚠ MD5 對不上現檔，中止（防寫壞）。")
        return 2

    mapping = build_mapping()

    # 命中＝引號形 exact 全名（只換系統名，不碰 user/stale）
    hits = {}
    for old, new in mapping.items():
        c = seg.count('"%s"' % old)
        if c:
            hits[old] = (new, c)
    stale = set()
    for mt in re.finditer(r'"([^"]*(?:%s)[^"]*)"'
                          % "|".join(re.escape(k) for k in COMBO_DISPLAY), seg):
        v = mt.group(1)
        if v not in mapping:
            stale.add(v)

    total = sum(c for _, c in hits.values())
    print("命中 %d 種系統全名、共 %d 處；跳過 %d 種（user/stale 含舊 token 但非 exact）"
          % (len(hits), total, len(stale)))
    for old in sorted(hits):
        new, c = hits[old]
        print("  [換 ×%d] %s -> %s" % (c, old, new))
    for v in sorted(stale):
        print("  [跳過] %s" % v)

    if a.dry_run or not hits:
        return 0

    if app_running():
        print("⚠ PingSlicer 執行中——請先關閉 app 再跑 --apply（防寫壞）。")
        return 2

    # 實套：備份 → 文字手術 → 尾行 MD5 重算 → 讀回復驗
    bak = a.conf + ".bak-comborename-" + time.strftime("%Y%m%d%H%M%S")
    shutil.copy2(a.conf, bak)
    new_seg = seg
    for old, (new, _c) in hits.items():
        new_seg = new_seg.replace('"%s"' % old, '"%s"' % new)
    new_tail = re.sub(r"# MD5 checksum [0-9A-Fa-f]{32}",
                      "# MD5 checksum " + md5_of_segment(new_seg), tail)
    io.open(a.conf, "w", encoding="utf-8", newline="").write(new_seg + new_tail)

    # 讀回復驗：MD5 自洽＋舊名歸零＋新名到位＋stale 原封不動
    chk = io.open(a.conf, encoding="utf-8", newline="").read()
    clast = chk.rfind("}")
    cseg, ctail = chk[:clast + 1], chk[clast + 1:]
    cm = re.search(r"# MD5 checksum ([0-9A-Fa-f]{32})", ctail)
    problems = []
    if not cm or cm.group(1).upper() != md5_of_segment(cseg):
        problems.append("MD5 不自洽")
    for old, (new, c) in hits.items():
        if cseg.count('"%s"' % old) != 0:
            problems.append("舊名殘留：%s" % old)
        if cseg.count('"%s"' % new) < c:
            problems.append("新名未到位：%s" % new)
    for v in stale:
        if cseg.count('"%s"' % v) != seg.count('"%s"' % v):
            problems.append("誤動 user/stale：%s" % v)
    if problems:
        shutil.copy2(bak, a.conf)
        print("復驗失敗、已回滾：" + "；".join(problems))
        return 1

    print("完成：%d 種、%d 處換名；MD5 自洽；user/stale 未動。備份＝%s" % (len(hits), total, bak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
