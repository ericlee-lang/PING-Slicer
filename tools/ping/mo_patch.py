"""PING: 把新增 UI 字串的繁中翻譯 patch 進現成 .mo（坑 #16：CI 不跑 gettext，.mo 是 repo 預存檔）。

GNU .mo 格式單純（magic/N/原文表/譯文表），解析全部 entries 後加入新翻譯重寫。
hash 表寫 0（wxMsgCatalog 不用 hash 表，二分原文表即可）。

用法：python mo_patch.py            # patch zh_TW 的 OrcaSlicer.mo + PINGSlicer.mo
"""
import io
import os
import re
import struct
import sys

MAGIC_LE = 0x950412DE

# 新增字串：msgid（必須與 C++ L() 字串 byte-for-byte 一致）→ 繁中翻譯
NEW_ENTRIES = {
    # PING(2026-07-09)：新增實例 tooltip 補說明（Eric 給的文案）
    (
        "Creates a linked copy of the object. Unlike a plain copy, instances stay in sync "
        "with the original and use less system resources."
    ): "建立一個與原物件連動的複製品（跟單純複製不同），可節省系統資源。",
    # PING(2026-07-09)：print_host 說明改短版（去 HAProxy 帳密@URL 段——非 PING 用法，Eric 定）
    (
        "PING Slicer can upload G-code files to a printer host. This field should contain "
        "the hostname, IP address or URL of the printer host instance."
    ): "PING Slicer 可以將 G-code 檔案上傳到列印設備。此欄位填列印設備的主機名、IP 位址或 URL。",
    "Purge idle filaments every": "閒置線材沖刷間隔",
    (
        "For shared-nozzle multi-material hotends (2-in-1-out / 4-in-1-out), filaments that "
        "are not being printed keep sitting in the hot end and degrade over time. "
        "When set to a value N greater than zero, every filament used by this print is purged "
        "on the prime tower after sitting idle for N layers, even on layers where it does not "
        "print anything. Set to 1 to refresh every filament on every layer. 0 disables this."
    ): (
        "兩進一出／四進一出共用噴頭的多色列印中，未在列印的線材會持續停留在噴頭內並隨時間劣化。"
        "設為大於 0 的數值 N 時，本次列印使用的每一支線材只要連續閒置 N 層，"
        "就會在換料塔上沖刷一次（即使該層沒有使用它）。"
        "設為 1 表示每一層更新所有線材；0 表示停用。"
    ),
    # PING(2026-08-09 Eric 令)：收縮補償警告改「不一致」——英文原文 "does not match" 沒有門檻，
    # 原譯「差異過大」會讓人以為差一點沒關係（實際差 0.1% 也整個停用，Print.cpp:3623）。
    (
        "Filament shrinkage will not be used because filament shrinkage for the used "
        "filaments does not match."
    ): "線材收縮補償將被停用，因為所使用的線材收縮率不一致。",
    # PING(2026-08-17 I18N-02)：補完 7/9 品牌清洗漏掉的 .mo 配套。
    # Eric 0817 三裁：校正項目名（Orca Cube/YOLO…）保留 Orca；C5 用「開啟來自下列網站的模型：」；本批走 mo_patch。
    # A. 原本 .mo 查無此 msgid ⇒ 繁中顯示英文（詞法掃描確認，已排除註解死碼）
    # C1 SysInfoDialog  src/slic3r/GUI/SysInfoDialog.cpp:151
    "Blacklisted libraries loaded into PING Slicer process:": "已載入 PING Slicer 程序的黑名單程式庫：",
    # C2 Snapshot 標題  src/slic3r/Config/Snapshot.cpp:597
    "PING Slicer error": "PING Slicer 錯誤",
    # C3 Snapshot  src/slic3r/Config/Snapshot.cpp:596
    "PING Slicer has encountered an error while taking a configuration snapshot.": "PING Slicer 在建立設定快照時發生錯誤。",
    # C4 換料塔（沿用舊譯換品牌字）  src/slic3r/GUI/WipeTowerDialog.cpp:328
    "PING Slicer would re-calculate your flushing volumes everytime the filaments color changed or filaments changed. You could disable the auto-calculate in PING Slicer > Preferences": "每當線材顏色變更或線材變更時，PING Slicer 都會重新計算您的沖洗體積。您可以在 PING Slicer > 偏好設定中停用自動計算",
    # C5 網頁連結關聯 tooltip（Eric 0817 定稿）  src/slic3r/GUI/Preferences.cpp:1154
    "with PING Slicer so that it can open models from": "開啟來自下列網站的模型：",
    # B. msgid 查得到但中文仍寫 Orca（值不同即覆蓋）
    # F1 使用者預設同步
    "\n\nOrca has detected that your user presets synchronization function is not enabled, which may result in unsuccessful Filament settings on the Device page.\nClick \"Sync user presets\" to enable the synchronization function.": "\n\nPING Slicer 偵測到您的使用者預設同步功能尚未啟用，這可能導致線材設定在裝置頁面上無法正常使用。\n請點擊『同步使用者預設』以啟用同步功能。",
    # F3 記住線材/製程
    "If enabled, Orca will remember and switch filament/process configuration for each printer automatically.": "啟用後，PING Slicer 會記住且自動切換各機臺線材與列印設定。",
    # F4 連線偏差
    "Junction deviation setting exceeds the printer's maximum value (machine_max_junction_deviation).\nOrca will automatically cap the junction deviation to ensure it doesn't surpass the printer's capabilities.\nYou can adjust the machine_max_junction_deviation value in your printer's configuration to get higher limits.": "連線偏差設定超出列印設備的最大值 (machine_max_junction_deviation)。\nPING Slicer 將自動限制連線偏差，以確保其不會超出列印設備的能力。\n您可以調整列印設備配置中的 machine_max_junction_deviation 值以獲得更高的限制。",
    # F10 API Key 說明
    "PING Slicer can upload G-code files to a printer host. This field should contain the API Key or the password required for authentication.": "PING Slicer 可以將 G-code 檔案上傳到列印設備。此欄位應包含用於身份驗證的 API 金鑰或密碼。",
    # F12 加速度（另修參數名筆誤）
    "The acceleration setting exceeds the printer's maximum acceleration (machine_max_acceleration_extruding).\nOrca will automatically cap the acceleration speed to ensure it doesn't surpass the printer's capabilities.\nYou can adjust the machine_max_acceleration_extruding value in your printer's configuration to get higher speeds.": "加速度設定已超過列印設備的最大加速度值 (machine_max_acceleration_extruding)。\nPING Slicer 將自動限制加速度，以確保不超出列印設備的性能範圍。\n如需更高速度，您可以在列印設備配置中調整 machine_max_acceleration_extruding 值。",
    # F13 韌體更新
    "The firmware version is abnormal. Repairing and updating are required before printing. Do you want to update now? You can also update later on printer or update next time starting Orca.": "韌體版本異常，必須修復並更新後才能列印。您要現在更新嗎？也可以稍後在列印設備上更新，或在下次啟動 PING Slicer 時進行更新。",
    # F14 急動
    "The jerk setting exceeds the printer's maximum jerk (machine_max_jerk_x/machine_max_jerk_y).\nOrca will automatically cap the jerk speed to ensure it doesn't surpass the printer's capabilities.\nYou can adjust the maximum jerk setting in your printer's configuration to get higher speeds.": "抖動設定已超過列印設備的最大急動值（machine_max_jerk_x/machine_max_jerk_y）。\nPING Slicer 將自動限制急動速度，以確保不超出列印設備的性能範圍。\n如需更高速度，您可以在列印設備配置中調整最大急動值。",
    # F15 移動加速度
    "The travel acceleration setting exceeds the printer's maximum travel acceleration (machine_max_acceleration_travel).\nOrca will automatically cap the travel acceleration speed to ensure it doesn't surpass the printer's capabilities.\nYou can adjust the machine_max_acceleration_travel value in your printer's configuration to get higher speeds.": "移動加速度設定已超過列印設備的最大移動加速度值（machine_max_acceleration_travel）。\nPING Slicer 將自動限制移動加速度，以確保不超出列印設備的性能範圍。\n如需更高速度，您可以在列印設備配置中調整 machine_max_acceleration_travel 值。",
    # F16 換料預熱
    "To reduce the waiting time after tool change, Orca can preheat the next tool while the current tool is still in use. This setting specifies the time in seconds to preheat the next tool. Orca will insert a M104 command to preheat the tool in advance.": "為了縮短工具更換後的等待時間，PING Slicer 可在目前工具使用期間提前預熱下一個工具。此設定用於指定預熱下一個工具的時間（單位：秒）。PING Slicer 將自動插入 M104 指令以提前進行工具預熱。",
}


