# PING Slicer V3.5 — Session Hand-off ＆ 客製化指南

> 這份是「接手用」文件：給下一個 Session（或維護者）快速接續 + 避免重踩坑。
> 搭配 `PING_CUSTOMIZATION.md`（AGPL 修改紀錄）一起看。

---

## 0. 立即接續（上一個 Session 停在哪）

**正在做**：恢復設定精靈的「**每噴嘴勾選**」。
- 已把 3.0 的 `resources/web/guide/21/21.js` + `24/24.js`（每噴嘴版）複製覆蓋新版（Orca 簡化版），並同步到 `D:\PING-Slicer-portable`。
- **【已修・本 session】「選擇 3D 列印機」頁失效根因 = CSS，不是 JS**。只移植了 3.0 的 JS，CSS 卻留著新版 Orca 的，class 對不上：
  - `21.css`/`24.css` 的 `.pNozzel { display:none }`（新版改用圖上覆蓋勾選 `ModelCheckBox`）→ **每噴嘴勾選框被藏 → 看不到、無法選 → 頁面「失效」**。
  - 圖片縮放規則是 `img.ModelThumbnail{100%}`，但 3.0 JS 的 `<img>` **沒有 ModelThumbnail class** → 圖片以原圖尺寸渲染 → **爆大重疊**（截圖那樣）。
  - **修法**（保留 PING 橘＋深色模式，只補兩處）：`.pNozzel` 改 `display:flex`；新增 `.PImg img { width/height:100%; object-fit:contain }`。`21.css`/`24.css` 皆改，已同步 portable。
  - 註：失效截圖是 **guide/24**（App 內「確定/取消」對話框），非首次精靈 guide/21；兩頁同 bug、已一起修。翻譯 t11/12/13/38/39（全部/清空/mm 噴嘴/取消/確定）zh_TW 齊全。
- **CSS 修已驗證成功**：使用者重測，每噴嘴勾選框正常顯示、圖片大小正常、可勾選、可進到線材頁。✅

**【接著揪出第二個更深的 bug・已修・本 session】「勾得到機器卻載不到任何機器」（主畫面列印設備下拉空白）= 製程 profile 的 `inherits` 寫成空字串，害整包 PING vendor 載入中止。**
- 證據：`%APPDATA%\PINGSlicer\log\debug_*.log` →
  `PresetBundle::load_vendor_configs_from_json ... can not find inherits  for 0.125mm @FD300 (0.25)`。
- 機制（`PresetBundle.cpp` L4037-4068）：loader 看「JSON **有沒有 `inherits` key**」，不是值是否為空。`"inherits":""` 會被當成「找名為空字串的父 preset」→ 找不到 → **return 中止整個 vendor 載入** → 所有 PING 機器/製程/線材都不見。
- 根因：`tools/ping/embed_params.py` L157 產生 FD300 定稿製程時寫死 `"inherits":""`（其他機型骨架是 `fdm_process_ping_common`，所以只有 FD300 那 9 顆中毒）。
- **修法**（不動參數人員任何數值——定稿檔本來就是 283 鍵完整 config、child 永遠覆蓋 parent）：
  1. `embed_params.py` L157 `"inherits":""` → `"inherits":"fdm_process_ping_common"`（根治產生器）。
  2. repo `resources/profiles/PING/process/` 9 顆 FD300 檔同改。
  3. `PING.json` version `01.00.00.02`→`03`（坑 #4，強制重新複製）。
  4. 已同步：repo / portable `resources` / `%APPDATA%\PINGSlicer\system\PING`（三處 version=.03、0 空 inherits）。全 bundle 預檢通過（machine/process/filament inherits 全解析、instantiation/filament_id 齊全）。
- **inherits 修已驗證成功**：使用者重測，FD300/FP300/FD450 Pro 等機台 preset 真的載入、製程/線材帶出、參數可編輯。✅

**【再修兩個使用者回報問題・本 session】**

