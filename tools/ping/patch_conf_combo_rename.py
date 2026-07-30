# -*- coding: utf-8 -*-
"""組合製程功能歸類改名 conf 手術。

Review state：v1 一輪否決（C-01~C-14）→ v2 二輪（D-01~D-09）→ v3 三輪（E-01~E-03）→
v4 四輪（F-01~F-03＋E-02殘）→ v5 五輪（F-01殘/測試真實性/G-01/G-02）→ **本檔＝v6**
（process 檔 aggregate digest 入 manifest／T5 脫 live／T12 byte-exact／版本文案對齊），
**待 Codex 六輪複審通過＋Eric 核可殘窗（P-4）才准 --apply**。
審查軌跡＝專案根 `_審查_conf組合名手術_*`。

把 %APPDATA%\\PingSlicer\\PINGSlicer.conf 內 `orca_presets[*].process` 記住的選中
製程名由舊材料對全名換成新功能歸類全名（90 條 exact 映射；user/stale 不碰）。
必要性受證：app 啟動對 orca_presets 的 process 走 `select_preset_by_name_strict()`
＝exact-only、無 renamed_from 回溯（PresetBundle.cpp:1979→Preset.cpp:3148）。

conf 格式（實檔受證）：JSON 本體＋尾段 `\\r\\n# MD5 checksum <32HEX>\\r\\n`（結尾、
恰一次、無 BOM）。MD5＝對 LF 正規化後本體之 md5 大寫（AppConfig.cpp:539-557 同構）。

v6 安全設計（對應歷輪審查條號）：
  C-01/D-01 原子寫入＋交易化復驗：tmp（exclusive）→fsync→讀回驗→os.replace；
       換入後**所有可恢復例外**（含 OSError）都進回滾判定；程序被殺/斷電不宣稱保證回滾
       （備份＋MD5 尾行可偵測損壞、人工還原）
  C-02/D-03 競態閘：tasklist 例外/rc≠0/空輸出＝中止（fail-closed）；replace 前查 app＋
       bytes 比對緊貼 replace。⚠ 比對→replace 毫秒殘窗＝**已知殘餘風險、條件接受**
       （威脅模型：app 寫檔須先啟動＝被前置守衛擋；由 Eric 核可）。換入後復驗＋
       ownership 檢查＝**檢測與止損**（不再蓋一次）、**非**殘窗事件的復原手段——
       殘窗中被覆蓋的外力版本無法由本腳本救回（D-04 三輪措辭修正）
  C-03 stdout/stderr 強制 utf-8＋狀態字全 ASCII
  C-04/D-05/E-01/E-02 動態掃描＋manifest 全欄契約：期望命中「不寫死數字」（基準會被
       app 合法飄移），dry-run 產 manifest（schema v3：conf SHA-256/size/file_id＋
       bundle root/version/PING.json SHA-256/process agg SHA-256＋逐 path old→new＋
       stale 清單＋expected
       SHA-256），--apply 必帶且**全欄 type-aware 綁定**（欄位集不符/任一欄不符＝拒）；
       **零命中不是特權路徑**——一樣要 manifest、一樣全欄核對後才回報冪等
  C-06 雙路交叉：文字 vs JSON 樹逐名計數一致、path 白名單 fullmatch
       orca_presets/<i>/process、dict key 命中即中止、escape 形式差異即中止
  C-07/D-06 strict parse（拒重複鍵/NaN/Inf/溢位 inf）×3 段＋expected bytes 三度比對＋
       expected 樹 type-aware 全等（deep_eq 擋 True==1/1==1.0）＋新名計數 post==pre+delta
  C-08 尾段結尾錨定 fullmatch＋checksum 恰一＋拒 BOM
  C-09/D-07 bundle 守衛：version＋90 新名恰一次＋sub_path 正確＋舊名清單消失＋
       檔內 name==新名＋renamed_from 逐字
  C-10/D-02 備份 exclusive＋SHA-256 驗證；回滾 ownership 檢查（正檔非腳本寫入的
       expected＝外力版本＝**禁止覆蓋**、保三檔人工）＋回滾前查 app＋回滾後驗證
  C-13 APPDATA 缺失中止；mapping 完整性 runtime check（-O 免疫）

已知限制（誠實記載）：
  - 本腳本只遷移「仍存在的舊名」；若某機的選擇已被 app fallback 覆寫，無法恢復原選擇（C-05）
  - 產品級缺口另案：升級 T015 的其他機器同樣會 fallback——正解＝C++ 載入 orca_presets
    時先過 renamed resolver（押下顆 T、交 Eric 裁）（C-12）

用法（兩段式，D-05）：
  python patch_conf_combo_rename.py --dry-run [--conf 路徑] [--bundle-root 路徑]
      → 輸出命中清單＋產 manifest 檔（過目清單）
  python patch_conf_combo_rename.py --apply --manifest <dry-run 產出的檔> [--conf ...] [--bundle-root ...]
      → conf 與 manifest 逐項核對（SHA-256）後才動檔
冪等：實套後複跑 dry-run 應零命中。
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # C-03
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

COMBO_DISPLAY = {"PLA+SUP": "易拆(Z0)", "PLA+PVA": "易拆(Z0)水溶", "ABS+SUP": "易拆(Z0)+棧板",
                 "PLA+PLA": "雙料(Z隙)", "ABS+ABS": "雙料(Z隙)+棧板"}
# 90 條 exact 映射＝6 台雙料機 × 各 3 組口徑層高 × 5 token（與 embed_params 產名規則同構）
MACHINES = {  # model: [(nozzle, layer_height)] — 每台恰 3 組
    "FD300":      [("0.25", "0.125"), ("0.4", "0.2"), ("0.6", "0.3")],
    "FD300 Pro":  [("0.25", "0.125"), ("0.4", "0.2"), ("0.6", "0.3")],
    "FD300 關門": [("0.25", "0.125"), ("0.4", "0.2"), ("0.6", "0.3")],
    "FD450 Pro":  [("0.4", "0.2"), ("0.6", "0.3"), ("1.0", "0.5")],
    "FD600 Pro":  [("0.4", "0.2"), ("0.6", "0.3"), ("1.0", "0.5")],
    "FD800 Pro":  [("0.4", "0.2"), ("0.6", "0.3"), ("1.0", "0.5")],
}
TAIL_RE = re.compile(r"\r\n# MD5 checksum ([0-9A-F]{32})\r\n\Z")   # C-08 fullmatch（結尾錨定）
BUNDLE_VERSION = "01.00.00.86"                                     # C-09（T015）
DEFAULT_BUNDLE = r"D:\PING-Slicer-portable"


def build_mapping():
    mp = {}
    for model, pairs in MACHINES.items():
        for nz, lh in pairs:
            for old_tok, new_tok in COMBO_DISPLAY.items():
                old = "%smm %s @%s (%s)" % (lh, old_tok, model, nz)
                new = "%smm %s @%s (%s)" % (lh, new_tok, model, nz)
                mp[old] = new
    # C-13：不用 assert（python -O 會消失）
    if len(mp) != 90 or len(set(mp.values())) != 90 or (set(mp) & set(mp.values())):
        raise SystemExit("mapping 完整性失敗：%d 條/新名唯一 %d/交集 %d"
                         % (len(mp), len(set(mp.values())), len(set(mp) & set(mp.values()))))
    return mp


def md5_of_segment(seg):
    """尾行 MD5 演算法（app 對 LF 版 dump 算 md5、text mode 寫成 CRLF 的等價式）"""
    return hashlib.md5(seg.replace("\r\n", "\n").encode("utf-8")).hexdigest().upper()


def sha256_of_bytes(b):
    return hashlib.sha256(b).hexdigest()


def write_verified_tmp(tmp_path, data):
    """E-03/F-03：forward/rollback/expected artifact 共用——exclusive 寫入＋fsync＋
    讀回逐位元驗證；驗證不過或中途任何例外＝清掉自建檔＋raise，
    絕不讓未驗證的 tmp 進 os.replace、也不遺留半成品檔。"""
    f = open(tmp_path, "xb")            # exclusive create 成功後，本函式擁有該檔
    try:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
        f.close()
        back = open(tmp_path, "rb").read()
        if back != data:
            raise RuntimeError("暫存檔 %s 讀回 ≠ 目標內容（%d vs %d bytes）——拒絕換入"
                               % (os.path.basename(tmp_path), len(back), len(data)))
    except BaseException:               # F-03：含 SystemExit/KeyboardInterrupt 都先清自建檔
        try:
            f.close()
        except Exception:
            pass
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def app_running():
    """C-02/D-03：查詢失敗或非零退出碼＝中止（fail-closed），不得回傳 False 蒙混"""
    try:
        cp = subprocess.run(["tasklist"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    except Exception as e:
        raise SystemExit("ABORT: 無法查詢處理程序（fail-closed）：%r" % e)
    if cp.returncode != 0:
        raise SystemExit("ABORT: tasklist 退出碼 %d（fail-closed）" % cp.returncode)
    out = (cp.stdout or "").lower()
    if not out.strip():
        raise SystemExit("ABORT: tasklist 輸出為空（fail-closed）")
    return "ping-slicer.exe" in out or "pingslicer.exe" in out


def strict_loads(text, what):
    """C-07/D-06：拒重複鍵、拒 NaN/Infinity（含 1e400 溢位成 inf）"""
    import math

    def no_dup(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError("重複鍵 %r" % k)
            d[k] = v
        return d

    def no_const(name):
        raise ValueError("非法常數 %r" % name)

    def finite_float(s):
        v = float(s)
        if not math.isfinite(v):
            raise ValueError("非有限數值 %r" % s)
        return v
    try:
        return json.loads(text, object_pairs_hook=no_dup, parse_constant=no_const,
                          parse_float=finite_float)
    except Exception as e:
        raise SystemExit("ABORT: %s strict JSON 解析失敗：%r" % (what, e))


def deep_eq(a, b):
    """D-06：type-aware 全等——type 必須嚴格相同（擋 True==1、1==1.0），遞迴比較"""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if set(a) != set(b):
            return False
        return all(deep_eq(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(deep_eq(x, y) for x, y in zip(a, b))
    return a == b


def scan_tree(data, mapping):
    """C-06：JSON 樹 walk——值命中收集 path；dict key 命中＝立即違規"""
    hits, key_viol = [], []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in mapping or k in mapping.values():
                    key_viol.append("/".join(path + [k]))
                walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + [str(i)])
        elif isinstance(node, str):
            if node in mapping:
                hits.append(("/".join(path), node))
    walk(data, [])
    return hits, key_viol


def verify_bundle(bundle_root, mapping):
    """C-09/D-07/F-01：bundle 守衛——version＋90 新名在冊（恰一次、sub_path 正確）＋
    舊名已從清單消失＋檔內 name==新名＋renamed_from 逐字。
    F-01：PING.json **只讀一次**，digest 與驗證出自同一份 bytes；回傳該 digest
    給 manifest 綁定（manifest 綁的就是被驗證過的那份，無斷鏈）。"""
    from collections import Counter
    pj_path = os.path.join(bundle_root, "resources", "profiles", "PING.json")
    if not os.path.isfile(pj_path):
        raise SystemExit("ABORT: 找不到 bundle：%s" % pj_path)
    pj_bytes = open(pj_path, "rb").read()
    pj_digest = sha256_of_bytes(pj_bytes)
    try:
        pj_text = pj_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SystemExit("ABORT: bundle PING.json 非 UTF-8：%r" % e)
    pj = strict_loads(pj_text, "bundle PING.json")
    ver = pj.get("version")
    if ver != BUNDLE_VERSION:
        raise SystemExit("ABORT: bundle 版本 %r ≠ %s（T015 未裝機？）" % (ver, BUNDLE_VERSION))
    plist = pj.get("process_list", [])
    name_cnt = Counter(e.get("name") for e in plist)
    sub_by_name = {e.get("name"): e.get("sub_path") for e in plist}
    probs = []
    for n in mapping.values():
        if name_cnt.get(n, 0) != 1:
            probs.append("新名 %s 在清單出現 %d 次（應恰 1）" % (n, name_cnt.get(n, 0)))
        elif sub_by_name.get(n) != "process/%s.json" % n:
            probs.append("新名 %s sub_path=%r 異常" % (n, sub_by_name.get(n)))
    for o in mapping:
        if name_cnt.get(o, 0) != 0:
            probs.append("舊名 %s 仍在清單（應消失）" % o)
    if probs:
        raise SystemExit("ABORT: bundle 清單守衛失敗 %d 條，如 %r" % (len(probs), probs[:3]))
    proc_dir = os.path.join(bundle_root, "resources", "profiles", "PING", "process")
    bad = []
    proc_digests = []          # F-01 五輪殘項：90 支「驗證過的那份 bytes」digest 聚合
    for old, new in mapping.items():
        fp = os.path.join(proc_dir, new + ".json")
        if not os.path.isfile(fp):
            bad.append("%s：檔缺" % new)
            continue
        pd_bytes = open(fp, "rb").read()           # 只讀一次：digest 與驗證同源
        proc_digests.append("%s:%s" % (new, sha256_of_bytes(pd_bytes)))
        try:
            pd_text = pd_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            bad.append("%s：非 UTF-8 %r" % (new, e))
            continue
        pd = strict_loads(pd_text, new)
        if pd.get("name") != new:
            bad.append("%s：檔內 name=%r" % (new, pd.get("name")))
        if pd.get("renamed_from") != old:
            bad.append("%s：renamed_from=%r≠%r" % (new, pd.get("renamed_from"), old))
    if bad:
        raise SystemExit("ABORT: bundle 檔內守衛失敗 %d 條，如 %r" % (len(bad), bad[:3]))
    proc_agg = sha256_of_bytes("\n".join(sorted(proc_digests)).encode("utf-8"))
    print("[bundle] OK：version %s、90 新名恰一次+sub_path 正確、舊名清單 0、"
          "檔內 name/renamed_from 90/90（PING.json %s.../process agg %s...）"
          % (ver, pj_digest[:12], proc_agg[:12]))
    return pj_digest, proc_agg


def read_conf(path):
    """讀檔＋格式守衛（C-08）。回傳 (raw_bytes, text, seg, tail, tail_hash, file_id)。
    F-02：bytes 與 file_id 取自**同一個開啟 handle**（os.fstat），杜絕「A 的 bytes＋B 的
    file-id」拼裝；file_id 為零/不可用＝fail-closed。"""
    with open(path, "rb") as fh:
        st = os.fstat(fh.fileno())
        raw = fh.read()
    file_id = [st.st_dev, st.st_ino]
    if not st.st_dev or not st.st_ino:
        raise SystemExit("ABORT: 檔案系統不提供有效 file identity（st_dev/st_ino 為零）——fail-closed")
    if raw[:3] == b"\xef\xbb\xbf":
        raise SystemExit("ABORT: conf 帶 BOM＝非 app 寫出的格式")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SystemExit("ABORT: conf 非 UTF-8：%r" % e)
    last = text.rfind("}")
    if last < 0:
        raise SystemExit("ABORT: 找不到 JSON 結尾 '}'")
    seg, tail = text[:last + 1], text[last + 1:]
    m = TAIL_RE.match(tail)          # \Z 錨定＝fullmatch
    if not m:
        raise SystemExit("ABORT: 尾段格式不符（應恰為 CRLF+'# MD5 checksum <32HEX>'+CRLF）：%r" % tail[-80:])
    if text.count("# MD5 checksum") != 1:
        raise SystemExit("ABORT: checksum 行出現 %d 次（應恰 1）" % text.count("# MD5 checksum"))
    return raw, text, seg, tail, m.group(1), file_id


def analyze(seg, data, mapping):
    """雙路交叉（C-04/C-06）。回傳 (hits_text{old:cnt}, tree_hits, stale{name:cnt})"""
    hits_text = {}
    for old in mapping:
        c = seg.count('"%s"' % old)
        if c:
            hits_text[old] = c
    tree_hits, key_viol = scan_tree(data, mapping)
    if key_viol:
        raise SystemExit("ABORT: dict key 命中映射名（不該發生）：%r" % key_viol[:3])
    # 逐名計數一致（escape 形式差異會讓樹多於文字）
    from collections import Counter
    tree_cnt = Counter(v for _p, v in tree_hits)
    if dict(tree_cnt) != hits_text:
        raise SystemExit("ABORT: 文字/樹掃描不一致（escape 形式差異或結構異常）：text=%r tree=%r"
                         % (hits_text, dict(tree_cnt)))
    # 路徑白名單：orca_presets/<idx>/process
    bad_path = [p for p, _v in tree_hits
                if not re.fullmatch(r"orca_presets/\d+/process", p)]
    if bad_path:
        raise SystemExit("ABORT: 命中落在白名單外路徑：%r" % bad_path[:5])
    # stale：含舊 token 但非 exact
    stale = {}
    tok_re = re.compile(r'"([^"\\]*(?:%s)[^"\\]*)"' % "|".join(re.escape(k) for k in COMBO_DISPLAY))
    for mt in tok_re.finditer(seg):
        v = mt.group(1)
        if v not in mapping:
            stale[v] = stale.get(v, 0) + 1
    return hits_text, tree_hits, stale


def compute_expected(seg, pre_data, mapping, hits_text, stale):
    """手術＋記憶體全套驗證（dry-run/apply 共用；D-05 使兩模式推導同一 expected）。
    回傳 (expected_bytes, expected_tree)。"""
    import copy
    total = sum(hits_text.values())
    new_seg = seg
    for old, new in mapping.items():                        # 全集 replace（與命中集等效：未命中者 0 次）
        new_seg = new_seg.replace('"%s"' % old, '"%s"' % new)
    new_tail = "\r\n# MD5 checksum %s\r\n" % md5_of_segment(new_seg)
    expected_bytes = (new_seg + new_tail).encode("utf-8")   # C-07-5

    expected_tree = copy.deepcopy(pre_data)                 # 獨立於文字手術推導
    changed = 0
    for entry in expected_tree.get("orca_presets", []):
        cur = entry.get("process")
        if isinstance(cur, str) and cur in mapping:
            entry["process"] = mapping[cur]
            changed += 1
    if changed != total:
        raise SystemExit("ABORT: 樹側可換數 %d ≠ 文字側 %d" % (changed, total))

    post_data = strict_loads(new_seg, "術後（記憶體）")      # C-07 第 2 段
    if not deep_eq(post_data, expected_tree):               # D-06 type-aware
        raise SystemExit("ABORT: 術後樹 ≠ 預期樹（超出 orca_presets[*].process 的變更）")
    for old, c in hits_text.items():
        new = mapping[old]
        pre_new = seg.count('"%s"' % new)
        post_new = new_seg.count('"%s"' % new)
        if new_seg.count('"%s"' % old) != 0:
            raise SystemExit("ABORT: 舊名殘留 %s" % old)
        if post_new != pre_new + c:                         # C-07-4：== 不是 >=
            raise SystemExit("ABORT: 新名 %s 計數 %d ≠ %d+%d" % (new, post_new, pre_new, c))
    for v, c in stale.items():
        if new_seg.count('"%s"' % v) != c:
            raise SystemExit("ABORT: 誤動 user/stale：%s" % v)
    if not TAIL_RE.match(new_tail):
        raise SystemExit("ABORT: 新尾段格式自檢失敗")
    return expected_bytes, expected_tree


def main():
    ap = argparse.ArgumentParser()
    appdata = os.environ.get("APPDATA")
    ap.add_argument("--conf", default=None)
    ap.add_argument("--bundle-root", default=DEFAULT_BUNDLE)
    ap.add_argument("--manifest", default=None,
                    help="--apply 必帶：dry-run 產出的 manifest 檔（D-05 apply 契約）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if a.conf is None:
        if not appdata:                                     # C-13
            raise SystemExit("ABORT: APPDATA 環境變數缺失，拒絕以相對路徑操作")
        a.conf = os.path.join(appdata, "PingSlicer", "PINGSlicer.conf")
    a.conf = os.path.abspath(a.conf)
    if not os.path.isfile(a.conf):
        raise SystemExit("ABORT: 找不到 conf：%s" % a.conf)
    print("[conf] %s" % a.conf)
    if a.apply and not a.manifest:
        raise SystemExit("ABORT: --apply 必須帶 --manifest（先 --dry-run 產出並過目清單）")

    mapping = build_mapping()
    bundle_digest, bundle_proc_agg = verify_bundle(a.bundle_root, mapping)  # C-09/D-07/F-01（單快照 digest×2）

    if app_running():                                       # fail-closed 在函式內
        raise SystemExit("ABORT: PingSlicer 執行中——關閉後再跑")

    raw, text, seg, tail, tail_hash, conf_file_id = read_conf(a.conf)
    calc = md5_of_segment(seg)
    print("[md5] 尾行=%s 重算=%s %s" % (tail_hash, calc, "OK" if tail_hash == calc else "FAIL"))
    if tail_hash != calc:
        raise SystemExit("ABORT: MD5 對不上現檔（外力動過或格式不符），中止")

    pre_data = strict_loads(seg, "術前 conf")               # C-07 第 1 段
    hits_text, tree_hits, stale = analyze(seg, pre_data, mapping)
    total = sum(hits_text.values())

    print("[scan] 命中 %d 種、%d 處（全部在 orca_presets[*].process、雙路交叉一致）；"
          "stale 不碰 %d 種" % (len(hits_text), total, len(stale)))
    for old in sorted(hits_text):
        print("  [CHG x%d] %s -> %s" % (hits_text[old], old, mapping[old]))
    for p, v in sorted(tree_hits):
        print("    path %s" % p)
    for v in sorted(stale):
        print("  [SKIP x%d] %s" % (stale[v], v))

    # 零命中時 expected＝現檔原樣（E-01：零命中不再是特權路徑，一樣走 manifest 契約）
    if hits_text:
        expected_bytes, expected_tree = compute_expected(seg, pre_data, mapping, hits_text, stale)
    else:
        expected_bytes, expected_tree = raw, pre_data

    # manifest 內容（dry-run 產出＝apply 核對，同一函式推導；E-02 全欄綁定）。
    # F-01：bundle digest＝verify_bundle 驗證過的那份 bytes；F-02：conf_file_id＝
    # read_conf 同 handle fstat——兩者都不在此重讀。
    def build_manifest():
        body = {
            "schema": "combo-rename-manifest/3",
            "conf_path": a.conf,
            "conf_sha256": sha256_of_bytes(raw),
            "conf_size": len(raw),
            "conf_file_id": conf_file_id,
            "bundle_root": os.path.abspath(a.bundle_root),
            "bundle_version": BUNDLE_VERSION,
            "bundle_pingjson_sha256": bundle_digest,
            "bundle_process_agg_sha256": bundle_proc_agg,
            "changes": [{"path": p, "old": v, "new": mapping[v]} for p, v in sorted(tree_hits)],
            "stale_untouched": {k: v for k, v in sorted(stale.items())},
            "expected_sha256": sha256_of_bytes(expected_bytes),
        }
        # E-02：manifest 自身 token＝canonical dump 之 SHA-256 前 16 碼——dry-run 與 apply
        # 兩端都列印，人審過目的那份與實際執行的那份以同一 token 對上
        body["manifest_token"] = sha256_of_bytes(
            json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8"))[:16]
        return body

    if a.dry_run:
        ts = time.strftime("%Y%m%d%H%M%S") + ("%03d" % (int(time.time() * 1000) % 1000))
        manifest = build_manifest()
        mpath = a.conf + ".manifest-comborename-" + ts + ".json"
        with open(mpath, "xb") as f:
            f.write(json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        print("[manifest] %s" % mpath)
        print("[token] %s（apply 時核對同一 token＝人審過目的同一份）" % manifest["manifest_token"])
        print("[dry-run] 未動 conf；過目清單後以 --apply --manifest 該檔執行"
              if hits_text else "[dry-run] 零命中（冪等）；manifest 仍已產出供留痕")
        return 0

    # ---------- E-01/E-02/D-05：manifest 契約核對（一律先驗、全欄 type-aware 綁定） ----------
    if not os.path.isfile(a.manifest):
        raise SystemExit("ABORT: 找不到 manifest：%s" % a.manifest)
    mf = strict_loads(io.open(a.manifest, encoding="utf-8").read(), "manifest")
    now = build_manifest()
    # mtime 不入綁定集（防毒/索引 touch 不改內容；內容一致性由 sha256+size+file_id 保證）
    tok = mf.get("manifest_token")
    body_wo = {k: v for k, v in mf.items() if k != "manifest_token"}
    calc_tok = sha256_of_bytes(
        json.dumps(body_wo, ensure_ascii=False, sort_keys=True).encode("utf-8"))[:16]
    if tok != calc_tok:
        raise SystemExit("ABORT: manifest_token 不自洽（檔案被改過）：%r vs %r" % (tok, calc_tok))
    print("[token] %s（與 dry-run 過目版核對）" % tok)
    if set(mf) != set(now):
        raise SystemExit("ABORT: manifest 欄位集不符（缺欄或未知欄）：%r vs %r"
                         % (sorted(set(mf) ^ set(now)), sorted(now)))
    diffs = [k for k in now if not deep_eq(mf[k], now[k])]
    if diffs:
        for k in diffs:
            print("  [MISMATCH] %s：manifest=%r 當下=%r" % (k, mf[k], now[k]))
        raise SystemExit("ABORT: manifest 與當下狀態不符（欄位 %s）——conf/bundle 已變動，"
                         "重跑 --dry-run 產新 manifest 過目後再 apply" % "、".join(diffs))

    if not hits_text:
        print("[apply] 零命中＝無事可做（冪等；manifest 契約已核對）")
        return 0

    # ---------- 備份（C-10：exclusive＋digest 驗證） ----------
    ts = time.strftime("%Y%m%d%H%M%S") + ("%03d" % (int(time.time() * 1000) % 1000))
    bak = a.conf + ".bak-comborename-" + ts
    with open(bak, "xb") as f:                              # exclusive：同名即炸
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    if sha256_of_bytes(open(bak, "rb").read()) != sha256_of_bytes(raw):
        raise SystemExit("ABORT: 備份 SHA-256 與原檔不符（未動正檔）：%s" % bak)
    print("[backup] %s（SHA-256 驗證一致）" % os.path.basename(bak))

    # ---------- 原子寫入（C-01/E-03）＋競態閘（C-02） ----------
    tmp = a.conf + ".tmp-comborename-" + ts
    try:
        write_verified_tmp(tmp, expected_bytes)             # E-03 共用驗證寫入
        # 競態閘（順序有意義）：先擋秒級威脅（app 啟動→載入→寫檔），
        # bytes 比對必須「緊貼」replace——比對與換入間殘窗＝毫秒級，
        # 遠小於威脅模型的秒級（app 寫 conf 走 tmp+rename、啟動後才可能發生）。
        if app_running():
            raise RuntimeError("app 在手術期間啟動（未覆蓋）")
        if open(a.conf, "rb").read() != raw:
            raise RuntimeError("正檔在手術期間被外力變更（未覆蓋、正檔保持外力版本）")
        os.replace(tmp, a.conf)                             # Windows 原子換入
    except BaseException as e:                              # 三輪必改 1 殘項：SystemExit 也要清 tmp
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass
        if isinstance(e, KeyboardInterrupt):
            raise
        raise SystemExit("ABORT: %s（正檔未被覆蓋；備份在 %s）" % (e, bak))

    # ---------- 換入後復驗（C-07 第 3 段）——交易化：一切可恢復例外都進回滾判定（D-01） ----------
    problems = []
    try:
        chk = open(a.conf, "rb").read()
        if chk != expected_bytes:
            problems.append("換入後 bytes ≠ expected")
        else:
            _r, _t, cseg, ctail, chash, _fid = read_conf(a.conf)
            if chash != md5_of_segment(cseg):
                problems.append("換入後 MD5 不自洽")
            if not deep_eq(strict_loads(cseg, "換入後 conf"), expected_tree):
                problems.append("換入後樹 ≠ 預期樹")
    except SystemExit as e:            # read_conf/strict_loads 的守衛失敗
        problems.append(str(e))
    except Exception as e:             # D-01：OSError 等一般例外一樣進交易處理
        problems.append("復驗例外 %r" % e)

    if problems:
        # ---------- 回滾（D-02：ownership 檢查——只回滾「腳本擁有」的內容） ----------
        try:
            cur = open(a.conf, "rb").read()
        except Exception as e2:
            raise SystemExit("ABORT: 復驗失敗且正檔不可讀（人工介入！正檔=%s 備份=%s；%r）"
                             % (a.conf, bak, e2))
        if cur == raw:
            raise SystemExit("ABORT: 復驗失敗（正檔已是術前內容、無需回滾）：%s" % "；".join(problems))
        if cur != expected_bytes:
            # 外力已寫入新版本＝腳本不再擁有正檔 → 禁止覆蓋（D-02）；
            # expected artifact 落盤供人工比對（三輪必改 2 殘項）
            exp_path = a.conf + ".expected-comborename-" + ts
            try:
                write_verified_tmp(exp_path, expected_bytes)
            except Exception as e3:
                exp_path = "（落盤失敗 %r）" % e3
            raise SystemExit("ABORT: 復驗失敗且正檔已被外力改寫——不回滾以免蓋掉較新版本"
                             "（人工介入！正檔=%s 備份=%s 期望版=%s；問題：%s）"
                             % (a.conf, bak, exp_path, "；".join(problems)))
        # 回滾前查 app（fail-closed；app 開著不自動回滾）
        try:
            if app_running():
                raise RuntimeError("app 已啟動")
        except (SystemExit, Exception) as e2:
            raise SystemExit("ABORT: 復驗失敗且回滾前置檢查未過（%s）——不自動回滾"
                             "（人工：關閉 app 後將備份 %s 複製回 %s）"
                             % (e2, bak, a.conf))
        try:
            rtmp = a.conf + ".tmp-rollback-" + ts
            write_verified_tmp(rtmp, raw)                   # E-03：rollback tmp 同樣驗後才准換入
            # ownership 再驗（緊貼 replace）：正檔必須仍是 expected_bytes
            if open(a.conf, "rb").read() != expected_bytes:
                os.remove(rtmp)
                raise RuntimeError("回滾前正檔又被外力改寫——放棄自動回滾")
            os.replace(rtmp, a.conf)
            if open(a.conf, "rb").read() != raw:
                raise RuntimeError("回滾後 bytes 仍不符")
            print("[rollback] 已還原術前內容")
        except Exception as e2:
            raise SystemExit("ABORT: 復驗失敗且回滾異常（人工介入！正檔=%s 備份=%s；%r）"
                             % (a.conf, bak, e2))
        raise SystemExit("ABORT: 復驗失敗已回滾：%s" % "；".join(problems))

    print("[done] %d 種、%d 處換名完成；bytes/MD5/樹三重復驗過；備份＝%s"
          % (len(hits_text), total, os.path.basename(bak)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
