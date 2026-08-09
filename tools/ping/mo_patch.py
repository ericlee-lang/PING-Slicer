"""PING: 把新增 UI 字串的繁中翻譯 patch 進現成 .mo（坑 #16：CI 不跑 gettext，.mo 是 repo 預存檔）。

GNU .mo 格式單純（magic/N/原文表/譯文表），解析全部 entries 後加入新翻譯重寫。
hash 表寫 0（wxMsgCatalog 不用 hash 表，二分原文表即可）。

用法：python mo_patch.py            # patch zh_TW 的 OrcaSlicer.mo + PINGSlicer.mo
"""
import os
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


if __name__ == "__main__":
    # PING(2026-08-09)：原本寫死開發線絕對路徑 ⇒ 不論在哪個 worktree 跑都會去改開發線的 .mo
    #（本次實爆：在出貨線跑，結果改到 PING-Slicer 那份）。改成相對本檔推導 repo 根。
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "resources", "i18n", "zh_TW")
    for name in ("OrcaSlicer.mo", "PINGSlicer.mo"):
        patch(rf"{base}\{name}")