**問題 A：選 FD300（雙料）沒自動跳 2 卷線材（只 1 槽）。✅根因確定 + 原生 patch 已寫（待 build）。**
- **用 V3.0 匯出檔比對定案**（使用者提供 `G:\...\切片參數\V3.0\` 的 `.orca_printer` + `.3mf`）：V3.0 可用的 2 料 FD300 是 `nozzle_diameter=['0.4']`（1元素）+ `SEMM=1` + `default_filament_profile=2` + `change_filament_gcode=''`（**空**）+ `filament_settings_id=2`（=槽數來源）。**preset 結構 V3.5 與 V3.0 幾乎一模一樣**（差的鍵都與槽數無關）→ **不是 profile 問題**。
- **真正機制（坑#13）**：線材槽數 = 專案 `filament_settings_id` 數量，由選機時的初始化決定，**不是** nozzle_diameter（那段 `#if 0` 關掉了）。`GUI_App.cpp::load_current_presets` **L7104** 是 **Orca 2.3.2 原生**（commit `c724a3f5 bump 2.3.2`，非 PING 加的）：`if (ptFFF && !SEMM) set_num_filaments(nozzle數)`——**只對 SEMM=0 同步**。Orca 2.3.2 把 SEMM 機當 AMS 變動數量、不初始化；V3.0 舊版 Orca 會用 `default_filament_profile` 初始化 → 這是**版本行為差異**。
- **先前走錯路（已還原）**：依坑#9 把 nozzle 改 2 元素 → 無效（只觸發 `extruder_index 2` 錯誤）+ 誤判要改 SEMM=0/補換料 G-code。**全部假設作廢**：nozzle=1、SEMM=1、空 change_filament_gcode 都跟 V3.0 一樣是對的。已 git 還原機台檔與 embed_params.py（僅保留製程 inherits 修）。
- **修法（已套用・原生・併入下次 build 批次）**：`GUI_App.cpp` L7104 後加 `else if (ptFFF)` 分支——SEMM 機若 `default_filament_profile` 數量 > 目前線材數則 `set_num_filaments(default_filament_profile數)`。**只增不減**，還原 V3.0；FD→2槽、FF→4槽、FP→1槽。`ConfigOptionStrings`/`filament_presets` 在該檔已現成可用。
- 連帶：槽數變 2 後，製程 `support_filament=2` 變有效 → 「參數已變更」對話框自動消失。（V3.0 用 support_filament=1/interface=2，V3.5 用 2/2，屬參數人員數值差異，不影響功能。）
- 連帶：製程 `support_filament=2`（支撐用第2料）在只有 1 卷時無效 → 跳「參數已變更」對話框；槽數變 2 後自動消失。

**問題 B：第一次開啟程式沒載入機器 = 前次壞檔狀態殘留，非持續性 bug。**
- conf（`PINGSlicer.conf`）機器啟用清單存在 **`models`** 區段（非 `vendors`）；現已有 FD300/FD450 Pro/FP300，`firstguide.finish=true`、`presets.machine="FD300 0.6 nozzle"` → **往後開啟會自動載入 FD300**。
- 之所以「第一次沒機器」：壞檔那輪 vendor 載入失敗 → 作用機台停在 `Default Printer` + `firstguide.finish` 已被設 true（精靈不再自動跳）。修好 vendor + 手動選一次後即恢復。
- **全新安裝**現在 vendor 能載入、精靈跑完會帶機器，故不會重演。要乾淨重現驗證：清 `%APPDATA%\PINGSlicer`（**保留 OrcaFilamentLibrary**，坑 #2）→ 重開 → 精靈跑一次。

