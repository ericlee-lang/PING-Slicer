"""PING profiles 參照完整性驗證（每次 embed regen 後跑）。

檢查：
1. PING.json 所有 sub_path 檔案存在；檔內 name 與清單一致
2. inherits 指向存在的 preset（且絕非空字串——坑#12：空字串=整包 vendor 載入中止）
3. process/filament 的 compatible_printers 指向存在的 machine preset
4. machine 的 default_print_profile / default_filament_profile 指向存在 preset
5. filename_format 不得以非 ASCII 開頭、'}' 後不得緊接非 ASCII
   （PlaceholderParser rule 邊界限制——中文前綴必須包進 {"X_"} 字串字面值）
6. 主線製程保守值固定為：稀疏填充加速度 5000、空駛加速度 5000、接縫 aligned
   照片磚維持其獨立特調：稀疏填充加速度 10000、空駛加速度 3000、接縫 back
7. 支撐幾何口徑連動（Eric 2026-07-17 裁）：樹狀支撐分支直徑＝口徑×10、
   主體圖案線距＝口徑×8（=支撐線寬/密度12.5%，分子用口徑名目值）；照片磚不套
8. 洗料塔寬度全庫 25（Eric 2026-07-17 裁，蓋掉 0708 的 15；含照片磚——其塔關閉無副作用）
9. 線材洗料塔最小清理量（Eric 2026-07-17 裁）：一般 30、SupPLA 系 60、
   FF 四料高流量噴頭/(3in1) 維持特調 120（同日裁「不蓋」）
10. 機器動力學＝Klipper 實值（Eric 2026-07-17 裁「全機隊」）：FD/FP＝400/5000/jerk7、
    FF＝200/1500/jerk56；DL1016 與 Classic 前代機跳過。時間預估校正用，不改列印行為
13. 爬坡品質（Eric 2026-07-24 裁「加入所有的參數」）：全製程 懸空處降速 1＋四段 50/50/25/10
    ＋橋接流量 0.95（照片磚特調豁免）；全線材 懸空冷卻觸發閾值 25%
14. PVA 水溶支撐線材（Eric 2026-07-24 裁）：PING PVA 存在＋關鍵值
    （PVA 型別／水溶／支撐／220／床 60／風扇 100／閾值 25%／purge 60）
"""
import hashlib
import io
import json
import math
import os
import re
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PINGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "resources", "profiles", "PING")
ROOT_JSON = PINGDIR + ".json"

errors = []

# ★ 組合製程功能歸類名（Eric 0729 裁；Codex 四輪雙審可定稿）。token 抽取＝與 Tab.cpp
# ping_apply_combo_filaments 同規則（@ 前、最後一個 ASCII 空白後），分類判定一律走本組，
# 不再 substring 猜名（二輪必改 9）。
COMBO_CAT_EASY,   COMBO_CAT_PVA      = "易拆(Z0)",      "易拆(Z0)水溶"
COMBO_CAT_EASYPAL, COMBO_CAT_DUAL    = "易拆(Z0)+棧板", "雙料(Z隙)"
COMBO_CAT_DUALPAL                    = "雙料(Z隙)+棧板"
# 🆕 2026-09-19（Eric 兩輪 grill 裁，牌 c-0919-ETR-01；出貨線同批名「易拆樹狀」）：第六個 token「易拆(Z0)樹狀」
#   = 同口徑易拆(Z0) 只換 support_type=tree(auto)／support_style=tree_hybrid／支撐＋支撐面速度 50。
#   列入 COMBO_TOKENS ⇒ 連動表鍵集合／token 契約／每機口徑一支普查自動涵蓋；新品無舊名 ⇒ renamed_from 改驗不得存在。
COMBO_CAT_EASYTREE                   = "易拆(Z0)樹狀"
EASY_TREE_ALLOWED_DIFF = {"name", "setting_id", "renamed_from", "support_type", "support_style",
                          "support_speed", "support_interface_speed"}
COMBO_TOKENS = {COMBO_CAT_EASY, COMBO_CAT_PVA, COMBO_CAT_EASYPAL, COMBO_CAT_DUAL, COMBO_CAT_DUALPAL,
                COMBO_CAT_EASYTREE}
# 🆕 0907 #153（Eric 四裁）：3in1 兩支改名成「… - 高流量噴頭」。名字集中在這裡，
#   下方所有 exact 比對一律引用這兩個常數——SOP §N 第 3 條（內聯複製的條件要改成共用變數）。
#   ⚠ 新名仍含 `(3in1)` 與 `高流量` ⇒ is_hf／PA 豁免／清料 120 三處子字串判定**都還命中**，
#     但那是實查過的結果、不是靠巧合（§N 第 2 條：不依賴「新名碰巧也含某關鍵字」）。
TI_FIL_PLA = "PING PLA(3in1) - 高流量噴頭"
TI_FIL_SUP = "PING SupPLA(3in1) - 高流量噴頭"
TI_FIL_OLD = {"PING PLA(3in1)", "PING SupPLA(3in1)"}   # 改名前的名字，不得復活成 preset 名
COMBO_OLD_TOKENS = {"PLA+SUP", "PLA+PVA", "ABS+SUP", "PLA+PLA", "ABS+ABS"}

def cxx_unescape(s):
    """把 C++ 字面裡的 \\xNN 逸出序列解回 UTF-8 字串（房規：CJK 字面走逸出）。"""
    return re.sub(r'(?:\\x[0-9A-Fa-f]{2})+',
                  lambda m: bytes(int(h, 16) for h in re.findall(r'\\x([0-9A-Fa-f]{2})', m.group(0)))
                            .decode("utf-8", "replace"), s)

def cxx_escape(s):
    """把字串裡的非 ASCII 字元轉成 C++ \\xNN 逸出形（用於比對 C++ 原始碼字面）。"""
    return "".join(c if ord(c) < 128 else "".join("\\x%02X" % b for b in c.encode("utf-8")) for c in s)

def strip_cxx_comments(src):
    """剝掉 C++ 的 // 與 /* */ 註解，供「原始碼字面」型跨層護欄比對用（出貨線同名函式的本線副本；
    verify 刻意不互相 import＝既有慣例）。2026-09-19 反向測試實抓：連動表某列被 `//` 註解掉仍判有效＝假綠。"""
    out, i, n = [], 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(src[i]); i += 1
    return "".join(out)

def combo_token(name):
    """回傳製程名的組合 token（五新名之一）；非組合製程回 None。"""
    at = name.find("@")
    if at <= 0:
        return None
    head = name[:at].rstrip()
    sp = head.rfind(" ")
    if sp < 0:
        return None
    tok = head[sp + 1:]
    return tok if tok in COMBO_TOKENS else None

# 期望配對 baseline（值＝dump 自 Tab.cpp:177-247 現值；四輪修訂 C——配錯在冊線材也要紅）
EXPECTED_COMBO_MAP = {
    COMBO_CAT_EASY:    ("PING PLA - 210", "PING SupPLA"),
    COMBO_CAT_PVA:     ("PING PLA - 210", "PING PVA"),
    COMBO_CAT_EASYPAL: ("PING ABS", "PING SupABS"),
    COMBO_CAT_DUAL:    ("PING PLA - 220", "PING PLA - 220"),
    COMBO_CAT_DUALPAL: ("PING ABS", "PING ABS"),
    COMBO_CAT_EASYTREE: ("PING PLA - 210", "PING SupPLA"),              # 0919：同易拆配料
}
EXPECTED_COMBO_MAP_HF = {
    COMBO_CAT_EASY:    ("PING PLA - 高流量噴頭", "PING SupPLA - 高流量噴頭"),
    COMBO_CAT_PVA:     ("PING PLA - 高流量噴頭", "PING PVA"),
    COMBO_CAT_EASYPAL: ("PING ABS", "PING SupABS"),
    COMBO_CAT_DUAL:    ("PING PLA - 高流量噴頭", "PING PLA - 高流量噴頭"),
    COMBO_CAT_DUALPAL: ("PING ABS", "PING ABS"),
    COMBO_CAT_EASYTREE: ("PING PLA - 高流量噴頭", "PING SupPLA - 高流量噴頭"),  # 0919：同易拆配料
}
# ⓘ 2026-09-20（回移批2，牌 c-0920-ABS-01）：原 EXPECTED_P39（#39「手選 ABS→建議切棧板版」
#   對話框的 source→target 期望表）已隨該對話框整支退役——批2 的材料→製程自動收斂做同一件事。
#   取代它的是下方跨層護欄 §3（批2 三支 C++ 必須在位＋退役函式不得復活）與 §3b（甲案覆蓋盤點）。



def err(msg):
    errors.append(msg)


root = json.load(io.open(ROOT_JSON, encoding="utf-8"))
presets = {}   # name -> (kind, dict)

for kind, key in (("machine_model", "machine_model_list"), ("machine", "machine_list"),
                  ("process", "process_list"), ("filament", "filament_list")):
    for it in root.get(key, []):
        p = os.path.join(PINGDIR, it["sub_path"].replace("/", os.sep))
        if not os.path.isfile(p):
            err(f"[missing] {key}: {it['sub_path']}")
            continue
        d = json.load(io.open(p, encoding="utf-8"))
        if d.get("name") != it["name"]:
            err(f"[name mismatch] {it['sub_path']}: json={d.get('name')!r} list={it['name']!r}")
        presets[it["name"]] = (kind, d)

machines = {n for n, (k, _) in presets.items() if k == "machine"}

