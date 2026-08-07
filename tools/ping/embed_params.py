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
    # 關門模式（Eric 2026-07-26）：門關著印（ABS 保艙溫）＝列印範圍剩直徑 200、高度不變；
    # 同一台實體機、吃 FD300 交付 config，只縮床＋預擠內移（BED_OVERRIDE）。
    # kind=dual1＝只出雙料本體（Eric 裁「關門版只需要 FD300」，不出 關門 同進/單料頭）。
    ("FD300",       "FD300 關門",  "dual1"),
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
# ★ 基礎支改名（Eric 2026-07-28 裁「把 PLA 改 PLA_210。它是給 FP300 使用的噴頭」・規格檔
#   _切片規則同步_來自pingslicer_TPE回抽速度與PLA210_20260728.md）：
#   「PING PLA」→「PING PLA - 210」（噴溫本就 210、值不動；名稱帶溫度尾碼與「- 220」一致）。
#   renamed_from ⚠ 字串（T004 鐵則）；filament_id/setting_id GPINGPLA 不動（同一支材料身份）；
#   alias 給獨立值防併組（3in1 教訓）。
# ★ 0728 v2 連動定案（Eric 回「連動」）：**單一出料機一律預設 210**＝FP300×3＋FD300 系
#   單料頭×6＋同進×6＋同進照片磚×2（機）＋其 model 檔；**雙料機維持 220**＝FD300/FD300 Pro
#   標準雙料×6＋關門×3（v1 誤把關門列單一出料、v2 更正＝關門是 FD300 雙料變體）。
#   P200+（客戶版）不在範圍＝維持 220 待裁。Classic 變體預設 Classic 220 是否改＝另案待裁。
BASE_PLA_OLD, BASE_PLA_NEW = "PING PLA", "PING PLA - 210"
# ★ 高流量噴頭專用線材（2026-07-12 Eric 裁定：高流量＝噴頭屬性非機型屬性，回抽值落材料層；
# 規格 _切片規則同步_來自pingslicer_高流量噴頭線材_20260712.md）。不分口徑、不限機型
#（無 compatible_printers）。覆蓋值＝Eric %APPDATA% 權威樣本 4 鍵（規格表另列的擦拭/空駛
# 欄樣本未覆蓋＝吃機器層，照「權威＝樣本」抄 4 鍵，偏差已回報參數端）。
HFN_PLA = "PING PLA - 高流量噴頭"
HFN_SUP = "PING SupPLA - 高流量噴頭"
HFN_PETG = "PING PETG - 高流量噴頭"   # 2026-07-18 Eric：PETG 也開高流量支
# 2026-07-12 Eric 二裁：擦拭/空駛 4 欄也入覆蓋（8 鍵＝完整定義；取代同日稍早「4 鍵免加」）
# 2026-07-12 統一四值④：PA 0.2 兩支都套；噴溫 210/210 只 PLA 版（SupPLA 版溫度待 Eric 裁）
# 2026-07-30 Eric 三裁：高流量家族回抽長度 2→3（「雙料高流量與四料高流量都一致 3/30/30」）
HFN_OVERRIDES = {"filament_retraction_length": ["3"], "filament_retraction_speed": ["30"],
                 "filament_deretraction_speed": ["30"], "filament_retract_restart_extra": ["0.6"],
                 "filament_retraction_minimum_travel": ["3"], "filament_wipe": ["1"],
                 "filament_wipe_distance": ["5"], "filament_retract_before_wipe": ["100%"],
                 "enable_pressure_advance": ["1"], "pressure_advance": ["0.2"]}
# 2026-07-12 Eric 補裁：SupPLA 版噴溫同 210（高流量噴頭組整組統一 210/210，不套 SUP=220 慣例）
HFN_EXTRA = {HFN_PLA: {"nozzle_temperature_initial_layer": ["210"], "nozzle_temperature": ["210"]},
             HFN_SUP: {"nozzle_temperature_initial_layer": ["210"], "nozzle_temperature": ["210"]},
             # PETG 高流量（2026-07-19 Eric 二裁）：噴溫 230（原 235）；床 75 承 PING PETG 基底、
             # PA 0.2 由 HFN_OVERRIDES 帶。基底由 PETG-235 改 PING PETG（兩支值全等；235 支同日刪除）
             HFN_PETG: {"nozzle_temperature_initial_layer": ["230"], "nozzle_temperature": ["230"]}}
# FD450/600/800 Pro 出廠＝高流量噴頭 → 預設線材改高流量支（FD300 系/FP300 不動）
def def_fil_dual_for(base):
    return [HFN_PLA, HFN_SUP] if tier_of(base) == "450" else DEF_FIL_DUAL
def def_fil_single_for(base):
    if tier_of(base) == "450":
        return [HFN_PLA]
    if base == "P200+":
        return DEF_FIL_SINGLE   # 客戶版不在 0728 連動範圍＝維持 220（待裁）
    return [BASE_PLA_NEW]   # 0728 v2 連動：FP300＋FD300 系單一出料（單料頭/同進）＝210
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
# ⓘ 2026-08-07 起本常數只是「種子值」——最終 default_materials 由 4d-2 的
#   apply_default_materials() post-pass 全族重算（Eric 0807 裁）。死名 PING ABS - 250／
#   PING PolyABS（0725 ABS 整併已移除）在此一併清掉，post-pass 也會再擋一次。
DEFAULT_MATERIALS_FD = ("PING PLA - 220;PING SupPLA;PING PLA - 210;"
                        "PING SupABS;PING PETG;PING ABS;PING PA-CF;"
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
    # FD300 關門（Eric 2026-07-26）：直徑 300→200、高度不變（不帶 height 鍵＝沿用 FD300）；
    # 預擠直線 Y-140/-138 → +50 內移＝P200+ 門關 200 實機驗過的同款幾何。
    # ⚠ 預擠弧白名單（apply_fd300_prime_arc）全名比對不含本機型＝不會誤套 R144 弧（超出 200 床）。
    "FD300 關門": {"area_diameter": 200.0, "prime_y_shift": 50},
}

# ---------- Classic 前代機（V3.6） ----------
# 名稱、尺寸與預設口徑以 PingSlicer V2.1 為權威；速度／回抽沿用同版品質檔。
# 這批皆為 Marlin 非 Klipper 機：不送 machine limits、不產生 M204、不用韌體回抽／PA。
# EDU 料管約 40cm，保留專屬 4/30；PING 270 約 70cm，使用 6/60。
CLASSIC_SPECS = [
    {"name":"EDU 200",  "src_model":"FP300",       "src_nozzle":"0.6", "src_diameter":300,
     "diameter":200, "height":"200", "nozzle":"0.6", "layer":"0.3",  "initial":"0.35",
     "retract":"4", "retract_speed":"30", "dual":False, "heated_bed":False, "speed_class":"single"},
    {"name":"PING 200", "src_model":"FP300",       "src_nozzle":"0.4", "src_diameter":300,
     "diameter":200, "height":"200", "nozzle":"0.4", "layer":"0.2",  "initial":"0.25",
     "retract":"2", "retract_speed":"20", "dual":False, "heated_bed":True,  "speed_class":"single"},
    {"name":"PING 270", "src_model":"FP300",       "src_nozzle":"0.4", "src_diameter":300,
     "diameter":270, "height":"300", "nozzle":"0.4", "layer":"0.2",  "initial":"0.25",
     "retract":"6", "retract_speed":"60", "dual":False, "heated_bed":True,  "speed_class":"single"},
    {"name":"PING 300+","src_model":"FP300",       "src_nozzle":"0.4", "src_diameter":300,
     "diameter":300, "height":"270", "nozzle":"0.4", "layer":"0.2",  "initial":"0.25",
     "retract":"2", "retract_speed":"20", "dual":False, "heated_bed":True,  "speed_class":"single"},
    {"name":"DUAL 300", "src_model":"FD300",       "src_nozzle":"0.4", "src_diameter":300,
     "diameter":300, "height":"270", "nozzle":"0.4", "layer":"0.2",  "initial":"0.25",
     "retract":"2", "retract_speed":"20", "dual":True,  "heated_bed":True,  "speed_class":"dual04"},
    {"name":"DUAL 450", "src_model":"FD450 Pro",   "src_nozzle":"0.6", "src_diameter":450,
     "diameter":450, "height":"600", "nozzle":"0.6", "layer":"0.25", "initial":"0.3",
     "retract":"3", "retract_speed":"30", "dual":True,  "heated_bed":True,  "speed_class":"dual06"},
    {"name":"DUAL 600", "src_model":"FD600 Pro",   "src_nozzle":"0.6", "src_diameter":600,
     "diameter":600, "height":"580", "nozzle":"0.6", "layer":"0.25", "initial":"0.3",
     "retract":"3", "retract_speed":"30", "dual":True,  "heated_bed":True,  "speed_class":"dual06"},
    {"name":"DUAL 800", "src_model":"FD800 Pro",   "src_nozzle":"0.6", "src_diameter":800,
     "diameter":800, "height":"580", "nozzle":"0.6", "layer":"0.25", "initial":"0.3",
     "retract":"3", "retract_speed":"30", "dual":True,  "heated_bed":True,  "speed_class":"dual06"},
]
CLASSIC_MODELS = [s["name"] for s in CLASSIC_SPECS]

def scale_circle_area(area_pts, target_diameter):
    """圓床 printable_area 是以床心(0,0)為原點的 72 點；FP300 半徑150 → 等比縮放至目標直徑"""
    s = (target_diameter / 2.0) / 150.0
    out = []
    for p in area_pts:
        x, y = p.split("x")
        out.append("%gx%g" % (round(float(x) * s, 4), round(float(y) * s, 4)))
    return out

def scale_circle_area_from(area_pts, source_diameter, target_diameter):
    """以來源機的實際直徑等比縮放圓床，供 Classic 從相近 Fast 機型複製。"""
    s = float(target_diameter) / float(source_diameter)
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
    if "height" in ov:                       # FD300 關門：高度不變＝不帶 height 鍵
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

# ★ 預擠點升溫——【2026-07-20 Eric 裁回退・停用】實測失敗：冷噴頭先移到預擠第一點才升溫，
# 升溫過程殘料滲出、在第一點原地積一坨（前面沒有清噴頭步驟）；需配套「清噴頭」等其他機制
# 驗證通過才重新納入。函式與 Classic 守衛留存備查（main 4e 呼叫已停用），首發＝主線 04725e02。
# —— 以下為原設計說明（2026-07-19 Eric 裁定：開印前不預熱噴頭——預熱會滴料還要清料；主線移植）：
# header 只留熱床（M140/M190，前加 M117 熱床加熱中提示），G28 歸位＋移動全程冷噴頭；
# 移到預擠第一點（第一個接近 travel G0 F8000）後才 M109 升溫等到溫（M117 噴頭加熱中），
# 到溫後恆溫等 60 秒才預擠——每秒一則 M117 倒數（Eric UX 準則 FBK-21：顯示即時、不留資訊空白）。
# 結尾 M117 清提示。中文 M117 已於主線 CLI 實切驗證（PlaceholderParser 純文字行不炸）。
# 引擎不自動補溫（custom_gcode_sets_temperature 只查 custom gcode 內有無 M104/M109）。
# post-pass 套 machine/*.json（見 main 4e）；冪等（marker＝M117 噴頭加熱中）。
# ⚠ Classic 前代 8 機（DUAL/EDU/PING 2xx/3xx，Marlin）不套——隔離原則，Eric 未裁前保守排除。
_HEAT_HEAD = re.compile(r"^M10[49] S\[nozzle_temperature_initial_layer\][^\n]*\n", re.M)
_CLASSIC_PREFIX = ("DUAL ", "EDU ", "PING 2", "PING 3")
def apply_deferred_heating(mac):
    sg = mac.get("machine_start_gcode")
    if not isinstance(sg, str) or "M117 噴頭加熱中" in sg:
        return False
    # 交付源 gcode 髒空白（FF 四色：行尾/行首空白＋空行）→ 先逐行 strip 統一（乾淨檔＝零變化）
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

# 檔名主體（模式前綴之後的部分）——**唯一真實來源**。
# ⚠ 抽成常數的理由：2026-07-26 已連續兩次踩到「規則改了但某個角落沒跟上」
#（照片磚範本、Classic emit）。凡要改檔名格式，只改這一行。
FILENAME_BASE = "{printer_model}({nozzle_diameter[0]})_{input_filename_base}_{print_time_half_h}_{total_weight_g}.gcode"

def filename_tpl(mode_key):
    """輸出檔名模板：**模式_列印設備(口徑)_檔名_時間_重量**（2026-07-23 Eric 改版，取代 0610 版）。
    模式共 **7 種**（Eric 2026-07-26 定稿）：易拆／雙色／單料／四色／3in1／同進／照片磚。
    雙料依「槽2是否支撐材」自動判：易拆(裝SUP)／雙色(裝一般料)；單料頭/FP=單料。
    ⚠ **沒有「經典」模式**——Classic 前代機用它實際的模式（雙料→易拆、單料→單料）；
      機型名本身已帶 DUAL/EDU/PING 2xx 等字樣，再標「經典」對客戶無意義（Eric 2026-07-26 裁）。
    時間 {print_time_half_h}（0.5H 無條件進位）、重量 {total_weight_g}（整數克進位）
    ——兩佔位符 2026-07-23 進 Print.cpp，需該版之後 binary（profile 與 binary 必須同車出貨）。
    ⚠ 前綴一律包進 code block 字串字面值 {"X_"}：PlaceholderParser 模板的 rule 邊界
    （開頭、} 之後）遇非 ASCII 即 throw（pre-skip skipper）、裸中文前綴會炸
    「Non-ASCII7 characters...」；字串字面值是 lexeme[utf8char]、中文合法。"""
    base = FILENAME_BASE
    # 2026-07-23 Eric 改版：模式_列印設備(口徑)_檔名_時間0.5H_重量g（佔位符需同日後 binary，profile 與 binary 同車）
    if mode_key in ("PLA+SUP", "ABS+SUP", "PLA+PVA"): return '{"易拆_"}' + base   # 組合別製程→前綴直判，免模板條件式
    if mode_key in ("PLA+PLA", "ABS+ABS"): return '{"雙色_"}' + base
    # Mix_ → 同進_（Eric 2026-07-26 裁）：7 個前綴裡只有這個是英文，與 易拆/雙色/單料/四色/經典
    # 不一致，同事看檔名會覺得不整齊。已查無消費者——切片端無人讀此前綴，機台端判混色是看
    # gcode 內容的 M6051/M6052 而非檔名 ⇒ 純顯示層改名，零功能影響。
    if mode_key == "同進":  return '{"同進_"}' + base
    if mode_key == "四色":  return '{"四色_"}' + base
    if mode_key == "3in1":  return '{"3in1_"}' + base   # FF 範本製程（emit_ff_extra 套用）
    # 照片磚自成一個模式（Eric 2026-07-26 裁）：它雖然跑在同進機上，但對使用者是獨立產品，
    # 檔名直接標「照片磚」比標「同進」有意義。
    if mode_key == "照片磚": return '{"照片磚_"}' + base
    return '{"單料_"}' + base   # 單料頭 / FP300

