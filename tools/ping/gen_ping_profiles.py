# -*- coding: utf-8 -*-
"""Generate PING vendor profiles for OrcaSlicer (PING Slicer V3.5) — v2.
Incorporates PING切片參數整理.md: nozzle list (incl 1.0/0.25), layer-height rule
(lh=0.5*nozzle), material temp table, M6050 dual-material Start/End G-code, skeleton values.

PING printers: DELTA, circular bed, Klipper firmware (Moonraker host),
single-nozzle + dual-feed (single_extruder_multi_material, T0/T1 via M6050).

STILL PENDING confirmation: printable_height (delta Z) — flagged; prime E values need flow calibration.
"""
import os, json, math, shutil

REPO = r"D:\dev\2026claude\20260604 ORCA客製\PING-Slicer"
PROF = os.path.join(REPO, "resources", "profiles")
FLSUN = os.path.join(PROF, "FLSun")
PINGDIR = os.path.join(PROF, "PING")
STAGE = r"D:\dev\2026claude\20260604 ORCA客製\_staging\FD300_orca"
GD = r"G:\共用雲端硬碟\07 計劃案\01 關鍵技術\20250403 ORCA軟體客制"
TEX_SRC = GD + r"\客製資料\底板\ping_buildplate_texture.png"

# clean regen
if os.path.isdir(PINGDIR):
    shutil.rmtree(PINGDIR)
for sub in ("machine", "filament", "process"):
    os.makedirs(os.path.join(PINGDIR, sub), exist_ok=True)

# name, diameter(mm), height(mm EST/❓), nozzles, max_vel, max_accel
MODELS = [
    ("FD300",     300, 300, ["0.25", "0.4", "0.6", "1.0"], 400, 5000),
    ("FD300-Pro", 300, 300, ["0.25", "0.4", "0.6", "1.0"], 400, 5000),
    ("FP300",     300, 300, ["0.25", "0.4", "0.6", "1.0"], 400, 5000),
    ("FD450-Pro", 450, 450, ["0.25", "0.4", "0.6"],        400, 5000),
    ("FD600-Pro", 600, 600, ["0.4", "0.6", "1.0"],         400, 5000),
    ("FF600-Pro", 600, 600, ["0.4", "0.6", "1.0"],         400, 1500),
    ("FD800-Pro", 800, 800, ["0.4", "0.6", "1.0"],         250, 1500),
    ("FF800-Pro", 800, 800, ["0.4", "0.6", "1.0"],         250, 1500),
]
# per-nozzle: (layer_height, initial_layer_height, prime_line_E)  — 層高=0.5×口徑
NZ = {"0.25": (0.125, 0.15, 20), "0.4": (0.2, 0.25, 30),
      "0.6": (0.3, 0.35, 45), "1.0": (0.5, 0.55, 70)}
# material temp table (nozzle°C, bed°C, fan%)
MATS = [("PING Generic PLA", "fdm_filament_pla", 210, 60, 100),
        ("PING Generic PETG", "fdm_filament_pet", 235, 75, 50),
        ("PING Generic ABS", "fdm_filament_abs", 250, 100, 30),
        ("PING Generic PA-CF", "fdm_filament_pa", 255, 70, 30)]


def circle(R, n=72):
    return ["%gx%g" % (round(R*math.cos(2*math.pi*i/n), 4), round(R*math.sin(2*math.pi*i/n), 4)) for i in range(n)]


def start_gcode(R, z, E):
    """Dual-material (T0/T1) prime per PING M6050 spec. Y=-(R-10), 4 lines."""
    y = R - 10
    L = ["G28 ;Home", "G90", "M82",
         "M140 S[bed_temperature_initial_layer_single]",
         "M104 S[nozzle_temperature_initial_layer] T0",
         "M190 S[bed_temperature_initial_layer_single]",
         "M109 S[nozzle_temperature_initial_layer] T0"]
    seq = [("T0", "X-50", "X50"), ("T1", "X50", "X-50"), ("T0", "X-50", "X50"), ("T1", "X50", "X-50")]
    for k, (tool, a, b) in enumerate(seq):
        yy = -(y - 2*k)
        L += [tool, "G0 F8000 %s Y%g Z%g" % (a, yy, z), "G92 E0",
              "G1 F800 %s Y%g E%d" % (b, yy, E), "G92 E0"]
    L += ["G1 Z1 F1200", "G92 E0"]
    return "\n".join(L)