for name, (kind, d) in presets.items():
    if kind == "machine_model":
        continue
    inh = d.get("inherits")
    if inh is not None:
        if inh == "":
            err(f"[inherits EMPTY — fatal 坑#12] {name}")
        elif inh not in presets:
            err(f"[inherits missing] {name} -> {inh!r}")
    for cp in d.get("compatible_printers", []) or []:
        if cp not in machines:
            err(f"[compatible_printers missing] {name} -> {cp!r}")
    if kind == "machine":
        dpp = d.get("default_print_profile")
        if dpp and dpp not in presets:
            err(f"[default_print_profile missing] {name} -> {dpp!r}")
        for f in d.get("default_filament_profile", []) or []:
            if f not in presets:
                err(f"[default_filament_profile missing] {name} -> {f!r}")
        # ★ 檢查 12（Eric 2026-08-16 裁・槽位預設護欄；與出貨線同版）——四條都是「已經是這樣、
        #   把它釘住」，動機是這些預設散落在 def_fil_*／ff_extra 範本／照片磚範本三條產線，
        #   被改掉都是靜默的（0813 back-fill 事故即一例）。
        _dfp = d.get("default_filament_profile") or []
        if len(_dfp) >= 2 and "3in1" in name:
            # 🔴 0907 #153 改名連坐：這裡原本硬寫 "PING SupPLA(3in1)"，改名後會直接紅。
            #    名字集中在 TI_FIL_SUP 一處，不再散落（SOP §N 第 3 條）。
            if _dfp[1] != TI_FIL_SUP:
                err(f"[3in1 第二槽必為 {TI_FIL_SUP}] {name} -> {_dfp[1]!r}")
        elif len(_dfp) == 2 and name.startswith(("FD", "DUAL")):
            if "SupPLA" not in _dfp[1]:
                err(f"[雙料機第二槽必為 SupPLA 系] {name} -> {_dfp[1]!r}")
        if name.startswith(("FF600", "FF800")) and not any(
                t in name for t in ("同進", "3in1", "照片磚")):
            if _dfp and set(_dfp) != {"PING PLA - 高流量噴頭"}:
                err(f"[四料本體機四槽必為高流量噴頭支] {name} -> {sorted(set(_dfp))!r}")
        if "同進照片磚" in name and name.startswith(("FF600", "FF800")):
            if _dfp and set(_dfp) != {"PING PLA(照片磚)"}:
                err(f"[FF 照片磚機必為照片磚專用支] {name} -> {sorted(set(_dfp))!r}")
        if ("machine_max_acceleration_x" in d and "DL1016" not in name
                and not re.match(r"^(EDU|DUAL|PING 2|PING 3)", name)):
            V, A, J = ("200", "1500", "56") if "FF" in name else ("400", "5000", "7")
            for key, value in (("machine_max_speed_x", [V, V]), ("machine_max_speed_y", [V, V]),
                               ("machine_max_acceleration_x", [A, A]), ("machine_max_acceleration_y", [A, A]),
                               ("machine_max_acceleration_extruding", [A, A]),
                               ("machine_max_acceleration_travel", [A, A]),
                               ("machine_max_acceleration_retracting", [A, A]),
                               ("machine_max_jerk_x", [J, J]), ("machine_max_jerk_y", [J, J])):
                if d.get(key) != value:
                    err(f"[機器動力學 Klipper 實值] {name}: {key}={d.get(key)!r}, expected {value!r}")
    if kind == "process":
        if d.get("instantiation") == "true":
            expected = ({
                "sparse_infill_acceleration": "10000",
                "travel_acceleration": "3000",
                # 2026-07-20 Eric 裁（照片磚線 d09ab243）：接縫預設 背面→對齊（V 溝配套）
                "seam_position": "aligned",
                # 支撐參數統一（Eric 2026-07-25 裁）：照片磚支撐豁免取消，角度與全庫同 35
                #（爬坡品質＝速度類，仍維持照片磚特調豁免）
                "support_threshold_angle": "35",
                # 支撐開關關閉（Eric 2026-07-25 追裁）：照片磚不需要支撐，開關直接關，
                # 不再停留在「開著但平貼床永遠不生成」的誤導狀態。
                "enable_support": "0",
            } if "照片磚" in name else {
                "sparse_infill_acceleration": "5000",
                "travel_acceleration": "5000",
                # 🔴 Eric 2026-08-26 改裁：接縫 aligned → back（取代 0715）。照片磚維持 aligned＝
                #    它有自己的 0720 裁定「背面→對齊（V 溝配套）」，見上一個分支。
                "seam_position": "back",
                # 爬坡品質（Eric 2026-07-24）：懸空降速四段＋橋接流量；照片磚特調豁免
                # 🔴 2026-08-16 Eric 裁「A+C」**推翻上面 0724 的降速部分**（四段值本身留著當備援）：
                #    A＝`enable_overhang_speed` 全庫關（實測：0.6 黃銅跑 75% 那階的 10 mm/s，
                #       噴頭停留過久、料在裡面滾沸，品質反而變差）
                #    C＝最慢那階 10 → **25**（不取 30：50% 段就是 25，取 30 會讓懸空更多的那段更快＝順序反了）
                #    ⚠ 要放寬回 "1"／"10" 必須是 **Eric 新的一次裁定**，不是實作者順手改這行。
                "enable_overhang_speed": "0",
                "overhang_1_4_speed": "50",
                "overhang_2_4_speed": "50",
                "overhang_3_4_speed": "25",
                "overhang_4_4_speed": "25",
                "bridge_flow": "0.95",
                # 支撐臨界角 35（Eric 2026-07-25 裁，推翻 07-24 的 60；照片磚豁免）
                # 🔴 Orca 基準（= Cura/V2.1 的 55）；兩線相反 Orca = 90 − Cura，見 ping-slicer/orca-sync.md
                "support_threshold_angle": "35",
            })
            # PLA+PVA 專屬製程（Eric 2026-07-25 裁「出」；值＝V2.1 定稿案對帳）：案值特例覆蓋家規。
            # 支撐角 50 ＝ 案值 Cura 40 換算（Orca ＝ 90 − Cura）＝比全庫 35 多支撐＝水溶支撐合理特例。
            _ctok = combo_token(name)
            if _ctok == COMBO_CAT_PVA:
                expected["support_threshold_angle"] = "50"
            # 高流量製程組（Eric 2026-07-30 裁・客戶建誌 FF800 同進實測移植）：加速度逐項取保守
            # ＝travel/sparse 2000（min(客戶 2000, 現值 5000)）⇒ 全庫 5000 斷言對此組豁免；
            # 完整定案值 exact 斷言在檔尾「高流量製程組」區塊（含範圍鎖）。
            if " 高流量 @" in name:
                expected["sparse_infill_acceleration"] = "2000"
                expected["travel_acceleration"] = "2000"
            # jerk 對齊機器上限（Eric 2026-07-20 裁）：FD/FP 系=7、FF 系=40（上限 56 不動）
            expected["default_jerk"] = "40" if "@FF" in name else "7"
            # PA-CF 專屬製程（Eric 2026-08-26 裁）：接縫固定藏背面＝材料特例。
            # 全庫 aligned 的斷言對這 6 支改要求 back，**閘門沒關**——寫錯值一樣會被抓。
            if " PA-CF " in name or " PA-CF@" in name:
                expected["seam_position"] = "back"
            for key, value in expected.items():
                if d.get(key) != value:
                    err(f"[process safety default] {name}: {key}={d.get(key)!r}, expected {value!r}")
            m_nz = re.search(r"\(([\d.]+)\)\s*$", name)
            if m_nz:   # 2026-07-25 Eric 裁「支撐參數全部統一」：照片磚不再豁免（原 and "照片磚" not in name）
                nz = float(m_nz.group(1))
                # 線距 2026-07-22 裁 ×9（密度 10%＝Cura 全庫等效；蓋 7/17 ×8=12.5%）
                # 樹狀 2026-07-25 裁保守配方：分支直徑 ×10→×12（引擎上限 10）、新增分支距離 ×6
                # 主體線距：家規 ×9（密度 10%）；PLA+PVA 專屬製程 ×19（案值密度 5%）
                _spacing = ("%g" % round(nz * 19, 2)) if _ctok == COMBO_CAT_PVA else ("%g" % (nz * 9))
                for key, value in (("tree_support_branch_diameter", "%g" % min(nz * 12, 10.0)),
                                   ("tree_support_branch_distance", "%g" % (nz * 6)),
                                   ("support_base_pattern_spacing", _spacing)):
                    if d.get(key) != value:
                        err(f"[support geometry 口徑連動] {name}: {key}={d.get(key)!r}, expected {value!r}")
                # 頂部接觸面間距（Eric 2026-08-04 裁「70% 密度等效」蓋 0714「一律 0.1」）：
                # 一般支撐＝口徑×3/7 取兩位（密度＝線寬/(間距+線寬)⇒70%；0.25→0.11/0.4→0.17/
                # 0.6→0.26＝Eric 截圖錨值/1.0→0.43）；易拆家族既值不動（介面密＝表面品質、不影響拆）：
                # PLA+SUP/PVA 0.1、ABS+SUP 黃金 0.04、3in1 實心 0（承 0714/0722「不蓋」先例）。
                if _ctok == COMBO_CAT_EASYPAL:
                    _sis = "0.04"
                elif _ctok in (COMBO_CAT_EASY, COMBO_CAT_PVA, COMBO_CAT_EASYTREE):
                    _sis = "0.1"
                elif "3in1" in name:
                    _sis = "0"
                else:
                    _sis = "%g" % round(nz * 3 / 7, 2)
                if d.get("support_interface_spacing") != _sis:
                    err(f"[支撐介面 70% 等效 0804] {name}: support_interface_spacing={d.get('support_interface_spacing')!r}, expected {_sis!r}")
                # 支撐首層密度（同鍵服務 raft 首層）＝10% 全庫（0804；主體類規則全庫套＝0722 ×9 先例，
                # 含 3in1 範本 30%→10%）；raft 機種（ABS 系/棧板 raft_layers≥1）＝貼床抓床維持 100%。
                _rfd = "100%" if str(d.get("raft_layers", "0")) != "0" else "10%"
                if d.get("raft_first_layer_density") != _rfd:
                    err(f"[支撐首層密度 0804] {name}: raft_first_layer_density={d.get('raft_first_layer_density')!r}, expected {_rfd!r}")
                # 普通支撐配方（Eric 2026-07-22 七裁；行為四項同日二裁擴及易拆）：
                # 類型/獨立層高/樣式/圖案＝全支撐；XY＝一般口徑×1（易拆維持 7/14 各自定稿不查）
                expected_recipe = [("support_type", "normal(auto)"),
                                   ("independent_support_layer_height", "0"),
                                   ("support_style", "snug"),
                                   ("support_base_pattern", "rectilinear")]
                # PA-CF 樹狀版（Eric 2026-08-26 追裁「增加一個製程參數，是樹狀支撐」）：
                # 只有帶「樹狀」token 的 3 支換支撐類型；PA-CF 一般版仍走普通支撐配方（Q1 甲）。
                # style 必須明寫 default：ConfigManipulation.cpp:476-479 把「snug＋tree」判為非法配對、
                # 自動退回 default（SupportParameters.hpp:180-183 ⇒ smsTreeOrganic＝Eric 實印那組），
                # 不明寫的話使用者一開檔就吃到「設定已被修正」提示。
                if " PA-CF 樹狀 @" in name:
                    expected_recipe = [("support_type", "tree(auto)"),
                                       ("independent_support_layer_height", "0"),
                                       ("support_style", "default"),
                                       ("support_base_pattern", "rectilinear")]
                # 易拆(Z0)樹狀（Eric 2026-09-19 改裁 Q2＝乙＝有機樹）：style 明寫 organic（UI 才顯示「有機樹」；
                # default 行為相同但 UI 顯示「預設 (網格/有機)」＝Eric 0919 GUI 實看抓到）
                # （同 PA-CF 樹狀）。寫成 tree_hybrid／snug 一律紅。
                elif _ctok == COMBO_CAT_EASYTREE:
                    expected_recipe = [("support_type", "tree(auto)"),
                                       ("independent_support_layer_height", "0"),
                                       ("support_style", "organic"),
                                       ("support_base_pattern", "rectilinear")]
                # PLA+PVA＝易拆類（PVA 為水溶支撐料、與 PLA 不相熔，同 +SUP 家族）
                # ⇒ XY 走易拆家規 口徑×0.75，不套一般支撐的 ×1
                if _ctok == COMBO_CAT_PVA:
                    expected_recipe.append(("support_object_xy_distance", "%g" % round(nz * 0.75, 2)))
                elif _ctok not in (COMBO_CAT_EASY, COMBO_CAT_EASYPAL, COMBO_CAT_EASYTREE) and "3in1" not in name:
                    expected_recipe.append(("support_object_xy_distance", "%g" % round(nz * 1.0, 2)))
                for key, value in expected_recipe:
                    if d.get(key) != value:
                        err(f"[普通支撐配方 0722] {name}: {key}={d.get(key)!r}, expected {value!r}")
                # 樹狀支撐保守配方（Eric 2026-07-25 裁）：只在使用者手動切「混合樹」後生效，
                # 預設 normal(auto)+snug 不受影響。auto_brim 必須為 0，否則 brim_width 被引擎忽略
                #（TreeSupport.cpp:2068）。_organic 兩鍵＝防呆（snug+樹狀會被引擎退回 default＝有機樹）：
                # 🔴 diameter_organic 2.6 是 bug 修——Print.cpp:1532 硬限 ≥2×支撐線寬，
                #    FF 系 1.0 口徑線寬 1.02 需 ≥2.04，舊值 2 會讓那 4 支勾樹狀即切片報錯。
                # wall_count 0＝Eric 2026-07-27 裁「支撐牆數改零」（UI 支撐牆數＝此鍵、普通/樹狀共用：
                # 普通支撐 0=無牆 with_sheath=false；樹狀 0=auto——0725「維持一圈」同鍵被上蓋）
                for key, value in (("tree_support_branch_angle", "30"),
                                   ("tree_support_auto_brim", "0"),
                                   ("tree_support_brim_width", "10"),
                                   ("tree_support_wall_count", "0"),
                                   ("tree_support_branch_diameter_organic", "2.6"),
                                   ("tree_support_branch_angle_organic", "40")):
                    if d.get(key) != value:
                        err(f"[樹狀支撐保守配方 0725] {name}: {key}={d.get(key)!r}, expected {value!r}")
            # 洗料塔寬：全庫 25（0717 裁）；PLA+PVA 專屬製程 45（案值＝劉勝賢現行）
            _tower = "45" if combo_token(name) == COMBO_CAT_PVA else "25"
            if d.get("prime_tower_width") != _tower:
                err(f"[洗料塔寬度 {_tower}] {name}: prime_tower_width={d.get('prime_tower_width')!r}")
            # 洗料塔 0729 三裁（Eric）：錐體＋頂角 30＋最快列印速度 60（0708 肋條裁定退役）
            for key, value in (("wipe_tower_wall_type", "cone"),
                               ("wipe_tower_cone_angle", "30"),
                               ("wipe_tower_max_purge_speed", "60")):
                if d.get(key) != value:
                    err(f"[洗料塔錐體 0729] {name}: {key}={d.get(key)!r}, expected {value!r}")
            # 內外牆加速度 0729（Eric「表面品質與穩定性」）：全機型 1500（本線無 Classic）
            for key in ("outer_wall_acceleration", "inner_wall_acceleration"):
                if d.get(key) != "1500":
                    err(f"[內外牆加速度 1500] {name}: {key}={d.get(key)!r}")
            # 牆體列印方向固定逆時針（Eric 2026-07-30 裁）：全庫 ccw，跳過引擎的
            # reorient_perimeters（PerimeterGenerator.cpp:1424）⇒ 層間迴路方向恆一致
            if d.get("wall_direction") != "ccw":
                err(f"[牆方向固定 ccw 0730] {name}: wall_direction={d.get('wall_direction')!r}")
            # ★ 功能歸類五類值鎖（0730 改名批；Z隙＝一層層高〔三輪更正、非固定 0.2〕）
            _vtok = combo_token(name)
            if _vtok:
                _lh_m = re.match(r"([\d.]+)mm ", name)
                _lh_v = _lh_m.group(1) if _lh_m else None
                if _vtok in (COMBO_CAT_EASY, COMBO_CAT_PVA, COMBO_CAT_EASYPAL, COMBO_CAT_EASYTREE):
                    for zk in ("support_top_z_distance", "support_bottom_z_distance"):
                        if d.get(zk) != "0":
                            err(f"[功能歸類・易拆 Z0] {name}: {zk}={d.get(zk)!r}")
                else:
                    # 🔴 Z隙規則 2026-08-17 由 Eric 改裁：一般家族＝固定 0.2，不再是「一層層高」。
                    # 舊規只套得到雙料機（combo_overrides 只在 is_dual_machine 跑），非雙料機沿用母檔值
                    # ⇒ 全庫散成五種值。Eric 看到「FF800 四料本體是 0、FD300 卻是 0.3」後裁「全部改 0.2」。
                    # 出貨線同批＝054a1f2cde。⚠ 易拆 0 不變（「易拆＝沒有間隙」是命名語意本身）。
                    for zk in ("support_top_z_distance", "support_bottom_z_distance"):
                        if d.get(zk) != "0.2":
                            err(f"[功能歸類・一般 Z隙=0.2] {name}: {zk}={d.get(zk)!r}, expected '0.2'"
                                f"（Eric 2026-08-17 裁，取代舊規「一層層高」）")
                # raft 層數：易拆(Z0)+棧板＝3／雙料(Z隙)+棧板＝3／其餘＝0（單料 _棧板 雙生＝3，見下方 elif）——三族皆 3。
                #   沿革：舊值「ABS 系一律 2」出自 2026-06-10 V3.0「最佳 ABS」定稿；Eric 2026-09-17 同日兩裁，
                #   前裁只改易拆+筏層（本線顯示名＝易拆(Z0)+棧板；牌 c-0917-REL-01）、後裁「三族都改 3」（牌 c-0917-REL-02）
                #   ——後裁蓋前裁。對應產生器＝embed_params.py combo_overrides() 的 startswith("ABS") 那行；改值要兩邊一起改。
                _raft = {COMBO_CAT_EASYPAL: "3", COMBO_CAT_DUALPAL: "3"}.get(_vtok, "0")
                if d.get("raft_layers") != _raft:
                    err(f"[功能歸類・棧板 raft {_raft}] {name}: raft_layers={d.get('raft_layers')!r}, expected {_raft!r}"
                        f"（三族皆 3：易拆(Z0)+棧板／雙料(Z隙)+棧板／單料 _棧板，其餘＝0；Eric 2026-09-17 同日兩裁，後裁蓋前裁）")
                # renamed_from＝字串＋恰為對應舊材料對全名（改名批回溯鏈）
                _new2old = {COMBO_CAT_EASY: "PLA+SUP", COMBO_CAT_PVA: "PLA+PVA",
                            COMBO_CAT_EASYPAL: "ABS+SUP", COMBO_CAT_DUAL: "PLA+PLA",
                            COMBO_CAT_DUALPAL: "ABS+ABS"}
                _rf = d.get("renamed_from")
                if _vtok == COMBO_CAT_EASYTREE:
                    # 0919 新品、沒有改名史 ⇒ **不得帶 renamed_from**（從易拆複製來的那條若沒拿掉，
                    #   兩支會宣稱同一個舊名＝引擎 rename map 1:1 先到先贏，舊 3mf 可能被接到樹狀版）。
                    if "renamed_from" in d:
                        err(f"[功能歸類・易拆樹狀不得有 renamed_from] {name}: {_rf!r}")
                else:
                    _rf_expect = name.replace(" %s @" % _vtok, " %s @" % _new2old[_vtok])
                    if not isinstance(_rf, str) or _rf != _rf_expect:
                        err(f"[功能歸類・renamed_from] {name}: {_rf!r}, expected {_rf_expect!r}")
            # 單料 _棧板 雙生（產生器 PALLET_OVERRIDES；combo_token 回 None 的那一群）：raft_layers＝3。
            #   Eric 2026-09-17 同日兩裁：前裁只改易拆+筏層（本線顯示名＝易拆(Z0)+棧板；本族當時維持 2）、
            #   後裁「三族都改 3」⇒ 本族同步為 3（牌 c-0917-REL-02，後裁蓋前裁）。
            #   本斷言的由來：同日反向測試實抓本族的 raft 值原本**沒有任何斷言**（手改值 verify 照綠）⇒ 補上。
            #   日後再改值：產生器 PALLET_OVERRIDES 與這裡兩邊一起改。
            elif "_棧板 @" in name and d.get("raft_layers") != "3":
                err(f"[單料棧板雙生 raft 3] {name}: raft_layers={d.get('raft_layers')!r}, expected '3'"
                    f"（PALLET_OVERRIDES；Eric 2026-09-17 後裁「三族都改 3」）")
    if kind == "filament":
        if d.get("instantiation") == "true":
            pv = d.get("filament_minimal_purge_on_wipe_tower")
            pv = pv[0] if isinstance(pv, list) and pv else pv
            # 🔴 2026-08-16 改名：「四料高流量噴頭」→「四料同進噴頭」；照片磚專用支同享 120
            expected_pv = ("120" if ("四料同進噴頭" in name or "(照片磚)" in name or "(3in1)" in name)
                           else "85" if "PVA" in name else "60" if "SupPLA" in name else "30")
            # ★ 檢查 13（Eric 2026-08-16 裁・四料同進流量）：同進 PLA 支 50、SupPLA 30、
            #   照片磚專用支 30（豁免，等 Eric 實印再定）。⚠ 放寬必須是 Eric 新的一次裁定。
            _mvs = d.get("filament_max_volumetric_speed")
            _mvs = _mvs[0] if isinstance(_mvs, list) and _mvs else _mvs
            #   🆕 0907 #153 Eric 裁②：3in1 PLA 支 20→30；SupPLA 支未點名＝維持 12
            #      （同 0816「未點名不順手改」）。同樣要放寬得是 Eric 新的一次裁定。
            _want_mvs = {"PING PLA - 四料同進噴頭": "50",
                         "PING SupPLA - 四料同進噴頭": "30",
                         "PING PLA(照片磚)": "30",
                         TI_FIL_PLA: "30",
                         TI_FIL_SUP: "12"}.get(name)
            if _want_mvs and _mvs != _want_mvs:
                err(f"[四料同進流量 0816／3in1 流量 0907] {name}: {_mvs!r}, expected {_want_mvs!r}")
            # ★ 檢查 13b（0907 #153）：改名後的兩支要有一張**新名 → 期望值**的硬表。
            #   SOP §N 第 4 條的教訓：產生器與驗證器的家族判定若都綁同一個名字字串，
            #   **兩邊會一起錯、一起綠**；唯一擋得住的是這種不靠子字串推導的 exact 表。
            _ti_want = {TI_FIL_PLA: {"filament_minimal_purge_on_wipe_tower": "120",
                                     "filament_retraction_length": "3",
                                     "filament_retract_restart_extra": "0.6",
                                     "pressure_advance": "0.4",
                                     "nozzle_temperature": "210"},
                        TI_FIL_SUP: {"filament_minimal_purge_on_wipe_tower": "120",
                                     "filament_retraction_length": "3",
                                     "filament_retract_restart_extra": "0.6",
                                     "pressure_advance": "0.2",
                                     "nozzle_temperature": "210",
                                     "filament_is_support": "1"}}.get(name)
            if _ti_want:
                for _tk, _tv in _ti_want.items():
                    _tg = d.get(_tk)
                    _tg = _tg[0] if isinstance(_tg, list) and _tg else _tg
                    if _tg != _tv:
                        err(f"[3in1 高流量支硬表 0907] {name}: {_tk}={_tg!r}, expected {_tv!r}")
            if name in TI_FIL_OLD:
                err(f"[3in1 舊名不得復活 0907] {name}: 已於 #153 改名，舊名只能待在 renamed_from")
            if pv is not None and pv != expected_pv:
                err(f"[洗料塔最小清理量] {name}: {pv!r}, expected {expected_pv!r}")
            # 檢查 11：降速層時間一律 10 秒（Eric 2026-07-18 裁）＋
            # 🔴 冷卻降速一律**關**（Eric 2026-08-07 裁，翻 0718 自己那條「一律開」）
            #    原話：「經過實測…它是在特殊情況下才需要進行勾選，因此大部分情況下都要取消」
            #    ⇒ 實測為據的翻案，不是迴歸；引擎預設 true 故必須每支明寫 0 才擋得住。
            # 🔴 2026-09-10 Eric 再裁：一般線材降速**開**＋最小列印速度 25；**照片磚系三支維持關**。
            #    起因＝其他同事回報「尖端成型不好」（Eric 明說不是照片磚線）。不算翻 0807——
            #    0807 原話就寫「特殊情況下才需要勾選」，這次是把「一般件」歸進那個情況、照片磚成為例外。
            _cd_is_pt = name in ("PING PLA(照片磚)", "PING PLA(照片磚 FD300)", "PING PLA(照片磚 FD高流量)")
            _cd_want = ["0"] if _cd_is_pt else ["1"]
            if d.get("slow_down_for_layer_cooling") != _cd_want:
                _tag = "照片磚系應關 0910" if _cd_is_pt else "一般線材應開 0910"
                err(f"[冷卻降速 {_tag}] {name}: {d.get('slow_down_for_layer_cooling')!r}, expected {_cd_want!r}")
            # 照片磚系明寫 10（不是「不管」）——那三支是深拷貝派生的，母體改 25 之後
            #   「不設」會讓 25 跨 regen 漂進來（0910 實撞，噴溫也栽過同一個坑）。
            _ms_want = ["10"] if _cd_is_pt else ["25"]
            if d.get("slow_down_min_speed") != _ms_want:
                err(f"[最小列印速度 0910] {name}: {d.get('slow_down_min_speed')!r}, expected {_ms_want!r}")
            if d.get("slow_down_layer_time") != ["10"]:
                err(f"[降速層時間非 10] {name}: {d.get('slow_down_layer_time')!r}")
            # 🆕 G1（Eric 2026-08-13 裁・連動規格批1；出貨線 bdbdcecef5，2026-09-19 回移＝牌 c-0919-BP3-01）：
            #   配料屬性必須**顯式**帶兩鍵。
            # 為什麼：家族軸讀 filament_is_support／filament_soluble（有支撐材⇒易拆；水溶⇒易拆水溶）。
            #   缺鍵時引擎吃 C++ 預設 false／繼承鏈的 0，**行為看起來正常但護欄驗不到**——
            #   屬「缺鍵型靜默」，正是下方 G2 要依賴的地基。
            # ⚠ 這裡讀的是**未解 inherits 的原始檔內容**（presets 的建法），所以「顯式」在此可驗。
            # 產生器對應：embed_params.py `_backfill_filament_attrs()` 4a-0b／4b-2g 兩趟（缺鍵補 ["0"]、已有顯式值不動）。
            for _ak in ("filament_is_support", "filament_soluble"):
                if d.get(_ak) not in (["0"], ["1"]):
                    err(f"[配料屬性須顯式 0813] {name}: {_ak}={d.get(_ak)!r}, expected ['0'] 或 ['1']")
            # 線材回抽統一（Eric 2026-07-23 三裁 → 0819 一般流量改寫）
            # 🔴 Classic 前代豁免：赤兔不能吃韌體回抽（Eric 0807）⇒ 材料層不得覆蓋回抽，
            #    專屬護欄在檔尾「Classic 材料層回抽覆蓋 0807」。
            if name.startswith("PING") and "Classic" not in name:
                def _v(k):
                    x = d.get(k)
                    return x[0] if isinstance(x, list) and x else x
                for k, want in (("filament_retraction_minimum_travel", "3"), ("filament_wipe", "1"),
                                ("filament_wipe_distance", "5"), ("filament_retract_before_wipe", "100%")):
                    if _v(k) != want:
                        err(f"[線材回抽四項 0723] {name}: {k}={_v(k)!r}, expected {want!r}")
                # 🔴 2026-08-16 改名連坐：舊名靠字串「高流量」落進 is_hf，改成「四料同進噴頭」
                #    後會掉出去、被當一般流量（出貨線實測踩到）。照片磚專用支同屬同進硬體。
                # ⚠ 「PING PLA(照片磚 FD300)」不含「(照片磚)」⇒ 刻意落在一般流量側（FD300＝雙料一般流量）。
                is_hf = (("高流量" in name) or ("四料同進" in name)
                         or ("(照片磚)" in name) or ("(3in1)" in name))
                # ⚠ 這裡是**內聯清單**，不吃 embed_params 的常數（兩支是獨立程式）。
                #   新增照片磚專用線材時兩邊都要加——0730 就是漏了這一行，照片磚支被掃成
                #   回抽 3、靜默蓋掉零回抽 20 天。正本＝embed_params.PT_FIL_SPECS。
                is_pt = name in ("PING PLA(照片磚)", "PING PLA(照片磚 FD300)",
                                 "PING PLA(照片磚 FD高流量)")
                # 🔴 四料照片磚噴溫 190（Eric 2026-09-10 裁「四料使用的照片磚參數要特別降到 190 度」）。
                #    只有 `PING PLA(照片磚)`＝FF600／FF800 照片磚六台專用支；雙料照片磚兩支維持 210
                #    （Eric 同日裁「雙料不改」）。溫度統一鐵律 ⇒ 兩個噴溫鍵必須同值。
                #    ⚠️ 與 2026-07-17「0.6 實機 190 塞頭」相反，是 Eric 0910 明確改裁；若實印再塞頭，
                #       回退點＝embed_params 的 PT_FIL_PLA 那兩行＋本條。
                if name == "PING PLA(照片磚)":
                    for _tk in ("nozzle_temperature", "nozzle_temperature_initial_layer"):
                        if _v(_tk) != "190":
                            err(f"[四料照片磚噴溫 190 0910] {name}: {_tk}={_v(_tk)!r}, expected '190'")
                elif name in ("PING PLA(照片磚 FD300)", "PING PLA(照片磚 FD高流量)"):
                    for _tk in ("nozzle_temperature", "nozzle_temperature_initial_layer"):
                        if _v(_tk) != "210":
                            err(f"[雙料照片磚噴溫 210 0910] {name}: {_tk}={_v(_tk)!r}, expected '210'")

                # 🆕 Eric 2026-08-19 令：一般流量「額外回填長度」＝**取消勾選**（nil，退回機器層 0）；
                #    高流量家族維持 0.6。蓋掉 0723 的「一般流量 0.2」。
                # 🔴 四料照片磚 0.2（Eric 2026-09-10「額外裝填 0.6 會擠出蠻多的」）；
                #    FD300 照片磚維持 nil（它本來就沒有額外回填，設 0.2 是增加、方向相反）、
                #    FD高流量照片磚與其餘高流量家族維持 0.6。
                _want_extra = "0.2" if name == "PING PLA(照片磚)" else ("0.6" if is_hf else "nil")
                if _v("filament_retract_restart_extra") != _want_extra:
                    err(f"[額外回填 0819] {name}: {_v('filament_retract_restart_extra')!r}, expected {_want_extra!r}")
                # 🆕 Eric 2026-08-19 令：回抽速度／裝填速度全庫 30/30
                # 🆕 Eric 2026-08-26 裁（Q4 甲）：PA-CF＝40/40（只改線材層、機器層不動）。
                _is_pacf = "PA-CF" in name
                _want_spd = "40" if _is_pacf else "30"
                for _k, _label in (("filament_retraction_speed", "回抽速度"),
                                   ("filament_deretraction_speed", "裝填速度")):
                    if _v(_k) != _want_spd:
                        err(f"[回抽速度 0819/0826] {name}: {_label}={_v(_k)!r} 應 {_want_spd}")
                # 檢查 13 線材側（Eric 2026-07-24 爬坡品質批）：懸空冷卻觸發閾值全線材 25%
                if _v("overhang_fan_threshold") != "25%":
                    err(f"[懸空冷卻閾值 25% 0724] {name}: {_v('overhang_fan_threshold')!r}")
                # 🆕 Eric 2026-09-08 令：ABS 家族「懸空與外部橋接區域的冷卻風扇速度」80%→30%
                #   （ABS 風扇吹太強會翹；ABS 與 SupABS 都要）。基底 fdm_filament_abs 同改、葉檔明寫。
                #   _v 只看葉檔不解析繼承 ⇒ 葉檔必須明寫，靠基底繼承會在這裡被抓成缺值。
                if "ABS" in name and _v("overhang_fan_speed") != "30":
                    err(f"[ABS 懸空風扇 30% 0908] {name}: overhang_fan_speed={_v('overhang_fan_speed')!r} 應 30")
                # 🆕 Eric 2026-09-10 裁（牌 c-0910-ABS-01）：ABS 拆 PEI／玻璃。`PING ABS` 名不動＝PEI 版
                #   （C++ Tab.cpp 組合連動硬寫此名，不改名＝不 build）；玻璃版首層床溫 60、其它層 100。
                if name == "PING ABS(玻璃)" and (_v("hot_plate_temp_initial_layer") != "60" or _v("hot_plate_temp") != "100"):
                    err(f"[ABS 玻璃床溫 0910] {name}: 首層={_v('hot_plate_temp_initial_layer')!r} 應 60、其它層={_v('hot_plate_temp')!r} 應 100")
                # ★ PA 分流量家族（Eric 2026-07-25 裁「PA 0.12 只限一般流量」→ 2026-07-28 三輪裁
                #   「材料如果不是高流量跟火山口或四料，它的壓力提前是 0.08」＝一般流量 0.12→0.08）
                #   現況表（0728 起、以下為權威）：
                #     一般流量  PLA-220/PLA-210/SupPLA/ABS/SupABS/PETG/PVA ＝ **0.08**（enable 1）
                #     高流量噴頭 PLA／SupPLA／PETG ＝ 0.2
                #     四料高流量 PLA／SupPLA        ＝ 0.4
                #     3in1      PLA 0.4／SupPLA 0.2
                #     火山口     PA-CF ＝ 材料特例維持既值（不在 0.08 範圍）
                #     TPE／SupTPE                   ＝ 關（0）＝0725 裁軟料待實測、0728 不翻案
                #   單向護欄照舊：0.12 不得出現在高流量／3in1 家族。
                if is_hf and _v("pressure_advance") == "0.12":
                    err(f"[PA 0.12 只限一般流量 0725] {name}: 高流量/3in1 家族不得用 0.12")
                #   ⚠ Classic 前代線材另有 PA 全關斷言（Marlin 無 PA），不受本條影響。
                if not is_hf and "TPE" not in name and not _is_pacf:
                    if _v("enable_pressure_advance") != "1" or _v("pressure_advance") != "0.08":
                        err(f"[一般流量 PA 0.08 0728] {name}: enable={_v('enable_pressure_advance')!r} "
                            f"pa={_v('pressure_advance')!r}, expected 1/0.08")
                # 🆕 Eric 2026-08-26 裁：PA-CF＝1/0.4（材料特例；0728 起它只是「豁免 0.08」＝實際沒開）
                if _is_pacf:
                    if _v("enable_pressure_advance") != "1" or _v("pressure_advance") != "0.4":
                        err(f"[PA-CF PA 0.4 0826] {name}: enable={_v('enable_pressure_advance')!r} "
                            f"pa={_v('pressure_advance')!r}, expected 1/0.4")
                # 回抽長度四分支（🆕 0819 改寫）
                if is_pt:
                    # 🔴 照片磚系線材**一律 nil＝吃機器層**，線材端不得自己覆蓋回抽長度。
                    #    ⚠ 2026-09-07 起機器層已不是零回抽（Eric 裁：韌體回抽＋抬升 0.1，
                    #      見 [照片磚機器層回抽政策 0907]）——但**本條的形狀完全不變**：
                    #      線材層覆蓋會贏，所以無論機器層是 0 還是 1.3，線材端都必須是 nil。
                    #    線材覆蓋會贏，所以線材端必須是 nil。0730 那批曾把 FF 照片磚支掃成 3，
                    #    靜默蓋掉零回抽整整 20 天沒人發現；這條護欄就是為了不再發生。
                    if _v("filament_retraction_length") != "nil":
                        err(f"[照片磚零回抽 0819] {name}: {_v('filament_retraction_length')!r} 應 nil（吃機器層 0）")
                elif "TPE" in name or "PVA" in name:
                    # 軟料/PVA 長度維持既值不動（Eric 0819「軟料回抽為 3、不改動」；PVA 0724 定稿）。
                    if _v("filament_retraction_length") != "3":
                        err(f"[TPE/PVA 回抽長度 3] {name}: {_v('filament_retraction_length')!r}")
                elif _is_pacf:
                    # 🆕 2026-08-26 Eric 裁：PA-CF 回抽長度 3（高溫滲料，2 擋不住牽絲）。
                    if _v("filament_retraction_length") != "3":
                        err(f"[PA-CF 回抽長度 3 0826] {name}: {_v('filament_retraction_length')!r} 應 3")
                elif is_hf:   # 🔴 0816：原本是內聯複製的字串判定（漏了四料同進/照片磚），改用同一個變數
                    # 2026-07-30 Eric 裁：高流量家族（含 3in1）回抽長度 3；0819「排除不動」再確認。
                    if _v("filament_retraction_length") != "3":
                        err(f"[高流量家族長度 3（0730 裁·0819 再確認）] {name}: {_v('filament_retraction_length')!r} 應 3")
                else:
                    # 🆕 Eric 2026-08-19 令：一般流量線材回抽長度 2（蓋掉 0723 的「收斂繼承 nil」）
                    if _v("filament_retraction_length") != "2":
                        err(f"[一般流量回抽長度 2 0819] {name}: {_v('filament_retraction_length')!r} 應 2")
        # 檢查 12（Eric 2026-07-18 裁「只做腳本」）：3in1 線材起始 gcode 必須含 T 指令。
        # 缺 T 時切片器會自動補「槽位序號」T（第2槽→T1）→機上無此巨集→Klipper 只警告不停
        # →三路同步進料靜默失效（0717 同事 T1 事故機制）。T4/T012/T3 皆可（^T 開頭即過）。
        if "(3in1)" in name:
            sg = d.get("filament_start_gcode")
            sg = sg[0] if isinstance(sg, list) and sg else (sg or "")
            if not re.search(r"^\s*T\S+", sg, re.M):
                err(f"[3in1 起始gcode 缺 T 指令 — 同步進料會靜默失效] {name}")
        # 檢查 12b（Eric 2026-07-26 裁 C・3in1 口徑合一＝統一值照 0.4/0.6）：舊口徑尾碼支不得復活
        #（六支已併 PLA(3in1)/SupPLA(3in1) 各一、不綁機；舊名走 renamed_from 字串相容）。
        if "(3in1) @FF" in name:
            err(f"[3in1 口徑合一 0726] {name}: 舊口徑別名支不得存在")
        fmt = d.get("filename_format", "")
        if fmt:
            if ord(fmt[0]) > 127:
                err(f"[filename_format 開頭非 ASCII — PlaceholderParser 會炸] {name}: {fmt[:20]}")
            for i, ch in enumerate(fmt[1:], 1):
                if ord(ch) > 127 and fmt[i - 1] == "}":
                    err(f"[filename_format '}}' 後接非 ASCII — 會炸] {name}: ...{fmt[max(0,i-5):i+5]}...")

