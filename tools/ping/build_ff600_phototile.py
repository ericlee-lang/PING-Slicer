# -*- coding: utf-8 -*-
"""建 FF600 同進照片磚母版（Eric 2026-08-05 令「四料沒有機器可以試，請幫我建一下」）。

做法＝SOP_加機型 §2 步驟 1「先 diff 一台已知可用的同類機型當範本」：
  範本＝FF800 同進照片磚（已在版、已出貨、已知可用）
  差異＝從「FF800 同進 vs FF600 同進」這對已知正確的一般機型 diff 出來，原樣套用。
**所有 FF600 專屬值都從 FF600 同進的實檔取，不手打**——手打就是臆測。

SOP 遵守點：
  §2.6 照片磚機 single_extruder_multi_material 必須 = 1（否則 default_filament_profile 的 64 槽
       不生效、選機後只長 2 槽）→ 本腳本 assert，不通過就中止。
  §2.5 FF800 同進的 T5 曾造成 GCodeProcessor 索引越界閃退 → 本腳本 assert start_gcode 內零 T 指令。
  §3  PINGM###/PINGP### 由 embed_params.emit_phototile 統一重編，母版裡的值不承重。

跑法：python tools/ping/build_ff600_phototile.py            （只檢查、不寫檔）
      python tools/ping/build_ff600_phototile.py --write    （實際產出母版）
"""
import json, io, os, re, shutil, argparse, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PT = os.path.join(HERE, "base", "phototile")
APPDATA = os.path.join(os.environ["APPDATA"], "PingSlicer", "system", "PING", "machine")
NOZZLES = ["0.4", "0.6", "1.0"]
# 照片磚製程檔名：層高隨口徑（沿用 FF800 既有命名）
PROC_LH = {"0.4": "0.25mm", "0.6": "0.35mm", "1.0": "0.45mm"}


def load(p):
    return json.load(io.open(p, encoding="utf-8"))


def dump(p, d):
    io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=4) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    problems = []

    # ── 1. 取「FF800→FF600」的權威差異：從已知正確的一般同進機實檔取，不手打 ──────
    ff600_ref = {}
    for nz in NOZZLES:
        f6 = os.path.join(APPDATA, "FF600 同進 %s nozzle.json" % nz)
        f8 = os.path.join(APPDATA, "FF800 同進 %s nozzle.json" % nz)
        if not (os.path.exists(f6) and os.path.exists(f8)):
            problems.append("缺參照機型：%s 或 %s" % (f6, f8))
            continue
        d6, d8 = load(f6), load(f8)
        ff600_ref[nz] = {
            "printable_area":     d6["printable_area"],
            "printable_height":   d6["printable_height"],
            "machine_start_gcode": d6["machine_start_gcode"],
        }
        # 照片磚的 start_gcode 應與同型號一般同進機相同（0.4 已實測 0 行差異）——逐口徑複驗
        pt8 = os.path.join(PT, "machine", "FF800 同進照片磚 %s nozzle.json" % nz)
        if os.path.exists(pt8):
            if load(pt8)["machine_start_gcode"] != d8["machine_start_gcode"]:
                problems.append("⚠ FF800 照片磚 %s 的 start_gcode 與 FF800 同進不同 ⇒ "
                                "「照片磚沿用同進 start_gcode」的前提在此口徑不成立，不可照套" % nz)

    # ── 2. machine_model ────────────────────────────────────────────────────
    src_mm = load(os.path.join(PT, "machine", "FF800 同進照片磚.json"))
    ref600_mm = load(os.path.join(APPDATA, "FF600 同進.json"))
    mm = dict(src_mm)
    mm["name"] = "FF600 同進照片磚"
    mm["model_id"] = "PING_FF600_tongjin_phototile"
    mm["bed_model"] = ref600_mm["bed_model"]          # FD800→FD600 床模型，取實檔不手打

    # ── 3. 三個口徑的機型檔 ──────────────────────────────────────────────────
    machines = {}
    for nz in NOZZLES:
        src = load(os.path.join(PT, "machine", "FF800 同進照片磚 %s nozzle.json" % nz))
        d = dict(src)
        d["name"] = "FF600 同進照片磚 %s nozzle" % nz
        d["alias"] = "FF600 同進照片磚"
        d["printer_model"] = "FF600 同進照片磚"
        d["default_print_profile"] = "%s @FF600 同進照片磚 (%s)" % (PROC_LH[nz], nz)
        if nz in ff600_ref:
            d.update(ff600_ref[nz])                    # 床形/高度/預擠線 一次套上
        # —— SOP 硬性檢查 ——
        if str(d.get("single_extruder_multi_material")) != "1":
            problems.append("SOP §2.6 違反：%s 的 single_extruder_multi_material != 1" % d["name"])
        tcmds = [l for l in d["machine_start_gcode"].split("\n") if re.match(r"^\s*T\d", l)]
        if tcmds:
            problems.append("SOP §2.5 風險：%s 的 start_gcode 含 T 指令 %s" % (d["name"], tcmds))
        if "FF800" in json.dumps(d, ensure_ascii=False):
            problems.append("殘留 FF800 字樣：%s" % d["name"])
        machines[d["name"]] = d

    # ── 4. 三支製程 ─────────────────────────────────────────────────────────
    procs = {}
    for nz in NOZZLES:
        src = load(os.path.join(PT, "process", "%s @FF800 同進照片磚 (%s).json" % (PROC_LH[nz], nz)))
        d = dict(src)
        d["name"] = "%s @FF600 同進照片磚 (%s)" % (PROC_LH[nz], nz)
        d["compatible_printers"] = ["FF600 同進照片磚 %s nozzle" % nz]
        if "FF800" in json.dumps(d, ensure_ascii=False):
            problems.append("殘留 FF800 字樣：%s" % d["name"])
        procs[d["name"]] = d

    # ── 5. 報告 ─────────────────────────────────────────────────────────────
    print("將產出：machine_model 1／機型 %d／製程 %d／cover 1" % (len(machines), len(procs)))
    for n in list(machines) + list(procs):
        print("   " + n)
    if problems:
        print("\n❌ 檢查未過（%d）：" % len(problems))
        for p in problems:
            print("   - " + p)
        sys.exit(1)
    print("\n✅ SOP 檢查全過（SEMM=1／start_gcode 零 T 指令／無 FF800 殘留）")

    if not a.write:
        print("（未加 --write，沒有寫任何檔）")
        return

    dump(os.path.join(PT, "machine", "FF600 同進照片磚.json"), mm)
    for n, d in machines.items():
        dump(os.path.join(PT, "machine", "%s.json" % n), d)
    for n, d in procs.items():
        dump(os.path.join(PT, "process", "%s.json" % n), d)
    shutil.copy2(os.path.join(PT, "cover", "FF800 同進照片磚_cover.png"),
                 os.path.join(PT, "cover", "FF600 同進照片磚_cover.png"))
    print("已寫入母版。⚠ 還要把新名字加進 embed_params.py 的 "
          "PHOTOTILE_MACHINES／PHOTOTILE_PROCS，然後重產。")


if __name__ == "__main__":
    main()
