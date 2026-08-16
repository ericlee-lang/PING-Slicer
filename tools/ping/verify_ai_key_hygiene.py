#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PING AI 金鑰衛生閘門（P3「子」，2026-08-16）

守的是 PingAiKeyStore.hpp 檔頭那三條紀律——它們是「寫在註解裡的規矩」，
而寫在註解裡的規矩下一棒一定會改掉。這支把它們變成會紅的東西。

檢查六條：
  C1 秘密識別字（service／user 常數）只准出現在存取層一個檔
  C2 明文取用 PingAiKey::load( 的呼叫點受白名單管制
  C3 網頁層（resources/web/）完全不得出現金鑰相關識別字
  C4 存取層不得碰 AppConfig（PINGSlicer.conf 會被備份、同步、打包）
  C5 log 敘述不得把金鑰變數送進去
  C6 3mf／匯出／報價包等「會產出檔案給別人」的地方不得引用存取層

用法：
  python verify_ai_key_hygiene.py            # 對本 repo 跑閘門
  python verify_ai_key_hygiene.py --self-test # 反向測試：故意弄壞，確認每條真的會紅
"""

import os
import re
import sys
import tempfile

try:                       # 踩坑 #10：PS 5.1 主控台是 cp950，印中文會爆
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SECRET_MARKERS = ["PING-Slicer/AI-Image"]
STORE_IMPL     = "src/slic3r/Utils/PingAiKeyStore.cpp"
STORE_HDR      = "src/slic3r/Utils/PingAiKeyStore.hpp"

# 🔴 白名單＝「誰可以拿到明文」。要新增一個呼叫點就得改這裡，
#    而改這裡會逼你回頭讀 PingAiKeyStore.hpp 檔頭第 3 條。這是刻意的摩擦。
PLAINTEXT_READERS = [
    "src/slic3r/GUI/PingAiKeyDialog.cpp",   # 測試連線（Eric 裁二＝乙）
]

WEB_ROOT       = "resources/web"
EXPORT_HINTS   = ["src/libslic3r/Format/", "PingQuotePack", "PingQuoteFormat"]
SCAN_DIRS      = ["src", "resources/web", "tools/ping"]
SCAN_EXT       = (".cpp", ".hpp", ".h", ".c", ".js", ".html", ".py", ".json")
SKIP_PARTS     = (".git", "node_modules", "build")


def iter_files(root):
    for d in SCAN_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP_PARTS]
            for fn in filenames:
                if not fn.endswith(SCAN_EXT):
                    continue
                if ".bak-" in fn:            # 備份檔不算現行碼
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as f:
                        yield rel, f.read()
                except OSError:
                    continue


def check(root):
    """回傳 violations list[(code, rel_path, 說明)]。空 list＝過。"""
    v = []
    gate_self = "tools/ping/verify_ai_key_hygiene.py"

    for rel, text in iter_files(root):
        lines = text.splitlines()

        # C1 秘密識別字只准在存取層
        if rel not in (STORE_IMPL, gate_self):
            for m in SECRET_MARKERS:
                if m in text:
                    v.append(("C1", rel, "秘密識別字「%s」只准出現在 %s" % (m, STORE_IMPL)))

        # C2 明文取用白名單
        if "PingAiKey::load(" in text and rel not in (STORE_IMPL, STORE_HDR, gate_self):
            if rel not in PLAINTEXT_READERS:
                v.append(("C2", rel, "取用金鑰明文（PingAiKey::load）不在白名單內"))

        # C3 網頁層完全不得知情
        if rel.startswith(WEB_ROOT + "/"):
            for pat in ("PingAiKey", "ai_key", "apiKey", "api_key"):
                if pat in text:
                    v.append(("C3", rel, "網頁層出現金鑰識別字「%s」——明文不得進 WebView2" % pat))

        # C4 存取層不得碰 AppConfig
        if rel == STORE_IMPL and ("AppConfig" in text or "app_config" in text):
            v.append(("C4", rel, "存取層引用 AppConfig——金鑰不得進會被備份／同步／打包的設定檔"))

        # C5 log 不得印值
        # 🔴 先剝字串字面值與註解再比對，否則 `<< "PingAiKey: key stored"` 這種
        #    「訊息文字裡剛好有 key」會被誤判成印出金鑰＝假陽性（本閘門第一版實錯，
        #    被乾淨樹對照當場抓到）。同 profile 閘門先 strip_cxx_comments() 的作法。
        if rel in (STORE_IMPL, STORE_HDR) or rel in PLAINTEXT_READERS:
            for i, ln in enumerate(lines, 1):
                if "BOOST_LOG" not in ln:
                    continue
                bare = re.sub(r'"(\\.|[^"\\])*"', '""', ln)   # 去掉 "..." 內容
                bare = re.sub(r"//.*$", "", bare)             # 去掉行末註解
                if re.search(r"<<[^;]*\bkey\b", bare):
                    v.append(("C5", "%s:%d" % (rel, i), "log 敘述把金鑰變數送進去了"))

        # C6 產出檔案給別人的地方不得引用存取層
        if "PingAiKeyStore.hpp" in text and rel not in (STORE_IMPL, STORE_HDR, gate_self):
            if any(h in rel for h in EXPORT_HINTS):
                v.append(("C6", rel, "匯出／格式輸出路徑引用存取層——金鑰可能被寫進產出檔"))

    return v


# ─────────────────────────── 反向測試 ───────────────────────────
CLEAN = {
    STORE_IMPL: 'const char* SECRET_SERVICE = "PING-Slicer/AI-Image";\n'
                'BOOST_LOG_TRIVIAL(info) << "PingAiKey: key stored";\n',
    STORE_HDR:  "bool load(std::string& out);\n",
    "src/slic3r/GUI/PingAiKeyDialog.cpp": "if (!PingAiKey::load(key)) { return; }\n",
    "resources/web/phototile/index.html": "<div>照片磚工作室</div>\n",
    "src/libslic3r/Format/bbs_3mf.cpp": "// 3mf writer\n",
}

CASES = [
    ("C1", "src/slic3r/GUI/Other.cpp", 'wxString s = "PING-Slicer/AI-Image";\n'),
    ("C2", "src/slic3r/GUI/Other.cpp", "std::string k; PingAiKey::load(k);\n"),
    ("C3", "resources/web/phototile/index.html", "<script>var apiKey='x';</script>\n"),
    ("C4", STORE_IMPL, 'const char* S = "PING-Slicer/AI-Image";\nwxGetApp().app_config->set("k", v);\n'),
    ("C5", "src/slic3r/GUI/PingAiKeyDialog.cpp", "BOOST_LOG_TRIVIAL(info) << key;\n"),
    # 假陽性對照：訊息文字裡有 key、但沒真的印值 ⇒ 這一筆**不該**紅，
    # 由乾淨樹（CLEAN 內 STORE_IMPL 就是這種寫法）負責證明。
    ("C6", "src/libslic3r/Format/bbs_3mf.cpp", '#include "slic3r/Utils/PingAiKeyStore.hpp"\n'),
]


def write_tree(root, files):
    for rel, body in files.items():
        full = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(body)


def self_test():
    failures = []

    with tempfile.TemporaryDirectory() as td:
        write_tree(td, CLEAN)
        base = check(td)
        if base:
            failures.append("乾淨樹應該全過，卻報了：%s" % base)
        else:
            print("  ✓ 乾淨樹：0 違規（閘門不會亂紅）")

    for code, rel, body in CASES:
        with tempfile.TemporaryDirectory() as td:
            files = dict(CLEAN)
            files[rel] = files.get(rel, "") + body if rel in files else body
            write_tree(td, files)
            hits = [x for x in check(td) if x[0] == code]
            if hits:
                print("  ✓ %s：注入違規後確實變紅（%s）" % (code, hits[0][2]))
            else:
                failures.append("%s：注入違規後閘門沒紅——這條檢查是空的" % code)

    print("")
    if failures:
        for f in failures:
            print("  ✗ %s" % f)
        print("反向測試失敗 %d 項 ⇒ 閘門本身不可信" % len(failures))
        return 1
    print("反向測試 %d/%d 全過（含乾淨樹對照）" % (len(CASES) + 1, len(CASES) + 1))
    return 0


def main():
    if "--self-test" in sys.argv:
        print("PING AI 金鑰衛生閘門 — 反向測試")
        return self_test()

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    print("PING AI 金鑰衛生閘門 — 掃描 %s" % root)
    v = check(root)
    if not v:
        print("6 條檢查全過（C1 識別字／C2 明文白名單／C3 網頁層／C4 設定檔／C5 log／C6 匯出路徑）")
        return 0
    for code, where, why in v:
        print("  ✗ [%s] %s — %s" % (code, where, why))
    print("違規 %d 筆" % len(v))
    return 1


if __name__ == "__main__":
    sys.exit(main())