# 檢查 14（Eric 2026-07-24 裁）：PVA 水溶支撐線材存在＋關鍵值
if "PING PVA" not in presets:
    err("[PVA 缺席] PING PVA 不在 PING.json filament_list")
else:
    _k, pd = presets["PING PVA"]
    # 值＝V2.1 定稿案 DPro_0.6_T210_PVA+PLA (0609) 對帳（2026-07-24）：210 全鍵/回抽3/hop0.6/purge85
    for k, want in (("filament_type", ["PVA"]), ("filament_soluble", ["1"]),
                    ("filament_is_support", ["1"]), ("nozzle_temperature", ["210"]),
                    ("nozzle_temperature_initial_layer", ["210"]), ("hot_plate_temp", ["60"]),
                    ("fan_max_speed", ["100"]), ("overhang_fan_threshold", ["25%"]),
                    ("filament_retraction_length", ["3"]), ("filament_z_hop", ["0.6"]),
                    ("filament_minimal_purge_on_wipe_tower", ["85"])):
        if pd.get(k) != want:
            err(f"[PVA 關鍵值] PING PVA: {k}={pd.get(k)!r}, expected {want!r}")

# SupPLA 基礎支噴溫 210（Eric 0729 裁・#32「SUP 與 PLA 同溫」單）：全 SupPLA 家族統一 210
# （高流量/四料/3in1 三支本已 210、基礎支原為唯一 220）。⚠ 連帶：PLA-220＋SupPLA 切片會觸發
#  #33 溫度不一致確認視窗（正確提醒、可繼續）。
_se = presets.get("PING SupPLA")
if not _se:
    err("[SupPLA 缺席] PING SupPLA 不在 filament_list")
