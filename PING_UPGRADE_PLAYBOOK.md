# PING Slicer — Orca 升級 Playbook

> 目的：當上游 **OrcaSlicer 出新版**時，用「對的動作」把 PING 客製有效率地搬到新版上。
> 這份回答「客製到底改了哪些東西、升級時哪些會痛、按什麼順序搬最省力」。
> 搭配 `PING_CUSTOMIZATION.md`（AGPL 逐項紀錄）與 `PING_HANDOFF.md`（踩坑表）一起看。
>
> 基準：**OrcaSlicer `v2.3.2`**（tag 在本 repo）。上游 = `github.com/OrcaSlicer/OrcaSlicer`（原 SoftFever）。
> 客製 = v2.3.2 之上的 **44 個 commit**。

---

## 0. 一頁速覽（TL;DR）

升級 = 把客製面分四類、依風險序重搬，**不要硬 merge 全部**：

| 類別 | 規模 | 升級動作 | 風險 |
|------|------|----------|------|
| **A. PING 自有檔（新增）** | 147 檔 | 整包搬過去 | 🟢 幾乎零衝突（上游沒這些檔）|
| **B. 機械式改動（換色＋品牌字串）** | ~58 個 native 檔，各 ≤4 行 | **跑腳本重套**，不要逐檔 merge | 🟡 量大但無腦 |
| **C. 邏輯改動（真的動行為）** | **~10 檔**（GUI_App 佔大半）| 逐檔比對、人工 merge | 🔴 升級唯一要動腦的地方 |
| **D. 廠商精簡（刪除）** | 刪 10389 檔 | 重刪非 PING 廠商 + 檢查上游新增廠商 | 🟡 注意別刪到 `OrcaFilamentLibrary.json`（坑#2）|

**核心洞見**：升級痛苦的根源是「換色散在 ~58 個檔」。一旦把換色＋品牌字串抽成**可重跑腳本**（見 §7），升級的衝突面就塌縮到 **C 類那 ~10 個邏輯檔 + 資源**，半天可完成。

---

## 1. 客製面的真實形狀（數據・`git diff v2.3.2..ping/v3.5`）

```
新增 (A)  147 檔   ← PING 自有：profiles/PING、images、SplashLayered、i18n .mo、docs
修改 (M)  533 檔   ← 其中 src/ 約 90 檔
刪除 (D) 10389 檔  ← 精簡掉所有非 PING 廠商 profile/資源
```

**修改的 native 檔按改動行數排序（churn）：**
```
125 行  src/slic3r/GUI/GUI_App.cpp   ← 一枝獨秀＝PING native 邏輯心臟
 20 行  MultiTaskManagerPage.cpp
 18 行  Plater.cpp / NetworkPluginDialog.cpp
 16 行  ImGuiWrapper.cpp
 14 行  BBLTopbar.cpp
 ≤12 行 其餘 ~80 檔（多為換色/品牌）
─────────
 58 檔 ≤4 行（機械式）｜ 32 檔 >4 行（升級時要看一眼）
```

> ⚠️ **churn 小 ≠ 不重要**：`PresetBundle.cpp` 行數少，但藏著 `inherits` 致命坑與 SEMM 線材槽初始化（坑#9/#12/#13），語意關鍵，升級必看。

**PING 自有的 native 檔只有 2 個**：`src/slic3r/GUI/SplashLayered.cpp` / `.hpp`（splash 去背，坑#15）。其餘 native 全是「改上游既有檔」。

---

## 2. 三層架構（先判斷改哪層 → 決定要不要 build）

PING = Orca = Bambu Studio 的 fork，C++ / wxWidgets / CMake。改動落在三層：

### 原生 C++（`src/**`）→ **要 CI build（~50 分）**
- `libslic3r/`：核心切片引擎（平台無關）。**PING 幾乎不碰**，只動 `PresetBundle.cpp`（preset 載入/SEMM）與 `libslic3r.h`（app 全名字串）。→ 上游若重構切片引擎，**對我們影響極小**。
- `slic3r/GUI/`：wxWidgets UI。PING 客製集中在這（配色、品牌、Bambu 移除、SEMM gate、splash）。→ 上游 UI 改版**最會打到我們**。

