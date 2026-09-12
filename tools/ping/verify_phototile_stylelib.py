# -*- coding: utf-8 -*-
"""閘門：照片磚工作室頁內嵌的款式庫，必須與款式庫 JSON 正本語意相同。

為什麼需要這道閘門
------------------
產品用 `file://` 載工作室頁（`src/slic3r/GUI/WebViewDialog.cpp` 的 phototile URL），
所以頁面**不能 fetch 同目錄的 JSON**（file:// origin 會被 CORS 擋）。
唯一可行的做法是把款式庫內嵌成 `<script id="ptStyleLib" type="application/json">`。

代價＝同一份資料存在兩處。**改了 JSON 忘了同步內嵌副本，畫面不會報錯、只會安靜地用舊款式庫**
——這正是最難發現的一類 bug。這支就是把那個沉默變成一次 build 前的紅燈。

用法
----
    python tools/ping/verify_phototile_stylelib.py          # 檢查（exit 0 / 1）
    python tools/ping/verify_phototile_stylelib.py --sync   # 用 JSON 正本覆寫內嵌副本
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "resources" / "web" / "phototile"
INDEX = WEB / "index.html"
LIBJSON = WEB / "款式庫_照片磚.json"

BLOCK = re.compile(
    r'(<script id="ptStyleLib" type="application/json">)(.*?)(</script>)',
    re.S,
)

REQUIRED_STYLE_KEYS = {
    "id", "name", "requiresAI", "subjects", "tones", "mode", "slots",
    "preserves", "drops", "minTileMm", "priority",
    # lockSlots＝料色鎖不鎖（Eric 2026-08-17 裁）。頁面用 `s.lockSlots===false` 判斷，
    # 缺了會被當成 undefined ⇒ 靜默走鎖定分支、本地款式又變回鎖死料色。
    "lockSlots",
}
NOZZLES = {"0.4", "0.6", "1.0"}          # 引擎 NOZZLES 白名單；沒有 0.8


def fail(msg):
    print("FAIL  " + msg)
    return 1


def check_unit_cost(root):
    """C++ 的單價常數必須等於款式庫正本的 unitCostNtd.low。

    為什麼要這條：頁面從 JSON 讀價、C++ 的金鑰對話框要顯示累計金額也需要價
    ⇒ 同一個數字存在兩處。這是本檔開頭那個「改了一邊忘了另一邊、畫面不報錯只是安靜錯」
    的同型風險，差別只在它錯的是**錢**。
    """
    hdr = root / "src" / "slic3r" / "Utils" / "PingAiImage.hpp"
    if not hdr.exists():
        return []                      # 還沒有丙案的線就不管這條
    truth = json.loads(LIBJSON.read_text(encoding="utf-8"))
    want = (truth.get("constants", {}).get("aiImage", {}).get("unitCostNtd", {}) or {}).get("low")
    if want is None:
        return ["款式庫正本缺 constants.aiImage.unitCostNtd.low"]
    m = re.search(r"constexpr\s+double\s+UNIT_COST_NTD_LOW\s*=\s*([0-9.]+)\s*;",
                  hdr.read_text(encoding="utf-8"))
    if not m:
        return ["PingAiImage.hpp 找不到 UNIT_COST_NTD_LOW"]
    got = float(m.group(1))
    if abs(got - float(want)) > 1e-9:
        return ["單價不一致：JSON=%s／PingAiImage.hpp=%s（正本是 JSON）" % (want, got)]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true",
                    help="用 JSON 正本覆寫 index.html 的內嵌副本")
    args = ap.parse_args()

    bad = 0
    for msg in check_unit_cost(REPO):
        bad |= fail(msg)
    for p in (INDEX, LIBJSON):
        if not p.exists():
            return fail("找不到 %s" % p)

    raw = LIBJSON.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        # 0816 鐵則：這批 JSON 用 PowerShell 文字模式寫回會加 BOM，JSON 立刻解不開
        bad |= fail("%s 有 UTF-8 BOM（不可用 PowerShell 文字模式寫回，改用 Python 二進位）"
                    % LIBJSON.name)
        raw = raw[3:]
    try:
        truth = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return fail("%s 不是合法 JSON：%s" % (LIBJSON.name, e))

    html = INDEX.read_text(encoding="utf-8")
    m = BLOCK.search(html)
    if not m:
        return fail('index.html 找不到 <script id="ptStyleLib" type="application/json"> 區塊')

    if args.sync:
        packed = json.dumps(truth, ensure_ascii=False, separators=(",", ":"))
        INDEX.write_text(html[:m.start(2)] + packed + html[m.end(2):],
                         encoding="utf-8", newline="")
        print("SYNC  內嵌副本已由 %s 覆寫（%d bytes）" % (LIBJSON.name, len(packed.encode())))
        return 0

    try:
        inlined = json.loads(m.group(2))
    except Exception as e:
        return fail("內嵌區塊不是合法 JSON：%s" % e)

    # ① 語意相同（不比字面，容許縮排/鍵序不同——比的是資料）
    if inlined != truth:
        bad |= fail("內嵌副本與 %s 不一致。跑 --sync 同步，或確認哪一邊才是你要的。"
                    % LIBJSON.name)
        for k in sorted(set(inlined) | set(truth)):
            if inlined.get(k) != truth.get(k):
                print("      差異鍵：%s" % k)
    else:
        print("PASS  內嵌副本與正本語意相同（%d 款式／%d 題材）"
              % (len(truth["styles"]), len(truth["subjects"])))

    # ② 結構完備（頁面邏輯讀得到的鍵一個都不能缺，缺了是畫面壞掉而不是報錯）
    subject_ids = {s["id"] for s in truth["subjects"]}
    for s in truth["styles"]:
        miss = REQUIRED_STYLE_KEYS - set(s)
        if miss:
            bad |= fail("款式 %s 缺鍵：%s" % (s.get("id", "?"), sorted(miss)))
            continue
        unknown = set(s["subjects"]) - subject_ids
        if unknown:
            bad |= fail("款式 %s 指到不存在的題材：%s" % (s["id"], sorted(unknown)))
        if set(s["minTileMm"]) != NOZZLES:
            bad |= fail("款式 %s 的 minTileMm 鍵必須恰為 %s（頁面用 toFixed(1) 查表），實際 %s"
                        % (s["id"], sorted(NOZZLES), sorted(s["minTileMm"])))
        want_slots = 4 if s["mode"] == "quad" else 2
        if len(s["slots"]) != want_slots:
            bad |= fail("款式 %s 是 %s，料色該有 %d 支，實際 %d"
                        % (s["id"], s["mode"], want_slots, len(s["slots"])))
        if not 2 <= s["tones"] <= 8:
            # 色階上限 8＝Eric 2026-08-02 裁（引擎 clamp 同值）
            bad |= fail("款式 %s 的 tones=%s 超出 2~8" % (s["id"], s["tones"]))

    # ③ 每個題材至少要有一個款式，否則使用者選到它會看到空清單
    for sid in sorted(subject_ids):
        if not [s for s in truth["styles"] if sid in s["subjects"]]:
            bad |= fail("題材 %s 沒有任何款式" % sid)

    # ④ 誠實登記：哪些題材在「沒有 AI」時無款可用（階段 A 的真實狀態，不是錯誤）
    local_only = [sid for sid in sorted(subject_ids)
                  if not [s for s in truth["styles"]
                          if sid in s["subjects"] and not s["requiresAI"]]]
    if local_only:
        print("INFO  沒有本地款式的題材（階段 A 會顯示「沒有款式可用」）：%s" % local_only)

    if not bad:
        print("OK    款式庫閘門全過")
    return bad


if __name__ == "__main__":
    sys.exit(main())