def read_mo(path):
    data = open(path, "rb").read()
    magic = struct.unpack("<I", data[:4])[0]
    assert magic == MAGIC_LE, f"{path}: not a little-endian .mo"
    n, off_o, off_t = struct.unpack("<III", data[8:20])
    entries = []
    for i in range(n):
        olen, ooff = struct.unpack("<II", data[off_o + i * 8 : off_o + i * 8 + 8])
        tlen, toff = struct.unpack("<II", data[off_t + i * 8 : off_t + i * 8 + 8])
        entries.append((data[ooff : ooff + olen], data[toff : toff + tlen]))
    return entries


def write_mo(path, entries):
    entries = sorted(entries, key=lambda e: e[0])  # 原文需排序（二分查找）
    n = len(entries)
    header = 28
    table_o = header
    table_t = table_o + n * 8
    strings_start = table_t + n * 8
    blob = bytearray()
    offsets = []
    for orig, trans in entries:
        o_off = strings_start + len(blob)
        blob += orig + b"\x00"
        t_off = strings_start + len(blob)
        blob += trans + b"\x00"
        offsets.append((len(orig), o_off, len(trans), t_off))
    out = bytearray()
    out += struct.pack("<7I", MAGIC_LE, 0, n, table_o, table_t, 0, 0)
    for olen, ooff, _, _ in offsets:
        out += struct.pack("<II", olen, ooff)
    for _, _, tlen, toff in offsets:
        out += struct.pack("<II", tlen, toff)
    out += blob
    open(path, "wb").write(bytes(out))