### 資源（`resources/**`）→ **免 build，改完同步即可**
- `profiles/PING/`：機型/製程/線材（PING 自有，整包搬）。
- `web/guide/`：**設定精靈是網頁不是原生**（坑#1）！HTML/JS。上游若改精靈 → 要重新對照移植。
- `i18n/**/*.mo`：翻譯（已收進 repo，坑#16；app key=PINGSlicer 找 `PINGSlicer.mo`，坑#5）。
- `images/`：圖示/splash/封面（**保留上游檔名**換內容，免動數十處引用）。

### 建置 meta → 要 build
- `version.inc`（app 名/key/版號）、`CMakeLists.txt`（CPack/NSIS 捷徑/bundle id）、`.github/workflows/build_*.yml`（產物命名）。

判斷口訣（同 HANDOFF §3）：**對話框文字/logo/splash→原生；設定精靈頁→web；機型/製程/線材→資源 profile；配色→原生+web 兩邊；App 名→version.inc+libslic3r.h。**

---

## 3. 升級策略：三選一（含建議）

| 策略 | 怎麼做 | 適用 | 評價 |
|------|--------|------|------|
| **Merge** | `git merge <新tag>` 進 ping 分支，一次解衝突 | patch 小改版（如 2.3.2→2.3.3）| 上游改動小時最快 |
| **Rebase** | `git rebase --onto <新tag> v2.3.2 ping/v3.5` 重放 44 commit | 想保留線性歷史 | 44× 衝突、PING 歷史多迭代（splash/色改了好幾次）→ **痛** |
| **Re-fork ＋ 腳本重套** ⭐ | 從新 tag 開乾淨分支，**B 類跑腳本、C 類逐檔搬、A/D 類整包** | **大版號跳升（建議預設）** | 衝突面最小、最可控 |

**建議**：
- **小改版** → Merge，解掉 C 類那幾檔衝突即可。
- **大改版** → **Re-fork ＋ 腳本重套**（§4 SOP）。理由：換色佔了大半衝突，用腳本重跑比逐行 merge 乾淨太多；PING 的 44 commit 含大量迭代（多次 splash/配色修正），rebase 它們不划算。

---

## 4. 升級 SOP（大改版・Re-fork 流程）

```bash
# 1) 接上游、取得新 tag 與其 release notes（先讀 notes 找破壞性變更！）
git remote add upstream https://github.com/OrcaSlicer/OrcaSlicer.git   # 只需一次
git fetch upstream --tags
#   讀 https://github.com/OrcaSlicer/OrcaSlicer/releases 看新版改了什麼

# 2) 從新 tag 開乾淨分支
git checkout -b ping/v3.6 v<新版tag>

# 3) 依風險序重搬客製（A→D）
#  A. PING 自有檔整包搬（零衝突）
git checkout ping/v3.5 -- resources/profiles/PING resources/i18n \
    src/slic3r/GUI/SplashLayered.cpp src/slic3r/GUI/SplashLayered.hpp \
    PING_CUSTOMIZATION.md PING_HANDOFF.md PING_UPGRADE_PLAYBOOK.md tools/ping
#     images：用 PING 版覆蓋同名上游檔（保留檔名）
#     web/guide：先 diff 上游有沒有改精靈，再決定整包搬 or 重新移植

#  B. 機械式（換色＋品牌字串）→ 跑腳本（見 §7；尚未建立則先逐檔重套一次並順手寫成腳本）

#  C. 邏輯檔逐檔搬：對每個 §6「🔴邏輯」檔，先看 PING 的改動
git diff v2.3.2 ping/v3.5 -- src/slic3r/GUI/GUI_App.cpp   # 取得 PING patch
#     在新版對應位置重做同樣意圖（上游若搬了函式/改了簽名 → 對位重貼）
#     GUI_App.cpp 是重點：Bambu 移除×4、SEMM gate(L7104 區)、停更新器、預設繁中

#  D. 廠商精簡：刪掉新版 resources/profiles 內非 PING 廠商
#     ⚠ 務必保留 OrcaFilamentLibrary.json（坑#2，啟動必需）
#     檢查上游有沒有「新增的廠商」也要一起刪

# 4) 先只驗 Windows（快）
gh workflow run "Build all" --ref ping/v3.6   # 目前無平台選擇器，只抓 Windows artifact
#     未來可加 platforms input 做 Windows-only（§7）

# 5) 跑 §5 驗證 checklist
```

