"""驗證 patch 後的 .mo：gettext 標準庫可讀 + 新舊翻譯都查得到"""
import gettext

base = r"D:\dev\2026claude\20260604 ORCA客製\PING-Slicer\resources\i18n\zh_TW"
for name in ("OrcaSlicer.mo", "PINGSlicer.mo"):
    with open(rf"{base}\{name}", "rb") as f:
        cat = gettext.GNUTranslations(f)
    new_label = cat.gettext("Purge idle filaments every")
    old1 = cat.gettext("Prime tower")
    old2 = cat.gettext("No sparse layers (beta)")
    old3 = cat.gettext("layers")
    print(name, "->", new_label, "|", old1, "|", old2, "|", old3)
    assert new_label == "閒置線材沖刷間隔"
    assert old1 == "換料塔"
    assert old3 == "層"
print("OK: .mo 格式正確、新舊翻譯齊全")
