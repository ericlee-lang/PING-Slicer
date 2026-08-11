"""PING profiles 參照完整性驗證（每次 embed regen 後跑）。

檢查：
1. PING.json 所有 sub_path 檔案存在；檔內 name 與清單一致
2. inherits 指向存在的 preset（且絕非空字串——坑#12：空字串=整包 vendor 載入中止）
3. process/filament 的 compatible_printers 指向存在的 machine preset
4. machine 的 default_print_profile / default_filament_profile 指向存在 preset
5. filename_format 不得以非 ASCII 開頭、'}' 後不得緊接非 ASCII
   （PlaceholderParser rule 邊界限制——中文前綴必須包進 {"X_"} 字串字面值）
6. 正式製程保守值固定為：稀疏填充加速度 5000、空駛加速度 5000、接縫 aligned
   照片磚若存在則維持獨立特調：稀疏填充加速度 10000、空駛加速度 3000、接縫 back
7. 支撐預設：FD300 全家族樹狀；FF600／FF600 3in1 普通；FF600 同進樹狀
8. 精靈同家族排列：基本款 → 同進 → 3in1 → 單料頭（單料頭最右）
9. V3.6 Classic 八機型：Marlin、無 M204／machine limits／韌體回抽／PA，回抽值符合 V2.1
"""
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
# ★ 0811 改名批（Eric 兩裁合併：「棧板」→「筏層」＋拿掉 (Z0)／(Z隙)／「雙料」）
#   現行只剩 **三個 token**；另兩類雙料製程**沒有 token**（與單料/四料同形，這正是 Eric 要的統一）：
#     一般雙料（原 雙料(Z隙)）  → 「{lh}mm @…」
#     雙料筏層（原 雙料(Z隙)+棧板）→「{lh}mm_筏層 @…」（與單料的 _筏層 雙生同形）
#   ⇒ 無 token 的兩類**不能靠名字分類**，本檔一律以 renamed_from 鏈尾（PLA+PLA／ABS+ABS）判定，
#     那條鏈由產生器單一入口 combo_renamed_from() 寫入、且下方會逐支 exact 驗。
COMBO_CAT_EASY,   COMBO_CAT_PVA      = "易拆",      "易拆水溶"
COMBO_CAT_EASYPAL                    = "易拆+筏層"
COMBO_TOKENS = {COMBO_CAT_EASY, COMBO_CAT_PVA, COMBO_CAT_EASYPAL}
COMBO_OLD_TOKENS = {"PLA+SUP", "PLA+PVA", "ABS+SUP", "PLA+PLA", "ABS+ABS"}
# 0730 五類名（**歷史值**，只用於 renamed_from 回溯鏈驗證）
COMBO_0730 = {"PLA+SUP": "易拆(Z0)", "PLA+PVA": "易拆(Z0)水溶", "ABS+SUP": "易拆(Z0)+棧板",
              "PLA+PLA": "雙料(Z隙)", "ABS+ABS": "雙料(Z隙)+棧板"}
# 無 token 兩類的內部代號（僅供錯誤訊息可讀；不是製程名的一部分）
CAT_PLAIN_DUAL, CAT_RAFT_DUAL = "(無token・一般雙料)", "(無token・雙料筏層)"
NEW2OLDCB = {COMBO_CAT_EASY: "PLA+SUP", COMBO_CAT_PVA: "PLA+PVA", COMBO_CAT_EASYPAL: "ABS+SUP",
             CAT_PLAIN_DUAL: "PLA+PLA", CAT_RAFT_DUAL: "ABS+ABS"}

def cxx_unescape(s):
    """把 C++ 字面裡的 \\xNN 逸出序列解回 UTF-8 字串（房規：CJK 字面走逸出）。"""
    return re.sub(r'(?:\\x[0-9A-Fa-f]{2})+',
                  lambda m: bytes(int(h, 16) for h in re.findall(r'\\x([0-9A-Fa-f]{2})', m.group(0)))
                            .decode("utf-8", "replace"), s)

def cxx_escape(s):
    """把字串裡的非 ASCII 字元轉成 C++ \\xNN 逸出形（用於比對 C++ 原始碼字面）。"""
    return "".join(c if ord(c) < 128 else "".join("\\x%02X" % b for b in c.encode("utf-8")) for c in s)

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

def strip_cxx_comments(src):
    """剝掉 C++ 的 // 與 /* */ 註解，供「原始碼字面」型跨層護欄比對用。
    不處理字串字面值裡的 // （本檔用途只比對程式碼 token，誤剝也只會讓護欄更嚴、不會放水）。"""
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

def combo_kind(name, d):
    """回傳製程的功能歸類（三 token 之一，或兩個無 token 雙料代號）；非組合製程回 None。
    0811 起一般雙料／雙料筏層沒有 token（與單料/四料同形）⇒ 改以 renamed_from 鏈尾判定：
    只有這兩類的鏈會以「PLA+PLA @…」／「ABS+ABS @…」開頭（產生器唯一入口寫入、下方逐支 exact 驗）。"""
    t = combo_token(name)
    if t:
        return t
    rf = d.get("renamed_from")
    if isinstance(rf, str):
        first = rf.split(";")[0]
        if " PLA+PLA @" in first:
            return CAT_PLAIN_DUAL
        if " ABS+ABS @" in first:
            return CAT_RAFT_DUAL
    return None

# 期望配對 baseline（值＝dump 自 Tab.cpp:177-247 現值；四輪修訂 C——配錯在冊線材也要紅）
EXPECTED_COMBO_MAP = {
    COMBO_CAT_EASY:    ("PING PLA - 210", "PING SupPLA"),
    COMBO_CAT_PVA:     ("PING PLA - 210", "PING PVA"),
    COMBO_CAT_EASYPAL: ("PING ABS", "PING SupABS"),
}
EXPECTED_COMBO_MAP_HF = {
    COMBO_CAT_EASY:    ("PING PLA - 高流量噴頭", "PING SupPLA - 高流量噴頭"),
    COMBO_CAT_PVA:     ("PING PLA - 高流量噴頭", "PING PVA"),
    COMBO_CAT_EASYPAL: ("PING ABS", "PING SupABS"),
}
# 0811：兩個雙料鍵已從 Tab.cpp 的 map 消失——一般雙料改走「空 token 分支」（Eric 裁「雙料機無
# token 就當 PLA+PLA」），雙料筏層改走既有「_筏層 分支」（全槽 ABS）。下方跨層護欄另有專查。
EXPECTED_PLAIN_DUAL    = ("PING PLA - 220", "PING PLA - 220")
EXPECTED_PLAIN_DUAL_HF = ("PING PLA - 高流量噴頭", "PING PLA - 高流量噴頭")
# #39 筏層建議（PresetComboBoxes.cpp）期望兩組 source→target（原第三組「雙料→雙料+棧板」
# 已被「{lh}mm @…→{lh}mm_筏層 @…」那條通則吸收＝0811 改名後兩者同形）
EXPECTED_P39 = {" %s @" % COMBO_CAT_EASY:  " %s @" % COMBO_CAT_EASYPAL,
                " %s @" % COMBO_CAT_PVA:   " %s @" % COMBO_CAT_EASYPAL}

