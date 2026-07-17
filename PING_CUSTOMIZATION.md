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

## 1. 品牌外觀 / Branding  ✅

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
| `src/libslic3r/libslic3r.h` | `SLIC3R_APP_FULL_NAME` `Orca Slicer` → `PING Slicer`（About/對話框/錯誤訊息 86 處） |
| **配色** `src/**` + `resources/web/**`（35+ 檔） | OrcaSlicer 青綠色階 → PING 橘色階 **62 處**：`#009688`→`#EA4E16`、hover `#26A69A`→`#F26C3D`、按鈕/圖示色塊 `#52c7b8`→`#EA4E16`、淺底 `#BFE1DE`/`#E5F0EE`→淺橘、暗色模式 `#223C3C`→暗橘、web hover/首頁。**保留語意色**（GCode/線材調色盤、Google 登入圖示、座標軸色） |
| `resources/images/splash_logo.png` / `_dark.png` + `GUI_App.cpp` | 最終 welcome-screen 圖（內含品牌 + AGPL 合規版權文字）；SplashScreen 700×450；版本「**V3.5**」**白字**置於圖中「Pro Slicer」右側（像素對位 x=22.4% / y=52.7%） |
| `src/slic3r/GUI/AboutDialog.cpp` + `PING_about.png`/`_dark.png` | About logo → PING（CIS logo_compact）；版權 → LINKIN FACTORY（**保留 OrcaSlicer 版權 + 傳承段落 + Portions copyright**）；連結 → ping3dp.com + GitHub 源碼 |

**待辦 / TODO**
- [ ] 上方工具列 title logo `OrcaSlicerTitle.png` / `OrcaSlicer_154_title.png`（需 PING 橫式 wordmark）
- [ ] 停用/改指向 PING 的自動更新器（`check_new_version_sf`）
- [ ] Mac `.app` bundle 名與 dmg 檔名

## 2. 介面預設值 / Defaults  ✅
- ✅ 預設語言 zh_TW（`GUI_App.cpp` `load_language()`：首次啟動無設定時預設繁中）。
- ✅ 繁中翻譯目錄：`CMakeLists.txt` L761 `.mo` 檔名用 `${SLIC3R_APP_KEY}` → build 產 `PINGSlicer.mo`（修「app 找 PINGSlicer.mo、檔卻叫 OrcaSlicer.mo」→ 原生選單英文 fallback）。
- ✅ wizard 不顯示多餘「PING Family」：machine_model `family` 清空（橘色廠商徽章保留）。
- ✅ 雙噴頭機型預設 **2 線材槽**：`nozzle_diameter`=進料數 + SEMM=1 + offset 0x0（2 進 1 出共用 1 實體噴頭，G-code 正確）；FF 四噴頭=4 槽、FP 單噴頭=1 槽。
- ✅ web 簡中→繁中：`resources/web/data/text.js` `TranslatePage()` zh_CN→zh_TW 重導。
- ✅ 另存系統列印參數時，副本預設名稱去掉 ` @機型 (口徑)`，例如 `0.2mm PLA+SUP - 複製`；機器／線材等其他預設維持原命名。

## 3. PING 機型 profiles + 圓盤底板 / Profiles  ✅ (v4, 原廠確認 + Orca 驗證底稿校準)
- `resources/profiles/PING.json` + `PING/{machine,filament,process}/`，以內建 **FLSun delta** 為範本。
- 一般製程採保守運動值：稀疏填充加速度 **5000**、空駛加速度 **5000**、接縫位置 **對齊 (`aligned`)**；照片磚維持獨立特調 **10000／3000／`back`**。
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

## 4. 移除 Bambu 雲端 / Remove Bambu cloud  ✅
全部於 `src/slic3r/GUI/GUI_App.cpp`，採「UI early-return + 不載入外掛」最小侵入法（保留抽象層與內建 LAN 代理，編譯安全）：
- `show_network_plugin_download_dialog()`、`ShowDownNetPluginDlg()` → early-return：不跳「安裝/下載 Bambu Network 外掛」。
- `ShowUserLogin()` → early-return：移除 Bambu 帳號登入框（v2.3.2 上游已移除帳號鈕/模型商城選單）。
- `has_model_mall()` → `return false`：隱藏 Bambu/MakerWorld 模型商城。
- `on_init_network()`：`should_load_networking_plugin` 強制 `false` → 永不載入閉源 `BambuNetwork` DLL、不連 Bambu（走「無外掛」優雅路徑，`m_agent=null` 上游已全程 `if(m_agent)` 保護）。
- **合規**：不打包/不下載 Bambu 閉源外掛（無散布授權）。**LAN 送印不受影響**：Moonraker/Octoprint 走內建 PrintHost，非 Bambu 外掛。

## 5. 文件 / Docs  ✅
- ✅ `PING_CLOUD_PLAN.md`（Bambu 架構解析 + PING 圖庫/生產列印件方案 + Moonraker 路徑）。
- ✅ `PING_CUSTOMIZATION.md`（本檔，AGPL 修改紀錄）。
- ✅ About 框標註「Based on OrcaSlicer」+ 源碼連結（AGPL §13）+ 保留上游傳承段落與 Portions copyright。

## 6. 線材槽數同步（native）2026-06-10
- `src/slic3r/GUI/Tab.cpp::select_preset`：切換印表機後，線材槽數一律同步為該機 `default_filament_profile` 數量（FP=1/FD=2/FF=4），修「慢一拍」（Orca `remember_printer_config` 快照還原會沿用前一台槽數）。
- `src/slic3r/GUI/GUI_App.cpp::load_current_presets`：PING SEMM 槽數初始化由「只增不減」改「完全同步」。
- ⬜ 未 build（湊 B5 一次 build）。

## 7. wizard 連動真因修正（native）2026-06-10
- `src/slic3r/GUI/WebGuideDialog.cpp::save_userguide_models`：
  1. 機型比對由 `wxString`（隱式依系統 locale 轉碼，含中文 UTF-8 名在 CP950 轉換失敗成空字串→任兩中文名相等）改為 `std::string` 位元組比對——修「勾任一 單料頭/同進 → 所有含中文機型跨家族連動」（先前誤判為前綴比對，去空格實驗無效的真正原因）。
  2. `nozzle_selected` 改用 JS 送來的「實際勾選口徑清單」——修「勾一口徑 → 該機全部口徑被啟用」。
- ⬜ 未 build（湊 B5 一次 build）。

## 8. B7 批次（native）2026-06-10
- `PhysicalPrinterDialog.cpp`：①另存實體設備預設名＝機型名(printer_model)，取代「{preset} - 複製」；②主機類型清單只留 Octo/Klipper(host_type 一律 htOctoPrint)；③設備代理只留 Moonraker(id 防呆過濾)。
- `MsgDialog.cpp`：品牌 logo 對話框 64→40、錯誤框 84→48（左上角小標誌，不當主視覺）。
- splash 去背 v2：`SplashLayered` 介面改收 wxImage、`GUI_App.cpp render_layered()` 全程 wxImage 合成（v1 經 MemoryDC 的 ConvertToImage 丟 alpha＝黑底真因）；文字以取樣底色之不透明貼片蓋上。
- `utils.cpp`：gcode 頁首改「OrcaSlicer 2.3.2 (PING Slicer …)」開頭（Moonraker regex 識別）。
