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
import io
import json
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
COMBO_TOKENS = {COMBO_CAT_EASY, COMBO_CAT_PVA, COMBO_CAT_EASYPAL, COMBO_CAT_DUAL, COMBO_CAT_DUALPAL}
COMBO_OLD_TOKENS = {"PLA+SUP", "PLA+PVA", "ABS+SUP", "PLA+PLA", "ABS+ABS"}

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

# 期望配對 baseline（值＝dump 自 Tab.cpp:177-247 現值；四輪修訂 C——配錯在冊線材也要紅）
EXPECTED_COMBO_MAP = {
    COMBO_CAT_EASY:    ("PING PLA - 210", "PING SupPLA"),
    COMBO_CAT_PVA:     ("PING PLA - 210", "PING PVA"),
    COMBO_CAT_EASYPAL: ("PING ABS", "PING SupABS"),
    COMBO_CAT_DUAL:    ("PING PLA - 220", "PING PLA - 220"),
    COMBO_CAT_DUALPAL: ("PING ABS", "PING ABS"),
}
EXPECTED_COMBO_MAP_HF = {
    COMBO_CAT_EASY:    ("PING PLA - 高流量噴頭", "PING SupPLA - 高流量噴頭"),
    COMBO_CAT_PVA:     ("PING PLA - 高流量噴頭", "PING PVA"),
    COMBO_CAT_EASYPAL: ("PING ABS", "PING SupABS"),
    COMBO_CAT_DUAL:    ("PING PLA - 高流量噴頭", "PING PLA - 高流量噴頭"),
    COMBO_CAT_DUALPAL: ("PING ABS", "PING ABS"),
}
# #39 棧板建議（PresetComboBoxes.cpp）期望三組 source→target＋守衛 token（跨層護欄用）
EXPECTED_P39 = {" %s @" % COMBO_CAT_EASY:  " %s @" % COMBO_CAT_EASYPAL,
                " %s @" % COMBO_CAT_PVA:   " %s @" % COMBO_CAT_EASYPAL,
                " %s @" % COMBO_CAT_DUAL:  " %s @" % COMBO_CAT_DUALPAL}



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
                "seam_position": "aligned",
                # 爬坡品質（Eric 2026-07-24）：懸空降速四段＋橋接流量；照片磚特調豁免
                "enable_overhang_speed": "1",
                "overhang_1_4_speed": "50",
                "overhang_2_4_speed": "50",
                "overhang_3_4_speed": "25",
                "overhang_4_4_speed": "10",
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
                elif _ctok in (COMBO_CAT_EASY, COMBO_CAT_PVA):
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
                # PLA+PVA＝易拆類（PVA 為水溶支撐料、與 PLA 不相熔，同 +SUP 家族）
                # ⇒ XY 走易拆家規 口徑×0.75，不套一般支撐的 ×1
                if _ctok == COMBO_CAT_PVA:
                    expected_recipe.append(("support_object_xy_distance", "%g" % round(nz * 0.75, 2)))
                elif _ctok not in (COMBO_CAT_EASY, COMBO_CAT_EASYPAL) and "3in1" not in name:
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
                if _vtok in (COMBO_CAT_EASY, COMBO_CAT_PVA, COMBO_CAT_EASYPAL):
                    for zk in ("support_top_z_distance", "support_bottom_z_distance"):
                        if d.get(zk) != "0":
                            err(f"[功能歸類・易拆 Z0] {name}: {zk}={d.get(zk)!r}")
                else:
                    for zk in ("support_top_z_distance", "support_bottom_z_distance"):
                        if d.get(zk) != _lh_v:
                            err(f"[功能歸類・雙料 Z隙=層高] {name}: {zk}={d.get(zk)!r}, expected {_lh_v!r}")
                _raft = "2" if _vtok in (COMBO_CAT_EASYPAL, COMBO_CAT_DUALPAL) else "0"
                if d.get("raft_layers") != _raft:
                    err(f"[功能歸類・棧板 raft {_raft}] {name}: raft_layers={d.get('raft_layers')!r}")
                # renamed_from＝字串＋恰為對應舊材料對全名（改名批回溯鏈）
                _new2old = {COMBO_CAT_EASY: "PLA+SUP", COMBO_CAT_PVA: "PLA+PVA",
                            COMBO_CAT_EASYPAL: "ABS+SUP", COMBO_CAT_DUAL: "PLA+PLA",
                            COMBO_CAT_DUALPAL: "ABS+ABS"}
                _rf = d.get("renamed_from")
                _rf_expect = name.replace(" %s @" % _vtok, " %s @" % _new2old[_vtok])
                if not isinstance(_rf, str) or _rf != _rf_expect:
                    err(f"[功能歸類・renamed_from] {name}: {_rf!r}, expected {_rf_expect!r}")
    if kind == "filament":
        if d.get("instantiation") == "true":
            pv = d.get("filament_minimal_purge_on_wipe_tower")
            pv = pv[0] if isinstance(pv, list) and pv else pv
            expected_pv = ("120" if ("四料高流量噴頭" in name or "(3in1)" in name)
                           else "85" if "PVA" in name else "60" if "SupPLA" in name else "30")
            if pv is not None and pv != expected_pv:
                err(f"[洗料塔最小清理量] {name}: {pv!r}, expected {expected_pv!r}")
            # 檢查 11（Eric 2026-07-18 裁「擴及所有材料」）：冷卻降速一律開＋降速層時間 10 秒
            if d.get("slow_down_for_layer_cooling") != ["1"]:
                err(f"[冷卻降速未開] {name}: {d.get('slow_down_for_layer_cooling')!r}")
            if d.get("slow_down_layer_time") != ["10"]:
                err(f"[降速層時間非 10] {name}: {d.get('slow_down_layer_time')!r}")
            # 線材回抽統一（Eric 2026-07-23 三裁）：四項＋額外回填流量律＋長度收斂
            if name.startswith("PING"):
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
                # 檢查 13 線材側（Eric 2026-07-24 爬坡品質批）：懸空冷卻觸發閾值全線材 25%
                if _v("overhang_fan_threshold") != "25%":
                    err(f"[懸空冷卻閾值 25% 0724] {name}: {_v('overhang_fan_threshold')!r}")
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
                if not is_hf and "TPE" not in name and "PA-CF" not in name:
                    if _v("enable_pressure_advance") != "1" or _v("pressure_advance") != "0.08":
                        err(f"[一般流量 PA 0.08 0728] {name}: enable={_v('enable_pressure_advance')!r} "
                            f"pa={_v('pressure_advance')!r}, expected 1/0.08")
                if "TPE" in name or "PVA" in name:
                    if _v("filament_retraction_length") != "3":
                        err(f"[TPE/PVA 回抽長度 3] {name}: {_v('filament_retraction_length')!r}")
                elif ("高流量" in name) or ("(3in1)" in name):
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
        if _mn == "FD300 同進照片磚" and ("PING PLA - 220" in _dmt or "PING PLA - 210" not in _dmt):
            err(f"[照片磚 model 預設 210 0728v2] {_mn}: {_md.get('default_materials')!r}")

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
        err(f"[跨層護欄・process token 集合] 實得 {sorted(_proc_tokens)!r} ≠ 期望五類")
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
        if cxx_escape("+棧板") not in _psrc and '"+棧板"' not in _psrc:
            err("[跨層護欄・#39 棧板建議] 守衛未改「+棧板」判定（舊 ABS+ 守衛對新名失效）")
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
        if _ent[1].get("renamed_from") != _row["old"]:
            err(f"[功能歸類・id baseline] {_row['new']}: renamed_from={_ent[1].get('renamed_from')!r} ≠ {_row['old']!r}")

print(f"presets: {len(presets)} | machines: {len(machines)}")
if errors:
    print(f"\n[FAIL] {len(errors)} 個問題：")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("[OK] 參照完整性全部通過")