CLASSIC = {
    "EDU 200":  {"nozzle":"0.6", "retract":"4", "speed":"30", "height":"200", "bed":False},
    "PING 200": {"nozzle":"0.4", "retract":"2", "speed":"20", "height":"200", "bed":True},
    "PING 270": {"nozzle":"0.4", "retract":"6", "speed":"60", "height":"300", "bed":True},
    "PING 300+":{"nozzle":"0.4", "retract":"2", "speed":"20", "height":"270", "bed":True},
    "DUAL 300": {"nozzle":"0.4", "retract":"2", "speed":"20", "height":"270", "bed":True},
    "DUAL 450": {"nozzle":"0.6", "retract":"3", "speed":"30", "height":"600", "bed":True},
    "DUAL 600": {"nozzle":"0.6", "retract":"3", "speed":"30", "height":"580", "bed":True},
    "DUAL 800": {"nozzle":"0.6", "retract":"3", "speed":"30", "height":"580", "bed":True},
}

# Classic DUAL 變體（Eric 2026-07-26 裁「只針對 DUAL 四台」補同進/單料頭、口徑照 FD 對應機；
# 2026-07-27 實作）：機名 "{model} {變體} {nz} nozzle"。參數繼承照 FD、Marlin 隔離照舊
# ⇒ 變體機必須吃到與本體同一組 Classic 斷言（marlin／回抽 Classic 值／無 Klipper 指令）。
CLASSIC_VARIANT_NOZZLES = {
    "DUAL 300": ("0.25", "0.4", "0.6"),
    "DUAL 450": ("0.4", "0.6", "1.0"),
    "DUAL 600": ("0.4", "0.6", "1.0"),
    "DUAL 800": ("0.4", "0.6", "1.0"),
}
CLASSIC_VARIANTS = ("同進", "單料頭")

def classic_model_for_machine(name):
    for model, spec in CLASSIC.items():
        if name == f"{model} {spec['nozzle']} nozzle":
            return model
        for variant in CLASSIC_VARIANTS:
            for nz in CLASSIC_VARIANT_NOZZLES.get(model, ()):
                if name == f"{model} {variant} {nz} nozzle":
                    return model
    return None


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