def end_gcode(R, h):
    y = R - 10
    ztop = max(50, int(h*0.8))
    return "\n".join([
        "M104 S240 ;heat to purge", "G91", "G1 Z10 F3000", "G90",
        "G1 X0 Y-%g Z%d F3000" % (y, ztop), "G91",
        "M6050 S0", "G1 E10 F60 ;purge feed-0",
        "M6050 S1", "G1 E10 F60 ;purge feed-1",
        "M6050 S0.5", "G1 E40 F60 ;dual purge",
        "G1 E-500 F12000 ;retract filament out of nozzle", "G4 S3",
        "M104 S0", "M140 S0", "G90", "G28 X0 Y0", "M84"])


def w(path, obj):
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=4)


# ---- copy base presets from FLSun ----
shutil.copyfile(os.path.join(FLSUN, "machine", "fdm_machine_common.json"), os.path.join(PINGDIR, "machine", "fdm_machine_common.json"))
shutil.copyfile(os.path.join(FLSUN, "process", "fdm_process_common.json"), os.path.join(PINGDIR, "process", "fdm_process_common.json"))
FIL_BASE = ["fdm_filament_common.json", "fdm_filament_pla.json", "fdm_filament_abs.json",
            "fdm_filament_pet.json", "fdm_filament_tpu.json", "fdm_filament_pa.json"]
for fn in FIL_BASE:
    s = os.path.join(FLSUN, "filament", fn)
    if os.path.exists(s):
        shutil.copyfile(s, os.path.join(PINGDIR, "filament", fn))
for fn in ["PING PolyABS.json", "PING SupABS.json"]:
    s = os.path.join(STAGE, "filament", fn)
    if os.path.exists(s):
        shutil.copyfile(s, os.path.join(PINGDIR, "filament", fn))
if os.path.exists(TEX_SRC):
    shutil.copyfile(TEX_SRC, os.path.join(PINGDIR, "ping_buildplate_texture.png"))

# ---- fdm_ping_common (machine base: klipper + Moonraker + skeleton retraction) ----
w(os.path.join(PINGDIR, "machine", "fdm_ping_common.json"), {
    "type": "machine", "name": "fdm_ping_common", "from": "system", "instantiation": "false",
    "inherits": "fdm_machine_common", "gcode_flavor": "klipper", "host_type": "octoprint",
    "use_relative_e_distances": "1", "single_extruder_multi_material": "1",
    "machine_pause_gcode": "PAUSE", "nozzle_type": "brass", "printer_structure": "delta",
    "z_hop": ["0.5"], "z_hop_types": ["Normal Lift"],
    "retraction_length": ["2"], "retraction_speed": ["20"], "deretraction_speed": ["20"],
    "retract_when_changing_layer": ["1"], "retraction_minimum_travel": ["1"], "wipe": ["0"],
    "extruder_clearance_radius": "65", "extruder_clearance_height_to_rod": "36",
    "extruder_clearance_height_to_lid": "140", "emit_machine_limits_to_gcode": "1",
    "thumbnails": "48x48/PNG,300x300/PNG", "thumbnails_format": "PNG",
    "default_filament_profile": ["PING Generic PLA"],
})

# ---- fdm_process_ping_common (process skeleton per spec) ----
w(os.path.join(PINGDIR, "process", "fdm_process_ping_common.json"), {
    "type": "process", "name": "fdm_process_ping_common", "from": "system", "instantiation": "false",
    "inherits": "fdm_process_common",
    "travel_speed": "250", "initial_layer_speed": "25",
    "sparse_infill_density": "15%", "sparse_infill_pattern": "zig-zag", "seam_position": "back",
    "support_threshold_angle": "60", "support_object_xy_distance": "0.3", "support_top_z_distance": "0",
    "support_interface_top_layers": "2", "enable_prime_tower": "1", "prime_tower_width": "35",
})

machine_models, machine_list, process_list = [], [
    {"name": "fdm_machine_common", "sub_path": "machine/fdm_machine_common.json"},
    {"name": "fdm_ping_common", "sub_path": "machine/fdm_ping_common.json"}], [
    {"name": "fdm_process_common", "sub_path": "process/fdm_process_common.json"},
    {"name": "fdm_process_ping_common", "sub_path": "process/fdm_process_ping_common.json"}]
all_machines = []
DEF_MAT = "PING Generic PLA;PING Generic PETG;PING Generic ABS;PING Generic PA-CF;PING PolyABS;PING SupABS"
gm = gp = 1