---

## 5. 升級高風險區（哪些上游改動會打到我們 ＋ 對策 ＋ 驗證）

| 風險點 | 上游若動到什麼會出事 | 對策 / 驗證 |
|--------|----------------------|-------------|
| **配色** | 上游改了某 widget 的顏色行 → 腳本沒覆蓋到 → 殘留綠 | 重跑換色腳本後，全 UI 掃一遍殘留青綠；HANDOFF 坑#14 |
| **SEMM 線材槽 gate** | 上游動 `GUI_App::load_current_presets`（坑#13 的 L7104 區）→ PING 的「SEMM 機自動展開線材槽」patch 對不上 | 重新定位該 gate、重貼 `else if(ptFFF)` 分支；驗 FD→2槽/FF→4槽/FP→1槽 |
| **inherits 致命坑** | 新 profile 若 `inherits:""` 空字串 → 整包 vendor 載入中止（坑#12）| 主畫面下拉非空＝OK；崩就讀 `log/debug_*.log` 搜 `load_vendor_configs_from_json` |
| **.mo 打包** | CI 從不跑 `gettext_po_to_mo`（坑#16）→ 安裝版只剩英文 | 確認 `resources/i18n/**/*.mo` 在 repo（`.gitignore` 有 `!` 例外）；語言清單要有繁中 |
| **profile schema** | 上游升 profile 格式版本 → 舊 PING profile 載入失敗或被遷移 | 跑官方 C++ 驗證器（`check_profiles.yml`）；對照新版內建範本機型 |
| **Bambu 移除** | 上游重構網路層 → PING 的 early-return 點消失/改名（坑：`should_load_networking_plugin` 等）| 驗：啟動不跳 Bambu 外掛下載、無登入框、不連雲；CUSTOMIZATION §4 |
| **splash 去背** | 純 runtime（坑#15）| build 後看 splash：白底/全透/邊緣暗 → 調 premultiply/layered 序列 |
| **app key / .mo 檔名** | — | app 找 `PINGSlicer.mo`（坑#5），確認 CMake 用 `${SLIC3R_APP_KEY}` |

**最小驗證 checklist（每次升級 build 後）**：① app 名/圖示/splash 是 PING ② 選單繁中 ③ 全 UI 無殘留青綠 ④ 選機精靈勾機器→主畫面下拉有 preset（非 Default）⑤ FD300 選機→2 線材槽 ⑥ 不跳 Bambu 雲端/登入/外掛 ⑦ About 框保留 OrcaSlicer 致謝＋源碼連結（AGPL）。

---

## 6. 客製面總表（檔案 → 改什麼 → 升級類別）

> 🔴=邏輯（人工 merge）｜🟡=機械（腳本）｜🟢=自有/資源（整包）。詳細「為何」見 `PING_CUSTOMIZATION.md`。

