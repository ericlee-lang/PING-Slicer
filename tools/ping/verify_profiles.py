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
                # 支撐臨界角 60（Eric 2026-07-24；V3.0 底稿 30 全庫翻正；照片磚豁免）
                "support_threshold_angle": "60",
            })
            # jerk 對齊機器上限（Eric 2026-07-20 裁）：FD/FP 系=7、FF 系=40（上限 56 不動）
            expected["default_jerk"] = "40" if "@FF" in name else "7"
            for key, value in expected.items():
                if d.get(key) != value:
                    err(f"[process safety default] {name}: {key}={d.get(key)!r}, expected {value!r}")
            m_nz = re.search(r"\(([\d.]+)\)\s*$", name)
            if m_nz and "照片磚" not in name:
                nz = float(m_nz.group(1))
                # 線距 2026-07-22 裁 ×9（密度 10%＝Cura 全庫等效；蓋 7/17 ×8=12.5%）
                for key, value in (("tree_support_branch_diameter", "%g" % (nz * 10)),
                                   ("support_base_pattern_spacing", "%g" % (nz * 9))):
                    if d.get(key) != value:
                        err(f"[support geometry 口徑連動] {name}: {key}={d.get(key)!r}, expected {value!r}")
                # 普通支撐配方（Eric 2026-07-22 七裁；行為四項同日二裁擴及易拆）：
                # 類型/獨立層高/樣式/圖案＝全支撐；XY＝一般口徑×1（易拆維持 7/14 各自定稿不查）
                expected_recipe = [("support_type", "normal(auto)"),
                                   ("independent_support_layer_height", "0"),
                                   ("support_style", "snug"),
                                   ("support_base_pattern", "rectilinear")]
                if "+SUP" not in name and "3in1" not in name:
                    expected_recipe.append(("support_object_xy_distance", "%g" % round(nz * 1.0, 2)))
                for key, value in expected_recipe:
                    if d.get(key) != value:
                        err(f"[普通支撐配方 0722] {name}: {key}={d.get(key)!r}, expected {value!r}")
            if d.get("prime_tower_width") != "25":
                err(f"[洗料塔寬度 25] {name}: prime_tower_width={d.get('prime_tower_width')!r}")
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

print(f"presets: {len(presets)} | machines: {len(machines)}")
if errors:
    print(f"\n[FAIL] {len(errors)} 個問題：")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("[OK] 參照完整性全部通過")