def expected_support_type(printer_name):
    # 0722 七裁後全池預設普通(自動)；照片磚特調維持 tree(auto) 不查。保留函式供 wizard 一致性檢查
    if "照片磚" in printer_name:
        return None
    if printer_name.startswith(("FD300", "FF600")):
        return "normal(auto)"
    return None

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
        # 檢查 10（Eric 2026-07-17 裁「全機隊」）：機器動力學＝Klipper 實值（時間預估校正）；
        # DL1016 與 Classic 前代機跳過
        if ("machine_max_acceleration_x" in d and "DL1016" not in name
                and not classic_model_for_machine(name)):
            V, A, J = ("200", "1500", "56") if "FF" in name else ("400", "5000", "7")
            for key, value in (("machine_max_speed_x", [V, V]), ("machine_max_speed_y", [V, V]),
                               ("machine_max_acceleration_x", [A, A]), ("machine_max_acceleration_y", [A, A]),
                               ("machine_max_acceleration_extruding", [A, A]),
                               ("machine_max_acceleration_travel", [A, A]),
                               ("machine_max_acceleration_retracting", [A, A]),
                               ("machine_max_jerk_x", [J, J]), ("machine_max_jerk_y", [J, J])):
                if d.get(key) != value:
                    err(f"[機器動力學 Klipper 實值] {name}: {key}={d.get(key)!r}, expected {value!r}")
        classic_model = classic_model_for_machine(name)
        if classic_model:
            spec = CLASSIC[classic_model]
            expected = {
                "gcode_flavor":"marlin", "emit_machine_limits_to_gcode":"0",
                "use_firmware_retraction":"0", "printable_height":spec["height"],
            }
            for key, value in expected.items():
                if d.get(key) != value:
                    err(f"[Classic machine] {name}: {key}={d.get(key)!r}, expected {value!r}")
            for key, value in (("retraction_length", spec["retract"]),
                               ("retraction_speed", spec["speed"]),
                               ("deretraction_speed", spec["speed"])):
                values = d.get(key, []) or []
                if not values or any(v != value for v in values):
                    err(f"[Classic retraction] {name}: {key}={values!r}, expected all {value!r}")
            start = d.get("machine_start_gcode", "")
            if "SET_RETRACTION" in start or "M204" in start:
                err(f"[Classic Klipper/acceleration command] {name}: machine_start_gcode")
            # M6051/M6052＝Klipper 巨集，前代 Marlin 韌體不認——任何 Classic 機（本體/變體）都不得帶。
            # M6050 舊格式只准出現在「同進」變體（該規則在下方變體完整性區檢查）。
            if "M6051" in start or "M6052" in start:
                err(f"[Classic Klipper mix command] {name}: machine_start_gcode 帶 M6051/M6052")
            # 0729 Klipper #128（Eric 令）：赤兔板無 T 工具語意——Classic 出檔禁 T0/T1。
            # start/end 溫度行不帶 T、無裸 T 行；雙料本體換刀＝change_filament_gcode M6050 模板、
            # 單料模板必空（單料引擎本就不出換刀）。
            _endg = d.get("machine_end_gcode", "")
            for _gk, _gv in (("machine_start_gcode", start), ("machine_end_gcode", _endg)):
                if re.search(r"M10[49][^\n]*\bT\d", _gv):
                    err(f"[Classic no-T 溫度 0729] {name}: {_gk} 帶 M104/M109 T…")
                if re.search(r"(?m)^\s*T\d", _gv):
                    err(f"[Classic no-T 換刀 0729] {name}: {_gk} 帶裸 T 行")
            _cfg = d.get("change_filament_gcode", "")
            # 模板只屬雙料「本體」；同進/單料頭變體＝SEMM=0 單一出料、模板必空（下方變體區另鎖）
            if name.startswith("DUAL") and "同進" not in name and "單料頭" not in name:
                for _tok in ("{if next_extruder == 0}", "M6050 S1 P0", "M6050 S0 P0"):
                    if _tok not in _cfg:
                        err(f"[Classic 雙料 M6050 換刀模板 0729] {name}: change_filament_gcode 缺 {_tok!r}")
                if re.search(r"(?m)^\s*T\d", _cfg):
                    err(f"[Classic 雙料 M6050 換刀模板 0729] {name}: change_filament_gcode 帶裸 T 行")
            elif _cfg:
                err(f"[Classic 單料 change_filament 應空 0729] {name}: {_cfg[:40]!r}")
            if not spec["bed"] and any(cmd in start for cmd in ("M140", "M190")):
                err(f"[EDU heated bed command] {name}: machine_start_gcode")
    if kind == "process":
        if d.get("instantiation") == "true":
            compatible = d.get("compatible_printers", []) or []
            is_classic = any(classic_model_for_machine(p) for p in compatible)
            expected = ({
                # Marlin 隔離維持：加速度全 0、不送 machine limits（與本次「套新工藝」無關）
                "default_acceleration": "0",
                "sparse_infill_acceleration": "0",
                "travel_acceleration": "0",
                "seam_position": "aligned",
                # ★ Classic 套 F 系新工藝（Eric 2026-07-25 裁）：爬坡品質＋支撐臨界角改與全庫同值
                #   （原本這裡是豁免的，由 emit_classic 還原成 關/1/30；本裁取消該還原）
                "enable_overhang_speed": "1",
                "overhang_1_4_speed": "50",
                "overhang_2_4_speed": "50",
                "overhang_3_4_speed": "25",
                "overhang_4_4_speed": "10",
                "bridge_flow": "0.95",
                "support_threshold_angle": "35",
            } if is_classic else {
                "sparse_infill_acceleration": "10000",
                "travel_acceleration": "3000",
                # 2026-07-20 Eric 裁（照片磚線 a06fed2c）：接縫預設 背面→對齊（V 溝配套）
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
                "seam_position": "aligned",
                # 爬坡品質（Eric 2026-07-24）：懸空降速四段＋橋接流量；照片磚/Classic 豁免
                # ⚠ 單位＝mm/s（裸數字；ratio_over=outer_wall_speed，要用 % 須帶符號）
                "enable_overhang_speed": "1",
                "overhang_1_4_speed": "50",
                "overhang_2_4_speed": "50",
                "overhang_3_4_speed": "25",
                "overhang_4_4_speed": "10",
                "bridge_flow": "0.95",
                # 支撐臨界角 35（Eric 2026-07-25 裁）
                # 🔴 Orca 基準（= Cura/V2.1 的 55）；兩線相反 Orca = 90 − Cura，見 ping-slicer/orca-sync.md
                # ⚠ 出貨線從未被 07-24 的 60 汙染（本規則首次新增，原全庫 30＝V3.0 底稿值）
                "support_threshold_angle": "35",
            })
            # PLA+PVA→「易拆(Z0)水溶」專屬製程（Eric 2026-07-25 裁「出」；0730 改名批 token 判定）：
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
            # jerk：F 系對齊機器上限（Eric 2026-07-20 裁）＝FD/FP 7、FF 40；Classic 維持 0（Marlin 停用）
            expected["default_jerk"] = "0" if is_classic else ("40" if "@FF" in name else "7")
            for key, value in expected.items():
                if d.get(key) != value:
                    err(f"[process safety default] {name}: {key}={d.get(key)!r}, expected {value!r}")
            # 檢查 7/8（Eric 2026-07-17 裁）：支撐幾何口徑連動＋洗料塔寬 25（照片磚不在 release 線）
            m_nz = re.search(r"\(([\d.]+)\)\s*$", name)
            if m_nz:   # 2026-07-25 Eric 裁「支撐參數全部統一」：照片磚不再豁免（原 and "照片磚" not in name）
                nz_v = float(m_nz.group(1))
                # 線距 2026-07-22 裁 ×9（密度 10%＝Cura 全庫等效；蓋 7/17 ×8）
                #   PLA+PVA 專屬製程 ×19（案值密度 5%）
                # 樹狀 2026-07-25 裁保守配方：分支直徑 ×10→×12（引擎上限 10）、新增分支距離 ×6
                _spacing = ("%g" % round(nz_v * 19, 2)) if _ctok == COMBO_CAT_PVA else ("%g" % (nz_v * 9))
                # ★ Classic 前代改為**跟進**新工藝（Eric 2026-07-25 裁）：樹狀配方一併查。
                #   口徑安全＝CLASSIC_SPECS 每台 nozzle == src_nozzle，母檔算的口徑連動值直接成立。
                _cls_proc = any(t in name for t in ("@DUAL", "@PING ", "@EDU"))
                _geo = [("tree_support_branch_diameter", "%g" % min(nz_v * 12, 10.0)),
                        ("tree_support_branch_distance", "%g" % (nz_v * 6)),
                        ("support_base_pattern_spacing", _spacing)]
                for key, value in _geo:
                    if d.get(key) != value:
                        err(f"[support geometry 口徑連動] {name}: {key}={d.get(key)!r}, expected {value!r}")
                # 頂部接觸面間距（Eric 2026-08-04 裁「70% 密度等效」蓋 0714「一律 0.1」）：
                # 一般支撐＝口徑×3/7 取兩位（密度＝線寬/(間距+線寬)⇒70%；0.25→0.11/0.4→0.17/
                # 0.6→0.26＝Eric 截圖錨值/1.0→0.43）；易拆家族既值不動（介面密＝表面品質、不影響拆）：
                # PLA+SUP/PVA 0.1、ABS+SUP 黃金 0.04、3in1 實心 0。Classic 由 Fast 複製繼承＝同查。
                if _ctok == COMBO_CAT_EASYPAL:
                    _sis = "0.04"
                elif _ctok in (COMBO_CAT_EASY, COMBO_CAT_PVA):
                    _sis = "0.1"
                elif "3in1" in name:
                    _sis = "0"
                elif "@DUAL" in name and "同進" not in name and "單料頭" not in name:
                    # Classic 標準雙料（DUAL 300/450/600/800 本體）＝從 Fast 易拆(Z0) 母檔複製、
                    # 槽 2 裝 Classic SupPLA（0726 裁「Classic 用它實際的模式：雙料→易拆」）⇒ 名稱雖無
                    # 易拆 token，仍屬易拆家族＝介面 0.1 不套 70% 等效。
                    # DUAL 同進/單料頭變體＝單一出料同料＝一般家族 → 走下方口徑連動（Classic 單料同）。
                    _sis = "0.1"
                else:
                    _sis = "%g" % round(nz_v * 3 / 7, 2)
                if d.get("support_interface_spacing") != _sis:
                    err(f"[支撐介面 70% 等效 0804] {name}: support_interface_spacing={d.get('support_interface_spacing')!r}, expected {_sis!r}")
                # 支撐首層密度（同鍵服務 raft 首層）＝10% 全庫（0804；主體類規則全庫套＝0722 ×9 先例，
                # 含 3in1 範本 30%→10%）；raft 機種（ABS 系/棧板 raft_layers≥1）＝貼床抓床維持 100%。
                _rfd = "100%" if str(d.get("raft_layers", "0")) != "0" else "10%"
                if d.get("raft_first_layer_density") != _rfd:
                    err(f"[支撐首層密度 0804] {name}: raft_first_layer_density={d.get('raft_first_layer_density')!r}, expected {_rfd!r}")
                # 普通支撐配方（Eric 2026-07-22 七裁；行為四項同日二裁擴及易拆）
                expected_recipe = [("support_type", "normal(auto)"),
                                   ("independent_support_layer_height", "0"),
                                   ("support_style", "snug"),
                                   ("support_base_pattern", "rectilinear")]
                # Classic 前代（@DUAL/@PING/@EDU）＝Fast 母檔複製：雙料複製自 PLA+SUP＝易拆幾何 0.45 正確，XY 不以一般律查
                is_classic = any(t in name for t in ("@DUAL", "@PING ", "@EDU"))
                # 水溶＝易拆類（PVA 與 PLA 不相熔）⇒ XY 走易拆家規 口徑×0.75；
                # 易拆(Z0)/易拆(Z0)+棧板（原 +SUP 家族）不以一般律查（易拆幾何另有 0.45 家規）；
                # 其餘（雙料類/單料/非組合）走一般 ×1。（0730 改名批：token 判定取代 substring）
                if _ctok == COMBO_CAT_PVA:
                    expected_recipe.append(("support_object_xy_distance", "%g" % round(nz_v * 0.75, 2)))
                elif _ctok not in (COMBO_CAT_EASY, COMBO_CAT_EASYPAL) and "3in1" not in name and not is_classic:
                    expected_recipe.append(("support_object_xy_distance", "%g" % round(nz_v * 1.0, 2)))
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
                for key, value in [("tree_support_branch_angle", "30"),
                                   ("tree_support_auto_brim", "0"),
                                   ("tree_support_brim_width", "10"),
                                   ("tree_support_wall_count", "0"),
                                   ("tree_support_branch_diameter_organic", "2.6"),
                                   ("tree_support_branch_angle_organic", "40")]:
                    if d.get(key) != value:
                        err(f"[樹狀支撐保守配方 0725] {name}: {key}={d.get(key)!r}, expected {value!r}")
                # ★ Classic 前代：確認新工藝**確實有套**（Eric 2026-07-25 裁「Classic 套新工藝」，
                #   本斷言由「豁免破功」反轉為「跟進破功」——防哪天有人又把還原塞回 emit_classic）
                if _cls_proc:
                    for key, value in (("enable_overhang_speed", "1"), ("bridge_flow", "0.95"),
                                       ("support_threshold_angle", "35"),
                                       ("tree_support_branch_angle", "30"),
                                       ("tree_support_branch_diameter", "%g" % min(nz_v * 12, 10.0))):
                        if d.get(key) != value:
                            err(f"[Classic 前代新工藝跟進破功] {name}: {key}={d.get(key)!r}, expected {value!r}")
            # 洗料塔寬：全庫 25（0717 裁）；PLA+PVA 專屬製程 45（案值＝劉勝賢現行）
            _tower = "45" if combo_token(name) == COMBO_CAT_PVA else "25"
            if "照片磚" not in name and d.get("prime_tower_width") != _tower:
                err(f"[洗料塔寬度 {_tower}] {name}: prime_tower_width={d.get('prime_tower_width')!r}")
            # 洗料塔 0729 三裁（Eric）：錐體＋頂角 30＋最快列印速度 60（0708 肋條裁定退役）
            for key, value in (("wipe_tower_wall_type", "cone"),
                               ("wipe_tower_cone_angle", "30"),
                               ("wipe_tower_max_purge_speed", "60")):
                if d.get(key) != value:
                    err(f"[洗料塔錐體 0729] {name}: {key}={d.get(key)!r}, expected {value!r}")
            # 內外牆加速度 0729（Eric「表面品質與穩定性」）：全機型 1500；Classic 維持 Marlin 隔離 0
            _wall_acc = "0" if _cls_proc else "1500"
            for key in ("outer_wall_acceleration", "inner_wall_acceleration"):
                if d.get(key) != _wall_acc:
                    err(f"[內外牆加速度 {_wall_acc}] {name}: {key}={d.get(key)!r}")
            # 牆體列印方向固定逆時針（Eric 2026-07-30 裁）：全庫 ccw，跳過引擎的
            # reorient_perimeters（PerimeterGenerator.cpp:1424）⇒ 層間迴路方向恆一致
            if d.get("wall_direction") != "ccw":
                err(f"[牆方向固定 ccw 0730] {name}: wall_direction={d.get('wall_direction')!r}")
            # ★ 功能歸類五類值鎖（0730 改名批；Z隙＝一層層高〔三輪更正、非固定 0.2〕）
            _vtok = combo_kind(name, d)
            if _vtok:
                _lh_m = re.match(r"([\d.]+)mm", name)
                _lh_v = _lh_m.group(1) if _lh_m else None
                if _vtok in (COMBO_CAT_EASY, COMBO_CAT_PVA, COMBO_CAT_EASYPAL):
                    for zk in ("support_top_z_distance", "support_bottom_z_distance"):
                        if d.get(zk) != "0":
                            err(f"[功能歸類・易拆 Z0] {name}: {zk}={d.get(zk)!r}")
                else:
                    for zk in ("support_top_z_distance", "support_bottom_z_distance"):
                        if d.get(zk) != _lh_v:
                            err(f"[功能歸類・一般雙料 Z隙=層高] {name}: {zk}={d.get(zk)!r}, expected {_lh_v!r}")
                _raft = "2" if _vtok in (COMBO_CAT_EASYPAL, CAT_RAFT_DUAL) else "0"
                if d.get("raft_layers") != _raft:
                    err(f"[功能歸類・筏層 raft {_raft}] {name}: raft_layers={d.get('raft_layers')!r}")
                # 0811 起名字裡的「筏層」與 raft_layers 必須同進退（防「改名沒改值」／「改值沒改名」）
                _name_raft = ("+筏層 @" in name) or ("_筏層 @" in name)
                if _name_raft != (_raft == "2"):
                    err(f"[功能歸類・筏層名值不一致] {name}: 名字帶筏層={_name_raft}, raft_layers={d.get('raft_layers')!r}")
                # renamed_from＝**分號分隔字串**、恰為兩條舊全名（① 材料對原名 ② 0730 五類名）
                _oldcb = NEW2OLDCB[_vtok]
                _head_new = name[:name.find("@")].rstrip()          # 例「0.2mm 易拆」「0.2mm_筏層」「0.2mm」
                _lh_tok = "%smm" % _lh_v
                _tail = name[name.find("@"):]                        # 「@FD300 (0.4)」
                _rf_expect = ";".join(["%s %s %s" % (_lh_tok, _oldcb, _tail),
                                       "%s %s %s" % (_lh_tok, COMBO_0730[_oldcb], _tail)])
                _rf = d.get("renamed_from")
                if not isinstance(_rf, str) or _rf != _rf_expect:
                    err(f"[功能歸類・renamed_from 回溯鏈] {name}: {_rf!r}, expected {_rf_expect!r}")
            support_expected = {expected_support_type(p) for p in (d.get("compatible_printers", []) or [])}
            support_expected.discard(None)
            if len(support_expected) > 1:
                err(f"[support mode ambiguous] {name}: expected candidates={sorted(support_expected)!r}")
            elif support_expected:
                value = next(iter(support_expected))
                if d.get("support_type") != value:
                    err(f"[support mode default] {name}: support_type={d.get('support_type')!r}, expected {value!r}")
            if is_classic and d.get("support_type") != "normal(auto)":
                err(f"[Classic support mode] {name}: support_type={d.get('support_type')!r}, expected 'normal(auto)'")
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
    if kind == "filament":
        # 檢查 9（Eric 2026-07-17 裁）：洗料塔最小清理量——一般 30、SupPLA 系 60、
        # FF 四料高流量噴頭/(3in1) 維持特調 120（同日裁「不蓋」）
        if d.get("instantiation") == "true":
            pv = d.get("filament_minimal_purge_on_wipe_tower")
            pv = pv[0] if isinstance(pv, list) and pv else pv
            # PVA＝85（V2.1 案 75＋劉勝賢現行 +10，0724 對帳定稿）；SupPLA 系 60；其餘 30
            expected_pv = ("120" if ("四料高流量噴頭" in name or "(3in1)" in name)
                           else "85" if "PVA" in name else "60" if "SupPLA" in name else "30")
            if pv is not None and pv != expected_pv:
                err(f"[洗料塔最小清理量] {name}: {pv!r}, expected {expected_pv!r}")
            # 檢查 11：降速層時間一律 10 秒（Eric 2026-07-18 裁「擴及所有材料」）＋
            # 🔴 冷卻降速一律**關**（Eric 2026-08-07 裁，翻 0718 自己那條「一律開」）
            #    原話：「經過實測…它是在特殊情況下才需要進行勾選，因此大部分情況下都要取消」
            #    ⇒ 實測為據的翻案，不是迴歸；引擎預設 true 故必須每支明寫 0 才擋得住。
            if d.get("slow_down_for_layer_cooling") != ["0"]:
                err(f"[冷卻降速應關 0807] {name}: {d.get('slow_down_for_layer_cooling')!r}, expected ['0']")
            if d.get("slow_down_layer_time") != ["10"]:
                err(f"[降速層時間非 10] {name}: {d.get('slow_down_layer_time')!r}")
            # 檢查 13 線材側（Eric 2026-07-24 爬坡品質批）：懸空冷卻觸發閾值全線材 25%
            # ⚠ 0725 補上（Eric 裁「verify 也補」）：本條主線早有、出貨線一直缺＝值兩線一致
            #    但少一道護欄。**刻意放在 Classic 排除區塊之外**——Eric 2026-07-25 裁
            #   「Classic 套新工藝」後，Classic 4 支線材也吃 25%（見 _classic_filament），
            #    全 25 支實測皆為 25% ⇒ 不需任何豁免。
            if d.get("overhang_fan_threshold") != ["25%"]:
                err(f"[懸空冷卻閾值 25% 0724] {name}: {d.get('overhang_fan_threshold')!r}")
            # 線材回抽統一（Eric 2026-07-23 三裁＋兩補裁）；Classic 前代豁免（Marlin 隔離）
            if name.startswith("PING") and "Classic" not in name:
                def _v(k):
                    x = d.get(k)
                    return x[0] if isinstance(x, list) and x else x
                for k, want in (("filament_retraction_minimum_travel", "3"), ("filament_wipe", "1"),
                                ("filament_wipe_distance", "5"), ("filament_retract_before_wipe", "100%")):
                    if _v(k) != want:
                        err(f"[線材回抽四項 0723] {name}: {k}={_v(k)!r}, expected {want!r}")
                is_hf = ("高流量" in name) or ("(3in1)" in name)
                if _v("filament_retract_restart_extra") != ("0.6" if is_hf else "0.2"):
                    err(f"[額外回填流量律 0723] {name}: {_v('filament_retract_restart_extra')!r}, expected {'0.6' if is_hf else '0.2'!r}")
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
                #   ⚠ Classic 前代線材另有 PA 全關斷言（Marlin 無 PA），不受本條影響。
                if is_hf and _v("pressure_advance") == "0.12":
                    err(f"[PA 0.12 只限一般流量 0725] {name}: 高流量/3in1 家族不得用 0.12")
                if not is_hf and "TPE" not in name and "PA-CF" not in name:
                    if _v("enable_pressure_advance") != "1" or _v("pressure_advance") != "0.08":
                        err(f"[一般流量 PA 0.08 0728] {name}: enable={_v('enable_pressure_advance')!r} "
                            f"pa={_v('pressure_advance')!r}, expected 1/0.08")
                # PVA 與 TPE 同列（Eric 2026-07-24 PVA 對帳 V2.1 定稿＝回抽長度 3）
                # ⚠ 0725 稽核抓漏：本行原只認 TPE，PVA 落到 else 被要求 nil ⇒ 與主線不同步
                if "TPE" in name or "PVA" in name:
                    if _v("filament_retraction_length") != "3":
                        err(f"[TPE/PVA 回抽長度 3] {name}: {_v('filament_retraction_length')!r}")
                elif is_hf:
                    # 2026-07-30 Eric 裁：高流量家族（含 3in1）回抽 3/30/30——長度 2→3 上蓋 0723 補裁；
                    # 速度/裝填明寫 30（四料高流量兩支原為 nil＝繼承機器 20/20，Eric 抓到的漏）
                    for _k, _want, _label in (("filament_retraction_length", "3", "長度"),
                                              ("filament_retraction_speed", "30", "回抽速度"),
                                              ("filament_deretraction_speed", "30", "裝填速度")):
                        if _v(_k) != _want:
                            err(f"[高流量家族 3/30/30（0730 裁·含 3in1）] {name}: {_label}={_v(_k)!r} 應 {_want}")
                else:
                    if _v("filament_retraction_length") != "nil":
                        err(f"[基礎支長度應收斂繼承 0723] {name}: {_v('filament_retraction_length')!r}")

