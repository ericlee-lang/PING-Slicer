# -*- coding: utf-8 -*-
"""crash_symbolize.py — 把 PING Slicer 的 crash log 位址解成「函式 + 原始碼行號」。

用途：Windows 版閃退時 %APPDATA%\\PingSlicer\\log\\crash_*.log 會記下錯誤位址，
但 log 裡印的符號名是「最近的匯出符號」＝幾乎都是騙人的（hid_write、BRepExtrema…）。
真正有用的是 `0x1:0x325DFFD` 這種 `section:offset`，配上同一顆 build 的 PDB 就能解回行號。

前提：**PDB 必須來自同一次 build**（不同 build 的 RVA 完全對不上，會解出無關的函式）。
      CI 產物在 GitHub Actions 該次 run 的 `PDB` artifact（Debug_PDB_*.7z，約 145MB → 解開 1.8GB）：
          gh run list --limit 20
          gh run download <run-id> -n PDB -D <目錄>
          7z x Debug_PDB_*.7z
      驗證同版：PDB 檔的時間戳應與安裝目錄 OrcaSlicer.dll 一致。

用法：
    python crash_symbolize.py <OrcaSlicer.pdb> --log <crash_xxx.log>
    python crash_symbolize.py <OrcaSlicer.pdb> 325DFFD 2805F27        # 直接給 section 1 的 offset
    python crash_symbolize.py <OrcaSlicer.pdb> 1:325DFFD 1:2805F27    # 指定 section

本檔自己解 MSF/PDB，不依賴 WinDbg／DIA SDK／LLVM——那台機器上一個都沒有。
2026-08-28 首次使用：解出 T033 閃退 = GLGizmoMove.cpp:250（instances[-1] 垃圾指標）。
"""
import bisect
import mmap
import re
import struct
import sys

S_PUB32 = 0x110E
DBI_HEADER_SIZE = 64


class Pdb:
    def __init__(self, path):
        self._f = open(path, "rb")
        self.mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        if not self.mm[:24].startswith(b"Microsoft C/C++ MSF 7.00"):
            raise SystemExit("不是 MSF 7.00 格式的 PDB：%s" % path)

        (self.block_size, _free, _nblocks, dir_bytes,
         _unk, block_map_addr) = struct.unpack_from("<6I", self.mm, 32)

        n_dir_blocks = (dir_bytes + self.block_size - 1) // self.block_size
        dir_ids = struct.unpack_from("<%dI" % n_dir_blocks, self.mm, block_map_addr * self.block_size)
        directory = self._read_blocks(dir_ids, dir_bytes)

        n = struct.unpack_from("<I", directory, 0)[0]
        self.sizes = list(struct.unpack_from("<%dI" % n, directory, 4))
        pos = 4 + 4 * n
        self.blocks = []
        for size in self.sizes:
            if size == 0xFFFFFFFF:
                size = 0
            nb = (size + self.block_size - 1) // self.block_size
            self.blocks.append(struct.unpack_from("<%dI" % nb, directory, pos))
            pos += 4 * nb

        self._parse_dbi()
        self._parse_publics()
        self._parse_names()

    # ---------- MSF ----------
    def _read_blocks(self, ids, size):
        out = bytearray()
        for b in ids:
            out += self.mm[b * self.block_size:(b + 1) * self.block_size]
            if len(out) >= size:
                break
        return bytes(out[:size])

    def stream(self, idx):
        size = self.sizes[idx]
        if size == 0xFFFFFFFF:
            size = 0
        return self._read_blocks(self.blocks[idx], size)

    # ---------- DBI：模組表 + section contribution ----------
    def _parse_dbi(self):
        dbi = self.stream(3)
        # 欄位序：vsig, vhdr, age, gsi, buildno, psi, dllver, symrec, dllrbld, modinfo_size, …
        hdr = struct.unpack_from("<iIIHHHHHHiiiiiIiiHHI", dbi, 0)
        self.sym_record_stream = hdr[7]
        modinfo_size, seccontrib_size = hdr[9], hdr[10]

        # ModInfo：名稱固定在 record 起點 +64，整筆 4-byte 對齊
        self.mods = []
        p, end = DBI_HEADER_SIZE, DBI_HEADER_SIZE + modinfo_size
        while p < end:
            _flags, symstream, symbytes, c11, c13, _nsrc = struct.unpack_from("<HhIIIH", dbi, p + 32)
            q = p + 64
            e = dbi.index(b"\0", q); name = dbi[q:e].decode("utf-8", "replace"); q = e + 1
            e = dbi.index(b"\0", q); obj = dbi[q:e].decode("utf-8", "replace"); q = e + 1
            self.mods.append(dict(symstream=symstream, symbytes=symbytes, c11=c11, c13=c13,
                                  name=name, obj=obj))
            p = q + ((4 - (q % 4)) % 4)

        # SectionContribution：(section, offset) → 模組
        self.contribs = []
        p = DBI_HEADER_SIZE + modinfo_size + 4          # +4 跳過 version
        end = DBI_HEADER_SIZE + modinfo_size + seccontrib_size
        while p + 28 <= end:
            sec, _p1, off, size, _ch, modidx, _p2, _d, _r = struct.unpack_from("<HHiiIHHII", dbi, p)
            self.contribs.append((sec, off, size, modidx))
            p += 28
        self.contribs.sort()

    def find_module(self, sec, off):
        i = bisect.bisect_right(self.contribs, (sec, off, 1 << 40, 1 << 20)) - 1
        if i < 0:
            return None
        s, o, size, modidx = self.contribs[i]
        return modidx if (s == sec and o <= off < o + size) else None

    # ---------- 公開符號（函式名） ----------
    def _parse_publics(self):
        sym = self.stream(self.sym_record_stream)
        self._sym = sym
        self.pubs = {}
        off, n = 0, len(sym)
        while off + 4 <= n:
            ln, kind = struct.unpack_from("<HH", sym, off)
            if ln < 2:
                break
            if kind == S_PUB32:
                _flags, o, seg = struct.unpack_from("<IIH", sym, off + 4)
                self.pubs.setdefault(seg, []).append((o, off + 14))
            off += ln + 2
        for seg in self.pubs:
            self.pubs[seg].sort()

    def symbol(self, sec, off):
        arr = self.pubs.get(sec)
        if not arr:
            return None
        i = bisect.bisect_right(arr, (off, 1 << 62)) - 1
        if i < 0:
            return None
        o, p = arr[i]
        e = self._sym.index(b"\0", p)
        return self._sym[p:e].decode("utf-8", "replace"), off - o

    # ---------- /names 字串表（檔名） ----------
    def _parse_names(self):
        info = self.stream(1)
        p = 12 + 16                                     # ver/sig/age + GUID
        strsize, = struct.unpack_from("<I", info, p); p += 4
        strbuf = info[p:p + strsize]; p += strsize
        cnt, _cap = struct.unpack_from("<II", info, p); p += 8
        for _ in range(2):                              # present / deleted bit vectors
            words, = struct.unpack_from("<I", info, p); p += 4 + 4 * words
        named = {}
        for _ in range(cnt):
            ni, si = struct.unpack_from("<II", info, p); p += 8
            e = strbuf.index(b"\0", ni)
            named[strbuf[ni:e].decode()] = si
        self._names = self.stream(named["/names"])

    def _name_at(self, off):
        base = 12                                       # sig + ver + size
        e = self._names.index(b"\0", base + off)
        return self._names[base + off:e].decode("utf-8", "replace")

    # ---------- 行號（C13 line info） ----------
    def line(self, sec, off):
        modidx = self.find_module(sec, off)
        if modidx is None:
            return None
        m = self.mods[modidx]
        if m["symstream"] < 0:
            return dict(mod=m["name"])
        ms = self.stream(m["symstream"])
        start = m["symbytes"] + m["c11"]
        c13 = ms[start:start + m["c13"]]

        files, best, p = {}, None, 0
        while p + 8 <= len(c13):
            kind, size = struct.unpack_from("<II", c13, p); p += 8
            data = c13[p:p + size]
            if kind == 0xF4:                            # DEBUG_S_FILECHKSMS
                q = 0
                while q + 8 <= len(data):
                    nameoff, cbsz, _ctype = struct.unpack_from("<IBB", data, q)
                    files[q] = nameoff
                    q += 6 + cbsz
                    q += (4 - q % 4) % 4
            elif kind == 0xF2:                          # DEBUG_S_LINES
                loff, lseg, _flags, lcode = struct.unpack_from("<IHHI", data, 0)
                if lseg == sec and loff <= off < loff + lcode:
                    q = 12
                    while q + 12 <= len(data):
                        fidx, nlines, blocksz = struct.unpack_from("<III", data, q)
                        for i in range(nlines):
                            lo, lf = struct.unpack_from("<II", data, q + 12 + 8 * i)
                            addr = loff + lo
                            if addr <= off and (best is None or addr > best[0]):
                                best = (addr, lf & 0xFFFFFF, fidx)
                        q += blocksz
            p += size
            p += (4 - p % 4) % 4

        res = dict(mod=m["name"])
        if best:
            res.update(line=best[1], file=self._name_at(files.get(best[2], 0)))
        return res


