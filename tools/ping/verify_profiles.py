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

PINGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "resources", "profiles", "PING")
ROOT_JSON = PINGDIR + ".json"

errors = []


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
            if "PLA+PVA" in name:
                expected["support_threshold_angle"] = "50"
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
                _spacing = ("%g" % round(nz * 19, 2)) if "PLA+PVA" in name else ("%g" % (nz * 9))
                for key, value in (("tree_support_branch_diameter", "%g" % min(nz * 12, 10.0)),
                                   ("tree_support_branch_distance", "%g" % (nz * 6)),
                                   ("support_base_pattern_spacing", _spacing)):
                    if d.get(key) != value:
                        err(f"[support geometry 口徑連動] {name}: {key}={d.get(key)!r}, expected {value!r}")
                # 普通支撐配方（Eric 2026-07-22 七裁；行為四項同日二裁擴及易拆）：
                # 類型/獨立層高/樣式/圖案＝全支撐；XY＝一般口徑×1（易拆維持 7/14 各自定稿不查）
                expected_recipe = [("support_type", "normal(auto)"),
                                   ("independent_support_layer_height", "0"),
                                   ("support_style", "snug"),
                                   ("support_base_pattern", "rectilinear")]
                # PLA+PVA＝易拆類（PVA 為水溶支撐料、與 PLA 不相熔，同 +SUP 家族）
                # ⇒ XY 走易拆家規 口徑×0.75，不套一般支撐的 ×1
                if "PLA+PVA" in name:
                    expected_recipe.append(("support_object_xy_distance", "%g" % round(nz * 0.75, 2)))
                elif "+SUP" not in name and "3in1" not in name:
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
            _tower = "45" if "PLA+PVA" in name else "25"
            if d.get("prime_tower_width") != _tower:
                err(f"[洗料塔寬度 {_tower}] {name}: prime_tower_width={d.get('prime_tower_width')!r}")
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
                # ★ PA 分流量家族（Eric 2026-07-25 裁「PA 0.12 只用在一般流量上」）
                #   現況表（本裁確認、以下為權威）：
                #     一般流量  PLA-220／PETG／ABS ＝ 0.12
                #     高流量噴頭 PLA／SupPLA／PETG ＝ 0.2
                #     四料高流量 PLA／SupPLA        ＝ 0.4
                #     3in1      PLA 0.4／SupPLA 0.2
                #     TPE／SupTPE                   ＝ 關（0）
                #   本斷言＝單向護欄：**0.12 不得出現在高流量／3in1 家族**（ABS 整併把 0.12 帶進
                #   一般流量支，未經 PA 塔實測；不讓它外溢到流量特性完全不同的噴頭）。
                #   反向不強制（一般流量支未設 PA＝繼承 common，屬既有狀態，不在本裁範圍）。
                if is_hf and _v("pressure_advance") == "0.12":
                    err(f"[PA 0.12 只限一般流量 0725] {name}: 高流量/3in1 家族不得用 0.12")
                if "TPE" in name or "PVA" in name:
                    if _v("filament_retraction_length") != "3":
                        err(f"[TPE/PVA 回抽長度 3] {name}: {_v('filament_retraction_length')!r}")
                elif ("高流量" in name) or ("(3in1)" in name):
                    if _v("filament_retraction_length") != "2":
                        err(f"[高流量家族長度 2（0723 補裁含 3in1）] {name}: {_v('filament_retraction_length')!r}")
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

    # 2) 每個「雙料組合製程」的組合 token 都必須在 COMBO_FILAMENTS 表裡有對應
    _map_keys = set(re.findall(r'\{"([A-Z]{2,4}\+[A-Z]{2,4})",\s*\{', _src))
    if not _map_keys:
        err("[跨層護欄] Tab.cpp 抓不到 COMBO_FILAMENTS 的組合鍵（格式變了？護欄失效）")
    _proc_tokens = set()
    for _n, (_k, _d) in presets.items():
        if _k != "process" or _d.get("instantiation") != "true":
            continue
        _at = _n.find("@")
        if _at <= 0:
            continue
        _head = _n[:_at].rstrip()
        _sp = _head.rfind(" ")
        if _sp == -1:
            continue
        _tok = _head[_sp + 1:]
        if "+" in _tok:
            _proc_tokens.add(_tok)
    for _tok in sorted(_proc_tokens - _map_keys):
        err(f"[跨層護欄・組合製程沒有連動對應] 製程存在 {_tok} 但 Tab.cpp COMBO_FILAMENTS 無此鍵 "
            f"⇒ 使用者選了該模式，線材槽不會跟著換")

print(f"presets: {len(presets)} | machines: {len(machines)}")
if errors:
    print(f"\n[FAIL] {len(errors)} 個問題：")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("[OK] 參照完整性全部通過")
