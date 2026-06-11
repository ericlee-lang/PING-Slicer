"""一次性：把 process preset 的 filename_format 中文前綴包進字串字面值 {"X_"}。

PlaceholderParser 模板 rule 邊界（開頭、} 後）遇非 ASCII 即 throw；
字串字面值 lexeme 內中文合法。Mix 雖為 ASCII 也一併統一格式。
"""
import glob
import io
import json
import re

PROC = r"D:\dev\2026claude\20260604 ORCA客製\PING-Slicer\resources\profiles\PING\process\*.json"
PREFIX_RE = re.compile(r"^(雙色|易拆|單料|Mix|四色)_")

changed = 0
for p in sorted(glob.glob(PROC)):
    with io.open(p, encoding="utf-8") as f:
        d = json.load(f)
    fmt = d.get("filename_format")
    if not fmt:
        continue
    m = PREFIX_RE.match(fmt)
    if not m:
        print("skip (no prefix):", p.split("\\")[-1], "->", fmt)
        continue
    d["filename_format"] = '{"%s_"}' % m.group(1) + fmt[m.end():]
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=4)
        f.write("\n")
    changed += 1
print("changed:", changed)
