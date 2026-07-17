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
    if printer_name.startswith("FD300"):
        return "tree(auto)"
    if printer_name.startswith("FF600 同進"):
        return "tree(auto)"
    if printer_name.startswith("FF600"):
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
                "default_acceleration": "0",
                "sparse_infill_acceleration": "0",
                "travel_acceleration": "0",
                "seam_position": "aligned",
            } if is_classic else {
                "sparse_infill_acceleration": "10000",
                "travel_acceleration": "3000",
                "seam_position": "back",
            } if "照片磚" in name else {
                "sparse_infill_acceleration": "5000",
                "travel_acceleration": "5000",
                "seam_position": "aligned",
            })
            for key, value in expected.items():
                if d.get(key) != value:
                    err(f"[process safety default] {name}: {key}={d.get(key)!r}, expected {value!r}")
            # 檢查 7/8（Eric 2026-07-17 裁）：支撐幾何口徑連動＋洗料塔寬 25（照片磚不在 release 線）
            m_nz = re.search(r"\(([\d.]+)\)\s*$", name)
            if m_nz and "照片磚" not in name:
                nz_v = float(m_nz.group(1))
                for key, value in (("tree_support_branch_diameter", "%g" % (nz_v * 10)),
                                   ("support_base_pattern_spacing", "%g" % (nz_v * 8))):
                    if d.get(key) != value:
                        err(f"[support geometry 口徑連動] {name}: {key}={d.get(key)!r}, expected {value!r}")
            if "照片磚" not in name and d.get("prime_tower_width") != "25":
                err(f"[洗料塔寬度 25] {name}: prime_tower_width={d.get('prime_tower_width')!r}")
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
            expected_pv = ("120" if ("四料高流量噴頭" in name or "(3in1)" in name)
                           else "60" if "SupPLA" in name else "30")
            if pv is not None and pv != expected_pv:
                err(f"[洗料塔最小清理量] {name}: {pv!r}, expected {expected_pv!r}")

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

print(f"presets: {len(presets)} | machines: {len(machines)}")
if errors:
    print(f"\n[FAIL] {len(errors)} 個問題：")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("[OK] 參照完整性全部通過")
