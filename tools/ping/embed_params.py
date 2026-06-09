#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PING 參數嵌入器 / param embedder
吃「參數人員」產出的 Orca project_settings.config（扁平化完整設定）
→ 依 OrcaSlicer 權威分類拆成 machine / process / filament 預設
→ 寫進 resources/profiles/PING/ 並更新 PING.json

用法（從 repo 根目錄）：
    python tools/ping/embed_params.py "<定稿資料夾>"  [機型]
目前支援 FD300（3 模式：雙料 PLA+SUP / 單噴頭 / 兩進一出，× 3 口徑）。
"""
import re, json, glob, os, sys, io

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PINGDIR = os.path.join(REPO, "resources", "profiles", "PING")
PRESET_CPP = os.path.join(REPO, "src", "libslic3r", "Preset.cpp")

# ---------- 1. OrcaSlicer 權威 key 分類 ----------
_src = open(PRESET_CPP, encoding="utf-8", errors="ignore").read()
def _ex(v):
    m = re.search(r"s_Preset_%s_options\s*\{(.*?)\n\}" % v, _src, re.S)
    return set(re.findall(r'"([a-zA-Z_][a-zA-Z0-9_]*)"', m.group(1))) if m else set()
PROC, FILA, MACH = _ex("print"), _ex("filament"), _ex("printer")
# printer_options() 還 append s_Preset_machine_limits_options(machine_max_*) 與 nozzle_options(per-extruder)；
# 前者在此補抽，後者(retraction/wipe/z_hop…)由下方 FORCE_M 涵蓋。這些 key 同時列於 filament_options(per-filament 覆寫)。
MACH |= _ex("machine_limits")

SKIP = {"from","name","version","inherits_group","different_settings_to_system",
        "print_settings_id","printer_settings_id","filament_settings_id",
        "print_compatible_printers","is_custom_defined"}
# 未列於權威清單、需手動歸類者：
FORCE_M = {"deretraction_speed","extruder_colour","extruder_offset","max_layer_height",
    "min_layer_height","nozzle_diameter","retract_before_wipe","retract_length_toolchange",
    "retract_lift_above","retract_lift_below","retract_restart_extra","retract_restart_extra_toolchange",
    "retract_when_changing_layer","retraction_length","retraction_minimum_travel","retraction_speed",
    "wipe","wipe_distance","z_hop","start_end_points","default_filament_profile",
    "flush_volumes_matrix","flush_volumes_vector","flush_multiplier","filament_colors",
    "default_filament_colors","filament_ids"}
FORCE_P = {"Each_layer_prime_tower","first_layer_print_sequence","other_layers_print_sequence",
    "other_layers_print_sequence_nums","overhang_speed_classic","has_scarf_joint_seam",
    "rotate_solid_infill_direction","tree_support_adaptive_layer_height",
    "tree_support_branch_diameter_double_wall","wipe_tower_x","wipe_tower_y",
    "layer_height","slice_closing_radius","filename_format"}

def cat(k):
    if k in SKIP: return None
    if k in FORCE_M: return "M"
    if k in FORCE_P: return "P"
    if k in MACH and k not in PROC: return "M"   # 機台優先於 filament（machine_max_*/per-extruder 與 filament 重疊時歸機台）
    if k in FILA and k not in PROC: return "F"
    if k in PROC: return "P"
    return "P"   # 預設歸 process（process 為最大宗）

def split(cfg):
    b = {"M":{}, "P":{}, "F":{}}
    for k,v in cfg.items():
        c = cat(k)
        if c: b[c][k] = v
    return b

# ---------- 2. 機型/模式定義 ----------
# (filename mode token) -> (machine_model 名稱, feeds)
MODELS = {
    "FD300": {
        "bed_model":"PING_FD300_buildplate_model.stl", "bed_texture":"ping_buildplate_texture.png",
        "cover":"FD300_cover.png", "nozzles":["0.25","0.4","0.6"],
        "default_materials":"PING PLA;PING SUP;PING PolyABS;PING SupABS;PING PETG;PING ABS;PING PA-CF",
        "modes":[
            ("PLA+SUP",  "FD300",        2),   # 雙料
            ("單噴頭",    "FD300 單料頭",  1),   # 單料頭（檔名 token = 非 PLA+SUP / 非 single）
            ("single",   "FD300 同進",  1),   # 同進 兩進一出 M6050 S0.5（標配口徑 0.4）
        ],
    },
}

def fil_at(cfg_F, idx, feeds):
    """從扁平 filament 區取第 idx 槽 → 單槽 filament 預設值"""
    out = {}
    for k,v in cfg_F.items():
        if isinstance(v, list) and len(v) == feeds:
            out[k] = [v[idx]]
        elif isinstance(v, list) and len(v) > idx:
            out[k] = [v[idx]]
        else:
            out[k] = v
    return out

def jdump(path, obj):
    json.dump(obj, io.open(path,"w",encoding="utf-8"), ensure_ascii=False, indent=4)

# ---------- 3. 主流程 ----------
def main(src_folder, model_key="FD300"):
    M = MODELS[model_key]
    # 清掉舊的同機型 machine/process 檔（避免孤兒）
    for p in (glob.glob(os.path.join(PINGDIR,"machine","%s*.json"%model_key)) +
              glob.glob(os.path.join(PINGDIR,"process","*@%s*.json"%model_key))):
        os.remove(p)
    configs = {}  # (nozzle, mode_token) -> dict
    for f in glob.glob(os.path.join(src_folder, "%s_*_project_settings.config" % model_key)):
        base = os.path.basename(f).replace("%s_"%model_key,"").replace("_project_settings.config","")
        # base 形如 "0.4_PLA+SUP" / "0.4_single_PLA" / "0.4_單噴頭_PLA"
        nozzle = base.split("_")[0]
        rest = base[len(nozzle)+1:]
        if rest.startswith("PLA+SUP"): mode="PLA+SUP"
        elif rest.startswith("single"): mode="single"
        else: mode="單噴頭"
        configs[(nozzle,mode)] = json.load(open(f,encoding="utf-8"))
    print("讀入 %d 個定稿 config" % len(configs))

    gm = gp = gf = 0
    mm_list, mac_list, proc_list, fil_list = [], [], [], []

    # 3a. filament 預設：取雙料(PLA+SUP)任一口徑，槽0=PLA、槽1=SUP
    dual = None
    for (nz,mode),c in configs.items():
        if mode=="PLA+SUP": dual=c; break
    fil_presets = []
    if dual:
        bF = split(dual)["F"]
        # SUP 用既有 PING SupPLA(PETG/210)、ABS 用既有 PING ABS-250，皆不在此新建；只從 dual slot0 萃 PLA-220
        for idx,(nm,fid) in enumerate([("PING PLA - 220","PINGFILPLA220")]):
            fp = fil_at(bF, idx, 2)
            fp.update({"type":"filament","name":nm,"from":"system","instantiation":"true",
                  "setting_id":fid,"filament_id":fid,"inherits":"fdm_filament_common"})
            jdump(os.path.join(PINGDIR,"filament","%s.json"%nm), fp)
            fil_list.append({"name":nm,"sub_path":"filament/%s.json"%nm}); gf+=1
    DEF_FIL = {2:["PING PLA - 220","PING SupPLA"], 1:["PING PLA - 220"]}

    # 3b. 每模式 → machine_model + 各口徑 machine/process
    for mode_token, model_name, feeds in M["modes"]:
        mm = {"type":"machine_model","name":model_name,
              "model_id":"PING_"+model_name.replace(" ","_"),
              "nozzle_diameter":";".join(M["nozzles"]),"machine_tech":"FFF","family":"",
              "bed_model":M["bed_model"],"bed_texture":M["bed_texture"],"hotend_model":"",
              "default_materials":M["default_materials"]}
        jdump(os.path.join(PINGDIR,"machine","%s.json"%model_name), mm)
        mm_list.append({"name":model_name,"sub_path":"machine/%s.json"%model_name})

        for nz in M["nozzles"]:
            c = configs.get((nz,mode_token))
            if not c:
                print("  ! 缺 config:", nz, mode_token); continue
            b = split(c)
            lh = c.get("layer_height","0.2")
            mac_name = "%s %s nozzle" % (model_name, nz)
            proc_name = "%smm @%s (%s)" % (lh, model_name, nz)
            # machine 預設（自包含 M keys + 身分）
            mac = dict(b["M"])
            mac.update({"type":"machine","name":mac_name,"from":"system","instantiation":"true",
                   "setting_id":"PINGM%03d"%gm,"printer_model":model_name,"printer_variant":nz,
                   "default_print_profile":proc_name,"default_filament_profile":DEF_FIL[feeds],
                   # alias=機型名 → active 標籤顯示乾淨名(無口徑)；口徑走噴嘴 chip(printer_variant)
                   "alias":model_name})
            # 註：nozzle_diameter / single_extruder_multi_material 沿用參數人員 .config 原值。
            # 「選機自動跳 N 槽」需 single_extruder_multi_material=0（GUI_App.cpp:7104 的 ORCA gate），
            # 但那會改變多材料 G-code 模型，且 change_filament_gcode 目前為空 → 屬參數/硬體人員的多材料架構決定。
            jdump(os.path.join(PINGDIR,"machine","%s.json"%mac_name), mac)
            mac_list.append({"name":mac_name,"sub_path":"machine/%s.json"%mac_name}); gm+=1
            # process 預設（自包含 P keys + 綁機台）
            # inherits 必須指向有效父 preset：OrcaSlicer 載 vendor config 時看「有無 inherits key」，
            # 寫 "" 會被當成「找名為空字串的父項」→ can not find inherits → 整包 PING vendor 載入中止。
            proc = dict(b["P"])
            # 列印加速度規範(2026-06-07)：300機(FD300/FP300)=3000、450+=1500；travel兩者皆3000。
            # 覆寫定稿原值(5000)，與 gen_ping_profiles.py 一致。
            pacc = "3000" if model_key in ("FD300", "FP300") else "1500"
            proc.update({"type":"process","name":proc_name,"from":"system","instantiation":"true",
                    "setting_id":"PINGP%03d"%gp,"inherits":"fdm_process_ping_common","compatible_printers":[mac_name],
                    "default_acceleration":pacc,"outer_wall_acceleration":pacc,
                    "inner_wall_acceleration":pacc,"travel_acceleration":"3000",
                    # Scarf 斜接縫(隱形 Z 接縫)：外牆/起始高10%/長度8mm。注:Orca 2.3.2 無 "scarf slope gap" key。
                    "seam_slope_type":"external","has_scarf_joint_seam":"1",
                    "seam_slope_start_height":"10%","seam_slope_min_length":"8"})
            jdump(os.path.join(PINGDIR,"process","%s.json"%proc_name), proc)
            proc_list.append({"name":proc_name,"sub_path":"process/%s.json"%proc_name}); gp+=1

    print("產出: machine_model=%d machine=%d process=%d filament=%d"%(len(mm_list),gm,gp,gf))
    return mm_list, mac_list, proc_list, fil_list

def wire_ping_json(mm_list, mac_list, proc_list, fil_list, model_key="FD300"):
    pj_path = os.path.join(REPO,"resources","profiles","PING.json")
    pj = json.load(open(pj_path,encoding="utf-8"))
    def merge(sec, new, match):
        newnames = {x["name"] for x in new}
        pj[sec] = [x for x in pj.get(sec,[]) if not match(x["name"]) and x["name"] not in newnames] + new
    merge("machine_model_list", mm_list, lambda n: n==model_key or n.startswith(model_key+" "))
    merge("machine_list",       mac_list, lambda n: n.startswith(model_key))
    merge("process_list",       proc_list, lambda n: ("@"+model_key) in n)
    merge("filament_list",      fil_list, lambda n: False)
    json.dump(pj, io.open(pj_path,"w",encoding="utf-8"), ensure_ascii=False, indent=4)
    print("PING.json 已更新: machine_model=%d machine=%d process=%d filament=%d"%(
        len(pj["machine_model_list"]),len(pj["machine_list"]),len(pj["process_list"]),len(pj["filament_list"])))

if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv)>1 else glob.glob(r"G:\*\2026claude\*\orca_fd300_*")[0]
    lists = main(folder)
    wire_ping_json(*lists)