elif (_se[1].get("nozzle_temperature") != ["210"]
      or _se[1].get("nozzle_temperature_initial_layer") != ["210"]):
    err(f"[SupPLA 噴溫 210 0729] {_se[1].get('nozzle_temperature')!r}/"
        f"{_se[1].get('nozzle_temperature_initial_layer')!r}, expected ['210']")

# ★ 高流量製程組（Eric 2026-07-30 裁・客戶（建誌）FF800 同進 0.6 實測參數移植；0.4/1.0 口徑連動推）：
# 三支 exact——六類速度全跟客戶（外100/內125/填充150/頂面150/實心150/支撐與介面100）＋首層 100
#（Eric 追裁）＋加速度逐項取保守（實際變更僅 travel/sparse 2000；default 1500/首層 500/頂面 800
#  現值更保守維持）＋層高 0.5×口徑（首層＋0.05）＋頂底厚 1.2；支撐角 35/gyroid/aligned 維持家規
#（客戶 Cura 慣例不吃——support_angle 60 是 Cura 語意＝Orca 30、0724 已踩過的換算坑）。
HF_PROCS = {"0.2mm 高流量 @FF800 同進 (0.4)": ("0.2", "0.25", "0.4"),
            "0.3mm 高流量 @FF800 同進 (0.6)": ("0.3", "0.35", "0.6"),
            "0.5mm 高流量 @FF800 同進 (1.0)": ("0.5", "0.55", "1.0")}
for _hn, (_lh, _flh, _nz) in HF_PROCS.items():
    _he = presets.get(_hn)
    if not _he or _he[0] != "process":
        err(f"[高流量製程組 0730・缺席] {_hn}")
        continue
    _hd = _he[1]
    for _hk, _hw in (("layer_height", _lh), ("initial_layer_print_height", _flh),
                     ("outer_wall_speed", "100"), ("inner_wall_speed", "125"),
                     ("sparse_infill_speed", "150"), ("top_surface_speed", "150"),
                     ("internal_solid_infill_speed", "150"),
                     ("support_speed", "100"), ("support_interface_speed", "100"),
                     ("initial_layer_speed", "100"), ("initial_layer_infill_speed", "100"),
                     ("travel_acceleration", "2000"), ("sparse_infill_acceleration", "2000"),
                     ("default_acceleration", "1500"), ("initial_layer_acceleration", "500"),
                     ("top_surface_acceleration", "800"),
                     ("outer_wall_acceleration", "1500"), ("inner_wall_acceleration", "1500"),
                     ("top_shell_thickness", "1.2"), ("bottom_shell_thickness", "1.2"),
                     ("sparse_infill_pattern", "gyroid"), ("seam_position", "back"),
                     ("support_threshold_angle", "35"), ("instantiation", "true"),
                     ("compatible_printers", ["FF800 同進 %s nozzle" % _nz])):
        if _hd.get(_hk) != _hw:
            err(f"[高流量製程組 0730] {_hn}: {_hk}={_hd.get(_hk)!r} 應 {_hw!r}")
# 範圍鎖：高流量製程現階段僅 FF800 同進三口徑（Eric 裁「實印驗過再擴」——FF600/四色/3in1 出現即紅）
for _n, (_k, _d) in presets.items():
    if _k == "process" and " 高流量 @" in _n and _n not in HF_PROCS:
        err(f"[高流量製程組 0730・範圍外溢] {_n}: 現階段僅 FF800 同進三口徑")

# TPE 一對（Eric 0728 二輪）：本體改名「PING TPE - 210」＋噴溫 220→210（SupTPE 名不動、溫跟 210）；
# 回抽速度 30/30（「TPE軟料的回抽 3/30/30」；長度 3 斷言在上方回抽統一段）
if "PING TPE" in presets:
    err("[TPE 舊名復活 0728v2] PING TPE 應已改名 PING TPE - 210")
if os.path.isfile(os.path.join(PINGDIR, "filament", "PING TPE.json")):
    err("[TPE 舊檔殘留 0728v2] filament/PING TPE.json 應已移除")
for _tn in ("PING TPE - 210", "PING SupTPE"):
    _te = presets.get(_tn)
    if not _te or _te[0] != "filament":
        err(f"[TPE 缺席] {_tn} 不在 PING.json filament_list")
        continue
    for _tk in ("filament_retraction_speed", "filament_deretraction_speed"):
        if _te[1].get(_tk) != ["30"]:
            err(f"[TPE 回抽 3/30/30 0728] {_tn}: {_tk}={_te[1].get(_tk)!r}, expected ['30']")
    for _tk in ("nozzle_temperature", "nozzle_temperature_initial_layer"):
        if _te[1].get(_tk) != ["210"]:
            err(f"[TPE 噴溫 210 0728v2] {_tn}: {_tk}={_te[1].get(_tk)!r}, expected ['210']")
    # 0729 Eric 裁（回報中心單）：TPE 最大體積流量 7（SpiderMaker 官方起始值）；SupTPE 維持 5.5
    _mv_want = ["5.5"] if _tn == "PING SupTPE" else ["7"]
    if _te[1].get("filament_max_volumetric_speed") != _mv_want:
        err(f"[TPE 最大體積流量 0729] {_tn}: {_te[1].get('filament_max_volumetric_speed')!r}, expected {_mv_want!r}")
_te = presets.get("PING TPE - 210")
if _te:
    if _te[1].get("renamed_from") != "PING TPE":
        err(f"[TPE renamed_from 0728v2] PING TPE - 210: {_te[1].get('renamed_from')!r}, expected 'PING TPE'（字串）")
    if _te[1].get("filament_id") != "PINGFILTPE" or _te[1].get("setting_id") != "PINGFILTPE":
        err(f"[TPE id 不得變 0728v2] PING TPE - 210: {_te[1].get('filament_id')!r}/{_te[1].get('setting_id')!r}")

# 基礎支改名（Eric 2026-07-28）：PING PLA → PING PLA - 210；舊名走 renamed_from（字串）相容
if "PING PLA" in presets:
    err("[基礎支舊名復活 0728] PING PLA 應已改名 PING PLA - 210")
if os.path.isfile(os.path.join(PINGDIR, "filament", "PING PLA.json")):
    err("[基礎支舊檔殘留 0728] filament/PING PLA.json 應已移除")
_be = presets.get("PING PLA - 210")
if not _be or _be[0] != "filament":
    err("[基礎支缺席 0728] PING PLA - 210 不在 PING.json filament_list")
else:
    _bd = _be[1]
    if _bd.get("renamed_from") != "PING PLA":
        err(f"[基礎支 renamed_from 0728] PING PLA - 210: {_bd.get('renamed_from')!r}, expected 'PING PLA'（字串）")
    if _bd.get("nozzle_temperature") != ["210"] or _bd.get("nozzle_temperature_initial_layer") != ["210"]:
        err(f"[基礎支噴溫 210] PING PLA - 210: {_bd.get('nozzle_temperature')!r}/{_bd.get('nozzle_temperature_initial_layer')!r}")
    if _bd.get("filament_id") != "GPINGPLA" or _bd.get("setting_id") != "GPINGPLA":
        err(f"[基礎支 id 不得變 0728] PING PLA - 210: {_bd.get('filament_id')!r}/{_bd.get('setting_id')!r}")
# 預設連動定案（Eric 0728 v2「連動」）：單一出料機（FP300×3＋FD300 系 單料頭/同進/同進照片磚）
# 預設一律 PLA - 210；雙料機（FD300/FD300 Pro 標準雙料＋關門＝FD300 雙料變體）首槽維持 PLA - 220；
# 其餘機器不得外溢（P200+ 客戶版/Classic 變體＝不在範圍待裁）。
# 🆕 2026-08-19：FD300 同進照片磚**移出**本集合——它改吃 `PING PLA(照片磚 FD300)` 專用支
#   （Eric 0819 裁「給它專用支」，理由＝零回抽必須靠線材端 nil 才不被覆蓋；見下方專屬護欄）。
#   噴溫仍是 210（專用支從 PLA-210 整支派生），0728 v2 的意旨沒有被推翻，只是落點換到專用支。
_single_out_210 = {"FD300 單料頭", "FD300 Pro 單料頭", "FD300 同進", "FD300 Pro 同進"}
_pt_fd_model = "FD300 同進照片磚"
_PT_FIL_FD = "PING PLA(照片磚 FD300)"
_dual_keep_220 = {"FD300", "FD300 Pro", "FD300 關門"}
for _mn, (_mk, _md) in presets.items():
    if _mk == "machine":
        _dfp = _md.get("default_filament_profile")
        _pmod = _md.get("printer_model", "")
        if _mn.startswith("FP300 ") and _mn.endswith("nozzle"):
            if _dfp != ["PING PLA - 210"]:
                err(f"[FP300 預設 210 0728] {_mn}: {_dfp!r}, expected ['PING PLA - 210']")
        elif _pmod == _pt_fd_model:
            # 🆕 檢查 12 追加（Eric 2026-08-19）：FD300 照片磚機必為照片磚 FD300 專用支。
            # 🔴 動機與 FF 那條同源：照片磚的零回抽只寫在機器層，線材覆蓋會贏 ⇒ 只要槽位被
            #    換回任何一般流量支（例如共用的 PLA-210），零回抽就**靜默失效、不會報錯**。
            if _dfp and set(_dfp) != {_PT_FIL_FD}:
                err(f"[FD300 照片磚機必為照片磚 FD300 專用支 0819] {_mn} -> {sorted(set(_dfp))!r}")
        elif _pmod in _single_out_210:
            if not isinstance(_dfp, list) or "PING PLA - 220" in _dfp or "PING PLA - 210" not in _dfp:
                err(f"[單一出料預設 210 0728v2] {_mn}: {_dfp!r}")
        elif _pmod in _dual_keep_220:
            if not (isinstance(_dfp, list) and _dfp and _dfp[0] == "PING PLA - 220"):
                err(f"[雙料首槽維持 220 0728v2] {_mn}: {_dfp!r}")
        elif isinstance(_dfp, list) and "PING PLA - 210" in _dfp:
            err(f"[預設 210 外溢 0728] {_mn}: 僅 FP300＋FD300 系單一出料應指 PING PLA - 210")
    elif _mk == "machine_model":
        _dmt = (_md.get("default_materials", "") or "").split(";")
        if "PING PLA" in _dmt:
            err(f"[default_materials 舊名未改 0728] {_mn}")
        # 🔁 **被 Eric 2026-08-22「甲」取代**（原條文：照片磚 model 的可勾清單必須含 PLA - 210）。
        #    為什麼取代：0728v2 那條寫在「通用料本來就會出現在照片磚機上」的世界裡（因為它們
        #    compatible_printers 空＝跟誰都相容，再被 0807 rule ② 強制補進可勾清單）。
        #    但那些料的 filament_retraction_length 非 nil，會覆蓋掉機器層的零回抽——與上面
        #    0819 那條「FD300 照片磚機必為照片磚專用支」是同一個理由，只是 0819 只鎖了
        #    default_filament_profile（預設指誰），沒鎖可勾清單（使用者仍選得到）。
        #    Eric 2026-08-22 裁「甲」＝照片磚機的下拉只剩照片磚專用料 ⇒ 210 依定義不可能還在清單裡。
        #    新條文＝可勾清單必須**恰好**是該機型的照片磚專用支，與 0819 對齊成同一把尺。
        _PT_MODEL_FIL = {"FD300 同進照片磚": "PING PLA(照片磚 FD300)",
                         "FF600 同進照片磚": "PING PLA(照片磚)",
                         "FF800 同進照片磚": "PING PLA(照片磚)"}
        if _mn in _PT_MODEL_FIL:
            _want_dmt = {_PT_MODEL_FIL[_mn]}
            if {x for x in _dmt if x} != _want_dmt:
                err(f"[照片磚 model 可勾清單必為專用支 0822甲] {_mn}: "
                    f"{_md.get('default_materials')!r}（應為 {sorted(_want_dmt)!r}）")

# ★ 預勾線材全族補齊護欄（Eric 2026-08-07 裁）——對應 embed_params.py 的
#   apply_default_materials() post-pass。三條斷言：
#   ① 死名：default_materials 每一項都必須是 bundle 內實際存在的線材 preset
#   ② 漏勾：每台機型必須涵蓋「所有與它相容且同族群的 PING 線材」
#   ③ 族群雙向隔離：Classic 線材不進 Fast 機、Fast 線材不進 Classic 機
_CLASSIC_MODEL_RE = re.compile(r"^(EDU|DUAL|PING 2|PING 3)")
_ping_fils = {n: (d.get("compatible_printers") if isinstance(d.get("compatible_printers"), list)
                  and d.get("compatible_printers") else None)
              for n, (k, d) in presets.items()
              if k == "filament" and n.startswith("PING ") and d.get("instantiation") == "true"}