- **本 session 確定可 commit 的**：CSS（每噴嘴勾選+圖片尺寸，已驗證）+ 製程 inherits 修（vendor 載入，已驗證）+ embed_params.py inherits + PING.json version。**不含** nozzle_diameter（已還原）。
- **下一步（多材料）優先**：先請參數/硬體人員定 FD300 的 SEMM 模型 + 提供換料 G-code，再由軟體端 wire（改 SEMM/補 `change_filament_gcode`/必要時加 `extruder_variant_list` 消除 extruder_index 2 錯誤）。
- **其餘待辦**：① 樣式收尾（`SmallBtn_Green`「全部」鈕改橘）② 嵌入其他機型參數 ③ 線材只留 PING。
- **觀察項**：embed_params.py `M["modes"]`「FD300 兩進一出」設 feeds=1，與坑#9「2進1出=feeds 2」字面矛盾，待與參數人員對齊。`PING PLA - 220`/`PING SUP - 220` 是 FD300 預設線材但不在 conf filaments 可見清單（generic「PING PLA」在）。
- **次要待修**：`printer_preview_.png`（空機型 id）載圖失敗 → 某機型缺封面圖（log warning，不影響功能）。
- **若仍壞** → web JS/CSS 還原：`69b7c750`（含）之前 / 3.0 原版 `C:\Program Files\PING slicerV3.0\`；profile 還原見 git。

---

## 1. 關鍵位置

| 用途 | 路徑 |
|------|------|
| **repo（git）** | `D:\dev\2026claude\20260604 ORCA客製\PING-Slicer`，分支 `ping/v3.5`，remote `github.com/ericlee-lang/PING-Slicer`（gh 已登入 ericlee-lang）|
| **測試用 portable** | `D:\PING-Slicer-portable`（使用者只用這個，不安裝）|
| **參數人員規格/定稿** | `G:\我的雲端硬碟\2026claude\20260603 切片參數`（`orca_fd300_定稿\` 已用；`匯出_3mf\` 有各機型 .3mf；規格 MD 文件）|
| **3.0 參照安裝** | `C:\Program Files\PING slicerV3.0\`（每噴嘴 wizard、舊參數參照）|
| **設定快取** | `%APPDATA%\PINGSlicer`（= `C:\Users\ericl\AppData\Roaming\PINGSlicer`），清掉可強制全新啟動 |
| **轉換器** | `tools/ping/embed_params.py`（吃 .config → 生 profile）|
| **機型生成器** | `tools/ping/gen_ping_profiles.py`（骨架 profile）|

---

## 2. ⚠️ 踩過的坑（務必先讀，省幾小時）

1. **【最大坑】設定精靈是 WEB 網頁，不是原生 `ConfigWizard.cpp`。**
   「選擇 3D 列印機」「選擇線材」「Bambu 網路插件」這些頁面都在 **`resources/web/guide/`**（HTML/JS）。我一開始狂查原生 `ConfigWizard.cpp`（PrinterPicker/PagePrinters）找「PING 前綴」「插件頁」，全查錯地方——code 都對、畫面卻不對就是這原因。**動 wizard 一律先看 `resources/web/guide/`。**
   - 印表機卡片渲染：`guide/21/21.js` 與 `24/24.js` 的 `CreatePrinterBlock` / `HandleModelList`。
   - 卡片多餘「PING」＝ JS 印了 `<p>vendorName</p>`（不是機型名、不是 family）。
   - 「Bambu 網路插件」頁＝ `guide/5/index.html`（文字在 `resources/web/data/text.js` 的 t75/t65），由 `guide/4orca/4orca.js` 的 `GotoNetPluginPage()` 導入。

2. **`OrcaFilamentLibrary.json` 是啟動必需檔。** 移除非 PING 廠商時若把它一起刪 → 啟動崩潰（`Copying of OrcaFilamentLibrary.json ... failed`）。它 0 印表機 / 353 線材，**務必保留**。（也是「線材清單出現一堆非 PING 廠牌」的來源。）

3. **資源檔 vs 原生 code（決定要不要 build）：**
   - **資源檔（免 build，改完同步 portable 即可）**：`resources/profiles/**`、`resources/web/**`、`resources/images/**`、`resources/i18n/**/*.mo`。
   - **原生 code（要 CI build ~50min）**：`src/**/*.cpp/.hpp`、`version.inc`、`CMakeLists.txt`、`libslic3r.h`。
   - portable 的 `ping-slicer.exe` 是 binary，**只有 build 才會變**（改資源檔它不會動，這是正常的）。

4. **改 profile 後要把 `PING.json` 的 `version` +1**，否則 app 比對版本沒變、不會從 resources 重新複製到 `%APPDATA%\PINGSlicer\system`，你會看到舊的。

5. **繁中 `.mo` 檔名陷阱**：app（`SLIC3R_APP_KEY="PINGSlicer"`）找 `PINGSlicer.mo`，但 build 產出的是 `OrcaSlicer.mo` → 原生選單變英文。**暫解**：把每個 `resources/i18n/<lang>/OrcaSlicer.mo` 複製一份成 `PINGSlicer.mo`。**根治待辦**：CMakeLists L761 的 `.mo` 命名改 `${SLIC3R_APP_KEY}` 沒完全生效，build 仍產 OrcaSlicer.mo，需再查。

6. **嵌入參數人員 `.config` 的 key 分類**（machine/process/filament）：用 `Preset.cpp` 的權威清單 `s_Preset_print_options`/`s_Preset_filament_options`/`s_Preset_printer_options`。**坑**：`Preset::printer_options()` 還會 append `s_Preset_machine_limits_options`（`machine_max_*`）和 `nozzle_options()`（per-extruder retraction/wipe/z_hop）——這些**同時也列在 filament_options**，所以分類要「機台優先於 filament」，否則 `machine_max_*` 會被 filament 的 index-split 截斷成 1 元素。`embed_params.py` 已處理（`MACH |= _ex("machine_limits")` + cat() 機台優先）。

7. **wizard 選機器需要「每噴嘴」選取才會啟用 preset。** OrcaSlicer 機台 preset 是按噴嘴的（`FD300 0.4 nozzle`）。Orca 2.3.2 web wizard 簡化成「一個 model 勾選框」、退出只送機型名不送噴嘴 → 原生選不到 preset →「**勾了機器卻選不到機器**」。解法＝恢復 3.0 的每噴嘴勾選（`guide/21,24.js`）。原生 handler 在 `WebGuideDialog.cpp` 的 `save_userguide_models`（L425）。

8. **中文路徑會讓 bash/PowerShell 工具間歇亂碼。** 用 Python `glob`/`os.walk` 配 ASCII 萬用字元（`glob.glob(r"G:\*\2026claude\*")`）避免打中文，或先 `shutil.copy` 到 ASCII 暫存路徑再處理。

9. **PING「2 馬達 1 噴頭」（2 進 1 出）= `nozzle_diameter=[nz]*feeds`（FD=2）+ `single_extruder_multi_material=1` + `extruder_offset` 全 `0x0`。** 給「2 線材槽共用 1 實體噴頭」、2 進 1 出 G-code 正確。（先前以為設 2 會崩，其實崩潰是 OrcaFilamentLibrary 被刪，不是這個。）

10. **`build` 顯示 failure 常常只是 `Unit Tests` 那個 job 掛**（既有問題），**各平台編譯其實 success、安裝檔有產出**（artifacts）。別被紅 X 嚇到，去看各 job。

11. **封面圖的「PING」是真實產品照**（機台機身印的 logo，`FD300_cover.png` 等），web wizard 用 `OneModel['cover']` 載入。那個 PING 不是文字、要修圖才能改。

12. **【profile 致命坑】preset 的 `inherits` 寫成空字串 `""` 會讓整包 vendor 載入中止。** OrcaSlicer `PresetBundle.cpp::load_vendor_configs_from_json`（L4037）判斷的是「JSON **有沒有 `inherits` key**」，不是值是否為空：有 key 但值為 `""` → 去找名為空字串的父 preset → `can not find inherits` → **return 中止**，該 vendor 之後所有 preset 全部不載入（症狀：精靈勾得到機器，但主畫面列印設備下拉全空、`presets.machine` 退回 `Default Printer`、conf 無 `[vendors]`）。**規則**：preset 的 `inherits` 要嘛**整個 key 不要寫**（→ 用 Orca default base），要嘛指向**存在的父 preset**（製程用 `fdm_process_ping_common`、線材用 `fdm_filament_common`）；**絕不可留空字串**。`embed_params.py` 已修（L157）。診斷起手式：讀 `%APPDATA%\PINGSlicer\log\debug_*.log` 搜 `load_vendor_configs_from_json`。`machine_model` 型檔（machine_model_list 指向、`FD300.json` 等）不是 preset、本來就沒有 `inherits`/`instantiation`，別誤修。

---

## 3. ✅ 正確的客製化流程

1. **先判斷：這個改動是「資源檔」還是「原生 code」？**（見坑 #3 的清單）
   - 對話框文字/logo（About、splash 版本字）→ 原生（`AboutDialog.cpp`、`GUI_App.cpp`）。
   - 設定精靈（選機器/線材/插件頁）→ **WEB**（`resources/web/guide/`）。
   - 機型/製程/線材 profile → 資源（`resources/profiles/PING/`）。
   - 配色 → 兩邊：原生 `src/**/*.cpp` + web `resources/web/**/*.css/.js`。
   - App 名稱 → `version.inc`（APP_NAME/KEY）+ `libslic3r.h`（FULL_NAME）。
2. **資源檔改動**：在 repo 改 → `cp` 同步到 `D:\PING-Slicer-portable\resources\...` →（若動 profile，`PING.json` version +1）→ 重開 portable 測。**不 build。**
3. **原生改動**：改 `src/` → commit → 觸發 build：`gh workflow run "Build all" --ref ping/v3.5` → ~50min → 下載 portable artifact（見步驟 5）。
4. **嵌入參數定稿**：把 .config/.3mf 放好 → `python tools/ping/embed_params.py "<定稿資料夾>"` → 同步 portable。會驗證 round-trip（合併產出 == 定稿）。
5. **取 build 安裝檔/portable**：`gh run download <run_id> -R ericlee-lang/PING-Slicer -n PING_Slicer_Windows_V3.5.0_portable -D <dir>`；新 binary 要配最新資源（FD300 三模式參數在 build 之後的 commit），記得把 repo 的 `resources/profiles/PING` + `.mo`(複製成 PINGSlicer.mo) 疊上去。
6. **換完整版 portable**：app 完全關閉 → `mv D:\PING-Slicer-portable D:\...old`（鎖住會乾淨失敗）→ `mv 新portable D:\PING-Slicer-portable` → 清 `%APPDATA%\PINGSlicer`。

---

## 4. 目前進度

### ✅ 已完成（已 commit + push 到 ping/v3.5）
- 品牌：app 名稱 `PING Slicer`、splash（最終圖 + V3.5 白字、原生繪製層待最終定位）、About 框（PING logo + 版權 + 保留 OrcaSlicer 致謝 + 源碼連結）、配色青綠→PING 橘（src 62 處 + web）。
- 介面：預設繁中（`load_language`）、`.mo` 複製成 PINGSlicer.mo（portable）、web 簡中→繁中。
- 移除 Bambu：原生 `show_network_plugin_download_dialog`/`ShowUserLogin`/`has_model_mall` early-return + `should_load_networking_plugin=false`；web 插件頁跳過（`4orca.js`）。
- FD300 定稿參數：3 機台變體（雙料/單噴頭/兩進一出）× 3 口徑，machine+process 0 差異、雙料 100%；`embed_params.py` 轉換器。
- CI build：全平台編譯成功，安裝檔產出（run 27005916752）。
- web wizard：移除卡片「PING」前綴。

### ⬜ 待辦（接續）
1. **【測試中】每噴嘴勾選**（3.0 版 21/24.js 已複製）→ 等使用者確認；OK 後修樣式（綠鈕→橘）。
2. **嵌入其他機型參數**：`匯出_3mf\` 有 FD600/FF600/FF800/FP300 的 .3mf → 用 `embed_params.py` 套（先擴充它支援 .3mf 解壓 + 這些機型的模式）。
3. **線材只留 PING**：wizard 線材頁出現一堆 OrcaFilamentLibrary 廠牌；要過濾成只顯示 PING（查 web 線材頁 `guide/22` + 相容性）。
4. **`.mo` build 根治**：build 仍產 OrcaSlicer.mo（CMakeLists L761 未生效）。
5. **macOS bundle 名**仍是 OrcaSlicer；**自動更新器**停用（`check_new_version_sf`，免導去官方 Orca）；**工具列 title logo**。
6. **最終 splash 圖的 V3.5 位置**（原生 `GUI_App.cpp`，目前白字在 x=22.4%/y=52.7%，配合圖片可微調）。
7. **最終出貨 build**：把以上 native 補完 + 最新資源 → 出一次乾淨 build。

---

## 5. 機型 / 噴嘴 lineup（**待與規格文件對齊** — 有矛盾）

`匯出_3mf\` 檔名顯示的口徑：
| 機型 | 口徑 | 模式 |
|------|------|------|
| FD300 | 0.25 / 0.4 / 0.6 | PLA+SUP、single、單噴頭 |
| FD600 | 0.4 / 0.6 / 1.0 | PLA+SUP、single、單噴頭 |
| FF600 | 0.4 / 0.6 | 3in1、PLA(4) |
| FF800 | 0.6 / 1.0 | 3in1、PLA(4)、single |
| FP300 | 0.25 / 0.4 / 0.6 | 單噴 |

⚠️ **開放問題**：使用者口頭說「**單料 FP300 = 0.2 噴嘴、不是 0.25**」「**沒有 0.8 噴嘴**」，但 3mf 檔名是 FP300_(0.25)。**下個 Session 請先讀 `切片參數\` 裡的規格 MD（FD300_V21_*、_fd300_matrix 等）對齊正確口徑**，再改 profile 的 `nozzle_diameter`。目前生成器 FP300=`0.2;0.4;0.6`。

---

## 6. 本次 session 主要 git commits

```
d8ab376d family空 + 雙噴頭2線材槽(SEMM) + PING.json version+1
d9c4d126 splash 版本字 3.5.0→V3.5
a73a9dd6 移除splash版本繪製層 + app名稱PING Slicer + 配色青綠→橘(62處)
78adb9b6 移除Bambu雲端(early-return + 不載入外掛)
711eeaaa 最終splash圖 + V3.5白字
446b7099 About框PING化(保留致謝)   ← build 27005916752 就是這顆
e357e7c3 FD300三模式參數嵌入 + embed_params.py轉換器
69b7c750 web設定精靈:移除PING前綴 + 跳過Bambu插件頁
(未commit) 3.0每噴嘴版 21/24.js 複製 ← 待測試後 commit
```

---

## 7. 使用者的硬性偏好（來自全域 CLAUDE.md / 對話）
- **一律繁體中文**回覆。
- **PING 相關成品一律套 PING CIS**（動手前載 `ping-cis` skill；主色 Raised Orange `#EA4E16` 僅 accent ~5%、白底為主、禁大面積橘、Logo 用 assets 原檔不可重畫）。
- **切片參數由「另一個人」負責**：我只做軟體/功能 + 把標準參數嵌進去；參數值是他的源檔（如單料 config 的 PLA 值有錯，提醒他改源檔，不是我改）。
- **效率**：能免 build 就免 build（資源檔即時改 portable）；native 改動批次化、一次 build。
- AGPL 合規：保留 LICENSE、About 標註 based on OrcaSlicer + 源碼連結、不可寫 "All Rights Reserved"、不打包 Bambu 閉源 DLL。