# Wizard order is driven by machine_model_list. Verify each family independently so a regen
# cannot silently put the hardware-swap single-head card back between dual-head modes.
variant_rank = {"": 0, "同進": 1, "3in1": 2, "單料頭": 3}
families = {}
for index, item in enumerate(root.get("machine_model_list", [])):
    match = re.match(r"^(.*?)(?: (單料頭|同進|3in1))?$", item["name"])
    base, variant = match.group(1), match.group(2) or ""
    families.setdefault(base, []).append((index, variant))
for base, entries in families.items():
    if not any(variant == "單料頭" for _, variant in entries):
        continue
    ranks = [variant_rank.get(variant, 9) for _, variant in entries]
    if ranks != sorted(ranks) or entries[-1][1] != "單料頭":
        err(f"[wizard model order] {base}: variants={[variant for _, variant in entries]!r}")

# Classic 完整性與專用材料隔離。
model_names = {n for n, (k, _) in presets.items() if k == "machine_model"}
for model, spec in CLASSIC.items():
    if model not in model_names:
        err(f"[Classic model missing] {model}")
    machine = f"{model} {spec['nozzle']} nozzle"
    if machine not in machines:
        err(f"[Classic machine missing] {machine}")
    elif "M605" in presets[machine][1].get("machine_start_gcode", ""):
        # 本體（雙料/單料）start 不得有任何混色指令——M6050 只屬同進變體的預擠同進
        err(f"[Classic 本體 start 不應有 M605x] {machine}")
    if model.startswith("DUAL") and machine in machines:
        # 0728「變體預設跟 210」的對向鎖：DUAL 本體＝雙料 → 首槽維持 Classic 220
        _cdfp = presets[machine][1].get("default_filament_profile")
        if not (isinstance(_cdfp, list) and _cdfp and _cdfp[0] == "PING PLA - Classic 220"):
            err(f"[Classic DUAL 本體首槽維持 Classic 220 0728] {machine}: {_cdfp!r}")

