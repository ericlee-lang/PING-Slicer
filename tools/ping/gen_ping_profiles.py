# -*- coding: utf-8 -*-
"""Generate PING vendor profiles for OrcaSlicer (PING Slicer V3.5).
All PING printers are DELTA with circular beds, Klipper firmware (Moonraker host).
Templated on the built-in FLSun delta vendor + the legacy PING FD300 .orca_printer.

NOTE: printable_height (delta Z) and nozzle availability are BEST-ESTIMATES pending
PING confirmation. Diameters derive from Klipper print_radius / model nominal size.
"""
import os, json, math, shutil

REPO = r"D:\dev\2026claude\20260604 ORCA客製\PING-Slicer"
PROF = os.path.join(REPO, "resources", "profiles")
FLSUN = os.path.join(PROF, "FLSun")
PINGDIR = os.path.join(PROF, "PING")
STAGE = r"D:\dev\2026claude\20260604 ORCA客製\_staging\FD300_orca"
GD = r"G:\共用雲端硬碟\07 計劃案\01 關鍵技術\20250403 ORCA軟體客制"
TEX_SRC = GD + r"\客製資料\底板\ping_buildplate_texture.png"

for sub in ("machine", "filament", "process"):
    os.makedirs(os.path.join(PINGDIR, sub), exist_ok=True)

# ---- model specs: name, diameter(mm), height(mm EST), nozzles, max_vel, max_accel, sqv ----
MODELS = [
    ("FD300",     300, 300, ["0.4", "0.6"],        400, 5000, 5),
    ("FD300-Pro", 300, 300, ["0.4", "0.6"],        400, 5000, 5),
    ("FP300",     300, 300, ["0.4", "0.6"],        400, 5000, 5),
    ("FD450-Pro", 450, 450, ["0.4", "0.6"],        400, 5000, 5),   # FD450 specs interpolated
    ("FD600-Pro", 600, 600, ["0.4", "0.6", "0.8"], 400, 5000, 5),
    ("FF600-Pro", 600, 600, ["0.4", "0.6", "0.8"], 400, 1500, 5),
    ("FD800-Pro", 800, 800, ["0.4", "0.6", "0.8"], 250, 1500, 40),
    ("FF800-Pro", 800, 800, ["0.4", "0.6", "0.8"], 250, 1500, 40),
]

# shared Klipper start/end gcode (from legacy PING FD300 .orca_printer — proven, dual-tool aware)
START_GCODE = ("G21\nG90\nM82\nM107 T0\n"
               "M140 S[bed_temperature_initial_layer_single]\n"
               "M104 S[nozzle_temperature_initial_layer] T0\n"
               "M190 S[bed_temperature_initial_layer_single]\n"
               "M109 S[nozzle_temperature_initial_layer] T0\n\n"
               "G28 ;Home\n"
               "G1 F3000 Z1\nG1 X-90 Y0 Z0.4\nG92 E0\n"
               "G3 X0 Y-90 I90 Z0.3 E20 F2000 ;prime arc\nG92 E0\n")
END_GCODE = ("M107 T0\nM104 S0\nM140 S0\nG92 E0\nG91\nG1 E-1 F300\n"
             "G1 Z+5 F6000\nG28\nG90 ;absolute positioning\nM84")


def circle(R, n=72):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append("%gx%g" % (round(R * math.cos(a), 4), round(R * math.sin(a), 4)))
    return pts


def w(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=4)


# ---- copy base presets from FLSun (each vendor ships its own copies) ----
copied = []
for fn in ["fdm_machine_common.json"]:
    shutil.copyfile(os.path.join(FLSUN, "machine", fn), os.path.join(PINGDIR, "machine", fn)); copied.append("machine/" + fn)
for fn in ["fdm_process_common.json"]:
    shutil.copyfile(os.path.join(FLSUN, "process", fn), os.path.join(PINGDIR, "process", fn)); copied.append("process/" + fn)
FIL_BASE = ["fdm_filament_common.json", "fdm_filament_pla.json", "fdm_filament_abs.json",
            "fdm_filament_pet.json", "fdm_filament_tpu.json", "fdm_filament_pa.json",
            "fdm_filament_asa.json", "fdm_filament_pc.json"]
