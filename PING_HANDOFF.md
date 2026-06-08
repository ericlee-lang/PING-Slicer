# PING Slicer V3.5 — Session Hand-off ＆ 客製化指南

> 這份是「接手用」文件：給下一個 Session（或維護者）快速接續 + 避免重踩坑。
> 搭配 `PING_CUSTOMIZATION.md`（AGPL 修改紀錄）一起看。
> 最近一次 session 圖文總結：`D:\dev\2026claude\20260604 ORCA客製\PING_session_summary_20260607.html`。

---

## 0. 立即接續（現況 + 待辦）

**現況（2026-06-07・本 session 完成、多數已驗證）**
- 選機精靈「選擇 3D 列印機」頁正常運作（CSS 修，見坑 #1 註）。
- **FD300 家族 vendor 載入正常**（製程 inherits 修，坑 #12）；**FD300（雙料）選機自動跳 2 卷線材**（原生 patch，坑 #9）——已 build（run `27049518615`）+ 驗證、混料切片正常（更換線材 30 次）。
- **機型已改名**：兩進一出 → **FD300 同進**、單噴頭 → **FD300 單料頭**；FD300 / 單料頭 / 同進 **三台共用同一張 FD300 照片**。
  - ⚠ 命名定案（2026-06-07）：混料機型名用全中文「**同進**」（多料同一噴頭進料），**取代曾用的「Mix50」**。原因：未來「四料」是 25% 混料、非 50%，「50」無法通用；改全中文好理解。下個 session 一律用「同進」，不要再出現 Mix50。
- **切片命名規範統一**（詳見 §8）：機型名去口徑(`alias`)、製程 `<層高>mm @<機型> (<口徑>)` 去 Standard、材料歸線材 preset。
- **製程標配 Scarf 斜接縫**（隱形 Z 接縫，坑 #13 機制）。
- **對話框去金魚 logo**：`OrcaSlicer.svg` + web logo 換成 PING（坑 #14）。

**版本 / commit 狀態**
- 已 build + commit + **已發 Release v3.5.0**（run 27108286233 → Windows 安裝版公開連結 https://github.com/ericlee-lang/PING-Slicer/releases/tag/v3.5.0）：
  - `0a626ad5` CSS 選機頁 + 製程 inherits + 原生線材槽 patch
  - `b762903f` 機型同進改名 + 命名規範 + 列印加速度 + SupPLA + 去金魚 logo + Scarf（純資源，PING.json v08，已同步 portable/APPDATA）
  - `4eb0162b` GLCanvas3D 停用 PLA/PETG 混用警告（原生）
  - **列印加速度規範（使用者定）**：300 機（FD300/單料頭/同進/FP300）普/內/外 = **3000**；450+ 機（FD450/600/800 Pro·FF600/800）三者 = **1500**；**travel 兩組 3000**（原 5000 已降）。27 製程全套用，生成器已同步（`gen_ping_profiles.py` 用 `dia==300`；`embed_params.py` 用 `model_key`）。
  - **PING SupPLA** 換料塔最小清洗量 = **60**（原 15；只此一支，SupABS/SUP-220 未動）。
- **未 commit / 待下次 build（原生）**：**啟動畫面 per-pixel 去背**（splash 桌面透出，取代白底）——新增 `GUI/SplashLayered.cpp/.hpp`（Win32 `UpdateLayeredWindow`，windows.h 隔離避免巨集污染）＋ `GUI_App.cpp` 的 `SplashScreen` 加 `render_layered()`／`SetText` MSW 分支／建構子呼叫 ＋ `src/slic3r/CMakeLists.txt` 列入新檔。**僅 MSW**（非 MSW 維持原白底不透明）。⚠ **未經 build 驗證**：per-pixel alpha 有 runtime 風險（wxGraphicsContext→bitmap 的 alpha 保留、premultiplied、layered 視窗序列），可能需一次微調再 build。
  - 機制：`splash_logo.png` 本身去背；原 `MakeBitmap()` 白底畫布在 MSW 被 layered DIB 蓋過。`render_layered()` 用 wxGraphicsContext 在透明圖上重合成 logo+版本字+載入字 → `update_splash_layered()` 做 premultiplied BGRA + `UpdateLayeredWindow`。

**下一棒待辦** → 見 §4。

---

## 1. 關鍵位置