# ★ 照片磚機的線材收斂（Eric 2026-08-22 裁「甲」）——本節是 0807 rule ② 的必要例外。
#   起因：0807 rule ② 要求「每台機型必須涵蓋所有與它相容的 PING 線材」，而通用料的
#   compatible_printers 是空的＝跟誰都相容 ⇒ **照片磚機被這條規則強制預勾了 13 支通用料**。
#   那些料的 filament_retraction_length 非 nil（例：PETG 高流量＝3），會**覆蓋掉機器層的
#   零回抽**（照片磚的硬需求）——正是 0730「FF 照片磚支被掃成 3、零回抽破了 20 天沒人發現」
#   那個坑的另一個入口：這次不是值被寫錯，是不該出現的料能合法待在那台機上。
#   解法＝照片磚機掛 printer_notes 標記 PHOTOTILE，通用料加 compatible_printers_condition
#   把它們排除（C++ 端 Preset.cpp:710 只在「沒有明列 compatible_printers」時才求值條件）。
#   ⚠ 這裡刻意只認**這一條已知條件字串**：出現任何其他條件式就顯性報錯，不要靜默忽略——
#     驗證器看不懂的條件如果被當成「沒有限制」，rule ② 會反過來要求把料加回去。
_PHOTOTILE_MARK = "PHOTOTILE"
_PHOTOTILE_COND = "printer_notes!~/.*%s.*/" % _PHOTOTILE_MARK
_fil_cond = {}
for _n, (_k, _d) in presets.items():
    if _k != "filament" or not _n.startswith("PING ") or _d.get("instantiation") != "true":
        continue
    _c = (_d.get("compatible_printers_condition") or "").strip()
    if not _c:
        continue
    if _c != _PHOTOTILE_COND:
        err(f"[未知的 compatible_printers_condition] {_n}: {_c!r}；"
            f"驗證器只認識 {_PHOTOTILE_COND!r}，請先更新本檔再加新條件")
    _fil_cond[_n] = _c
# 哪些 machine preset 掛了 PHOTOTILE 標記
_phototile_machines = {n for n, (k, d) in presets.items()
                       if k == "machine" and _PHOTOTILE_MARK in (d.get("printer_notes") or "")}
# 🆕 **照片磚機器層回抽政策護欄（Eric 2026-09-07 裁，取代 0718 的零回抽）**
#   為什麼要有：這組值原本是「零回抽」，而它 2026-07~08 曾經被線材層靜默蓋掉 20 天沒人發現
#   （見同檔 [照片磚零回抽 0819] 那條的註解）。政策改了，**護欄要跟著改而不是拿掉**——
#   否則下一次有人動機器層或範本，就會再靜默漂一次，而且症狀（短路徑缺料）要實印才看得出來。
#   值的出處：回抽長度與韌體回抽＝同進家族既有的韌體回抽組（不另訂數字）；抬升 0.1＝Eric 指定。
#   🔴 `retract_length_toolchange` 必須維持 0：照片磚的 Tn 是後處理要換成 M6051/M6052 的混色指令，
#      不是真的換料頭；插換料回抽等於每次換色都白抽一次。
_PT_MACHINE_POLICY = {
    "use_firmware_retraction": "1",
    "retraction_length": ["1.3", "1.3"],
    "z_hop": ["0.1"],
    "retract_length_toolchange": ["0", "0"],
}
for _pm in sorted(_phototile_machines):
    _pd = presets[_pm][1]
    for _k, _want in _PT_MACHINE_POLICY.items():
        _got = _pd.get(_k)
        if _got != _want:
            err(f"[照片磚機器層回抽政策 0907] {_pm}: {_k}={_got!r} 應 {_want!r}")

# ★ Z 抬升＝口徑（Eric 2026-09-10 裁）：**一般機**（非照片磚）0.6→0.6、1.0→1.0；0.4 維持 0.4。
#   0.2／0.25 維持 0.4（Eric 同日裁不套：照規則會從 0.4 降到 0.2/0.25，方向與另外三個相反、撞件風險反升）。
#   照片磚 19 台維持 0.1 由上面那條把關，兩條各管各的、不重疊。
#   ⚠ 線材層 `filament_z_hop` 會蓋過機器層（PING PVA／SupTPE／TPE - 210 三支寫死 0.6）——那是材料
#      特性值、不在本條範圍；但要記得「機器層設了不等於印出來就是那個值」。
_ZHOP_BY_NOZZLE = {"0.2": ["0.4"], "0.25": ["0.4"], "0.4": ["0.4"], "0.6": ["0.6"], "1": ["1"]}
for _n, (_k, _d) in presets.items():
    if _k != "machine" or _d.get("instantiation") != "true" or _n in _phototile_machines:
        continue
    _nz = (_d.get("nozzle_diameter") or [""])[0]
    _want = _ZHOP_BY_NOZZLE.get(str(_nz))
    if _want is None:
        continue
    if _d.get("z_hop") != _want:
        err(f"[Z 抬升＝口徑 0910] {_n}（口徑 {_nz}）: z_hop={_d.get('z_hop')!r} 應 {_want!r}")

_model_variants = {}
for _n, (_k, _d) in presets.items():
    if _k == "machine" and _d.get("instantiation") == "true" and _d.get("printer_model"):
        _model_variants.setdefault(_d["printer_model"], set()).add(_n)
_chk_fast = _chk_classic = 0
for _mn, (_mk, _md) in presets.items():
    if _mk != "machine_model":
        continue
    _vs = _model_variants.get(_mn)
    if not _vs:
        err(f"[機型無任何 machine preset] {_mn}")
        continue
    _is_classic = bool(_CLASSIC_MODEL_RE.match(_mn))
    _chk_classic += _is_classic
    _chk_fast += (not _is_classic)
    _have = [x for x in (_md.get("default_materials", "") or "").split(";") if x]
    _dead = [x for x in _have if x not in _ping_fils]
    if _dead:
        err(f"[default_materials 死名 0807] {_mn}: {'、'.join(_dead)} 不在 bundle 線材清單內")
    # 條件式排除（0822 甲）：機型的所有 variant 都掛了 PHOTOTILE ⇒ 帶排除條件的料不算相容
    _all_photo = bool(_vs) and _vs <= _phototile_machines
    _want = {n for n, cp in _ping_fils.items()
             if (cp is None or (set(cp) & _vs)) and (("Classic" in n) == _is_classic)
             and not (_all_photo and n in _fil_cond)}
    _missing = sorted(_want - set(_have))
    if _missing:
        err(f"[預勾漏勾 0807] {_mn}: 相容卻沒進 default_materials — {'、'.join(_missing)}")
    _spill = sorted(x for x in _have if ("Classic" in x) != _is_classic)
    if _spill:
        _dir = "Fast 線材外溢前代機" if _is_classic else "Classic 線材外溢 Fast 機"
        err(f"[族群隔離破口 0807·{_dir}] {_mn}: {'、'.join(_spill)}")
# SOP §9 通則：照名字分類的斷言跑完要對數量
if _chk_fast + _chk_classic != len([1 for _k, _ in presets.values() if _k == "machine_model"]):
    err(f"[預勾護欄分類漏台 0807] Fast {_chk_fast}＋Classic {_chk_classic} 未涵蓋全部機型")

# 🔴 型別護欄（0725 T004 事故）：`renamed_from` 必須是**字串**，寫成 JSON 陣列會讓
# PresetBundle.cpp:4098 的 unescape_strings_cstyle 收到 array → nlohmann 丟
# type_error.302「type must be string, but is array」→ 該 filament 檔載入失敗
# → **整包 PING vendor 解析中止** → 使用者開起來沒有任何 PING 機型、跳設定精靈、
#   機器掉成 Default Printer。多個舊名用 **分號** 串接（Config.cpp:146 以 ';' 分隔）。
# 教訓：verify 過去只查「參照與值」，查不到「引擎能不能載入」——這類型別錯是啞的。
# 顏色鍵護欄（0725）：線材 preset 只准 `default_filament_colour`。
# `filament_colour` 在 Preset.cpp:960 的 filament_options 是註解掉的＝引擎會剝掉並刷 log；
# 複數版（filament_colors／default_filament_colors）更是引擎根本不認的舊誤植。
for _n, (_k, _d) in presets.items():
    if _k == "filament":
        for _dead in ("filament_colour", "filament_colors", "default_filament_colors"):
            if _dead in _d:
                err(f"[線材顏色鍵殘留 — 引擎會剝掉] {_n}: 不應有 {_dead}（只留 default_filament_colour）")

for _n, (_k, _d) in presets.items():
    _rf = _d.get("renamed_from")
    if _rf is not None and not isinstance(_rf, str):
        err(f"[renamed_from 型別錯 — 會讓整包 vendor 載入失敗] {_n}: {_rf!r}（須為分號字串）")

# renamed_from 舊名唯一性（0728 基礎支改名首驗實抓〔出貨線〕：_classic_filament 從母檔複製把
# renamed_from 一起帶進 Classic 210/EDU ⇒ 兩支搶同一舊名、引擎解析任挑一支＝靜默地雷；
# 開發線無 Classic 但護欄同置＝防未來同型坑）
_rf_claims = {}
for _n, (_k, _d) in presets.items():
    _rf = _d.get("renamed_from")
    if isinstance(_rf, str):
        for _tok in _rf.split(";"):
            _tok = _tok.strip()
            if _tok:
                _rf_claims.setdefault((_k, _tok), []).append(_n)
for (_k, _tok), _ns in sorted(_rf_claims.items()):
    if len(_ns) > 1:
        err(f"[renamed_from 舊名重複認領] {_tok!r} ({_k}): {_ns!r}")


# ★ 跨層護欄（Eric 2026-07-26 兩爆之後補）：C++ 的「組合製程→線材連動」表必須跟得上 profile。
#   `Tab.cpp` 的 ping_apply_combo_filaments() 用**硬寫的線材名**呼叫 find_preset()，
#   而 find_preset() **不走 renamed_from 回溯**（那是 find_preset2）⇒ 名字對不上就是靜默失效：
#     ①0725 ABS 三支併一後，表裡仍寫「PING ABS - 250」⇒ ABS+ABS／ABS+SUP／棧板連動全啞
#     ②0725 新出 PLA+PVA 製程，沒補進表 ⇒ 選了模式第 2 槽不會變 PVA
#   兩個都是「verify 全綠、成品驗收全過」卻壞掉的類型——因為過去沒有任何一條檢查跨到 C++ 這層。
_repo = os.path.dirname(os.path.dirname(os.path.dirname(PINGDIR)))
_tab = os.path.join(_repo, "src", "slic3r", "GUI", "Tab.cpp")
if not os.path.isfile(_tab):
    err(f"[跨層護欄] 找不到 {_tab}（路徑推導失效，護欄形同虛設）")