for fn in FIL_BASE:
    src = os.path.join(FLSUN, "filament", fn)
    if os.path.exists(src):
        shutil.copyfile(src, os.path.join(PINGDIR, "filament", fn)); copied.append("filament/" + fn)

# ---- copy legacy PING materials from staging ----
for fn in ["PING PolyABS.json", "PING SupABS.json"]:
    s = os.path.join(STAGE, "filament", fn)
    if os.path.exists(s):
        shutil.copyfile(s, os.path.join(PINGDIR, "filament", fn)); copied.append("filament/" + fn)

# ---- copy bed texture ----
if os.path.exists(TEX_SRC):
    shutil.copyfile(TEX_SRC, os.path.join(PINGDIR, "ping_buildplate_texture.png")); copied.append("ping_buildplate_texture.png")

# ---- fdm_ping_common (machine base: klipper + Moonraker + retraction, from legacy PING) ----
ping_common = {
    "type": "machine", "name": "fdm_ping_common", "from": "system", "instantiation": "false",
    "inherits": "fdm_machine_common",
    "gcode_flavor": "klipper", "host_type": "octoprint",
    "use_relative_e_distances": "1", "single_extruder_multi_material": "1",
    "machine_start_gcode": START_GCODE, "machine_end_gcode": END_GCODE,
    "machine_pause_gcode": "PAUSE", "change_filament_gcode": "",
    "nozzle_type": "brass", "z_hop": ["0.4"], "z_hop_types": ["Normal Lift"],
    "retraction_length": ["1.3"], "retraction_speed": ["30"], "deretraction_speed": ["30"],
    "retract_when_changing_layer": ["1"], "retraction_minimum_travel": ["1"],
    "wipe": ["0"], "wipe_distance": ["1"], "retract_before_wipe": ["70%"],
    "extruder_clearance_radius": "65", "extruder_clearance_height_to_rod": "36",
    "extruder_clearance_height_to_lid": "140",
    "printer_structure": "delta",
    "thumbnails": "48x48/PNG,300x300/PNG", "thumbnails_format": "PNG",
    "emit_machine_limits_to_gcode": "1", "default_filament_profile": ["PING Generic PLA"],
}
w(os.path.join(PINGDIR, "machine", "fdm_ping_common.json"), ping_common)

# ---- generate per-model machine_model + machine(s) ----
gm = 1
machine_models = []
machine_list = [{"name": "fdm_machine_common", "sub_path": "machine/fdm_machine_common.json"},
                {"name": "fdm_ping_common", "sub_path": "machine/fdm_ping_common.json"}]
all_machine_names = []
DEF_MAT = "PING Generic PLA;PING Generic PETG;PING Generic ABS;PING PolyABS;PING SupABS;PING Generic TPU"

for (model, dia, hgt, nozzles, mv, ma, sqv) in MODELS:
    R = dia / 2.0
    mm_name = "PING " + model
    mm_file = "machine/%s.json" % mm_name
    machine_models.append({"name": mm_name, "sub_path": mm_file})
    w(os.path.join(PINGDIR, mm_file), {
        "type": "machine_model", "name": mm_name,
        "model_id": "PING_" + model.replace("-", "_"),
        "nozzle_diameter": ";".join(nozzles), "machine_tech": "FFF", "family": "PING",
        "bed_model": "", "bed_texture": "ping_buildplate_texture.png", "hotend_model": "",
        "default_materials": DEF_MAT,
    })
    area = circle(R)
    for nz in nozzles:
        m_name = "PING %s %s nozzle" % (model, nz)
        m_file = "machine/%s.json" % m_name
        all_machine_names.append(m_name)
        machine_list.append({"name": m_name, "sub_path": m_file})
        w(os.path.join(PINGDIR, m_file), {
            "type": "machine", "name": m_name, "from": "system", "instantiation": "true",
            "setting_id": "PINGM%03d" % gm, "inherits": "fdm_ping_common",
            "printer_model": mm_name, "printer_variant": nz,
            "default_print_profile": "0.20mm Standard @PING %s" % model,
            "nozzle_diameter": [nz],
            "printable_area": area, "printable_height": str(hgt),
            "bed_exclude_area": ["0x0"],
            "machine_max_speed_x": [str(mv), str(mv)], "machine_max_speed_y": [str(mv), str(mv)],
            "machine_max_speed_z": ["20", "20"], "machine_max_speed_e": ["30", "30"],
            "machine_max_acceleration_x": [str(ma), str(ma)], "machine_max_acceleration_y": [str(ma), str(ma)],
            "machine_max_acceleration_z": ["500", "500"], "machine_max_acceleration_e": ["5000", "5000"],
            "machine_max_acceleration_extruding": [str(ma), str(ma)],
            "machine_max_acceleration_travel": [str(ma), str(ma)],
            "machine_max_acceleration_retracting": ["5000", "5000"],
            "machine_max_jerk_x": ["9", "9"], "machine_max_jerk_y": ["9", "9"],
            "machine_max_jerk_z": ["0.2", "0.4"], "machine_max_jerk_e": ["2.5", "2.5"],
        })
        gm += 1