def proc_overrides(kind, base, is_single_mode):
    """軟體端裁定值 override（FF 不套）。
    2026-06-11 大清理（吃當日交付驗證）：加速度(3000/1500)、scarf=none、速度兩線新裁定
    （雙料/FP 60-80-150、單料頭/同進 50-60-150、口徑連動填充）——源檔已全套→override 拿掉
    （「源檔套完→拿掉 embed override」原則）。
    接縫與兩個加速度由 normalize_unified_values 集中套用，此處不再覆寫。"""
    return {}

# ★ 正式製程統一值（Eric 2026-07-15 最新裁定；取代 2026-07-12 的 aligned_back／travel 20000，
# 規格 _切片規則同步_來自orca_主線保守加速度與接縫_20260715.md）：
# ①首層流量比 1.1（set_other_flow_ratios 開；其餘流量比維持預設 1）
# ②接縫位置＝對齊 aligned（⚠ enum 對映：UI「對齊」=aligned；「背部對齊」=aligned_back；
#   照片磚特調用的是 back＋seam_gap0——本函式不套照片磚，見 emit_phototile 註）
# ③空駛加速度 5000（20000 會造成馬達錯位／失步；空駛速度 250 不變）
# 全 PING 製程套（含棧板雙生＝從已正規化的 proc 派生自然繼承）；DL1016 不在 repo 自然跳過；
# 照片磚特調跳過（seam/換料路徑特調，已回報參數端）。
def normalize_unified_values(proc, ff=False):
    proc["set_other_flow_ratios"] = "1"
    proc["first_layer_flow_ratio"] = "1.1"
    proc["seam_position"] = "aligned"
    proc["travel_acceleration"] = "5000"
    # ④ jerk 對齊機器上限 7（Eric 2026-07-20 裁「jerk 改 7」）：機器檔動力學改 Klipper 實值後
    # FD/FP 上限 7、製程 40 → 每切必跳「抖動設定已超過…自動限制」警告；改 7 輸出不變
    #（本就被夾到 7，Klipper 又忽略 M205）＝純清警告。FF 上限 56＞40 不跳警告、維持 40
    #（改 7 反而真降 FF 轉角速）→ ff=True 跳過。Classic 前代不走本函式（Marlin 隔離，
    # jerk "0"=停用不得動）；照片磚不走本函式、FD300 照片磚由範本自帶 7。
    if not ff:
        for k in ("default_jerk", "infill_jerk", "initial_layer_jerk", "inner_wall_jerk",
                  "outer_wall_jerk", "top_surface_jerk", "travel_jerk"):
            if k in proc:
                proc[k] = "7"
    # ⑤ 爬坡品質（Eric 2026-07-24 裁「一併加入所有的參數」；工程端 FD300 同進 0.4
    # 「爬坡測試」A/B 對照實證懸空品質高提升）：懸空處降速開＋四段 50/50/25/10
    # （10%/25%/50%/75%；25% 段沿用原值 50＝對照兩側同值）＋橋接流量 0.95。
    # 線材側配套「懸空冷卻觸發閾值 25%」＝4b-2c sweep。
    # ⚠ 單位＝mm/s（coFloatOrPercent 裸數字；ratio_over=outer_wall_speed，要用 % 須帶符號）。
    # 值源自 Orca 端 A/B 對照實印檔，非 V2.1 換算——Cura 無四段結構（僅單一
    # wall_overhang_speed_factor 百分比），故不涉跨基準換算。
    # 照片磚/Classic/DL1016 不走本函式＝天然豁免（同 jerk 註）。
    proc["enable_overhang_speed"] = "1"
    proc["overhang_1_4_speed"] = "50"
    proc["overhang_2_4_speed"] = "50"
    proc["overhang_3_4_speed"] = "25"
    proc["overhang_4_4_speed"] = "10"
    proc["bridge_flow"] = "0.95"
    # ⑥ 支撐臨界角 35（Eric 2026-07-25 裁，推翻 07-24 的 60）。照片磚/Classic/DL1016 豁免同上。
    # 🔴 這是 Orca 基準值（自水平量、越大支撐越多），= Cura/V2.1 的 55。
    #    兩線基準相反：Orca = 90 − Cura。改這個值前必讀 ping-slicer/orca-sync.md「Cura → Orca key 對照」。
    # ⚠ 07-24 的 60 係把 V2.1 語意的「支撐角 60」直接寫進 Orca key（實等於 Cura 30）＝支撐暴增
    #    （層高 0.3：判懸空的逐層外擴門檻 0.52mm→0.17mm，敏感度約 3 倍），現場回報「60 支撐太多」。
    #    ⚠ 出貨線從未被 60 汙染（本規則係首次新增，原全庫 30＝V3.0 底稿值）。
    proc["support_threshold_angle"] = "35"
    return proc

# ★ 支撐介面值（Eric 2026-08-04 裁，V2.1「密度表示」→Orca「間距表示」換算；蓋 0714「間距一律 0.1」）：
# 頂部接觸面層數 4（0714 不變）；頂部接觸面間距分家族——
# ①一般支撐（同料，密度決定好不好拆）＝70% 密度等效口徑連動：Orca 間距＝線與線淨間隙、
#   密度＝線寬/(間距+線寬)（SupportParameters.hpp:104，同 0722 主體線距 ×9 的推導）
#   ⇒ 70% 需間距＝口徑×3/7 取兩位（0.25→0.11、0.4→0.17、0.6→0.26＝Eric 截圖錨值、1.0→0.43）。
#   分子用口徑名目值（FF 微調線寬不入分子，同 0722 家規）。替換集合含單料/同進 V3.0 源值 0.04
#   與 0714 產物 0.1（Eric 示範正是把同進 0.6 的 0.04 改 0.26）。
# ②易拆家族（SUP/PVA 專用支撐料，介面密＝表面品質、不影響拆）＝維持既值不動：
#   PLA+SUP/PVA 0.1（0714 規則照舊）、ABS+SUP 黃金 0.04、3in1 實心 0（承 0714/0722「不蓋」先例）。
# 支撐首層密度 raft_first_layer_density（支撐貼板首層；與 raft 共用鍵）＝10% 全庫（Eric 0804 裁；
#   主體類規則全庫套＝同 0722 ×9 先例，含易拆/3in1 範本 30%）；raft 機種（ABS 系/棧板 raft_layers≥1）
#   ＝raft 首層＝貼床要抓床，維持 100% 不動——呼叫點須在 combo_overrides 之後（raft_layers 已定）。
# Classic 前代由 Fast 複製自然繼承（支撐屬切片行為、韌體無關）；DL1016 不在 repo 自然跳過。
def normalize_support_interface(proc, nozzle=None, easy_release=False):
    if proc.get("support_interface_top_layers") in ("1", "2"):
        proc["support_interface_top_layers"] = "4"
    if easy_release or nozzle is None:
        if proc.get("support_interface_spacing") in ("0.2", "0.4", "0.5", "1"):
            proc["support_interface_spacing"] = "0.1"
    else:
        if proc.get("support_interface_spacing") in ("0.04", "0.1", "0.2", "0.4", "0.5", "1"):
            proc["support_interface_spacing"] = "%g" % round(float(nozzle) * 3 / 7, 2)
    if str(proc.get("raft_layers", "0")) == "0":
        proc["raft_first_layer_density"] = "10%"
    return proc

# ★ 支撐幾何口徑連動（Eric 2026-07-17 裁；線距 2026-07-22 裁 ×9 新規蓋舊規）：
# 樹狀支撐分支直徑＝口徑×10；主體圖案線距＝口徑×9（支撐密度 10%＝Cura 線全庫密度等效。
# Orca 線距=線間淨間隙、密度=線寬/(線距+線寬) → ×9；7/17 舊規 ×8=12.5% 作廢）。
# 分子用口徑名目值（FF 微調線寬不入分子，0.4→3.6/0.6→5.4/1.0→9）；全口徑含 0.2/0.25 照公式；
# 照片磚維持獨立特調不套；Classic 由 Fast 複製自然繼承。
def normalize_support_geometry(proc, nozzle):
    # 分支直徑 2026-07-25 Eric 裁 ×10→×12（保守配方；引擎上限 10 ⇒ 1.0 口徑取 10）。
    proc["tree_support_branch_diameter"] = "%g" % min(float(nozzle) * 12, 10.0)
    # 分支距離 2026-07-25 新增＝口徑×6（原固定 5）：與直徑同為口徑連動 ⇒ 直徑/距離恆為 2.0，
    # 各口徑得到相同支撐幾何（固定 5 會讓 0.25 口徑比例失衡到 0.5＝分支不融合）。引擎範圍 1~10。
    proc["tree_support_branch_distance"] = "%g" % (float(nozzle) * 6)
    proc["support_base_pattern_spacing"] = "%g" % (float(nozzle) * 9)
    return proc


# ★ 樹狀支撐保守配方（Eric 2026-07-25 裁・主線 fa3ecb90 移植）
# 前提：預設支撐維持 normal(auto)+snug 不變；本組只在**使用者手動把樣式切成「混合樹」**後生效。
# 選型依據＝Orca 官方 tooltip：slim/organic 會積極合併分支大量省料，而 **hybrid 在大面積平懸空下
#   產生「類似普通支撐的結構」** ⇒ 最貼近 PING 已實機驗證的 normal+snug 行為；且易拆系（+SUP/3in1）
#   Z 間距 0＋專用支撐料（介面料槽 2）＝靠材料不相熔剝離，密實介面鋪得完整，正對症。
#   單料頭/同進系 Z 間距 0.2＋無專用料（同料）＝靠空氣間隙剝離，樹狀為點接觸 ⇒ 能用但非首選。
# ⚠ 欄位分組是引擎硬分的（ConfigManipulation.cpp:750-758）：branch_angle/distance/diameter 與
#   auto_brim/brim_width 屬「normal tree」（hybrid 吃）；帶 _organic 後綴者與 tip_diameter/
#   top_rate/angle_slow/branch_diameter_angle 屬 organic 專屬（切 hybrid 後不生效）。
def normalize_tree_support(proc):
    # 甲組：混合樹會吃的（保守＝穩定優先，代價為費料、難拆）
    proc["tree_support_branch_angle"] = "30"      # 原 40（原廠值）；角度小＝分支更垂直＝更不易垮。範圍 0~60
    proc["tree_support_auto_brim"] = "0"          # 必須關，brim_width 才生效
    #   （TreeSupport.cpp:2068 `!auto_brim ? tree_brim_width : 自動計算` ＝開著時手設值被完全忽略，
    #    且 ConfigManipulation.cpp:760 會把該欄位灰掉不可編輯）
    proc["tree_support_brim_width"] = "10"        # 原 3；樹狀為高瘦結構，底盤加寬＝不倒
    # ★ Eric 2026-07-27 裁「支撐牆數改零」（UI 支撐牆數＝本鍵，普通/樹狀共用・Tab.cpp:2663）：
    #   普通支撐 0＝無牆（SupportParameters.hpp:113 with_sheath=false＝本裁目的）；
    #   樹狀 0＝auto（TreeSupport.cpp:1552 需要處才加；organic 與 2424 路徑 max(1,·) 保底 1）
    #   ⇒ 0725「樹狀牆圈維持一圈」同鍵被本裁上蓋為 auto（無法分治，Eric 回報時已明示）。
    proc["tree_support_wall_count"] = "0"
    # tree_support_with_infill 不寫＝維持繼承 false（Eric 裁「填充維持空心」）
    # 乙組：organic 防呆（使用者忘記切樣式時會吃到——snug+樹狀會被引擎退回 default＝有機樹）
    # 🔴 diameter_organic 2→2.6 是 bug 修：Print.cpp:1532 硬性要求 ≥2×支撐線寬，
    #    FF600/FF800 的 1.0 口徑線寬 1.02 ⇒ 需 ≥2.04，原值 2 會讓那 4 支勾樹狀即切片報錯。
    proc["tree_support_branch_diameter_organic"] = "2.6"
    proc["tree_support_branch_angle_organic"] = "40"   # 原 60＝引擎上限（最水平＝最易垮），回原廠 40
    return proc

# ★ 普通支撐配方（Eric 2026-07-22 七裁＋同日二裁擴及易拆・主線 c7d22ac8/e0eace04 移植）：
# 行為四項（類型/獨立層高/樣式/圖案）全支撐同套；幾何 XY 分流：一般=口徑×1、
# 易拆維持 7/14 裁（PLA+SUP/3in1=口徑×0.75、ABS+SUP 黃金 0.5）。
# 照片磚/DL1016 特調豁免（不經此函式）；Classic 製程由 Fast 複製自然繼承（支撐屬切片行為、韌體無關）。
def normalize_support_recipe(proc, nozzle, easy_release=False):
    proc["support_type"] = "normal(auto)"
    proc["independent_support_layer_height"] = "0"
    proc["support_style"] = "snug"
    proc["support_base_pattern"] = "rectilinear"
    if not easy_release:
        proc["support_object_xy_distance"] = "%g" % round(float(nozzle) * 1.0, 2)
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

