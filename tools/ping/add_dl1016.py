#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DL1016（Dowell 大機，XY 笛卡爾 1000×1600×600）嵌入器——讀廠商三個 .3mf 注入 PING 目錄。

※ DL1016 是第三方機（非 PING delta），Eric 裁定（2026-06-15）：
   「放 PING 機型清單、但只進本機 portable、不上 build release」。
   → 本腳本**只注入本機 portable ＋ %APPDATA%**，**不碰 repo 的 resources**
     （repo 通用版 PING.json 不含 DL1016、build release 乾淨）。
   → 換新 portable（每次發版換裝）後**重跑本腳本**即可重新注入。

廠商來源：G:\\...\\20260529 Dowell 大機電路圖\\DL1016-6-{0.8,1.2,1.6}mm-PLA.3mf
  Orca 2.3.2 格式（project_settings.config）；XY 矩形床、單噴頭、2.85mm PLA、Klipper。

用法：python tools/ping/add_dl1016.py
"""
import zipfile, glob, json, io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embed_params import split, jdump   # 重用 Orca key 權威分類 + JSON 寫出

DOWELL = glob.glob(r"G:\我的雲端硬碟\2026claude\20260529 Dowell*")[0]
TARGETS = [
    r"D:\PING-Slicer-portable\resources\profiles",
    os.path.join(os.environ["APPDATA"], "PINGSlicer", "system"),
]


def bump(v):
    parts = v.split(".")
    parts[-1] = "%02d" % (int(parts[-1]) + 1)
    return ".".join(parts)


def make_cover(path, label):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (600, 600), (239, 239, 239, 255))   # PING Cool Gray 底
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 560, 560], outline=(234, 78, 22, 255), width=6)  # Raised Orange 框
    d.text((230, 285), label, fill=(32, 34, 33, 255))           # Charcoal 文字
    im.save(path)


def make_thumb(path):
    if not os.path.isdir(os.path.dirname(path)):
        return   # %APPDATA%\system 無 images 目錄；縮圖 app 從 portable resources/images 讀，跳過
    from PIL import Image
    Image.new("RGBA", (240, 240), (239, 239, 239, 255)).save(path)


def gen_dl1016():
    """讀三個 .3mf → (machine_model, machines[], processes[], filaments[])"""
    machines, processes, filaments, nzs = [], [], [], []
    for i, p in enumerate(sorted(glob.glob(os.path.join(DOWELL, "*.3mf"))), 1):
        d = json.loads(zipfile.ZipFile(p).read("Metadata/project_settings.config").decode("utf-8"))
        nz = d["nozzle_diameter"][0]
        nzs.append(nz)
        lh = d.get("layer_height", "0.2")
        b = split(d)   # 拆 M(machine)/P(process)/F(filament)，權威分類
        mac_name = "DL1016 %s nozzle" % nz
        proc_name = "%smm @DL1016 (%s)" % (lh, nz)
        fil_name = "DL1016 PLA (%s)" % nz
        mac = dict(b["M"]); mac.update({
            "type": "machine", "name": mac_name, "from": "system", "instantiation": "true",
            "setting_id": "DLM%03d" % i, "printer_model": "DL1016", "printer_variant": nz,
            "inherits": "fdm_machine_common", "alias": "DL1016",
            "default_print_profile": proc_name, "default_filament_profile": [fil_name]})
        machines.append((mac_name, mac))
        proc = dict(b["P"]); proc.update({
            "type": "process", "name": proc_name, "from": "system", "instantiation": "true",
            "setting_id": "DLP%03d" % i, "inherits": "fdm_process_common",
            "compatible_printers": [mac_name]})
        processes.append((proc_name, proc))
        fil = dict(b["F"]); fil.update({   # 2.85mm PLA（廠商「点维」值原樣保留）
            "type": "filament", "name": fil_name, "from": "system", "instantiation": "true",
            "setting_id": "DLF%03d" % i, "filament_id": "DLF%03d" % i,
            "inherits": "fdm_filament_common", "compatible_printers": [mac_name]})
        filaments.append((fil_name, fil))
    mm = {"type": "machine_model", "name": "DL1016", "model_id": "PING_DL1016",
          "nozzle_diameter": ";".join(nzs), "machine_tech": "FFF", "family": "",
          "bed_model": "", "bed_texture": "", "hotend_model": "",   # 無床 STL → Orca 依 printable_area 畫矩形
          "default_materials": ";".join("DL1016 PLA (%s)" % n for n in nzs)}
    return mm, machines, processes, filaments


def inject(prof_dir, mm, machines, processes, filaments):
    pj_path = os.path.join(prof_dir, "PING.json")
    if not os.path.isfile(pj_path):
        print("  !! 跳過(無 PING.json):", prof_dir); return
    ping_dir = os.path.join(prof_dir, "PING")
    for name, obj in machines:
        jdump(os.path.join(ping_dir, "machine", "%s.json" % name), obj)
    for name, obj in processes:
        jdump(os.path.join(ping_dir, "process", "%s.json" % name), obj)
    for name, obj in filaments:
        jdump(os.path.join(ping_dir, "filament", "%s.json" % name), obj)
    jdump(os.path.join(ping_dir, "machine", "DL1016.json"), mm)
    make_cover(os.path.join(ping_dir, "DL1016_cover.png"), "DL1016")
    make_thumb(os.path.join(prof_dir, "..", "images", "printer_preview_PING_DL1016.png"))
    pj = json.load(io.open(pj_path, encoding="utf-8"))
    added = [0]

    def add(lst, name, sub):
        if not any(x["name"] == name for x in lst):
            lst.append({"name": name, "sub_path": sub}); added[0] += 1
    add(pj["machine_model_list"], "DL1016", "machine/DL1016.json")
    for name, _ in machines:
        add(pj["machine_list"], name, "machine/%s.json" % name)
    for name, _ in processes:
        add(pj["process_list"], name, "process/%s.json" % name)
    for name, _ in filaments:
        add(pj["filament_list"], name, "filament/%s.json" % name)
    if added[0]:   # 冪等：只在真的有新增時 +version（重跑不亂跳）
        pj["version"] = bump(pj["version"])
        json.dump(pj, io.open(pj_path, "w", encoding="utf-8"), ensure_ascii=False, indent=4)
    print("  注入完成:", prof_dir, "→ PING.json v%s（新增 %d 項）" % (pj["version"], added[0]))


if __name__ == "__main__":
    mm, machines, processes, filaments = gen_dl1016()
    print("DL1016：機台 %d / 製程 %d / 線材 %d（口徑 %s）"
          % (len(machines), len(processes), len(filaments), mm["nozzle_diameter"]))
    for t in TARGETS:
        inject(t, mm, machines, processes, filaments)
