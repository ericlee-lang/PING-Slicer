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
import os
import re
import sys

PINGDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "resources", "profiles", "PING")
ROOT_JSON = PINGDIR + ".json"

errors = []

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

def classic_model_for_machine(name):
    for model, spec in CLASSIC.items():
        if name == f"{model} {spec['nozzle']} nozzle":
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
            # PLA+PVA 專屬製程（Eric 2026-07-25 裁「出」；值＝V2.1 定稿案對帳）：案值特例覆蓋家規。
            # 支撐角 50 ＝ 案值 Cura 40 換算（Orca ＝ 90 − Cura）＝比全庫 35 多支撐＝水溶支撐合理特例。
            if "PLA+PVA" in name:
                expected["support_threshold_angle"] = "50"
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
                _spacing = ("%g" % round(nz_v * 19, 2)) if "PLA+PVA" in name else ("%g" % (nz_v * 9))
                # ★ Classic 前代改為**跟進**新工藝（Eric 2026-07-25 裁）：樹狀配方一併查。
                #   口徑安全＝CLASSIC_SPECS 每台 nozzle == src_nozzle，母檔算的口徑連動值直接成立。
                _cls_proc = any(t in name for t in ("@DUAL", "@PING ", "@EDU"))
                _geo = [("tree_support_branch_diameter", "%g" % min(nz_v * 12, 10.0)),
                        ("tree_support_branch_distance", "%g" % (nz_v * 6)),
                        ("support_base_pattern_spacing", _spacing)]
                for key, value in _geo:
                    if d.get(key) != value:
                        err(f"[support geometry 口徑連動] {name}: {key}={d.get(key)!r}, expected {value!r}")
                # 普通支撐配方（Eric 2026-07-22 七裁；行為四項同日二裁擴及易拆）
                expected_recipe = [("support_type", "normal(auto)"),
                                   ("independent_support_layer_height", "0"),
                                   ("support_style", "snug"),
                                   ("support_base_pattern", "rectilinear")]
                # Classic 前代（@DUAL/@PING/@EDU）＝Fast 母檔複製：雙料複製自 PLA+SUP＝易拆幾何 0.45 正確，XY 不以一般律查
                is_classic = any(t in name for t in ("@DUAL", "@PING ", "@EDU"))
                # PLA+PVA＝易拆類（PVA 為水溶支撐料、與 PLA 不相熔，同 +SUP 家族）
                # ⇒ XY 走易拆家規 口徑×0.75，不套一般支撐的 ×1
                if "PLA+PVA" in name:
                    expected_recipe.append(("support_object_xy_distance", "%g" % round(nz_v * 0.75, 2)))
                elif "+SUP" not in name and "3in1" not in name and not is_classic:
                    expected_recipe.append(("support_object_xy_distance", "%g" % round(nz_v * 1.0, 2)))
                for key, value in expected_recipe:
                    if d.get(key) != value:
                        err(f"[普通支撐配方 0722] {name}: {key}={d.get(key)!r}, expected {value!r}")
                # 樹狀支撐保守配方（Eric 2026-07-25 裁）：只在使用者手動切「混合樹」後生效，
                # 預設 normal(auto)+snug 不受影響。auto_brim 必須為 0，否則 brim_width 被引擎忽略
                #（TreeSupport.cpp:2068）。_organic 兩鍵＝防呆（snug+樹狀會被引擎退回 default＝有機樹）：
                # 🔴 diameter_organic 2.6 是 bug 修——Print.cpp:1532 硬限 ≥2×支撐線寬，
                #    FF 系 1.0 口徑線寬 1.02 需 ≥2.04，舊值 2 會讓那 4 支勾樹狀即切片報錯。
                for key, value in [("tree_support_branch_angle", "30"),
                                   ("tree_support_auto_brim", "0"),
                                   ("tree_support_brim_width", "10"),
                                   ("tree_support_wall_count", "1"),
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
            _tower = "45" if "PLA+PVA" in name else "25"
            if "照片磚" not in name and d.get("prime_tower_width") != _tower:
                err(f"[洗料塔寬度 {_tower}] {name}: prime_tower_width={d.get('prime_tower_width')!r}")
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
            # 檢查 11（Eric 2026-07-18 裁「擴及所有材料」）：冷卻降速一律開＋降速層時間 10 秒
            if d.get("slow_down_for_layer_cooling") != ["1"]:
                err(f"[冷卻降速未開] {name}: {d.get('slow_down_for_layer_cooling')!r}")
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
                #   ⚠ Classic 前代線材另有 PA 全關斷言（Marlin 無 PA），不受本條影響。
                if is_hf and _v("pressure_advance") == "0.12":
                    err(f"[PA 0.12 只限一般流量 0725] {name}: 高流量/3in1 家族不得用 0.12")
                # PVA 與 TPE 同列（Eric 2026-07-24 PVA 對帳 V2.1 定稿＝回抽長度 3）
                # ⚠ 0725 稽核抓漏：本行原只認 TPE，PVA 落到 else 被要求 nil ⇒ 與主線不同步
                if "TPE" in name or "PVA" in name:
                    if _v("filament_retraction_length") != "3":
                        err(f"[TPE/PVA 回抽長度 3] {name}: {_v('filament_retraction_length')!r}")
                elif is_hf:
                    if _v("filament_retraction_length") != "2":
                        err(f"[高流量家族長度 2（0723 補裁含 3in1）] {name}: {_v('filament_retraction_length')!r}")
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
classic_filaments = ("PING PLA - Classic 210", "PING PLA - Classic 220",
                     "PING SupPLA - Classic", "PING PLA - EDU Classic")
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

# 🔴 型別護欄（0725 T004 事故）：`renamed_from` 必須是**字串**，寫成 JSON 陣列會讓
# PresetBundle.cpp:4098 的 unescape_strings_cstyle 收到 array → nlohmann 丟
# type_error.302「type must be string, but is array」→ 該 filament 檔載入失敗
# → **整包 PING vendor 解析中止** → 使用者開起來沒有任何 PING 機型、跳設定精靈、
#   機器掉成 Default Printer。多個舊名用 **分號** 串接（Config.cpp:146 以 ';' 分隔）。
# 教訓：verify 過去只查「參照與值」，查不到「引擎能不能載入」——這類型別錯是啞的。
for _n, (_k, _d) in presets.items():
    _rf = _d.get("renamed_from")
    if _rf is not None and not isinstance(_rf, str):
        err(f"[renamed_from 型別錯 — 會讓整包 vendor 載入失敗] {_n}: {_rf!r}（須為分號字串）")

print(f"presets: {len(presets)} | machines: {len(machines)}")
if errors:
    print(f"\n[FAIL] {len(errors)} 個問題：")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("[OK] 參照完整性全部通過")