# Classic DUAL 變體完整性＋M6050 舊格式規則（Eric 2026-07-26 裁、07-27 實作）：
# 同進 start 必含「M6050 S0.5」（預擠兩邊同進，對應 FD 同進機的同款行）；
# 單料頭 start 必無任何 M605x；全變體 SEMM=0（同 FD 變體＝Orca 眼裡 1 槽）。
for model, nzs in CLASSIC_VARIANT_NOZZLES.items():
    for variant in CLASSIC_VARIANTS:
        vmodel = f"{model} {variant}"
        if vmodel not in model_names:
            err(f"[Classic 變體 model missing] {vmodel}")
        else:
            # 0728 Eric 裁「Classic 變體預設跟」：變體 model 的可勾清單須含 Classic 210。
            # ⓘ 0807 全族補齊後 default_materials 不再只有一支（Eric 裁 Classic 同辦），
            #    故由「等於」放寬為「必須含」；首位仍是 Classic 210＝預設意旨保留。
            _vdm = [x for x in (presets[vmodel][1].get("default_materials") or "").split(";") if x]
            if not _vdm or _vdm[0] != "PING PLA - Classic 210":
                err(f"[Classic 變體 model 首選 Classic 210 0728·0807 調整] {vmodel}: {_vdm!r}")
        for nz in nzs:
            mname = f"{vmodel} {nz} nozzle"
            entry = presets.get(mname)
            if not entry or entry[0] != "machine":
                err(f"[Classic 變體 machine missing] {mname}")
                continue
            d = entry[1]
            if d.get("single_extruder_multi_material") != "0":
                err(f"[Classic 變體 SEMM] {mname}: "
                    f"{d.get('single_extruder_multi_material')!r}, expected '0'")
            # 0728 Eric 裁「Classic 變體預設跟」：變體＝單一出料 → 預設 Classic 210
            if d.get("default_filament_profile") != ["PING PLA - Classic 210"]:
                err(f"[Classic 變體預設 Classic 210 0728] {mname}: {d.get('default_filament_profile')!r}")
            start = d.get("machine_start_gcode", "")
            if variant == "同進":
                if "M6050 S0.5" not in start:
                    err(f"[Classic 同進 start 缺 M6050 S0.5] {mname}")
            elif "M605" in start:
                err(f"[Classic 單料頭 start 不應有 M605x] {mname}")
            # 0729 Klipper #128：變體同守 no-T（SEMM=0 引擎不出換刀，start 溫度行也不得帶 T）
            if re.search(r"M10[49][^\n]*\bT\d", start) or re.search(r"(?m)^\s*T\d", start):
                err(f"[Classic 變體 no-T 0729] {mname}: machine_start_gcode 帶 T")
            if d.get("change_filament_gcode", ""):
                err(f"[Classic 變體 change_filament 應空 0729] {mname}")