| 用途 | 路徑 |
|------|------|
| **repo（git）** | `D:\dev\2026claude\20260604 ORCA客製\PING-Slicer`，分支 `ping/v3.5`，remote `github.com/ericlee-lang/PING-Slicer`（gh 已登入 ericlee-lang）|
| **測試用 portable** | `D:\PING-Slicer-portable`（使用者只用這個，不安裝）|
| **參數人員規格/定稿** | `G:\我的雲端硬碟\2026claude\20260603 切片參數`（`orca_fd300_定稿\` 已用；`匯出_3mf\` 有各機型 .3mf；規格 MD 文件；`V3.0\` 有可用版匯出檔可比對）|
| **3.0 參照安裝** | `C:\Program Files\PING slicerV3.0\`（每噴嘴 wizard、舊參數參照）|
| **設定快取** | `%APPDATA%\PINGSlicer`（= `C:\Users\ericl\AppData\Roaming\PINGSlicer`），清掉可強制全新啟動 |
| **轉換器** | `tools/ping/embed_params.py`（吃 .config → 生 FD300 家族 profile）|
| **機型生成器** | `tools/ping/gen_ping_profiles.py`（骨架 profile + 寫 PING.json 基底）|

---

## 2. ⚠️ 踩過的坑（務必先讀，省幾小時）

1. **【最大坑】設定精靈是 WEB 網頁，不是原生 `ConfigWizard.cpp`。** 「選擇 3D 列印機」「選擇線材」「Bambu 網路插件」這些頁面都在 **`resources/web/guide/`**（HTML/JS）。動 wizard 一律先看 `resources/web/guide/`。印表機卡片渲染：`guide/21,24.js` 的 `HandleModelList`。
   - 註：「選機頁失效」根因是<u>只移植 3.0 的 JS 卻留新版 CSS</u>——`.pNozzel{display:none}` 把每噴嘴勾選框藏了、`<img>` 無 `ModelThumbnail` class 而爆大。修 `21/24.css`：`.pNozzel→display:flex` + 加 `.PImg img{width/height:100%;object-fit:contain}`。

2. **`OrcaFilamentLibrary.json` 是啟動必需檔。** 移除非 PING 廠商時若把它一起刪 → 啟動崩潰。它 0 印表機 / 353 線材，**務必保留**。

3. **資源檔 vs 原生 code（決定要不要 build）：**
   - **資源檔（免 build）**：`resources/profiles/**`、`resources/web/**`、`resources/images/**`、`resources/i18n/**/*.mo`。
   - **原生 code（要 CI build ~50min）**：`src/**/*.cpp/.hpp`、`version.inc`、`CMakeLists.txt`、`libslic3r.h`。
   - portable 的 `ping-slicer.exe` 是 binary，**只有 build 才會變**。

4. **改 profile 後要把 `PING.json` 的 `version` +1**，否則 app 不會從 resources 重新複製到 `%APPDATA%\PINGSlicer\system`，你會看到舊的。**同步要做兩處**：`D:\PING-Slicer-portable\resources` 與 `%APPDATA%\PINGSlicer\system`。

5. **繁中 `.mo` 檔名陷阱**：app（`SLIC3R_APP_KEY="PINGSlicer"`）找 `PINGSlicer.mo`，但 build 產出 `OrcaSlicer.mo` → 原生選單變英文。**暫解**：每個 `resources/i18n/<lang>/OrcaSlicer.mo` 複製成 `PINGSlicer.mo`。**根治待辦**：CMakeLists L761 未生效。

6. **嵌入參數人員 `.config` 的 key 分類**：用 `Preset.cpp` 權威清單。**坑**：`printer_options()` 還 append `machine_limits`（`machine_max_*`）與 `nozzle_options`（per-extruder），這些**同時列在 filament_options**，分類要「機台優先於 filament」。`embed_params.py` 已處理。

7. **wizard 機台 preset 按噴嘴（`FD300 0.4 nozzle`）；3.0 的「每噴嘴勾選」JS 已恢復。** 原生 handler 在 `WebGuideDialog.cpp::save_userguide_models`（L425）。
   - ⚠ 註（本 session 釐清）：「勾了機器卻載不到」的<strong>真正</strong>根因是製程 `inherits` 空字串害整包 vendor 載入中止（坑 #12），<u>不是</u>勾選方式；每噴嘴勾選仍需要，但別把那當成「載不到」的解。

8. **中文路徑會讓 bash/PowerShell 工具間歇亂碼。** 用 Python `glob`/`os.walk` 配 ASCII 萬用字元（`glob.glob(r"G:\*\2026claude\*")`）。

9. **【線材槽數機制・取代舊「[nz]*feeds」說法】線材槽數 = 專案 `filament_settings_id` 數量，<u>不是</u> `nozzle_diameter` 元素數。** Orca 把「依 nozzle 數 resize 線材」那段 `#if 0` 關掉了（`PresetBundle.cpp::update_multi_material_filament_presets` L4300）。選機初始化在 `GUI_App.cpp::load_current_presets` **L7104** 的 ORCA gate（stock 2.3.2）：`if (ptFFF && !single_extruder_multi_material) set_num_filaments(nozzle數)`——**只對非 SEMM 機同步**。PING 全系列 SEMM=1 → 選機不自動展開（V3.0 舊版會用 `default_filament_profile` 初始化 → 版本行為差異）。
   - **PING 解法（已 patch，已 build 驗證）**：L7104 後加 `else if (ptFFF)`——SEMM 機若 `default_filament_profile` 數 > 目前線材數則 `set_num_filaments(default_filament_profile數)`，只增不減。FD→2槽 / FF→4槽 / FP→1槽。
   - **FD300 同進（2 進 1 出）= nozzle_diameter `['0.4']`（1 元素）+ SEMM=1 + 空 `change_filament_gcode`**，與 V3.0 可用版一致；混料靠 Start G-code 的 `M6050 S0.5`（硬體層），切片端維持 1 卷。（先前「nozzle=[nz]*feeds 才有 2 槽」的假設已作廢。）