**原生 / 邏輯 🔴（升級的重點，逐檔搬）**
- `GUI_App.cpp` — Bambu 雲端移除×4 函式 early-return｜SEMM 線材槽 gate（坑#13）｜停自動更新器 `check_new_version_sf`｜預設語言 zh_TW｜部分配色
- `PresetBundle.cpp` — `inherits` 處理｜SEMM 多材料線材初始化（坑#9/#12）
- `libslic3r.h` — `SLIC3R_APP_FULL_NAME` → PING Slicer（影響 86 處）
- `MainFrame.cpp` — 手動「檢查更新」選單路徑｜splash 呼叫
- `AboutDialog.cpp` — About PING 化＋保留 AGPL 致謝/源碼連結
- `GLCanvas3D.cpp` — 停「混用 PLA/PETG」警告
- `MsgDialog.cpp` — 對話框 logo（`OrcaSlicer.svg`→PING，走 nanosvg；坑#14）
- `BBLNetworkPlugin.cpp`、`Process.cpp` — 重啟用的執行檔名 `ping-slicer.exe`
- `SplashLayered.cpp/.hpp`（🟢新增）— splash per-pixel 去背（Win32 layered window）

**原生 / 機械 🟡（腳本重套）**
- 配色：青綠色階→PING 橘（`#009688→#EA4E16`、`#26A69A→#F26C3D`、`#52c7b8→#EA4E16`、淺底→淺橘、暗模式→暗橘）散在 ~58 個 GUI/Widgets 檔。**保留語意色**（GCode/線材調色盤、Google 圖示、座標軸）。
- 品牌字串：`Orca/OrcaSlicer`→PING、執行檔名、CompanyName 等。

**建置 meta 🔴/🟡**
- `version.inc`、`CMakeLists.txt`、`src/CMakeLists.txt`（exe OUTPUT_NAME）、`OrcaSlicer.rc.in`、`*.desktop`、`.github/workflows/build_orca.yml`＋`check_profiles.yml`（產物命名/驗證判定）。

**資源 🟢（整包/同名覆蓋）**
- `resources/profiles/PING/**`（7 機型・profiles）｜`resources/i18n/**/*.mo`（42 檔）｜`resources/web/guide/**`（設定精靈，**比對上游有無改版**）｜`resources/web/data/text.js`（zh_CN→zh_TW 重導）｜`resources/images/OrcaSlicer*.{ico,png,icns}`＋`splash_logo*.png`＋`PING_about*.png`（同名換內容）。

**刪除 🟡**：所有非 PING 廠商 `resources/profiles/<vendor>`（保留 `OrcaFilamentLibrary.json`）。

---

## 7. 讓下次更省力的改善建議（一次性投資）

1. **把換色＋品牌字串寫成可重跑腳本** `tools/ping/apply_brand.py`（最高 CP 值）：
   - 一個 hex 對照表（綠階→橘階）+ 字串對照表（Orca→PING），對 `src/**`、`resources/web/**` 做確定性 find-replace，**跳過語意色清單**。
   - 升級時 B 類從「逐檔 merge 58 檔」→「跑一條指令」。把目前散在 commit 的換色知識固化成程式。
2. **CI 加平台選擇器**：`build_all.yml` 的 `workflow_dispatch` 加 `platforms` input（windows/all），讓客製驗證能 **Windows-only**（快又省）。目前只能建全平台再挑 Windows artifact。
3. **品牌字串集中化**：能集中的 PING 字串盡量收斂到 `version.inc`/`libslic3r.h`，減少散落點。
4. **維持「客製＝乾淨 commit 序列」**：未來客製盡量分主題、少迭代覆蓋，讓 cherry-pick/rebase 可行。
5. **PING profiles 與生成器同步**：改機型務必同步 `tools/ping/gen_ping_profiles.py` / `embed_params.py`（否則 regen 洗掉；HANDOFF §8）。

---

## 8. 維護備註
- 本 repo 分支 `ping/v3.5`，remote `github.com/ericlee-lang/PING-Slicer`。
- AGPL 合規：保留 `LICENSE.txt`、About「Based on OrcaSlicer」＋源碼連結、不打包 Bambu 閉源 DLL（CUSTOMIZATION §4/§5）。
- 升級完成後，記得更新本檔的「基準版本」與 `PING_CUSTOMIZATION.md`。