# Classic 全套 11 支（Eric 2026-08-07 裁「全套跟 Fast 對齊」：原 4 支 ＋ 新 7 支）。
# 下面逐支斷言：PA 全關（Marlin 無 PA）＋ start gcode 不得帶 Klipper 的 SET_RETRACTION。
classic_filaments = ("PING PLA - Classic 210", "PING PLA - Classic 220",
                     "PING SupPLA - Classic", "PING PLA - EDU Classic",
                     "PING ABS - Classic", "PING SupABS - Classic", "PING PETG - Classic",
                     "PING PA-CF - Classic", "PING PVA - Classic",
                     "PING TPE - Classic 210", "PING SupTPE - Classic")
for name in classic_filaments:
    entry = presets.get(name)
    if not entry or entry[0] != "filament":
        err(f"[Classic filament missing] {name}")
        continue
    d = entry[1]
    if d.get("enable_pressure_advance") != ["0"]:
        err(f"[Classic pressure advance] {name}: {d.get('enable_pressure_advance')!r}")
    if "SET_RETRACTION" in "\n".join(d.get("filament_start_gcode", []) or []):
        err(f"[Classic Klipper command] {name}: filament_start_gcode")
    # 🔴 赤兔不能吃韌體回抽（Eric 2026-08-07 補充的事實）：Classic 線材**不得**在材料層覆蓋回抽，
    #    一律由 Classic machine preset 控制（_classic_filament() 會 pop 掉這些鍵）。
    _leak = sorted(k for k in d if k.startswith("filament_retract")
                   or k in ("filament_wipe", "filament_wipe_distance",
                            "filament_z_hop", "filament_z_hop_types"))
    if _leak:
        err(f"[Classic 材料層回抽覆蓋 0807] {name}: 不得帶 {'、'.join(_leak)}（赤兔無韌體回抽，一律吃機器層）")
edu = presets.get("PING PLA - EDU Classic")
if edu and any(edu[1].get(key) != ["0"] for key in
               ("hot_plate_temp", "hot_plate_temp_initial_layer", "cool_plate_temp", "cool_plate_temp_initial_layer")):
    err("[EDU filament heated bed] PING PLA - EDU Classic must use 0C bed")

# PING PVA 線材本體（與主線 verify 同款；0725 稽核發現出貨線原本完全沒有這組斷言，
# 所以 01148acf 漏掉的回抽長度沒被抓到）。值＝V2.1 定稿案 DPro_0.6_T210_PVA+PLA (0609)
# 對帳（2026-07-24）：210 全鍵／回抽 3／z-hop 0.6／purge 85。
if "PING PVA" not in presets:
    err("[PVA 缺席] PING PVA 不在 PING.json filament_list")
else:
    _k, pd = presets["PING PVA"]
    for k, want in (("filament_type", ["PVA"]), ("filament_soluble", ["1"]),
                    ("filament_is_support", ["1"]), ("nozzle_temperature", ["210"]),
                    ("nozzle_temperature_initial_layer", ["210"]), ("hot_plate_temp", ["60"]),
                    ("fan_max_speed", ["100"]),
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
                     ("sparse_infill_pattern", "gyroid"), ("seam_position", "aligned"),
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
_single_out_210 = {"FD300 單料頭", "FD300 Pro 單料頭", "FD300 同進", "FD300 Pro 同進", "FD300 同進照片磚"}
_dual_keep_220 = {"FD300", "FD300 Pro", "FD300 關門"}
for _mn, (_mk, _md) in presets.items():
    if _mk == "machine":
        _dfp = _md.get("default_filament_profile")
        _pmod = _md.get("printer_model", "")
        if _mn.startswith("FP300 ") and _mn.endswith("nozzle"):
            if _dfp != ["PING PLA - 210"]:
                err(f"[FP300 預設 210 0728] {_mn}: {_dfp!r}, expected ['PING PLA - 210']")
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
        # ⓘ 0807 全族補齊後，default_materials＝「可勾清單」而非「預設是誰」：照片磚同時看得到
        #    210 與 220 是正常的。「預設指誰」的把關已在上面 machine 分支的 default_filament_profile。
        #    本條只保留 0728 意旨：照片磚機的可勾清單必須含 PLA - 210。
        if _mn == "FD300 同進照片磚" and "PING PLA - 210" not in _dmt:
            err(f"[照片磚 model 可勾含 210 0728v2·0807 調整] {_mn}: {_md.get('default_materials')!r}")

# ★ 預勾線材全族補齊護欄（Eric 2026-08-07 裁）——對應 embed_params.py 的
#   apply_default_materials() post-pass。三條斷言：
#   ① 死名：default_materials 每一項都必須是 bundle 內實際存在的線材 preset
#      （0725 ABS 整併後 PING ABS - 250／PING PolyABS 在 FD/FP 清單裡躺了兩週沒人發現，
#        C++ find_preset 找不到就靜默跳過＝壞得無聲）。
#   ② 漏勾：每台機型必須涵蓋「所有與它相容的 PING 線材」——這是 0807 裁定的本體
#      （起因＝PING PVA／TPE - 210／SupTPE 曾 0/41 台預勾，客戶端得自己去勾才看得到自家料）。
#   ③ Classic 隔離：前代 Marlin 專用線材不得外溢到 Fast 機（Classic 4 支沒設
#      compatible_printers，純靠相容性推導會外溢）。機型判定照 SOP §9 前綴，沒有機器叫「Classic」。
_CLASSIC_MODEL_RE = re.compile(r"^(EDU|DUAL|PING 2|PING 3)")
_ping_fils = {n: (d.get("compatible_printers") if isinstance(d.get("compatible_printers"), list)
                  and d.get("compatible_printers") else None)
              for n, (k, d) in presets.items()
              if k == "filament" and n.startswith("PING ") and d.get("instantiation") == "true"}
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
    # 族群雙向隔離（Eric 0807 二裁）：Classic 機只預勾 Classic 料、Fast 機只預勾非 Classic 料
    _want = {n for n, cp in _ping_fils.items()
             if (cp is None or (set(cp) & _vs)) and (("Classic" in n) == _is_classic)}
    _missing = sorted(_want - set(_have))
    if _missing:
        err(f"[預勾漏勾 0807] {_mn}: 相容卻沒進 default_materials — {'、'.join(_missing)}")
    _spill = sorted(x for x in _have if ("Classic" in x) != _is_classic)
    if _spill:
        _dir = "Fast 線材外溢前代機" if _is_classic else "Classic 線材外溢 Fast 機"
        err(f"[族群隔離破口 0807·{_dir}] {_mn}: {'、'.join(_spill)}")
# SOP §9 通則：照名字分類的斷言跑完要對數量，對不上＝分類規則錯了、不是資料錯了
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

# renamed_from 舊名唯一性（0728 基礎支改名首驗實抓：_classic_filament 從母檔複製把
# renamed_from 一起帶進 Classic 210/EDU ⇒ 兩支搶同一舊名、引擎解析任挑一支＝靜默地雷）
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


# ★ 跨層護欄・Classic M6050 換刀抑制（0729 Klipper #128）：change_filament_gcode 用 M6050 模板時，
#   引擎兩個呼叫端（wipe tower 路徑／一般路徑）靠 custom_gcode_changes_tool 判斷「模板是否已換刀」，
#   原版只認行首 T<n> ⇒ M6050 模板會被視為沒換刀而**補發裸 Tn**（赤兔板炸）。C++ 已加 M6050 認定；
#   本護欄鎖住它不被上游同步/重構沖掉。
_gcodecpp = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(PINGDIR))), "src", "libslic3r", "GCode.cpp")
if not os.path.isfile(_gcodecpp):
    err(f"[跨層護欄] 找不到 {_gcodecpp}（路徑推導失效，護欄形同虛設）")