# ★ 換料塔預設（2026-07-08 Eric 拍板・規格 _切片規則同步_來自pingslicer_換料塔與棧板雙版本_20260708.md）：
# 全庫統一 寬 30→15＋外牆肋條（rib）。肋寬/圓角吃引擎預設（肋寬 8；寬 15 時被引擎夾到 7.5
# ＝正常行為，PrintConfig.cpp wipe_tower_rib_width tooltip）。單料機不顯示換料塔、寫入無副作用
# → 不分機型全寫（含 FF 範本/照片磚範本）。
def normalize_prime_tower(proc):
    # 寬度 2026-07-17 Eric 改裁 15→25（新規蓋舊規）
    proc["prime_tower_width"] = "25"
    # 牆體 2026-07-29 Eric 改裁 rib→cone＋頂角 30＋最快列印速度 60（新規蓋舊規、肋條裁定退役；
    # 速度＝引擎預設 90 下修 60、錐體自帶底部圓角助穩，cone_angle 引擎預設同為 30＝明寫鎖定）
    proc["wipe_tower_wall_type"] = "cone"
    proc["wipe_tower_cone_angle"] = "30"
    proc["wipe_tower_max_purge_speed"] = "60"
    return proc

# ★ 內外牆加速度（2026-07-29 Eric 裁「提高表面品質與穩定性」）：全機型統一 1500。
# 與 normalize_prime_tower 同三呼叫點＝覆蓋全部 emit 製程（0.125mm 細層批原 3000 一併統一）；
# Classic 前代隨 emit_classic Marlin 隔離歸 0 照舊（既有裁定不變）＝實效 F 系全家＋照片磚。
def normalize_wall_accel(proc):
    proc["outer_wall_acceleration"] = "1500"
    proc["inner_wall_acceleration"] = "1500"
    # ★ 牆體列印方向固定逆時針（Eric 2026-07-30 裁「外牆的順序一律改成逆時針(固定的)，
    # 至少這樣可以提升品質」）。機制＝PerimeterGenerator.cpp:1424 —— auto 時偵測到陡懸空會
    # 呼叫 reorient_perimeters() 反轉整層迴路，設 ccw 直接跳過該段 ⇒ 層間方向恆一致。
    # ⚠ 實測記錄（0730 側孔盒 gcode 矩陣）：本測試件上 auto 與 ccw 輸出逐項相同（PING 的牆
    # 在 auto 下本就全 CCW；殘留的 7 條 CW 是孔洞迴路＝幾何約定、wall_direction 管不到）。
    # 價值在懸空多的模型（會觸發 reorient 的情形），非本次孔帶紋路的解。
    proc["wall_direction"] = "ccw"
    return proc

# ★ 棧板雙版本製程（2026-07-08 Eric 拍板，同上規格檔）：FD 單料頭/同進＋FP300 出「_棧板」雙生
#（raft 六鍵＝既有 ABS+SUP 黃金配方定稿值，與 0.2mm ABS+SUP @FD300 (0.4).json 全等）。
# 裁決：①FF 全系/DL1016/雙料組合不出 ②切回一般版不自動換回 PLA（Tab.cpp 單向連動）
# ③雙料 ABS+SUP/ABS+ABS 維持現名（功能上已是棧板版）。
# setting_id 一律排在全庫既有 id 之後（主迴圈收集、最後統一 emit），既有 id 零位移。
PALLET_OVERRIDES = {"raft_layers": "2", "raft_contact_distance": "0.1", "raft_expansion": "1.5",
                    "raft_first_layer_density": "100%", "raft_first_layer_expansion": "3",
                    "initial_layer_line_width": "150%"}

# ★ 高流量製程組（Eric 2026-07-30 裁・客戶（建誌）FF800 同進 0.6 實測參數移植；
#   來源 P800參數-建誌.zip「FF_0.6_PLA_T200(800)」、巡檢＝FF800高流量參數_巡檢報告_20260730.html）：
#   六類速度全跟客戶（外100/內125/填充150/頂面150/實心150/支撐與介面100）＋首層也開 100
#  （Eric 追裁、推翻「保留 40」建議）；加速度逐項取保守 min(客戶, PING 現值)——客戶檔僅明寫
#   print 2000/travel 2000/wall0 1500、其餘 Cura 繼承 print=2000 ⇒ 實際變更僅 travel 5000→2000
#   ＋sparse_infill 5000→2000（default 1500/首層 500/頂面 800/內外牆 1500 現值更保守、全維持）；
#   頂底厚 0.8→1.2（客戶值；高速印薄頂易露填充。layers 4 承基底＝下限語意，1.0 口徑實得 4 層）；
#   層高照口徑連動 0.5×口徑（0.6＝客戶實測 0.3/0.35；0.4/1.0 推 0.2/0.25、0.5/0.55，首層＝層高+0.05）。
#   其餘全維持 PING 現值（支撐角 35／gyroid／aligned／溫度／回抽——客戶的 Cura 慣例不吃，
#   巡檢報告逐項裁定；支撐角客戶 Cura 60＝Orca 30，0724 已踩過的換算坑、維持 35 實測收斂值）。
#   範圍＝FF800 同進三口徑（0.4/0.6/1.0）；FF600/四色/3in1 等實印驗過再擴（verify 有範圍鎖）。
#   派生＝emit_ff_extra 正規化完成後複製雙生、id 統一接尾（4a-6，同棧板/PVA 模式＝既有 id 零位移）。
#   ⚠ 1.0 口徑 150×0.5×1.02≈76mm³/s 超四料線材上限 30 ⇒ 引擎自動夾速（≈60mm/s）＝預期行為
#  （現行 0.45mm 檔 100 速同樣超上限被夾，非本批新增風險）。
HF_PROC_LAYER = {"0.4": ("0.2", "0.25"), "0.6": ("0.3", "0.35"), "1.0": ("0.5", "0.55")}
HF_PROC_OVERRIDES = {
    "outer_wall_speed": "100", "inner_wall_speed": "125",
    "sparse_infill_speed": "150", "top_surface_speed": "150",
    "internal_solid_infill_speed": "150",
    "support_speed": "100", "support_interface_speed": "100",
    "initial_layer_speed": "100", "initial_layer_infill_speed": "100",
    "travel_acceleration": "2000", "sparse_infill_acceleration": "2000",
    "top_shell_thickness": "1.2", "bottom_shell_thickness": "1.2",
}
_HF_FF800_RE = re.compile(r"@FF800 同進 \(([\d.]+)\)\s*$")

def make_hf_twin(proc):
    """從正規化完成的 FF800 同進製程派生高流量雙生（setting_id 由 4a-6 接尾統一給）。"""
    nz = _HF_FF800_RE.search(proc["name"]).group(1)
    lh, flh = HF_PROC_LAYER[nz]
    tw = dict(proc)
    tw.update(HF_PROC_OVERRIDES)
    tw["layer_height"] = lh
    tw["initial_layer_print_height"] = flh
    tw["name"] = "%smm 高流量 @FF800 同進 (%s)" % (lh, nz)
    return tw

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
        # （235 支已於 2026-07-19 Eric 裁刪：留 PING PETG＋PING PETG - 高流量噴頭(230)）
        if "PETG" in rest: continue
        if   rest in ("PLA+SUP","PLA+PLA","ABS+SUP","ABS+ABS"): mode = rest  # 雙料 4 組合各自成製程
        elif rest.startswith("單料頭"):   mode = "單料頭"
        elif rest.startswith("同進"):     mode = "同進"
        elif rest.startswith("四色"):     mode = "四色"
        else: continue
        out[(nozzle, mode)] = json.load(io.open(os.path.join(d, fn), encoding="utf-8"))
    return out

DUAL_COMBOS = ["PLA+SUP", "PLA+PLA", "ABS+SUP", "ABS+ABS"]

# ★ 組合製程功能歸類名（Eric 2026-07-29 裁「材料對→功能名」＋兩追裁：PVA 留第五支、字面照原話；
# Codex gpt-5.6-sol 四輪雙審「可定稿」＝計畫 v2+v3+v4 疊加，軌跡 _審查_組合製程功能歸類改名_*）。
# 顯示名唯一產名入口：pname()／PVA twin／Classic 母檔讀取／machine default 全走本表；
# 內部 cb token（"PLA+SUP" 等）不動＝easy_release／raft／檔名前綴／combo_overrides 照舊。
COMBO_DISPLAY = {"PLA+SUP": "易拆(Z0)", "PLA+PVA": "易拆(Z0)水溶", "ABS+SUP": "易拆(Z0)+棧板",
                 "PLA+PLA": "雙料(Z隙)", "ABS+ABS": "雙料(Z隙)+棧板"}

def combo_display(cb):
    return COMBO_DISPLAY.get(cb, cb)

def combo_renamed_from(lh, cb, model, nz):
    # 舊全名（renamed_from＝分號分隔「字串」鐵則；本表僅一條）。
    # ⚠ 刻意不收「舊去@別名」（計畫 v2 §3.2 原擬收）：同層高的去@形態跨 6 台機共用
    #（例「0.2mm PLA+SUP」＝六支同名）＝不唯一，塞入會撞 renamed_from 舊名唯一性護欄、
    # 引擎 rename map 也是 1:1 先到先贏＝語意錯誤。偏離已記回審補遺（v4 補遺段）。
    return "%smm %s @%s (%s)" % (lh, cb, model, nz)

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


# ★ PLA+PVA 專屬製程（Eric 2026-07-25 裁「出」・主線 0a5d1df3 移植；
#   值＝V2.1 定稿案 DPro_0.6_T210_PVA+PLA 對帳，劉勝賢 2026-07-24 提供 3mf）
# 產法＝從同口徑 PLA+SUP 製程雙生派生（同棧板雙生模式）：易拆幾何（Z0／XY 口徑×0.75）、
#   支撐料槽 2、速度/層高家規全部自然繼承，只覆蓋「案值與家規不同」的四項。
# ⚠ 兩項為跨基準換算值（同支撐角教訓，見 orca-sync.md），標待工程端實機驗證：
#   ①支撐角：案值 Cura 40 ＝ Orca 50（Orca ＝ 90 − Cura）＝比全庫 35 多支撐，屬水溶支撐合理特例
#   ②brim：案值「20 條」係 Cura 條數制，Orca 為 mm ⇒ 20 條 × 線寬 ≒ 口徑×20
# 未套（家規優先，刻意）：層高（案 0.35@0.6 vs 家規口徑×0.5＝0.3）、內牆/填充速度
#   （案「全 60」vs 家規外60/內≤80/填100 的吞吐設計；外牆與首層本就同值）。
def pva_overrides(nozzle):
    nz = float(nozzle)
    return {
        "support_threshold_angle": "50",                              # 案值 Cura 40 換算
        "support_base_pattern_spacing": "%g" % round(nz * 19, 2),     # 支撐密度 5%（案值；家規 10%＝×9）
        #   Orca 以線距表述密度：密度＝線寬/(線距+線寬) ⇒ 5% 需線距＝線寬×19（分子用口徑名目值，同 0722 家規）
        "prime_tower_width": "45",                                    # 案值（劉勝賢現行；家規 25）
        "brim_width": "%g" % round(nz * 20, 2),                       # 案值 20 條換算
    }

def normalize_support_mode(proc, model_name):
    """機型預設支撐模式（Eric 2026-07-15）：
    - FD300 全家族／所有模式＝樹狀
    - FF600 基本款與 3in1＝普通
    - FF600 同進＝樹狀
    放在組合別覆寫之後，避免 ABS+SUP 黃金配方把 FD300 改回普通。"""
    if model_name.startswith("FD300"):
        proc["support_type"] = "tree(auto)"
    elif model_name.startswith("FF600 同進"):
        proc["support_type"] = "tree(auto)"
    elif model_name.startswith("FF600"):
        proc["support_type"] = "normal(auto)"
    return proc

