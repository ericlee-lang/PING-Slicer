# PING Slicer — 客製紀錄 / Customization Log

**PING Slicer** is a customized distribution of **[OrcaSlicer](https://github.com/SoftFever/OrcaSlicer)** (AGPL-3.0),
maintained by **PING 3D Printer (聯造實業 / LINKIN FACTORY Co., Ltd.)** for PING delta 3D printers.

- Base: OrcaSlicer **v2.3.2** (tag `v2.3.2`)
- License: **GNU AGPL-3.0** (unchanged — see `LICENSE.txt`). Source: https://github.com/ericlee-lang/PING-Slicer
- This file records every change made on top of upstream OrcaSlicer, as required by AGPL-3.0 §5
  ("carry prominent notices stating that you modified it").

> PING Slicer is **based on** OrcaSlicer. It is **not** the official OrcaSlicer and is not endorsed by the
> OrcaSlicer / SoftFever project. Trademarks belong to their respective owners.

---

## 1. 品牌外觀 / Branding  ✅ (in progress)

| 檔案 | 變更 |
|------|------|
| `version.inc` | `SLIC3R_APP_NAME` → `PING Slicer`；`SLIC3R_APP_KEY` → `PINGSlicer`；`SoftFever_VERSION` → `3.5.0` |
| `CMakeLists.txt` | CPack 套件名/廠商/檔名/描述/首頁/註冊表 key/捷徑→PING；Mac bundle id → `com.ping3dp.PINGSlicer`；`SLIC3R_APP_CMD` → `ping-slicer` |
| `src/CMakeLists.txt` | 執行檔 `OUTPUT_NAME` `orca-slicer` → `ping-slicer`（Win shim + Linux + symlink） |
| `src/dev-utils/platform/msw/OrcaSlicer.rc.in` | CompanyName→PING、OriginalFilename→`ping-slicer.exe`、LegalCopyright |
| `src/dev-utils/platform/unix/*.desktop` | Name/Exec/StartupWMClass → PING / ping-slicer |
| `src/slic3r/Utils/Process.cpp`、`BBLNetworkPlugin.cpp` | 重啟新實例的執行檔名 → `ping-slicer.exe` |
| `src/slic3r/GUI/DesktopIntegrationDialog.cpp` | StartupWMClass → ping-slicer |
| `src/OrcaSlicer.cpp` | CLI usage 字串 → ping-slicer |
| `resources/images/OrcaSlicer*.ico/.png/.icns` | 內容替換為 PING 圖示（**保留檔名**以免動到數十處引用） |

**待辦 / TODO**
- [ ] 啟動畫面 `splash_logo.svg` / `splash_logo_dark.svg`（需 PING 向量稿，目前仍為 Orca）
- [ ] 上方工具列 title logo `OrcaSlicerTitle.png` / `OrcaSlicer_154_title.png`（需 PING 橫式 wordmark）
- [ ] 關於頁背景 `OrcaSlicer_about*.svg`
- [ ] 停用/改指向 PING 的自動更新器
- [ ] Linux desktop 整合的 Name/Icon（`DesktopIntegrationDialog.cpp`）

## 2. 介面預設值 / Defaults  🔶 (partial)
- ✅ 預設語言 zh_TW（`GUI_App.cpp` `load_language()`：首次啟動無設定時預設繁中）。
- ⬜ 啟動精靈預設勾選 PING 廠商（待與移除 Bambu 一起改 `ConfigWizard.cpp`）。

## 3. PING 機型 profiles + 圓盤底板 / Profiles  ✅ (initial, 待規格確認)
- `resources/profiles/PING.json` + `PING/{machine,filament,process}/`，以內建 **FLSun delta** 為範本。
- 8 款 delta 機型（FD300 / FD300-Pro / FP300 / FD450-Pro / FD600-Pro / FF600-Pro / FD800-Pro / FF800-Pro），
  圓形 `printable_area`、`gcode_flavor=klipper`、`host_type=octoprint`(Moonraker)、PING start/end gcode。
- 20 個機器(含 0.4/0.6/0.8 噴頭變體)、24 個 process(Fine/Standard/Draft)、PING 材料(PolyABS/SupABS + Generic PLA/PETG/ABS/TPU)。
- 底板紋理 `ping_buildplate_texture.png`。生成器：`_staging/gen_ping_profiles.py`。

> ⚠️ **待 PING 確認的規格（目前為估計值）**：
> - **列印高度 printable_height**：FD300類=300、FD450=450、FD600=600、FD800=800（暫=直徑；FLSun V400 同直徑卻為 410，故務必確認）。
> - **噴頭尺寸**：300/450 類給 0.4/0.6；600/800 類給 0.4/0.6/0.8（需確認各機型實際供應）。
> - **FD450-Pro**：Klipper 設定本次讀不到，速度/半徑用內插值。
> - 直徑取自 Klipper print_radius／機型名義值（FD300→Ø300…FD800→Ø800）。

## 4. 移除 Bambu 雲端 / Remove Bambu cloud  ⬜ (todo)
- 停用網路外掛下載、隱藏帳號登入、首頁/模型庫中性化。**不打包 Bambu 閉源外掛**。

## 5. 文件 / Docs  🔶 (partial)
- ✅ `PING_CLOUD_PLAN.md`（Bambu 架構解析 + PING 圖庫/生產列印件方案 + Moonraker 路徑）。
- ✅ `PING_CUSTOMIZATION.md`（本檔，AGPL 修改紀錄）。
- ⬜ 關於頁/README 標註 based on OrcaSlicer + 源碼連結。
