# -*- coding: utf-8 -*-
"""組合製程功能歸類改名 conf 手術（0730 改名批；Codex 四輪定稿 §6）。

把 %APPDATA%\\PingSlicer\\PINGSlicer.conf 內各機 `orca_presets[*].process` 的
**選中製程名**由舊材料對全名換成新功能歸類全名——**exact 全名映射**（90 條），
非 substring：user/stale 名（如「0.2mm PLA+SUP - 複製」）一律不碰。

時序（v2 §6）：新版（T015+）裝機、system 夾收編新 bundle 後、首次以新版啟動前
原子完成；app 關閉才動（看門狗模式）；備份→改→MD5 重算→讀回復驗，失敗回滾。

用法：
  python patch_conf_combo_rename.py --dry-run [--conf 路徑]   # 只列命中，不寫
  python patch_conf_combo_rename.py --apply   [--conf 路徑]   # 實套（自動備份）
冪等：實套後複跑 --apply 應零命中（四輪修訂 B 的副本冪等測法照此驗）。
"""
import argparse
import hashlib
import io
import json
import os
import shutil
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

def md5_of(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", default=os.path.join(os.environ.get("APPDATA", ""), "PingSlicer", "PINGSlicer.conf"))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.conf):
        print("找不到 conf：%s" % a.conf); return 2
    raw = io.open(a.conf, encoding="utf-8").read()
    # PINGSlicer.conf＝首行 MD5 註記＋JSON 本體（沿 patch_conf_* 慣例）
    nl = raw.find("\n")
    head, body = (raw[:nl + 1], raw[nl + 1:]) if raw.startswith("#") else ("", raw)
    data = json.loads(body)
    mapping = build_mapping()

    hits, skips = [], []
    presets_by_machine = data.get("orca_presets", [])
    for entry in presets_by_machine:
        cur = entry.get("process")
        if not isinstance(cur, str):
            continue
        if cur in mapping:
            hits.append((entry.get("machine", "?"), cur, mapping[cur]))
        elif any(tok in cur for tok in COMBO_DISPLAY):   # 含舊 token 但非 exact＝user/stale
            skips.append((entry.get("machine", "?"), cur))

    print("命中 %d 筆（exact 系統名）；跳過 %d 筆（user/stale 含舊 token 但非 exact）" % (len(hits), len(skips)))
    for m, o, n in hits:
        print("  [換] %s: %s -> %s" % (m, o, n))
    for m, o in skips:
        print("  [跳過] %s: %s" % (m, o))

    if a.dry_run or not hits:
        return 0

    # 實套：備份 → 改 → MD5 重算 → 讀回復驗
    bak = a.conf + ".bak-comborename-" + time.strftime("%Y%m%d%H%M%S")
    shutil.copy2(a.conf, bak)
    for entry in presets_by_machine:
        cur = entry.get("process")
        if isinstance(cur, str) and cur in mapping:
            entry["process"] = mapping[cur]
    new_body = json.dumps(data, ensure_ascii=False, indent=4)
    new_head = ("#%s\n" % md5_of(new_body)) if head else ""
    io.open(a.conf, "w", encoding="utf-8", newline="").write(new_head + new_body)
    check = io.open(a.conf, encoding="utf-8").read()
    cnl = check.find("\n")
    cbody = check[cnl + 1:] if check.startswith("#") else check
    assert json.loads(cbody) == data, "讀回不一致——回滾 %s" % bak
    if new_head:
        assert check[1:cnl] == md5_of(cbody), "MD5 不自洽——回滾 %s" % bak
    print("完成；備份＝%s" % bak)
    return 0

if __name__ == "__main__":
    sys.exit(main())