def emit_ff_extra(mm_list, mac_list, proc_list, gm, gp):
    """範本複製法：把已驗證的 FF 同進/3in1 machine/process/filament/cover 併入產出。
    - machine（type=machine 的口徑變體）：重指 setting_id（續 gm 計數避免撞號）→ mac_list
    - machine_model（底檔）：→ mm_list
    - process：重指 setting_id（續 gp）→ proc_list
    - filament（3in1 專用 PLA(3in1)/SupPLA(3in1)，含 T4/T3 filament_start_gcode、淺灰支撐色）→ 回傳 ff_fil
    - cover：複製到 PINGDIR（受 4c 孤兒清除保護，見 ff_models）
    回傳 (gm, gp, ff_fil, ff_models, hf_twins)。範本本身已驗證，不再改值、只重編 setting_id。"""
    ff_fil, ff_models = [], []
    hf_twins = []   # ★ 高流量雙生（2026-07-30）：FF800 同進三口徑、正規化後派生、id 由 4a-6 接尾
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
        normalize_prime_tower(d)  # 換料塔統一（0708 立；0717 寬 25；0729 錐體30/速60）
        normalize_wall_accel(d)   # 內外牆加速度 1500（2026-07-29 Eric 裁）
        normalize_unified_values(d, ff=True)  # 正式製程統一值；FF 範本 jerk 維持 40（上限 56 不警告）
        compatible = d.get("compatible_printers", []) or []
        if compatible:
            normalize_support_mode(d, compatible[0])
        m_nz = re.search(r"\(([\d.]+)\)\s*$", d["name"])   # 名尾口徑，如 "0.35mm @FF600 3in1 (0.6)"
        if m_nz:
            normalize_support_geometry(d, m_nz.group(1))  # 樹狀直徑×10＋主體線距×9（2026-07-17/0722，FF 範本同套）
            normalize_support_recipe(d, m_nz.group(1), easy_release=("3in1" in d["name"]))  # FF 同進套普通支撐配方；3in1 易拆跳過 XY
            normalize_tree_support(d)  # 樹狀保守配方＋organic 防呆（2026-07-25）
            # 介面間距 70% 等效＋首層密度 10%（0804 起 FF 範本同套：同進 0.04/四色 0.1→口徑×3/7、
            # 首層 100%/30%→10%；3in1 easy_release＝介面實心 0 維持）。0714「範本不套」自此作廢。
            normalize_support_interface(d, m_nz.group(1), easy_release=("3in1" in d["name"]))
        d["filename_format"] = filename_tpl("3in1" if "3in1" in d["name"] else "同進")  # 檔名新格式（2026-07-23）FF 範本同套
        # ★ 高流量雙生派生點（2026-07-30 Eric 裁）：FF800 同進限定（排除 3in1／FF600），
        #   在全部正規化完成之後複製＝速度/加速度家規先套滿、再被高流量定案值覆蓋
        if "3in1" not in d["name"] and _HF_FF800_RE.search(d["name"]):
            hf_twins.append(make_hf_twin(d))
        d["setting_id"] = "PINGP%03d" % gp; gp += 1
        jdump(os.path.join(PINGDIR, "process", "%s.json" % d["name"]), d)
        proc_list.append({"name": d["name"], "sub_path": "process/%s.json" % d["name"]}); n_proc += 1
    for fn in sorted(os.listdir(os.path.join(FF_EXTRA, "filament"))):
        d = json.load(io.open(os.path.join(FF_EXTRA, "filament", fn), encoding="utf-8"))
        jdump(os.path.join(PINGDIR, "filament", "%s.json" % d["name"]), d)
        ff_fil.append({"name": d["name"], "sub_path": "filament/%s.json" % d["name"]})
    for fn in os.listdir(os.path.join(FF_EXTRA, "cover")):
        shutil.copy2(os.path.join(FF_EXTRA, "cover", fn), os.path.join(PINGDIR, fn)); n_cov += 1
    print("  ff_extra 併入：machine=%d + machine_model=%d，process=%d，filament=%d，cover=%d（高流量雙生收集 %d）"
          % (n_mac, len(ff_models), n_proc, len(ff_fil), n_cov, len(hf_twins)))
    return gm, gp, ff_fil, ff_models, hf_twins

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
        normalize_wall_accel(d)   # 內外牆加速度 1500（照片磚同套；2026-07-29）
        # ★ 支撐參數全部統一（Eric 2026-07-25 裁「照片磚其實不會用到支撐，把支撐參數全部統一，
        #   就不會有差異了」）——取消照片磚既有的支撐豁免（0714 介面／0717 幾何／0722 七裁／0725 角度）。
        #   實測 enable_support=1（開啟）但磚體平貼床無懸空面 ⇒ 引擎不生成支撐、統一為純消除差異。
        #   影響：type tree(auto)→normal(auto)、style default→snug（原組合＝有機樹）、角度 30→35、
        #   線距 2.5→口徑×9、XY 0.3→口徑×1、獨立支撐層高 1→0。
        #   照片磚不含 "+SUP" ⇒ 依家規判定為「一般支撐」（easy_release=False）。
        m_nz_pt = re.search(r"\(([\d.]+)\)\s*$", name)
        if m_nz_pt:
            normalize_support_geometry(d, m_nz_pt.group(1))
            normalize_support_recipe(d, m_nz_pt.group(1))
        normalize_tree_support(d)
        # 介面間距 70% 等效＋首層密度 10%（0804；照片磚承 0725「支撐參數全部統一」＝0.04/100% 一併換，
        # enable_support=0＋磚體平貼床＝零功能影響、純消除差異）
        normalize_support_interface(d, m_nz_pt.group(1) if m_nz_pt else None)
        d["support_threshold_angle"] = "35"  # 與全庫同值（原 30 豁免取消）
        # ★ 支撐開關關掉（Eric 2026-07-25 追裁）：0725 首輪回報「enable_support 其實是 1」＝
        #   雖然磚體平貼床不會生成支撐、實務無影響，但「開著卻永遠不生成」本身會誤導使用者，
        #   且一旦有人把磚立起來或加高就會意外長支撐。照片磚不需要支撐 ⇒ 開關直接關。
        d["enable_support"] = "0"
        # 檔名：照片磚自成一模式（Eric 2026-07-26 裁）⇒ `照片磚_機型(口徑)_檔名_時間_重量`。
        # ⚠ 照片磚製程從範本檔複製、**不走 filename_tpl()**，範本裡連主體都還是 0610 舊佔位符
        #   （{filament_type}_{total_weight_str}_{print_time_hm}）⇒ 這裡整條覆蓋才會真的跟上。
        # ⚠ 同一類坑 0726 一天踩三次（DL1016 注入源／本處範本源／Classic emit）：
        #   **產生器規則函式掃不到的來源要各自處理**，改全庫規則後務必回頭數數量對不對。
        d["filename_format"] = filename_tpl("照片磚")
        # ⚠ 支撐以外的正式製程統一值仍「不套」照片磚：維持 back＋seam_gap0、travel 3000。
        d["setting_id"] = "PINGP%03d" % gp; gp += 1
        jdump(os.path.join(PINGDIR, "process", "%s.json" % name), d)
        proc_list.append({"name": name, "sub_path": "process/%s.json" % name})
    for fn in os.listdir(os.path.join(PHOTOTILE, "cover")):
        shutil.copy2(os.path.join(PHOTOTILE, "cover", fn), os.path.join(PINGDIR, fn))
    print("  phototile 併入：machine=%d + machine_model=%d，process=%d，cover=2"
          % (len(PHOTOTILE_MACHINES), len(pt_models), len(PHOTOTILE_PROCS)))
    return gm, gp, pt_models

CLASSIC_PLA_210 = "PING PLA - Classic 210"
CLASSIC_PLA_220 = "PING PLA - Classic 220"
CLASSIC_SUP_PLA = "PING SupPLA - Classic"
CLASSIC_EDU_PLA = "PING PLA - EDU Classic"

def _fill_array(d, key, value):
    """保留 Orca 來源 preset 的槽位數，只替換每槽值。"""
    old = d.get(key)
    d[key] = [str(value)] * (len(old) if isinstance(old, list) and old else 1)

def _classic_filament(base_name, name, setting_id, temperature, bed_temperature, is_support=False):
    d = json.load(io.open(os.path.join(PINGDIR, "filament", "%s.json" % base_name), encoding="utf-8"))
    # 母檔的舊名相容標記不得帶進衍生支（0728 基礎支改名首驗抓到：Classic 210/EDU 跟著母檔
    # 帶 renamed_from "PING PLA" ＝兩支搶同一舊名、引擎解析任挑一支＝地雷；verify 有唯一性護欄）
    d.pop("renamed_from", None)
    d.update({"type":"filament", "name":name, "alias":name, "from":"system", "instantiation":"true",
              "setting_id":setting_id, "filament_id":setting_id})
    # 回抽只由 Classic machine preset 控制。不可讓材料層覆蓋，也不可送 Klipper 指令。
    for key in list(d):
        if key.startswith("filament_retract") or key in ("filament_wipe", "filament_wipe_distance",
                                                          "filament_z_hop", "filament_z_hop_types"):
            d.pop(key, None)
    # ★ Classic 前代**改為跟進** F 系新工藝（Eric 2026-07-25 裁「Classic 套新工藝」，
    #   推翻 0719「Classic 不套預擠點升溫」延伸來的保守豁免）：
    #   懸空冷卻觸發閾值 25%（0724 爬坡品質批・線材側配套）自母檔複製時直接帶進來，不再 pop。
    #   ⚠ 舊 pop 之所以必要，是因為 _classic_filament 讀的是**磁碟上的母檔**（非冪等來源）；
    #     現在既然要套，就讓它自然繼承母檔值即可——但也因此 Classic 的該鍵**跟著母檔走**，
    #     日後若想再豁免，必須在這裡 pop 而不是在 sweep 端排除（此坑保留記錄）。
    d["filament_start_gcode"] = ["; Classic Marlin filament - machine retraction only\n"]
    d["enable_pressure_advance"] = ["0"]
    d["pressure_advance"] = ["0"]
    for key in ("adaptive_pressure_advance", "adaptive_pressure_advance_bridges",
                "adaptive_pressure_advance_overhangs"):
        if key in d:
            d[key] = ["0"]
    d["nozzle_temperature"] = [str(temperature)]
    d["nozzle_temperature_initial_layer"] = [str(temperature)]
    for key in ("hot_plate_temp", "hot_plate_temp_initial_layer", "cool_plate_temp",
                "cool_plate_temp_initial_layer", "textured_plate_temp", "textured_plate_temp_initial_layer",
                "eng_plate_temp", "eng_plate_temp_initial_layer"):
        if key in d or bed_temperature == 0:
            d[key] = [str(bed_temperature)]
    if is_support:
        d["filament_is_support"] = ["1"]
    return d