else:
    _src = io.open(_tab, encoding="utf-8", errors="ignore").read()

    def _cstr(lit):
        # 把 C 字串字面值（含 \xNN 逸出）還原成 Python str
        out = bytearray(); i = 0
        while i < len(lit):
            if lit[i] == "\\" and i + 1 < len(lit) and lit[i + 1] == "x":
                out.append(int(lit[i + 2:i + 4], 16)); i += 4
            else:
                out.append(ord(lit[i])); i += 1
        return out.decode("utf-8", "replace")

    # 1) 常數表列的線材名都必須存在於 bundle
    # ⚠ 2026-09-20（回移批2，牌 c-0920-ABS-01）：Tab.cpp 同一段現在**還有製程 token 常數**
    #   （`PING_TOK_*`，家族分類與連動表共用同一份字面）。它們不是線材名，**必須排除**，
    #   否則本檢查會把 12 個 token 全報成「不在 bundle」＝整段護欄被雜訊淹掉。
    #   token 常數另有自己的契約檢查（見 1b）。
    _names = {}
    _toks  = {}
    for m in re.finditer(r'constexpr\s+const\s+char\s*\*\s*(PING_\w+)\s*=\s*"((?:[^"\\]|\\.)*)"', _src):
        (_toks if m.group(1).startswith("PING_TOK_") else _names)[m.group(1)] = _cstr(m.group(2))
    if not _names:
        err("[跨層護欄] Tab.cpp 抓不到任何 PING_* 線材常數（格式變了？護欄失效）")
    for _k, _v in sorted(_names.items()):
        if _v not in presets:
            err(f"[跨層護欄・C++ 線材名對不上 profile] Tab.cpp {_k} = {_v!r} 不在 bundle ⇒ 組合連動會靜默失效")

    # 1b) 製程 token 常數契約（2026-09-20 回移批2）：本線現行那組必須**恰好**等於在冊製程的
    #     組合 token 集合＋筏層後綴；出貨線新名那組是 0811 改名批回移前的預留，只許是那五個字面。
    #     漏掉／多出任一個，家族分類就會把某類製程判成「一般」⇒ Eric 0920 裁的「ABS 只相容棧板」
    #     會靜默失效（而畫面看起來一切正常＝最難查的那種）。
    _TOK_CUR_EXPECTED = COMBO_TOKENS | {"_棧板"}
    _TOK_NEW_EXPECTED = {"_筏層", "易拆", "易拆水溶", "易拆樹狀", "易拆+筏層"}
    _tok_cur = {v for k, v in _toks.items() if not k.endswith("_NEW") and k != "PING_TOK_RAFT_SFX"}
    _tok_new = {v for k, v in _toks.items() if k.endswith("_NEW") or k == "PING_TOK_RAFT_SFX"}
    if not _toks:
        err("[跨層護欄] Tab.cpp 抓不到任何 PING_TOK_* 製程 token 常數（批2 家族分類失效？）")
    if _tok_cur != _TOK_CUR_EXPECTED:
        err(f"[跨層護欄・token 常數・本線現行] 實得 {sorted(_tok_cur)!r} ≠ 期望 {sorted(_TOK_CUR_EXPECTED)!r}")
    if _tok_new != _TOK_NEW_EXPECTED:
        err(f"[跨層護欄・token 常數・出貨線預留] 實得 {sorted(_tok_new)!r} ≠ 期望 {sorted(_TOK_NEW_EXPECTED)!r}")

    # 2) 功能歸類改名批（0730、Codex 四輪定稿）：兩張連動表**分別**解析、逐張對期望配對 baseline
    #    exact 比對（缺鍵/多鍵/配錯在冊線材皆紅——二輪必改 10）；process token 與兩張 map 雙向相等。
    # ⚠ 2026-09-20（回移批2）：連動表的鍵從字面值改吃 `PING_TOK_*` 常數（與家族分類共用同一份
    #   字面，0811 改名批的教訓）⇒ 解析器必須**兩種都認**，否則鍵集合會抓成空的＝假紅。
    def _parse_combo_map(src, map_name, consts):
        m = re.search(re.escape(map_name) + r"\s*=\s*\{(.*?)\n\s*\};", src, re.S)
        if not m:
            return None
        body = m.group(1)
        pairs = {}
        for lit, ident, v1, v2 in re.findall(
                r'\{(?:"([^"]+)"|([A-Za-z_]\w*)),\s*\{([A-Za-z_0-9]+),\s*([A-Za-z_0-9]+)\}\}', body):
            if lit:
                pairs[cxx_unescape(lit)] = (v1, v2)
            elif ident in consts:
                pairs[consts[ident]] = (v1, v2)
            else:
                err(f"[跨層護欄・{map_name} 鍵] 常數 {ident!r} 在 Tab.cpp 找不到定義（護欄解析不到）")
        return pairs

    _consts = {k: cxx_unescape(v) for k, v in
               re.findall(r'constexpr const char \*(\w+)\s*=\s*"([^"]*)"', _src)}
    for _map_name, _expected in (("COMBO_FILAMENTS", EXPECTED_COMBO_MAP),
                                 ("COMBO_FILAMENTS_HF", EXPECTED_COMBO_MAP_HF)):
        # ⚠ 先剝註解（2026-09-19 反向測試實抓，牌 c-0919-ETR-01）：吃未剝註解的原始碼時，
        #   某一列被 `//` 註解掉（C++ 裡已不存在）仍被解析成有效鍵＝假綠。
        _pairs = _parse_combo_map(strip_cxx_comments(_src), _map_name, _consts)
        if _pairs is None:
            err(f"[跨層護欄] Tab.cpp 抓不到 {_map_name}（格式變了？護欄失效）")
            continue
        _resolved = {k: (_consts.get(a, a), _consts.get(b, b)) for k, (a, b) in _pairs.items()}
        if set(_resolved) != set(_expected):
            err(f"[跨層護欄・{_map_name} 鍵集合] 實得 {sorted(_resolved)!r} ≠ 期望 {sorted(_expected)!r}")
        for _k, _exp_pair in _expected.items():
            if _k in _resolved and _resolved[_k] != _exp_pair:
                err(f"[跨層護欄・{_map_name} 配對] {_k}: {_resolved[_k]!r} ≠ 期望 {_exp_pair!r}")
        for _k, (_a, _b) in _resolved.items():
            for _fil in (_a, _b):
                if _fil not in presets:
                    err(f"[跨層護欄・{_map_name} 線材不在 bundle] {_k} → {_fil!r}")
    # token 契約（三輪建議 1 落點）：五 token 禁含 ASCII 空白與 @；抽取函數 exact 復原
    for _t in COMBO_TOKENS:
        if " " in _t or "@" in _t:
            err(f"[跨層護欄・token 契約] {_t!r} 含空白或 @＝Tab.cpp 最後空白後擷取會壞")
        if combo_token(f"0.2mm {_t} @FD300 (0.4)") != _t:
            err(f"[跨層護欄・token 契約] {_t!r} 經抽取函數無法 exact 復原")
    # process token ↔ map 雙向相等（每支雙料組合製程都有連動；map 無多餘鍵已在鍵集合查過）
    _proc_tokens = set()
    for _n, (_k, _d) in presets.items():
        if _k == "process" and _d.get("instantiation") == "true":
            _t = combo_token(_n)
            if _t:
                _proc_tokens.add(_t)
    if _proc_tokens != COMBO_TOKENS:
        err(f"[跨層護欄・process token 集合] 實得 {sorted(_proc_tokens)!r} ≠ 期望五類")
    # 3) 材料→製程自動收斂・批2（2026-09-20 回移出貨線，牌 c-0920-ABS-01；取代原 #39 棧板建議護欄）
    #    Eric 0920 裁「ABS 族只相容棧板製程」＝靠這套家族軸落地，**不是靠 profile 的
    #    compatible_prints_condition**（實查：FF600／FF800 全系 18 台零棧板製程，硬相容會把它們
    #    打成 0 支可選；批2 的 fail-open 才擋得住）。三支 C++ 掉任何一支＝規則靜默失效。
    #    ⛔ 同時守 `ping_suggest_pallet_for_abs` 已退役：它與收斂做同一件事，復活＝雙重機制。
    for _f, _need, _tag in (
            (os.path.join(_repo, "src", "slic3r", "GUI", "Tab.cpp"),
             ("PingFamily ping_classify_process", "PingFamily ping_derive_family",
              "void ping_converge_process", "s_ping_converge_guard"), "Tab.cpp 批2 三支"),
            (os.path.join(_repo, "src", "slic3r", "GUI", "PresetComboBoxes.cpp"),
             ("ping_derive_family()", "ping_filter_active", "ping_classify_process(preset.name)"),
             "PresetComboBoxes.cpp 製程下拉過濾"),
            (os.path.join(_repo, "src", "slic3r", "GUI", "Plater.cpp"),
             ("ping_converge_process()",), "Plater.cpp 側欄換料收斂掛點")):
        if not os.path.isfile(_f):
            err(f"[跨層護欄] 找不到 {_f}（批2 護欄形同虛設）")
            continue
        # ⚠ 先剝註解（0919 ETR 實抓）：被 // 註解掉的字面仍在檔裡＝假綠。
        _s2 = strip_cxx_comments(io.open(_f, encoding="utf-8", errors="ignore").read())
        for _pat in _need:
            if _pat not in _s2:
                err(f"[跨層護欄・批2 收斂] {_tag} 缺 {_pat!r} ⇒ ABS 只相容棧板會靜默失效")
        if "ping_suggest_pallet_for_abs" in _s2:
            err(f"[跨層護欄・批2 收斂] {_tag} 出現已退役的 ping_suggest_pallet_for_abs ⇒ 與自動收斂重複")

    # 3b) 甲案覆蓋盤點（2026-09-20）：離線重算「線材組合 → 允許的製程」，確認 Eric 的規則成立
    #     且**沒有機型會被打成零製程**。這是把當初做決策時的實查數字釘成回歸測試。
    def _classify(_name):
        _at = _name.find("@")
        if _at <= 0:
            return ("PLAIN", False)
        _h = _name[:_at].rstrip()
        _sp = _h.rfind(" ")
        _tk = _h[_sp + 1:] if _sp >= 0 else ""
        _rf = ("_棧板" in _h) or ("_筏層" in _h)
        if _tk in (COMBO_CAT_PVA, "易拆水溶"):        return ("EASY_SOL", _rf)
        if _tk in (COMBO_CAT_EASYPAL, "易拆+筏層"):   return ("EASY", True)
        if _tk == COMBO_CAT_DUALPAL:                  return ("PLAIN", True)
        if _tk in (COMBO_CAT_EASYTREE, "易拆樹狀"):   return ("EASY", _rf)
        if _tk in (COMBO_CAT_EASY, "易拆"):           return ("EASY", _rf)
        return ("PLAIN", _rf)

    _proc_by_printer = {}
    for _n, (_k, _d) in presets.items():
        if _k != "process" or _d.get("instantiation") != "true":
            continue
        for _pr in (_d.get("compatible_printers") or []):
            _proc_by_printer.setdefault(_pr, []).append(_n)
    # ABS 會推導出兩種家族，**看機器有幾槽**：雙料機 ABS＋SupABS ⇒（易拆, 筏層）；
    # 單槽機（單料頭／同進／FP300）只放得下 ABS 本體、ABS+ABS 雙料也一樣 ⇒（一般, 筏層）。
    # 任一台機器只會走到其中一種，故判準＝「兩者聯集非空」，不是「兩者都要有」。
    _ABS_FAMS = (("EASY", True), ("PLAIN", True))
    _PLA_FAMS = (("EASY", False), ("PLAIN", False))
    for _pr, _ns in sorted(_proc_by_printer.items()):
        if not [x for x in _ns if "棧板" in x or "筏層" in x]:
            continue                    # 該機沒有棧板製程（FF 全系）＝走 fail-open，不受本規則管
        _abs_ok = [x for x in _ns if _classify(x) in _ABS_FAMS]
        _pla_ok = [x for x in _ns if _classify(x) in _PLA_FAMS]
        if not _abs_ok:
            err(f"[跨層護欄・甲案覆蓋] {_pr}：有棧板製程卻推導不出任何 ABS 可用製程（過濾會誤殺）")
        for _x in _abs_ok:
            if "棧板" not in _x and "筏層" not in _x:
                err(f"[跨層護欄・甲案覆蓋] {_pr}：ABS 組合仍可選到非棧板製程 {_x!r}（違反 Eric 0920 裁甲案）")
        if not _pla_ok:
            err(f"[跨層護欄・甲案覆蓋・反向] {_pr}：PLA 組合一支製程都不剩（過濾誤殺非 ABS 路徑）")
        for _x in _pla_ok:
            if "棧板" in _x or "筏層" in _x:
                err(f"[跨層護欄・甲案覆蓋・反向] {_pr}：PLA 組合竟可選到棧板製程 {_x!r}")
    # 4) C-12 renamed 回溯（Eric 2026-07-30 裁）：orca_presets 載入端（load_selections＋
    #    update_selections）的 strict 選擇與多料槽 filament_XX 必須帶 renamed resolver——
    #    select_preset_by_name_strict 是 exact-only，系統 preset 改名批後升級版機器 conf
    #    記的舊名會靜默 fallback 掉使用者記住的選擇（C-12 產品級缺口；切機＝主場景）。
    _pbc = os.path.join(_repo, "src", "libslic3r", "PresetBundle.cpp")
    if not os.path.isfile(_pbc):
        err(f"[跨層護欄] 找不到 {_pbc}（C-12 護欄形同虛設）")
    else:
        _pbsrc = io.open(_pbc, encoding="utf-8", errors="ignore").read()
        for _pat, _need in (("get_preset_name_renamed(initial_print_profile_name", 2),
                            ("get_preset_name_renamed(initial_filament_profile_name", 2),
                            ("get_preset_name_renamed(fp_name", 2)):
            _got = _pbsrc.count(_pat)
            if _got < _need:
                err(f"[跨層護欄・C-12 renamed 回溯] PresetBundle.cpp {_pat!r} 出現 {_got} 次"
                    f"（應 ≥{_need}＝load_selections＋update_selections 各一）")

# 🆕 G2（Eric 2026-08-13 裁・連動規格批1；出貨線 bdbdcecef5，2026-09-19 回移＝牌 c-0919-BP3-01）：
#   C++ 連動表的配料 ↔ profile 屬性「語意一致」
# 為什麼：`Tab.cpp` 的 COMBO_FILAMENTS 是「類別預設配料」**捷徑表**（手選製程時自動帶哪兩支），
#   家族軸則看**材料屬性**（filament_is_support／filament_soluble）。兩者若對不上——例如有人把
#   SupPLA 的 is_support 改成 0——就會出現「手選易拆製程配好料、屬性卻判成一般家族」的分裂，
#   而且**兩邊單獨看都正常**，只有交叉比對抓得到。
# 🔴 本線改寫（SOP §S-9：搬斷言要對目標線查）：出貨線 G2 寫「三 token 槽2 恆支撐」，因為出貨線的兩張表
#   只剩三類易拆（一般雙料 0811 改走空 token 分支）。**本線兩張表仍有「雙料(Z隙)」「雙料(Z隙)+棧板」**，
#   槽2 是本體料（PLA-220／ABS）⇒ 照抄會把合法的雙料配對打紅。改成**按家族**判：
#     易拆家族（token 以「易拆」開頭）＝槽2 是支撐材（is_support=1）；水溶只有「易拆(Z0)水溶」一類
#     雙料家族（token 以「雙料」開頭）＝兩槽皆本體料（0／0）＝出貨線 EXPECTED_PLAIN_DUAL 那道檢查的本線版
#     其他開頭 ⇒ **未分類就紅**（fail-closed），新增家族時要來這裡表態
#   ⓘ 用家族前綴而非逐類窮舉：同族新 token（例：c-0919-ETR-01 的「易拆(Z0)樹狀」）自動涵蓋——
#     SOP §S-6「窮舉表過期時只有一個目的會叫」。前綴是 Eric 0729 裁定的家族名本身，不是碰巧含字。
# ⚠ 刻意掛在**模組層**，不放進上面 Tab.cpp 存在性的 `else:` 區——G2 驗的是「baseline 常數 ↔ profile
#   屬性」，不該因為找不到 Tab.cpp 就整條靜默失效。
# ⚠ 依賴 G1：presets 不解 inherits ⇒ 屬性必須是顯式值（embed 4a-0b／4b-2g 補完才成立）。
def _fil_attr(_name):
    """回傳 (filament_is_support, filament_soluble) 的**顯式**值；非線材或不存在回 None。"""
    _e = presets.get(_name)
    if not _e or _e[0] != "filament":
        return None
    return (_e[1].get("filament_is_support"), _e[1].get("filament_soluble"))

def _g2_slot2_expect(_cat):
    """槽2 應有的 (is_support, soluble)；未分類家族回 None。"""
    if _cat.startswith("易拆"):
        return (["1"], ["1"] if _cat == COMBO_CAT_PVA else ["0"])
    if _cat.startswith("雙料"):
        return (["0"], ["0"])
    return None

_g2_checked = 0
for _mapname, _map in (("COMBO_FILAMENTS", EXPECTED_COMBO_MAP),
                       ("COMBO_FILAMENTS_HF", EXPECTED_COMBO_MAP_HF)):
    for _cat, (_s1, _s2) in _map.items():
        _want2 = _g2_slot2_expect(_cat)
        if _want2 is None:
            err(f"[G2・未分類家族] {_mapname} {_cat!r}：不以「易拆」或「雙料」開頭 ⇒ 槽2 該放支撐材還是本體料？"
                f"到 verify G2 的 _g2_slot2_expect 表態")
            continue
        for _slot, _fil in (("槽1", _s1), ("槽2", _s2)):
            _at = _fil_attr(_fil)
            if _at is None:
                err(f"[G2・配料屬性] {_mapname} {_cat} {_slot}：{_fil!r} 不在 bundle 或非線材")
                continue
            _g2_checked += 1
            _is_sup, _sol = _at
            if _slot == "槽1":
                # 槽1＝本體材料，恆非支撐、非水溶（否則「本體全 ABS」這類判定會算進支撐槽）
                if _is_sup != ["0"] or _sol != ["0"]:
                    err(f"[G2・本體槽屬性] {_mapname} {_cat} 槽1 {_fil}: "
                        f"is_support={_is_sup!r} soluble={_sol!r}, expected ['0']／['0']")
            else:
                if _is_sup != _want2[0]:
                    err(f"[G2・槽2 支撐屬性] {_mapname} {_cat} 槽2 {_fil}: is_support={_is_sup!r}, "
                        f"expected {_want2[0]!r}（{'易拆家族槽2＝支撐材' if _want2[0] == ['1'] else '雙料家族槽2＝本體料'}）")
                if _sol != _want2[1]:
                    err(f"[G2・水溶語意] {_mapname} {_cat} 槽2 {_fil}: "
                        f"soluble={_sol!r}, expected {_want2[1]!r}（水溶只有「{COMBO_CAT_PVA}」一類）")
# 防空轉（同本檔既有範式）：掃到 0 筆＝常數或 presets 建法有變，護欄形同虛設
if _g2_checked == 0:
    err("[G2・防空轉] 配料屬性一條都沒驗到 ⇒ baseline 常數或 presets 建法有變，護欄形同虛設")

# ★ 功能歸類普查（0730 改名批）：五 token × N 支 exact；舊材料對名歸零。
#   N＝雙料本體機（FD300／FD300 Pro／FD300 關門／FD450 Pro／FD600 Pro／FD800 Pro）的口徑變體總數——
#   0730 時＝6 台 × 3 口徑＝18；2026-09-09 NZ 棒大機加 0.25 後＝21。從 machine preset 算、不寫死常數，
#   下次再加口徑不必回來改這裡（每個雙料機口徑變體恰出五 token 各一支）。
_DUAL_BODY_MODELS = {"FD300", "FD300 Pro", "FD300 關門", "FD450 Pro", "FD600 Pro", "FD800 Pro"}
_combo_expect = sum(1 for _n, (_k, _d) in presets.items() if _k == "machine" and _d.get("printer_model") in _DUAL_BODY_MODELS)
_combo_census = {}
for _n, (_k, _d) in presets.items():
    if _k != "process":
        continue
    _t = combo_token(_n)
    if _t:
        _combo_census[_t] = _combo_census.get(_t, 0) + 1
    for _old in COMBO_OLD_TOKENS:
        if (" %s @" % _old) in _n:
            err(f"[功能歸類・舊材料對名殘留] {_n}")