def patch(path):
    entries = read_mo(path)
    existing = {orig: i for i, (orig, _) in enumerate(entries)}
    added = updated = 0
    for msgid, msgstr in NEW_ENTRIES.items():
        k, v = msgid.encode("utf-8"), msgstr.encode("utf-8")
        if k in existing:
            if entries[existing[k]][1] != v:
                entries[existing[k]] = (k, v)
                updated += 1
        else:
            entries.append((k, v))
            added += 1
    write_mo(path, entries)
    print(f"{path}: {len(entries)} entries (added {added}, updated {updated})")


# ---------------------------------------------------------------------------
# PING(2026-08-17)：跑完 .mo 就順手把 .po 同步回來。
#
# 為什麼要有這段：CMake 的 gettext_po_to_mo 是獨立 custom target、不在 ALL_BUILD 內
# ⇒ .po 不是生效來源（產品吃 repo 預存的 .mo）。但 .po 是唯一 grep 得到的可讀來源，
# 一旦漂移，後人 grep 到的就是過期譯文。0817 人工補平過一次（補 86 條、修 11 條），
# 補完隨即發現：只要有人跑了本腳本而沒同步 .po，下一秒就再度漂移 ⇒ 併進工具才根治。
#
# 合併式，不是重生：只改「值不同」的 msgstr、只追加「.po 沒有」的 msgid，
# 既有註解（#: 出處、#. 說明、#, 旗標）與複數形區塊一律原樣保留，不刪任何條目。
# ---------------------------------------------------------------------------

_PO_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
_PO_KW = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+"(.*)"\s*$')
_PO_STR = re.compile(r'^"(.*)"\s*$')