def emit_classic(mm_list, mac_list, proc_list, nozzles_of, gm, gp):
    """V3.6 Classic：由已產生且可載入的 Fast preset 複製結構，再套 V2.1 舊機參數。"""
    classic_filaments = [
        # 母檔名跟進基礎支改名（0728）：BASE_PLA_NEW＝磁碟實檔名（_classic_filament 讀檔）
        _classic_filament(BASE_PLA_NEW,     CLASSIC_PLA_210, "PINGFILCLASSIC210", 210, 60),
        _classic_filament("PING PLA - 220", CLASSIC_PLA_220, "PINGFILCLASSIC220", 220, 60),
        _classic_filament("PING SupPLA",    CLASSIC_SUP_PLA, "PINGFILCLASSICSUP", 220, 60, True),
        _classic_filament(BASE_PLA_NEW,     CLASSIC_EDU_PLA, "PINGFILCLASSICEDU", 210, 0),
    ]
    classic_fil_list = []
    for d in classic_filaments:
        jdump(os.path.join(PINGDIR, "filament", "%s.json" % d["name"]), d)
        classic_fil_list.append({"name":d["name"], "sub_path":"filament/%s.json" % d["name"]})

    accel_keys = ("default_acceleration", "outer_wall_acceleration", "inner_wall_acceleration",
                  "sparse_infill_acceleration", "internal_solid_infill_acceleration",
                  "top_surface_acceleration", "initial_layer_acceleration", "bridge_acceleration",
                  "travel_acceleration")
    jerk_keys = ("default_jerk", "outer_wall_jerk", "inner_wall_jerk", "infill_jerk",
                 "top_surface_jerk", "initial_layer_jerk", "travel_jerk")

    for spec in CLASSIC_SPECS:
        name, nz = spec["name"], spec["nozzle"]
        src_mac_name = "%s %s nozzle" % (spec["src_model"], spec["src_nozzle"])
        src_mac = os.path.join(PINGDIR, "machine", "%s.json" % src_mac_name)
        mac = json.load(io.open(src_mac, encoding="utf-8"))
        mac_name = "%s %s nozzle" % (name, nz)
        proc_name = "%smm @%s (%s)" % (spec["layer"], name, nz)
        defaults = ([CLASSIC_PLA_220, CLASSIC_SUP_PLA] if spec["dual"] else
                    [CLASSIC_EDU_PLA] if not spec["heated_bed"] else [CLASSIC_PLA_210])

        mac.update({"type":"machine", "name":mac_name, "alias":name, "from":"system",
                    "instantiation":"true", "setting_id":"PINGM%03d" % gm,
                    "printer_model":name, "printer_variant":nz,
                    "default_print_profile":proc_name, "default_filament_profile":defaults,
                    "gcode_flavor":"marlin", "emit_machine_limits_to_gcode":"0",
                    "use_firmware_retraction":"0", "use_relative_e_distances":"0",
                    "machine_pause_gcode":"M0", "disable_m73":"1",
                    "printable_height":spec["height"],
                    "single_extruder_multi_material":"1" if spec["dual"] else "0"})
        if isinstance(mac.get("printable_area"), list):
            mac["printable_area"] = scale_circle_area_from(
                mac["printable_area"], spec["src_diameter"], spec["diameter"])
        for key, value in (("retraction_length", spec["retract"]),
                           ("retraction_speed", spec["retract_speed"]),
                           ("deretraction_speed", spec["retract_speed"]),
                           ("retract_length_toolchange", spec["retract"]),
                           ("retract_restart_extra", "0"),
                           ("retraction_minimum_travel", "1"),
                           ("z_hop", "0.5"), ("wipe", "0"),
                           ("retract_before_wipe", "0%")):
            _fill_array(mac, key, value)
        mac["default_filament_colors"] = (["#EA4E16", "#D3D3D3"] if spec["dual"] else ["#EA4E16"])
        mac["filament_colors"] = list(mac["default_filament_colors"])
        _fill_array(mac, "max_layer_height", "%g" % (0.75 * float(nz)))
        _fill_array(mac, "min_layer_height", "0.1")

        # 0729 Klipper 同步單 #128（Eric 令）：赤兔板無 T 工具語意——溫度行一律不帶 T
        #（雙料共用一顆熱嘴；單料同去＝V2.1 後處理本就滅全部 M104/M109 T 行）
        heat = ["M104 S[nozzle_temperature_initial_layer]"]
        if spec["heated_bed"]:
            heat = ["M140 S[bed_temperature_initial_layer_single]"] + heat + [
                "M190 S[bed_temperature_initial_layer_single]"]
        heat += ["M109 S[nozzle_temperature_initial_layer]"]
        prime_e = "5" if spec["dual"] else "3"
        mac["machine_start_gcode"] = "\n".join(
            ["G21", "G90", "M82"] + heat + ["G28 ;Home", "G92 E0", "G1 F200 E%s" % prime_e, "G92 E0"])
        if spec["dual"]:
            # Classic 雙料換刀＝M6050 原生輸出（0729 同步單硬規則）：S=第一路比例（S1=工具0全開、
            # S0=工具1）、P0 常規檔固定帶。模板含 M6050 ⇒ C++ custom_gcode_changes_tool 認定已換刀
            # ⇒ 兩呼叫端不再補裸 Tn（含起印首次選刀）；兩路同溫 220 ⇒ 引擎無中途變溫指令。
            mac["change_filament_gcode"] = "{if next_extruder == 0}M6050 S1 P0{else}M6050 S0 P0{endif}"
        end = ["G91", "G1 Z10 E-1 F9000", "M104 S0"]
        if spec["heated_bed"]:
            end.append("M140 S0")
        mac["machine_end_gcode"] = "\n".join(end + ["G90", "G28 X0 Y0", "M84"])

        jdump(os.path.join(PINGDIR, "machine", "%s.json" % mac_name), mac)
        mac_list.append({"name":mac_name, "sub_path":"machine/%s.json" % mac_name})
        gm += 1

        src_proc_name = (("%smm %s @%s (%s)" %
                          ("0.2" if nz == "0.4" else "0.3", combo_display("PLA+SUP"),
                           spec["src_model"], spec["src_nozzle"]))
                         if spec["dual"] else
                         ("%smm @%s (%s)" %
                          ("0.2" if nz == "0.4" else "0.3", spec["src_model"], spec["src_nozzle"])))
        proc = json.load(io.open(os.path.join(PINGDIR, "process", "%s.json" % src_proc_name), encoding="utf-8"))
        # 0730 改名批：Fast 母檔帶 renamed_from（易拆(Z0) 的舊名）——複製時必剝，否則 Classic
        # 製程冒領同一舊名＝重複認領地雷（0728 _classic_filament 線材版同族坑、verify 首跑實抓）。
        proc.pop("renamed_from", None)
        proc.update({"type":"process", "name":proc_name, "from":"system", "instantiation":"true",
                     "setting_id":"PINGP%03d" % gp, "inherits":"fdm_process_ping_common",
                     "compatible_printers":[mac_name], "layer_height":spec["layer"],
                     "initial_layer_print_height":spec["initial"], "seam_position":"aligned",
                     "support_type":"normal(auto)", "accel_to_decel_enable":"0",
                     # 檔名（Eric 2026-07-26 兩裁）：①跟進新格式 ②**取消「經典_」前綴**——
                     # 機型名本身已帶 DUAL/EDU/PING 2xx 字樣，再標「經典」對客戶無意義、他也不懂這個詞。
                     # ⇒ Classic 用它**實際的模式**：雙料機槽2 裝 Classic SupPLA ＝易拆；單料機＝單料。
                     #   例：`易拆_DUAL 600(0.6)_3DBenchy_3H_38g.gcode`
                     # ⚠ {print_time_half_h}/{total_weight_g} 是 2026-07-23 才進 Print.cpp 的佔位符，
                     #   舊 binary 吃到會炸 ⇒ profile 與 binary 必須同車出貨（既有耦合鐵則）。
                     "filename_format": filename_tpl("PLA+SUP" if spec["dual"] else "單料")})
        for key in accel_keys + jerk_keys:
            proc[key] = "0"
        sc = spec["speed_class"]
        if sc == "single":
            speeds = {"outer_wall_speed":"40", "inner_wall_speed":"40", "sparse_infill_speed":"40",
                      "internal_solid_infill_speed":"40", "top_surface_speed":"40", "gap_infill_speed":"40",
                      "support_speed":"40", "support_interface_speed":"40", "bridge_speed":"40",
                      "initial_layer_speed":"30", "initial_layer_infill_speed":"30", "travel_speed":"250"}
        elif sc == "dual04":
            speeds = {"outer_wall_speed":"40", "inner_wall_speed":"40", "sparse_infill_speed":"40",
                      "internal_solid_infill_speed":"40", "top_surface_speed":"40", "gap_infill_speed":"40",
                      "support_speed":"25", "support_interface_speed":"25", "bridge_speed":"40",
                      "initial_layer_speed":"25", "initial_layer_infill_speed":"25", "travel_speed":"250"}
        else:
            speeds = {"outer_wall_speed":"40", "inner_wall_speed":"80", "sparse_infill_speed":"60",
                      "internal_solid_infill_speed":"60", "top_surface_speed":"40", "gap_infill_speed":"40",
                      "support_speed":"25", "support_interface_speed":"25", "bridge_speed":"40",
                      "initial_layer_speed":"25", "initial_layer_infill_speed":"25", "travel_speed":"250"}
        proc.update(speeds)
        for key in ("line_width", "outer_wall_line_width", "inner_wall_line_width",
                    "sparse_infill_line_width", "internal_solid_infill_line_width",
                    "top_surface_line_width", "support_line_width"):
            proc[key] = nz
        proc["enable_prime_tower"] = "1" if spec["dual"] else "0"
        # ★ Classic 前代**套 F 系新工藝**（Eric 2026-07-25 裁「Classic 套新工藝」）。
        # Classic 由 Fast 母檔複製而來 ⇒ 母檔已套的新規則直接沿用，不再還原成 V3.6 Classic 舊值。
        # 沿用來源：normalize_unified_values ⑤爬坡品質/⑥支撐臨界角 35、normalize_support_geometry
        #（支撐幾何）、normalize_support_recipe（普通支撐配方）、normalize_tree_support（樹狀配方）。
        # 行為變更（本裁的實質內容，驗收看這幾項）：
        #   懸空降速 關→**開**（爬坡品質 50/50/25/10）、橋接流量 1→**0.95**、
        #   支撐臨界角 30→**35**、樹狀改保守配方（分支直徑 口徑×12 上限 10／距離 口徑×6／
        #   角度 30／auto_brim 關／brim 10／牆圈 1）、organic 防呆 2→2.6・60→40。
        # ⚠ 口徑安全：CLASSIC_SPECS 每台的 nozzle 皆等於 src_nozzle（0.4→0.4、0.6→0.6），
        #   所以母檔算出來的口徑連動值（線距／XY／分支直徑）對 Classic 直接成立，無錯配。
        # ⚠ Marlin 隔離原則仍在：本裁只放行「切片行為」類參數；加速度/jerk 全 "0"、
        #   不送 machine limits、不用韌體回抽／PA 等韌體相關設定在上方維持不變。
        jdump(os.path.join(PINGDIR, "process", "%s.json" % proc_name), proc)
        proc_list.append({"name":proc_name, "sub_path":"process/%s.json" % proc_name})
        gp += 1

        mm = {"type":"machine_model", "name":name,
              "model_id":"PING_" + name.replace(" ", "_").replace("+", "Plus"),
              "nozzle_diameter":nz, "machine_tech":"FFF", "family":"Classic",
              "bed_model":"" if spec["diameter"] in (200, 270) else bed_for(spec["src_model"]),
              "bed_texture":BED_TEXTURE, "hotend_model":"",
              "default_materials":";".join(defaults)}
        jdump(os.path.join(PINGDIR, "machine", "%s.json" % name), mm)
        mm_list.append({"name":name, "sub_path":"machine/%s.json" % name})
        nozzles_of[name] = [nz]

    print("  Classic V3.6 併入：machine=%d + machine_model=%d，process=%d，filament=%d" %
          (len(CLASSIC_SPECS), len(CLASSIC_SPECS), len(CLASSIC_SPECS), len(classic_fil_list)))

    # ★ Classic DUAL 變體：同進＋單料頭（Eric 2026-07-26 裁「只針對 DUAL 四台」、07-27「照做」）。
    #   放在既有 8 台迴圈之後＝既有 Classic 的 PINGM/PINGP id 零位移（後續棧板/PVA twins id 位移＝預期）。
    #   口徑照 FD 對應機（DUAL 300→FD300 三口徑；450/600/800→FD Pro 三口徑，1.0 照裁定字面照出）；
    #   參數繼承照 FD＝machine/process 從 FD 對應「變體」複製（速度/層高/支撐全 FD 值——與既有
    #   DUAL 雙料本體的 Classic 速度不同體系，Eric 0727 確認照字面）；Marlin 隔離照舊（加速度/jerk
    #   歸 0、不送 limits、無韌體回抽/PA、回抽 Classic 值）。
    #   同進混色＝M6050 S 舊格式（前代 Marlin 韌體只認 M6050）：start gcode 於 G28 後插 M6050 S0.5
    #  （對應 FD 同進 start 的同款行＝預擠兩邊同進）；逐層插碼由 BackgroundSlicingProcess 判
    #   printer_model「DUAL」開頭改傳 M6050（兩線 C++ 對稱；PingColorMix 剝除規則本就含 M6050＝不雙插）。
    #   預擠沿用 Classic 原地擠法（G1 F200 E<n>），不搬 FD 的床邊預擠線（那是 Klipper 床幾何）。
    vm = vp = vmm = 0
    for spec in CLASSIC_SPECS:
        if not spec["dual"]:
            continue
        for variant in ("同進", "單料頭"):
            model = "%s %s" % (spec["name"], variant)
            src_model = "%s %s" % (spec["src_model"], variant)
            vnzs = nozzles_of.get(src_model)
            if not vnzs:
                print("  !! Classic 變體 %s 缺 FD 源機型 %s" % (model, src_model)); continue
            for nz in vnzs:
                src_mac_path = os.path.join(PINGDIR, "machine", "%s %s nozzle.json" % (src_model, nz))
                mac = json.load(io.open(src_mac_path, encoding="utf-8"))
                mac_name = "%s %s nozzle" % (model, nz)
                src_dpp = mac.get("default_print_profile", "")
                proc_name = src_dpp.replace("@%s (" % src_model, "@%s (" % model)
                assert proc_name != src_dpp, "FD 變體 default_print_profile 格式變了: %r" % src_dpp
                mac.update({"type":"machine", "name":mac_name, "alias":model, "from":"system",
                            "instantiation":"true", "setting_id":"PINGM%03d" % gm,
                            "printer_model":model, "printer_variant":nz,
                            "default_print_profile":proc_name,
                            # 0728 Eric 裁「Classic 變體預設跟」：變體＝單一出料 → Classic 210
                            #（與 FD 連動同邏輯；DUAL 本體雙料維持 Classic 220 見 emit_classic defaults）
                            "default_filament_profile":[CLASSIC_PLA_210],
                            "gcode_flavor":"marlin", "emit_machine_limits_to_gcode":"0",
                            "use_firmware_retraction":"0", "use_relative_e_distances":"0",
                            "machine_pause_gcode":"M0", "disable_m73":"1",
                            "printable_height":spec["height"],
                            "single_extruder_multi_material":"0"})
                if isinstance(mac.get("printable_area"), list):
                    mac["printable_area"] = scale_circle_area_from(
                        mac["printable_area"], spec["src_diameter"], spec["diameter"])
                for key, value in (("retraction_length", spec["retract"]),
                                   ("retraction_speed", spec["retract_speed"]),
                                   ("deretraction_speed", spec["retract_speed"]),
                                   ("retract_length_toolchange", spec["retract"]),
                                   ("retract_restart_extra", "0"),
                                   ("retraction_minimum_travel", "1"),
                                   ("z_hop", "0.5"), ("wipe", "0"),
                                   ("retract_before_wipe", "0%")):
                    _fill_array(mac, key, value)
                mac["default_filament_colors"] = ["#EA4E16"]   # 變體＝1 槽（SEMM 0，同 FD 變體）
                mac["filament_colors"] = list(mac["default_filament_colors"])
                _fill_array(mac, "max_layer_height", "%g" % (0.75 * float(nz)))
                _fill_array(mac, "min_layer_height", "0.1")
                heat = ["M104 S[nozzle_temperature_initial_layer]"]
                if spec["heated_bed"]:
                    heat = ["M140 S[bed_temperature_initial_layer_single]"] + heat + [
                        "M190 S[bed_temperature_initial_layer_single]"]
                heat += ["M109 S[nozzle_temperature_initial_layer]"]
                # 同進＝兩馬達同動各半（先 M6050 S0.5 再擠 5）；單料頭＝實體單頭擠 3（同 Classic 單料機）
                sync = ["M6050 S0.5"] if variant == "同進" else []
                prime_e = "5" if variant == "同進" else "3"
                mac["machine_start_gcode"] = "\n".join(
                    ["G21", "G90", "M82"] + heat + ["G28 ;Home"] + sync
                    + ["G92 E0", "G1 F200 E%s" % prime_e, "G92 E0"])
                end = ["G91", "G1 Z10 E-1 F9000", "M104 S0"]
                if spec["heated_bed"]:
                    end.append("M140 S0")
                mac["machine_end_gcode"] = "\n".join(end + ["G90", "G28 X0 Y0", "M84"])
                jdump(os.path.join(PINGDIR, "machine", "%s.json" % mac_name), mac)
                mac_list.append({"name":mac_name, "sub_path":"machine/%s.json" % mac_name})
                gm += 1; vm += 1

                proc = json.load(io.open(os.path.join(PINGDIR, "process", "%s.json" % src_dpp),
                                         encoding="utf-8"))
                proc.update({"type":"process", "name":proc_name, "from":"system", "instantiation":"true",
                             "setting_id":"PINGP%03d" % gp, "inherits":"fdm_process_ping_common",
                             "compatible_printers":[mac_name], "accel_to_decel_enable":"0",
                             "filename_format": filename_tpl("同進" if variant == "同進" else "單料")})
                for key in accel_keys + jerk_keys:
                    proc[key] = "0"
                jdump(os.path.join(PINGDIR, "process", "%s.json" % proc_name), proc)
                proc_list.append({"name":proc_name, "sub_path":"process/%s.json" % proc_name})
                gp += 1; vp += 1

            mm = {"type":"machine_model", "name":model,
                  "model_id":"PING_" + model.replace(" ", "_"),
                  "nozzle_diameter":";".join(vnzs), "machine_tech":"FFF", "family":"Classic",
                  "bed_model":bed_for(spec["src_model"]), "bed_texture":BED_TEXTURE, "hotend_model":"",
                  "default_materials":CLASSIC_PLA_210}   # 0728 變體預設跟（單一出料＝210）
            jdump(os.path.join(PINGDIR, "machine", "%s.json" % model), mm)
            mm_list.append({"name":model, "sub_path":"machine/%s.json" % model})
            nozzles_of[model] = list(vnzs)   # cover 空白卡（endswith 同進/單料頭）＋側欄縮圖迴圈自動吃
            vmm += 1

    print("  Classic DUAL 變體併入：machine=%d，process=%d，machine_model=%d" % (vm, vp, vmm))
    return gm, gp, classic_fil_list

