"""列印時間估計監測：每 30s 記錄 duration/file progress/M73，驗證時間爆炸根因。

用法：python monitor_print_time.py [host] [分鐘數]
列印開始後自動記錄；輸出 CSV 到 stdout＋彙總判讀。
"""
import json
import sys
import time
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.0.169"
MINUTES = float(sys.argv[2]) if len(sys.argv) > 2 else 40


def q(path):
    return json.load(urllib.request.urlopen(HOST + path, timeout=5))["result"]


meta_cache = {}

print("time,state,duration_s,file_progress_%,m73_progress_%,file_extrap_min,slicer_est_min")
end = time.time() + MINUTES * 60
seen_printing = False
while time.time() < end:
    try:
        st = q("/printer/objects/query?print_stats&display_status&virtual_sdcard")["status"]
        ps, ds, vs = st["print_stats"], st["display_status"], st["virtual_sdcard"]
        state = ps["state"]
        fn = ps["filename"]
        est = ""
        if fn and fn not in meta_cache:
            try:
                m = q("/server/files/metadata?filename=" + urllib.request.quote(fn))
                meta_cache[fn] = round((m.get("estimated_time") or 0) / 60, 1)
            except Exception:
                meta_cache[fn] = ""
        est = meta_cache.get(fn, "")
        dur, prog = ps["print_duration"], vs["progress"]
        extrap = round(dur / prog / 60, 1) if prog > 0.0005 else "INF"
        print(f"{time.strftime('%H:%M:%S')},{state},{round(dur,1)},{round(prog*100,2)},{round(ds['progress']*100,1)},{extrap},{est}", flush=True)
        if state == "printing":
            seen_printing = True
        elif seen_printing and state in ("complete", "cancelled", "error"):
            print(f"# 列印結束（{state}），停止記錄", flush=True)
            break
    except Exception as e:
        print(f"# poll error: {e}", flush=True)
    time.sleep(30)
