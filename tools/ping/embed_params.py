#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PING 參數嵌入器 v2 — 完整 F 系列（11 機型家族、136 config）
吃參數端交付：G:\\...\\20260603 切片參數\\PING Slicer V3.5\\F系列參數\\{機型}\\*.config
→ 依 OrcaSlicer 權威分類拆 machine / process → 寫 resources/profiles/PING/ → 重建 PING.json

用法（repo 根目錄）：
    python tools/ping/embed_params.py            # 用預設交付路徑
    python tools/ping/embed_params.py "<F系列參數資料夾>"

結構（2026-06-10 定案）：
- 7 個 FD 雙料家族（FD300 / FD300 E / FD300 Pro / FD300 E Pro / FD450/600/800 Pro）
  × 3 模式（雙料=家族名 / 單料頭 / 同進，各自獨立 printer_model）× 3 口徑。
  雙料 4 組合（PLA+SUP/PLA+PLA/ABS+SUP/ABS+ABS）共用機台/製程，只差線材選擇 →
  機台/製程一律取 PLA+SUP 為母檔。
- FP300 / FP300 E：單料機（口徑 0.2/0.4/0.6——單料機最小 0.2、雙料機最小 0.25）。
- FF600 / FF800（交付夾名帶 Pro、preset 名不帶）：四進一出四色，口徑 0.6/1.0；
  線材 0.6/1.0 數值不同 → 口徑別子 preset（@FF 0.6 / @FF 1.0，alias 顯示母名），
  FF600/FF800 同口徑共用。

軟體端 override（源檔尚未套用的裁定值；參數端源檔修正後可移除）：
- 加速度規範(2026-06-07)：300級=3000 / 450+級=1500 / travel=3000（FF 維持實機值，未裁定）
- Scarf 接縫(§8)：seam_slope_type=external / start 10% / min_length 8
  （注意 2.3.2 無 has_scarf_joint_seam key，external 即啟用）