# ---------- 3z. 預勾線材（default_materials）post-pass ----------
# ★ Eric 2026-08-07 裁「全族補齊」：每台機型的 default_materials ＝「所有與它相容的 PING 線材」。
#   起因＝Eric 實地發現設定精靈「選擇線材」頁只預勾 12 支，`PING PVA`／`PING TPE - 210`／
#   `PING SupTPE` 更是 0/41 台預勾——客戶端一定得自己去勾才看得到我們自家的料。
#
# 為什麼做成 post-pass、而不是各處補字串：預勾清單原本散在 **4 條 emit 路徑**
#（DEFAULT_MATERIALS_FD／def_fil_ff／emit_classic 本體與變體）**＋6 個 base 範本**硬寫，
# 正是 SOP_參數入版紀律 §4「產生器規則函式掃不到的來源」的教科書案例（0726 一天踩三次）。
# 收斂成單一 post-pass 後規則只有一處，日後新增線材／新增機型自動涵蓋，且順手剔除
# filament_list 已無的死名（0725 ABS 整併留下的 `PING ABS - 250`／`PING PolyABS`）。
#
# 兩條族群規則：
#  (a) **Classic 線材只進 Classic 前代機**——4 支 Classic 線材沒設 compatible_printers（＝不限機型），
#      純靠相容性推導會把前代 Marlin 專用料外溢到 Fast 25 台（現況沒外溢，本 post-pass 不得製造）。
#      機型判定照 SOP §9：前代機＝機型名前綴 `EDU|DUAL|PING 2|PING 3`，沒有任何機器叫「Classic」。
#  (b) 其餘 PING 線材一律依各自的 compatible_printers（3in1 支綁 3in1 機、四料高流量支綁 FF 非 3in1）。
#
# ⚠ 已知代價（Eric 看過實證後重申照做＝有意識取捨、非疏漏，下一棒勿當缺口回補）：
#   Fast 線線材的 filament_start_gcode 帶 Klipper 專用 `SET_RETRACTION`，Classic（赤兔/Marlin）
#   線材則明寫 "machine retraction only" 刻意不帶。全族補齊後前代機也預勾得到 Fast 料，
#   客戶選到就會把 SET_RETRACTION 送給 Marlin 板（韌體不認、回抽覆蓋靜默失效，
#   與 0729「Classic 出檔鐵律」精神相衝）。正解＝另開不帶該指令的 Classic 版線材，本批不做。
CLASSIC_MODEL_RE = re.compile(r"^(EDU|DUAL|PING 2|PING 3)")

def _is_classic_model(name):
    return bool(CLASSIC_MODEL_RE.match(name))

def apply_default_materials(pj):
    """依「線材 compatible_printers × 機型」重算每台 machine_model 的 default_materials。"""
    def _load(sub):
        p = os.path.join(PINGDIR, sub)
        return json.load(io.open(p, encoding="utf-8")) if os.path.isfile(p) else None

    # 1) 可勾的 PING 線材 → compatible_printers（None＝不限機型）。fdm_filament_* 基底
    #    instantiation=false、使用者選不到，不進預勾清單。
    fil_compat = {}
    for e in pj["filament_list"]:
        if not e["name"].startswith("PING "):
            continue
        d = _load(e["sub_path"])
        if not d or d.get("instantiation") != "true":
            continue
        cp = d.get("compatible_printers")
        fil_compat[e["name"]] = set(cp) if isinstance(cp, list) and cp else None
    order = list(fil_compat)   # filament_list 順序＝新增項排序基準（dict 保序）

    # 2) printer_model → 該機型底下的 machine preset 名（口徑變體）
    variants = {}
    for e in pj["machine_list"]:
        d = _load(e["sub_path"])
        if d and d.get("instantiation") == "true" and d.get("printer_model"):
            variants.setdefault(d["printer_model"], set()).add(e["name"])

    changed = added = dropped = n_classic = n_fast = 0
    for e in pj["machine_model_list"]:
        p = os.path.join(PINGDIR, e["sub_path"])
        d = json.load(io.open(p, encoding="utf-8"))
        model = d["name"]
        vs = variants.get(model)
        if not vs:
            print("  ⚠ 預勾 post-pass：機型 %s 找不到任何 machine preset，跳過" % model)
            continue
        classic_model = _is_classic_model(model)
        n_classic += classic_model
        n_fast += (not classic_model)
        want = [n for n in order
                if (fil_compat[n] is None or (fil_compat[n] & vs))          # (b) 相容性
                and (classic_model or "Classic" not in n)]                  # (a) Classic 線材隔離
        old = [x for x in (d.get("default_materials") or "").split(";") if x]
        keep = [x for x in old if x in want]                                # 保序＝最小 diff
        new = keep + [x for x in want if x not in keep]
        dropped += len(old) - len(keep)
        added += len(want) - len(keep)
        if new != old:
            d["default_materials"] = ";".join(new)
            jdump(p, d)
            changed += 1
    # SOP §4 對帳：數量對不上＝有掃不到的來源，不是四捨五入
    print("  預勾線材全族補齊：%d/%d 台機型更新（Fast %d 台／Classic %d 台；"
          "新增 %d 項、剔除死名或不相容 %d 項）"
          % (changed, len(pj["machine_model_list"]), n_fast, n_classic, added, dropped))
    return changed