10. **`build` 顯示 failure 常常只是 `Unit Tests` 那個 job 掛**（既有問題），**各平台編譯其實 success、安裝檔有產出**。去看各 job，別被紅 X 嚇到。

11. **wizard 卡片封面 = `resources/profiles/PING/<機型名>_cover.png`**（fallback `resources/web/image/printer/`），`WebGuideDialog.cpp:1291`。**用機型名解析，不是 JSON 欄位**——機型改名要同步改封面檔名，否則卡片空白。封面上的「PING」是真實產品照（機身印的），要修圖才能改。

12. **【profile 致命坑】preset 的 `inherits` 寫成空字串 `""` 會讓整包 vendor 載入中止。** `PresetBundle.cpp::load_vendor_configs_from_json`（L4037）判斷「JSON 有沒有 `inherits` key」，不是值是否為空：有 key 但值 `""` → 找名為空字串的父 preset → `can not find inherits` → **return 中止**，該 vendor 之後所有 preset 全部不載入（症狀：精靈勾得到機器，主畫面下拉全空、`presets.machine` 退回 `Default Printer`）。**規則**：`inherits` 要嘛整個 key 不寫，要嘛指向存在父 preset（製程 `fdm_process_ping_common`、線材 `fdm_filament_common`）；**絕不可留空字串**。診斷：讀 `%APPDATA%\PINGSlicer\log\debug_*.log` 搜 `load_vendor_configs_from_json`。`machine_model` 型檔（`FD300.json` 等）不是 preset、本來就沒 `inherits`/`instantiation`，別誤修。

13. **機型/製程的「顯示」機制（命名規範的基礎）：**
    - 印表機下拉文字 = `printer_model`（去重，每機型一項）｜噴嘴 chip = `printer_variant`｜active 標籤 = `Preset::label()` = `alias`(未設則 name)。三者**互不讀 preset 檔名**。
    - 所以「機型名去口徑」靠：每個 per-nozzle machine preset 加 `"alias"=printer_model`。切噴嘴時 `prefer_printer=alias` 會 fallback 到 variant-match，仍正確（`PresetBundle.cpp:2943`）。
    - 製程名含 `@` 時，alias = `@` 之前那段（`PresetBundle.cpp:4198`）→ 左側「列印參數」下拉只顯示 `@` 之前（如 `0.2mm`）；完整名在設定分頁/tooltip/專案檔。
    - 接縫 Scarf：`seam_slope_type=external`(外牆) / `seam_slope_start_height=10%` / `seam_slope_min_length=8`(mm) / `has_scarf_joint_seam=1`。⚠ Orca 2.3.2 **無** 「scarf slope gap」key（更新版才有）。