def addresses_from_log(path, module="OrcaSlicer.dll"):
    """撈出 crash log 裡屬於指定模組的 `section:offset`，依出現順序（＝由上而下的呼叫堆疊）。

    「Show CallStack」那段印的是絕對位址＋假符號名（解到最近的匯出符號，幾乎都無關），
    真正可用的是「Fault address」與「Logical Address」段的 `0xF829EFFD 0x1:0x325DFFD <模組路徑>`。
    其他模組（KERNEL32／ntdll／ping-slicer.exe）的 offset 拿這顆 PDB 解會得到無關的函式，故過濾掉。
    """
    out, seen = [], set()
    pat = re.compile(r"0x[0-9A-Fa-f]+\s+0x([0-9A-Fa-f]+):0x([0-9A-Fa-f]+)\s+(\S.*)$")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for row in fh:
            m = pat.search(row.rstrip())
            if not m or module.lower() not in m.group(3).lower():
                continue
            key = (int(m.group(1), 16), int(m.group(2), 16))
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    pdb_path, rest = args[0], args[1:]

    targets = []
    if rest and rest[0] == "--log":
        targets = addresses_from_log(rest[1])
    else:
        for a in rest:
            sec, _, off = a.rpartition(":")
            targets.append((int(sec, 16) if sec else 1, int(off, 16)))
    if not targets:
        raise SystemExit("沒有要解析的位址。")

    pdb = Pdb(pdb_path)
    for sec, off in targets:
        sym = pdb.symbol(sec, off)
        ln = pdb.line(sec, off)
        where = ""
        if ln and ln.get("line"):
            where = "  %s:%d" % (ln["file"], ln["line"])
        elif ln:
            where = "  [%s]" % ln["mod"]
        print("0x%X:0x%08X  %s%s" % (
            sec, off,
            ("%s +0x%X" % sym) if sym else "<no symbol>",
            where))


if __name__ == "__main__":
    main()
