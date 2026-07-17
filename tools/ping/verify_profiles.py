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
    if kind == "process":
        if d.get("instantiation") == "true":
            expected = ({
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
            m_nz = re.search(r"\(([\d.]+)\)\s*$", name)
            if m_nz and "照片磚" not in name:
                nz = float(m_nz.group(1))
                for key, value in (("tree_support_branch_diameter", "%g" % (nz * 10)),
                                   ("support_base_pattern_spacing", "%g" % (nz * 8))):
                    if d.get(key) != value:
                        err(f"[support geometry 口徑連動] {name}: {key}={d.get(key)!r}, expected {value!r}")
        fmt = d.get("filename_format", "")
        if fmt:
            if ord(fmt[0]) > 127:
                err(f"[filename_format 開頭非 ASCII — PlaceholderParser 會炸] {name}: {fmt[:20]}")
            for i, ch in enumerate(fmt[1:], 1):
                if ord(ch) > 127 and fmt[i - 1] == "}":
                    err(f"[filename_format '}}' 後接非 ASCII — 會炸] {name}: ...{fmt[max(0,i-5):i+5]}...")

print(f"presets: {len(presets)} | machines: {len(machines)}")
if errors:
    print(f"\n[FAIL] {len(errors)} 個問題：")
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("[OK] 參照完整性全部通過")
