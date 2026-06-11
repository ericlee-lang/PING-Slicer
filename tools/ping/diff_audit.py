"""一次性：regen 後 git diff 審計——統計所有 JSON key 的變化模式，揪出非預期覆寫"""
import collections
import io
import json
import subprocess

REPO = r"D:\dev\2026claude\20260604 ORCA客製\PING-Slicer"

files = subprocess.run(
    ["git", "-C", REPO, "diff", "--name-only", "--", "resources/profiles/PING"],
    capture_output=True).stdout.decode("utf-8").splitlines()

changes = collections.Counter()   # (key, old→new) -> count
for rel in files:
    if not rel.endswith(".json"):
        continue
    old_raw = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{rel}"],
                             capture_output=True).stdout.decode("utf-8")
    try:
        old = json.loads(old_raw)
    except Exception:
        old = {}
    try:
        new = json.load(io.open(f"{REPO}\\{rel}", encoding="utf-8"))
    except Exception:
        continue
    for k in set(old) | set(new):
        ov, nv = old.get(k), new.get(k)
        if ov != nv:
            changes[(k, f"{ov} -> {nv}")] += 1

for (k, delta), c in sorted(changes.items()):
    print(f"{c:4d}x  {k}: {delta}")
