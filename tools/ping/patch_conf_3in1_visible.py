#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PINGSlicer.conf 3in1 支可見清單修補（2026-07-26，Eric 裁 C＝口徑合一）。

背景：3in1 六支（@FF 0.4/0.6/1.0）於 bundle 64/74 併成 PING PLA(3in1)/PING SupPLA(3in1)
各一支（不綁機、renamed_from 相容）。Eric 機 conf 可見清單只有 0.6 兩支（當年精靈只勾過
3in1 0.6）⇒ 0.4 機的預設支不可見 → 預設套用失敗 fallback（Generic ABS 事件 2026-07-26）。

兩階段（⚠ 時序：T008 裝機前不可換名——舊六支還在機上，換了現行選擇會斷鏈）：
  --pre-t008 ：只「加」可見（舊六支補齊＋合併兩支預掛）＝當下 T007 就修好 0.4 預設。
  （預設）  ：T008 裝機後跑——引號形全域換名（含 orca_presets 記住的選擇）舊六名→合併名、
              可見清單去舊名補新名。
做法同 patch_conf_tpe_visible.py：文字手術保格式＋重算尾行 MD5＋app 關閉守衛＋備份。

用法：
  python tools/ping/patch_conf_3in1_visible.py --pre-t008 [--check]
  python tools/ping/patch_conf_3in1_visible.py [--check]          # T008 裝機後
"""
import io, os, re, sys, json, hashlib, shutil, subprocess, time

CONF = os.path.join(os.environ["APPDATA"], "PingSlicer", "PINGSlicer.conf")

OLD = ["PING %s(3in1) @FF %s" % (s, nz) for s in ("PLA", "SupPLA") for nz in ("0.4", "0.6", "1.0")]
MERGED = ["PING PLA(3in1)", "PING SupPLA(3in1)"]
RENAME_QUOTED = {'"%s"' % o: '"PING %s(3in1)"' % ("PLA" if "PLA(3in1)" in o and "Sup" not in o else "SupPLA")
                 for o in OLD}


def md5_of_segment(seg):
    return hashlib.md5(seg.replace("\r\n", "\n").encode("utf-8")).hexdigest().upper()


def app_running():
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
        return "ping-slicer.exe" in out or "pingslicer.exe" in out
    except Exception:
        return False


def main():
    check = "--check" in sys.argv
    pre = "--pre-t008" in sys.argv
    t = io.open(CONF, encoding="utf-8", newline="").read()
    last = t.rfind("}")
    seg, tail = t[: last + 1], t[last + 1:]
    m = re.search(r"# MD5 checksum ([0-9A-Fa-f]{32})", tail)
    cur_hash, calc = (m.group(1).upper() if m else None), md5_of_segment(seg)
    print("尾行 MD5=%s / 重算=%s / %s" % (cur_hash, calc, "一致✓" if cur_hash == calc else "不一致✗"))
    if cur_hash != calc:
        print("⚠ MD5 對不上現檔，中止（防寫壞）。"); sys.exit(2)

    if not pre:   # post-T008：換名（含 orca_presets 記住的選擇）
        n_ren = {}
        for old, new in RENAME_QUOTED.items():
            n_ren[old] = seg.count(old)
            seg = seg.replace(old, new)
        print("換名次數：", {k: v for k, v in n_ren.items() if v})

    bm = re.search(r'("filaments"\s*:\s*\[)(.*?)(\r?\n\s*\])', seg, re.S)
    if not bm:
        print("⚠ 找不到 filaments 陣列，中止。"); sys.exit(2)
    entries = json.loads("[" + bm.group(2).rstrip().rstrip(",") + "]")
    before = list(entries)
    if pre:
        for a in OLD + MERGED:          # 只加不刪：T007 舊支照舊可用、合併支先掛
            if a not in entries:
                entries.append(a)
    else:
        entries = [e for e in entries if e not in OLD]
        for a in MERGED:
            if a not in entries:
                entries.append(a)
    entries = sorted(set(entries))
    body = "".join("\r\n        %s," % json.dumps(e, ensure_ascii=False) for e in entries)
    body = body.rstrip(",")
    seg = seg[: bm.start()] + bm.group(1) + body + bm.group(3) + seg[bm.end():]

    new_hash = md5_of_segment(seg)
    new_tail = re.sub(r"([0-9A-Fa-f]{32})", new_hash, tail, count=1)
    print("filaments：%d → %d 支" % (len(before), len(entries)))
    for e in entries:
        if e not in before:
            print("  ＋", e)
    for e in before:
        if e not in entries:
            print("  －", e)
    if check:
        print("（--check 乾跑，未寫入）"); return

    if app_running():
        print("⚠ PingSlicer 執行中——關閉後再跑（app 退出時會覆寫 conf）。"); sys.exit(3)
    bak = CONF + ".bak-3in1visible-" + time.strftime("%Y%m%d%H%M%S")
    shutil.copy2(CONF, bak)
    io.open(CONF, "w", encoding="utf-8", newline="").write(seg + new_tail)
    print("已寫入；備份＝%s；新 MD5=%s" % (bak, new_hash))


if __name__ == "__main__":
    main()