14. **對話框 logo = `OrcaSlicer.svg`**（`MsgDialog` 的 `create_scaled_bitmap("OrcaSlicer")`，走 nanosvg）。app 圖示 `.ico/.png` 早已是 PING 橘 P，但 svg 優先載入且先前漏換 → 對話框一直金魚。**nanosvg 不吃 base64 `<image>`**，要用純向量 SVG（可用 PyMuPDF 把官方 `src_compact.pdf` 轉 SVG + 去 clipPath）。web logo 在 `guide/1/index.html` + `homepage/index.html`（方形槽，用橘 P 方圖）。

---

## 3. ✅ 正確的客製化流程

1. **先判斷：資源檔 還是 原生 code？**（見坑 #3）
   - 對話框文字/logo（About、splash）→ 原生；設定精靈頁 → WEB（`resources/web/guide/`）；機型/製程/線材 profile → 資源；配色 → 兩邊；App 名稱 → `version.inc` + `libslic3r.h`。
2. **資源檔改動**：repo 改 → 同步 `D:\PING-Slicer-portable\resources` + `%APPDATA%\PINGSlicer\system` →（動 profile 就 `PING.json` version +1）→ **同步改產生器**（`embed_params.py`/`gen_ping_profiles.py`）避免重生跑掉 → 重開 portable 測。**不 build。**
3. **原生改動**：改 `src/` → commit → `gh workflow run "Build all" --ref ping/v3.5` → ~50min。
4. **嵌入參數定稿**：`python tools/ping/embed_params.py "<定稿資料夾>"` → 同步。
5. **取 build portable**：`gh run download <run_id> -R ericlee-lang/PING-Slicer -n PING_Slicer_Windows_V3.5.0_portable -D <dir>`；新 binary 要疊最新 `resources/profiles/PING` + `.mo`(複製成 PINGSlicer.mo)。
6. **換 portable**：app 完全關閉 → `mv` 舊的備份 → `mv` 新的進去 → 視需要清 `%APPDATA%\PINGSlicer`（**保留 OrcaFilamentLibrary**）。

---

## 4. 進度

### ✅ 已完成
- 品牌：app 名稱、splash、About 框、配色青綠→橘、預設繁中、移除 Bambu 雲端。
- **選機精靈頁修復**（CSS）、**vendor 載入修復**（製程 inherits）、**FD300 自動 2 卷**（原生 patch，已 build run 27049518615）。
- **去金魚 logo**（OrcaSlicer.svg + web logo）。
- **機型改名 + 切片命名規範統一 + 接縫 Scarf**（見 §8）。
- FD300 定稿參數：3 機台變體（雙料 FD300 / 單料頭 / 同進）× 3 口徑。