else:
    _gsrc = io.open(_gcodecpp, encoding="utf-8", errors="ignore").read()
    _gm = re.search(r"custom_gcode_changes_tool\s*\([^)]*\)\s*\{(.{0,800})", _gsrc, re.S)
    if not _gm or "M6050" not in _gm.group(1):
        err("[跨層護欄・Classic M6050 換刀抑制] GCode.cpp custom_gcode_changes_tool 未認 M6050 ⇒ 模板後會補裸 Tn")

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
    _names = {}
    for m in re.finditer(r'constexpr\s+const\s+char\s*\*\s*(PING_\w+)\s*=\s*"((?:[^"\\]|\\.)*)"', _src):
        _names[m.group(1)] = _cstr(m.group(2))
    if not _names:
        err("[跨層護欄] Tab.cpp 抓不到任何 PING_* 線材常數（格式變了？護欄失效）")
    for _k, _v in sorted(_names.items()):
        if _v not in presets:
            err(f"[跨層護欄・C++ 線材名對不上 profile] Tab.cpp {_k} = {_v!r} 不在 bundle ⇒ 組合連動會靜默失效")

    # 2) 功能歸類改名批（0730、Codex 四輪定稿）：兩張連動表**分別**解析、逐張對期望配對 baseline
    #    exact 比對（缺鍵/多鍵/配錯在冊線材皆紅——二輪必改 10）；process token 與兩張 map 雙向相等。
    def _parse_combo_map(src, map_name):
        m = re.search(re.escape(map_name) + r"\s*=\s*\{(.*?)\n\s*\};", src, re.S)
        if not m:
            return None
        body = m.group(1)
        pairs = {}
        for k, v1, v2 in re.findall(r'\{"([^"]+)",\s*\{([A-Za-z_0-9]+),\s*([A-Za-z_0-9]+)\}\}', body):
            pairs[cxx_unescape(k)] = (v1, v2)
        return pairs

    _consts = {k: cxx_unescape(v) for k, v in
               re.findall(r'constexpr const char \*(\w+)\s*=\s*"([^"]*)"', _src)}
    for _map_name, _expected in (("COMBO_FILAMENTS", EXPECTED_COMBO_MAP),
                                 ("COMBO_FILAMENTS_HF", EXPECTED_COMBO_MAP_HF)):
        _pairs = _parse_combo_map(_src, _map_name)
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
        err(f"[跨層護欄・process token 集合] 實得 {sorted(_proc_tokens)!r} ≠ 期望三類（0811 改名後）")
    # 0811 新增：無 token 的兩類雙料製程必須存在且成對（每台雙料本體機、每口徑各一）——
    # 它們是這次「統一命名」的產物，一旦產生器回頭把 token 加回來，這條會紅。
    _plain = {n for n, (k, dd) in presets.items()
              if k == "process" and dd.get("instantiation") == "true" and combo_kind(n, dd) == CAT_PLAIN_DUAL}
    _rdual = {n for n, (k, dd) in presets.items()
              if k == "process" and dd.get("instantiation") == "true" and combo_kind(n, dd) == CAT_RAFT_DUAL}
    if not _plain or not _rdual:
        err(f"[跨層護欄・無 token 雙料兩類] 一般雙料 {len(_plain)} 支／雙料筏層 {len(_rdual)} 支，兩者都不該是 0")
    elif len(_plain) != len(_rdual):
        err(f"[跨層護欄・無 token 雙料兩類] 支數不成對：一般 {len(_plain)}／筏層 {len(_rdual)}")
    for _n in _plain:
        if combo_token(_n) is not None or "_筏層" in _n:
            err(f"[跨層護欄・一般雙料應無 token] {_n}")
    # Tab.cpp 必須有「空 token ⇒ 雙料機當 PLA+PLA」那條分支（Eric 2026-08-11 裁）。
    # 沒有它，一般雙料版選了不會自動配料＝靜默失效（正是 0725 T004 那型的坑）。
    if os.path.isfile(_tab):
        # ⚠ **必須剝掉註解再比對**（2026-08-11 反向測試實抓）：本守衛原本只做「字串存在」比對，
        #   把 `combo.empty()` 註解掉、行為已死，守衛卻因為註解裡那份仍在而照樣綠 ⇒ 假綠。
        #   同型風險存在於所有「grep 原始碼字面」的跨層護欄，本批先修這一條。
        _tsrc = strip_cxx_comments(io.open(_tab, encoding="utf-8", errors="ignore").read())
        if "combo.empty()" not in _tsrc:
            err("[跨層護欄・空 token 分支] Tab.cpp 找不到 combo.empty() ⇒ 一般雙料版連動會靜默失效")
        for _c in ("PLAIN_DUAL", "PLAIN_DUAL_HF"):
            if _c not in _tsrc:
                err(f"[跨層護欄・空 token 分支] Tab.cpp 缺 {_c} 常數")
        if "filament_presets.size() != 2" not in _tsrc:
            err("[跨層護欄・空 token 分支] Tab.cpp 缺「槽數==2」判準 ⇒ 單料/四料可能被誤套 PLA+PLA")
    # 3) #39 棧板建議（PresetComboBoxes.cpp）：三組 source→target＋守衛 pattern exact（二輪必改 8/10）
    _pcb = os.path.join(_repo, "src", "slic3r", "GUI", "PresetComboBoxes.cpp")
    if not os.path.isfile(_pcb):
        err(f"[跨層護欄] 找不到 {_pcb}（#39 護欄形同虛設）")
    else:
        _psrc = io.open(_pcb, encoding="utf-8", errors="ignore").read()
        for _s, _t in EXPECTED_P39.items():
            if (_s not in _psrc and cxx_escape(_s) not in _psrc) or \
               (_t not in _psrc and cxx_escape(_t) not in _psrc):
                err(f"[跨層護欄・#39 棧板建議] 缺 source/target 字面 {_s!r}→{_t!r}")
        for _lit in ("+筏層", "_筏層"):
            if cxx_escape(_lit) not in _psrc and ('"%s"' % _lit) not in _psrc:
                err(f"[跨層護欄・#39 筏層建議] 守衛/目標名未帶「{_lit}」字面（0811 改名後舊守衛失效）")
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