for _t in sorted(COMBO_TOKENS):
    if _combo_census.get(_t, 0) != _combo_expect:
        err(f"[功能歸類・{_t} 應 {_combo_expect} 支＝雙料本體機口徑變體數] 實得 {_combo_census.get(_t, 0)}")

# ★ 易拆樹狀族（Eric 2026-09-19 兩輪 grill 裁，牌 c-0919-ETR-01）：
#   ①支撐＋支撐面速度 exact 50（Q5／Q6 甲＝兩線同值；本線普通易拆目前 40＝0812 下限未進本線，另案）
#   ②每支都必須是「同口徑易拆(Z0)」的雙生，**只准**差 EASY_TREE_ALLOWED_DIFF 那幾鍵——哪天有人把樹狀版
#     接到別的 normalize 之前，其他鍵一偏就紅（不必逐鍵列期望值）。
_et_n = 0
for _n, (_k, _d) in sorted(presets.items()):
    if _k != "process" or combo_token(_n) != COMBO_CAT_EASYTREE:
        continue
    _et_n += 1
    for _key in ("support_speed", "support_interface_speed"):
        if _d.get(_key) != "50":
            err(f"[支撐速度・易拆樹狀 50] {_n}: {_key}={_d.get(_key)!r}, expected '50'（Eric 2026-09-19 裁）")
    _sib = _n.replace(" %s @" % COMBO_CAT_EASYTREE, " %s @" % COMBO_CAT_EASY, 1)
    _se = presets.get(_sib)
    if not _se or _se[0] != "process":
        err(f"[易拆樹狀・雙生對象不存在] {_n}：找不到 {_sib!r}")
        continue
    _sd = _se[1]
    _dk = sorted(k for k in set(_d) | set(_sd) if _d.get(k) != _sd.get(k) and k not in EASY_TREE_ALLOWED_DIFF)
    if _dk:
        err(f"[易拆樹狀・與易拆雙生的差異超出允許] {_n}: {_dk[:6]}"
            f"（只准差 support_type／support_style／兩個支撐速度）")
if _et_n == 0:
    err("[易拆樹狀・防空轉] 一支易拆樹狀製程都沒掃到 ⇒ 產生器沒產或 token 判定壞了")
print("易拆樹狀：%d 支（速度 exact 50＋逐支與同口徑易拆(Z0)雙生比對）" % _et_n)
# id baseline（二輪必改 14／四輪修訂 C）：改名前快照＝舊名→新名→setting_id 90 條 exact，
# 防重構位移／PVA 插回主迴圈／依新名重排 emission（fixture＝regen 前 dump、進 repo）。
_idb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "combo_rename_id_baseline.json")
if not os.path.isfile(_idb_path):
    err("[功能歸類・id baseline] fixture 不存在（combo_rename_id_baseline.json）")
else:
    _idb = json.load(io.open(_idb_path, encoding="utf-8"))
    if len(_idb) != 90:
        err(f"[功能歸類・id baseline] fixture 應 90 條、實得 {len(_idb)}")
    for _row in _idb:
        _ent = presets.get(_row["new"])
        if not _ent or _ent[0] != "process":
            err(f"[功能歸類・id baseline] 新名不存在：{_row['new']}")
            continue
        if _ent[1].get("setting_id") != _row["setting_id"]:
            err(f"[功能歸類・id baseline] {_row['new']}: setting_id={_ent[1].get('setting_id')!r} ≠ {_row['setting_id']!r}（位移！）")
        if _ent[1].get("renamed_from") != _row["old"]:
            err(f"[功能歸類・id baseline] {_row['new']}: renamed_from={_ent[1].get('renamed_from')!r} ≠ {_row['old']!r}")

# ★ 檢查 13：線材收縮補償全庫一致（Eric 2026-08-09 裁 A；產生器 4b-5b 的硬閘門）
#   引擎規則（Print.cpp:3623）：所有用到的料 filament_shrink / _z 必須完全相同，
#   否則整個補償停用並跳「線材收縮補償將被停用」警告。全庫同值就永遠不會踩到。
#   ⚠ 未寫該鍵者＝吃引擎預設 100%，與明寫 100% 等價、不算違規。
_shrink_vals = {}
for _name, (_kind, _d) in presets.items():
    if _kind != "filament":
        continue
    for _k in ("filament_shrink", "filament_shrinkage_compensation_z"):
        if _k in _d:
            _shrink_vals.setdefault(_k, {}).setdefault(str(_d[_k]), []).append(_name)
# 🆕 2026-09-11（Eric：「ABS 的收縮率是 99.75%」）：守衛從「全庫 100%」改成「**族內同值**」。
#   引擎的真實約束（Print.cpp:3623 has_same_shrinkage_compensations）是「同一次列印**用到的**
#   所有料要同值」，不是「全庫要同值」——ABS 件只用 ABS 族、PLA 件只用 PLA 族，各族內同值即可。
#   0809 那條「全庫 100%」當時是對的（因為只有 SupABS 是 99.7%＝異常值），但它把
#   **引擎約束**寫成了**比引擎更嚴的規則**，於是擋住了這個合法的族別設定（SOP §S-8 第 1 例）。
#   ⓘ 出處＝出貨線 dedaf42f3f；2026-09-19 回移本線（牌 c-0919-BP3-01）。名單按本線實查＝3 支
#     （本線沒有 Classic 線材；出貨線另有 `PING ABS - Classic`／`PING SupABS - Classic`）。
#   ⚠ 這裡與產生器 4b-5b 的 ABS_SHRINK_FAMILY 是同一份名單，改一邊要改兩邊。
_ABS_SHRINK_FAMILY = ("PING ABS", "PING ABS(玻璃)", "PING SupABS")
_SHRINK_EXPECT = {"filament_shrink": {True: "99.75%", False: "100%"},
                  "filament_shrinkage_compensation_z": {True: "100%", False: "100%"}}
# 名單 fail-closed：族員改名／消失時，下面「沒有明寫」會誤導成缺鍵——先把「根本不在 bundle」講清楚
for _n in _ABS_SHRINK_FAMILY:
    if presets.get(_n, (None,))[0] != "filament":
        err(f"[收縮補償一致性] ABS 族名單的 {_n!r} 不在 bundle ⇒ 改名了？產生器 4b-5b 與本名單要一起改")
for _k, _groups in _shrink_vals.items():
    for _v, _names in _groups.items():
        for _n in _names:
            _want = _SHRINK_EXPECT[_k][_n in _ABS_SHRINK_FAMILY]
            if _v not in ("['%s']" % _want, "['%s']" % _want.rstrip("%")):
                err(f"[收縮補償一致性] {_n} 的 {_k}={_v}，應為 ['{_want}']"
                    f"——{'ABS 族' if _n in _ABS_SHRINK_FAMILY else '非 ABS 族'}的值不對 ⇒ "
                    f"同族多料列印時引擎會整個停用補償並跳警告")
# 族內一致性正向斷言：ABS 族必須全部帶 filament_shrink 且同值（缺鍵＝吃引擎預設 100%＝族內不一致）
_abs_seen = {n: v for v, names in _shrink_vals.get("filament_shrink", {}).items()
             for n in names if n in _ABS_SHRINK_FAMILY}
if len(_abs_seen) != len(_ABS_SHRINK_FAMILY):
    _missing = [n for n in _ABS_SHRINK_FAMILY if n not in _abs_seen]
    err(f"[收縮補償一致性] ABS 族有 {len(_missing)} 支沒有明寫 filament_shrink：{_missing}"
        f"——缺鍵＝吃引擎預設 100%，與族內其他支的 99.75% 不一致 ⇒ 補償會被整個停用")
elif len(set(_abs_seen.values())) != 1:
    err(f"[收縮補償一致性] ABS 族內值不一致：{_abs_seen}")
else:
    print("收縮補償：ABS 族 %d 支同值 %s｜其餘全庫 100%%"
          % (len(_abs_seen), list(_abs_seen.values())[0]))

# ════ 關門床形四道閘門（出貨線 e841538431／66646635f9／e905f8f2ee＋6862f99ff3；2026-09-19 回移＝牌 c-0919-BP3-01）════
# ★ 檢查：關門機型的列印範圍＝圓角三角形（Eric 2026-08-11 裁，產生器 rounded_triangle_area）
#   幾何條件（兩條就鎖死形狀）：①三圓角貼合 Ø300 ⇒ 弧上每點離床心恰 150
#                               ②三角形內切圓 Ø200 ⇒ 三條直邊各距床心 100
#   ⚠ **凸性是硬條件**：引擎 BuildVolume 對凹形（Type::Custom）的碰撞判定會退回用凸包＝凹口不會被擋。
#   🔴 本線改寫：出貨線只掃「FD300 關門」；本線 FP300 關門 同幾何（BED_OVERRIDE），一併掃，
#     且**兩個家族各自至少一支**（少一個＝那台的床形閘門形同虛設，fail-closed）。
_TRI_FAMILIES = ("FD300 關門", "FP300 關門")
_tri_machines = [(_n, _d) for _n, (_k, _d) in presets.items()
                 if _k == "machine" and _n.startswith(tuple(f + " " for f in _TRI_FAMILIES))
                 and isinstance(_d.get("printable_area"), list)]
for _fam in _TRI_FAMILIES:
    if not any(_n.startswith(_fam + " ") for _n, _ in _tri_machines):
        err(f"[關門床形] 找不到任何 {_fam} 機型的 printable_area（改床形的閘門形同虛設）")
for _n, _d in _tri_machines:
    _pts = []
    for _p in _d["printable_area"]:
        _x, _y = _p.split("x")
        _pts.append((float(_x), float(_y)))
    if len(_pts) < 12:
        err(f"[關門床形] {_n}: 點數 {len(_pts)} 過少，不像圓角三角形")
        continue
    _r = [math.hypot(x, y) for x, y in _pts]
    if abs(max(_r) - 150.0) > 0.01 or min(_r) < 100.0 - 0.01:
        err(f"[關門床形・圓角貼合 Ø300] {_n}: 離床心距離 min={min(_r):.4f} max={max(_r):.4f}，"
            f"期望 max=150（弧在 Ø300 上）且 min≥100")
    # 內切圓 Ø200：任一點都不得落在半徑 100 的圓內（三直邊恰切於該圓）
    if min(_r) < 99.99:
        err(f"[關門床形・內切圓 Ø200] {_n}: 有點離床心僅 {min(_r):.4f} < 100")
    # 凸性：逐點外積同號（多邊形為凸）
    _cross = []
    for _i in range(len(_pts)):
        _a, _b, _c = _pts[_i], _pts[(_i + 1) % len(_pts)], _pts[(_i + 2) % len(_pts)]
        _cross.append((_b[0] - _a[0]) * (_c[1] - _b[1]) - (_b[1] - _a[1]) * (_c[0] - _b[0]))
    if not (all(_v >= -1e-6 for _v in _cross) or all(_v <= 1e-6 for _v in _cross)):
        err(f"[關門床形・凸性] {_n}: 多邊形非凸 ⇒ 引擎會退回用凸包判定，凹口不會被擋")

# ★ 檢查：床形不對稱的機型必須明講盤心（Eric 2026-08-11 夜裁「走乙案」）
#   引擎（`3DBed.cpp` update_model_offset）預設把床身 3D 模型擺在 printable_area 的**外框中心**。
#   床形對稱時外框中心＝盤心（圓床、矩形床皆然，所以上游從沒踩到）；圓角三角形外框 Y[-100,+150]
#   ⇒ 中心 (0,+25) ⇒ 圓盤被往 +Y 畫 25mm。⚠ 純渲染：碰撞判定走 m_build_volume 真實多邊形。
#   對策＝機台 preset 用 `bed_model_offset` 明講盤心；**空值維持引擎原行為 ⇒ 其他機型零影響**。
#   🔴 本閘門刻意寫成**通則而非特例**：任何「非矩形、也非以外框中心為圓心的圓」的床形都必須宣告
#      ⇒ P200+ 之後若也改成三角形卻忘了宣告，會在這裡被擋下來，而不是等使用者看到歪盤。
def _area_is_symmetric(_pts):
    """矩形（4 點）或「以外框中心為圓心的圓」＝外框中心本來就等於盤心，不必宣告。"""
    if len(_pts) == 4:
        return True
    _cx = (min(_p[0] for _p in _pts) + max(_p[0] for _p in _pts)) / 2.0
    _cy = (min(_p[1] for _p in _pts) + max(_p[1] for _p in _pts)) / 2.0
    _rr = [math.hypot(_p[0] - _cx, _p[1] - _cy) for _p in _pts]
    return (max(_rr) - min(_rr)) <= 0.05

_asym_checked = 0
for _n, (_k, _d) in sorted(presets.items()):
    if _k != "machine" or not isinstance(_d.get("printable_area"), list):
        continue
    _pts = []
    for _p in _d["printable_area"]:
        _x, _y = _p.split("x")
        _pts.append((float(_x), float(_y)))
    if len(_pts) < 3 or _area_is_symmetric(_pts):
        continue
    _asym_checked += 1
    _decl = _d.get("bed_model_offset")
    if not (isinstance(_decl, list) and len(_decl) == 1):
        _bx = (min(_p[0] for _p in _pts) + max(_p[0] for _p in _pts)) / 2.0
        _by = (min(_p[1] for _p in _pts) + max(_p[1] for _p in _pts)) / 2.0
        err(f"[床盤盤心] {_n}: 床形不對稱（外框中心 ({_bx:.3f}, {_by:.3f})）卻沒宣告 "
            f"`bed_model_offset` ⇒ 引擎會拿外框中心當盤心，圓盤會被畫歪。"
            f"在 embed_params.py 的 BED_OVERRIDE 補 `bed_model_center`")
        continue
    _ox, _oy = (float(_v) for _v in _decl[0].split("x"))
    # PING 的圓盤機 printable_area 一律以床心 (0,0) 為原點（見 embed_params.py scale_circle_area）
    # ⇒ 盤心恆為原點。日後若出現非中心原點的床，這條要連同該註解一起改，不要只放寬數值。
    if abs(_ox) > 1e-6 or abs(_oy) > 1e-6:
        err(f"[床盤盤心] {_n}: bed_model_offset={_decl[0]!r}，但 PING 圓盤機的盤心恆為床原點 0x0")
if _asym_checked == 0:
    err("[床盤盤心] 沒有掃到任何不對稱床形機型（關門應該要在內）⇒ 閘門形同虛設")

# ★ 檢查：床形不對稱的機型，其床貼圖 logo 必須完全落在可印範圍內（Eric 2026-08-11 夜裁「logo 下移」）
#   機制：床貼圖是「拉滿床形外框、再用床形裁切」（`3DBed.cpp` init_model_from_poly）
#         u=(x-min_x)/size_x；v_eff=1-(y-min_y)/size_y ⇒ **v=0 是影像上緣＝床 +Y（後方）**。
#   共用圖的 logo 垂直置中，映到三角外框後上緣兩側會被斜邊切掉 ⇒ 關門改用專屬貼圖（往床前緣平移 17mm）。
#   🔴 這裡驗的是**幾何結果**不是檔名：拿 fixture 記的**墨跡凸包頂點**反算世界座標，逐點要求在床形內。
#   CI 沒有 PIL，所以墨跡外接矩形離線算好放進 `tools/ping/bed_texture_ink_extents.json`，
#   並用 SHA-256 綁住貼圖檔——換了圖沒重跑產生器就會被擋。
#   🔴 本線改寫兩處：①找機台用 `printer_model` 精確比對——出貨線用 `startswith(機型名+" ")`，
#     「FD300」會連「FD300 關門 …」一起撈進來、取 [0] 取到誰看載入順序（出貨線目前恰好沒踩到）；
#     ②修正指引改指 `make_bed_texture_svg.py`（出貨線訊息仍寫已退役的 make_closeddoor_texture.py）。
_ink_fix_path = os.path.normpath(os.path.join(_repo, "tools", "ping", "bed_texture_ink_extents.json"))
_ink_fix = {}
if os.path.isfile(_ink_fix_path):
    _ink_fix = json.load(io.open(_ink_fix_path, encoding="utf-8"))
