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
import re, json, os, sys, io, shutil

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PINGDIR = os.path.join(REPO, "resources", "profiles", "PING")
PROF = os.path.join(REPO, "resources", "profiles")
PRESET_CPP = os.path.join(REPO, "src", "libslic3r", "Preset.cpp")
DEFAULT_SRC = r"G:\我的雲端硬碟\2026claude\20260603 切片參數\PING Slicer V3.5\F系列參數"

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
# 資安版 E 機型（FD300 E / FD300 E Pro / FP300 E）不上 slicer 精靈——2026-06-10 使用者定
# （畫面太滿；參數端交付 config 保留，要上架時加回 FAMS 即可）
DEF_FIL_DUAL   = ["PING PLA - 220", "PING SupPLA"]
DEF_FIL_SINGLE = ["PING PLA - 220"]
def def_fil_ff(nz):
    return ["PING PLA - 高流量 @FF %s" % nz]*3 + ["PING SupPLA - 高流量 @FF %s" % nz]
DEFAULT_MATERIALS_FD = ("PING PLA - 220;PING SupPLA;PING ABS - 250;PING PLA;"
                        "PING PolyABS;PING SupABS;PING PETG;PING ABS;PING PA-CF")
BED = ("PING_FD300_buildplate_model.stl", "ping_buildplate_texture.png")

def tier_of(base):
    return "300" if base.startswith(("FD300","FP300")) else "450"