### ⬜ 待辦（給下一棒）
1. **commit 已確認批**（去金魚 logo + 機型/製程命名 + 接縫；純資源、免 build）— 待使用者測 OK。
2. **下次 native build 批**：PLA/PETG 混用警告移除（已寫未 commit）＋ `.mo` 根治（CMakeLists L761）＋ macOS bundle 名 ＋ 自動更新器停用（`check_new_version_sf`）＋ 工具列 title logo ＋ splash V3.5 定位。
3. **清測試殘留 user presets**：`FD300 0.25 nozzle - 複製`、`-0.173`、`0.125mm @FD300 (0.25) - 複製`（需 App 關閉再刪；線材 `PING PLA - 210` 使用者決定）。
4. **繼續切片參數**：材料溫度/支撐/速度…（材料相關放 **filament preset**，依 §8；值是參數人員源檔）。
5. **線材頁只留 PING**：wizard 線材頁 `guide/22` 過濾掉 OrcaFilamentLibrary 廠牌。
6. **嵌入其他機型參數**：`匯出_3mf\` 的 FD600/FF600/FF800/FP300（先擴充 `embed_params.py` 支援 .3mf 解壓）。
7. **FP300 口徑對齊**：讀 `切片參數\` 規格 MD 確認 0.2 vs 0.25、有無 0.8（見 §5 開放問題）。

---

## 5. 機型 / 噴嘴 lineup（**FP300 口徑待對齊**）

| 機型（printer_model）| 口徑（printer_variant）| 模式 |
|------|------|------|
| FD300 | 0.25 / 0.4 / 0.6 | 雙料（PLA+SUP，自動 2 卷）|
| FD300 單料頭 | 0.25 / 0.4 / 0.6 | 單料（1 卷）|
| FD300 同進 | 0.25 / 0.4 / 0.6 | 2 進 1 出混料（1 卷 + Start `M6050 S0.5`）|
| FP300 | 0.2 / 0.4 / 0.6 | 高速單料 |
| FD450 Pro / FD600 Pro / FD800 Pro | 0.4 / 0.6 / 1.0 | 雙料 |
| FF600 / FF800 | 0.4 / 0.6 / 1.0 | 高速四料 |

⚠️ **開放問題**：使用者口頭說「**單料 FP300 = 0.2 噴嘴**」「**沒有 0.8 噴嘴**」，目前生成器 FP300=`0.2;0.4;0.6`。下個 Session 讀 `切片參數\` 規格 MD 對齊正確口徑再改 `nozzle_diameter`。

---

## 6. 主要 git commits

```
（本 session・ping/v3.5）
0a626ad5 CSS選機頁 + 製程inherits修 + 原生線材槽patch(GUI_App.cpp:7104)  ← build run 27049518615
（更早）
446b7099 About框PING化(保留致謝)
e357e7c3 FD300三模式參數嵌入 + embed_params.py轉換器
69b7c750 web設定精靈:移除PING前綴 + 跳過Bambu插件頁
（未 commit・純資源）去金魚logo(OrcaSlicer.svg+web) + 機型改名(同進/單料頭) + 製程命名去Standard + alias + 接縫Scarf
（未 commit・原生）PLA/PETG混用警告移除(GLCanvas3D.cpp)
```

---

## 7. 使用者的硬性偏好

- **一律繁體中文**回覆。
- **PING 相關成品一律套 PING CIS**（動手前載 `ping-cis` skill；Raised Orange `#EA4E16` 僅 accent ~5%、白底為主、禁大面積橘、Logo 用 assets 原檔不可重畫）。**給人閱讀文件優先單檔 HTML**（離線、不引 CDN/網路字型）；機器/AI 用途檔（README、設定檔）才用 Markdown。
- **切片參數由「另一個人」負責**：軟體端只做功能 + 把標準參數嵌進去；參數值是他的源檔（值有錯提醒他改源檔）。
- **效率**：能免 build 就免 build；native 改動批次化、一次 build。
- AGPL 合規：保留 LICENSE、About 標註 based on OrcaSlicer + 源碼連結、不可寫 "All Rights Reserved"、不打包 Bambu 閉源 DLL。

---

## 8. 切片命名規範（本 session 訂定）

**三層命名，材料維度與品質維度分開（對齊 Bambu 慣例）：**

| 層 | 規則 | 範例 | 主畫面看到 |
|----|------|------|-----------|
| **機型**（printer_model）| `<機型>[ <變體>]`，**不帶口徑** | `FD300`、`FD300 單料頭`、`FD300 同進` | 下拉/標籤乾淨名；口徑走噴嘴 chip |
| **製程**（process name）| `<層高>mm @<機型> (<口徑>)`，**不寫 Standard、材料不進名** | `0.2mm @FD300 同進 (0.4)` | 下拉只顯示 `@` 之前 → `0.2mm` |
| **材料**（filament name）| 材料放這層 | `PING PLA`、`PING SUP`、`PING PLA - 220` | 線材下拉 |

- **機型名去口徑**：每個 per-nozzle machine preset 加 `"alias"=printer_model`（坑 #13）。**套用全部 PING 機型**。口徑只存 `printer_variant`。
- **FD300 三模式 = 三個獨立機型**（Option A）：Orca 一機型只有一個變體維度（被口徑用掉），模式無法做成第二個勾選/chip，除非原生加 dual-selector（~200 行 + build）。三台共用同一張 FD300 cover 即達成「只要一張照片」。
- **產生器同步**：`embed_params.py`（MODES 名 + 機台加 alias + 製程接縫）、`gen_ping_profiles.py`（製程模板去 Standard + 機台加 alias + 接縫 + version）。改名/規範務必同步改產生器，否則 regen 洗掉。
- **後續**：要做材料專屬製程時，材料放 filament preset；若同口徑要多品質階再引入 Bambu 式階名（Fine/Optimal/Draft…，置於 `@` 之前）。