else:
    err(f"[床貼圖] 找不到墨跡 fixture {os.path.basename(_ink_fix_path)}（logo 裁切閘門形同虛設）")

def _poly_clearance(_pts, _x, _y):
    """凸多邊形內側餘裕（mm）；負＝在外面。"""
    _a2 = 0.0
    for _i in range(len(_pts)):
        _p, _q = _pts[_i], _pts[(_i + 1) % len(_pts)]
        _a2 += _p[0] * _q[1] - _q[0] * _p[1]
    _sgn = 1.0 if _a2 > 0 else -1.0          # CCW→1，CW→-1
    _best = None
    for _i in range(len(_pts)):
        _p, _q = _pts[_i], _pts[(_i + 1) % len(_pts)]
        _ex, _ey = _q[0] - _p[0], _q[1] - _p[1]
        _len = math.hypot(_ex, _ey)
        if _len < 1e-9:
            continue
        _d = _sgn * ((_ex * (_y - _p[1]) - _ey * (_x - _p[0])) / _len)
        _best = _d if _best is None else min(_best, _d)
    return _best if _best is not None else -1e9

_tex_checked = 0
for _mn, (_mk, _md) in sorted(presets.items()):
    if _mk != "machine_model":
        continue
    # 找這個機型底下任一支機台 preset 拿 printable_area（同機型各口徑同形，前面閘門已驗過一致）
    _own = [_d for _n2, (_k2, _d) in presets.items()
            if _k2 == "machine" and _d.get("printer_model") == _mn and isinstance(_d.get("printable_area"), list)]
    if not _own:
        continue
    _pts = []
    for _p in _own[0]["printable_area"]:
        _x, _y = _p.split("x")
        _pts.append((float(_x), float(_y)))
    if len(_pts) < 3 or _area_is_symmetric(_pts):
        continue
    _tex_checked += 1
    _tex = _md.get("bed_texture") or ""
    _fx = _ink_fix.get(_tex)
    if _fx is None:
        err(f"[床貼圖] {_mn}: 床形不對稱卻用了沒登錄墨跡極值的貼圖 {_tex!r} ⇒ logo 會被斜邊切掉。"
            f"跑 tools/ping/make_bed_texture_svg.py 產專屬貼圖並更新 fixture")
        continue
    _tp = os.path.join(PINGDIR, _tex)
    if not os.path.isfile(_tp):
        err(f"[床貼圖] {_mn}: 貼圖檔不存在 {_tex}")
        continue
    _sha = hashlib.sha256(open(_tp, "rb").read()).hexdigest()
    if _sha != _fx.get("sha256"):
        err(f"[床貼圖] {_mn}: {_tex} 的 SHA-256 與 fixture 不符（貼圖換過但沒重跑產生器）")
        continue
    _bx0 = min(_p[0] for _p in _pts); _bx1 = max(_p[0] for _p in _pts)
    _by0 = min(_p[1] for _p in _pts); _by1 = max(_p[1] for _p in _pts)
    _worst, _wpt = None, None
    for _u, _v in _fx.get("ink_hull_uv", []):
        _wx = _bx0 + _u * (_bx1 - _bx0)
        _wy = _by0 + (1.0 - _v) * (_by1 - _by0)
        _c = _poly_clearance(_pts, _wx, _wy)
        if _worst is None or _c < _worst:
            _worst, _wpt = _c, (_wx, _wy)
    print(f"床貼圖 logo 餘裕：{_mn} {_tex} → "
          f"{('無取樣點' if _worst is None else '%+.2f mm' % _worst)}（{len(_fx.get('ink_hull_uv', []))} 點）")
    if _worst is None:
        err(f"[床貼圖] {_mn}: fixture 沒有墨跡凸包頂點")
    elif _worst < 0:
        err(f"[床貼圖] {_mn}: logo 墨跡超出可印範圍 {-_worst:.2f}mm"
            f"（最糟點 ({_wpt[0]:.1f}, {_wpt[1]:.1f})）⇒ 畫面上會被切掉")
if _tex_checked == 0:
    err("[床貼圖] 沒有掃到任何不對稱床形機型（關門應該要在內）⇒ 閘門形同虛設")

# ★ 跨層護欄：`bed_model_offset` 是 profile↔C++ 雙邊契約，任一邊掉了都是「verify 全綠但功能壞」。
#   ⚠ 一律先 strip_cxx_comments()——出貨線 0811 實測過：註解掉的那份字串會讓 grep 型護欄假綠。
#   ⚠ C++ 端本線 2026-09-19 才回移、**尚未 build 驗證**（編譯＋GUI 看盤心置中要等 Eric 的 build 令）；
#     本護欄只保證「字面在」，保證不了「編得過、畫得對」。
for _rel, _needles in (
    (("src", "slic3r", "GUI", "3DBed.cpp"),
     ["m_bed_model_offset = bed_model_offset", "m_bed_model_offset.size() == 1"]),
    (("src", "libslic3r", "PrintConfig.cpp"),
     ['this->add("bed_model_offset", coPoints)']),
    (("src", "libslic3r", "Preset.cpp"),
     ['"bed_model_offset"']),
    (("src", "slic3r", "GUI", "Plater.cpp"),
     ['option<ConfigOptionPoints>("bed_model_offset")']),
):
    _fp = os.path.join(_repo, *_rel)
    if not os.path.isfile(_fp):
        err(f"[床盤盤心・跨層] 找不到 {os.path.join(*_rel)}")
        continue
    _src = strip_cxx_comments(io.open(_fp, encoding="utf-8", errors="ignore").read())
    for _needle in _needles:
        if _needle not in _src:
            err(f"[床盤盤心・跨層] {os.path.join(*_rel)} 少了 {_needle!r} ⇒ "
                f"profile 宣告了盤心但 C++ 不吃，圓盤照樣歪（靜默失效）")

# ★ 檢查 12：支撐首層擴展＋支撐線寬（Eric 2026-08-09 兩裁；產生器 4b-6 post-pass 的硬閘門）
#   本區塊與出貨線 `release/v3.6` commit 91d2b219 同內容（規則同步，值可因兩線 preset 集合不同而數量不同）。
#   ①raft_first_layer_expansion：raft_layers==0（支撐用途）＝0；raft_layers>=1（棧板/raft）＝6（Eric 2026-09-18「三族都改」3→6；原 0809＝3）
#     ——同一顆鍵管兩件事，分家族是刻意的，不是漏改（Eric 0809 明裁「棧板保留 3、其餘歸 0」）。
#   ②support_line_width＝口徑查表窄一階（0.2→0.15/0.25→0.2/0.4→0.35/0.6→0.5/1.0→0.8）；
#     FF 高流量線寬 1.02×口徑 一律歸回名目口徑查表（同 0722「FF 微調不入分子」家規）。
#     🔴 舊規「support_line_width＝line_width」已於 0809 作廢，看到相等反而是沒套到新規。
#   ⚠ 開發線無棧板家族時 raft_layers>=1 可能為 0 支，故此處不做「棧板家族必須存在」的斷言
#     （出貨線版本有該斷言）。
_SUP_LW_BY_NOZZLE = {"0.2": "0.15", "0.25": "0.2", "0.4": "0.35", "0.6": "0.5", "1": "0.8"}


def _nominal_nozzle_v(lw):
    try:
        v = float(lw)
    except (TypeError, ValueError):
        return None
    for _n in ("0.2", "0.25", "0.4", "0.6", "1"):
        if abs(v - float(_n)) <= 0.03:
            return _n
    return None


_exp_census = {"支撐0": 0, "筏層6": 0}
for _name, (_kind, _d) in presets.items():
    if _kind != "process" or _name.startswith("fdm_"):
        continue
    if "raft_first_layer_expansion" in _d:
        _is_raft = str(_d.get("raft_layers", "0")) != "0"
        _want = "6" if _is_raft else "0"
        if _d["raft_first_layer_expansion"] != _want:
            err(f"[支撐首層擴展] {_name}: raft_first_layer_expansion="
                f"{_d['raft_first_layer_expansion']!r} ≠ {_want!r}"
                f"（raft_layers={_d.get('raft_layers', '0')!r}）")
        else:
            _exp_census["筏層6" if _is_raft else "支撐0"] += 1
    if "support_line_width" in _d:
        # 口徑優先從製程名「(口徑)」取（2026-09-09 PTP 棒：照片磚線寬 1.5×口徑，line_width 反推會錯一階）
        _m_nz = re.search(r"\(([\d.]+)\)\s*$", _name)
        _nzn = None
        if _m_nz:
            _c = "%g" % float(_m_nz.group(1))
            _nzn = _c if _c in _SUP_LW_BY_NOZZLE else None
        if _nzn is None:
            _nzn = _nominal_nozzle_v(_d.get("line_width"))
        if _nzn is None:
            err(f"[支撐線寬] {_name}: line_width={_d.get('line_width')!r} 認不出口徑（查表失效）")
        elif _d["support_line_width"] != _SUP_LW_BY_NOZZLE[_nzn]:
            err(f"[支撐線寬] {_name}: support_line_width={_d['support_line_width']!r} "
                f"≠ {_SUP_LW_BY_NOZZLE[_nzn]!r}（口徑 {_nzn}）")

# ★ 檢查：支撐／支撐面速度下限 60，Classic 前代機除外（Eric 2026-08-12 裁；2026-09-19 裁「A」回移開發線，牌 c-0919-SPD-01）
#   出處＝出貨線 verify 同名段（a73bf75349＋caa5f20441）。規則＝把支撐拉回與外牆同量級
#   （Fast 系外牆 60／內牆 80／稀疏 100，支撐 40 是唯一異類）。
#   🔴 Classic 前代機**刻意排除**：Marlin 非 Klipper、無 Input Shaper，整張速度表本來就慢
#      （EDU 200 全表 40；DUAL 450 外牆 40／頂面 40／支撐 25）⇒ 支撐拉到 60 會變成盤上最快的
#      東西＝內部倒置。**下一棒看到 Classic 是 25/40 不要「順手統一」。**
#   ⛔ 本規則只動支撐兩鍵：稀疏填充 100／內牆 80 是全庫標準（Eric 0719 親裁），不得順手改。
#   ⚠ 開發線差異：①開發線沒有 Classic ⇒ 出貨線的反向斷言「Classic 一支都不剩 <60 就紅」照抄會永遠紅，
#      改成「有 Classic 才驗」（沒有時印一行說明，不靜默）②豁免名單的字面是開發線名「易拆(Z0)樹狀」。
_SPD_FLOOR = 60.0
_CLASSIC_PREFIXES = ("EDU 200", "PING 200", "PING 270", "PING 300+",
                     "DUAL 300", "DUAL 450", "DUAL 600", "DUAL 800")
# 🔴 豁免名單（Eric 2026-09-19，牌 c-0919-ETR-01）＝產生器 4b-7 的 SUPPORT_SPEED_FLOOR_EXEMPT_TOKENS **同名同值**
#    （verify 刻意不 import 產生器，兩邊一起改）。名單內的族不套 ≥60，改驗 exact 50。
#    PA-CF 樹狀不在名單內＝照樣要 ≥60。
SUPPORT_SPEED_FLOOR_EXEMPT_TOKENS = (COMBO_CAT_EASY + "樹狀",)   # ＝("易拆(Z0)樹狀",)
_EXEMPT_SUPPORT_SPEED = "50"

def _proc_machine(_name):
    """製程 preset 名形如「0.3mm 易拆 @EDU 200 (0.6)」；取 @ 後、( 前的機型名。"""
    _at = _name.rfind("@")
    if _at < 0:
        return ""
    _m = _name[_at + 1:]
    _p = _m.rfind("(")
    return (_m[:_p] if _p >= 0 else _m).strip()

_spd_bad, _classic_total, _classic_below, _spd_checked, _easy_tree_spd = [], 0, 0, 0, 0
for _n, (_k, _d) in sorted(presets.items()):
    if _k != "process":
        continue
    # 排除 fdm_* 範本母檔：它們不是出貨 preset；post-pass 若遇到葉檔缺鍵會印警告，那才是要處理的情況。
    if _n.startswith("fdm_"):
        continue
    _vals = []
    for _key in ("support_speed", "support_interface_speed"):
        try:
            _vals.append((_key, float(_d[_key])))
        except (KeyError, TypeError, ValueError):
            continue
    if not _vals:
        continue
    _is_classic = any(_proc_machine(_n).startswith(_c) for _c in _CLASSIC_PREFIXES)
    if _is_classic:
        _classic_total += 1
        if any(_v < _SPD_FLOOR for _key, _v in _vals):
            _classic_below += 1
        continue
    # 易拆樹狀族（Eric 2026-09-19「樹狀支撐的支撐速度 60>50」＋Q5 甲＝支撐與支撐面兩格）：
    #    刻意低於 0812 下限 ⇒ 不套 ≥60，改 **exact 50**（寫成 60／40／漏一格都紅）。
    if any((" %s @" % _t) in _n for _t in SUPPORT_SPEED_FLOOR_EXEMPT_TOKENS):
        _easy_tree_spd += 1
        for _key in ("support_speed", "support_interface_speed"):
            if _d.get(_key) != _EXEMPT_SUPPORT_SPEED:
                err(f"[支撐速度・易拆樹狀 50] {_n}: {_key}={_d.get(_key)!r}, expected {_EXEMPT_SUPPORT_SPEED!r}（Eric 2026-09-19 裁）")
        continue
    _spd_checked += 1
    for _key, _v in _vals:
        if _v < _SPD_FLOOR:
            _spd_bad.append("%s: %s=%g" % (_n, _key, _v))
if _spd_checked == 0:
    err("[支撐速度] 沒有掃到任何非 Classic 製程 ⇒ 閘門形同虛設")
for _b in _spd_bad[:8]:
    err(f"[支撐速度] {_b} < {_SPD_FLOOR:g}（Eric 0812 裁：非 Classic 一律 ≥60）")
if len(_spd_bad) > 8:
    err(f"[支撐速度] 另有 {len(_spd_bad) - 8} 項未列出")
# 反向：有 Classic 而一支都不剩 <60，代表排除規則沒生效或被人「順手統一」了 ⇒ 要有人來看。
#   開發線目前沒有 Classic（_classic_total＝0）⇒ 這條驗不了，照實印出來、不假裝驗過。
if _classic_total and _classic_below == 0:
    err("[支撐速度・Classic 排除] Classic 前代機已無任何支撐速度 <60 ⇒ "
        "排除規則失效或被順手統一。Classic 是 Marlin 無 Input Shaper，整表本來就慢，"
        "支撐拉到 60 會比外牆還快")
print("支撐速度下限：非 Classic %d 支全數 ≥%g｜Classic %d 支（保留 <60 者 %d 支；%s）｜易拆樹狀 exact 50 者 %d 支"
      % (_spd_checked, _SPD_FLOOR, _classic_total, _classic_below,
         "反向斷言已驗" if _classic_total else "本線無 Classic、反向斷言不適用", _easy_tree_spd))

print(f"presets: {len(presets)} | machines: {len(machines)}")
print(f"支撐首層擴展：支撐 0 ×{_exp_census['支撐0']}｜筏層 6 ×{_exp_census['筏層6']}")
if errors:
    print(f"\n[FAIL] {len(errors)} 個問題：")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("[OK] 參照完整性全部通過")
