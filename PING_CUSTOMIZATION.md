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

## 3. PING 機型 profiles + 圓盤底板 / Profiles  ✅ (v4, 原廠確認 + Orca 驗證底稿校準)
- `resources/profiles/PING.json` + `PING/{machine,filament,process}/`，以內建 **FLSun delta** 為範本。
- **7 款** delta 機型、**21 機器 / 23 process / 12 filament**（已過官方 C++ 驗證器）。
- **原廠確認規格**（高度為實際建構值，與直徑無關）：

  | 機型 | 類型(進料) | Ø | 高度Z | 噴頭 |
  |------|------|---|---|------|
  | FD300 | 雙料(2) | 300 | 270 | 0.25/0.4/0.6 |
  | FP300 | 高速·單料(1) | 300 | 270 | 0.2/0.4/0.6 |
  | FD450-Pro | 雙料(2) | 450 | 600 | 0.4/0.6/1.0 |
  | FD600-Pro | 雙料(2) | 600 | 580 | 0.4/0.6/1.0 |
  | FF600 | 高速·四料(4) | 600 | 580 | 0.4/0.6/1.0 |
  | FD800-Pro | 雙料(2) | 800 | 600 | 0.4/0.6/1.0 |
  | FF800 | 高速·四料(4) | 800 | 600 | 0.4/0.6/1.0 |

- 參數邏輯：**層高=0.5×口徑**；材料溫度 PLA 210/60/100、PETG 235/75/50、ABS 250/100/30、PA-CF 255/70/30。
- **Start/End G-code 依進料數分流**：單料(FP)=無 M6050 單線 prime；雙料(FD)=T0/T1 + `M6050 S0/S1/S0.5`；四料(FF)=T0~T3 + 各 M6050。prime 在 `Y=-(R-10)`，End 以 `E-500` 抽料。
- 骨架值：回抽 2/Z-hop 0.5、support 60°·xy0.3、travel 250、首層速 25、infill zig-zag 15%、seam back、prime tower。
- 圓形 `printable_area`、`gcode_flavor=klipper`、`host_type=octoprint`(Moonraker)、單噴頭多料(SEMM)。生成器：`tools/ping/gen_ping_profiles.py`。

> ⚠️ **仍需校準（非結構問題）**：prime 吐料 E 值（0.2≈16/0.25≈20/0.4≈30/0.6≈45/1.0≈70）與 End `E-500` 需依齒輪比流量實測；FF 四料的 M6050 細節待原廠確認。
> ✅ **已用 FD300 Orca 驗證底稿（495-key 母檔）校準**：回抽 1.3 / Z-hop 0.4 / firmware retraction；填充 **gyroid 15%**、牆 3 圈、上下殼 4 層/0.8、外牆速 60·加速 2000、內牆 60·5000；支撐 **tree(auto)·門檻 30°·z-distance 0.2**；prime tower 30·vol 45；filament PA 0.12；start gcode 末行對齊 `G1 Z1 E(prime-1)`。
> ⚠️ 仍需實切校準：prime 吐料 E 值（依齒輪比）、FF 四料 M6050 細節。

## 6. CI 修正 / Build fixes  ✅
- `build_appimage.sh.in`：Linux 圖示來源改既有檔（修打包失敗）。
- `build_orca.yml`：Windows 安裝檔上傳 glob → `PING_Slicer*.exe`、輸出/artifact 改 PING 名、PDB 上傳 continue-on-error。
- `check_profiles.yml`：最終判定只看系統驗證（含 PING），不再因上游測試樣本誤報失敗（停掉 GitHub 失敗通知信）。
- ⬜ 待辦：Mac `.app` bundle 名與 dmg 檔名仍為 OrcaSlicer（需單獨小心處理）。

## 4. 移除 Bambu 雲端 / Remove Bambu cloud  ⬜ (todo)
- 停用網路外掛下載、隱藏帳號登入、首頁/模型庫中性化。**不打包 Bambu 閉源外掛**。

## 5. 文件 / Docs  🔶 (partial)
- ✅ `PING_CLOUD_PLAN.md`（Bambu 架構解析 + PING 圖庫/生產列印件方案 + Moonraker 路徑）。
- ✅ `PING_CUSTOMIZATION.md`（本檔，AGPL 修改紀錄）。
- ⬜ 關於頁/README 標註 based on OrcaSlicer + 源碼連結。