# ---- generate processes per model (Standard/Fine/Draft), compatible with that model's machines ----
process_list = [{"name": "fdm_process_common", "sub_path": "process/fdm_process_common.json"}]
LAYERS = [("0.12mm Fine", "0.12", "0.18"), ("0.20mm Standard", "0.2", "0.32"), ("0.28mm Draft", "0.28", "0.42")]
gp = 1
for (model, dia, hgt, nozzles, mv, ma, sqv) in MODELS:
    comp = ["PING %s %s nozzle" % (model, nz) for nz in nozzles]
    for (label, lh, lw) in LAYERS:
        p_name = "%s @PING %s" % (label, model)
        p_file = "process/%s.json" % p_name
        process_list.append({"name": p_name, "sub_path": p_file})
        w(os.path.join(PINGDIR, p_file), {
            "type": "process", "name": p_name, "from": "system", "instantiation": "true",
            "setting_id": "PINGP%03d" % gp, "inherits": "fdm_process_common",
            "layer_height": lh, "initial_layer_print_height": "0.25",
            "line_width": lw, "compatible_printers": comp,
        })
        gp += 1

# ---- PING generic filaments (inherit base, compatible with PING) ----
filament_list = [{"name": "fdm_filament_common", "sub_path": "filament/fdm_filament_common.json"}]
for fn in FIL_BASE[1:]:
    nm = fn.replace(".json", "")
    filament_list.append({"name": nm, "sub_path": "filament/" + fn})
GEN_FIL = [("PING Generic PLA", "fdm_filament_pla", "215", "60"),
           ("PING Generic PETG", "fdm_filament_pet", "240", "75"),
           ("PING Generic ABS", "fdm_filament_abs", "255", "90"),
           ("PING Generic TPU", "fdm_filament_tpu", "230", "35")]
gf = 1
for (nm, base, nt, bt) in GEN_FIL:
    fpath = "filament/%s.json" % nm
    filament_list.append({"name": nm, "sub_path": fpath})
    w(os.path.join(PINGDIR, fpath), {
        "type": "filament", "name": nm, "from": "system", "instantiation": "true",
        "setting_id": "PINGF%03d" % gf, "inherits": base,
        "filament_vendor": ["PING"],
        "nozzle_temperature": [nt, nt], "nozzle_temperature_initial_layer": [nt, nt],
        "hot_plate_temp": [bt, bt], "hot_plate_temp_initial_layer": [bt, bt],
        "compatible_printers": all_machine_names,
    })
    gf += 1
# legacy PING materials present as copied files
for nm in ["PING PolyABS", "PING SupABS"]:
    if os.path.exists(os.path.join(PINGDIR, "filament", nm + ".json")):
        filament_list.append({"name": nm, "sub_path": "filament/%s.json" % nm})

# ---- vendor index PING.json ----
w(os.path.join(PROF, "PING.json"), {
    "name": "PING", "version": "01.00.00.00", "force_update": "0",
    "description": "PING 3D Printer (LINKIN FACTORY) delta printers",
    "machine_model_list": machine_models,
    "process_list": process_list,
    "filament_list": filament_list,
    "machine_list": machine_list,
})

print("copied base files:", len(copied))
print("machine_models:", len(machine_models), "machines:", len(all_machine_names),
      "processes:", len(process_list), "filaments:", len(filament_list))
print("DONE")