# ---------- 4. 主流程 ----------
def main(src_base):
    # 4a. 清掉舊 machine/process（保留 fdm 基底）
    for sub, keep in (("machine", ("fdm_machine_common.json","fdm_ping_common.json")),
                      ("process", ("fdm_process_common.json","fdm_process_ping_common.json"))):
        d = os.path.join(PINGDIR, sub)
        for f in os.listdir(d):
            if f.endswith(".json") and f not in keep:
                os.remove(os.path.join(d, f))

    # 4a-0. ★ 基礎支改名 sweep（Eric 2026-07-28；常數見 BASE_PLA_OLD/NEW）——放在最前：
    #       emit_classic 以新名讀母檔、4b-2 系列 sweep 掃到的即是新檔；殘檔清除＝regen-durable。
    _oldp = os.path.join(PINGDIR, "filament", BASE_PLA_OLD + ".json")
    _newp = os.path.join(PINGDIR, "filament", BASE_PLA_NEW + ".json")
    if os.path.isfile(_oldp):
        _fd = json.load(io.open(_oldp, encoding="utf-8"))
        _fd.update({"name": BASE_PLA_NEW, "alias": BASE_PLA_NEW,
                    "renamed_from": BASE_PLA_OLD})   # ⚠ 字串（T004 鐵則）
        jdump(_newp, _fd)
        os.remove(_oldp)
        print("  基礎支改名：%s → %s（renamed_from 字串相容、id 不動）" % (BASE_PLA_OLD, BASE_PLA_NEW))

    gm = gp = 0
    mm_list, mac_list, proc_list = [], [], []
    nozzles_of = {}   # model -> [nz...]
    pallet_twins = []   # 棧板雙生製程（主迴圈收集、4a-4 統一 emit＝id 排最後）
    pva_twins = []      # PLA+PVA 專屬製程（同上，emit 接在棧板之後＝棧板 id 亦零位移）

    for dirname, base, kind in FAMS:
        cfgs = parse_dir(src_base, dirname)
        if kind == "dual":
            modes = [("PLA+SUP", base, def_fil_dual_for(base), False),   # 雙料機母檔=PLA+SUP；製程另出 4 組合
                     ("單料頭", base + " 單料頭", def_fil_single_for(base), True),
                     ("同進",   base + " 同進",   def_fil_single_for(base), True)]
        elif kind == "dual1":   # 衍生雙料機只出本體（FD300 關門——Eric 裁不出 關門 同進/單料頭）
            modes = [("PLA+SUP", base, def_fil_dual_for(base), False)]
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
                is_dual_machine = (kind in ("dual", "dual1") and mode_key == "PLA+SUP")
                combos = [cb for cb in DUAL_COMBOS if (nz, cb) in cfgs] if is_dual_machine else [mode_key]
                def pname(cb):
                    return ("%smm %s @%s (%s)" % (lh, combo_display(cb), model, nz)) if is_dual_machine \
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
                    normalize_support_mode(proc, model)
                    normalize_fast_speed(proc)   # 牆速/填充正規化（外60/內≤80/填100/accel5000；首層不動）
                    normalize_prime_tower(proc)  # 換料塔統一（0708 立；0717 寬 25；0729 錐體30/速60）
                    normalize_wall_accel(proc)   # 內外牆加速度 1500（2026-07-29 Eric 裁）
                    normalize_unified_values(proc, ff=(kind == "ff"))  # 正式製程統一值；FF 四色 jerk 維持 40
                    # 介面 4 層＋間距 70% 密度等效口徑連動＋首層密度 10%（0804；易拆間距既值不動、
                    # ABS 系 raft_layers=2 已由 combo_overrides 設定→首層 100% 自然跳過）
                    normalize_support_interface(proc, nz, easy_release=cb.endswith("+SUP"))
                    normalize_support_geometry(proc, nz)  # 樹狀直徑口徑×12(上限10)＋分支距離口徑×6＋主體線距口徑×9（0717/0722/0725）
                    normalize_support_recipe(proc, nz, easy_release=cb.endswith("+SUP"))  # 普通支撐配方（2026-07-22 七裁）
                    normalize_tree_support(proc)  # 樹狀保守配方＋organic 防呆（2026-07-25）
                    proc.update({"type":"process","name":pname(cb),"from":"system","instantiation":"true",
                        "setting_id":"PINGP%03d"%gp,"inherits":"fdm_process_ping_common",
                        "compatible_printers":[mac_name],
                        "filename_format": filename_tpl(cb)})
                    if is_dual_machine:   # 功能歸類改名：舊材料對全名入 renamed_from（舊 3mf 回溯）
                        proc["renamed_from"] = combo_renamed_from(lh, cb, model, nz)
                    jdump(os.path.join(PINGDIR,"process","%s.json"%pname(cb)), proc)
                    proc_list.append({"name":pname(cb),"sub_path":"process/%s.json"%pname(cb)}); gp += 1
                    # 棧板雙生（單料頭/同進/FP 限定；kind=ff 的四色 is_single=False 天然排除）
                    if is_single and not PING_ONLY:
                        tw = dict(proc); tw.update(PALLET_OVERRIDES)
                        tw["name"] = "%smm_棧板 @%s (%s)" % (lh, model, nz)
                        pallet_twins.append(tw)
                    # PLA+PVA 專屬製程雙生（Eric 2026-07-25 裁「出」）：從同口徑 PLA+SUP 派生
                    #（易拆幾何 Z0／XY 口徑×0.75、支撐料槽 2、速度/層高家規全部自然繼承）
                    if is_dual_machine and cb == "PLA+SUP":
                        pv = dict(proc); pv.update(pva_overrides(nz))
                        pv["name"] = "%smm %s @%s (%s)" % (lh, combo_display("PLA+PVA"), model, nz)
                        pv["renamed_from"] = combo_renamed_from(lh, "PLA+PVA", model, nz)
                        pv["filename_format"] = filename_tpl("PLA+PVA")
                        pva_twins.append(pv)

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
        gm, gp, ff_fil, ff_models, hf_twins = emit_ff_extra(mm_list, mac_list, proc_list, gm, gp)
    else:
        ff_fil, ff_models, hf_twins = [], [], []
    # 4a-3b. V3.6 Classic 前代機：和 Fast 同 bundle，但用獨立 machine/process/filament，
    # 避免 Klipper 指令與高加速度滲入 Marlin 舊板。
    if not PING_ONLY:
        gm, gp, classic_fil = emit_classic(mm_list, mac_list, proc_list, nozzles_of, gm, gp)
    else:
        classic_fil = []

    # 4a-4. 棧板雙生製程統一 emit（setting_id 接在全庫最後＝既有 id 零位移）
    for tw in pallet_twins:
        tw["setting_id"] = "PINGP%03d" % gp; gp += 1
        jdump(os.path.join(PINGDIR, "process", "%s.json" % tw["name"]), tw)
        proc_list.append({"name": tw["name"], "sub_path": "process/%s.json" % tw["name"]})
    if pallet_twins:
        print("  棧板雙生製程：%d 支（PINGP%03d 起）" % (len(pallet_twins), gp - len(pallet_twins)))

    # 4a-5. PLA+PVA 專屬製程統一 emit（接在棧板之後＝既有＋照片磚＋棧板 id 全零位移）
    for pv in pva_twins:
        pv["setting_id"] = "PINGP%03d" % gp; gp += 1
        jdump(os.path.join(PINGDIR, "process", "%s.json" % pv["name"]), pv)
        proc_list.append({"name": pv["name"], "sub_path": "process/%s.json" % pv["name"]})
    if pva_twins:
        print("  PLA+PVA 專屬製程：%d 支（PINGP%03d 起）" % (len(pva_twins), gp - len(pva_twins)))

    # 4a-5. 照片磚範本併入（需 FF800/FD300 家族＝通用版；客戶版 PING_ONLY 跳過）。
    #       須在 4b 之前跑，讓高流量 PLA 的 compatible 掛得到照片磚機。
    #       範本資料夾不存在（如無照片磚的 release 分支）＝自動跳過，同一支產生器兩線通用。
    #       ⚠ 位置＝id 佈局承重牆（2026-07-20 修正）：8c487d82 setting_id 治理把照片磚
    #       重掛「全庫最尾」（機 PINGM074-078＝接 Classic 073 之後、製程 PINGP152-156＝
    #       接棧板雙生 151 之後），故照片磚必須在 Classic 與棧板雙生「之後」emit，
    #       regen 才零位移；先前排在 Classic 前＝每次 regen 都撞號（r6 事故同源）。
    if not PING_ONLY and os.path.isdir(PHOTOTILE):
        gm, gp, pt_models = emit_phototile(mm_list, mac_list, proc_list, gm, gp)
    else:
        pt_models = []
    # 0728 v2 連動：FD300 同進照片磚＝單一出料 → 預設 PLA-220 → PLA-210（機 2＋model 1；
    # 範本值不動、emit 後就地改寫＝regen-durable。FF800 同進照片磚＝FF 系四料高流量、不在範圍）
    _pt210 = 0
    for _pm in ("FD300 同進照片磚 0.4 nozzle", "FD300 同進照片磚 0.6 nozzle", "FD300 同進照片磚"):
        _pp = os.path.join(PINGDIR, "machine", _pm + ".json")
        if not os.path.isfile(_pp):
            continue
        _pd = json.load(io.open(_pp, encoding="utf-8"))
        _hit = False
        _dfp = _pd.get("default_filament_profile")
        if isinstance(_dfp, list) and "PING PLA - 220" in _dfp:
            _pd["default_filament_profile"] = [BASE_PLA_NEW if x == "PING PLA - 220" else x for x in _dfp]
            _hit = True
        _dm = _pd.get("default_materials")
        if isinstance(_dm, str) and "PING PLA - 220" in _dm.split(";"):
            _pd["default_materials"] = ";".join(BASE_PLA_NEW if t == "PING PLA - 220" else t
                                                for t in _dm.split(";"))
            _hit = True
        if _hit:
            jdump(_pp, _pd); _pt210 += 1
    if _pt210:
        print("  照片磚 FD300 同進預設 210：改 %d 檔" % _pt210)

    # 4a-6. 高流量製程組統一 emit（Eric 2026-07-30 裁；id 接尾＝既有＋Classic＋棧板＋PVA＋照片磚
    #        全零位移——⚠ 本線照片磚在 PVA 之後 emit〔id 佈局承重牆〕，高流量必須排照片磚之後）
    for hf in hf_twins:
        hf["setting_id"] = "PINGP%03d" % gp; gp += 1
        jdump(os.path.join(PINGDIR, "process", "%s.json" % hf["name"]), hf)
        proc_list.append({"name": hf["name"], "sub_path": "process/%s.json" % hf["name"]})
    if hf_twins:
        print("  高流量製程組：%d 支（PINGP%03d 起）" % (len(hf_twins), gp - len(hf_twins)))

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
            # PING(2026-07-26 Eric 裁 A・下拉去重)：四料高流量噴頭支＝FF 四進一出硬體專屬
            #（四色/同進/FF 照片磚 64 槽預設引用實證），與 3in1 支（帶 T012/T3 同步進料
            # gcode、流量 20/12、PA 0.2）互為**不同機構**、不是重複——各綁各的機，下拉
            # 不再互相出現；值與行為分毫不動。清單動態取自本輪 mac_list（含 ff_extra/照片磚
            # ——4b 在其後跑，本檔 4a-3 註解即為此設計）＝regen-durable。
            fp["compatible_printers"] = sorted(
                x["name"] for x in mac_list
                if x["name"].startswith(("FF600", "FF800")) and "3in1" not in x["name"])
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
                                     (("PING PETG"),       HFN_PETG, "PINGFILHFNPETG")):
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
    # PING TPE - 210（本體）＋ PING SupTPE（TPU 系支撐料）。
    # ★ 0729 Eric 裁（回報中心單）：TPE 最大體積流量 3.2→**7**＝對齊 SpiderMaker TPE 官方建議
    #   6~8 的起始值 7（原 3.2 係 0718「軟慢」夾速設計＝0.2×0.4 下限速 40，比官方保守）。
    #   ⚠ 行為變更：0.4 口徑實質不再夾速（7÷0.08≈87>製程速度）；0.6 口徑 7÷0.18≈39 仍約 40。
    #   SupTPE 維持 5.5（本裁只點名 TPE）。
    # ★ 0728 Eric 二輪裁「PING TPE - 210(温度也改低一点)」：本體改名帶溫度尾碼＋噴溫 220→210
    #  （初層/其他層一致）；SupTPE 名不動、噴溫跟隨 210（兩側一致原則不變）。
    #   renamed_from ⚠ 字串（T004 鐵則）只掛本體；id 不動（同一支材料身份）；殘檔清除 regen-durable。
    # 床溫承 PLA 慣例 60（Eric 實跑基底）、回抽 3/z-hop 0.6、TPE 風扇 50/SupTPE 100、
    # PA 關（軟料待實測）。不限機型；SET_RETRACTION 行由 4b-2 sweep 保證。
    _old_tpe = os.path.join(PINGDIR, "filament", "PING TPE.json")
    if os.path.isfile(_old_tpe):
        os.remove(_old_tpe)
        print("  TPE 改名：移除殘檔 PING TPE.json（新名 PING TPE - 210、renamed_from 相容）")
    for new_name, fid, is_sup in (("PING TPE - 210", "PINGFILTPE", False),
                                  ("PING SupTPE", "PINGFILSUPTPE", True)):
        fd_ = {"type": "filament", "name": new_name, "alias": new_name, "from": "system",
               "instantiation": "true", "inherits": "fdm_filament_tpu",
               "setting_id": fid, "filament_id": fid,
               "filament_type": ["TPU"],
               "nozzle_temperature_initial_layer": ["210"], "nozzle_temperature": ["210"],
               "hot_plate_temp_initial_layer": ["60"], "hot_plate_temp": ["60"],
               "fan_min_speed": ["100" if is_sup else "50"],
               "fan_max_speed": ["100" if is_sup else "50"],
               "filament_max_volumetric_speed": ["5.5" if is_sup else "7"],
               "filament_retraction_length": ["3"], "filament_z_hop": ["0.6"],
               # 0728 Eric「TPE軟料的回抽 3/30/30」：速度/裝填補 30（原未設＝吃機器層 20/20）
               "filament_retraction_speed": ["30"], "filament_deretraction_speed": ["30"],
               "enable_pressure_advance": ["0"], "pressure_advance": ["0"],
               "slow_down_for_layer_cooling": ["1"], "slow_down_layer_time": ["10"],
               "filament_minimal_purge_on_wipe_tower": ["30"]}
        if is_sup:
            fd_.update({"filament_is_support": ["1"],
                        "filament_colors": ["#D3D3D3"], "default_filament_colors": ["#D3D3D3"]})
        else:
            fd_["renamed_from"] = "PING TPE"   # ⚠ 字串（T004 鐵則）；舊名相容（0728 改名）
        jdump(os.path.join(PINGDIR, "filament", "%s.json" % new_name), fd_)
        fil_new.append({"name": new_name, "sub_path": "filament/%s.json" % new_name})

    # 4b-1d. ★ PVA 水溶支撐線材（Eric 2026-07-24 裁「參考 2.1 追加、一般流量即可」・主線 37cad9cb/48023ae8 移植；
    # 值已對帳 V2.1 定稿案＝劉勝賢提供 D800 Pro(0.6)_PVA+PLA.3mf
    # 〔中華航空案、DPro_0.6_T210_PVA+PLA (0609)、Eric：「比較保守、練出來也不錯」〕）：
    #   噴溫 210/210（V2.1 案全鍵一致 210——PLA 側同降 210 的保守組；蓋掉首版推定 220）、
    #   床 60、風扇 100/100（V2.1 案未定此鍵＝沿 Orca 支撐慣例）、
    #   回抽長度 3＋z-hop 0.6（V2.1 案 PVA 側定稿；速度 30=機器層家規）、
    #   purge 85（V2.1 檔內 75＋劉勝賢現行「+10」＝85；4b-3 同步豁免）、
    #   水溶＋支撐旗標、支撐色 #D3D3D3、最大體積流量 12（V2.1 速度 60×0.35×0.6≈12.6 貼合）、
    #   密度 1.23。額外回填 0.2＋四項統一（4b-2/2b sweep；長度 3=PVA 特例、sweep 豁免同 TPE）。
    # 「一般流量即可」＝不出高流量變體；不限機型（噴頭屬性原則，同 TPE 先例）。
    fd_ = {"type": "filament", "name": "PING PVA", "alias": "PING PVA", "from": "system",
           "instantiation": "true", "inherits": "fdm_filament_pla",
           "setting_id": "PINGFILPVA", "filament_id": "PINGFILPVA",
           "filament_vendor": ["PING"], "filament_type": ["PVA"],
           "filament_soluble": ["1"], "filament_is_support": ["1"],
           "filament_density": ["1.23"],
           "nozzle_temperature_initial_layer": ["210"], "nozzle_temperature": ["210"],
           "hot_plate_temp_initial_layer": ["60"], "hot_plate_temp": ["60"],
           "cool_plate_temp_initial_layer": ["60"], "cool_plate_temp": ["60"],
           "fan_min_speed": ["100"], "fan_max_speed": ["100"],
           "filament_retraction_length": ["3"], "filament_z_hop": ["0.6"],
           "filament_max_volumetric_speed": ["12"],
           "filament_colors": ["#D3D3D3"], "default_filament_colors": ["#D3D3D3"],
           "filament_minimal_purge_on_wipe_tower": ["85"],
           "slow_down_for_layer_cooling": ["1"], "slow_down_layer_time": ["10"]}
    jdump(os.path.join(PINGDIR, "filament", "PING PVA.json"), fd_)
    fil_new.append({"name": "PING PVA", "sub_path": "filament/PING PVA.json"})

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
        if "Classic" in fd.get("name", ""):
            continue   # Classic 是 Marlin：不可加入 Klipper SET_RETRACTION
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

    # 4b-2b. ★ 線材回抽統一（Eric 2026-07-23 三裁＋兩補裁・主線 25650196/8515bafb/95bf5a7c 移植）：
    # ①長度收斂繼承（未勾＝機器 1.3＝與韌體 config 同值等效）；特例：高流量家族（高流量噴頭/四料/3in1）=2、TPE=3
    # ②額外回填長度＝噴頭流量形式律：高流量=0.6、一般流量=0.2（含 TPE）——換料/回抽後補缺料
    # ③四項統一（PLA - 220 基準）：空駛臨界 3／回抽時擦拭 1／擦拭距離 5／擦拭前回抽 100%
    # ⚠ Classic 前代線材豁免（Marlin 隔離原則：回抽行為值未經 Eric 裁、不動）；DL1016 不在名單自然豁免。
    rt_touched = 0
    for fp_path in glob.glob(os.path.join(PINGDIR, "filament", "PING*.json")):
        fd = json.load(io.open(fp_path, encoding="utf-8"))
        if fd.get("instantiation") != "true":
            continue
        bn = os.path.basename(fp_path)[:-5]
        if "Classic" in bn:
            continue
        before = json.dumps(fd, sort_keys=True)
        fd["filament_retraction_minimum_travel"] = ["3"]
        fd["filament_wipe"] = ["1"]
        fd["filament_wipe_distance"] = ["5"]
        fd["filament_retract_before_wipe"] = ["100%"]
        is_hf = ("高流量" in bn) or ("(3in1)" in bn)
        fd["filament_retract_restart_extra"] = ["0.6" if is_hf else "0.2"]
        if "TPE" in bn or "PVA" in bn:
            pass                                          # TPE/SupTPE 維持 3（0718 定稿）；PVA 維持 3（0724 V2.1 案定稿）
                                                          # ⚠ 0725 稽核抓漏：01148acf 全批移植時這裡漏了 PVA，
                                                          #   PVA 掉進 else 拿 nil＝繼承機器 1.3，與主線 48023ae8 不符
        elif is_hf:
            # 2026-07-30 Eric 裁「高流量材料回抽 3/30/30，雙料高流量與四料高流量都一致」：
            # 長度 2→3（0723 補裁的 2 被上蓋）＋速度/裝填 30 明寫。四料高流量兩支原本 speed/
            # deretraction 是 nil（＝繼承機器 20/20、非 30）＝Eric 說的「沒改到」，本裁一併補齊。
            # 範圍＝is_hf 家族（含 3in1，沿 0723「3in1 同勾」的同族慣例）。
            fd["filament_retraction_length"] = ["3"]
            fd["filament_retraction_speed"] = ["30"]
            fd["filament_deretraction_speed"] = ["30"]
        else:
            fd["filament_retraction_length"] = ["nil"]    # 其餘收斂繼承機器 1.3
        if json.dumps(fd, sort_keys=True) != before:
            jdump(fp_path, fd); rt_touched += 1
    if rt_touched:
        print("  線材回抽統一（長度收斂＋額外回填流量律＋四項；Classic 豁免）：%d 支" % rt_touched)

    # 4b-2f. ★ 一般流量 PA 0.08（Eric 2026-07-28 三輪裁「材料如果不是高流量跟火山口或四料，
    # 它的壓力提前是 0.08」）：非高流量／非火山口(PA-CF)／非四料(含 3in1) 的一般流量硬料
    # → enable_pressure_advance 1＋pressure_advance 0.08（蓋 0725 ABS 整併帶進的 0.12＝
    # 未經 PA 塔實測值）。豁免照既有裁定：TPE/SupTPE（軟料 PA 關＝0725 裁待實測、本條不翻案）、
    # Classic（Marlin 無 PA、全關斷言）、DL1016（注入源不在產線）。冪等 sweep＝regen-durable。
    pa_set = 0
    for fp_path in glob.glob(os.path.join(PINGDIR, "filament", "PING*.json")):
        fd = json.load(io.open(fp_path, encoding="utf-8"))
        if fd.get("instantiation") != "true":
            continue
        bn = os.path.basename(fp_path)[:-5]
        if any(t in bn for t in ("Classic", "高流量", "(3in1)", "TPE", "PA-CF")):
            continue
        if fd.get("enable_pressure_advance") != ["1"] or fd.get("pressure_advance") != ["0.08"]:
            fd["enable_pressure_advance"] = ["1"]
            fd["pressure_advance"] = ["0.08"]
            jdump(fp_path, fd); pa_set += 1
    if pa_set:
        print("  一般流量 PA 0.08（高流量/火山口/四料/3in1/TPE/Classic 豁免）：%d 支" % pa_set)

    # 4b-2c. ★ 懸空冷卻觸發閾值 25%（Eric 2026-07-24 爬坡品質批・線材側配套・主線 37cad9cb 移植）：
    # 全 PING 線材統一 25%（PLA - 220／ABS - 250 既值 25% 冪等不動；PLA 210 系／SupPLA／
    # PETG／TPE 等原繼承 50%／95% → 收 25%）。overhang_fan_speed 不動（爬坡測試對照未改此鍵，
    # 各支既值/繼承值保留）。冪等 sweep。
    # ⚠ 出貨線特調：**Classic 前代線材豁免**（Marlin 隔離原則，同 0723 回抽統一先例）——
    #   主線註解稱「Classic 不在 PING*.json 名單自然豁免」僅對主線成立；出貨線的 Classic 線材
    #   就是叫 `PING PLA - Classic 210.json` 等，會被本 sweep 掃到，必須明文排除。
    of_set = 0
    for fp_path in glob.glob(os.path.join(PINGDIR, "filament", "PING*.json")):
        if "Classic" in os.path.basename(fp_path):
            continue   # Classic 前代豁免（出貨線特調）
        fd = json.load(io.open(fp_path, encoding="utf-8"))
        if fd.get("instantiation") != "true":
            continue
        if fd.get("overhang_fan_threshold") != ["25%"]:
            fd["overhang_fan_threshold"] = ["25%"]
            jdump(fp_path, fd)
            of_set += 1
    if of_set:
        print("  線材懸空冷卻觸發閾值 25%%：改 %d 支" % of_set)

    # 4b-2e. ★ 線材顏色 key 正規化（Eric 2026-07-25 實測「切換線材不會給預設的顏色」→ 追碼定讞）
    # 🔴 真因：PING 線材長期寫的是 `filament_colors`／`default_filament_colors`（**美式・複數**），
    #    但 Orca **preset 層**認的是 `filament_colour`／`default_filament_colour`
    #   （**英式・單數**，PrintConfig.cpp:2279/2287）⇒ 引擎完全讀不到、我們設的顏色從未生效。
    # ⚠ 複數版 key 在引擎裡只存在於 AppConfig.cpp（app 設定檔 `presets.filament_colors` ＝ conf 層，
    #    不是 profile 層）——名字像、層級完全不同，是這個坑好發的原因。
    # 連動鏈：側欄槽位色塊＝`clr_picker`（Plater.cpp:2305）→ 切換 preset 時讀 preset 的
    #   `default_filament_colour`（PresetComboBoxes.cpp:241）⇒ key 對了才會隨線材更新。
    # 冪等 sweep：改名後移除舊複數鍵；已是單數者跳過。Classic 線材同套（顏色與 Marlin 隔離無關）。
    ck_fixed = 0
    for fp_path in glob.glob(os.path.join(PINGDIR, "filament", "PING*.json")):
        fd = json.load(io.open(fp_path, encoding="utf-8"))
        touched = False
        # 只保留 `default_filament_colour`＝**線材 preset 唯一合法的顏色鍵**。
        # 🔴 0725 查證：`Preset.cpp:960` 的 s_Preset_filament_options 裡，
        #    `"filament_colour"` 是**被上游註解掉的**（/*"filament_colour", */）
        #    ⇒ 線材檔帶它，引擎載入時會判為 incorrect key 直接剝掉，
        #      並在 log 刷 "contains incorrect keys: filament_colour, which were removed"。
        #    功能上無害（顏色是靠 default_filament_colour 生效），但屬無效殘留 ⇒ 一併清掉。
        if "default_filament_colors" in fd and "default_filament_colour" not in fd:
            fd["default_filament_colour"] = fd["default_filament_colors"]
            touched = True
        elif "filament_colors" in fd and "default_filament_colour" not in fd:
            # 舊檔只有複數版 filament_colors 時，值同樣拿來當預設色來源
            fd["default_filament_colour"] = fd["filament_colors"]
            touched = True
        for dead in ("filament_colors", "default_filament_colors", "filament_colour"):
            if dead in fd:
                fd.pop(dead, None); touched = True
        if touched:
            jdump(fp_path, fd); ck_fixed += 1
    if ck_fixed:
        print("  線材顏色 key 正規化（複數→單數）：%d 支" % ck_fixed)

    # 4b-3. ★ 洗料塔最小清理量（Eric 2026-07-17 裁）：全線材 30；SupPLA 系（含高流量噴頭/Classic）60；
    # FF「四料高流量噴頭」/「(3in1)」維持特調 120 不動（四色換色需大量清洗，Eric 同日裁「不蓋」）。
    # 放 4b-2 之後同樣吃冪等 sweep：重生檔每次 regen 自動補。
    pv_set = 0
    for fp_path in glob.glob(os.path.join(PINGDIR, "filament", "PING*.json")):
        bn = os.path.basename(fp_path)
        if "四料高流量噴頭" in bn or "(3in1)" in bn:
            continue
        fd = json.load(io.open(fp_path, encoding="utf-8"))
        # PVA＝85（V2.1 案 75＋劉勝賢現行 +10，0724 對帳定稿）；SupPLA 系 60；其餘 30
        want = "85" if "PVA" in bn else ("60" if "SupPLA" in bn else "30")
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
    # DL1016（無實測值）與 Classic 前代機（Marlin，emit_machine_limits=0 另案）跳過。
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

    # 4b-5. ★ 冷卻降速統一：slow_down_layer_time（最大風扇臨界·每層列印時間）一律 10 秒
    #（Eric 2026-07-18 裁「擴及所有材料」，原預設 5 與 FF 7/基底 2~8 特調一併統一）。
    #
    # 🔴 **slow_down_for_layer_cooling 1 → 0（Eric 2026-08-07 裁・翻 0718 自己那條）**
    # 原話：「經過實測，所有材料的這個選項請取消打勾。它是在特殊情況下才需要進行勾選，
    #        因此大部分情況下都要取消。」
    # ⇒ ground truth＝實機實測，**不是疏漏、是有依據的翻案**；下一棒看到 0 不要「修正」回 1。
    # 引擎預設是 true（PrintConfig.cpp:1709 set_default_value true），所以必須每支明寫 0 才擋得住。
    # ⚠ `slow_down_layer_time` 維持 10 不動——那顆同時驅動「最大風扇速度臨界值」的風扇轉速插值，
    #    不是只驅動降速；Eric 只指名取消勾選那一格。
    CD_SLOWDOWN = ["0"]      # ← 要翻回開啟只改這一行
    cd_set = 0
    for fp_path in glob.glob(os.path.join(PINGDIR, "filament", "*.json")):
        fd = json.load(io.open(fp_path, encoding="utf-8"))
        if fd.get("slow_down_for_layer_cooling") == CD_SLOWDOWN and fd.get("slow_down_layer_time") == ["10"]:
            continue
        fd["slow_down_for_layer_cooling"] = list(CD_SLOWDOWN)
        fd["slow_down_layer_time"] = ["10"]
        jdump(fp_path, fd)
        cd_set += 1
    if cd_set:
        print("  冷卻降速統一（降速%s＋層時間 10 秒）：改 %d 支"
              % ("開" if CD_SLOWDOWN == ["1"] else "關", cd_set))


    # 4c. 封面（cover 以機型名解析——坑#11）：
    #     家族基本款=機器照片；單料頭/同進 模式卡=透明空白（2026-06-10 使用者定）；孤兒封面刪除
    # 每家族專屬照片（FD300 Pro 有自己的照片，勿沿用 FD300——取最長前綴匹配）
    cover_src = {"EDU 200":"FP300_cover.png", "PING 200":"FP300_cover.png",
                 "PING 270":"FP300_cover.png", "PING 300+":"FP300_cover.png",
                 "DUAL 300":"FD300_cover.png", "DUAL 450":"FD450 Pro_cover.png",
                 "DUAL 600":"FD600 Pro_cover.png", "DUAL 800":"FD800 Pro_cover.png",
                 "FD300 Pro":"FD300 Pro_cover.png","FD300":"FD300_cover.png",
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
        if model.endswith(("單料頭", "同進", "關門")):
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
    # 家族依 FAMS 順序，家族內：基本款 → 同進 → 3in1 → 單料頭。
    # 單料頭需要實際換噴頭，放最右以免和 FD300／同進的雙料硬體混在一起（Eric 2026-07-15）。
    # 關門＝FD300 的家族「變體」（排序面）：從 base 候選拿掉，否則精確自我匹配會把它
    # 當成獨立家族排在整個 FD300 家族之後，_variant_rank 的「關門」永遠輪不到。
    fam_bases = [f[1] for f in FAMS if not f[1].endswith("關門")]
    classic_bases = [s["name"] for s in CLASSIC_SPECS]
    # 關門插第三＝Eric 2026-07-26 指定家族順序 FD300／同進／關門／單料頭。
    _variant_rank = {"": 0, "同進": 1, "關門": 2, "3in1": 3, "單料頭": 4}
    def _lay11_key(entry):
        name = entry["name"]
        base = max((b for b in fam_bases if name == b or name.startswith(b + " ")), key=len, default=None)
        if base is None:
            # Classic 家族同樣做 base＋變體分解（0727 DUAL 補同進/單料頭）：
            # 本體 rank 0、變體照 _variant_rank ⇒ 家族內 本體→同進→單料頭，與 F 系同律（LAY-11）。
            cbase = max((b for b in classic_bases if name == b or name.startswith(b + " ")),
                        key=len, default=None)
            if cbase is not None:
                variant = name[len(cbase):].strip()
                return (len(fam_bases) + classic_bases.index(cbase), _variant_rank.get(variant, 9))
            return (len(fam_bases) + len(classic_bases), 9, name)   # 不明機型殿後
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
    # ★ ABS 整併（Eric 2026-07-25 裁「ABS 不需要 3 個，1 個就夠」・異常單 #37）：
    # 三支實測＝**溫度/床/風扇/purge 完全相同**（250/100/30·30/30）；`PING PolyABS` 與
    # `PING ABS` **葉檔逐鍵完全一致＝純副本**；`PING ABS - 250` 只因繼承鏈不同
    #（直接繼承 common、跳過 fdm_filament_abs）而多出流量比 0.98／最大流量 30／PA 0.12。
    # ⇒ 保留 `PING ABS` 並收編 ABS-250 的較佳值；另兩支移除，舊名走 renamed_from 相容
    #（Preset.cpp:2084 會拿舊名比對 system profile 的 renamed_from ⇒ 客戶既有 3mf 自動對應）。
    ABS_MERGED_AWAY = {"PING ABS - 250", "PING PolyABS"}
    # ★ 3in1 支口徑合一（Eric 2026-07-26 裁 C・統一值照 0.4/0.6）：六支 @FF 口徑別名併成
    # PLA(3in1)/SupPLA(3in1) 各一支、不綁機（0718 四料先例）。範本已收斂；此處清單過濾＋
    # 殘檔清除＝regen-durable，舊名走 renamed_from（⚠ 字串型別）相容。
    THREE_IN1_MERGED_AWAY = {"PING %s(3in1) @FF %s" % (_s, _nz)
                             for _s in ("PLA", "SupPLA") for _nz in ("0.4", "0.6", "1.0")}
    for _old in sorted(THREE_IN1_MERGED_AWAY):
        _p = os.path.join(PINGDIR, "filament", _old + ".json")
        if os.path.isfile(_p):
            os.remove(_p); print("  3in1 合一：移除殘檔", _old)
    # 0728 改名批：清單條目就地改指新名（保序＝最小 diff；後續 regen 舊名不存在＝no-op）
    # 基礎支（v1）＋TPE 本體（v2 二輪：改名帶溫度尾碼、SupTPE 名不動）
    _renamed_0728 = {BASE_PLA_OLD: BASE_PLA_NEW, "PING TPE": "PING TPE - 210"}
    for x in pj["filament_list"]:
        if x["name"] in _renamed_0728:
            x["name"] = _renamed_0728[x["name"]]
            x["sub_path"] = "filament/%s.json" % x["name"]
    pj["filament_list"] = [x for x in pj["filament_list"]
                           if x["name"] not in FF_FIL_RENAME and x["name"] not in ABS_MERGED_AWAY
                           and x["name"] not in THREE_IN1_MERGED_AWAY]
    have = {x["name"] for x in pj["filament_list"]}
    pj["filament_list"] += [x for x in (fil_new + ff_fil + classic_fil) if x["name"] not in have]
    # PING_ONLY 精簡：移除 FF 專用高流量線材（對單機客戶版無意義）——清 list ＋ 刪檔
    if PING_ONLY:
        pj["filament_list"] = [x for x in pj["filament_list"] if "@FF" not in x["name"]]
        for f in glob.glob(os.path.join(PINGDIR, "filament", "*@FF*.json")):
            os.remove(f)
    json.dump(pj, io.open(pj_path,"w",encoding="utf-8"), ensure_ascii=False, indent=4)

    # 4d-2. 預勾線材全族補齊（Eric 2026-08-07 裁）——必須排在 PING.json 重建**之後**，
    #        因為要吃最終的 filament_list／machine_list（含 ff_extra／照片磚／Classic 全部 emit
    #        完畢後的實況）。PING.json 本身不含 default_materials，故不需回寫。
    apply_default_materials(pj)

    # 4e. ★ 預擠點升溫 post-pass——【2026-07-20 Eric 裁回退・停用，勿重新接上】
    # start gcode 回到 header 升溫舊制（base 排放即舊制，停用後 regen 自然還原）；
    # 重新啟用前需「清噴頭」等機制配套驗證通過（見 apply_deferred_heating 註記）。

    print("\n產出: machine_model=%d machine=%d process=%d (+FF filament %d)，PING.json 已重建（版號請另行+1）"
          % (len(mm_list), gm, gp, len(fil_new)))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC)