for (model, dia, hgt, nozzles, mv, ma) in MODELS:
    R = dia/2.0
    mm = "PING " + model
    machine_models.append({"name": mm, "sub_path": "machine/%s.json" % mm})
    w(os.path.join(PINGDIR, "machine", "%s.json" % mm), {
        "type": "machine_model", "name": mm, "model_id": "PING_" + model.replace("-", "_"),
        "nozzle_diameter": ";".join(nozzles), "machine_tech": "FFF", "family": "PING",
        "bed_model": "", "bed_texture": "ping_buildplate_texture.png", "hotend_model": "",
        "default_materials": DEF_MAT})
    area = circle(R)
    for nz in nozzles:
        lh, ilh, E = NZ[nz]
        mname = "PING %s %s nozzle" % (model, nz)
        pname = "%gmm Standard @PING %s (%s)" % (lh, model, nz)
        all_machines.append(mname)
        machine_list.append({"name": mname, "sub_path": "machine/%s.json" % mname})
        w(os.path.join(PINGDIR, "machine", "%s.json" % mname), {
            "type": "machine", "name": mname, "from": "system", "instantiation": "true",
            "setting_id": "PINGM%03d" % gm, "inherits": "fdm_ping_common",
            "printer_model": mm, "printer_variant": nz, "default_print_profile": pname,
            "nozzle_diameter": [nz], "printable_area": area, "printable_height": str(hgt),
            "bed_exclude_area": ["0x0"],
            "machine_start_gcode": start_gcode(R, ilh, E), "machine_end_gcode": end_gcode(R, hgt),
            "machine_max_speed_x": [str(mv), str(mv)], "machine_max_speed_y": [str(mv), str(mv)],
            "machine_max_speed_z": ["20", "20"], "machine_max_speed_e": ["30", "30"],
            "machine_max_acceleration_x": [str(ma), str(ma)], "machine_max_acceleration_y": [str(ma), str(ma)],
            "machine_max_acceleration_z": ["500", "500"], "machine_max_acceleration_e": ["5000", "5000"],
            "machine_max_acceleration_extruding": [str(ma), str(ma)],
            "machine_max_acceleration_travel": [str(ma), str(ma)],
            "machine_max_acceleration_retracting": ["5000", "5000"],
            "machine_max_jerk_x": ["9", "9"], "machine_max_jerk_y": ["9", "9"],
            "machine_max_jerk_z": ["0.2", "0.4"], "machine_max_jerk_e": ["2.5", "2.5"]})
        gm += 1
        process_list.append({"name": pname, "sub_path": "process/%s.json" % pname})
        w(os.path.join(PINGDIR, "process", "%s.json" % pname), {
            "type": "process", "name": pname, "from": "system", "instantiation": "true",
            "setting_id": "PINGP%03d" % gp, "inherits": "fdm_process_ping_common",
            "layer_height": str(lh), "initial_layer_print_height": str(ilh),
            "line_width": str(nz), "compatible_printers": [mname]})
        gp += 1

# ---- filaments (real temps) ----
filament_list = [{"name": "fdm_filament_common", "sub_path": "filament/fdm_filament_common.json"}]
for fn in FIL_BASE[1:]:
    filament_list.append({"name": fn.replace(".json", ""), "sub_path": "filament/" + fn})
gf = 1
for (nm, base, nt, bt, fan) in MATS:
    fp = "filament/%s.json" % nm
    filament_list.append({"name": nm, "sub_path": fp})
    w(os.path.join(PINGDIR, fp), {
        "type": "filament", "name": nm, "from": "system", "instantiation": "true",
        "setting_id": "PINGF%03d" % gf, "filament_id": "GPING%02d" % gf, "inherits": base, "filament_vendor": ["PING"],
        "nozzle_temperature": [str(nt), str(nt)], "nozzle_temperature_initial_layer": [str(nt), str(nt)],
        "hot_plate_temp": [str(bt), str(bt)], "hot_plate_temp_initial_layer": [str(bt), str(bt)],
        "fan_max_speed": [str(fan), str(fan)],
        "compatible_printers": all_machines})
    gf += 1
for nm, sid, ftype in [("PING PolyABS", "PINGF005", None), ("PING SupABS", "PINGF006", "HIPS")]:
    fp = os.path.join(PINGDIR, "filament", nm + ".json")
    if os.path.exists(fp):
        d = json.load(open(fp, encoding="utf-8"))
        d.update({"inherits": "fdm_filament_abs", "from": "system", "instantiation": "true",
                  "setting_id": sid, "filament_id": "GPING" + sid[-2:], "filament_vendor": ["PING"],
                  "compatible_printers": all_machines})
        d.pop("version", None)
        if ftype:
            d["filament_type"] = [ftype]
        w(fp, d)
        filament_list.append({"name": nm, "sub_path": "filament/%s.json" % nm})

w(os.path.join(PROF, "PING.json"), {
    "name": "PING", "version": "01.00.00.00", "force_update": "0",
    "description": "PING 3D Printer (LINKIN FACTORY) delta printers",
    "machine_model_list": machine_models, "process_list": process_list,
    "filament_list": filament_list, "machine_list": machine_list})

print("models:", len(machine_models), "machines:", len(all_machines),
      "processes:", len(process_list), "filaments:", len(filament_list))
print("DONE")