- 單料頭/同進/FP 製程速度(2026-06-10 裁定)：travel 250 / 填充 60 / support 40
"""
import re, json, os, sys, io, shutil, glob

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PINGDIR = os.path.join(REPO, "resources", "profiles", "PING")
PROF = os.path.join(REPO, "resources", "profiles")
PRESET_CPP = os.path.join(REPO, "src", "libslic3r", "Preset.cpp")
DEFAULT_SRC = r"G:\我的雲端硬碟\2026claude\20260603 切片參數\PING Slicer V3.5\F系列參數"
# FF 同進/3in1 範本（無源 config、屬衍生模式）：已驗證手工檔收進 repo 當範本，重產時複製併入。
# 內含 machine（含 machine_model 底檔）／process／filament（3in1 專用 T4/T3 料）／cover。
# 2026-07-01：3in1 收 2 槽（T4/T3 走 filament_start_gcode）+ 同進(T5) 編進產生器（範本複製法）。
FF_EXTRA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base", "ff_extra")
# ★ 照片磚範本（2026-07-08 收編）：垂直混色照片磚專用機（衍生自同進、Eric 實印驗證）。
# 無源 config——%APPDATA% 手工建置檔收進 repo 當範本（建置腳本見當時 scratchpad
# build_phototile_machine.py／extend_phototile_nozzles.py／build_fd300_phototile.py）。
# 範本已含：SEMM=1（槽位才會吃 64 槽 default_filament_profile）＋64 槽開滿＋
# Eric 四項製程預設（填充0%／上下殼0層／牆2圈／接縫背部）＋零回抽（retraction 全 0
# ＋use_firmware_retraction=0，防繞道 Klipper G10）＋seam_gap 0%/wipe_on_loops 0
#（2026-07-08 轉角 C 缺口定案）。機名含「同進」＝gcode 後處理閘門零改碼認得。
# 順序寫死＝重現 %APPDATA% 建置時的 setting_id（PINGM066-070／PINGP111-115）。
PHOTOTILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base", "phototile")
PHOTOTILE_MACHINES = ["FF800 同進照片磚 0.6 nozzle", "FF800 同進照片磚 0.4 nozzle",
                      "FF800 同進照片磚 1.0 nozzle", "FD300 同進照片磚 0.4 nozzle",
                      "FD300 同進照片磚 0.6 nozzle"]
PHOTOTILE_PROCS = ["0.35mm @FF800 同進照片磚 (0.6)", "0.25mm @FF800 同進照片磚 (0.4)",
                   "0.45mm @FF800 同進照片磚 (1.0)", "0.2mm @FD300 同進照片磚 (0.4)",
                   "0.3mm @FD300 同進照片磚 (0.6)"]

# ---------- 1. OrcaSlicer 權威 key 分類 ----------
_src = open(PRESET_CPP, encoding="utf-8", errors="ignore").read()
def _ex(v):
    m = re.search(r"s_Preset_%s_options\s*\{(.*?)\n\}" % v, _src, re.S)
    return set(re.findall(r'"([a-zA-Z_][a-zA-Z0-9_]*)"', m.group(1))) if m else set()
PROC, FILA, MACH = _ex("print"), _ex("filament"), _ex("printer")
MACH |= _ex("machine_limits")   # printer_options() 會 append machine_max_*

# 專案層/身分 key——不進任何 preset（含 2.3.2 載入時會報 incorrect keys 的項目）
SKIP = {"from","name","version","inherits_group","different_settings_to_system",
        "print_settings_id","printer_settings_id","filament_settings_id",
        "print_compatible_printers","is_custom_defined",
        # machine 層會被剝除的專案 key（debug log: incorrect keys）
        "filament_ids","flush_multiplier","flush_volumes_matrix","flush_volumes_vector",
        "start_end_points",
        # process 層會被剝除的專案/盤面 key
        "bbl_calib_mark_logo","curr_bed_type","first_layer_print_sequence",
        "other_layers_print_sequence","other_layers_print_sequence_nums",
        "wipe_tower_x","wipe_tower_y","has_scarf_joint_seam"}
# 未列權威清單、需手動歸 machine 者（per-extruder/槽位類）
FORCE_M = {"deretraction_speed","extruder_colour","extruder_offset","max_layer_height",
    "min_layer_height","nozzle_diameter","retract_before_wipe","retract_length_toolchange",
    "retract_lift_above","retract_lift_below","retract_restart_extra","retract_restart_extra_toolchange",
    "retract_when_changing_layer","retraction_length","retraction_minimum_travel","retraction_speed",
    "wipe","wipe_distance","z_hop","default_filament_profile",
    "filament_colors","default_filament_colors"}
FORCE_P = {"Each_layer_prime_tower","overhang_speed_classic",
    "rotate_solid_infill_direction","tree_support_adaptive_layer_height",
    "tree_support_branch_diameter_double_wall",
    "layer_height","slice_closing_radius","filename_format"}

def cat(k):
    if k in SKIP: return None
    if k in FORCE_M: return "M"
    if k in FORCE_P: return "P"
    if k in MACH and k not in PROC: return "M"
    if k in FILA and k not in PROC: return "F"
    if k in PROC: return "P"
    return "P"

def split(cfg):
    b = {"M":{}, "P":{}, "F":{}}
    for k,v in cfg.items():
        c = cat(k)
        if c: b[c][k] = v
    return b

def fil_at(cfg_F, idx, feeds):
    """從扁平 filament 區取第 idx 槽 → 單槽 filament 預設值"""
    out = {}
    for k,v in cfg_F.items():
        if isinstance(v, list) and len(v) > idx:
            out[k] = [v[idx]]
        else:
            out[k] = v
    return out

def jdump(path, obj):
    json.dump(obj, io.open(path,"w",encoding="utf-8"), ensure_ascii=False, indent=4)

# ---------- 2. 機型家族定義 ----------
# (交付夾名, preset 機型名, kind)；kind: dual=雙料機3模式 / single=單料機 / ff=四進一出
# 順序＝精靈顯示順序（2026-06-10 使用者定）：單料 → 雙料 → 四料；同類依列印範圍小→大
FAMS = [
    ("FP300",       "FP300",       "single"),
    ("FD300",       "FD300",       "dual"),
    ("FD300 Pro",   "FD300 Pro",   "dual"),
    ("FD450 Pro",   "FD450 Pro",   "dual"),
    ("FD600 Pro",   "FD600 Pro",   "dual"),
    ("FD800 Pro",   "FD800 Pro",   "dual"),
    ("FF600 Pro",   "FF600",       "ff"),
    ("FF800 Pro",   "FF800",       "ff"),
]
# PING(2026-06-12)：P200+（過渡版）是「客戶專屬」機型，不進通用版 FAMS。
# 客戶精簡交付：環境變數 PING_ONLY=P200+ → FAMS 換成只剩 P200+ 這一台（其餘全砍、
# FF 線材也跳過）→ 產出「只有這台機器」的客戶版 build（讀 FP300 config + 床 override）。
PING_ONLY = os.environ.get("PING_ONLY", "").strip()
if PING_ONLY == "P200+":
    FAMS = [("FP300", "P200+", "single")]
elif PING_ONLY:
    raise SystemExit("不支援的 PING_ONLY=%r（目前僅 P200+）" % PING_ONLY)
# 資安版 E 機型（FD300 E / FD300 E Pro / FP300 E）不上 slicer 精靈——2026-06-10 使用者定
# （畫面太滿；參數端交付 config 保留，要上架時加回 FAMS 即可）
DEF_FIL_DUAL   = ["PING PLA - 220", "PING SupPLA"]
DEF_FIL_SINGLE = ["PING PLA - 220"]
# ★ 高流量噴頭專用線材（2026-07-12 Eric 裁定：高流量＝噴頭屬性非機型屬性，回抽值落材料層；
# 規格 _切片規則同步_來自pingslicer_高流量噴頭線材_20260712.md）。不分口徑、不限機型
#（無 compatible_printers）。覆蓋值＝Eric %APPDATA% 權威樣本 4 鍵（規格表另列的擦拭/空駛
# 欄樣本未覆蓋＝吃機器層，照「權威＝樣本」抄 4 鍵，偏差已回報參數端）。
HFN_PLA = "PING PLA - 高流量噴頭"
HFN_SUP = "PING SupPLA - 高流量噴頭"
HFN_PETG = "PING PETG - 高流量噴頭"   # 2026-07-18 Eric：PETG 也開高流量支
# 2026-07-12 Eric 二裁：擦拭/空駛 4 欄也入覆蓋（8 鍵＝完整定義；取代同日稍早「4 鍵免加」）
# 2026-07-12 統一四值④：PA 0.2 兩支都套；噴溫 210/210 只 PLA 版（SupPLA 版溫度待 Eric 裁）
HFN_OVERRIDES = {"filament_retraction_length": ["2"], "filament_retraction_speed": ["30"],
                 "filament_deretraction_speed": ["30"], "filament_retract_restart_extra": ["0.6"],
                 "filament_retraction_minimum_travel": ["3"], "filament_wipe": ["1"],
                 "filament_wipe_distance": ["5"], "filament_retract_before_wipe": ["100%"],
                 "enable_pressure_advance": ["1"], "pressure_advance": ["0.2"]}
# 2026-07-12 Eric 補裁：SupPLA 版噴溫同 210（高流量噴頭組整組統一 210/210，不套 SUP=220 慣例）
HFN_EXTRA = {HFN_PLA: {"nozzle_temperature_initial_layer": ["210"], "nozzle_temperature": ["210"]},
             HFN_SUP: {"nozzle_temperature_initial_layer": ["210"], "nozzle_temperature": ["210"]},
             # PETG 高流量（2026-07-18 Eric）：235/床75 承 PETG-235 基底、PA 0.2 由 HFN_OVERRIDES 帶
             HFN_PETG: {}}
# FD450/600/800 Pro 出廠＝高流量噴頭 → 預設線材改高流量支（FD300 系/FP300 不動）
def def_fil_dual_for(base):
    return [HFN_PLA, HFN_SUP] if tier_of(base) == "450" else DEF_FIL_DUAL
def def_fil_single_for(base):
    return [HFN_PLA] if tier_of(base) == "450" else DEF_FIL_SINGLE
# FF 四料線材改名（同裁定：綁機型＝錯）：「高流量 @FF」→「四料高流量噴頭」系、解除機型綁定。
# setting_id/filament_id 不變（同一支材料身份）；3in1 專用支不動。
FF_FIL_ALIAS = {"PLA": "PING PLA - 四料高流量噴頭", "SupPLA": "PING SupPLA - 四料高流量噴頭"}
FF_FIL_RENAME = {}   # 舊名→新名（4b 填入，供 ff_extra/照片磚範本 default 引用改名）
for _nz in ("0.4", "0.6", "1.0"):
    # 2026-07-18 口徑合一：舊「@FF 口徑」與「四料高流量噴頭 口徑」一律指到合併支（無口徑尾碼）
    FF_FIL_RENAME["PING PLA - 高流量 @FF %s" % _nz] = FF_FIL_ALIAS["PLA"]
    FF_FIL_RENAME["PING SupPLA - 高流量 @FF %s" % _nz] = FF_FIL_ALIAS["SupPLA"]
    FF_FIL_RENAME["%s %s" % (FF_FIL_ALIAS["PLA"], _nz)] = FF_FIL_ALIAS["PLA"]
    FF_FIL_RENAME["%s %s" % (FF_FIL_ALIAS["SupPLA"], _nz)] = FF_FIL_ALIAS["SupPLA"]
def _dedup_semilist(s):
    """分號清單去重（保序）。口徑合一（2026-07-18）後多口徑引用同映到合併支會重複——
    default_materials 重複無意義，去重＝921921c8 手工清 2 項的 regen-durable 版。"""
    seen, out = set(), []
    for x in s.split(";"):
        if x and x not in seen:
            seen.add(x); out.append(x)
    return ";".join(out)
def rename_ff_filament_refs(d):
    """機器/機型檔內的高流量 @FF 引用改新名（default_filament_profile／default_materials）"""
    v = d.get("default_filament_profile")
    if isinstance(v, list):
        d["default_filament_profile"] = [FF_FIL_RENAME.get(x, x) for x in v]
    dm = d.get("default_materials")
    if isinstance(dm, str):
        d["default_materials"] = _dedup_semilist(";".join(FF_FIL_RENAME.get(x, x) for x in dm.split(";")))
# PING(2026-07-02)：範本收編的口徑變體——machine 檔在 ff_extra（無交付 config，Eric 已實機驗收），
# 這裡只把口徑補進 machine_model 的 nozzle_diameter（精靈勾選）；default_materials 維持交付口徑不動。
EXTRA_MODEL_NOZZLES = {"FF800": ["0.4"]}
def def_fil_ff(nz):
    # 口徑合一（2026-07-18）：四槽預設＝合併支，不再帶口徑尾碼
    return [FF_FIL_ALIAS["PLA"]]*3 + [FF_FIL_ALIAS["SupPLA"]]
DEFAULT_MATERIALS_FD = ("PING PLA - 220;PING SupPLA;PING ABS - 250;PING PLA;"
                        "PING PolyABS;PING SupABS;PING PETG - 235;PING PETG;PING ABS;PING PA-CF;"
                        # 高流量噴頭支入精靈預設清單（FD450+ 預設線材要看得見；任何 FD 換噴頭可選）
                        "PING PLA - 高流量噴頭;PING SupPLA - 高流量噴頭;PING PETG - 高流量噴頭")
# 床模型依機台直徑（300mm 原盤 XY 等比縮放產生；2026-06-10 修 FF600 黑色床板不滿版）
BED_TEXTURE = "ping_buildplate_texture.png"
BED_STL = {"FD300":"PING_FD300_buildplate_model.stl","FP300":"PING_FD300_buildplate_model.stl",
           "P200+":"P200+_buildplate_model.stl",   # 250 床盤（FD300 300 盤 ×0.833 置中）切齊網格
           "FD450":"PING_FD450_buildplate_model.stl",
           "FD600":"PING_FD600_buildplate_model.stl","FF600":"PING_FD600_buildplate_model.stl",
           "FD800":"PING_FD800_buildplate_model.stl","FF800":"PING_FD800_buildplate_model.stl"}
def bed_for(model):
    key = max((k for k in BED_STL if model.startswith(k)), key=len)
    return BED_STL[key]

# PING(2026-06-12)：衍生機型——吃別人的 G槽 config，只改「列印範圍」（床/高/預擠位置）。
# P200+（過渡版，名稱沿用客戶端既有名）：套 FP300 全套參數。
#   - printable_area＝直徑250（門打開的最大列印範圍）、printable_height＝200
#   - ⚠預擠線位置用「門關」常態直徑200（半徑100）計算：FP300 Y-140/-138（距前緣10mm）
#     → 平移 50mm 至 -90/-88（落在半徑100 內，門關著也不撞）。X±50 在範圍內不動。
# 床 STL 沿用 FD300（視覺略大、過渡機可接受）。
BED_OVERRIDE = {
    # bed_texture：P200+ 專屬床貼圖——在門開列印範圍 250 內多畫一圈「門關 200」橘色標示
    #（P200+_buildplate_texture.png＝原圖＋直徑200橘圈，0.8×網格半徑；使用者 2026-06-15 要求）
    "P200+": {"area_diameter": 250.0, "height": "200", "prime_y_shift": 50,
              "bed_texture": "P200+_buildplate_texture.png",
              "nozzles": ["0.4", "0.6"]},   # 去掉 0.2、只留 0.4/0.6（使用者 2026-06-15）
}
def scale_circle_area(area_pts, target_diameter):
    """圓床 printable_area 是以床心(0,0)為原點的 72 點；FP300 半徑150 → 等比縮放至目標直徑"""
    s = (target_diameter / 2.0) / 150.0
    out = []
    for p in area_pts:
        x, y = p.split("x")
        out.append("%gx%g" % (round(float(x) * s, 4), round(float(y) * s, 4)))
    return out
def apply_bed_override(model, mac):
    ov = BED_OVERRIDE.get(model)
    if not ov:
        return
    if isinstance(mac.get("printable_area"), list):
        mac["printable_area"] = scale_circle_area(mac["printable_area"], ov["area_diameter"])
    mac["printable_height"] = ov["height"]
    sg = mac.get("machine_start_gcode")
    if isinstance(sg, str):   # 預擠線 Y 往床心平移（門關直徑計），避免門關時超出床
        mac["machine_start_gcode"] = re.sub(
            r"Y(-1[34][0-9])", lambda m: "Y%d" % (int(m.group(1)) + ov["prime_y_shift"]), sg)

# ★ FD300/FP300 預擠「左側弧線」幾何定稿（2026-07-14 Eric 雙料實機定稿，取代 2026-07-09 初版
# 掃角 195-225°/R140-134/E15——全部作廢）：弧中點方位角 209°、弦長固定 100mm（半角＝asin(50/R)）、
# 半徑由外而內 144/142/140/138（間距 2mm）、I/J＝圓心(0,0)−弧起點、每弧 E＝直線版同量
#（0.4 基準 E30，既有口徑流量比：0.2→16／0.25→20／0.6→45）、Z＝各口徑首層高、
# 末弧 G1 Z1 E(e−1)（抬升＋回抽 1mm）。座標採定稿 gcode 字面值（規格檔
# _切片規則同步_來自pingslicer_FD300弧線預擠幾何定稿_20260714.md）——實機驗過，勿以公式重算竄動；
# 半徑固定故全口徑共用同一組座標，只有 Z/E 隨口徑。
_FD300_ARC_PTS = {  # r: (a=188.7° 側點, b=229.3° 側點)；G3 走 a→b、G2 走 b→a
    144: ((-142.35, -21.74), (-93.88, -109.21)),
    142: ((-140.49, -20.70), (-92.00, -108.17)),
    140: ((-138.63, -19.67), (-90.13, -107.13)),
    138: ((-136.77, -18.63), (-88.26, -106.09)),
}
def _fd300_arc_block(radii_tools, z, e):
    """radii_tools=[(半徑, T字串或None), ...] 由外而內；偶數索引 G3 去、奇數索引 G2 回。"""
    lines = []
    for i, (r, tool) in enumerate(radii_tools):
        a, b = _FD300_ARC_PTS[r]
        start, end, cmd = (a, b, "G3") if i % 2 == 0 else (b, a, "G2")
        if tool is not None:
            lines.append(tool)
        lines.append("G0 F%d X%.2f Y%.2f Z%s" % (8000 if i == 0 else 800, start[0], start[1], z))
        lines.append("G92 E0")
        lines.append("%s F800 X%.2f Y%.2f I%.2f J%.2f E%s" % (cmd, end[0], end[1], -start[0], -start[1], e))
        if i < len(radii_tools) - 1:
            lines.append("G92 E0")
    lines.append("G1 Z1 E%g" % (float(e) - 1))
    lines.append("G92 E0")
    return "\n".join(lines)

# ★ 預擠段正規化（2026-07-12 Eric 抓錯）：①預擠段「中途」travel 誤植 F8000（多一個 0，
# 熱料拖行過快）→ 除第一個接近 travel 保留 F8000 外，其餘 G0 F8000 一律改 F800。
# ②T0/T1 交替預擠的最後一條改成 T0（起印主料免多一次換刀）——交替序整組對調
#（T0,T1,T0,T1 → T1,T0,T1,T0）。僅動獨立成行的 T0/T1（M104/M107 的 T0 參數不受影響）；
# 3in1 的 T4/T3 與 FF 四色不在此規則（Eric 限定 T0/T1 交替）。
_T01_LINE = re.compile(r"^(T[01])\s*$", re.M)
def normalize_prime_lines(mac):
    sg = mac.get("machine_start_gcode")
    if not isinstance(sg, str) or "G0" not in sg:
        return
    # ① 中途 travel F8000 → F800（保留第一個）
    parts = sg.split("G0 F8000")
    if len(parts) > 2:
        sg = parts[0] + "G0 F8000" + "G0 F800".join(parts[1:])
    # ② T0/T1 交替 → 對調使結尾為 T0
    tools = _T01_LINE.findall(sg)
    if len(tools) >= 2 and set(tools) == {"T0", "T1"} and tools[-1] == "T1":
        sg = _T01_LINE.sub(lambda m: "T1" if m.group(1) == "T0" else "T0", sg)
    mac["machine_start_gcode"] = sg

def apply_fd300_prime_arc(model, mac):
    # 白名單（Eric 2026-07-14「目前只針對 FD300/FP300 即可」）：FD300 非 Pro 三模式＋FP300 新納入
    #（同 300 床殼直線預擠一樣撞門）。FD300 Pro／E 系、FP300 E 未提及＝不套；FD450+/FF 無門問題。
    # ⚠ P200+/FP200 絕不可納入：衍生自 FP300 但床只有 250（半徑 125）——R144 弧會超出床外；
    # 它的預擠本就按門關 200 另算（apply_bed_override 預擠內移），此處用「全名精確比對」防繼承。
    if model not in ("FD300", "FD300 單料頭", "FD300 同進", "FP300"):
        return
    sg = mac.get("machine_start_gcode")
    if not isinstance(sg, str) or "G28 ;Home" not in sg or "Y-140" not in sg:
        return
    m_z = re.search(r"G0 F8000 [^\n]*?Z([\d.]+)", sg)
    m_e = re.search(r"G1 F800 [^\n]*?E([\d.]+)", sg)
    if not m_z or not m_e:
        return
    z, e = m_z.group(1), m_e.group(1)   # 取直線版的首層高與每線 E（口徑流量比已在源檔）
    head = sg.split("G28 ;Home", 1)[0] + "G28 ;Home"
    if "M6050" in sg:
        head += "\nM6050 S0.5"
    if "\nT1\n" in sg:   # 雙料：4 弧交替、最後一條 T0（2026-07-12 Eric 定＝起印主料免換刀）
        block = _fd300_arc_block([(144, "T1"), (142, "T0"), (140, "T1"), (138, "T0")], z, e)
    else:                # 單料頭/同進/FP300：2 弧（外側 R144/142，由 4 弧定稿裁減、待實機驗）
        block = _fd300_arc_block([(144, None), (142, None)], z, e)
    mac["machine_start_gcode"] = head + "\n" + block

# ★ 預擠點升溫（2026-07-19 Eric 裁定：開印前不預熱噴頭——預熱會滴料還要清料）：
# header 只留熱床（M140/M190，前加 M117 Bed heating 提示），G28 歸位＋移動全程冷噴頭；
# 移到預擠第一點（第一個 G0 F8000 接近 travel）後才 M109 升溫等到溫（M117 Nozzle heating），
# 到溫後恆溫等 60 秒才預擠——每秒一則 M117 倒數（Eric UX 準則 2026-07-19：機器靜止時面板
# 一定要有提示、顯示要即時、不留資訊空白；步驟可精簡、顯示不可跳格）。結尾 M117 清空提示。
# 提示文字＝中文（2026-07-19 CLI 實切驗證通過：FD600 Pro 同進 0.4＋高流量 PLA，M117 中文完好、
# 佔位符正常代入——filename_tpl 的非 ASCII 炸雷是「模板規則邊界」特有，純文字行不觸發）。
# 引擎不會自動補溫：GCode.cpp _print_first_layer_extruder_temperatures 只檢查 custom gcode 內
# 「有沒有」M104/M109（custom_gcode_sets_temperature）——M109 搬進預擠點仍在 start gcode 內，
# 與搬移前走同一分支（只記狀態、不輸出）。post-pass 套所有 machine/*.json（見 main 4e），
# 主迴圈＋ff_extra＋照片磚一體適用；冪等（marker＝M117 噴頭加熱中）。
_HEAT_HEAD = re.compile(r"^M10[49] S\[nozzle_temperature_initial_layer\][^\n]*\n", re.M)
def apply_deferred_heating(mac):
    sg = mac.get("machine_start_gcode")
    if not isinstance(sg, str) or "M117 噴頭加熱中" in sg:
        return False
    # FF 四色交付源 gcode 帶髒空白（行尾空白＋行首空白＋空行）→ 先逐行 strip 統一格式，
    # 其餘機檔本就乾淨＝strip 零變化；不 strip 則行首錨定（^M109/^G0）比對不到。
    sg = "\n".join(l.strip() for l in sg.split("\n") if l.strip())
    m109 = re.search(r"^M109 S\[nozzle_temperature_initial_layer\][^\n]*$", sg, re.M)
    if not m109 or not re.search(r"^G0 F8000 ", sg, re.M):
        return False
    m109_line = m109.group(0)
    sg = _HEAT_HEAD.sub("", sg)                                      # header 去 M104/M109
    sg = sg.replace("\nM140 S[", "\nM117 熱床加熱中\nM140 S[", 1)    # 熱床等待提示
    heat = ["M117 噴頭加熱中", m109_line]
    for s in range(60, 0, -1):                                       # 到溫後 60 秒恆溫，每秒倒數
        heat += ["M117 恆溫等待 %d 秒" % s, "G4 P1000"]
    heat.append("M117 預擠中")
    trav = re.search(r"^G0 F8000 [^\n]*$", sg, re.M)                 # 預擠第一點的接近 travel
    sg = sg[:trav.end()] + "\n" + "\n".join(heat) + sg[trav.end():]
    mac["machine_start_gcode"] = sg.rstrip("\n") + "\nM117"          # 收尾清空面板提示
    return True

def tier_of(base):
    # 300 級＝加速度3000＋一般流量（小機單/雙噴頭）；450+＝1500＋高流量（大機標配高流量噴頭）
    # P200+（過渡版）物理上是 250 小機單噴頭，與 FP300 同級（一般流量、勿套高流量）
    return "300" if base.startswith(("FD300","FP300","P200+")) else "450"

def filename_tpl(mode_key):
    """輸出檔名模板（2026-06-10 使用者定）：模式_檔名_線材_重量_時間。
    雙料依「槽2是否支撐材」自動判：易拆(裝SUP)/雙色(裝一般料)；同進=Mix；四色=四色；單料頭/FP=單料。
    重量/時間用 PING 佔位符（Print.cpp PrintStatistics：total_weight_str=395g/2.3kg、
    print_time_hm=15m/7h15m/1d8h）——需 B6(run 27262735687) 之後的 binary。
    ⚠ 前綴一律包進 code block 字串字面值 {"X_"}：PlaceholderParser 模板的 rule 邊界
    （開頭、} 之後）遇非 ASCII 即 throw（pre-skip skipper）、裸中文前綴會炸
    「Non-ASCII7 characters...」；字串字面值是 lexeme[utf8char]、中文合法。"""
    base = "{input_filename_base}_{filament_type[initial_tool]}_{total_weight_str}_{print_time_hm}.gcode"
    if mode_key in ("PLA+SUP", "ABS+SUP"): return '{"易拆_"}' + base   # 組合別製程→前綴直判，免模板條件式
    if mode_key in ("PLA+PLA", "ABS+ABS"): return '{"雙色_"}' + base
    if mode_key == "同進":  return '{"Mix_"}' + base
    if mode_key == "四色":  return '{"四色_"}' + base
    return '{"單料_"}' + base   # 單料頭 / FP300

def proc_overrides(kind, base, is_single_mode):
    """軟體端裁定值 override（FF 不套）。
    2026-06-11 大清理（吃當日交付驗證）：加速度(3000/1500)、scarf=none、速度兩線新裁定
    （雙料/FP 60-80-150、單料頭/同進 50-60-150、口徑連動填充）——源檔已全套→override 拿掉
    （「源檔套完→拿掉 embed override」原則）。
    接縫與兩個加速度由 normalize_unified_values 集中套用，此處不再覆寫。"""
    return {}

# ★ 主線製程統一值（Eric 2026-07-15 最新裁定；取代 2026-07-12 的 aligned_back／travel 20000，
# 規格 _切片規則同步_來自orca_主線保守加速度與接縫_20260715.md）：
# ①首層流量比 1.1（set_other_flow_ratios 開；其餘流量比維持預設 1）
# ②接縫位置＝對齊 aligned（⚠ enum 對映：UI「對齊」=aligned；「背部對齊」=aligned_back；
#   照片磚特調用的是 back＋seam_gap0——本函式不套照片磚，見 emit_phototile 註）
# ③空駛加速度 5000（20000 會造成馬達錯位／失步；空駛速度 250 不變）
# 全 PING 製程套（含棧板雙生＝從已正規化的 proc 派生自然繼承）；DL1016 不在 repo 自然跳過；
# 照片磚特調跳過（seam/換料路徑特調，已回報參數端）。
def normalize_unified_values(proc):
    proc["set_other_flow_ratios"] = "1"
    proc["first_layer_flow_ratio"] = "1.1"
    proc["seam_position"] = "aligned"
    proc["travel_acceleration"] = "5000"
    return proc

# ★ 支撐介面一律值（Eric 2026-07-14 裁）：頂部接觸面層數 4、頂部接觸面間距 0.1。
# 只「收緊不放鬆」：層數 1/2→4；間距比 0.1 鬆（0.2/0.4/0.5/1）→0.1；
# 比 0.1 更密的既有定稿不動（ABS+SUP 黃金 0.04、3in1 實心 0——是否也收 0.1 待 Eric 另裁）。
# 範本 emit（ff_extra 3in1/同進、照片磚）不套（範本已驗證不改值原則）；DL1016 不在 repo 自然跳過。
def normalize_support_interface(proc):
    if proc.get("support_interface_top_layers") in ("1", "2"):
        proc["support_interface_top_layers"] = "4"
    if proc.get("support_interface_spacing") in ("0.2", "0.4", "0.5", "1"):
        proc["support_interface_spacing"] = "0.1"
    return proc

# ★ 支撐幾何口徑連動（Eric 2026-07-17 裁）：樹狀支撐分支直徑＝口徑×10、
# 主體圖案線距＝支撐線寬/支撐密度 12.5%＝口徑×8。分子用口徑名目值
#（FF 微調線寬 0.41/0.62/1.02 不入分子，全庫統一 3.2/4.8/8）；全口徑含 0.2/0.25
# 照公式（0.2→2/1.6、0.25→2.5/2）；照片磚維持獨立特調不套（emit_phototile 不呼叫）。
def normalize_support_geometry(proc, nozzle):
    proc["tree_support_branch_diameter"] = "%g" % (float(nozzle) * 10)
    proc["support_base_pattern_spacing"] = "%g" % (float(nozzle) * 8)
    return proc

# ★ 牆速/填充正規化（2026-07-05，吃參數端規格 _切片規則同步_來自pingslicer_牆速填充_20260703.md）
# Eric 定「公司不在意快、在意穩定品質」→ 牆（外/內）降速求品質、吞吐靠填充高速＋高加速。
# 全 Fast 系列（FD/FF/FP）標準製程統一：
#   外牆 60（統一，含單料/同進/四色）；內牆 min(現值,80)（只降不升——單料/同進內 60 不升）；
#   填充 100（2026-07-19 Eric 裁 150→100 全機型，新規蓋舊規）；
#   填充加速度 sparse_infill_acceleration=5000（2026-07-15 由 10000 下修，避免錯位／失步）。
#   首層速度 initial_layer_speed 不動；solid/top/gap 不在規格 → 交回源檔（順帶對齊 Cura V2.1）。
# ⚠ 此規（2026-07-03）取代舊 HF_SPEED「速度＝口徑×流量上限、75/100/150 暫定」的 2026-06-11 裁定
#   （新規蓋舊規：牆慢統一 60，不再逐口徑寫死高流量速度）。
# 例外（不套、維持材料特例）：PA-CF crater（材料專屬製程另出，is_pacf=True 跳過）；
#   TPE 軟料 40/70（目前無 TPE 製程檔，故①不觸及；未來若出 TPE 製程一樣要跳過）。
def normalize_fast_speed(proc, is_pacf=False, preserve_sparse_acceleration=False):
    if is_pacf:
        return proc   # PA-CF 火山口製程走自己的 50/80/80，見 pacf_overrides
    try:
        cur_inner = float(proc.get("inner_wall_speed", "80"))
    except (TypeError, ValueError):
        cur_inner = 80.0
    proc["outer_wall_speed"] = "60"
    proc["inner_wall_speed"] = "%g" % min(cur_inner, 80.0)
    proc["sparse_infill_speed"] = "100"
    if not preserve_sparse_acceleration:
        proc["sparse_infill_acceleration"] = "5000"
    return proc

# ★ 換料塔預設（2026-07-08 Eric 拍板・規格 _切片規則同步_來自pingslicer_換料塔與棧板雙版本_20260708.md；
# 寬度 2026-07-17 Eric 改裁 15→25，新規蓋舊規）：全庫統一 寬 25＋外牆肋條（rib）。
# 肋寬/圓角吃引擎預設（PrintConfig.cpp wipe_tower_rib_width tooltip）。單料機不顯示換料塔、
# 寫入無副作用 → 不分機型全寫（含 FF 範本/照片磚範本——照片磚 enable_prime_tower=0 無副作用）。
def normalize_prime_tower(proc):
    proc["prime_tower_width"] = "25"
    proc["wipe_tower_wall_type"] = "rib"
    return proc

# ★ 棧板雙版本製程（2026-07-08 Eric 拍板，同上規格檔）：FD 單料頭/同進＋FP300 出「_棧板」雙生
#（raft 六鍵＝既有 ABS+SUP 黃金配方定稿值，與 0.2mm ABS+SUP @FD300 (0.4).json 全等）。
# 裁決：①FF 全系/DL1016/雙料組合不出 ②切回一般版不自動換回 PLA（Tab.cpp 單向連動）
# ③雙料 ABS+SUP/ABS+ABS 維持現名（功能上已是棧板版）。
# setting_id 一律排在全庫既有 id 之後（主迴圈收集、最後統一 emit），既有 id 零位移。
PALLET_OVERRIDES = {"raft_layers": "2", "raft_contact_distance": "0.1", "raft_expansion": "1.5",
                    "raft_first_layer_density": "100%", "raft_first_layer_expansion": "3",
                    "initial_layer_line_width": "150%"}

# ---------- 3. 交付檔解析 ----------
def parse_dir(src_base, dirname):
    """回傳 {(nozzle, mode): config}；mode ∈ {dual, 單料頭, 同進, 四色}（dual=PLA+SUP 母檔）"""
    prefix = dirname.replace(" ", "_") + "_"
    d = os.path.join(src_base, dirname)
    out = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith("_project_settings.config"): continue
        body = fn[len(prefix):-len("_project_settings.config")]
        nozzle = body.split("_")[0]
        rest = body[len(nozzle)+1:]
        # PETG 檔（單料頭/同進_PETG，2026-06-11 補 48 檔）：與 PLA 版差異 100% 在 filament 層
        # （235/床75/風扇50/密度1.27，已驗證製程 key 零差異）→ 不出製程，只建 PING PETG - 235 線材
        if "PETG" in rest: continue
        if   rest in ("PLA+SUP","PLA+PLA","ABS+SUP","ABS+ABS"): mode = rest  # 雙料 4 組合各自成製程
        elif rest.startswith("單料頭"):   mode = "單料頭"
        elif rest.startswith("同進"):     mode = "同進"
        elif rest.startswith("四色"):     mode = "四色"
        else: continue
        out[(nozzle, mode)] = json.load(io.open(os.path.join(d, fn), encoding="utf-8"))
    return out

DUAL_COMBOS = ["PLA+SUP", "PLA+PLA", "ABS+SUP", "ABS+ABS"]

def combo_overrides(combo, layer_height, nozzle):
    """V3.0 組合別製程差異復原（2026-06-10 使用者規格＋V3.0「最佳 ABS」定稿實證）：
    - 支撐介面：有 SUP＝z 距離 0（貼緊、靠支撐料好剝）；無 SUP＝1 層層高（留縫好拆）
    - Raft：ABS 系＝2 層、PLA 系＝0
    - ABS+SUP 另套 V3.0 黃金支撐配方（normal/主體料1/界面料2/界面4·2層/間距0.04/xy0.5）
    - PLA+SUP 支撐幾何（Eric 2026-07-14 裁）：XY=口徑×0.75、支撐/物件第一層間隙=口徑/3
      （易拆支撐口徑公式；ABS+SUP 維持黃金配方 xy0.5 不套）"""
    o = {}
    if combo.endswith("+SUP"):
        o.update({"support_top_z_distance": "0", "support_bottom_z_distance": "0"})
    else:
        o.update({"support_top_z_distance": layer_height, "support_bottom_z_distance": layer_height})
    if combo == "PLA+SUP":
        o.update({"support_object_xy_distance": "%g" % round(float(nozzle) * 0.75, 2),
                  "support_object_first_layer_gap": "%g" % round(float(nozzle) / 3.0, 2)})
    if combo.startswith("ABS"):
        o["raft_layers"] = "2"
        # ABS 首層線寬 1.5×口徑（「最佳ABS(更新後)」定稿 0.4 噴嘴=0.6；百分比隨口徑縮放）
        o["initial_layer_line_width"] = "150%"
    if combo == "ABS+SUP":
        o.update({"support_type": "normal(auto)", "support_base_pattern": "rectilinear",
                  "support_filament": "1", "support_interface_filament": "2",
                  "support_interface_top_layers": "4", "support_interface_bottom_layers": "2",
                  "support_interface_spacing": "0.04", "support_bottom_interface_spacing": "0",
                  "support_object_xy_distance": "0.5"})
    return o

def emit_ff_extra(mm_list, mac_list, proc_list, gm, gp):
    """範本複製法：把已驗證的 FF 同進/3in1 machine/process/filament/cover 併入產出。
    - machine（type=machine 的口徑變體）：重指 setting_id（續 gm 計數避免撞號）→ mac_list
    - machine_model（底檔）：→ mm_list
    - process：重指 setting_id（續 gp）→ proc_list
    - filament（3in1 專用 PLA(3in1)/SupPLA(3in1)，含 T4/T3 filament_start_gcode、淺灰支撐色）→ 回傳 ff_fil
    - cover：複製到 PINGDIR（受 4c 孤兒清除保護，見 ff_models）
    回傳 (gm, gp, ff_fil, ff_models)。範本本身已驗證，不再改值、只重編 setting_id。"""
    ff_fil, ff_models = [], []
    n_mac = n_proc = n_cov = 0
    for fn in sorted(os.listdir(os.path.join(FF_EXTRA, "machine"))):
        d = json.load(io.open(os.path.join(FF_EXTRA, "machine", fn), encoding="utf-8"))
        rename_ff_filament_refs(d)   # 高流量 @FF → 四料高流量噴頭（2026-07-12 改名）
        name = d["name"]
        if d.get("type") == "machine_model":
            mm_list.append({"name": name, "sub_path": "machine/%s.json" % name}); ff_models.append(name)
        else:
            d["setting_id"] = "PINGM%03d" % gm; gm += 1
            mac_list.append({"name": name, "sub_path": "machine/%s.json" % name}); n_mac += 1
        jdump(os.path.join(PINGDIR, "machine", "%s.json" % name), d)
    for fn in sorted(os.listdir(os.path.join(FF_EXTRA, "process"))):
        d = json.load(io.open(os.path.join(FF_EXTRA, "process", fn), encoding="utf-8"))
        normalize_fast_speed(d)   # FF 範本製程同套牆速正規化（75/100/150 與 100/100/100 → 60/80/100）
        normalize_prime_tower(d)  # 換料塔 15＋肋條（2026-07-08）
        normalize_unified_values(d)  # 主線統一值（2026-07-15 最新裁定）
        m_nz = re.search(r"\(([\d.]+)\)\s*$", d["name"])   # 名尾口徑，如 "0.35mm @FF600 3in1 (0.6)"
        if m_nz:
            normalize_support_geometry(d, m_nz.group(1))  # 樹狀直徑×10＋主體線距×8（2026-07-17，FF 範本同套）
        d["setting_id"] = "PINGP%03d" % gp; gp += 1
        jdump(os.path.join(PINGDIR, "process", "%s.json" % d["name"]), d)
        proc_list.append({"name": d["name"], "sub_path": "process/%s.json" % d["name"]}); n_proc += 1
    for fn in sorted(os.listdir(os.path.join(FF_EXTRA, "filament"))):
        d = json.load(io.open(os.path.join(FF_EXTRA, "filament", fn), encoding="utf-8"))
        jdump(os.path.join(PINGDIR, "filament", "%s.json" % d["name"]), d)
        ff_fil.append({"name": d["name"], "sub_path": "filament/%s.json" % d["name"]})
    for fn in os.listdir(os.path.join(FF_EXTRA, "cover")):
        shutil.copy2(os.path.join(FF_EXTRA, "cover", fn), os.path.join(PINGDIR, fn)); n_cov += 1
    print("  ff_extra 併入：machine=%d + machine_model=%d，process=%d，filament=%d，cover=%d"
          % (n_mac, len(ff_models), n_proc, len(ff_fil), n_cov))
    return gm, gp, ff_fil, ff_models

def emit_phototile(mm_list, mac_list, proc_list, gm, gp):
    """照片磚範本併入（比照 emit_ff_extra 範本複製法）：machine_model×2＋口徑變體×5＋製程×5＋cover×2。
    製程套 normalize_fast_speed 的牆速／填充速度，但保留照片磚專屬 sparse acceleration；
    範本源值 75/100 是 %APPDATA% 建置當時未同步正規化的舊值→進 repo 時對齊。
    其餘照範本不改值、只重編 setting_id。回傳 (gm, gp, pt_models)。"""
    pt_models = []
    for fn in sorted(os.listdir(os.path.join(PHOTOTILE, "machine"))):
        d = json.load(io.open(os.path.join(PHOTOTILE, "machine", fn), encoding="utf-8"))
        rename_ff_filament_refs(d)   # 照片磚 64 槽高流量引用改新名（2026-07-12）
        if d.get("type") == "machine_model":
            jdump(os.path.join(PINGDIR, "machine", "%s.json" % d["name"]), d)
            mm_list.append({"name": d["name"], "sub_path": "machine/%s.json" % d["name"]})
            pt_models.append(d["name"])
    for name in PHOTOTILE_MACHINES:
        d = json.load(io.open(os.path.join(PHOTOTILE, "machine", "%s.json" % name), encoding="utf-8"))
        rename_ff_filament_refs(d)   # 照片磚 64 槽高流量引用改新名（2026-07-12）
        if name.startswith("FD300 同進照片磚"):   # FD300 硬體同款門 → 預擠同套左側弧線
            apply_fd300_prime_arc("FD300 同進", d)
        d["setting_id"] = "PINGM%03d" % gm; gm += 1
        jdump(os.path.join(PINGDIR, "machine", "%s.json" % name), d)
        mac_list.append({"name": name, "sub_path": "machine/%s.json" % name})
    for name in PHOTOTILE_PROCS:
        d = json.load(io.open(os.path.join(PHOTOTILE, "process", "%s.json" % name), encoding="utf-8"))
        normalize_fast_speed(d, preserve_sparse_acceleration=True)
        # 照片磚特調稀疏填充加速度＝10000（verify 期望；0715 主線下修 5000 不套照片磚）。
        # 範本源檔殘留 '100%' 舊值（%APPDATA% 建置當時的相對值）→ 比照範本速度值「進 repo 時對齊」。
        d["sparse_infill_acceleration"] = "10000"
        normalize_prime_tower(d)  # 統一寫（照片磚 enable_prime_tower=0、無副作用）
        # ⚠ 主線統一值「不套」照片磚：照片磚維持 back＋seam_gap0、travel 3000，
        # 稀疏填充加速度也保留特調範本值；主線 2026-07-15 保守值不得蓋進照片磚。
        d["setting_id"] = "PINGP%03d" % gp; gp += 1
        jdump(os.path.join(PINGDIR, "process", "%s.json" % name), d)
        proc_list.append({"name": name, "sub_path": "process/%s.json" % name})
    for fn in os.listdir(os.path.join(PHOTOTILE, "cover")):
        shutil.copy2(os.path.join(PHOTOTILE, "cover", fn), os.path.join(PINGDIR, fn))
    print("  phototile 併入：machine=%d + machine_model=%d，process=%d，cover=2"
          % (len(PHOTOTILE_MACHINES), len(pt_models), len(PHOTOTILE_PROCS)))
    return gm, gp, pt_models

# ---------- 4. 主流程 ----------
def main(src_base):
    # 4a. 清掉舊 machine/process（保留 fdm 基底）
    for sub, keep in (("machine", ("fdm_machine_common.json","fdm_ping_common.json")),
                      ("process", ("fdm_process_common.json","fdm_process_ping_common.json"))):
        d = os.path.join(PINGDIR, sub)
        for f in os.listdir(d):
            if f.endswith(".json") and f not in keep:
                os.remove(os.path.join(d, f))

    gm = gp = 0
    mm_list, mac_list, proc_list = [], [], []
    nozzles_of = {}   # model -> [nz...]
    pallet_twins = []   # 棧板雙生製程（主迴圈收集、4a-4 統一 emit＝id 排最後）

    for dirname, base, kind in FAMS:
        cfgs = parse_dir(src_base, dirname)
        if kind == "dual":
            modes = [("PLA+SUP", base, def_fil_dual_for(base), False),   # 雙料機母檔=PLA+SUP；製程另出 4 組合
                     ("單料頭", base + " 單料頭", def_fil_single_for(base), True),
                     ("同進",   base + " 同進",   def_fil_single_for(base), True)]
        elif kind == "single":
            modes = [("單料頭", base, def_fil_single_for(base), True)]
        else:
            modes = [("四色", base, None, False)]

        for mode_key, model, def_fil, is_single in modes:
            nzs = sorted({nz for (nz, mk) in cfgs if mk == mode_key}, key=float)
            _only_nz = BED_OVERRIDE.get(model, {}).get("nozzles")   # 衍生機型限定口徑（P200+ 去 0.2）
            if _only_nz:
                nzs = [n for n in nzs if n in _only_nz]
            if not nzs:
                print("  !! %s 缺 %s config" % (dirname, mode_key)); continue
            nozzles_of[model] = nzs
            for nz in nzs:
                c = cfgs[(nz, mode_key)]
                b = split(c)
                lh = c.get("layer_height", "0.2")
                mac_name = "%s %s nozzle" % (model, nz)
                # 雙料機：製程依 4 組合各出一支（V3.0 行為復原，2026-06-10）；其餘一機一製程
                is_dual_machine = (kind == "dual" and mode_key == "PLA+SUP")
                combos = [cb for cb in DUAL_COMBOS if (nz, cb) in cfgs] if is_dual_machine else [mode_key]
                def pname(cb):
                    return ("%smm %s @%s (%s)" % (lh, cb, model, nz)) if is_dual_machine \
                        else ("%smm @%s (%s)" % (lh, model, nz))
                # machine（雙料取 PLA+SUP 母檔）
                mac = dict(b["M"])
                # PING(2026-06-10)：換層回抽=關（全機型）——花瓶模式換層縫線明顯（使用者規格）
                if isinstance(mac.get("retract_when_changing_layer"), list):
                    mac["retract_when_changing_layer"] = ["0"] * len(mac["retract_when_changing_layer"])
                mac.update({"type":"machine","name":mac_name,"from":"system","instantiation":"true",
                    "setting_id":"PINGM%03d"%gm,"printer_model":model,"printer_variant":nz,
                    "default_print_profile":pname(combos[0]),
                    # alias=機型名 → active 標籤顯示乾淨名；口徑走噴嘴 chip(printer_variant)
                    "alias":model})
                mac["default_filament_profile"] = def_fil if def_fil else def_fil_ff(nz)
                # PING(2026-06-16)：max_layer_height 隨口徑連動＝0.75×口徑（OrcaSlicer 慣例）。
                # 修源檔把 0.35 一律套全機型、把 1.0 口徑標準層高 0.5 夾成 0.35 的 bug（陣列長度保留）。
                _mlh = "%g" % round(0.75 * float(nz), 4)
                _old_mlh = mac.get("max_layer_height")
                mac["max_layer_height"] = [_mlh] * (len(_old_mlh) if isinstance(_old_mlh, list) and _old_mlh else 1)
                apply_bed_override(model, mac)   # 衍生機型改列印範圍（FP200：床250/高200/預擠內移）
                normalize_prime_lines(mac)         # 預擠中途 travel F800＋T0/T1 結尾 T0（2026-07-12）
                apply_fd300_prime_arc(model, mac)  # FD300 預擠改左側弧線（防撞門，2026-07-09）
                jdump(os.path.join(PINGDIR,"machine","%s.json"%mac_name), mac)
                mac_list.append({"name":mac_name,"sub_path":"machine/%s.json"%mac_name}); gm += 1
                # processes（inherits 必須指向存在父 preset，絕不可空字串——坑#12）
                for cb in combos:
                    pb = split(cfgs[(nz, cb)])["P"] if is_dual_machine else b["P"]
                    proc = dict(pb)
                    # PING 支撐通用（2026-06-16）：攤平母檔會夾帶 Orca 原始預設 support_base_pattern=rectilinear
                    # 與 tree_support_wall_count=0，蓋掉 fdm_process_ping_common 的「空心／樹狀牆1」→ 先移除讓葉檔
                    # 繼承 common。ABS+SUP 的 V3.0 黃金支撐配方在 combo_overrides 之後另行覆寫，不受影響。
                    proc.pop("support_base_pattern", None)
                    proc.pop("tree_support_wall_count", None)
                    proc.update(proc_overrides(kind, base, is_single))
                    if is_dual_machine:
                        proc.update(combo_overrides(cb, lh, nz))
                    normalize_fast_speed(proc)   # 牆速/填充正規化（外60/內≤80/填100/accel5000；首層不動）
                    normalize_prime_tower(proc)  # 換料塔 15＋肋條（2026-07-08）
                    normalize_unified_values(proc)  # 主線統一值（2026-07-15 最新裁定）
                    normalize_support_interface(proc)  # 支撐介面一律 4 層/間距 0.1（2026-07-14）
                    normalize_support_geometry(proc, nz)  # 樹狀直徑口徑×10＋主體線距口徑×8（2026-07-17）
                    proc.update({"type":"process","name":pname(cb),"from":"system","instantiation":"true",
                        "setting_id":"PINGP%03d"%gp,"inherits":"fdm_process_ping_common",
                        "compatible_printers":[mac_name],
                        "filename_format": filename_tpl(cb)})
                    jdump(os.path.join(PINGDIR,"process","%s.json"%pname(cb)), proc)
                    proc_list.append({"name":pname(cb),"sub_path":"process/%s.json"%pname(cb)}); gp += 1
                    # 棧板雙生（單料頭/同進/FP 限定；kind=ff 的四色 is_single=False 天然排除）
                    if is_single and not PING_ONLY:
                        tw = dict(proc); tw.update(PALLET_OVERRIDES)
                        tw["name"] = "%smm_棧板 @%s (%s)" % (lh, model, nz)
                        pallet_twins.append(tw)

            # machine_model（每個 printer_model 一檔）；nozzle_diameter 併入範本收編口徑（如 FF800 0.4）
            mm_nzs = sorted(set(nzs) | set(EXTRA_MODEL_NOZZLES.get(model, [])), key=float)
            mm = {"type":"machine_model","name":model,
                  "model_id":"PING_"+model.replace(" ","_"),
                  "nozzle_diameter":";".join(mm_nzs),"machine_tech":"FFF","family":"",
                  "bed_model":bed_for(model),
                  "bed_texture":BED_OVERRIDE.get(model,{}).get("bed_texture",BED_TEXTURE),"hotend_model":"",
                  # FF：口徑合一後各口徑同指合併支 → 去重（921921c8 手工清 2 項的 regen-durable 版）
                  "default_materials": (_dedup_semilist(";".join(def_fil_ff(nzs[0]) + def_fil_ff(nzs[-1])))
                                        if kind=="ff" else DEFAULT_MATERIALS_FD)}
            jdump(os.path.join(PINGDIR,"machine","%s.json"%model), mm)
            mm_list.append({"name":model,"sub_path":"machine/%s.json"%model})

    # 4a-2. FF 同進/3in1 範本併入（衍生模式、無源 config）。須在 4b 之前跑，
    #       好讓 existing_machines 含 同進/3in1 機台 → 高流量線材 compatible 掛得到。
    if any(f[2] == "ff" for f in FAMS) and not PING_ONLY:
        gm, gp, ff_fil, ff_models = emit_ff_extra(mm_list, mac_list, proc_list, gm, gp)
    else:
        ff_fil, ff_models = [], []
    # 4a-3. 照片磚範本併入（需 FF800/FD300 家族＝通用版；客戶版 PING_ONLY 跳過）。
    #       同樣須在 4b 之前跑，讓高流量 PLA 的 compatible 掛得到照片磚機。
    #       範本資料夾不存在（如無照片磚的 release 分支）＝自動跳過，同一支產生器兩線通用。
    if not PING_ONLY and os.path.isdir(PHOTOTILE):
        gm, gp, pt_models = emit_phototile(mm_list, mac_list, proc_list, gm, gp)
    else:
        pt_models = []

    # 4a-4. 棧板雙生製程統一 emit（setting_id 接在全庫最後＝既有 111＋照片磚 5 支 id 零位移）
    for tw in pallet_twins:
        tw["setting_id"] = "PINGP%03d" % gp; gp += 1
        jdump(os.path.join(PINGDIR, "process", "%s.json" % tw["name"]), tw)
        proc_list.append({"name": tw["name"], "sub_path": "process/%s.json" % tw["name"]})
    if pallet_twins:
        print("  棧板雙生製程：%d 支（PINGP%03d 起）" % (len(pallet_twins), gp - len(pallet_twins)))

    # 4b. FF 高流量線材子 preset（口徑別；FF600/FF800 同口徑同值——已驗證；
    #     0.4 僅 FF600 有（2026-06-11 客戶要求新增）→ compatible 只列「實際存在」的機台）
    fil_new = []
    existing_machines = {m["name"] for m in mac_list}
    ff_cfg = {}   # nz -> 四色 config（FF800 優先；FF800 缺的口徑用 FF600 補，如 0.4）
    for fam in ("FF800 Pro", "FF600 Pro") if any(f[2] == "ff" for f in FAMS) else ():
        for (nz, mk), c in parse_dir(src_base, fam).items():
            if mk == "四色":
                ff_cfg.setdefault(nz, c)
    # 2026-07-18 Eric 裁「口徑合一」：四料高流量噴頭 PLA/SupPLA 各合併為一支——
    # 同一支噴頭只換嘴，原 0.4/0.6/1.0 三支的差異鍵統一為：PA 一律開、最大體積流量 30、
    # 床溫 60/60（噴溫 210 承 0717 裁定）。以 0.6 交付檔為基底。
    src_nz = "0.6" if "0.6" in ff_cfg else (sorted(ff_cfg, key=float)[0] if ff_cfg else None)
    if src_nz:
        F = split(ff_cfg[src_nz])["F"]
        for slot, mat, fid, alias, color, sup in (
                (0, "PLA",    "PINGFILHFPLA", FF_FIL_ALIAS["PLA"],    "#EA4E16", False),
                (3, "SupPLA", "PINGFILHFSUP", FF_FIL_ALIAS["SupPLA"], "#D3D3D3", True)):
            fp = fil_at(F, slot, 4)
            fp.update({"type":"filament","name":alias,"alias":alias,"from":"system",
                "instantiation":"true","setting_id":fid,"filament_id":fid,
                "inherits":"fdm_filament_pla",
                "filament_colors":[color],"default_filament_colors":[color],
                "enable_pressure_advance":["1"],
                # 2026-07-18 Eric 裁：四料兩支 PA 統一 0.4（原 SupPLA 承 0.6 基底帶到 0.12＝漏改）
                "pressure_advance":["0.4"],
                "filament_max_volumetric_speed":["30"],
                "hot_plate_temp":["60"],"hot_plate_temp_initial_layer":["60"]})
            fp.pop("compatible_printers", None)   # 不限機型
            if sup: fp["filament_is_support"] = ["1"]
            # 清洗量維持實機 120（FF 換色需大量清洗；Eric 2026-07-17 裁「不蓋」＝30/60 規則不套 FF）
            # 噴溫一律 210/210（Eric 2026-07-17 裁：0.6 實機 190 塞頭）
            fp["nozzle_temperature_initial_layer"] = ["210"]
            fp["nozzle_temperature"] = ["210"]
            jdump(os.path.join(PINGDIR,"filament","%s.json"%alias), fp)
            fil_new.append({"name":alias,"sub_path":"filament/%s.json"%alias})
    # 舊名檔清除（改名後不留雙份；PING.json 舊條目在 4d 過濾）
    for old in FF_FIL_RENAME:
        oldp = os.path.join(PINGDIR, "filament", "%s.json" % old)
        if os.path.exists(oldp):
            os.remove(oldp); print("  filament 移除(改名):", old)

    # 4b-1b. ★ 高流量噴頭專用線材 2 支（A 案）：承 PLA-220/SupPLA 本體＋樣本 4 鍵覆蓋、
    # 不限機型；SET_RETRACTION 四欄行由基底帶入/4b-2 sweep 保證。
    for base_name, new_name, fid in ((("PING PLA - 220"),  HFN_PLA,  "PINGFILHFNPLA"),
                                     (("PING SupPLA"),     HFN_SUP,  "PINGFILHFNSUP"),
                                     (("PING PETG - 235"), HFN_PETG, "PINGFILHFNPETG")):
        bp = os.path.join(PINGDIR, "filament", "%s.json" % base_name)
        fd_ = json.load(io.open(bp, encoding="utf-8"))
        fd_.update(HFN_OVERRIDES)
        fd_.update(HFN_EXTRA[new_name])
        fd_.update({"name": new_name, "alias": new_name,   # 獨立 alias 勿與其他 PLA 併組
                    "setting_id": fid, "filament_id": fid})
        fd_.pop("compatible_printers", None)   # 不限機型
        jdump(os.path.join(PINGDIR, "filament", "%s.json" % new_name), fd_)
        fil_new.append({"name": new_name, "sub_path": "filament/%s.json" % new_name})

    # 4b-1c. ★ TPE 軟料一對（Eric 2026-07-18 裁，承 V2.1 Cura 線 TPE 工程定稿）：
    # PING TPE（本體，軟慢）＋ PING SupTPE（TPU 系支撐料，可快）。
    # 「軟慢/硬快」靠 filament_max_volumetric_speed 天花板實現（TPE 3.2＝速度上限 40、
    # SupTPE 5.5＝支撐可跑 60+），製程速度欄不必為軟料改值。噴溫 220 兩側一致（定稿）、
    # 床溫承 PLA 慣例 60（Eric 實跑基底）、回抽 3/z-hop 0.6、TPE 風扇 50/SupTPE 100、
    # PA 關（軟料待實測）。不限機型；SET_RETRACTION 行由 4b-2 sweep 保證。
    for new_name, fid, is_sup in (("PING TPE", "PINGFILTPE", False),
                                  ("PING SupTPE", "PINGFILSUPTPE", True)):
        fd_ = {"type": "filament", "name": new_name, "alias": new_name, "from": "system",
               "instantiation": "true", "inherits": "fdm_filament_tpu",
               "setting_id": fid, "filament_id": fid,
               "filament_type": ["TPU"],
               "nozzle_temperature_initial_layer": ["220"], "nozzle_temperature": ["220"],
               "hot_plate_temp_initial_layer": ["60"], "hot_plate_temp": ["60"],
               "fan_min_speed": ["100" if is_sup else "50"],
               "fan_max_speed": ["100" if is_sup else "50"],
               "filament_max_volumetric_speed": ["5.5" if is_sup else "3.2"],
               "filament_retraction_length": ["3"], "filament_z_hop": ["0.6"],
               "enable_pressure_advance": ["0"], "pressure_advance": ["0"],
               "slow_down_for_layer_cooling": ["1"], "slow_down_layer_time": ["10"],
               "filament_minimal_purge_on_wipe_tower": ["30"]}
        if is_sup:
            fd_.update({"filament_is_support": ["1"],
                        "filament_colors": ["#D3D3D3"], "default_filament_colors": ["#D3D3D3"]})
        jdump(os.path.join(PINGDIR, "filament", "%s.json" % new_name), fd_)
        fil_new.append({"name": new_name, "sub_path": "filament/%s.json" % new_name})

    # 4b-2. ★ 回抽切片控制埋全線材（2026-07-12 Eric B 定案，取代同日 HOLD 的 M207/M208 案；
    # SSOT＝ping-slicer gcode.md「線材起始 G-code」節）：改埋 Klipper 原生 SET_RETRACTION
    # ——免機端 wrapper、全機隊（含舊 C8/單料/四料）原生支援、老檔無指令＝機器 config 預設、
    # 速度單位 mm/s 與 Orca 一致。切片端需開 firmware retraction（G10/G11）照舊。
    # ⚠ 交辦單原文 [retract_length] 非 Orca key（會炸 Variable does not exist）→ 實埋
    #   [retraction_length]；三個佔位符皆經 PrintApply filament_overrides 併入 placeholder
    #  （GH #3649 機制，PrintApply.cpp:1250）＝含線材層覆蓋鏈的有效值（07-12 ①查證）。
    # ⚠ 3in1 線材 T4/T3 進料觸發行必須保留（只追加）。既有 M207/M208 行（HOLD 遺留）就地退場。
    # 冪等：已含 SET_RETRACTION 跳過。放 4b 之後＝重生檔（高流量/3in1）每次 regen 自動補。
    sr_added = 0
    SR_LINE = ("SET_RETRACTION RETRACT_LENGTH=[retraction_length] "
               "RETRACT_SPEED=[retraction_speed] UNRETRACT_EXTRA_LENGTH=[retract_restart_extra] "
               "UNRETRACT_SPEED=[deretraction_speed]")   # 第四欄 2026-07-12 Eric 實測抓缺（裝填速度覆蓋要能下機）
    for fp_path in glob.glob(os.path.join(PINGDIR, "filament", "PING*.json")):
        fd = json.load(io.open(fp_path, encoding="utf-8"))
        sg = fd.get("filament_start_gcode")
        cur = (sg[0] if isinstance(sg, list) and sg else sg) or ""
        if "UNRETRACT_SPEED" in cur:
            continue   # 已是四欄新行
        # M207/M208 退場（B 定案）＋舊三欄 SET_RETRACTION 行就地升級成四欄
        cur = "\n".join(l for l in cur.splitlines()
                        if not l.startswith("M207 ") and not l.startswith("M208 ")
                        and not l.startswith("SET_RETRACTION "))
        add = SR_LINE
        if "; Filament gcode" not in cur:
            add = "; Filament gcode\n" + add
        fd["filament_start_gcode"] = [(cur.rstrip() + "\n" + add + "\n") if cur.strip() else (add + "\n")]
        jdump(fp_path, fd)
        sr_added += 1
    if sr_added:
        print("  線材 SET_RETRACTION 回抽控制：+%d 支（M207/M208 退場）" % sr_added)

    # 4b-3. ★ 洗料塔最小清理量（Eric 2026-07-17 裁）：全線材 30；SupPLA 系（含高流量噴頭）60；
    # FF「四料高流量噴頭」/「(3in1)」維持特調 120 不動（四色換色需大量清洗，Eric 同日裁「不蓋」）。
    # 放 4b-2 之後同樣吃冪等 sweep：重生檔每次 regen 自動補。
    pv_set = 0
    for fp_path in glob.glob(os.path.join(PINGDIR, "filament", "PING*.json")):
        bn = os.path.basename(fp_path)
        if "四料高流量噴頭" in bn or "(3in1)" in bn:
            continue
        fd = json.load(io.open(fp_path, encoding="utf-8"))
        want = "60" if "SupPLA" in bn else "30"
        cur = fd.get("filament_minimal_purge_on_wipe_tower")
        if (cur[0] if isinstance(cur, list) else cur) == want:
            continue
        fd["filament_minimal_purge_on_wipe_tower"] = [want]
        jdump(fp_path, fd)
        pv_set += 1
    if pv_set:
        print("  線材洗料塔最小清理量 30/60：改 %d 支（FF 四料/3in1 特調 120 不動）" % pv_set)

    # 4b-4. ★ 機器動力學＝Klipper 實值（Eric 2026-07-17 裁「全機隊直接改」）：
    # 時間預估器用機器檔 machine_max_* 模擬，原值 20000/jerk100 是幻想 → 29h 估 vs 33h 實差 14%。
    # 實值來源＝機隊 repo range cfg：FD/FP＝max_velocity 400/max_accel 5000/SCV 5（jerk≈5×√2≈7）；
    # FF＝200/1500/SCV 40（jerk≈56）。只影響時間預估與 M201/M203（Klipper 忽略），不改列印行為。
    # DL1016（無實測值）與 Classic 前代機（Marlin 另案）跳過。
    mm_set = 0
    for mp_path in glob.glob(os.path.join(PINGDIR, "machine", "*.json")):
        try:
            md_ = json.load(io.open(mp_path, encoding="utf-8"))
        except Exception:
            continue
        if md_.get("type") != "machine" or "machine_max_acceleration_x" not in md_:
            continue
        mname = md_.get("name", "")
        if "DL1016" in mname or re.match(r"^(EDU|DUAL|PING 2|PING 3)", mname):
            continue
        V, A, J = ("200", "1500", "56") if "FF" in mname else ("400", "5000", "7")
        want = {"machine_max_speed_x": [V, V], "machine_max_speed_y": [V, V],
                "machine_max_acceleration_x": [A, A], "machine_max_acceleration_y": [A, A],
                "machine_max_acceleration_extruding": [A, A], "machine_max_acceleration_travel": [A, A],
                "machine_max_acceleration_retracting": [A, A],
                "machine_max_jerk_x": [J, J], "machine_max_jerk_y": [J, J]}
        if all(md_.get(k) == v for k, v in want.items()):
            continue
        md_.update(want)
        jdump(mp_path, md_)
        mm_set += 1
    if mm_set:
        print("  機器動力學=Klipper實值：改 %d 台（FD/FP 400/5000/7、FF 200/1500/56）" % mm_set)

    # 4b-5. ★ 冷卻降速統一（Eric 2026-07-18 裁「擴及所有材料」）：
    # slow_down_for_layer_cooling 一律開＋slow_down_layer_time（最大風扇臨界·每層列印時間）一律 10 秒
    #（原預設 5 與 FF 7/基底 2~8 特調一併統一）。
    cd_set = 0
    for fp_path in glob.glob(os.path.join(PINGDIR, "filament", "*.json")):
        fd = json.load(io.open(fp_path, encoding="utf-8"))
        if fd.get("slow_down_for_layer_cooling") == ["1"] and fd.get("slow_down_layer_time") == ["10"]:
            continue
        fd["slow_down_for_layer_cooling"] = ["1"]
        fd["slow_down_layer_time"] = ["10"]
        jdump(fp_path, fd)
        cd_set += 1
    if cd_set:
        print("  冷卻降速統一（開＋10 秒）：改 %d 支" % cd_set)


    # 4c. 封面（cover 以機型名解析——坑#11）：
    #     家族基本款=機器照片；單料頭/同進 模式卡=透明空白（2026-06-10 使用者定）；孤兒封面刪除
    # 每家族專屬照片（FD300 Pro 有自己的照片，勿沿用 FD300——取最長前綴匹配）
    cover_src = {"FD300 Pro":"FD300 Pro_cover.png","FD300":"FD300_cover.png",
                 "FP300":"FP300_cover.png","P200+":"FP300_cover.png",
                 "FD450":"FD450 Pro_cover.png","FD600":"FD600 Pro_cover.png",
                 "FD800":"FD800 Pro_cover.png","FF600":"FF600_cover.png","FF800":"FF800_cover.png"}
    def blank_png(path):
        from PIL import Image
        Image.new("RGBA", (600, 600), (0, 0, 0, 0)).save(path)
    cover_sources = set(cover_src.values())  # 保留被引用的來源圖（如 P200+ 借 FP300_cover）
    for f in os.listdir(PINGDIR):           # 刪除不屬於現役機型的封面（ff_extra/照片磚 範本模型受保護）
        if f.endswith("_cover.png") and f[:-len("_cover.png")] not in nozzles_of \
           and f[:-len("_cover.png")] not in (ff_models + pt_models) and f not in cover_sources:
            os.remove(os.path.join(PINGDIR, f)); print("  cover 移除(孤兒):", f)
    for model in nozzles_of:
        dst = os.path.join(PINGDIR, "%s_cover.png" % model)
        if model.endswith(("單料頭", "同進")):
            blank_png(dst)                   # 模式卡固定空白（每次重生覆寫，確保不殘留照片）
        elif not os.path.exists(dst):
            key = max((k for k in cover_src if model.startswith(k)), key=len)
            shutil.copy2(os.path.join(PINGDIR, cover_src[key]), dst)
            print("  cover: %s_cover.png <- %s" % (model, cover_src[key]))

    # 4c-2. 側欄印表機縮圖 printer_preview_{model_id}.png（Plater.cpp:3969；缺檔=黑方塊）
    #       全部用「家族機器照」（模式變體同實機）；240x240 RGBA 同上游規格
    from PIL import Image
    img_dir = os.path.join(REPO, "resources", "images")
    for model in list(nozzles_of) + ff_models + pt_models:   # ff_models（同進/3in1）＋照片磚 側欄縮圖也要
        family_cover = cover_src[max((k for k in cover_src if model.startswith(k)), key=len)]
        mm_path = os.path.join(PINGDIR, "machine", "%s.json" % model)
        model_id = json.load(io.open(mm_path, encoding="utf-8"))["model_id"]
        im = Image.open(os.path.join(PINGDIR, family_cover)).convert("RGBA")
        im.thumbnail((240, 240), Image.LANCZOS)
        canvas = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
        canvas.paste(im, ((240-im.width)//2, (240-im.height)//2), im)
        canvas.save(os.path.join(img_dir, "printer_preview_%s.png" % model_id))

    # 4d-0. LAY-11（ping-ux）：machine_model_list 同型號變體相鄰成組——
    # 家族依 FAMS 順序，家族內：基本款 → 單料頭 → 同進 → 3in1（ff_extra 併入的變體不留在清單尾端）
    fam_bases = [f[1] for f in FAMS]
    _variant_rank = {"": 0, "單料頭": 1, "同進": 2, "3in1": 3}
    def _lay11_key(entry):
        name = entry["name"]
        base = max((b for b in fam_bases if name == b or name.startswith(b + " ")), key=len, default=None)
        if base is None:
            return (len(fam_bases), 9, name)   # 不明機型殿後（穩定排序保留原相對順序）
        variant = name[len(base):].strip()
        return (fam_bases.index(base), _variant_rank.get(variant, 9))
    mm_list = sorted(mm_list, key=_lay11_key)

    # 4d. PING.json 重建（machine/process 全量重建；filament 保留既有＋新增 FF）
    pj_path = os.path.join(PROF, "PING.json")
    pj = json.load(io.open(pj_path, encoding="utf-8"))
    pj["machine_model_list"] = mm_list
    pj["machine_list"] = ([{"name":"fdm_machine_common","sub_path":"machine/fdm_machine_common.json"},
                           {"name":"fdm_ping_common","sub_path":"machine/fdm_ping_common.json"}]
                          + mac_list)
    pj["process_list"] = ([{"name":"fdm_process_common","sub_path":"process/fdm_process_common.json"},
                           {"name":"fdm_process_ping_common","sub_path":"process/fdm_process_ping_common.json"}]
                          + proc_list)
    # 高流量 @FF 舊名條目過濾（2026-07-12 改名，檔已刪、條目不留＝防斷鏈）
    pj["filament_list"] = [x for x in pj["filament_list"] if x["name"] not in FF_FIL_RENAME]
    have = {x["name"] for x in pj["filament_list"]}
    pj["filament_list"] += [x for x in (fil_new + ff_fil) if x["name"] not in have]
    # PING_ONLY 精簡：移除 FF 專用高流量線材（對單機客戶版無意義）——清 list ＋ 刪檔
    if PING_ONLY:
        pj["filament_list"] = [x for x in pj["filament_list"] if "@FF" not in x["name"]]
        for f in glob.glob(os.path.join(PINGDIR, "filament", "*@FF*.json")):
            os.remove(f)
    json.dump(pj, io.open(pj_path,"w",encoding="utf-8"), ensure_ascii=False, indent=4)

    # 4e. ★ 預擠點升溫 post-pass（2026-07-19 Eric 裁定，見 apply_deferred_heating）——
    # 收在所有 emit 路徑之後、套全部 machine/*.json（machine_model／fdm 基底無 start gcode 自然跳過）
    n_heat = 0
    for f in sorted(glob.glob(os.path.join(PINGDIR, "machine", "*.json"))):
        d = json.load(io.open(f, encoding="utf-8"))
        if apply_deferred_heating(d):
            jdump(f, d); n_heat += 1
    print("預擠點升溫 post-pass：%d 機檔已套（header 去 M104/M109；預擠點 M109＋60s 每秒倒數）" % n_heat)

    print("\n產出: machine_model=%d machine=%d process=%d (+FF filament %d)，PING.json 已重建（版號請另行+1）"
          % (len(mm_list), gm, gp, len(fil_new)))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC)