# ★ 功能歸類普查（0730 改名批）：五 token × 18 支 exact；舊材料對名歸零
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
    if _combo_census.get(_t, 0) != 18:
        err(f"[功能歸類・{_t} 應 18 支] 實得 {_combo_census.get(_t, 0)}")
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
        # 0811 起 renamed_from 是**分號分隔的回溯鏈**（①材料對原名 ②0730 五類名）；
        # 本 fixture 的 old 欄＝材料對原名＝鏈的第一條，必須 exact 命中（鏈完整性另有專查）。
        _rf_chain = (_ent[1].get("renamed_from") or "").split(";")
        if not _rf_chain or _rf_chain[0] != _row["old"]:
            err(f"[功能歸類・id baseline] {_row['new']}: renamed_from 鏈首={_rf_chain[0] if _rf_chain else None!r}"
                f" ≠ {_row['old']!r}（全鏈={_ent[1].get('renamed_from')!r}）")

# ★ 檢查：FD300 關門的列印範圍＝圓角三角形（Eric 2026-08-11 裁，產生器 rounded_triangle_area）
#   幾何條件（兩條就鎖死形狀）：①三圓角貼合 Ø300 ⇒ 弧上每點離床心恰 150
#                               ②三角形內切圓 Ø200 ⇒ 三條直邊各距床心 100
#   ⚠ **凸性是硬條件**：引擎 BuildVolume 對凹形（Type::Custom）的碰撞判定會退回用凸包
#     （BuildVolume.cpp:78-79）＝凹口不會被擋；凸形才走 Type::Convex 精準路徑。
_tri_machines = [(_n, _d) for _n, (_k, _d) in presets.items()
                 if _k == "machine" and "FD300 關門" in _n and isinstance(_d.get("printable_area"), list)]
if not _tri_machines:
    err("[關門床形] 找不到任何 FD300 關門機型的 printable_area（改床形的閘門形同虛設）")
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

# ★ 檢查：床形不對稱的機型必須明講盤心（Eric 2026-08-11 夜裁「走乙案」・T021 眼驗①處置）
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

# ★ 跨層護欄：`bed_model_offset` 是 profile↔C++ 雙邊契約，任一邊掉了都是「verify 全綠但功能壞」。
#   ⚠ 一律先 strip_cxx_comments()——0811 實測過：註解掉的那份字串會讓 grep 型護欄假綠。
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

# ★ 跨層護欄（0727 Classic 變體）：profile 出了 Classic DUAL 同進機型，C++ 若沒有
#   「printer_model DUAL 開頭 → M6050 舊格式」分支，逐層插的會是 M6051（前代 Marlin
#   韌體不認）＝混色靜默失效——與 Tab.cpp 連動表同型的「verify 全綠但功能壞」坑。
_bsp = os.path.join(_repo, "src", "slic3r", "GUI", "BackgroundSlicingProcess.cpp")
if not os.path.isfile(_bsp):
    err(f"[跨層護欄] 找不到 {_bsp}（路徑推導失效，M6050 護欄形同虛設）")
else:
    _bsrc = io.open(_bsp, encoding="utf-8", errors="ignore").read()
    if '"M6050"' not in _bsrc or 'rfind("DUAL", 0)' not in _bsrc:
        err("[跨層護欄] Classic DUAL 的 M6050 舊格式分支不在 BackgroundSlicingProcess.cpp "
            "⇒ Classic 同進逐層混色會插 M6051（前代韌體不認）")

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
for _k, _groups in _shrink_vals.items():
    _bad = {v: names for v, names in _groups.items() if v not in ("['100%']", "['100']")}
    for _v, _names in _bad.items():
        err(f"[收縮補償一致性] {_k}={_v} 的線材 {len(_names)} 支（例：{_names[0]}）"
            f"——與全庫 100% 不一致 ⇒ 多料列印時引擎會整個停用補償並跳警告")

# ★ 檢查 12：支撐首層擴展＋支撐線寬（Eric 2026-08-09 兩裁；產生器 4b-6 post-pass 的硬閘門）
#   ①raft_first_layer_expansion：raft_layers==0（支撐用途）＝0；raft_layers>=1（棧板/raft）＝3
#     ——同一顆鍵管兩件事，分家族是刻意的，不是漏改（Eric 0809 明裁「棧板保留 3、其餘歸 0」）。
#   ②support_line_width＝口徑查表窄一階（0.2→0.15/0.25→0.2/0.4→0.35/0.6→0.5/1.0→0.8）；
#     FF 高流量線寬 1.02×口徑 一律歸回名目口徑查表（同 0722「FF 微調不入分子」家規）。
#     🔴 舊規「support_line_width＝line_width」已於 0809 作廢，看到相等反而是沒套到新規。
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


_exp_census = {"支撐0": 0, "棧板3": 0}
for _name, (_kind, _d) in presets.items():
    if _kind != "process" or _name.startswith("fdm_"):
        continue
    if "raft_first_layer_expansion" in _d:
        _is_raft = str(_d.get("raft_layers", "0")) != "0"
        _want = "3" if _is_raft else "0"
        if _d["raft_first_layer_expansion"] != _want:
            err(f"[支撐首層擴展] {_name}: raft_first_layer_expansion="
                f"{_d['raft_first_layer_expansion']!r} ≠ {_want!r}"
                f"（raft_layers={_d.get('raft_layers', '0')!r}）")
        else:
            _exp_census["棧板3" if _is_raft else "支撐0"] += 1
    if "support_line_width" in _d:
        _nzn = _nominal_nozzle_v(_d.get("line_width"))
        if _nzn is None:
            err(f"[支撐線寬] {_name}: line_width={_d.get('line_width')!r} 認不出口徑（查表失效）")
        elif _d["support_line_width"] != _SUP_LW_BY_NOZZLE[_nzn]:
            err(f"[支撐線寬] {_name}: support_line_width={_d['support_line_width']!r} "
                f"≠ {_SUP_LW_BY_NOZZLE[_nzn]!r}（口徑 {_nzn}）")
if _exp_census["棧板3"] == 0:
    err("[支撐首層擴展] 全庫找不到任何 raft_layers>=1 的棧板製程 ⇒ 棧板家族消失或判定失效")

print(f"presets: {len(presets)} | machines: {len(machines)}")
print(f"支撐首層擴展：支撐 0 ×{_exp_census['支撐0']}｜棧板 3 ×{_exp_census['棧板3']}")
if errors:
    print(f"\n[FAIL] {len(errors)} 個問題：")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("[OK] 參照完整性全部通過")