def proc_overrides(kind, base, is_single_mode):
    """軟體端裁定值 override（FF 不套——加速度/scarf 未裁定，維持實機）"""
    if kind == "ff": return {}
    acc = "3000" if tier_of(base) == "300" else "1500"
    o = {"default_acceleration": acc, "inner_wall_acceleration": acc,
         "outer_wall_acceleration": acc, "travel_acceleration": "3000",
         # Scarf 斜接縫(§8)：2.3.2 以 seam_slope_type=external 啟用（無 has_scarf key）
         "seam_slope_type": "external", "seam_slope_start_height": "10%",
         "seam_slope_min_length": "8"}
    if is_single_mode:
        # 單料頭/同進/FP 源檔 PA-CF 殘值 → 對齊雙料母檔(2026-06-10 裁定)
        o.update({"travel_speed": "250", "sparse_infill_speed": "60", "support_speed": "40"})
    return o

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
        if   rest.startswith("PLA+SUP"): mode = "dual"
        elif rest.startswith("單料頭"):   mode = "單料頭"
        elif rest.startswith("同進"):     mode = "同進"
        elif rest.startswith("四色"):     mode = "四色"
        else: continue   # PLA+PLA / ABS+SUP / ABS+ABS：線材組合，不產機台/製程
        out[(nozzle, mode)] = json.load(io.open(os.path.join(d, fn), encoding="utf-8"))
    return out

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

    for dirname, base, kind in FAMS:
        cfgs = parse_dir(src_base, dirname)
        if kind == "dual":
            modes = [("dual", base, DEF_FIL_DUAL, False),
                     ("單料頭", base + " 單料頭", DEF_FIL_SINGLE, True),
                     ("同進",   base + " 同進",   DEF_FIL_SINGLE, True)]
        elif kind == "single":
            modes = [("單料頭", base, DEF_FIL_SINGLE, True)]
        else:
            modes = [("四色", base, None, False)]

        for mode_key, model, def_fil, is_single in modes:
            nzs = sorted({nz for (nz, mk) in cfgs if mk == mode_key}, key=float)
            if not nzs:
                print("  !! %s 缺 %s config" % (dirname, mode_key)); continue
            nozzles_of[model] = nzs
            for nz in nzs:
                c = cfgs[(nz, mode_key)]
                b = split(c)
                lh = c.get("layer_height", "0.2")
                mac_name  = "%s %s nozzle" % (model, nz)
                proc_name = "%smm @%s (%s)" % (lh, model, nz)
                # machine
                mac = dict(b["M"])
                mac.update({"type":"machine","name":mac_name,"from":"system","instantiation":"true",
                    "setting_id":"PINGM%03d"%gm,"printer_model":model,"printer_variant":nz,
                    "default_print_profile":proc_name,
                    # alias=機型名 → active 標籤顯示乾淨名；口徑走噴嘴 chip(printer_variant)
                    "alias":model})
                mac["default_filament_profile"] = def_fil if def_fil else def_fil_ff(nz)
                jdump(os.path.join(PINGDIR,"machine","%s.json"%mac_name), mac)
                mac_list.append({"name":mac_name,"sub_path":"machine/%s.json"%mac_name}); gm += 1
                # process（inherits 必須指向存在父 preset，絕不可空字串——坑#12）
                proc = dict(b["P"])
                proc.update(proc_overrides(kind, base, is_single))
                proc.update({"type":"process","name":proc_name,"from":"system","instantiation":"true",
                    "setting_id":"PINGP%03d"%gp,"inherits":"fdm_process_ping_common",
                    "compatible_printers":[mac_name]})
                jdump(os.path.join(PINGDIR,"process","%s.json"%proc_name), proc)
                proc_list.append({"name":proc_name,"sub_path":"process/%s.json"%proc_name}); gp += 1

            # machine_model（每個 printer_model 一檔）
            mm = {"type":"machine_model","name":model,
                  "model_id":"PING_"+model.replace(" ","_"),
                  "nozzle_diameter":";".join(nzs),"machine_tech":"FFF","family":"",
                  "bed_model":BED[0],"bed_texture":BED[1],"hotend_model":"",
                  "default_materials": (";".join(def_fil_ff(nzs[0]) + def_fil_ff(nzs[-1]))
                                        if kind=="ff" else DEFAULT_MATERIALS_FD)}
            jdump(os.path.join(PINGDIR,"machine","%s.json"%model), mm)
            mm_list.append({"name":model,"sub_path":"machine/%s.json"%model})

    # 4b. FF 高流量線材子 preset（口徑別；FF600/FF800 共用，已驗證同值）
    fil_new = []
    ff800 = parse_dir(src_base, "FF800 Pro")
    ff_machines = lambda nz: ["FF600 %s nozzle"%nz, "FF800 %s nozzle"%nz]
    for nz in sorted({n for (n,mk) in ff800 if mk=="四色"}, key=float):
        F = split(ff800[(nz,"四色")])["F"]
        sfx = nz.replace(".","")   # 0.6 -> 06
        for slot, mat, fid_p, alias, color, sup in (
                (0, "PLA",    "PINGFILHFPLA", "PING PLA - 高流量",    "#EA4E16", False),
                (3, "SupPLA", "PINGFILHFSUP", "PING SupPLA - 高流量", "#808080", True)):
            fp = fil_at(F, slot, 4)
            name = "%s @FF %s" % (alias, nz)
            fid = fid_p + sfx
            fp.update({"type":"filament","name":name,"alias":alias,"from":"system",
                "instantiation":"true","setting_id":fid,"filament_id":fid,
                "inherits":"fdm_filament_pla","compatible_printers":ff_machines(nz),
                "filament_colors":[color],"default_filament_colors":[color]})
            if sup: fp["filament_is_support"] = ["1"]
            # 清洗量維持實機 120（FF 換色需大量清洗；FD 的 30/60 規則不適用，待裁定）
            jdump(os.path.join(PINGDIR,"filament","%s.json"%name), fp)
            fil_new.append({"name":name,"sub_path":"filament/%s.json"%name})

    # 4c. 封面（cover 以機型名解析——坑#11）：
    #     家族基本款=機器照片；單料頭/同進 模式卡=透明空白（2026-06-10 使用者定）；孤兒封面刪除
    # 每家族專屬照片（FD300 Pro 有自己的照片，勿沿用 FD300——取最長前綴匹配）
    cover_src = {"FD300 Pro":"FD300 Pro_cover.png","FD300":"FD300_cover.png","FP300":"FP300_cover.png",
                 "FD450":"FD450 Pro_cover.png","FD600":"FD600 Pro_cover.png",
                 "FD800":"FD800 Pro_cover.png","FF600":"FF600_cover.png","FF800":"FF800_cover.png"}
    def blank_png(path):
        from PIL import Image
        Image.new("RGBA", (600, 600), (0, 0, 0, 0)).save(path)
    for f in os.listdir(PINGDIR):           # 刪除不屬於現役機型的封面
        if f.endswith("_cover.png") and f[:-len("_cover.png")] not in nozzles_of:
            os.remove(os.path.join(PINGDIR, f)); print("  cover 移除(孤兒):", f)
    for model in nozzles_of:
        dst = os.path.join(PINGDIR, "%s_cover.png" % model)
        if model.endswith(("單料頭", "同進")):
            blank_png(dst)                   # 模式卡固定空白（每次重生覆寫，確保不殘留照片）
        elif not os.path.exists(dst):
            key = max((k for k in cover_src if model.startswith(k)), key=len)
            shutil.copy2(os.path.join(PINGDIR, cover_src[key]), dst)
            print("  cover: %s_cover.png <- %s" % (model, cover_src[key]))

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
    have = {x["name"] for x in pj["filament_list"]}
    pj["filament_list"] += [x for x in fil_new if x["name"] not in have]
    json.dump(pj, io.open(pj_path,"w",encoding="utf-8"), ensure_ascii=False, indent=4)
    print("\n產出: machine_model=%d machine=%d process=%d (+FF filament %d)，PING.json 已重建（版號請另行+1）"
          % (len(mm_list), gm, gp, len(fil_new)))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC)