def _po_unescape(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(_PO_ESCAPES.get(s[i + 1], "\\" + s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _po_escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n"))


def _po_emit(keyword, value):
    """多行字串照 gettext 慣例：含換行就 keyword "" 後逐行續行。"""
    if "\n" not in value:
        return ['%s "%s"' % (keyword, _po_escape(value))]
    parts = value.split("\n")
    lines = ['%s ""' % keyword]
    for i, seg in enumerate(parts):
        if i < len(parts) - 1:
            lines.append('"%s\\n"' % _po_escape(seg))
        elif seg:
            lines.append('"%s"' % _po_escape(seg))
    return lines


def _po_blocks(text):
    """切成 [(註解行, [[keyword, [片段…]], …]), …]；認不得的行原樣留在註解區。"""
    blocks, cur_c, cur_e = [], [], []
    for line in text.split("\n"):
        if line.strip() == "":
            if cur_c or cur_e:
                blocks.append((cur_c, cur_e))
                cur_c, cur_e = [], []
            continue
        if line.startswith("#"):
            if cur_e:                       # 註解代表新區塊開始
                blocks.append((cur_c, cur_e))
                cur_c, cur_e = [], []
            cur_c.append(line)
            continue
        m = _PO_KW.match(line)
        if m:
            cur_e.append([m.group(1), [m.group(2)]])
            continue
        m = _PO_STR.match(line)
        if m and cur_e:
            cur_e[-1][1].append(m.group(1))
            continue
        cur_c.append(line)
    if cur_c or cur_e:
        blocks.append((cur_c, cur_e))
    return blocks


def sync_po(po_path, mo_path):
    if not os.path.exists(po_path):
        print(f"{po_path}: 不存在，略過 .po 同步")
        return
    mo = {o.decode("utf-8"): t.decode("utf-8") for o, t in read_mo(mo_path)}
    with io.open(po_path, encoding="utf-8", newline="") as f:
        blocks = _po_blocks(f.read())

    seen, n_upd, out = set(), 0, []
    for comments, entries in blocks:
        kws = {e[0]: e for e in entries}
        rewrite = None
        if "msgid" in kws:
            msgid = _po_unescape("".join(kws["msgid"][1]))
            ctxt = _po_unescape("".join(kws["msgctxt"][1])) if "msgctxt" in kws else None
            key = (ctxt + "\x04" + msgid) if ctxt is not None else msgid
            if key in mo:
                seen.add(key)
                if "msgid_plural" not in kws and "msgstr" in kws and key != "":
                    if _po_unescape("".join(kws["msgstr"][1])) != mo[key]:
                        rewrite, n_upd = mo[key], n_upd + 1
        out.extend(comments)
        for e in entries:
            if rewrite is not None and e[0] == "msgstr":
                out.extend(_po_emit("msgstr", rewrite))
            else:
                out.append('%s "%s"' % (e[0], e[1][0]))
                out.extend('"%s"' % s for s in e[1][1:])
        out.append("")

    # ⚠ 追加時必須排除兩種特殊鍵，否則會把控制字元寫進 .po（0817 沙箱實測寫進 18 個 NUL）：
    #   "\x00" ＝ 複數形（.mo 存成 singular\0plural）、"\x04" ＝ msgctxt（存成 ctxt\4msgid）
    # 兩者在 .po 端本來就有 msgid_plural／msgctxt 區塊，不需也不可追加。
    missing = sorted(k for k in mo
                     if k not in seen and k != "" and "\x00" not in k and "\x04" not in k)
    if missing:
        out += ["#",
                "# ==== 以下由 tools/ping/mo_patch.py 自動補入：只存在於入版 .mo 的條目 ====",
                "# .po 不是生效來源（CMake 的 gettext_po_to_mo 不在 ALL_BUILD 內），",
                "# 產品吃 resources/i18n/zh_TW/*.mo。改譯文請走本腳本，見 SOP_翻譯與i18n入版.md。",
                "#", ""]
        for k in missing:
            out += _po_emit("msgid", k) + _po_emit("msgstr", mo[k]) + [""]

    with io.open(po_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")
    print(f"{po_path}: synced (updated {n_upd}, appended {len(missing)})")


if __name__ == "__main__":
    # PING(2026-08-09)：原本寫死開發線絕對路徑 ⇒ 不論在哪個 worktree 跑都會去改開發線的 .mo
    #（本次實爆：在出貨線跑，結果改到 PING-Slicer 那份）。改成相對本檔推導 repo 根。
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    base = os.path.join(repo, "resources", "i18n", "zh_TW")
    for name in ("OrcaSlicer.mo", "PINGSlicer.mo"):
        patch(os.path.join(base, name))
    # PING(2026-08-17)：.mo 改完就同步 .po，避免兩者再度漂移（見上方說明）。
    sync_po(os.path.join(repo, "localization", "i18n", "zh_TW", "OrcaSlicer_zh_TW.po"),
            os.path.join(base, "OrcaSlicer.mo"))
