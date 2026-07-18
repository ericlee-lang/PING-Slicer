#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PINGSlicer.conf TPE 系統支可見清單修補（2026-07-18）。

背景：TPE 一對入系統（PING TPE／PING SupTPE，commit ae027ac4）取代 Eric user 自建三支
（PING TPE／SupTPE／Sup_TPE）。user 檔刪除後，conf 的 filaments 可見清單與 orca_presets
記住的選擇要跟著轉：SupTPE/Sup_TPE → PING SupTPE（PING TPE 同名免轉），並補兩支新名可見。

做法（文字手術保格式，同 patch_conf_hf_visible.py）：
  1) 引號形全域換名 "SupTPE"→"PING SupTPE"、"Sup_TPE"→"PING SupTPE"（引號界定＝不誤傷）。
  2) filaments 陣列重建：去重、補 PING TPE／PING SupTPE、排序。
  3) 重算尾行 MD5。

用法：
  python tools/ping/patch_conf_tpe_visible.py --check   # 乾跑
  python tools/ping/patch_conf_tpe_visible.py           # 實改（PingSlicer 必須已關閉）
"""
import io, os, re, sys, json, hashlib, shutil, subprocess, time

CONF = os.path.join(os.environ["APPDATA"], "PingSlicer", "PINGSlicer.conf")

RENAME_QUOTED = {'"SupTPE"': '"PING SupTPE"', '"Sup_TPE"': '"PING SupTPE"'}
ADD = ["PING TPE", "PING SupTPE"]
DROP = ["SupTPE", "Sup_TPE"]   # filaments 清單殘留舊名移除（換名後理論上已不在）


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
    t = io.open(CONF, encoding="utf-8", newline="").read()
    last = t.rfind("}")
    seg, tail = t[: last + 1], t[last + 1 :]
    m = re.search(r"# MD5 checksum ([0-9A-Fa-f]{32})", tail)
    cur_hash, calc = (m.group(1).upper() if m else None), md5_of_segment(seg)
    print("尾行 MD5=%s / 重算=%s / %s" % (cur_hash, calc, "一致✓" if cur_hash == calc else "不一致✗"))
    if cur_hash != calc:
        print("⚠ MD5 演算法對不上現檔，中止（防止寫壞）。")
        sys.exit(2)

    n_ren = {}
    for old, new in RENAME_QUOTED.items():
        n_ren[old] = seg.count(old)
        seg = seg.replace(old, new)

    bm = re.search(r'("filaments"\s*:\s*\[)(.*?)(\r?\n\s*\])', seg, re.S)
    if not bm:
        print("⚠ 找不到 filaments 陣列，中止。"); sys.exit(2)
    entries = json.loads("[" + bm.group(2).rstrip().rstrip(",") + "]")
    before = list(entries)
    entries = [e for e in entries if e not in DROP]
    for a in ADD:
        if a not in entries:
            entries.append(a)
    entries = sorted(set(entries))
    body = "".join("\r\n        %s," % json.dumps(e, ensure_ascii=False) for e in entries)
    body = body.rstrip(",")
    seg = seg[: bm.start()] + bm.group(1) + body + bm.group(3) + seg[bm.end():]

    new_hash = md5_of_segment(seg)
    new_tail = re.sub(r"([0-9A-Fa-f]{32})", new_hash, tail, count=1)
    print("換名次數：", {k: v for k, v in n_ren.items() if v})
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
        print("⚠ PingSlicer 正在執行——關閉後再跑（app 退出時會覆寫 conf）。"); sys.exit(3)
    bak = CONF + ".bak-tpevisible-" + time.strftime("%Y%m%d%H%M%S")
    shutil.copy2(CONF, bak)
    io.open(CONF, "w", encoding="utf-8", newline="").write(seg + new_tail)
    print("已寫入；備份＝%s；新 MD5=%s" % (bak, new_hash))


if __name__ == "__main__":
    main()
