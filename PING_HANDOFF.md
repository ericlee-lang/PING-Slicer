# PING Slicer V3.5 — Session Hand-off ＆ 客製化指南

> 🧭 **加機型／動切片引擎前，先讀 `D:\dev\2026claude\20260604 ORCA客製\SOP_加機型.md`**（跨棒永久標準：機型＝多檔 preset bundle 結構、加機型步驟、`extruder_id 越界`/FF800 同進崩潰的已驗證真因與修法都在 §2.5）。
>
> 🟠 **本專案 repo（git）在：`D:\dev\2026claude\20260604 ORCA客製\PING-Slicer`**（分支 `ping/v3.5`）。
> **請在這個資料夾開 session**，不要開在 G 槽雲端的 `…\20250403 ORCA軟體客制\`（那是舊資料夾，沒有 repo）。
> 接續指令： `讀 D:\dev\2026claude\20260604 ORCA客製\PING-Slicer\PING_HANDOFF.md 接續`
>
> 這份是「接手用」文件：給下一個 Session（或維護者）快速接續 + 避免重踩坑。
> 搭配 `PING_CUSTOMIZATION.md`（AGPL 修改紀錄）一起看。
> 歷次 session 圖文總結都在 `D:\dev\2026claude\20260604 ORCA客製\_封存\session總結\`（最新 `PING_session_summary_20260703.html`）。

---

## 0. 立即接續（現況 + 待辦）

---
### 🏁 收工快照（2026-07-30 — **照片磚 C-0 技術尖峰**：四項全過＋Codex 13 條回審補測閉環；球在 Eric 裁 B 進 C-1）

**線況**：**兩線 repo 零觸碰**（不改碼不 build 不 push＝T015 候選 bundle 85 原封不動、出貨線勿推紅線遵守）；portable／%APPDATA% 未動。本棒全部產出在治理 repo：報告＋產物包＋認領簿（c-0729-PT-07 掛→銷）。

**C-0 戰果（計畫 §3 四項、11 項裁決定案值下執行）**：
1. **①引擎 API 化**＝`generate(request)→Promise<result>` 已做出（`照片磚_C0尖峰產物/phototile_engine.js`＝**C-1 起點**；逐行搬自工作室頁、行號註記；夾值/錯誤分類/取消契約全實測）。**雙路黃金 oracle 6/6 案全等**（`goldenrunner.html` iframe 載真工作室 vs 引擎、同輸入 → 3MF 逐 entry SHA-256 斷言；覆蓋 P2A/交錯齒/無柱/濾除關全分支；存證 `golden_report.json`）＝縫線/水密戰果 100% 內建。
2. **②隱形宿主**＝獨立 WebView2 原型（C#＋deps 原生 SDK vtable 轉錄、不經 wx）三情境 exit 0：runtime 正負檢測（bogus→0x80070002）／隱形 10 連發 sha 全同／TrySuspend-Resume（sha 驗證）／**崩潰重建三里程碑 controller +378ms・ready +531ms・首結果 +3,465ms**（重建 sha 不同＝FAIL 的 oracle）／**36MB 近上限圖片注入鏈**（247×192K-char ExecuteScript＝產品同形、1.3s 注入+2.5s 生成；UI 執行緒漂移 871ms→C-1 移出 UI 緒項）／生成中取消（grid 邊界砍掉）／noready・crashx4 負測。🔴 **紅字發現＝隱形頁 setTimeout 節流 ~1s/次（探針實測）→ 現行工作室頁不能直接搬進隱形宿主、引擎 API 化是 B 案前提**（引擎零計時器＝免疫；取消讓步點用 MessageChannel＝免疫）。
3. **③效能包絡**＝常用尺寸 dual 1.1-1.6s／quad 2.4-3.0s；**合法上限 quad・K=48・400×400＝p50 53.6s**（quantize 內積天性）＝**進度顯示＋取消為 C-1 必備**；持續負載變異帶 2.4×（筆電熱節流；「quad/1.0 離群」說經 ×3 複測撤銷）；高像素輸入（48M px）無爆量；記憶體＝JS heap ≤330MB、進程樹 WS 峰值 1Hz 觀測 1,303MB（低規機風險→C-1 GRID_MAX 降階＋OOM gate）；**512MB 傳輸上限非約束**（3MF 實際最大 2.33MB）。runtime 測程中 .99→.105 自動升級＝Evergreen 相依活證據。
4. **④行為矩陣定稿**＝輸入層 12 列（現況三管道親驗：拖放＝唯一圖片入口 Plater.cpp:4793／開檔 FT_MODEL 無圖片副檔名 GUI_App.cpp:650＋import_model :4480／Ctrl+V 僅內部剪貼簿 :18326）＋11 項裁決映射表（每項定案值落到 C-1~C-4 哪站）。
5. **Codex（gpt-5.6-sol）對抗審 13 條全數逐條回審**（採納 12/部分 1/不採 0；**4 條阻斷全以補測關閉**：雙路 oracle／包絡／注入鏈／真睡眠轉裁決）——回審表＝報告 §9。

**🔴 下一棒（球在 Eric，見 待確認 頂部）**：①**裁「准 B（隱形引擎）進 C-1」**——C-1 首站三閘門＝最小 wx 整合 smoke（此時才 build C++）＋實機睡眠過夜＋OOM gate，任一敗觸發轉 A（退出條件四條含 OOM、報告 §6）②**核可「真實睡眠喚醒」豁免出 C-0**（不能在 Eric 工作機睡眠；已用 TrySuspend+殺進程代理覆蓋）③准入後 C-1 範圍＝job 協定＋PhotoTileEngineHost（規格草案報告 §3.3）＋最小 metadata schema（計畫 §3 C-1 列）。**接手先讀**：`..\照片磚_C-0尖峰報告_20260729.html`（§6/§9）＋`..\照片磚_C0尖峰產物\README.md`（重現步驟）。

---
### 🏁 收工快照（2026-07-29 晚 — **照片磚線全日**：自動選機＋V溝移除＋縫線定案 P2A（量化100%內部化）＋C 案計畫交裁）

**線況**：開發線 `ping/v3.5` tip＝本 handoff commit（前一顆 `93c18f4c`）｜出貨線 `release/v3.6` tip `7e2f96b1`——**兩線各含 T11 參數批（`6caee4bf` bundle 84）＋照片磚線六顆 code commit（兩線對稱、功能行 md5 逐批驗）**，全未推＝押 T015（⚠ 出貨線 push 即觸發 CI、發車令未下前勿推）。**portable 已熱補至最新網頁層**（=出貨線檔 md5 `5ca33e98`）＝Eric 現用即最新；appdata 未動。

**本日戰果（時序）**：
1. **自動選機**（Eric 報「載入沒選到機器」→裁 A 案）：工作室匯出帶 mode×口徑 → C++ 開專案前查 preset 實資料切同進照片磚機（`416d091f`/`dcd0f29a`）。⚠ **C++ 未編譯＝隨 T015 CI 首驗**（眼驗五項在 commit msg）；**T013 binary 忽略新欄位＝裝 T015 前過渡動線「先選機再產生」**。
2. **V 溝移除**（Eric 裁「尖點無作用」）：`buildLabelMesh` 溝參數→null（`a75dfa34`/`fbe5b82e`）；水密關卡 59,624 tri 全過；mesh 模組溝碼保留休眠。
3. **縫線研究＋Codex 27 條雙審**：`..\照片磚_縫線位置控制研究_20260729.html`——五站管線機理（55°角點中位／flow_width 膨脹／樣條拉 60%／blocker 後判蓋 enforcer，全親驗行號）＋漏縫機制 M1 角點釘縫/M2 樣條漂移/M3 窄件整圈化。
4. **P2A 兩段落地＋量化定讞**（Eric 裁 C＋實走）：正背面 blocker checkbox（`5b4975c2`/`81d181d4`）＋外側窄面中性（`93c18f4c`/`7e2f96b1`）→ Eric 眼驗兩過＋gcode 全量分析：**縫 100% 合法（交界 99.9%＋側 fallback 0.1%）、正背面 0、連續疤 0、距交界中央 ±0.10mm**。工具＝`..\照片磚_縫點分析工具_20260729.py`（bbox 自推／skirt 排除／PCA 備援）。⚠ P2A checkbox **預設關**＝等實印終驗才裁轉預設。
5. **C 案「準備頁整合」計畫 v2**：`..\照片磚_C案準備頁整合計畫_20260729.html`——Codex 25 條回審畢（阻斷主張親驗：`request_open_project`=reset 整案取代／`OnDropFiles` 現況任何機型攔圖開工作室／材料函式拒非空盤＝**「加入目前盤」等四項基礎設施要新建非沿用**）；階段重切 **C-0 尖峰先行**、裁決表重做 11 項。

**🔴 下一棒**：①**C 案裁決表 11 項＝Eric 0729 晚「全照建議」全項拍板（定案值＝計畫 §5 建議欄）→ 新 session 跑 C-0**（引擎 API 化＋隱形 host spike＋效能基準＋行為矩陣；數據出來交 Eric 裁 A/B 路線）②T015 發車令（車上：T11 參數批＋選機＋V溝移除＋P2A×2；後四顆網頁層已在 portable 生效）③實印終驗（縫內部化＋交界疊縫強度）→ P2A 轉預設裁決 ④規則已沉澱：技術參考 §3.6-C 縫線定案版/§3.6-D V溝作廢＋memory photo-tile-vertical-mixing 0729 段——**接手先讀那兩處＋兩份 0729 報告**。

---
### 🏁 收工快照（2026-07-29 —「0728 ORCA 續」棒：**T012/T013/T014 三顆全鏈出貨＋治理修錯＋T015 候選備妥**）

**線況（0729 晚三批後）**：開發線 `ping/v3.5` tip＝`1cd30d32`（bundle 72＋GCode.cpp 對稱批、未推；⚠ PT 照片磚線同 repo 活動中、tip 可能再前進）｜出貨線 `release/v3.6` tip `d3d51b53`（bundle **85**、未推＝**押 T015**；⚠ 出貨線 push 即觸發 CI、發車令未下前勿推）｜phototile `f7e139cf`（僅治理 docs、其既存髒檔他線勿動）。

**T012~T014 全鏈已出貨**（G 槽現行＝TEST-T014、bundle 83；Eric D 槽＝T013）：帳目正本＝`00治理文件/發布登錄簿.md` T 號表＋`00治理文件/認領簿.md` T11 線 c-0728-T11-01~c-0729-T11-16（每張牌含收工全紀錄）。回報中心三單（#24/#51/#39＋#32）已知會發複測。

**T015 候選內容（兩線已入版未推、bundle 85）**：①內外牆加速度全機型 **1500**（Eric 0729 裁「表面品質與穩定性」；77 檔 3000→1500、**Classic Marlin 隔離 0 照舊**）②洗料塔 **錐體/頂角30/最快列印速度60**（rib→cone、20→30、90→60，211 製程統一）③**Classic 赤兔雙料出檔禁 T0/T1＝M6050 原生輸出**（Klipper #128 同步單、Eric 令：32 機 start 去 T＋DUAL 本體 4 台 `change_filament_gcode` M6050 條件模板＋**C++ `custom_gcode_changes_tool` 認 M6050**——不認則引擎兩呼叫端會在模板後補發裸 Tn〔實查定罪〕；Fast FD 照舊；回執在同步單檔）。verify 全綠（389/108、305/76）＋值稽核直方圖精準＋反向測試；skill core-rules 已回填（`d6de05d`＋`abff85e`）。**眼驗項（裝 T015 後）**：多料製程洗料塔呈錐形／內外牆加速度欄 1500／洗料塔速度≤60／**切 Classic DUAL 檔 grep 三判準**（^T[01]=0、M104·M109 T=0、換刀處 M6050 S1/S0 P0）。⚠ **本輪 C++ 兩刀（GUI 零、libslic3r 一函式）＝T015 CI 首驗**。

**治理修正 Stage 1（PM 發包、Eric 拍板）已完成**：三 worktree 根 CLAUDE.md（刪重複 build 段＋Linux build dir 定 `build`）＋ tests/CLAUDE.md（Catch2 v2→實況 **3.11.0**、include=catch_all.hpp、「NEVER USE APPROX」限縮＝**新測試優先 matchers、現存 16 檔豁免不遷移**）＋照片磚過期記憶標上蓋。三 commit：dev `a8580de0`／release `059d17cc`／phototile `f7e139cf`；逐條處置＋備份 SHA-256＝`00治理文件/治理修正_20260729_ORCA_manifest.md`。⚠ **時序鐵則：AGENTS.md 正本化／@AGENTS.md 橋接＝Stage 2，必須等 ping-system pilot gate（至 08-01）通過後另回合做，不得順手**。

**等 Eric**：①D 槽換 T014？（回「換」全自動；C++ 眼驗三條要裝機看）②T015 發車令 ③T012~T014 眼驗、8/9 實印。詳細等待項＝`待確認/20260604 ORCA客製.md` 頂部。

---
### 🏁 收工快照（2026-07-28 — 本 session 總收工：**T009/T010/T011 三顆 T 全結**＋兩台外機異常調查中）

**線況**：開發線 `ping/v3.5` tip＝本 handoff commit（前一顆 `0dff6dfe`、bundle **66**、已 push）｜出貨線 `release/v3.6` tip `81e9a96a`（bundle **77**＝T011、已 push）｜兩線工作區乾淨｜untracked `resources/web/mixer/`、`sandboxes/`＝他線勿動。

**T011（bundle 77 @ `81e9a96a`、run 30308665000、純 C++ 批）已上架 G 槽**：浮鈕折行二輪修正（T010 實機抓包四字一行＋疊卡片 → 真因＝Button::messureSize 把單行文字寬寫回最小寬 → 修法＝SetMaxSize 鎖寬 60＋UnsetToolTip）。17 項驗收全過；installer `EC857144…572A`／portable `68D308F0…024F`；T010 輪替 old\。**Eric D 槽現裝 T010**（浮鈕新樣式要看得靠換 T011——已問未裁）。
↳ 繞圈知識已沉澱 **`SOP_wxUI元件坑.md`**（新檔：Button 量測/折行機構 ✅ 實證＋SetMaxSize 修法 ⬜ 待眼驗）；UX 筆記 3 條已 append 收件匣。

**✅ 兩台外機異常＝Eric 2026-07-29 裁「個案不進行」結案（有意識取捨、非疏漏——下一棒勿當缺口回補）**：
① K620 機切片後當掉——初判最新 NVIDIA 驅動×2014 Maxwell Quadro 渲染崩、程式無罪傾向（同 binary 於 3050 Ti 正常）；事件檔未取、不再追。若日後再遇同型：驅動退 Quadro R550 系；備案＝`--opengl-version` CLI 移植（PrusaSlicer 有現成實作）。
② 客戶機 OpenGL＜3.2 警告——客戶實際仍能切片（0727 已裁暫不管）；顯卡名未取、不再追。若再發：查裝置管理員（「Microsoft 基本顯示卡」＝裝原廠驅動即解）；最後手段 Mesa 軟渲染 dll。

**下一棒**：①T011 D 槽要不要換（Eric 未裁）②K620 事件檔結果＋客戶 GPU 名回來後收尾兩案 ③T011 浮鈕眼驗（兩行白字橘底/不疊卡片/單一 tooltip）→ 過了把 SOP_wxUI元件坑 §4 轉 ✅ ④T010 其餘眼驗＋8/9 實印照舊 ⑤~~skill 回填候補~~（✅ 0728 續棒已做：ping-slicer materials.md 新條目「支撐牆數全庫 0」＋樹狀表 1→0＋兩處上蓋註，三處引擎引用實查後入文；定向兩檔同步三方一致、validate 19 PASS、commit `675cc99`；跨專案牌 x-0728-ORCA-01 掛→銷）。

---
### 🏁 收工快照（2026-07-27 傍晚 — **T010 全鏈結案＋D 槽已換**：牆數 0＋浮鈕改版到位）

**T010（bundle 77 @ `d475e293`、run 30247787533）**：慣性三紅照舊、**Windows 主建置綠＝浮鈕改版 C++（ButtonStyle::Confirm/Head_14/Label.hpp include）首驗過**。成品 **17 項全過**（T009 16 項＋⑰全庫牆數 0 含基底）。上架＝installer `F4F34AC5…9F14` 101.4MB／portable `141D2263…C62B` 133.9MB、G 槽 hash 一致、T009 輪替 old\。**D 槽 17:53 看門狗自動換裝完成**（Eric 預授權）：T008 備份 `-old-v360T008-0727` → 解壓 44 項 → DL1016 重注（10 檔+10 條、版號不動）→ 驗證全過（bundle 77／111/216/30／牆數 0）→ 備份照「留最新兩個」刪 T005＝**現存 T007+T008 兩份**（發車前已刪 0722/T004fix 兩份舊帳）。Eric 開 app 收編 77＝**牆數 0 一次到位、appdata 手術免重跑**。

**本日戰果鏈（一天四棒）**：Classic DUAL 變體（T009）→ 支撐牆數 0＋浮鈕改版（T010）→ T009/T010 雙發雙上架 → D 槽換 T010。支撐分段問題已答（接觸面設計）Eric 裁「C 不動」。

**下一棒**：①T010 眼驗回報（浮鈕兩行白字橘底/數字可見/深色模式；支撐牆數欄 0；DUAL 同進 M6050 gcode）②同事驗收（版本資訊五項）③8/9 實印照舊 ④開發線 workshop 未 dispatch（Eric 要再說）。工程側無懸帳。

---
### 🏁 收工快照（2026-07-27 下午 — **T009 全鏈結案＋支撐牆數 0 批**）

**T009（bundle 76 @ `0dd11580`、run 30239553158）**：慣性三紅照舊、**Windows 主建置綠＝M6050 分支 C++ 首驗全過**。成品 **16 項驗收全過**（T008 12 項＋Classic 變體四項：32 機/16 model/三卡相鄰、同進 M6050 S0.5、變體製程 FD 值、檔名 同進_49/單料_52）。上架＝installer `3127ED85…3B59F` 101.4MB／portable `34CF0D1A…5D23D` 133.9MB、G 槽 hash 一致、T008 輪替 old\。**Eric D 槽未換**（預授權不跨輪、已問）。

**支撐牆數 0 批（Eric 0727 裁「改零」）**：UI 支撐牆數＝`tree_support_wall_count`（普通/樹狀共用；普通 0=無牆、樹狀 0=auto ⇒ 0725 樹狀「牆圈 1」被上蓋、已明示）。兩線入版**未推＝押 T010**：出貨 `91ad538a`＋基底補遺 `12c7bfaa`（bundle **77**）／開發 `6c18fb9a`＋`43166890`（bundle **66**）；verify 兩線綠、diff 純度單鍵。**Eric appdata 已於 13:46 看門狗自動歸 0**（188 支含基底、備份 `PING.bak-wallcount0-0727`、版號 75 不動）。🔴 **交接紅線：Eric 若裝 T009（bundle 76＝牆數 1）appdata 被收編回 1 → 重跑手術（scratchpad `watchdog_wallcount0.py`、先刪備份夾）或等 T010**。

**支撐分段問題（Eric 問）已答並裁「C 不動」**：斷帶＝該高度有懸空面 → 4 層頂部接觸面（交錯直線、強制 +90°、間距 0.1）＋柱群換班；主體相位全域固定不會飄。零參數變更。

**下一棒**：①T009 驗收回報（Eric＋同事六項）②D 槽要不要換 T009（牆數 1）或直接等 T010（牆數 0）＝Eric 裁 ③T010 發車令（bundle 77/66 已備）④D 槽備份 4 份待裁清（沿前）。

---
### 🏁 收工快照（2026-07-27 — **Classic DUAL 變體完工**：同進＋單料頭×FD 口徑＋M6050 舊格式；押 T009）

**Eric「照做」核准後當日完工、兩線入版未推**：出貨線 `0dd11580`（139 檔、bundle **76**＝T009 候選）／開發線 `f2fc5398`（C++ 3 檔、與出貨線**逐位元一致**）。認領牌 c-0727-CV-01 掛→銷完整。

**內容**：DUAL 300/450/600/800 × {同進、單料頭} × FD 對應口徑（300＝0.25/0.4/0.6；其餘＝0.4/0.6/1.0）＝**+24 機 +24 製程 +8 機型**。machine 從 FD 對應變體機複製再 Marlin 化（回抽 Classic 值 300=2/20 其餘=3/30；動力學殘置＝sweep `^(EDU|DUAL|PING 2|PING 3)` 設計性跳過、limits=0 無實害）；**同進 start G28 後插 M6050 S0.5**；process 全 FD 值（層高 0.125/0.2/0.3/0.5）只歸零加速度/jerk；預設線材 Classic 220（1 槽 SEMM=0）。C++＝`build_mixed_gcode` 加 dual_cmd 參數＋`ping_apply_color_mix` 判「DUAL」開頭插 **M6050 S%.4f**（剝除規則本就含 M6050＝不雙插）＋照片磚 Classic guard。verify 新增：同進必含 M6050 S0.5／單料頭與本體必無 M605x／SEMM=0／完整性 16 model・32 machine／跨層護欄（C++ 必含 M6050 分支）——**反向測試過**（壞掉→FAIL 2 條精準命中）。

**驗證**：verify 389/108 全綠；值層面抽驗 24 機 24 製程（vs FD 源差異鍵全屬預期）；既有 61 檔＝純 setting_id 位移實質差異 0（棧板/PVA/照片磚 +24）；檔名分佈 同進_ 37→49、單料_ 40→52 精準 +12/+12；LAY-11 三卡相鄰。⚠ **C++ 未本地編譯＝隨 T009 CI 首驗**（眼驗項在兩線 commit message）。

**下一棒**：①**等 T009 發車令**（出貨線 push 自動觸發 CI；Eric 可能再湊批）②T008 驗收回報＋8/9 實印（沿前）③D 槽備份 4 份待裁 ④T009 裝機後照 SOP：G 槽上架/T008 輪替/D 槽換裝＋DL1016 重注。

---
### 🏁 收工快照（2026-07-27 凌晨 — **T008 全鏈完成**：build 綠→12 項驗收→G 槽上架→D 槽換裝→conf 清理）

**T008（bundle 75 @ `15bc85d4`、run 30207945408）**：慣性三紅照舊、**Windows 主建置綠＝本批 C++（顏色橋/混色開合標示/測試模型選單/視窗隱藏）CI 首驗全過**。成品 12 項驗收全過（七模式 189 支＝同進37/單料40/雙色36/易拆58/3in1 6/照片磚5/四色5，關門 +15 精準吻合）。上架＝installer `9FF22B3C…A185` 101.3MB／portable `9CE6801F…AC5F` 133.6MB、G 槽 hash 一致、T007 輪替 old\。**Eric D 槽已換 T008**（預授權；備份 `-old-v360T007-0727`、DL1016 重注 10+10、87/192/30 全過）；**conf 3in1 換名清理完成**（裝機後模式、19 處含 orca_presets、backups 在）。登錄簿 T008 行已結案。
**下一棒**：①收 T008 驗收回報（版本資訊六項＋Eric 六驗）②Classic 變體實作（DUAL 四台＋M6050 S 舊插法——規格與接點見下方快照）③D 槽備份 4 份待 Eric 裁清 ④8/9 實印回報。開發線 workshop 未 dispatch（Eric 要再說）。

---
### 🏁 收工快照（2026-07-26 晚二 T007 驗收批 — 三裁落地：顏色橋／混色開合標示／FD300 關門；押 T008）

**驗收記分板（Eric 實測）**：1 縮放座標系 ✓／3 溫度視窗 ✓（實截圖＝#33 視窗）／4 混色狀態行 ✓（兩態截圖）／5 組合連動 ✓／6 色塊消失 ✓／7 同進檔名 ✓——**1-7 全過**；2 顏色連動＝連動路徑真 bug（本批修）；8/9 實印待回報。

**三裁落地＝兩線各 2 顆 commit、未 push（Eric 令「先不要 build、還有其他要改」＝T008 湊批中）**：
| 批 | 開發線 | 出貨線 | 內容 |
|---|---|---|---|
| C++ | `b0722805` | `48bd996c` | ①連動換線材補槽位色橋（`update_ams_color` 升 public＋`ping_apply_combo_filaments` 兩分支收尾補呼叫＝與手動下拉同一條橋）②混色開合直寫狀態：展開標題「混色啟用（雙料/四料）」／收合浮鈕「混色停用」（直排高 64→116） |
| 關門 | `099e2e44`（bundle **63**） | `27f67e54`（bundle **73**＝T008 候選） | FD300 關門：kind=**dual1**（只出雙料本體）＋BED_OVERRIDE 縮床 200（高度沿用＝height 改可選鍵）；直線預擠 +50 內移（P200+ 同幾何）、弧白名單天然不套；機 3＋model 1＋製程 15＋cover 空白卡＋縮圖；guide 21/24 家族正則加「關門」；列內序 FD300→同進→關門→單料頭（＝Eric 指定；**開發線 `_variant_rank` 順帶對齊出貨線 0715 裁「單料頭放最右」＝既有漂移補正**） |

驗證＝兩線 regen＋verify 全綠（309/76、337/84）＋關門抽驗全過＋**值層面稽核 v3＝實質鍵值差異 0**（其餘 202/672 檔＝setting_id 位移，FAMS 中段插入預期效應）。⚠ 稽核工法坑：git 對 CJK 路徑輸出加引號＝首版腳本漏檢，v3 改 `ls-tree -z`＋`cat-file blob <hash>`（雜湊當參數＝繞開編碼）。

**🔶 Classic 變體＝規格已收齊、下一棒實作（工程量大）**：DUAL 300/450/600/800 補 同進＋單料頭、口徑照 FD 對應機、參數繼承照 FD（Marlin 隔離不動）；**同進混色＝`M6050 S<比例>` 舊格式**（Eric 明示「用舊的方法安插」）。接點已盤：`PingColorMix.cpp:212` 現行 `M6051 S%.4f` **同構單參數**＋`BackgroundSlicingProcess.cpp:210` 同進判定（printer_model 含「同進」→FF=M6052/FD=M6051）⇒ 差「Classic 判定＋指令字」分支；PingColorMix 剝除規則本就含 M6050（`:112`）＝不會雙插。⚠ 開放問題：單料 Classic（EDU 200 等 4 台）要不要也補＝已列待確認問 Eric。

**★ 同晚追加批（同 session 續，Eric 邊驗邊裁）**：
| 批 | 開發線 | 出貨線 | 內容 |
|---|---|---|---|
| 測試模型 | `64fef482` | `715e1014` | 「新增測試用模型」PING 件置頂（resources 檔名 ASCII＝避 narrow path 編碼雷、顯示名中文；3mf 走 Orca Cube 同載入路徑） |
| 抽件＋視窗 | `9bf155cf` | `f9314023` | Eric 裁 C＝抽法鬥(31MB)/摩埃(11MB)、留三件 ~4MB；實體列印設備視窗藏未用欄位（主機類型/代理/設備UI/API金鑰/CA+說明/吊銷——`update()` 尾端統一 hide 蓋過各分支 show、只藏不改值） |
| 3in1 合一 | `cb061ffe`（bundle **64**） | `608504e6`（bundle **74**＝T008 候選） | Eric 裁 C＋統一值照 0.4/0.6：六支併 `PLA(3in1)`/`SupPLA(3in1)` 各一、**不綁機**、renamed_from 舊三名（字串）；範本 6→2＋8 個機器/機型範本引用改名＋`THREE_IN1_MERGED_AWAY` regen-durable＋verify 12b「舊口徑別名不得復活」。**真因**＝3in1 支每口徑一支且綁機 × 精靈可見清單只收勾過的口徑 ⇒ 沒勾過口徑的預設支「存在但不可見」→ 預設套用 fallback（Generic ABS 事件；Eric conf 僅 0.6 兩支實證） |

**🔴 conf 時序雷（下一棒必讀）**：`tools/ping/patch_conf_3in1_visible.py` 兩模式——**T008 裝機前只可 `--pre-t008`**（只加可見 17→23、不刪不換名；看門狗 0726 晚已掛、Eric 關 app 自動跑）；**T008 裝機後**才跑預設模式（換名清理、含 orca_presets）。**裝機前換名＝斷現行 T007 選擇。**

**🔴 下一棒**：①收 Eric「其他要改」清單 → 一起入 T008（**兩線各 5 顆 code commit 未推**：C++ 批/關門/測試模型/抽件+視窗/3in1 合一；bundle 64/74）②Classic 變體實作（DUAL 四台限定＋同進混色 M6050 S 舊插法，接點見上）③8/9 實印回報＋build 後眼驗（各 commit message 有眼驗項）④T008 裝機後：conf 換名清理＋D 槽換裝（DL1016 備援重注照 SOP）。

---
### 🏁 收工快照（2026-07-26 晚 收尾棒 — D 槽換裝 T007＋skill 回填三項＋牌桌收攏）

**本棒三件事（皆完成、皆驗證過）**：
1. **Eric D 槽 portable 換裝 T007**（Eric 令「D 槽也放最新的」）：守衛（app 未執行，fail-closed）→ `_staging` zip sha256 實算＝登錄簿登記值 `239FB380…6981` → T005 整夾改名備份 `D:\PING-Slicer-portable-old-v360T005-0726` → 解壓（44 項、內容直出佈局）→ **DL1016 備援重注**（`DL1016_本機注入備援/` 10 檔＋cover＋PING.json 10 條註冊 1/3/3/3、**版號維持 72＝0725 兩次先例不抬**）。驗證全過：bundle 72／機 84・製程 177・線材 34（＝T007 基線 81/174/31＋DL1016 3/3/3）／`renamed_from`＝str／無效顏色鍵 0／PVA 回抽 3／照片磚 `enable_support`=0／Classic DUAL 600 支撐角 35。appdata（69）未動＝Eric 開 app 自然收編 72、DL1016 隨 portable 帶走（T005 收編已證此鏈：appdata 69 現有 DL1016 1/3/3/3）。⚠ **備份現 3 份**（v355ws0722／v360T004fix0725／v360T005-0726）超出「留兩個」慣例＝照先例不自動刪、留 Eric 裁（v360T004fix0725 內容物＝DEFECTIVE T004 修補版、回滾價值低）。
2. **skill 回填三項補齊**（0725/0726 兩棒懸帳）：ping-slicer `materials.md`＝①PLA+PVA 專屬製程已出、歸易拆（⏳ 待裁句轉 ✅；檔名前綴 `易拆_`＝`embed_params.py:379` 實碼）②**樹狀支撐保守配方**節（**hybrid 前提**＝預設池 normal(auto)+snug 不變、手動切「混合樹」才生效；欄位分組引擎硬分 `ConfigManipulation.cpp:750-758`；甲組 7 鍵＋`_organic` 防呆 2.6/40）③**ABS 整併記錄**（`renamed_from` 字串鐵則＝T004 死因／`find_preset()` 不走 renamed_from ⇒ C++ 硬寫名靜默失效坑／PA 分流量現況表＋單向護欄）；**＋過期活規則修正**＝臨界角 35 豁免句「Classic 前代不套」→「已跟進」（0725 三裁）。commit `6710f76`、定向單檔同步三方 hash `2862ec5b`、validate 全綠（`core-rules.md`／`maintenance.md` 他線未提交改動仍未碰）。
3. **牌桌收攏**：c-0726-T7-01（前棒漏銷、工作早已閉環）補銷；本棒 c-0726-T7-02（env:portable 覆蓋類）掛→銷完整；PM 簿 x-0726-ORCA-01（skill 單檔）掛→銷。

**🔴 下一棒＝收驗收回報，工程側無懸帳**：①Eric 待驗清單 9 項（縮放座標系／線材顏色連動／溫度確認視窗 #33／混色狀態行 #26／組合製程連動 ABS+ABS・PLA+PVA・棧板／材料色塊消失／檔名七模式／支撐實印／Classic 前代實印——D 槽開 T007 即可逐項走）②同事 T007 回報（版本資訊六項）③開發線 workshop 30173085575（bundle 62）成品未抓＝Eric 要裝再抓。
**🟡 未決沿前**：「成品能不能起得來」自動關卡提案（build 後 headless 載入抓 `load config file ... Failed`）仍待裁；D 槽備份 3 份留 Eric 裁。

---
### 🏁×7 收工快照（2026-07-26 0725-0726 續棒 — T004 事故／T005／T006 VOID／T007 建置中）

**線況**：開發線 `ping/v3.5` tip **`4aa2578a`**（bundle **62**，已 push）｜出貨線 `release/v3.6` tip **`667825dd`**（bundle **72**＝T007，已 push）｜兩線工作區乾淨｜untracked `resources/web/mixer/`、`sandboxes/`＝他線勿動。

**✅ T007 已上架 G 槽（收工後 build 綠、順手做完，下一棒不必再處理）**：run 30172821731 @ `667825dd`、bundle 72；
Windows 主建置綠、慣性三紅照舊；**成品驗收八項全過**（含新增三項：`renamed_from` 型別／無效顏色鍵 0／檔名七模式＋舊佔位符 0）；
installer 100.4MB `1881A281…9F59`／portable zip 132.2MB `239FB380…6981`，G 槽實檔 hash 一致；T005 輪替回 `old\`。
版本資訊開頭明寫 T004/T006 作廢與改裝指引，驗收重點六項。成品夾 `_staging/v3.6-T007-30172821731/`。
⏳ **開發線 workshop build 30173085575**（bundle 62 @ `4aa2578a`）＝Eric 要裝再抓，否則記錄即可。

**🔴 下一棒最優先（原本的 build 交棒項已完成，改為以下）**

| build | run | 內容 | 綠後要做 |
|---|---|---|---|
| **T007 出貨線** | **30172821731** | bundle 72 @ `667825dd` | 抓 Windows portable 驗內容 → 打包 → **上架 G 槽根層、T005 輪替 old\** → 版本資訊 → 登錄簿結案 |
| 開發線 workshop | **30173085575** | bundle 62 @ `4aa2578a` | Eric 要裝再抓；否則記錄即可 |

驗收流程照 T005 前例（`_staging/v3.6-T005-30155879901/` 有完整範例：zip → sha256 → 複製到 G 槽 → hash 複驗 → 舊 T 輪替 → 版本資訊）。

**成品驗收清單（本輪新增前三項，前兩顆就是靠它們才沒再出事）**
1. `PING ABS.json` 的 `renamed_from` **必須是字串**（T004 死因）
2. 線材檔**不得有** `filament_colour`／`filament_colors`／`default_filament_colors`
3. **檔名七模式**分佈正確 ＋ **零舊佔位符**（掃 `{print_time_hm}`／`{total_weight_str}`／`經典_`／`Mix_` 應全 0）
4. bundle 72 ／ 5. 檔名新格式 ／ 6. Classic 新工藝 ／ 7. 照片磚 `enable_support`=0 ／ 8. PVA 回抽 3

**★ 本棒發生什麼（依時序）**
1. **Eric 0725 三裁落地**：Classic 前代 8 機**套** F 系新工藝（取消豁免；verify 反向斷言由「豁免破功」翻成「跟進破功」）／照片磚 `enable_support` 關／PA 0.12 只限一般流量（實查現況已符合＝零參數變更，改為 verify 單向護欄）。
2. **兩線一致性稽核**（Eric 問「23 顆是否有些要落在出貨線」）：197 檔逐一比內容 ⇒ **只有 1 個真缺件**＝`PING PVA` 回抽長度 3 沒移植（出貨線 sweep 少寫 `or "PVA"`），已補 `ff074ceb`。
3. **🔴 T004 發車 → 上架 → 判定 DEFECTIVE 撤下**：`renamed_from` 寫成陣列 ⇒ 整包 vendor 載不進去 ⇒ 開起來沒有任何 PING 機型、跳設定精靈、機器掉 Default Printer。Eric 換裝後回報，機上 log 定罪。修＝`a50413a5`／`410d7c44`。T004 已改名標 DEFECTIVE 移入 old\。
4. **T005 發車＋上架**（bundle 69）＝T004 內容＋兩顆修正；Eric D 槽亦換裝 T005。
5. **Eric 0726 回報兩件**：選 PLA+PVA 不跳 PVA／選 ABS+ABS 兩槽不動 ⇒ 同一根＝`Tab.cpp` 連動表沒跟上 profile（**ABS 整併造成的迴歸**＋PLA+PVA 漏補），修 `b0488110`／`59f92e26` ＋ **verify 跨層護欄兩項**。
6. **顏色機制定調**（Eric）：材料色只負責「切材料時帶進槽位色」，槽位色可手動改且不被蓋回 ⇒ **不再顯示材料色塊**（側欄＋下拉）＝`b3c36da5`／`13646736`。
7. **檔名模式定稿 7 種**：`Mix_`→`同進_`、照片磚獨立成 `照片磚_`、**取消「經典_」**（Classic 改用實際模式：雙料→易拆、單料→單料）＝`6a00acc0`+`4aa2578a`／`3512acf2`+`667825dd`。
8. **T006 標 VOID**（build 中 Eric 追加兩裁，成品未產出即過時、未上架未發布；號碼不回收）→ 改發 **T007**。

**★ 已驗收（Eric 實機）**：#30 物件移動座標系 ✅／輸出檔名新格式 ✅（`雙色_FD300(0.4)_3DBenchy_3H_38g.gcode`）——兩件都已傳話「0725 回報與驗證中心」session 結案。

**★ 待驗（T007 上架後）**：縮放座標系／線材顏色連動／溫度確認視窗 #33／混色狀態行 #26／組合製程連動（ABS+ABS・PLA+PVA・棧板）／材料色塊已消失／檔名七模式／支撐實印／**Classic 前代機實印**（這版起吃新工藝，行為若異務必回報）。

**★ 沉澱到 SOP（不要只讀 handoff）**：`00治理文件/SOP_參數入版紀律.md` 新增「型別與跨層陷阱」七條——`renamed_from` 必須字串／`filament_colour` 非合法鍵／`find_preset()` 不走 renamed_from（C++ 硬寫名整併後靜默失效）／**產生器掃不到的來源要各自處理＋改完回頭數數量**／`profile_validator` 擋不住型別錯（勿誤用）／兩線稽核比內容不對標題／整檔覆蓋前必先 diff。**全部實測驗證過。**
↳ UX 筆記 6 條已 append `D:\dev\2026claude\UX筆記收件匣.md`。

**🟡 未決／待裁**
- 「成品能不能起得來」仍**無自動關卡**——提案：build 後跑一次 headless 載入抓 `load config file ... Failed`（未做、未驗證可行）。
- ~~Eric D 槽 portable 現行安裝＝T005；T007 綠後可再換~~ → ✅ **0726 晚已換 T007＋DL1016 重注**（見頂部收尾棒快照；備份現 3 份留 Eric 裁）。
- ~~上一棒遺留的 skill 回填三項仍未做~~ → ✅ **0726 晚補齊**（materials.md，commit `6710f76`；見頂部收尾棒快照）。

↳ 認領牌 c-0725-T4-03～08 全銷；Klipper 簿 c-0725-OR-01（.158 唯讀診斷）已銷。

---
### 🏁🏁🏁🏁🏁🏁 收工快照（2026-07-25 深夜 續棒 — 使用者回報批三張單全落地：#26 加固／#33／#30）

**線況**：開發線 `ping/v3.5` tip＝**本 handoff commit**（**27 顆未推**，遠端 `95bf5a7c`；碼/參數的最後一顆＝`b156a19e`；bundle **59**）｜出貨線 `release/v3.6` tip **`1150af89`**（**14 顆未推**，遠端 `53d4f273`＝T003；bundle **68**＝T004 候選）｜untracked `resources/web/mixer/`、`sandboxes/`＝他線勿動。**全部續押 T004、等 Eric 發車令。**

| 單 | 開發線 | 出貨線 | 內容 |
|---|---|---|---|
| #26 加固 | `50df716d` | `d38ac33f` | 上傳對話框「混色：啟用／停用」狀態行（同進機才顯示） |
| #33 | `88b47560` | `ea2586c2` | 一噴頭多料機兩支料目標溫度不一致 → 切片前確認視窗 |
| #30 | `7ac65f9c` | `b5270ff5` | 物件**移動**預設座標系改「物件座標」（照 V2.1） |
| #30 追裁 | `b0a04496` | `3b7d0eef` | **縮放**預設座標系也改「物件座標」（Eric 追裁） |

三顆移植前兩線 blob 皆**逐位元相同** ⇒ patch 乾淨套用、**兩線 diff 逐位元一致**（28cc3337／ee16ea13／2643b747）。⚠ **三張單的 C++ 都未本地編譯＝隨 T004 CI 首驗**，眼驗項寫在各自 commit message。

**🔴 #33 的關鍵事實（與直覺相反，下一棒別再走冤枉路）**——「噴頭同一組加熱」在 Orca 的判準是 `single_extruder_multi_material`，**不是機型名含「同進」**：
- **SEMM=1（一噴頭多料、會踩溫度停等）**：FD300／FD300 Pro／FD450 Pro／FD600 Pro／FD800 Pro＝**2 槽**；FF600／FF800＝**4 槽**；3in1＝2 槽；照片磚系
- **SEMM=0（Orca 眼裡只有 1 槽、設不出兩種溫度）**：**同進系**、單料頭系、FP300
- ⇒ **同進機反而不是受害者**（混色走 M6051/M6052 後插碼，引擎只看到一支料）。槽數來源＝`GUI_App.cpp:7300-7308` 依 `default_filament_profile` 數量初始化（SEMM=0 才吃 `nozzle_diameter` 數量）。
- 停等機制已在碼上證實：`GCode.cpp:852-853` 換料時比對前後線材的 `nozzle_temperature`／`nozzle_temperature_initial_layer` 後插變溫並等待。
- 實作：`Plater::priv::ping_confirm_filament_temperature(bool all_plates)`，插 `on_action_slice_plate`／`on_action_slice_all` 最前面（只有主動切片才問、背景切片不受干擾）；只比 `PartPlate::get_extruders(true)` 實際用到的槽；昂貴的 `full_config()` 擺在兩道早退之後。

**🔴 #30 的真因與連帶效應**——世界座標的位置以**模型中心點**為準：物件已貼地，Z 欄仍顯示 45.00，使用者誤判成浮空（Eric 實圖佐證）。切「物件座標」後欄位變**「平移（相對）」、X/Y/Z 全 0.00**＝正是 V2.1 移動面板的顯示方式 ⇒ **相對位移是要的行為，不是要迴避的副作用**（上一棒差點把它當成阻礙）。
- 改在 `GLGizmoMove3D::change_cs_by_selection()`——那裡本來就是「每次改選取依型別重設座標系」，所以不是改 default 常數、是改規則：單一整個物件（`is_single_full_instance`）也給 Instance。多選與換料塔維持 World（下拉本來就沒有「物件座標」可選，`GizmoObjectManipulation.cpp:882-889` 的 `modes.pop_back()`）。
- ✅ **連帶已裁並跟進（Eric 追裁「縮放也預設物件座標」）**：`m_coordinates_type` 是移動／旋轉／縮放**共用**的一個狀態，而 `GLGizmoScale3D::change_cs_by_selection()` 對單一整個物件原本**不設值＝沿用現值** ⇒ 顯示什麼取決於使用者先開哪個工具（行為會飄）。已明寫 Instance＝兩面板一致：開發線 `b0a04496`／出貨線 `3b7d0eef`（兩線 diff 逐位元一致 9ebfd04d）。合法性已查：縮放下拉為 `{世界／物件／零件}` 三項，單一整個物件不觸發 `pop_back` ⇒ Instance(index 1) 恆合法（`GizmoObjectManipulation.cpp:1232-1242`）。**旋轉面板沒有座標系下拉、不受影響。**

**★ 追加批（0725 深夜續，同一棒）**——三件，兩線各再入版：

| 件 | 開發線 | 出貨線 | 內容 |
|---|---|---|---|
| #26 修正 | `083d5f38` | `10fdbaa6` | **混色狀態行插錯對話框**→移到 `PrintHostSendDialog` |
| 三裁 | `d2a9fa3c`（bundle **59**） | `58e42376`（bundle **67**） | Classic 套新工藝／照片磚 `enable_support` 關／PA 分流量護欄 |

🔴 **`SendToPrinterDialog` 在 PING Slicer 走不到（下一棒別再插錯）**：`MainFrame.cpp:2097-2118` 對非 BBL 廠商把 `support_send=false`、「傳送」鈕根本不建立；`use_bbl_network()=is_bbl_vendor() && !bbl_use_printhost`（`PresetBundle.cpp:545`）對 PING 恆 false。**PING 按「列印」走的是 `on_action_print_plate` → 非 BBL 分支 → `send_gcode_legacy()` → `PrintHostSendDialog`**（`Plater.cpp:16125`）＝使用者真正看到的上傳對話框。

**★ Eric 0725 深夜三裁**（`d2a9fa3c`／`58e42376`）
1. **Classic 前代 8 機套 F 系新工藝**（出貨線專屬——Classic 只在 release 線 emit）：取消 `emit_classic` 還原塊＋`_classic_filament` 的 `overhang_fan_threshold` pop。行為變更＝懸空降速 關→**開**(50/50/25/10)、橋接 1→**0.95**、支撐角 30→**35**、樹狀改保守配方＋牆圈 1、organic 2→2.6・60→40；線材補 25%（3 支）。**口徑安全已查＝CLASSIC_SPECS 每台 `nozzle == src_nozzle`**（0.4→0.4／0.6→0.6）⇒ 母檔口徑連動值直接成立。**Marlin 隔離未動**（加速度/jerk 全 0、不送 machine limits、無韌體回抽/PA）。verify 反向斷言由「豁免破功」**反轉成「新工藝跟進破功」**。
2. **照片磚 `enable_support` 1→0**（兩線各 5 支）。
3. **PA 0.12 只限一般流量＝零參數變更**（實查現況已符合）→ verify 加**單向護欄**：高流量／3in1 不得為 0.12。現況表寫進 verify 註解當權威。

**🔴 下一棒最優先**：❶ **等 Eric 發車令 → T004**（開發線 22 顆未推／出貨線 12 顆未推）❷ 上一棒的 skill 回填三項（見下方 0725 T004 全帶線快照）仍未做 ❸ 本輪新增 skill 回填候補：Classic 由「豁免」翻為「跟進」新工藝（含 `_classic_filament` 讀磁碟母檔＝非冪等來源的坑）、PA 分流量表。

**★ 兩線一致性稽核（Eric 0725 深夜問「23 顆是否有些要落在出貨線」→ 內容層實比，不是對標題）**
把開發線這批動到的 **197 個檔**逐一與出貨線 HEAD 比對 ⇒ 136 個完全相同、60 個不同，
其中 186 個 PING profile 忽略 `setting_id` 等編號類後逐鍵比 ⇒ **184 個值完全一致**。
**只抓到 1 個實質缺件（已補，出貨線 `ff074ceb` bundle 68）**：

> 🔴 `PING PVA` 的 `filament_retraction_length`：開發線 `3`／出貨線 `nil`。
> 根因＝`01148acf` 全批移植時，回抽 sweep 的分支條件漏了 PVA
>（出貨線 `if "TPE" in bn:`／開發線 `if "TPE" in bn or "PVA" in bn:`）⇒ PVA 掉進 else 拿 nil＝繼承 1.3。
> **verify 沒抓到，是因為出貨線根本沒有 `PING PVA` 線材本體的斷言**（已一併補上 10 鍵）。
> 補完複驗＝**186 個共用參數檔實質差異 0**。

**其餘 60 個「不同」的判定（都不是漏移植）**：
- `PING.json`（bundle 版號＋Classic 條目）、`embed_params.py`／`verify_profiles.py`（出貨線多 Classic）＝**設計如此**
- 55 個 profile ＝ **只有 `setting_id` 編號差**（出貨線多 Classic 8 機 ⇒ 全庫 id 位移），值全同
- `PING_HANDOFF.md` ＝ 兩線各有各的
- `GUI_App.cpp` ＝ 只差 1 行註解措辭（已知良性，未動）
- ✅ `PingMixEditor.cpp` ＝ 曾是**反向差異**（出貨線多一段原生調色盤定位修正），**Eric 裁「回灌」→ 開發線 `b156a19e` 整檔對齊，兩線現逐位元相同**
- 開發線這批中 6 顆是 handoff 文件（出貨線有自己的）、1 顆 `2461c9e1`（支撐角 60）已被 `53f7c089` 的 35 推翻＝**不該移植**（出貨線從未被 60 汙染）

✅ **guard 缺口已補（Eric 裁「verify 也補」）**：出貨線 verify 補上「懸空冷卻閾值 25%」（`1150af89`）。刻意放在 Classic 排除區塊**之外**——Classic 套新工藝後 4 支 Classic 線材也吃 25%，實測 25 支全庫皆 25% ⇒ 不需豁免。**做過反向測試**：故意改壞 Classic 210 → verify FAIL 1；regen 還原 → 全綠（證明這條不是永遠不會失敗的裝飾）。

**★ 稽核終態（兩件修完後複驗）**：197 檔中兩線逐位元相同 **139**；仍不同的只剩 5 個且全是設計如此——`PING_HANDOFF.md`（各線自有）、`PING.json`（版號＋Classic 條目）、`embed_params.py`／`verify_profiles.py`（出貨線多 Classic）、`GUI_App.cpp`（1 行註解）。**共用參數檔 186 個實質值差異 ＝ 0。**

**★ 跨線轉交（已完成，不用再處理）**：劉鈞豪回報的機端「Unable to open file」已上 .158 查證定讞＝**PING webui 檔案頁「重新命名」**用「下載→重新上傳→刪舊檔」實作（10MB 跑 15～27 秒、零進度回饋＝他說的「沒有動作」；開印時拿到未刷新的舊檔名 → `virtual_sdcard.py:568` KeyError）。**切片端無關**（`OctoPrint::upload` 是單一請求帶 `print=true`＋單一檔名）。建議改用 Moonraker 原生 `/server/files/move`。已 send_message 給 0725 Klipper session，結論寫進 Klipper `00治理文件/認領簿.md` 的 `c-0725-OR-01`。
✅ **已結案（機台線同日回覆）**：根因與切片端排除經覆核成立；webui `pages.js` 1.41→**1.42**（`19b4bd8`）三項修法全做，.158 實測 7.6MB move **0.03 秒**（原 15–27 秒），**Eric 網頁實走驗收「改名 OK」**。
🔴 **我在該案犯的一個錯（記著別再犯）**：回報時寫「註解自陳『不修改原檔的下載時間』」＝**錯**，母版註解實為「讓修改日期更新為當下時間」，**意思相反**。錯因＝讀機上 `pages.js` 時終端把中文顯示成亂碼，我依上下文推讀成通順中文就當引文用——**那是改寫不是引用**。**鐵則：非 ASCII 內容要嘛用 hex／正確解碼取證，要嘛就不要加引號。** 實質影響＝那段「下載+重傳+刪舊檔」是**刻意**的（讓改名後的檔跳到列表最上面，列表依 `f.modified` 排序），不是繞遠路；換 move 會連帶拿掉該 UX 行為（Eric 已裁接受）。

↳ 認領牌 c-0725-T4-03（混色狀態行）／c-0725-T4-04（#33＋#30）皆已銷。

---
### 🏁🏁🏁🏁🏁 收工快照（2026-07-25 T004 全帶線 — 樹狀配方／照片磚統一／PVA 製程／出貨線全批移植）

**線況**：開發線 `ping/v3.5` tip **`0a5d1df3`**（**10 顆未推**，遠端 `95bf5a7c`）｜出貨線 `release/v3.6` tip **`6ed1ad6d`**（**3 顆未推**，遠端 `53d4f273`＝T003）｜untracked `resources/web/mixer/`、`sandboxes/`＝他線勿動。

**Eric 0725 四裁全落地**：①T004 走 **A 案全帶**（0724 批＋0725 全部一車帶齊）②PLA+PVA 專屬製程「出」③樹狀配方照表做（**混合樹**／牆圈維持一圈／填充空心）④照片磚支撐參數**全部統一**（取消豁免）。

| 線 | commit | 內容 | bundle |
|---|---|---|---|
| 開發 | `fa3ecb90` | 樹狀保守配方（149 支）＋照片磚支撐統一（5 支） | 54→55 |
| 開發 | `0a5d1df3` | PLA+PVA 專屬製程 15 支 | 55→56 |
| 出貨 | `01148acf` | 0724-0725 全批源移植（爬坡／支撐角 35／PVA 線材／懸空冷卻／樹狀／照片磚／PVA 製程） | 63→**64**＝T004 |
| 出貨 | `6ed1ad6d` | #24/#25 混色提示框修（cherry-pick `766136f5`，單檔 PingMixEditor.cpp） | — |

**verify**：開發線 **292 presets 全綠**／出貨線 **320 presets・81 machines 全綠**（皆 exit 0，真實 exit code 已用檔案重導向確認——`| tail` 會讓 `$?` 抓到 tail 的碼）。

**★ 樹狀支撐配方（Eric 0725 定案）**——前提：**預設仍是普通支撐＋緊貼 snug，本組只在使用者手動切「混合樹」後生效**。
- 選型鐵證：官方 tooltip「hybrid 在大面積平懸空下產生類似普通支撐的結構」；且易拆系（Z 間距 **0**＋專用支撐料槽 2＝靠材料不相熔剝離）密實介面鋪得完整＝正對症；單料頭/同進系（Z **0.2**＋無專用料＝靠空氣間隙剝離）樹狀為點接觸 ⇒ 能用但非首選。
- 甲組（hybrid 吃）：分支直徑 **口徑×12**（引擎上限 10 ⇒ 1.0 取 10）／分支距離 **口徑×6**（新增口徑連動，直徑/距離恆為 2.0）／角度 **30**／`auto_brim` **0**（★必須關，`TreeSupport.cpp:2068` 開著時手設 brim 被完全忽略）／brim **10**／牆圈 **1**／填充維持空心。
- 乙組（organic 防呆）：`_diameter_organic` 2→**2.6**（🔴 bug 修：`Print.cpp:1532` 硬限 ≥2×支撐線寬，FF600/FF800 的 1.0 口徑線寬 1.02 需 ≥2.04，舊值會讓那 4 支**勾樹狀即切片報錯**）／`_angle_organic` 60→**40**。
- ⚠ **引擎硬知識（改樹狀前必讀）**：`SupportParameters.hpp:173-180` 雙向 fallback——**snug＋樹狀會被退回 default＝有機樹**（所以未切樣式時吃的是乙組）；**樹狀樣式＋普通類型也會退回 default＝Grid**（所以 profile 預設**不能**設成 hybrid，會打壞 0722 的 snug 定案）。欄位分組硬分於 `ConfigManipulation.cpp:750-758`（`_organic`／tip_diameter／top_rate／angle_slow／branch_diameter_angle 屬 organic 專屬，切 hybrid 後不生效）。

**★ PLA+PVA 專屬製程 15 支**：從同口徑 PLA+SUP 雙生派生（emit 接棧板之後＝既有 id 零位移）。覆蓋四項＝支撐角 **50**（案值 Cura 40 換算）／線距 **口徑×19**（密度 5%）／塔 **45**／brim **口徑×20**（案值 20 條換算）；易拆幾何（Z0／XY 口徑×0.75）、層高與速度走家規（刻意未套案值層高 0.35／速度全 60）。⚠ 支撐角與 brim 為**跨基準換算值**，待工程端實機驗證。

**🔴 三個新發現（下一棒必讀）**
1. **Classic 前代 8 機會被 F 系新工藝夾帶**——Classic 製程由 Fast 母檔複製 ⇒ 爬坡品質/支撐角/樹狀全被蓋，而它**自有的懸空降速本來是關的**（enable 0、80/50/50/50、bridge 1、支撐角 30）。已依 0719「Classic 不套預擠點升溫」先例在 `emit_classic` 還原，並加 verify **反向斷言**「Classic 前代豁免破功」防下次 regen 再犯。**要不要套新工藝＝待 Eric 裁。**
2. **`_classic_filament` 讀的是磁碟母檔（非冪等來源）**——母檔在上一輪 regen 已被 sweep 寫入值 ⇒ **光在 sweep 端排除 Classic 擋不住**，必須在複製處 pop。例外＝母檔 `PING PLA - 220` 0724 前就自帶 25%（既有值），無條件 pop 會誤刪——**這是文字 diff 看不出、只有值層面逐鍵比對才抓得到的一類**。
3. **照片磚 `enable_support`＝1（開啟）**，只是磚體平貼床無懸空面所以不生成支撐。Eric 裁的「統一」已做（tree(auto)+default→normal(auto)+snug 等 6 鍵）；要連開關關掉＝產品決策，待裁。

**★ 驗證工法（本輪沉澱，建議沿用）**：`git diff` 的文字 diff 會被**尾逗號位移**與 **CRLF/LF** 干擾而失真 ⇒ 改用**值層面逐鍵比對**（`git show HEAD:<file>` vs 現檔，逐 key 比 changed/added/removed）。⚠ 取檔案清單務必用 `git diff --name-only **-z**`——中文檔名會被 git 轉義成引號包裹，用 `.json` 結尾過濾會**整批漏掉中文檔名**（本輪首跑就漏了照片磚，74 檔沒比到）。

**🔴 下一棒最優先**：❶ **等 Eric 發車令**（出貨線 push 自動觸發 CI／開發線需手動 dispatch `gh workflow run build_all.yml --ref ping/v3.5`）→ 綠後照 T003 流程上架 T004 ❷ 待裁三小項：Classic 要不要套新工藝／照片磚 `enable_support` 要不要關／**混色「啟用/停用」狀態行**（Eric 已裁「做」，本輪 context 不足未做——**接點已探明**：`plater->is_ping_tongjin_selected()` ＋ `plater->is_ping_mix_enabled()`，同 `GCodeViewer.cpp:1130` 用法，插 `SendToPrinter.cpp`）❸ skill 回填：`materials.md` 的「易拆 vs 一般」判定法要加 **PLA+PVA 歸易拆**（verify 首跑即抓到此誤判）。

**★ 追加批：使用者回報批（0725 晚）**——Eric 令「**接下來都塞 T004**，我還有很多要修正」＝繼續累積、發車另候。
- ✅ **#37 ABS 整併 3→1**（開發線 `2d30f9bc` bundle **57**／出貨線 `e5b0810b` bundle **65**；verify 290／318 全綠）。三支實測＝溫度/床/風扇/purge **完全相同**；`PolyABS` 與 `ABS` **逐鍵完全一致＝純副本**；`ABS-250` 只因繼承鏈不同（跳過 `fdm_filament_abs`）而多出流量比 0.98／最大流量 30／**PA 0.12 開**。保留 `PING ABS` 收編較佳值＋**`renamed_from`** 舊名相容（`Preset.cpp:2084` 拿舊名比對 system profile 的 renamed_from ⇒ 客戶舊 3mf 自動對應、不會變未知 preset）。產生器加 `ABS_MERGED_AWAY` 過濾＝regen-durable。⚠ PA 0.12 沿用舊值**未經 PA 塔實測**。⚠ **%APPDATA% conf 可見清單未同步**（等 app 關，舊兩支要從清單移除）。
- 🔴 **易拆顏色回報＝前提不成立，動手前先問清楚**：劉鈞豪要「易拆預設色與 PLA 不同（像白色）」，但查證發現**全部支撐料早就是 `#D3D3D3` 淺灰**、PLA 是 `#EA4E16` 橘，**連 T003（他手上那版）的 SupPLA 也已是淺灰**。⇒ 根因另在，候選：①他 user 層自建同名線材（0714/0718 老坑）②預覽切到「依擠出機(Tool)」著色＝吃 `extruder_colour`（雙槽黑+白、59 台單槽全黑）而非線材色 ③他講的是準備頁非預覽頁。**先要他補「哪個畫面＋截圖」再決定改什麼。**
- ⏳ **#30 物件移動預設座標系改「物件座標」**（符合 2.1 使用習慣）：未評估。UI 下拉已存在 ⇒ 應是改預設值／記住上次選擇。
- ⏳ **#33 兩支材料目標溫度不一致 → 切片時跳確認視窗**：未評估。**關鍵理由（Eric 補充，要寫進規格）＝噴頭是同一組加熱與溫度回饋，設兩種溫度會導致停等**。

**🔧 待回填 skill（本輪確立、尚未進 SSOT，下一棒或 PM 接手）**——動 `ai-skills-source` 需掛跨專案認領牌：
1. `ping-slicer/materials.md`「易拆 vs 一般」判定法 → **加 PLA+PVA 歸易拆**（PVA 為水溶支撐料、與 PLA 不相熔；verify 首跑即抓到此誤判）。
2. 新增「**樹狀支撐配方**」節（甲組/乙組值＋選型依據＋三條引擎硬知識：`SupportParameters.hpp:173-180` 雙向 fallback／`TreeSupport.cpp:2068` auto_brim 覆蓋 brim_width／`Print.cpp:1532` organic 分支直徑 ≥2×線寬硬限）。
3. ABS 整併記錄（三支差異調查結論＋`renamed_from` 舊名相容工法）。

↳ 認領牌 c-0725-T4-01（全帶線）／c-0725-SA-02（appdata 支撐角手術，監看中）；c-0725-SA-01 由 FD600 Pro 列印異常 session 銷牌並回覆停手。

---
### 🏁🏁🏁🏁 收工快照（2026-07-24 PVA＋爬坡品質線 — 新材料入系統／全庫品質批／異常單三張）

**線況**：開發線 `ping/v3.5` tip **`48023ae8`**（**未推 6 顆**＝0723 兩顆〔檔名新格式 `9074f3cb`／選機頁槽位修 `3e64a762`〕＋本輪四顆）｜出貨線 `release/v3.6` tip `4b1a199e`（未推 2 顆，**不含本輪**）｜untracked `resources/web/mixer/`、`sandboxes/`＝他線勿動。

**本輪四顆（bundle 52→**53**，verify 277 presets 全綠）**：
| commit | 內容 |
|---|---|
| `37cad9cb` | **PING PVA 水溶支撐線材**入系統＋**爬坡品質全庫**（懸空降速開＋四段 50/50/25/10＋橋接流量 0.95；線材懸空冷卻閾值 25%） |
| `2461c9e1` | **支撐臨界角 30→60** 全庫（V3.0 底稿殘值翻正，144 製程） |
| `766136f5` | 異常單 #24/#25：混色提示框自身 DC 量測＋300dp 折行、收合鈕「收合 ▶」→「收合」（⚠ **C++ 未本地編譯＝隨下顆 build CI 首驗**） |
| `48023ae8` | PVA 值**對帳 V2.1 定稿案**（劉勝賢提供 3mf）：噴溫 220→**210 全鍵**、回抽勾 **3**＋hop 0.6、purge 60→**85** |

**Eric 本輪裁決鏈**：①PVA「參考 2.1、一般流量即可」→ 案檔一度全網失蹤（池夾空＋成品庫 1715 支 3mf 掃無）→ 先按房規推定 → **當日取得實檔對帳定稿**（教訓：**案檔在工程師手上，直接開口要，別只掃硬碟**——已入 skill）②爬坡品質「一併加入所有的參數」③「支撐角度應該是 60，而不是 30」④#24/#25「修」⑤「四料應該是 M6052」（糾正我給錯的排查指令）。

**#26 混色漸層沒印出＝定讞（切片器/機器/韌體全無罪）**：.29（FF600 Pro Max）唯讀驗屍——巨集 M6052/T0123 齊在、機器 ready；實印檔（印到 91% 才取消）**全檔只有 start 一行 `M6052 A25 B25 C25 D25`、零逐層曲線** ⇒ **匯出當下混色面板是收合的**（B 案設計：收合＝停用）。Eric 向勝賢複驗「都是 25」＝雙向對證。解法＝展開面板後**直接重上傳、免重切**。↳ 已沉澱 `SOP_混色異常驗屍.md`。諷刺點：解釋這規則的兩條提示，正是 #24/#25 壞掉那兩條。

**本機狀態（下一棒別重踩）**：%APPDATA% 手術已跑（12:11，Eric「關了」後）＝**版號 61→62**、PVA 入系統＋conf 可見 23 支、144 製程爬坡＆支撐角 60、11 支線材閾值 25%，備份 `PING.bak-pvaslope0724`、複驗 0 mismatch；PVA 檔於對帳後**熱補為定稿值**（備份 `.v1-220`）。⚠ **appdata 仍不含 filename_format 新模板**（等新 binary，鐵則不變）。

**🔴 下一棒最優先**：❶ **T004 發車前先問 Eric A/B**（待確認檔已列）——**A 案**＝發車前把本輪四顆移植出貨線（params regen **bundle 64**＋C++ 兩顆 cherry-pick），T004 一車帶齊；**B 案**＝T004 照舊發車（bundle 63），本輪走 T005、**裝機後必須重跑 appdata 手術**（T004 收編 appdata 62 會蓋掉本輪）。⚠ 這是本輪唯一的相容紅線。❷ PLA+PVA 專屬製程要不要出（V2.1 案製程層特例：支撐角 40 **⚠與本輪全庫 60 衝突**、支撐密度 5%、塔尺寸 45、brim 20、PLA 側 210）。❸ #24/#25 眼驗（build 後）：提示完整多行、收合字置中。❹ 可選加固：上傳對話框對同進機顯示「混色：啟用/停用」。

↳ 規範正本＝ping-slicer skill `materials.md` PVA 節（commit `39a7d75`、三方 hash 8D3098F9）；驗屍工法＝`SOP_混色異常驗屍.md`；認領牌 c-0724-PQ-01（ORCA）／c-0724-OQ-01（Klipper，READ）／x-0724-02（skill）全銷。

---
### 🏁🏁🏁 收工快照（2026-07-22〜23 支撐調校線 — 支撐配方對齊 V2.1＋線材回抽統一＋T003 上架＋檔名新格式）

> 🆕 **用語改口（Eric 0723 裁，正本 `~/.claude/version-governance.md` §〇）**：**開發線**＝`ping/v3.5`（舊稱「主線/workshop」）；**出貨線**＝`release/v3.6`；版兩態＝**T 候選（TEST-T00x）→ 出貨版**。之後回報一律新語。

**線況**：開發線 tip `9074f3cb`（**1 顆未推**＝檔名新格式；`21715a40..95bf5a7c` 六顆已推已建）｜出貨線 tip `aa8fcd0f`（**1 顆未推**＝檔名新格式、bundle 63＝**T004 候選**；`53d4f273`＝**T003 已建已上架**）｜untracked `mixer/`、`sandboxes/`＝他線勿動。

**Eric 本輪裁決鏈（十餘裁全落地、規範正本全在 ping-slicer skill materials.md）**：
1. **普通支撐配方（七裁+易拆同套）**：普通(自動)／緊貼(snug)／直線＋牆1／獨立支撐層高**關**／XY＝口徑×1／線距＝口徑×9（=密度10%，蓋 7/17 ×8）；行為四項全支撐同套、幾何分流（易拆 0.75×/ABS+SUP 0.5）。Benchy 實測支撐 1h48m→35m；煙囪唇緣 XY=0.6 實測 ✅。引擎知識：獨立層高＝支撐自建層表（預覽隔層＝設計行為）；`;HEIGHT`＝槽差非厚度；**排查三律＝畫的加強＞屏蔽器＞自動／屏蔽只刪接觸面／「只開支撐面」預覽法**（skill 已載）。
2. **線材回抽統一（三裁+兩補裁）**：長度收斂繼承 1.3（特例：高流量家族 11 支勾 2〔HFN3+四料2+3in1×6〕、TPE 3）；額外回填＝流量形式律（高流量 0.6/一般 0.2）；四項統一（空駛3/擦拭開/5/100%）；Classic 前代線材豁免（Marlin 隔離）。**M207/M208 案**（Klipper 線轉交）查畢＝V3.0 Marlin 殘留、7/12 B 案已治本、殘吐＝**同事機 user 自建線材/舊 3mf 快照**（待同事排查）；SET_RETRACTION 未勾也下機（=機器 1.3，與韌體同值等效）。
3. **splash**：版號實際三碼（動態 `format_display_version`）＋字級 3.1%→2.6%（兩繪製路徑同步）。
4. **輸出檔名新格式**：`模式_{printer_model}({nozzle_diameter[0]})_檔名_{print_time_half_h}_{total_weight_g}`——新 C++ 佔位符（Print.cpp：0.5H 無條件進位/整數克進位）。⚠ **profile 與 binary 同車鐵則**：舊 binary 吃新模板炸未知佔位符→ **appdata 的 filename_format 必須等 T004/新開發線 build 裝機後才可同步**（兩線 regen 已含、僅在 repo）。Classic 維持「經典_」舊格式。
5. **T003 全鏈**：出貨線源移植（7 刀＋3 特調：Classic 線材豁免回抽／Classic 雙料 XY=易拆繼承／照片磚 tree 特調不查——後兩者 verify 閘門首跑抓出）→ bundle 62、verify 304 全綠 → build 29965226090（Windows 1h6m 綠/慣性三紅）→ **TEST-T003 已上架 G 槽根層**（hash 複驗一致、T002→old\）。Eric 0723 晨帶去客戶端更新。
6. **版本用語定案**（見頂部）＋T004 候選已備好待車。

**本機狀態（下一棒別重踩）**：%APPDATA% 三場手術全備份（`PING.bak-support0722`／`0722b`／`retract0723`）＝支撐+回抽新預設已生效；**appdata 未含 filename_format 新模板（刻意，等新 binary）**。D 槽 portable＝0722 夜換裝 build 29927073824（備份 `-old-v355ws0719`；DL1016 重注、portable 版號 53<appdata 61 安全）；「留最新兩個」應清 `-old-v360r4` 被系統路徑保護擋＝Eric 手動裁處。主線 build 29964671789＝純參數批（binary 同現裝、無需再換）。

**🔴 下一棒最優先**：❶ **T004 發車**（Eric 令）＝兩線各推 1 顆（出貨線 push 自動觸發 CI；開發線要手動 dispatch）→ 綠後照 T003 流程上架＋**appdata filename_format 同步**（裝機後）❷ 收 T003 驗收回報（同事/客戶端：支撐好拆度/換料缺料/splash 字級）❸ M207 同事機 user 線材排查結果。待裁小項：3in1 長度已勾 2 之後若有違和可退；Classic 檔名要不要換新格式。

**工具坑（已入 SOP_參數入版紀律）**：PS5.1 直改 UTF-8 JSON＝毀檔；一律 python 處理。

↳ 規範正本＝ping-slicer skill `materials.md`（支撐/回抽/排查三律，commits `7f47319..346b93c`）；發布記錄＝`00治理文件/發布登錄簿.md`（T003 行）；本輪認領牌 c-0722-SP-01~c-0723-SP-06 全銷。

---
### 🏁🏁 收工快照（2026-07-19〜20 照片磚線 — 畫質→可印性→接縫三戰役；11 顆 commit 全純網頁/參數層、免 build 即用）

**主線 `ping/v3.5` tip＝`4212ee29`（本 session 範圍 `183a108c..4212ee29`，11 顆，未 push）｜測試線 `release/v3.6` tip＝`fc09e2d3`（遠端在 `8c487d82`＝T001，本地 **5 顆未推**，等下次 build 令＝T002）**

> **下一棒最優先**：❶ **V 溝「不是每層都有」未解**（見下 §未解）❷ C 案準備頁面板 P0 可操作原型（規格已定稿，Eric 等原型實走）❸ 混色鈕在照片磚機隱藏（C++、需 build）。

**Eric 本輪裁決鏈（照片磚從「調不像」到「縫藏起來」）**：
1. **B 案・感知均勻色階**（`18e58ece`）——灰階圖洗白的真因＝**分箱（gamma 均分）與顯色（線性 RGB 均分）兩把尺**＋均分混比暗端有空洞。改 L\* 均分取階＋反解混比、分箱取最近階。灰梯 6 階 ΔE **1.7**。順帶格點 0.1→**0.05mm**（`GRID_MAX` 1600→3200）與 suggest 縮樣塌欄 bug。
2. **口徑選擇＋水平最小可印寬**（`d5e7878f`）——縫隙根因＝**零件水平剖面 < 2×口徑印不出來**（垂直靠層高不受限）。工作室加口徑 0.4/0.6/1.0，`enforceMinHorizontalWidth()` 異向性濾除。Eric 實測「正確了」✅
3. **接縫藏磚體內**（`0f3df88c`→`913c018c`→`4212ee29`）——端面 `paint_seam` enforcer ➜ GUI 實驗發現**「背面」模式壓過 enforcer、要用「對齊」** ➜ 仍有 ~5% 落面 ➜ Eric 裁幾何解「**方塊中間做小 V**」➜ 交界內埋 V 溝（**1.2×0.6mm**，初版 2.4×1.2 被評太大已縮）。
4. **選機 UI 統一＋照片磚成一類**（`13b91e95`＋`d408b375`）——三頁籤 Fast｜Classic｜照片磚；bundle 補照片磚 5 機（出貨線從缺＝FD300 選不到的真因）。
5. **3MF 誤報彈窗修**（`f6def0f0`）＋**user 副本清除**＋**照片磚 5 製程 seam 預設 back→aligned**（`d09ab243`／%APPDATA% 已手術）。

**🔴 未解（下一棒接手點）**：**V 溝只開在「交界垂直穩定段」**（上下列同位交界都存在才開）——**彎曲交界的步進列沒有溝**，Eric 已指出「沒有每層都有 V」。兩條實驗方向（皆未做）：①接縫位置改 **「最近」(spNearest)** 比對——每層獨立選點、無跨層對齊平滑，平滑正是把縫拉離交界的嫌疑 ②放寬穩定段守衛、改逐層開溝（要重驗水密＋確認斜面步進不會產生破面）。⚠ **1mm 級窄零件（<2.2mm）永遠不開溝**（守衛），只能靠端面標記——這是 Eric 提的情境，尚未有解。

**驗證與紀律（都已沉澱，見 §SOP）**：3MF 拆包水密稽核（0 開放邊/反向邊/退化面）為改 `buildLabelMesh` 的**強制關卡**——首輪 apex-cuts 就抓到 12 條 T 接點開放邊。**幾何結論必須自帶座標依據**：我曾未驗磚實際座標就宣稱「94.7% 縫在中段」，被 Eric 用畫面推翻（已記 §3.6-E）。
↳ **已沉澱到 `..\照片磚_Phase0_技術參考.md` §3.6**（色階/可印寬/接縫/V溝/工具鏈踩坑，✅實測 vs ⬜待實印分區）；切片規則 SSOT（ping-slicer skill）三處 seam 已改裁 `aligned`。

**本機狀態（下一棒別重踩）**：`D:\PING-Slicer-portable` 已熱補全部網頁層（備份 `.bak-bplan/.bak-nozzle/.bak-seam/.bak-vnotch/.bak-uitab`）＝**Eric 現在用的就是最新工作室**；%APPDATA% 照片磚 5 製程 seam 已改 aligned（`.bak-seamalign`）；EBWebView `Cache`/`Code Cache` 已清（子資源快取老坑，script 已帶 `?v=` 防再犯）。**T001 已由主線 session 上架 G 槽**（同事驗收中）——**本 session 這 11 顆都不在 T001 上**，要進同事手上得等 T002。

---
### 🏁 快照（2026-07-19 — 照片磚垂直雙料 B案感知均勻色階＋格點 0.05；portable 已同步免 build）

**起因**：Eric 丟灰階人像進照片磚工作室，模擬洗白、怎麼調都不像原圖。根因兩層：①雙料垂直「分箱在 gamma 亮度均分 × 顯色在線性 RGB 均分」**兩把尺對不上**→中暗調整批被畫亮一階 ②均分 S 的階梯亮端擠、**暗端 sRGB 122→0 整段沒有階**→深灰頭髮塌成亮灰+黑。Eric 裁 **B 案（感知均勻取階）**＋格點 0.1→0.05（「不影響列印時間、越細越好；層高 0.05 格點也要跟上才不鋸齒」）。

**改動（主線 `18e58ece` @ ping/v3.5 已 commit 未 push；出貨線 cherry-pick `addea28a` @ release/v3.6 未推——release 現 3 commits 待 build 令）**：
1. `simulateVertical()`：K 階改 **L\* 均分**、反解各階混比 t（線性混色下 Y 對 t 線性→解析解）；分箱改「像素 L\* 取最近階」＝與顯色同一把尺。四料 quad 路徑未動（本來就 nearest-Lab，其候選階梯仍均分 S——之後要不要同套 B 案另裁）。
2. `AUTO_CELL_MM` 0.1→0.05、`GRID_MAX` 1600→3200（16cm @0.05 不觸頂；mesh_union Uint16 座標範圍內安全）。
3. 順手修真 bug：縮樣一維 stride 與列寬有公因數時**塌縮成少數幾欄**（stride=列寬時只剩第 0 欄→suggest 把料B建議成白色）→ 改二維步進取樣。
- **驗證（AI 親眼＋數值）**：灰梯 6 階圖 ΔE **1.7**、階梯 L\* 100/80/60/40/20/0 全均分、合成人像深灰域不塌黑（截圖過）；S 值兩位小數 ∈[0,1]，C++ `is_num_token`（PingColorMix.cpp）契約相容**零 C++ 改動免 build**；5.85M 格（100×146mm @0.05）重算 2.6s、3MF 6 零件 484k 三角形 3.2MB 2.5s、console 零錯。
- **D 槽 portable 已同步**（`D:\PING-Slicer-portable\resources\web\phototile\` 兩檔換入，備份 `.bak-bplan`）——Eric 重開照片磚頁立即生效。
- **已知取捨**：①重算 ~0.4s→~2.6s（4 倍格點代價；嫌頓可議「預覽粗格/匯出細格」分離，未擅做）②髮絲被吃主因＝「雜訊濾除 2.0mm」預設（≤2mm 全合併），保細節調 0 ③色階數 >12 時暗端相鄰 S 差 <1%。
- ✅ **Eric 驗收（0719 午後）：「顏色相近了」＝B 案生效**。
- 🟡 **追加：「產生並載入列印板」跳『由舊版產生、僅載入幾何』彈窗＝誤報**（Eric 回報「輸出異常」）。根因＝照片磚 3MF 天生不帶專案設定→`config_loaded.empty()`（Plater.cpp:6137）誤判舊版檔；`load_config=false` 只是不套檔內 preset（本來就沒有），**零件名/擠出機/S 配比照常載**（bbs 解析自 model_settings.config，該分支不清 volume config；三份 gcode 全 PASS 同路實證）。**點確認即可正常用**。修法＝認 `model_info.metadata_items["Application"]` 前綴 `PING-PhotoTile` 靜默（Application 進 metadata_items＝bbs_3mf.cpp:3886 無差別收錄、ModelInfo::load 有帶）——主線 `f6def0f0`＋出貨線 `139a2844`。⚠ **C++ 6 行未經編譯驗證**，下次 build 留意。release/v3.6 現累積 **4 commits 未推**（TPE 一對＋conf 工具＋B案＋彈窗修）等 build 令。
- **⏳ 等 Eric**：切片後貼 gcode 驗 T→M6051／實印驗實機灰梯（C 案校正卡對帳待開）；下次 build 令時裁「出貨線一併推」。

**0719 續（同日第三批）——FD300 照片磚選不到＋「照片磚設為一類」（Eric 指示）**：
1. **根因**：r5（出貨線）bundle 從未帶照片磚機——`tools/ping/base/phototile/` 母版沒進出貨線→emit_phototile 被 isdir 守衛靜默跳過；選機頁（GuideFrame 讀 `resources_dir()/profiles`＝bundle，非 %APPDATA%）自然列不出。%APPDATA% 5 機一直都在（切片可用、選機動線斷）。
2. **出貨線修好（commit `13b91e95`，未 push；release 線現 5 commits 等 build 令）**：①補母版＋emit_phototile 特調行 `sparse_infill_acceleration=10000`（出貨線副本缺 0715 主線修正，verify 抓的）②regen bundle 帶 5 機＋PING.json 12 條目、**版號 56→57**（<Eric appdata 59）③**65 檔源漂移全回滾**（G 槽源 0719 變動不隨本案夾帶——注意：出貨線下次 regen 還會撞這批漂移，屆時是「主線參數要不要同步出貨線」的裁定，別誤當本案殘留）④guide 21/24.js `ProductLineOf` 認機名含「照片磚」→ 第三頁籤「Fast｜Classic｜照片磚」；假資料實測三籤路由互斥正確、active 態自動吃 #EA4E16 白字。
3. **portable 換裝協調（認領簿 c-0719-06）**：主線 session 同日把 D 槽 portable 換成 workshop（主線@183a108c、bundle 51 含照片磚＋DL1016）→ 原熱補計畫全取消（不需要）；**唯一實寫＝補回 photo­tile B案兩檔**（workshop 不含上午 B案＝靜默回歸，.bak-bplan、md5 對 `18e58ece`）。⚠ **workshop 選機頁＝主線家族分列版（無頁籤）**——照片磚勾得到但長相與出貨線頁籤版不同；**兩線選機 UI 收斂待 Eric 裁**（建議下次 build 前決定要不要把頁籤版港到主線）。
4. 🟡 未辦：user 副本「FF800 同進照片磚」遮蔽系統版（同名坑）——等 Eric 說「清」才移 bak；主線 24.js 若港頁籤版記得 CSS（ProductLineTabs 樣式在出貨線 21/24.css）一起。

---
### 🏁 收工快照（2026-07-18 晚〜19 — 三未決全裁＋照片磚/T012 進出貨線＋G 槽第5版＋TPE 入系統＋T012 契約閉環）

**主線 `3ac0fa69`（已 push）／release `7142f4f8`（⚠ **2 commits 未推**：TPE 一對 `255a2922`＋conf 工具 `7142f4f8`——**等 Eric 說 build 才推**＝推即觸發 CI；推時 bundle 56→57 進版）。本 session commit 範圍＝主線 `215e9b37..3ac0fa69`、release `4b27ec70..7142f4f8`。**

**Eric 六裁全落地**：①G-code 視窗＝只做 B（預設關，僅新 config 生效）②T012 現在就上（原「先韌體後切片」順序被 Eric 明示覆蓋，風險承接記契約單）③PETG PA 0.12 照收（⬜待 PA 塔實測）④照片磚整合＝主線＋出貨線都要（「不進正式版」舊規則**作廢**，memory 已翻轉）⑤PA 修正：四料 SupPLA 0.4＋3in1 四支開 PA＋SupPLA(3in1) 統一 0.2 ⑥TPE 軟料一對入系統。

**發布：G 槽根層＝V3.6.0 第5版 r5**（run 29638874083 @ `d194b4d7`，bundle 56）＝照片磚工作室＋T012＋PA 三修＋冷卻降速＋視窗預設關。成品抽驗 14/14 過；照片磚 C++ 編譯首驗過（macOS 只敗 DMG 打包=runner flaky）。r4 移 old\。**Eric D 槽 portable＝r5**（備份 -old-v360r4；r3 已清）；%APPDATA%＝版號 57＋T012 九檔（.bak-t012）＋TPE 兩支＋conf 可見 21→23（.bak-tpevisible）。

**✅ T012 契約閉環（2026-07-19）**：Klipper 回報 3in1 機隊 **3/3 全綠**（.24/.147/.29）——新切 3in1 檔可餵全機隊（外售未回廠機除外，G 槽版本資訊已載）。契約單兩邊一字不差。alias 裁撤＝下一四料正式版（quad_V3.9.4-Q4 待 Eric approve）後一週期，Klipper 屆時通知。`release/t012-pending` 已併入出貨線＝**該待命分支已完成使命可刪**。

**TPE 軟料一對（`ae027ac4`+conf 工具 `3ac0fa69`；⬜實印待驗）**：PING TPE＋PING SupTPE（TPU 系支撐料）——噴溫 220/床 60/回抽 3+hop0.6/風扇 50·100/PA 關；★**軟慢硬快＝流量天花板法**（TPE 3.2=上限 40、SupTPE 5.5=支撐 60+，製程速度欄免改；放寬到 50 只改 3.2→4.0）。產生器 4b-1c durable；Eric user 三支（PING TPE/SupTPE/Sup_TPE）已移 `%APPDATA%\PingSlicer\bak-user-tpe-20260718\`。↳ 工藝已沉澱到 ping-slicer skill materials.md「TPE+SupTPE（Orca 線）」節。

**出貨線 cherry-pick 踩坑（下一棒必讀）**：①照片磚 pick 衝突根因＝出貨線缺依賴 `be14c92a`（T→M605x）——**先補依賴再 pick 就順**②首頁磚兩線解法不同：主線=雙料照片+照片磚兩顆、**出貨線只加照片磚**（雙料照片=測試遺產不出貨）③G 槽 zip 打包用 **Windows 內建 bsdtar**（`tar.exe -a -cf out.zip -C dir .`）——python zipfile 會炸 MAX_PATH 長路徑、`\\?\` 前綴無效。

**⏳ 等 Eric/外部**：①**Eric 驗收三件**：TPE 首件（88-0019-2 兩槽選 PING TPE/PING SupTPE，速度著色驗本體 40/支撐 60）／首頁照片磚磚／3in1 切件驗 T012 ②build 令（release 2 commits 待推）③同事 G 槽 r5 驗證回報 ④時間預估 33h 閉環 ⑤FD300 槽數間歇掛觀察 ⑥TPE 覺得 40 慢→流量上限 3.2→4.0。詳見 `D:\dev\2026claude\待確認\20260604 ORCA客製.md`。

---
### 🏁 前期快照（2026-07-18 — 兩日大批：參數五批＋UI 六修＋T012 契約＋G 槽輪替至第4版）

**主線 `872a4a5e`／release `4b27ec70`（bundle 55）皆已 push；本 session commit 範圍＝主線 `60aeb77c..872a4a5e`、release `9bad4cef..4b27ec70`。**

**參數批（全部三處同步：兩線 repo＋%APPDATA%，各有 .bak-* 備份；durable＝embed sweep＋verify 檢查 7~11）**：
① 支撐幾何口徑連動（樹狀×10／線距×8=口徑/12.5%）② 洗料塔寬 25＋洗料量 30/SupPLA 60/FF 120 ③ 四料噴溫 210（塞頭）④ 機器動力學=Klipper 實值（FD/FP 400/5000/jerk7、FF 200/1500/jerk56——29h 估 vs 33h 實印 +14% 根因=轉角模型；DL1016/Classic 跳過）⑤ 四料口徑合一（PA開/流量30/床60）＋PETG 開 PA 0.12＋新支 PETG-高流量噴頭（PA 0.2）＋冷卻降速全開/降速層時間 10 秒。跨線同步單 5 份在專案根 `_切片規則同步_來自orca_*_2026071[78].md`，**切片參數 session 待回填 ping-slicer SSOT**。

**UI/C++（兩線同碼）**：混色提示框仿畫布 ImGui 樣式（PingDarkTooltip，勿用 RichToolTip/原生）＋混色面板白底（StaticBox 圓角清背=建構時父色，先設父色再建鈕）；複製對話框保底間距（DialogButtons 通用修）＋自動排列預設不勾；線材下拉「系統預設」第一層=材料類別（filament_type＋is_support 自動推導，PLA→SUP→ABS→PETG→PA）；選機頁「全選/清空」補按鈕樣式＋t11 改「全選」（resource 免 build）。**Eric 已親驗**：分類樹✓四料合一✓FD300 直選 2 槽✓。

**發布**：G 槽根層＝V3.6.0 **第4版**（run 29630307476，bundle 54）；🚌 **最終 build run 29635524383（bundle 55＝＋冷卻批＋選機頁按鈕）監看中——綠了照規則輪替第5版**（背景 task bmt200uoe，若 session 已換手→下一棒下載抽驗（bundle 55/冷卻 1+10/按鈕樣式）→G 槽輪替＋版本資訊）。Eric D 槽 portable＝r4（bundle 54；冷卻批他 %APPDATA% 已有，重啟即見；**選機頁按鈕樣式已直接修進他的 portable web 資源**）。

**🟡 T012 跨系統契約（備好不打）**：T4→T012、T5→T0123（Eric 裁；契約單 `..\integration-t012-toolnaming_20260718.md` 兩邊一式＋PROJECTS.md 紅線 5）。切片端主線已改（c70dc374）；**出貨線在待命分支 `release/t012-pending`（3e7bd9fa）勿併**——Klipper 端 🟠 四料母版+.24 完成、**3in1 機隊未完**；閘門＝Klipper 回報「3in1 存量機隊全綠」才併＋進版。alias 去留提案在 Eric 手上。

**工具新增**：`tools/ping/clean_user_presets.py`（清 user 線材/製程、機器保留、全量 zip 備份）＋`patch_conf_ff_merge.py`（口徑合一 conf 修補，已執行）。Eric user 夾已清 18 支實驗參數（備份 user_backup_20260718142549.zip）。

**⏳ 等 Eric/外部**：①同事 G 槽驗證回報 ②時間預估閉環（重切 FD600 PLA+SUP 對 33h 實印）③三未決：G-code 視窗兩案／3in1 T1 疑案 gcode／一般 PETG PA 值 0.12 屬推定 ④FD300 槽數間歇 bug 掛觀察（再遇記「從哪台切過去」＋截圖）⑤Klipper 3in1 全綠回報。詳見 `D:\dev\2026claude\待確認\20260604 ORCA客製.md`。

---
### 🚀 現況（2026-07-17b — V3.6.0 r2 上架 G 槽：bundle 52＋四料噴溫 210＋混色/複製 UI 修正）

- **G 槽根層＝V3.6.0 r2**（run **29570398619** @ release `e57bbbae`；r1 已移 old\）：①支撐幾何口徑連動＋洗料塔 25/30·60（bundle 51→52，Classic 也套）②四料高流量六支噴溫 190/185→210（0.6 實機塞頭，Eric 裁全家族統一）③混色提示框仿畫布 ImGui 樣式＋編輯器白底 ④複製對話框按鈕保底間距（DialogButtons 全 app 通用）＋自動排列預設不勾。成品抽驗過（bundle52/210/6·4.8/塔寬25/FF purge120）。
- 主線 ping/v3.5 同步至 `9bdd528c`（參數＋UI 全鏡射；均已 push）。%APPDATA% 與兩線 repo 三處一致。
- 中途兩顆 build 不上架：29552066505（無參數）在 `_staging\v3.6-mixfix-*`、29565795134（溫度仍 190）被 r2 取代。
- ⏳ 等：同事 G 槽驗證回報；Eric 三項未決（G-code 視窗做不做／3in1 T1 疑案 gcode／T 命名方案）見待確認檔。

---
### 🚀 現況（2026-07-17 — 🔴 客訴：V3.6 選機不帶高流量線材，根因已追到 code 層）

- 客戶端 V3.6.0 選到機器後高流量線材不出現，需「設備→全部清空→選別台→確定→再清空→選回本機→確定」才出現（Eric 07-16 實地驗證）。
- **根因三連**：①切機 carry-over——舊線材相容就沿用、永不套機器預設（Tab.cpp:5989）②「選擇3D列印機」對話框（guide 24 頁）不跑 ChooseDefaultFilament、重選同一台被 apply_config 判「沒變」early-out（WebGuideDialog.cpp:746-753）③load_installed_filaments 只要有任一相容線材就跳過補 default_materials（PresetBundle.cpp:1768-1786）→ 升級客戶永遠拿不到新預設線材。
- 完整分析＋暫行 SOP＋三個修法候選（等 Eric 裁）：**`..\_客戶問題記錄_V36選機不帶高流量線材_20260717.md`**。出貨包資源端已驗無辜（8 支都在、註冊/alias/版號 51 皆正確）。
- ✅ **0717 洗料塔三調整已落地（Eric 裁）**：寬 15→25（蓋 0708 舊裁）＋洗料量全庫 30／SupPLA 系 60／SupABS 30／FF 四料·3in1 維持特調 120（Eric 追裁「不蓋」，解掉 4b 段待裁註記）。commit `6760a838`（embed 4b-3 sweep＋verify 檢查 8/9）＋%APPDATA%（含 DL1016）。同步單：`..\_切片規則同步_來自orca_洗料塔寬25與洗料量3060_20260717.md`。⏳ 重啟驗：塔寬 25 黑字、SupPLA 60。
- ✅ **0717 支撐幾何口徑連動已落地（Eric 三裁：小口徑照公式/分子口徑名目值/全庫 144 支）**：樹狀分支直徑=口徑×10（原一律 5）、主體圖案線距=口徑×8（=線寬/密度12.5%；原 2.5、FF 特調 4 一併收編）。commit `8ce3bec3`（含 embed normalize_support_geometry＋verify 檢查 7）＋%APPDATA% 144 支（.bak-supgeo）；照片磚 5 支不套。前顆 `60aeb77c`＝補提交 0715 保守批遺留（v49/SavePresetDialog/common）。跨線同步單：`..\_切片規則同步_來自orca_支撐樹狀直徑與主體線距_20260717.md`。⏳ 等 Eric 重啟驗 0.6→6/4.8。

---
### 🚀 現況（2026-07-15 — 主線保守加速度／接縫對齊／副本短名稱）

- `ping/v3.5` 主線一般製程 144 支：`sparse_infill_acceleration` **10000→5000**、`travel_acceleration` **20000→5000**（20000 會造成馬達錯位／失步）、`seam_position` **aligned_back→aligned**（UI「對齊」）。
- 照片磚 5 支維持獨立特調 `10000／3000／back`，`ping/photo-tile` worktree／branch 未動。
- `SavePresetDialog.cpp`：另存系統列印參數時去掉 ` @機型 (口徑)`，例 `0.2mm PLA+SUP - 複製`；只套 `TYPE_PRINT`，機器／線材命名不受影響。
- durable：`embed_params.py` 已同步；`verify_profiles.py` 新增主線 144 支＋照片磚 5 支硬閘門；`PING.json` **v48→v49**（仍 `< %APPDATA% v50`，DL1016 紅線不破）。跨線規格＝專案根目錄 `_切片規則同步_來自orca_主線保守加速度與接縫_20260715.md`，已主動通知切片參數 session 回填 ping-slicer SSOT。

---
### 🚀 現況（2026-07-14 — 支撐四規則落地＋SupPLA 高流量「看不到」真因抓到，⏳ 等 Eric 關 app 補 conf）

**Eric 2026-07-14 裁「支撐四規則」已嵌（commit `c8c3e751`，ping/v3.5；repo＋%APPDATA% 各 51 檔同步改）**：
- PLA+SUP ×15：`support_object_xy_distance`＝口徑×0.75、`support_object_first_layer_gap`＝口徑/3（0.25→0.19/0.08、0.4→0.3/0.13、0.6→0.45/0.2、1.0→0.75/0.33）＋介面 4 層/間距 0.1。
- PLA+PLA／ABS+ABS ×30＋FF 四色 ×6：介面收到 4 層/0.1（**只收緊不放鬆**）。
- 不動（⏳ 待 Eric 裁「一律」是否也蓋）：ABS+SUP 黃金 4/0.04/XY0.5、3in1 4/0 實心、照片磚、DL1016。
- 產生器 durable：`combo_overrides` 帶口徑出 PLA+SUP 幾何＋新 `normalize_support_interface`；SSOT 已回填 ping-slicer skill materials.md。
- ✅ **r6 build 綠＋portable 已換裝（2026-07-14）**：三批（`c8c3e751`＋`4a3fa192`＋`cb10b456`）cherry-pick 上 release/v3.5.5＝`0673b585`/`92db6578`/`b5137817`＋版號 `34194a64`（tip）→ run **29296142180**。第一輪 Windows 在 cpack 缺 NSIS 紅＝**chocolatey 社群源 504**（編譯含 PartPlate.cpp 全綠、純 infra；choco 防呆重試已進 dev `4063d302`）→ rerun --failed 全過。`D:\PING-Slicer-portable`＝**r6**（bundle v49 全項驗過），備份 `-old-v355r5`；**%APPDATA% 版號已抬 50**（bundle 49<50＝DL1016 紅線維持）。
- ★ **G 槽發布夾常設規則（Eric 2026-07-14 裁）**：`G:\我的雲端硬碟\2026claude\PING Slicer\` **根層永遠放最新版檔案**（同事直接來抓）、**舊版一律移入 `old\`**（Google Drive 移動不斷連結）；官網檔另裁（Eric：目前還沒放官網）。r6 已照此上架：根層＝r6 portable zip（SHA-256 B5E84DCE…7002）＋版本資訊.txt；0709 官網三檔/7z/r5 內部測試夾已入 old\。安裝版 `PING_Slicer_Windows_Installer_V3.5.5_r6.exe`（SHA-256 E8327E8E…D5CF）已補齊＝**G 槽 r6 兩檔全齊、同事可下載**。cherry-pick 時照片磚 2 機檔 DU 衝突按「release 無照片磚」原則 git rm；release 驗證全過（支撐四值/黃金不蓋/FD300 弧/FP300 弧/FP200 不在通用版/照片磚 0/py_compile）。**版號：bundle 48→49、%APPDATA% 49→50**（維持 bundle<appdata 嚴格小於＝DL1016 紅線；r5 用戶 48→49 會吃到更新）。綠了照慣例換 portable（現版＝r5，備份名照 -old-v355r5）。
- ✅ **「不蓋」定案（Eric 0714）**：ABS+SUP 黃金 0.04／3in1 實心 0 維持——已記 ping-slicer materials.md。ping/photo-tile 分支仍未鏡像三批（下次照片磚 build 前 cherry-pick）。ping/photo-tile 分支也未鏡像這三顆，照片磚下次 build 前記得 cherry-pick（%APPDATA% 已是新值、Eric 本機照片磚切片不受影響）。
- **0714 弧線預擠幾何定稿（參數端同步單）已嵌（`cb10b456`）**：209°/弦100/R144-138/E=直線版同量（0.2→16/0.25→20/0.4→30/0.6→45）/Z=口徑首層高；白名單 FD300 三模式＋FP300（P200+/FP200 全名比對防繼承——床 250 會超床）；repo＋%APPDATA% 各 14 檔、備份 `.bak-primearc2`；0.4 雙料與定稿逐字相等（硬閘門）。⏳ FP300 2 弧版待實機驗。完成紀錄在規格檔尾。
- **0714 洗料塔兩案（Eric 裁定）**：A＝圓床預設塔位「頂部置中 X=0、含 brim 離頂 10mm」已做（`4a3fa192`，PartPlate.cpp set_default_wipe_tower_pos_for_plate，方床不動，需 build 驗）；B＝層層洗開關不用做——現成參數 `wipe_tower_max_idle_layers`（多線材→換料塔「閒置線材沖刷間隔」，0=原始/1=層層洗），Eric 裁「預設開」＝維持 `fdm_process_ping_common`=1 現狀、3in1 六支明寫 1。
- **conf 可見清單已補（0714 08:08，Eric 關 app 後）**：換名 147、filaments 22→24、MD5 重算、備份 `.bak-hfvisible-20260714080823`、復檢乾淨——⏳ 等 Eric 重開驗 SupPLA 高流量噴頭出現＋溫度 210。⚠ Eric user 夾仍有 7/12 手建同名樣本（PLA - 高流量噴頭等），若前台吃到 220＝那支，請他刪 user 版。

**🔴 「PING SupPLA - 高流量噴頭」下拉看不到的真因＝conf 可見清單被 app 回寫蓋回舊名**：07-12 記錄「conf 已換名＋MD5 重算」，07-14 實測已回魂（filaments 仍 22 支舊 @FF 名、全檔 147 處舊名殘留）——conf 若在 app 開著時補、退出時會被記憶體舊態覆寫。系統端本身沒問題（%APPDATA% 線材/註冊/機器 default 皆新名；線材×2 已補同步 210/210＋PA 0.2＝9a5c1892/572b9241 內容）。
- 修補腳本已收 repo：`tools/ping/patch_conf_hf_visible.py`（`--check` 乾跑已驗：MD5 方案重算＝現檔一致；147 處換名＋filaments 22→24）。**執行條件＝PingSlicer 完全關閉**（腳本有 running 防呆＋自動備份）。跑完重開＋開新專案。
- 順帶：Eric user 夾有自建同名樣本（`PING PLA - 高流量噴頭`／`- 複製`等）建議請他在 app 內刪除改用系統版，避免同名混淆。

**同事 FD600 Pro 同進「兩支料」＝同事本機狀態、非系統 bug**：同進機定義三處驗證皆 1 槽（repo ping/v3.5／%APPDATA%／release355 worktree：`nozzle_diameter` len1、SEMM=0、`default_filament_profile` 1 支）；「PING SupPLA - 210」**git 全歷史查無**＝同事自建 user 線材或開過 2 槽專案被 conf 記住。排查＝同事機選該機後把第 2 槽移除／重置該機選擇；刪不掉＝他的機器定義被動過→用正式版覆蓋 profiles。

---
### 🚀 前況（2026-07-12 下午 — build 綠、portable 已換裝 V3.5.5 第4版，⏳ 等 Eric 驗收）

**✅ build run `29183125531` 綠＋portable 已換裝（2026-07-12 16:38）**：build_windows 的 Build OrcaSlicer=success（整體 failure＝Flatpak×2＋UnitTests 坑#10 照舊）；`D:\PING-Slicer-portable`＝**V3.5.5 第4版**（release/v3.5.5 @ `2cb3557d`），前版備份 `D:\PING-Slicer-portable-old-v355r3`。換裝前已驗：bundle PING.json **v47 < %APPDATA% v49**（DL1016 安全）、機器 90／製程 146、高流量線材×2＋四料改名×6 全在。**下一棒＝等 Eric 驗收回饋（重點見下方「⏳ 等 Eric」五條，最優先＝回抽四欄圓柱體測試）。**

**這顆 build 內容（自上顆 29011140392 之後新增 9 顆碼 commit）**：
1. **佔位符引擎修正 `fdc1ba19`（最重要）**：線材回抽覆蓋值終於能進 SET_RETRACTION——上游 parser 生命週期 bug（clear_config 後只補「本輪有變」覆蓋），修法＝placeholder_parser_process 中央入口按當前線材錨定 m_config 有效值（四鍵：retraction_length/speed/deretraction_speed/retract_restart_extra）。**驗收＝Eric 的圓柱體測試檔（PLA-220 覆蓋：長度2/速30/裝填30/回填0.6）重切，SET_RETRACTION 四欄應全等於覆蓋值、機器 UI 同步變。**
2. SET_RETRACTION 四欄行（`0e9b421c`+`ac2478b5`；M207/M208 已退場）＋M207 歷程（`0def77fc`/`2397e40e` HOLD 標記）。
3. 高流量噴頭案 A-D（`7d7e5ff0`+`61811ade`）：新線材×2（8 鍵覆蓋）、FD450+ 預設高流量、FF 改名四料高流量噴頭系、**D＝Tab.cpp 連動機型相依**（FD450+ 選 PLA 組合→高流量組；FD300 原表）。
4. 檔名模板「Non-integer index」修正（`a68e548c`）＋預擠正規化（`a009d287`：中途 F800、T0/T1 結尾 T0）。
5. 上一輪 UI 批（混色/設備對話框/品牌清洗/專案頁移除等）已在前顆 build，此顆延續。

**%APPDATA% 現況（Eric 機、已全數同步）**：PING.json v49；線材 24 支（SET_RETRACTION 四欄＋高流量噴頭 8 鍵×2＋四料改名×6、舊名清零）；conf 可見清單/選擇已換名＋**MD5 已重算**（方案＝標準 md5·LF 正規化 JSON 段·大寫，詳 memory checklist 7c）；機器 97 檔含弧線預擠/棧板/64 槽新名；DL1016 完整。備份系列：.bak-hfnozzle／.bak-setretraction／.bak-primefix2／.bak-primearc。

**判例（本輪血淚，已記 memory）**：①靜態讀碼推斷 ≠ 執行期（[retract_length] 不會炸、PrintApply:1250 不保證——被 Eric 實切打臉兩次，唯一 ground truth＝實測 gcode）②線材改名波及清單＋conf MD5 方案＝memory checklist 7b/7c。

**⏳ 等 Eric（build 綠換裝後）**：①回抽四欄下機驗證（見上）②D 連動：FD600 選 PLA+SUP → 槽自動帶高流量噴頭對、FD300 → 原 PLA-220 對 ③高流量噴頭線材全機型可選、FD450+ 選機預設 ④檔名不再炸、FD300 弧線預擠、UI 批殘餘驗收。⑤照片磚原型回饋照舊等。


---
### 🏁 收工快照（2026-07-09 晚・本 session 結束——下一棒從這裡接）

**✅ build run `29011140392` 綠＋portable 已換裝（收工前完成）**：本體全 success（坑#10 照舊）；`D:\PING-Slicer-portable`＝V3.5.5 第3版（9 修正、bundle v45、無照片磚），前版備份 `-old-v355r2`。**下一棒＝等 Eric 驗收回饋**（重點五條見下段）。

**這顆 build 內容（V3.5.5 第 3 版，累積 9 修正）**：混色層級（同進不顯三選項/範本主選/收合鈕浮動）＋混色按鈕標準樣式＋設備未連線中文頁＋設備對話框三修（瀏覽鈕除/tooltip 去參數名/主機名說明短版）＋品牌清洗＋專案頁移除＋新增實例 tooltip＋洗料塔圓床預設＋FD300 弧線預擠。**Eric 驗收重點**：①混色浮動鈕 vs 縱向層滑桿位置（可能要調 offset）②專案頁消失後「校正」入口正常（FindPage 換算）③FD300 三模式切片＝弧線預擠、上機不撞門（雙料 4 弧 T0/T1、單料頭 2 弧、同進 M6050+2 弧）④選 `_棧板` 自動切 ABS 沒退化⑤About 頁品牌字樣。

**分支 tip**：`ping/v3.5`＝`5db7959f`｜`ping/photo-tile`＝`419f99c2`（版號 3.5.6、含照片磚＋全部修正）｜`release/v3.5.5`＝`48e95f8b`（無照片磚、已 push 觸發上述 build）。三線內容除照片磚外同步；**發版一律從 release/feature 分支、勿從 ping/v3.5 tip 切**（a11ee870 仍在主線歷史）。

**本 session 完成（2026-07-09，時序）**：①棧板驗收 OK（轉參數端定案）＋150%＝筏層貼床線寬（Flow.cpp:235）②G 槽下載夾確認最新（另 session 已覆蓋乾淨版）③混色 UX 兩修正＋標準按鈕化④設備對話框三修⑤品牌清洗（**保護清單＋regex 誤傷判例見下方 0709 品牌清洗段，跨棒必讀**）⑥專案頁移除/tooltip/線材對話框中文（text.js zh_TW 缺鍵——**text.js 是 CRLF、插入要偵測行尾**）⑦洗料塔圓床盤形夾限（PartPlate set_default_wipe_tower_pos_for_plate）⑧FD300 弧線預擠（embed_params `apply_fd300_prime_arc`，只 FD300 非 Pro——Eric 確認 Pro 不用；規則已轉參數端）⑨release/v3.5.5 重組發 build。**%APPDATA% 本日動過**：棧板同步（.bak-palletsync）＋FD300 弧線 11 機檔（.bak-primearc）。

**照片磚線待辦不變**：Eric 實走原型（`..\照片磚_整合原型_準備頁_20260708.html`）拍板 → P1 C++ 引擎移植。照片磚版 build 等原生整合後再發。

**其他掛著**：GitHub Release v3.5.5 要不要發（等 Eric）；更新對話框 Orca logo 圖檔資產另案；單獨「Orca」字樣散點；PA-CF 等參數端交付；牆速待參數端抽驗。

---
### 🏁 V3.5.5 無照片磚版 build 綠＋portable 已換裝（2026-07-09）
- run **28952768359** @ `98a7e2b6`（Eric 授權發車；整體 failure＝Flatpak×2＋UnitTests 坑#10，本體全綠、artifact 齊：Windows 安裝檔+portable/Mac Universal/Linux）。
- `D:\PING-Slicer-portable`＝乾淨 **V3.5.5**（混色＋預擠＋牆速＋版次＋棧板 A+B+C；無照片磚、無 a11ee870）。舊 v3.5.4 備份 `D:\PING-Slicer-portable-old-v354`（更早 -old-preB/-premix/-preprimefix 已於 2026-07-12 清除）。bundle PING.json v45 <%APPDATA% v48 → DL1016 安全。⚠ 這顆無照片磚後處理，切照片磚一律用 `D:\PING-Slicer-phototile-portable`。
- %APPDATA% 已同步棧板（Eric 授權）：備份 `process.bak-palletsync`、+33 雙生、版號 48、牆速新規一併帶上；照片磚 5 支/DL1016 未動。
- ✅ 棧板驗收 OK（Eric 07-09；150%＝筏層貼床層線寬，引擎碼 support_material_1st_layer_flow→Base flange 查證）；已轉參數端定案。
- ✅ **G 槽下載夾已換乾淨版**（`G:\我的雲端硬碟6claude\PING Slicer\`）：7/8 有人上傳了污染版 V3.5.5（run 28883963324 夾帶 a11ee870）→ 07-09 同名覆蓋為乾淨 run 28952768359（連結不變）、SHA-256/版本資訊.txt 已更新。⏳ 可選：補發 GitHub Release v3.5.5 tag（等 Eric 說）。

### 🎨 0709 Eric 驗收回饋批（混色 UX×2＋設備未連線頁＋按鈕標準化）— ✅ 已實作（C++ 搭下次 build）
- **混色編輯器**（`48dcd811`）：①範本列（同進/漸層）為主選、帶選中態；「漸層/階梯/平滑」只在非同進均分時顯示（is_flat_tongjin()；commit() 補 sync 讓拖曳離開均分即現身）②收合「混色」鈕改浮動疊畫布右上（不入 sizer、EVT_SIZE 重定位、Raise；⚠ 與縱向層滑桿相對位置 build 後親眼看）。
- **按鈕標準化**（Eric 再回饋「抓軟體本身按鈕的 hover/active 樣式」）：混色編輯器全部按鈕（範本/模式/收合/浮動混色鈕）由 wxButton 硬塗色改**軟體標準 `Widgets/Button`**——`SetStyle(Regular)`＝灰 hover `#D4D4D4`+focus 橘框、選中＝`SetStyle(Confirm)`＝橘底白字 hover `#F0683A`；深色模式/DPI 自動跟全 app。浮動混色鈕用 SetVertical(true)（同校正頁 btn_sync 前例）。
- **設備頁未連線畫面**（`c81582e8`，resource 免 build）：英文＋A4Max Pro 別牌 GIF → PING CIS 中文頁（CSS Wi-Fi 波紋動畫＋連線三步驟）；兩 portable 已同步；preview 自查過（screenshot 工具連兩天故障、用 DOM 數值自查）。安裝版等下次安裝檔。
- 下次發版（不論哪條線）記得帶上這批＋換料塔/棧板（皆已在 ping/v3.5＋photo-tile 兩線 tip）。

### 🏷 品牌清洗（2026-07-09 Eric「Orca Slicer 一次換掉」）— ✅ 完成（commit `d294b1ef`+`985a2db7` 兩分支）
- 腳本化四層清洗（src/hints/web/.mo 同一 transform）：規則＝「Orca Slicer」無條件、「OrcaSlicer」regex 前後界＋行級黑名單。**保護清單**（勿再誤改）：EProducer enum、generated by OrcaSlicer/「; OrcaSlicer」/OrcaSlicer- 前綴/OrcaSlicer 2.3.2 UA（gcode 相容）、Obico client_id、OrcaSlicer/Auth 密鑰庫、com.orcaslicer、圖檔資產名（OrcaSlicer*.png/logo_name/create_scaled_bitmap）、About 上游溯源兩段、DesktopIntegration/msvc 整檔。
- 判例：①regex 清洗必逐行審 diff（首輪把 EProducer::OrcaSlicer 換成「PING Slicer」＝編譯炸、Obico OAuth client_id 誤改＝登入斷——全回滾重掃才過）②句尾「OrcaSlicer.」與「
OrcaSlicer」是 lookahead/lookbehind 盲點要補掃。
- .mo：新 msgid→轉換譯文 79+5 條、譯文就地修 3 條；hints/精靈/text.js 屬 resource 已同步兩 portable（立即生效）；對話框/tooltip 類需 build。
- 遺留另案：更新對話框仍用 Orca logo 圖檔資產（換成 PING logo＝改 resources/images 資產檔，用 ping-cis assets）、散點單獨「Orca」字樣、NetworkTestDialog 連測標籤。
- 誤入修正：resources/web/mixer（棄用藍圖）曾被 git add 掃進、已 `git rm --cached` 移出（磁碟保留）。

### 🧱 換料塔＋棧板雙版本（2026-07-08 午後，參數端同步單・Eric 三裁決全 A 案）— ✅ repo 三線完成
- 規格：`..\_切片規則同步_來自pingslicer_換料塔與棧板雙版本_20260708.md`。實作＝主線 commit **`2d27bb2c`**（photo-tile cherry `e59364a1`、release/v3.5.5 同內容 `98a7e2b6`）：
  - **A** `normalize_prime_tower()`：全庫 `prime_tower_width` 30→15＋`wipe_tower_wall_type=rib`（主迴圈＋ff_extra＋照片磚範本三處）。
  - **B** 棧板雙生 33 支 `{層高}mm_棧板 @機型 (口徑)`（raft 六鍵＝ABS+SUP 黃金配方；主迴圈收集、**4a-4 統一 emit＝setting_id 排全庫最後、既有 id 零位移**）。⚠ **兩線 id 不同**：照片磚線/主線＝PINGP116-148（與 %APPDATA% 對齊）、無照片磚 release 線＝PINGP111-143（該線無照片磚 5 支）——同名異 id、無功能影響，未來查坑別混淆。
  - **C** Tab.cpp `ping_apply_combo_filaments` 前段加 `_棧板` 子字串偵測（UTF-8 位元組 `\xE6\xA3\xA7\xE6\x9D\xBF`）→ 全槽切 `PING ABS - 250`；≥1 槽即可；單向（切回一般版不換回 PLA）；僅手動點選觸發（沿用既有掛點）。**需 build＝搭下次發版**。
  - `emit_phototile` 加 `os.path.isdir` 守衛 → **同一支 embed_params.py 在無照片磚 release 分支直接可跑**（該線 regen 已驗：144 支/verify 過）。
- ⏸ **%APPDATA% 同步（驗收步驟①）被權限閘門擋、等 Eric 說「同步 %APPDATA%」**：做法＝備份 `process.bak-palletsync` → 複製 repo 全部製程（跳過照片磚 5 支＝牆速抉擇未裁不動）→ %APPDATA% PING.json 併 33 條目＋版號 47→48。⚠ 會把 07-05 牆速正規化一併帶上 Eric 機器（他機上還是舊速度）。
- 回報參數端：已依雙向協定 send_message（見該線）。

### 🎯 前況（2026-07-08 午 — Eric 拍板「照片磚分支切割」＋原生整合規劃出爐，等 Eric 實走原型）

**Eric 指示（原話重點）**：①照片磚區分成分支，**兩個版本：一個含照片磚、一個沒有**（＝上一段 a11ee870 問題的裁決：走乾淨切割）②照片磚整合**不是把 Web 貼進去**，要像混色一樣原生整合③目標動線＝開新專案→選照片磚機→丟照片→**「準備」頁旁邊直接調參數**（他認為準備頁比照混色的預覽頁合理，問我意見——我同意，理由見規劃書）。

**已完成**：
1. **分支切割**：
   - `release/v3.5.5`（**無照片磚**）＝本機重切 `21ff0003`：基底 00f0f08d＋牆速 `4fe0217b`＋版次顯示 `0567977f`＋進版 3.5.5。無 a11ee870、無任何照片磚。**⚠ 未 push——push 到 release/* 會自動觸發 build（build_all.yml on.push），等 Eric 說 OK 才推**（推的時候要 `git push --force` 蓋掉 GitHub 上舊的污染版）。
   - `ping/photo-tile`（**含照片磚**、已 push `9f373d24`）＝00f0f08d＋照片磚後處理 fb4f9033＋牆速＋版次＋照片磚 HTML/Help（cherry `ed62286d`，內含 version.inc 衝突解決）＋bundle `9f373d24`。**版號暫定 3.5.6**（兩版本頂列要分得出來；`ed62286d` 的 commit 訊息寫 3.5.5 但 version.inc 實為 3.5.6——cherry-pick 歷史訊息，勿被誤導）。無 a11ee870。原生整合（下述）之後也長在這條。
   - `ping/v3.5` 主線維持混歷史（含 a11ee870）＝開發紀錄；**發版一律從上面兩條 release/feature 分支走，別再從主線 tip 切**。
2. **原生整合規劃＋可操作原型**（P0，等 Eric 實走拍板）：
   - 規劃書 `..\照片磚_整合規劃_20260708.html`：準備頁左欄「照片磚」卡片（選照片磚機才出現、混色面板互斥隱藏）；C++ 引擎移植（`libslic3r/PingPhotoTile`，比照 PingColorMix 純 std::＋Python 鏡像驗證）；**直接生成 ModelObject 上盤（免 3MF 出入）**；零件名帶配比→既有 T→M605x 後處理零改動；分階段 P0 原型定稿→P1 引擎移植（免 build）→P2 面板接線（build）→P3 持久化＋實印。
   - 可操作原型 `..\照片磚_整合原型_準備頁_20260708.html`（雙擊開）：真的能丟照片/Ctrl+V→即時量化→改色階/尺寸/解析度/色票即時重算→產生零件（FBK-12 覆蓋確認）→切片閘門。已 preview 自查：合成測試圖三主色（紅屋/藍天/綠地）建議引擎全中、四料 A/B/C/D 與雙料 S 配比正確、一般機卡片消失、無橫向捲動、console 零錯誤。⚠ preview 截圖工具連續逾時（工具端問題），改以 DOM 數值＋像素讀取自查，Eric 實走原型時即是最終視覺驗收。
3. bundle 嵌入（`4f271975`）詳見下一段（上午完成）。

**⏳ 等 Eric**：①實走原型＋規劃書過審（拍板才開工 P1）②「可以 build」→ 我 force push `release/v3.5.5` 發車無照片磚版（要不要同時 workflow_dispatch build `ping/photo-tile` 一併說）③照片磚版號 3.5.6 認可或另定④（不阻塞）bundle 牆速正規化 vs 實印速度、專屬料。

---
### ✅ 前況（2026-07-08 上午接續 — 照片磚機器/製程已編進產生器＋repo bundle（commit `4f271975` push ping/v3.5）；🔴 發現 release/v3.5.5 夾帶 a11ee870 → **已由 Eric 分支切割指示解決（見上段）**）

**已完成（原「下一棒最優先」）**：照片磚 5 機＋5 製程＋零回抽/seam 參數編進 `tools/ping/embed_params.py`＋repo bundle，全新安裝不再丟機器。
1. **範本複製法比照 ff_extra**：`tools/ping/base/phototile/`（machine×7＝2 母檔+5 變體、process×5、cover×2，全部取自 %APPDATA% 實印驗證檔＝含 SEMM=1／64 槽／四項預設／零回抽 `use_firmware_retraction=0`／`seam_gap 0%`+`wipe_on_loops 0`）；`emit_phototile()` 順序寫死重現 setting_id **PINGM066-070／PINGP111-115**（與 %APPDATA% 全等）。
2. **製程套 `normalize_fast_speed`**（2026-07-03 牆速新規全系列統一）：repo 版＝外60/內≤80/填150/accel10000；**%APPDATA% 仍是建置時舊值（FF 外75/內100、FD 外50、accel 100%）**——Eric 實印那幾片是舊值印的；bundle 版牆稍慢＝品質向（與其他 111 支一致）。⚠ 若 Eric 要照片磚維持實印值，把 emit_phototile 裡 normalize 那行拿掉即可。
3. 高流量 PLA @FF 0.4/0.6/1.0 `compatible_printers` +照片磚機（SupPLA 不加）；wizard 21/24.js regex +「同進照片磚」；cover/preview 圖進孤兒保護＋側欄縮圖。
4. **PING.json 版號 44→45（刻意 < %APPDATA% 的 47）**：bundle 不含 DL1016（本機注入備援）——版號若壓過 47，app 會用 bundle 蓋 %APPDATA% → **DL1016 從 Eric 機上消失**。之後任何人 bump 版號 ≥48 前，先把 DL1016 也編進 bundle 或接受消失。
5. 驗證：regen 全庫 verify ✅ 243 presets/73 machines；既有 111 製程/66 機**位元零波及**；產出 vs %APPDATA% 語意比對＝機器 7 檔全等、製程僅差正規化速度鍵。**踩坑新判例**：建置腳本把 process 的 `compatible_printers` 寫成**字串**（app 容忍、verify 逐字元誤判）→ 範本已修成陣列；之後手建 preset 一律陣列。

**🔴 發現（跨 session 違規、需 Eric 裁決）**：昨晚 `release/v3.5.5` 是**直接從 ping/v3.5 tip 切的，夾帶了 `a11ee870`**（首頁「雙料照片」測試磚＋photo-mixer）——違反 07-05 發版鐵則「a11ee870 永不進正式發表、build 從排除它的基底切」（memory `photo-tile-testing-not-release`）。今早功能測試不受影響；**若 V3.5.5 要對外正式發布，須重切乾淨 release 分支**（法一比照 v3.5.4 worktree 從 00f0f08d 基底 cherry-pick；法二在 release 分支 revert a11ee870）＋重 build。或 Eric 改裁「照片磚產品化了、雙料照片磚一併轉正」。
- 註：a11ee870 也已隨 release/v3.5.5 push 上 GitHub（「不要 push」同時破戒，木已成舟、僅記錄）。

**bundle 未含（維持現狀）**：DL1016（本機備援 `D:\dev\...\DL1016_本機注入備援\`）；專屬料 `PING PLA(照片磚)` 未建（回抽關後 wipe 已歸零＝功能多餘，等 Eric 要不要純產品隔離用）。

---
### 🚀🚀🚀 前況（2026-07-08 深夜自主任務 — 照片磚整合進 V3.5.5＋build 已發，Eric 睡前授權、明早直接測）

**做了什麼（全在 `ping/v3.5`，並開 `release/v3.5.5` 觸發 build）**
1. **cherry-pick 照片磚 T→M605x 後處理**（`fb4f9033`→本分支 `be14c92a`）：ping/v3.5 原本只有混色器（曲線編輯 M6051/M6052），**沒有**「多零件 3MF 依零件名配比換 M605x」的照片磚後處理；已淨套進來（同底 00f0f08d，零衝突）。→ V3.5 現在具**完整照片磚切片管線**。
2. **HTML 產生器打包進 build**：`resources/web/phototile/index.html`（＝當前原型，含「解析度＝實體尺寸÷格點」引擎、預設 0.1）。
3. **Help 選單新增「照片磚產生器」**（`MainFrame.cpp generate_help_menu()`，用 `resources_dir()+wxLaunchDefaultBrowser` 開本地 HTML；全平台一致——Windows topbar 的 Help 下拉＋Mac/Linux Help 選單都有）。commit `b107b90f`。
4. **進版 `version.inc` 3.5.3 → 3.5.5**（頂列自動顯示「PING Slicer V3.5.5」）。
5. C++ 已過 reviewer 對抗式複核＝**COMPILE-CLEAN**（本機無編譯器，靠 review 驗；self-review 另抓掉一個 Windows 選單重複項）。

**⚠️ 明早測試前務必知道的關鍵限制（我留意到、誠實記）**
- **照片磚的機器/製程 profile 沒進 build 的 bundle**（FD300/FF800 同進照片磚、5 製程、SEMM/64槽、以及今天改的「零回抽＋seam_gap0＋wipe_on_loops0」都**只在 `%APPDATA%\PingSlicer\system\PING` ＋ phototile portable**，未進 `embed_params.py` 產生器/repo）。
  - **對 Eric 個人測試＝OK**：新版 3.5.5 讀同一個 `%APPDATA%`，你的照片磚機器/今天的參數都在、測得動（memory `pingslicer-profiles-read-from-appdata`：app 讀 %APPDATA%、不被 bundle 覆蓋）。
  - **但若照片磚機器不見了**（極少數：全新安裝/換機/%APPDATA% 被重置），那是因為沒 bundle → 之後要做「把機器/製程/參數編進 embed_params.py＋repo」才算完整可發布。
- **專屬料 `PING PLA(照片磚)` 未建**（Eric 要過但功能上多餘，回抽關後 wipe 已歸零）——不影響測試。

**明早測試 checklist**
1. build 綠了 → 裝 **PING Slicer V3.5.5**（頂列應顯示「PING Slicer V3.5.5」）。
2. **Help 選單 → 「照片磚產生器」** → 應在瀏覽器開出照片磚工具。
3. 用它出 3MF → 在 PingSlicer 開檔 → 選「FD300/FF800 同進照片磚」機器 → 切片 → gcode 應 Tn 全換 M6051/M6052（可貼 gcode 給下一棒跑 `scratchpad/check_phototile_gcode2.py`）。

**build 狀態**：✅ **成功確認**（run `28883963324`，2h11m）。build_windows/linux/macOS(x86+arm+Universal) 的 **Build OrcaSlicer 全 success**；artifacts＝`PING_Slicer_Windows_V3.5.5`(100MB 安裝檔)＋`PING_Slicer_Windows_V3.5.5_portable`(133MB)＋Mac/Linux 齊，版本 V3.5.5 確認。整體 run 顯 failure **僅因 Flatpak×2＋Unit Tests＝坑#10**（與本次改動無關，Windows artifact 可正常下載安裝）。（build_all.yml 僅 main/release/* 觸發；ping/v3.5 push 不觸發。）

**下一棒最優先（讓照片磚可正式發布）**：把照片磚**機器×5＋製程×5＋今天的零回抽/seam 參數**編進 `tools/ping/embed_params.py`＋repo bundle（現只在 %APPDATA%/portable）；順帶決定專屬料要不要建。回抽/轉角 saga 已定案（見 memory `photo-tile-vertical-mixing`）。

---

**🏁🏁🏁🏁🏁🏁🏁 現況（2026-07-06 晚收工 — 照片磚整條線跑通到「實印第一片＋縫隙優化 A 案」；②v3.5.5 牆速完成、PA-CF 等交付、版次顯示已寫）**
> **下一棒最優先**：照片磚縫隙 A 案（交錯齒 v2.1）實印驗收——Eric 重啟 phototile portable → 用**原型 v2.1**（「邊界：交錯齒」預設開）重出 3MF → 切片 → 貼 gcode 我自查 → 印出來跟前一片（有縫）對照交界縫隙。若齒還不夠→退而求其次改外牆線寬；若要真·零縫→啟動 D 案（單網格+沿牆換色，X 失銳邊）。

### 🆕 照片磚企劃（2026-07-06，與 v3.5.5 平行的新線）— ✅ 全鏈路跑通＋實印第一片，🔧 縫隙優化 A 案 v2.1 待實印驗

> **一句話現況**：垂直混色照片磚**從原型到實機全鏈路跑通**。核心後處理 build 綠（`fb4f9033`→run 28772878371）、獨立 portable 已裝 `D:\PING-Slicer-phototile-portable`（正式版 `D:\PING-Slicer-portable` 未動）。**FD300 小機第一片已印完**（`78g_6h36m`＝completed、實印 6h12m）；FF800 大機 gcode 已驗可印。Eric 首印回報**唯一問題＝零件交界有縫**→已定 A 案（交錯齒）、原型出到 **v2.1**，待實印驗。

> **🖨 已建照片磚機（全免 build、%APPDATA%＋phototile portable 雙邊、參照自檢過）**：
> - **FF800 同進照片磚**（四料 M6052）：**0.4／0.6／1.0** 三口徑（PINGM066/067/068、製程 PINGP111/112/113）。
> - **FD300 同進照片磚**（雙料 M6051，小機）：**0.4／0.6** 兩口徑（FD300 硬體無 1.0；PINGM069/070、PINGP114/115）。
> - 共通：**SEMM=1**（否則槽卡 2！＝克隆同進帶進的 SEMM=0）、`default_filament_profile`=**64 槽開滿**（選機自動長槽免手動+）、機名含「同進」讓後處理閘門零改碼認得、製程帶 **Eric 四項預設**（填充 0%／上下殼 0／牆 2 圈／接縫背部）＋**零回抽/零抬升**（retraction_length/z_hop/retract_length_toolchange 全 0——幾千次換料每次回抽既慢又擾混色）。PING.json 已到 **v47**。⚠ 未進 repo/embed_params 產生器（測試線慣例，正式化再編）。建置腳本 scratchpad `build_phototile_machine.py`／`extend_phototile_nozzles.py`／`build_fd300_phototile.py`。
> - ⚠ 兩 portable **共用 %APPDATA%** → 正式版也看得到照片磚機，**別用正式版切照片磚**（無翻譯器、混色面板展開還會插曲線碼）。

> **🎨 原型演進 v1.8→v2.1（`..\照片磚_原型_彩色模擬_v1.html`，檔名固定叫 v1、版本看頁內標題；雙擊即開）**：
> - **v1.9 洗料柱**（Eric 定，取代換料塔）：輸出多一根柱零件（四料 `洗料柱 A25 B25 C25 D25`／雙料 `洗料柱 S0.5`、100% 填充、extruder=N+1）→ 每層必印＝四/兩料每層都動、防久未用料空燒。翻譯器直接吃、C++ 零改動。
> - **v2.0 去層高化**（Eric 洞察：輸出是模型、層高歸切片器＝不會 Double）：垂直模式移除層高設定；洗料柱改**只設柱寬**（預設 25mm 方柱）、不再算每層體積。
> - **v2.1 交錯齒**（Eric 定 A 案解縫）：奇數像素列把**垂直邊界**右咬 1px（長溝→單列錯位短縫＋零件咬合；只動垂直邊界——水平邊界無內縮溝、做齒會孤島爆炸）。preview 驗過（212 flips、零件/換料數不變、console 零錯）。UI「邊界：交錯齒」預設開。
>
> **🆕 專用機器＋洗料柱（Eric 2026-07-06 下午定，全免 build）**：
> - **「FF800 同進照片磚」0.6 機器已建**（Eric 定名/口徑；克隆 FF800 同進 0.6）：`default_filament_profile`＝**64 槽開滿**（PLA 高流量 @FF 0.6）→ 選機自動長槽、免手動「+」。機名含「同進」＋FF 開頭＝後處理閘門**零改碼**直接認得。setting_id PINGM066/PINGP111、PING.json v44→**45** 三處註冊（LAY-11 排 FF800 3in1 之後）、高流量 0.6 線材 compatible += 新機、cover 複製、wizard 21/24.js regex 加「同進照片磚」＋EBWebView cache 已清。**裝在 %APPDATA%＋phototile portable 兩邊**（建置腳本 scratchpad `build_phototile_machine.py`、參照自檢雙邊過）。⚠ 未進 repo/embed_params 產生器（測試線慣例，正式化時再編）。
> - **洗料柱（取代換料塔，Eric 定）**：原型 v1.9 輸出 3MF 時多一個柱零件（`洗料柱 A25 B25 C25 D25`／雙料 `洗料柱 S0.5`、extruder=N+1、**帶 sparse_infill_density=100%** per-part 設定——bbs_3mf.cpp:4942 set_deserialize 已查證支援）→ 每層必印一次＝四支料每層都動防空燒；截面=每層洗料量÷層高（UI 欄位預設 75mm³，0.35 層高→14.6mm 方柱），擺磚右側 15mm。**現成 T→M6052 翻譯器直接吃柱名，C++ 零改動**。調色盤上限 64→柱開啟時 63。換料塔本來就 enable_prime_tower=0 免動。
> - **原型 v1.9 已驗**（preview 實測）：UI 列顯示/換算、雙料＋四料輸出攔截 zip 驗內容（柱 object/extruder/名稱/100%填充/palette 行全對）、層高加 0.35 選項、console 零錯。
> - **🔴 踩坑判例庫（2026-07-06 全實測，跨棒/售服會再踩）**：
>   1. **槽位卡 2** ＝克隆同進帶進 `single_extruder_multi_material=0`。照片磚機必須 **SEMM=1**（走四色同路徑）才會吃 `default_filament_profile` 的 64 槽——已修、已實測 64 槽自動長滿。
>   2. **零件交界縫隙**＝multi-volume 各自生外牆的幾何本質（每邊界 ≈1 線寬溝）。已排查：零回抽（Eric session 內即時關韌體回抽仍有縫）→非回抽問題；**`interlocking_beam` 在數百矩形零件上會炸引擎（Infill failed→當機）**，已試已收回**勿再開**；**XY 補償救不了**（多零件只作用最外輪廓，`PrintObjectSlice.cpp:1238` 重裁）；**彩繪路線（mmu painting）讀碼否決**——`apply_mm_segmentation`(`PrintObjectSlice.cpp:846`) 分區一樣各自生牆＝溝還在，且 `ExtruderMax=16`(`TriangleSelector.hpp:37`) 裝不下 39+ 色。**已定 A 案＝原型層做交錯齒**（v2.1，引擎只看到普通網格不會炸）。
>   3. **實機操作坑（.135 FD300 實測）**：①**「上傳並列印」＝開印即 klippy_shutdown**（用料 60mm＝預擠剛跑完就當）——真因＝SBC 還在掃 7.5MB/39 萬行 metadata，Klipper 同時起跑動作規劃→過載（Timer too close 家族）。**SOP：上傳與開印分兩步、上傳完等 1–2 分鐘再按列印**（78g 那片第一次當、第二次分開就 completed）。②**firmware retraction 每次 klippy 重啟回 `retract_length=1.3`**——這台走 G10/G11 韌體回抽，回抽量由 Klipper 決定不由 gcode。要當場無回抽＝Fluidd 下 `SET_RETRACTION RETRACT_LENGTH=0`（先 `GET_RETRACTION` 記原值），**klippy 一重啟就要重下**。檔案級乾淨＝重啟 portable 重切（吃零回抽預設）。
> - **gcode 自查工具**：`scratchpad/check_phototile_gcode.py <path>`——驗裸 T 殘留=0／Tn 全換 M605x／start 預擠保留／配比和=100／洗料柱全 25×4。四料認 M6052、雙料認 M6051（雙料版要用對話裡那段 M6051 規則版；下棒可把自動判雙/四料合進腳本）。三份 gcode（22h13m/498g/379g FF＋78g/133g FD）皆 PASS。

> **🧭 接手座標**
> - **build worktree**：`D:\dev\2026claude\20260604 ORCA客製\PING-Slicer-phototile`，分支 `ping/photo-tile`，基底＝`release/v3.5.4` tip `00f0f08d`（乾淨、含預擠修正、不含 a11ee870 照片磚）。**tip＝`fb4f9033`（照片磚後處理）、working tree 乾淨**。
> - **原型（產前端＝真相來源）**：`..\照片磚_原型_彩色模擬_v1.html`（v1.8，單檔零依賴雙擊即開）。垂直模式＝主線。
> - **技術全文**：`..\照片磚_Phase0_技術參考.md`（含 §3.5 Eric 實機 ground truth、Cura ImageReader 全演算法）。企劃書 `..\照片磚企劃_20260706.html`、Phase0 報告 `..\照片磚_Phase0_研究報告_20260706.html`。

> **✅ T→M6052 後處理實作定案（commit `fb4f9033`，2026-07-06）**
> 1. **palette 傳遞＝方案 C（零件名稱，優於原列 A/B）**：原型 3MF 每零件名稱自帶配比（`零件色N A70 B30 C0 D0`／`零件色N S0.72`）且 PingSlicer 開檔即載入 Model → 切片後端從 `print.model()` 的 volume 名稱直接解析，**配比隨模型走**（重存/複製不掉、零 GUI 管線）。`Metadata/ping_palette.txt` 退為人讀備援。
> 2. **模組層**（`PingColorMix.hpp/.cpp`，維持純 std:: 可鏡像驗證）：`parse_photo_part_name()`（尾端 pattern、字元集 [0-9.]、四料驗和=100±0.5、數字 token 逐字透傳不重格式化）＋`build_photo_tile_gcode()`（整行 `T<n>` 換 palette 指令＋行尾追溯註解；M104 T0 參數行/palette 外 T/start 預擠 M605x 不動；天然冪等——換過的行不再是 T 開頭）。
> 3. **BSP 層**（與混色同咽喉點分流）：`ping_collect_photo_palette()` **全有全無**（所有列印零件都解析得出＋≥2 件＋同工具不衝突才成立；否則退回原混色邏輯、舊行為 100% 保留）→ `ping_apply_photo_tile()`：同進機閘門、FF↔M6052/FD↔M6051 互驗（不符→error log＋不動）、**filament 數守衛**（palette 最大工具號 ≥ filament 數→不動＋error；防引擎 clamp_exturder_to_default 把超出的零件夾回 T0 吃錯配比）、殘留 `.pingorig` 先還原再替換。照片磚成立時**混色曲線面板配方被忽略**（互斥）。
> 4. **驗證（免 build）**：Python 鏡像 34 測全過（scratchpad `photo_mirror.py`：冪等/CRLF/檔尾無換行/T0abc 不誤觸/全有全無）；adversarial review 10 findings＝0 blocker、1 major（filament 守衛）＋2 minor 已修，餘下 MINOR 帶病可上（strtod locale 曝險與既有混色同級、CRLF 混行尾、`T1 P0` 假想行）。
> 5. **🔴 build 閘門**：Eric 說 OK 才發（照片磚獨立線第一次 build，~2h；Build all workflow_dispatch、看 build_windows 綠＋artifact）。
> 6. **build 綠後驗收**：裝**獨立 portable**（勿覆蓋 v3.5.4 正式 portable）→ 開原型 3MF → FF800 同進切片＋匯出 → gcode 檢查：每個 Tn 換成零件對應 M6052、start 的 `M6052 A25 B25 C25 D25` 還在、無殘留 palette 內 Tn → Eric 實印第一片（垂直四料；**機器線材要先「+」到零件數**——少於零件數時後處理會拒動並記 error log，這是故意的守衛）。
> 7. **⚠ 操作 SOP（review #9）**：照片磚**必須獨立專案開檔**——盤上混入任何非照片磚零件（如校正塊）→ 全有全無偵測失敗→退回混色路徑。已知可接受：混色編輯器面板在照片磚專案仍會顯示（配方被忽略、僅 log）；預覽「混色」檢視著色依曲線非照片磚配比（gcode 正確、純顯示）。

> **✅ 已完成（Phase 0 + 原型 v1→v1.8，全 2026-07-06、全免 build）**
> - **Phase 0**：Cura ImageReader 全演算法規格＋6 坑到手（本機 Cura 5.13.0 模組健在＝光刻畫基準）；HueForge TD/Beer-Lambert 模型、Kromacut/AutoForge 開源參照。
> - **原型八輪**（雙擊 HTML 即驗，每輪 AI 親眼截圖＋console 驗）：v1.1 建議引擎→v1.2 雙料白底漸層→v1.3 四色色相家族→**v1.4 垂直模式**→v1.5 垂直四料＋尺寸→**v1.6 🔴 垂直定主線/平躺凍結**→v1.7 輸出 3MF 多零件→**v1.8 🔴 調色盤＝兩兩色階線**。
> - **v1.8 調色盤結構（Eric 定，重要）**：白↔B/白↔C/白↔D＋B↔C/B↔D/C↔D 共 **6 條色階線 × K 階**（K＝色階數，8 階→40 唯一候選）；每像素填最近格。優點：①同時最多 2 支料在混（機構單純）②**Phase 3 校準色卡＝印這 6 條兩兩階梯就校完**（任意四料混搭校不完）③色差幾無損（11.2）。超 64 線材（`MAXIMUM_EXTRUDER_NUMBER=64`，libslic3r.h:65）自動併最少用的。
> - **3MF 輸出（v1.7，純 JS）**：眾數濾波去雜點→貪婪矩形合併→box mesh→JS ZIP（CompressionStream）→bbs 格式（`3D/3dmodel.model` components 組單物件＋`Metadata/model_settings.config` 每 part 帶 `extruder=n`＝開檔自動指定線材＋`Metadata/ping_palette.txt` 配比表）。Python 拆包＋PingSlicer 開檔雙驗過。輸出鉤子 `window.__buildExport()`。
> - ⚠ **Eric 實機 ground truth（技術參考 §3.5，跨棒鐵律）**：M6051/M6052 混比有**切換距離**、混比做不出銳利邊→**銳邊靠層線**；垂直列印＝換色過渡藏磚體後方、正面實色平整，兩料就能混整套色階（白黑=水墨、白藍=鋼鐵人，Prusa 那類層畫）。
> - ⏸ **平躺（疊色）模式＝凍結不發展**（Eric 2026-07-06）；光刻畫（Phase 1）未開工、非當前重點。

> **⏳ 等 Eric（不阻塞 build）**：實體料色清單（PING 現貨有哪些顏色料、哪些偏透光）——Phase 2 原型用暫定色、Phase 3 校準色卡實印時要真值。

### 🚧 v3.5.5 進度（2026-07-05）
> - 🔴 **發版鐵則（Eric 2026-07-05 定）**：`a11ee870`（首頁「雙料照片」磚＋photo-mixer）＝**測試用、永不列入正式發表**。它疊在 ping/v3.5 本地（未 push），我的 v3.5.5 commit 疊在它之上但內容與它無關。**v3.5.5 正式 build 一律比照 v3.5.4：用 git worktree 從排除 a11ee870 的基底切 release 分支**（基底＝`release/v3.5.4` tip `00f0f08d`，已含預擠修正、不含照片磚），把 ① 牆速（`4fe0217b`：`tools/ping/embed_params.py`＋`resources/profiles/PING/process/`）與 ②PA-CF cherry-pick 上去再 build。**別直接從 ping/v3.5 tip 發版**（會夾帶照片磚）。a11ee870 也**不要 push**。
> - ✅ **③ 防呆 cherry-pick 完成**：`00f0f08d`（預擠同步修正）已回 ping/v3.5 主線＝commit **`2e27e298`**（乾淨無衝突）。ff_extra 範本已含 M6052、mixer 已含 in_body 保留邏輯；regen 不會再打回 T5。
> - ✅ **① 牆速/填充正規化完成（免 build、resource，commit `4fe0217b`）**：吃參數端 `_切片規則同步_來自pingslicer_牆速填充_20260703.md`。產生器 `tools/ping/embed_params.py` 加 `normalize_fast_speed(proc, is_pacf=False)` 取代舊 `HF_SPEED`/`hf_overrides`（75/100/150 逐口徑暫定值，2026-06-11 裁定 → 新規蓋舊規），主迴圈（第 ~380 行）＋`emit_ff_extra`（FF 範本）兩處套用。**111 支製程檔全數命中**：外60／內 min(現,80)（100→80、單料/同進 60 不升）／填150／`sparse_infill_acceleration` 100%→**10000**／首層 `initial_layer_speed` 不動。副作用（已對齊 Cura V2.1）：54 支高流量 solid/top/gap 由舊 override 的 75 交回源檔 60。regen 零意外波及（PING.json/machine/Preset.cpp 未動＝setting_id 穩定）。**⏳ 待參數端牆速抽驗；portable 尚未換裝**（要驗切片可把 `resources/profiles/PING/process/` 同步進 %APPDATA%\PingSlicer\system\PING）。
> - ✅ **④ 頂列常駐版次顯示（Eric 2026-07-06 售服需求，commit `0567977f` on ping/v3.5、未 build）**：BBLTopbar::SetTitle 組入 `PING Slicer V{SoftFever_VERSION}` 前綴＋建構播種（啟動即顯示）；發版 bump version.inc 自動跟上。**發 v3.5.5 時記得 cherry-pick 這顆**（與牆速 4fe0217b 同模式、基底仍排除 a11ee870）。
> - ⏸ **② PA-CF crater — 等參數端交付 Orca `.config`（Eric 2026-07-05 定）**。**範圍：只 FD450 Pro 0.6 單料頭一支**。**取源：請參數端在 PingSlicer 開好該支 PA-CF → 匯出 `project_settings.config` 放 G 槽**（比照他料交付；Orca 匯出同時含製程＋線材＝零猜鍵）。原因：規格 `_切片規則同步_來自pingslicer_PACF專屬製程_20260703.md` 製程層級多為 **Cura 鍵**（`wall_thickness`/`skin_overlap`/`skin_outline_count`/`infill_wall_line_count`/`brim_gap`/`support_z_distance`/`cool_min_layer_time`/`top_bottom_thickness`），規格明令別猜；且現有 `resources/profiles/PING/filament/PING PA-CF.json` 線材值與規格對不上（溫 255≠250／床 70≠60／cool_plate 70／回抽 2≠1.3／缺 z_hop 0.8·hop速 90·韌體回抽·`material_flow_layer_0`=105）——交付檔會一併帶正確線材值。**交付到手後**：接進產生器出「FD450 Pro 0.6 單料頭 PA-CF」單一製程（`normalize_fast_speed` 帶 `is_pacf=True` 跳過牆速正規化，保火山口 50/80/80）＋同步 PING PA-CF 線材。Eric 可選「先把線材溫度暫改 250/60」兩個零疑義項先做。

---

**🏁🏁🏁🏁🏁🏁🏁 現況（2026-07-03 — 🎉 v3.5.4 Release 已發（混色漸層＋預擠同步）；v3.5.5 批次（牆速/填充＋PA-CF）規格在手待開工）**

### 🎉 v3.5.4 Release 已發（2026-07-03）＋ ⚠ 分支狀態與 v3.5.5 開工防呆（下一棒必讀）
> - **Release**：https://github.com/ericlee-lang/PING-Slicer/releases/tag/v3.5.4（Latest）＝ **`release/v3.5.4` 分支 tip `00f0f08d`**（run 28632486737）。含：混色①②③＋B案開關＋**預擠同步修正**＋FF800 四色 0.4＋LAY-11 排序＋版號 3.5.4。Google 雲端 `G:\我的雲端硬碟\2026claude\PING Slicer\` 兩檔已同名覆蓋＋版本資訊.txt 更新（SHA-256 在檔內）。
> - **⚠ 分支分歧（最重要防呆）**：`ping/v3.5` 主線 tip＝`a11ee870`（另條 session 的雙料照片磚，Eric 定不進 v3.5.4）＋**缺 `00f0f08d` 預擠修正**——主線的 ff_extra 範本仍是 T5、mixer 沒有 in_body 保留邏輯。**v3.5.5 開工第一步＝把 `00f0f08d` cherry-pick 回 ping/v3.5**，否則 regen 會把 FF 同進 start 打回 T5、且混色會剝掉預擠同步指令。
> - **預擠同步規則（Eric 實機糾正的 ground truth，勿回退）**：預擠料必須 co-feed——FD 同進 start 保留 `M6050 S0.5`、FF 同進 start 用 **`M6052 A25 B25 C25 D25`（不再用 T5**，T5 留給手動測試；Klipper 端 M6052 是驗證過的路）。混色插碼**只剝「第一個 `;Z:` 之後」的 M605x**（in_body 旗標，`PingColorMix.cpp` Pass 2），第一層之前的同步指令保留。舊認知「start 的 M6050 剝掉沒關係」只對列印本體成立、對預擠不成立（單邊擠料不均，Eric 2026-07-03 實機發現）。
> - **v3.5.5 批次（規格在手、Eric 定排 Release 後）**：①牆速/填充正規化（外60/內min(現,80)/填充150/`sparse_infill_acceleration`=10000、首層不動；規格 `..\_切片規則同步_來自pingslicer_牆速填充_20260703.md`；現況分佈已盤：75/100/150×66支→60/80/150 等；DL1016 跳過）②PA-CF crater 專屬製程（產生器加材料專屬製程：外50/內80/填充80/accel不套10000/溫250/床60/扇30；規格 `..\_切片規則同步_來自pingslicer_PACF專屬製程_20260703.md`）。嵌完回報參數端抽驗。speed 是資源改動、**免 build 可先在 portable 驗**。
> - **PETG 接縫**：Eric 嫌接縫粗＋起停凸瘤（現值＝ABS 定稿 aligned/gap15%/scarf=none 套在 PETG 上）→ 已轉參數端定 PETG 接縫標準（scarf 值得為 PETG 重測／seam_gap／PA 校準），等定稿再嵌。
> - **本機狀態**：portable＋%APPDATA% ＝ v3.5.4 預擠版（v44、M6052、DL1016 已回注）。舊備份 `-old-preB`/`-old-preprimefix`/`-old-premix` 已於 2026-07-12 清除。**DL1016 備援**（G 槽 Dowell 源已失蹤）＝`D:\dev\2026claude\20260604 ORCA客製\DL1016_本機注入備援\`（11 檔＋PING.json 註冊條目）。
> - 預擠 co-feed 已驗到 gcode/profile 層；**實機 co-feed 未印**（Eric 選直接發）——同事若回報預擠異常，先查 start 段 M6050/M6052 有沒有在。

### ✅（已收成）混色漸層整合 — ①②③ 全原生＋B案開關＋Eric 5 項驗收全過（細節保留供維護）
> **現況**：①插碼已 build 驗過（commit `06d04e63`、run 28526818670 綠；FD M6051 240 支逐層/S 單調、FF M6052 四值和=100、M6050 剝除——暫存 gcode 直驗＋Eric 確認）。②③ 已寫完（本次 commit）。
> - **② 原生預覽著色**：libvgcode 加 `EViewType::PingColorMix`（Types.hpp）＋per-layer `Palette` 色表與 setter（ViewerImpl/Viewer）；**混色數學不進 libvgcode**——GUI 端 `GCodeViewer::update_ping_mix_colors()` 把曲線烘成色表塞入（仿 set_tool_colors 髒旗標、改曲線重上色不重切）。同進機切片後自動切「混色」檢視；legend 頂→底 11 級漸層圖例。**換機型清單重建（review 三路同抓 blocker）**：view_type_items 只在首次 init／簡易進階切換重建（init 有 `m_gl_data_initialized` 早退！），已在 load_as_gcode 加「同進狀態 vs 清單含混色」不一致偵測→重跑 update_by_mode＋重定位 m_view_type_sel 防越界。
> - **③ 原生曲線編輯器**：`src/slic3r/GUI/PingMixEditor.hpp/.cpp`（新檔，已登錄 src/slic3r/CMakeLists.txt）掛 `Preview` 右側（GUI_Preview 外層 sizer 改 wxHORIZONTAL），同進才顯示（`Preview::update_ping_mix_editor()`；呼叫點＝Plater set_current_panel preview 分支＋load_print_as_fff）。雙料拖點曲線／四料堆疊帶、三模式、範本（同進/漸層/雙色/彩虹）、低流量（min_flow 0.10↔0.05）、E1..E4 色票（**同進機切片端只有 1 槽拿不到實體色→使用者自選**，wxColourDialog）。拖曳中只重畫、放開才 commit（免逐幀重烘百萬 vertex）；拖曳中 update_from_plater 不覆寫狀態（切片完成事件插隊防護）。**中文字串一律 wxString::FromUTF8**（/utf-8 有開但 wxString(const char*) 走 CP950——wizard conflation 同款坑）。
> - **資料流**：編輯器→`Plater::set_ping_mix_state()`→AppConfig 持久化（`ping_mix_dual/quad/colors`；quad 序列化含 `mf=` 低流量欄位、舊格式相容、載入時值域消毒）＋`BSP::set_ping_mix_recipes()`（`m_ping_mix_mutex` 保護、worker 咽喉點鎖下複製）＋`refresh_ping_mix_preview()` 重烘。①的硬寫測試曲線已換成 `default_recipe()`「同進還原」（未編輯＝韌體原生 50/50、25×4，既有客戶零影響）。**改曲線→重匯出/重上傳即吃新配方**（冪等插碼、免重切）。
> - **驗證**：純邏輯 Python 鏡像 vs web TS 全等（dual 101＋quad 286 點、序列化 round-trip＋mf 相容＋損壞值消毒）；4 路 adversarial review（編譯/執行緒/規格/整合）15 findings 全處理。
> - **已知可接受（不擋 build）**：①UI 語言非中文時 imgui「混色」缺字方框（zh_TW 主客群）②切片後換機型未重切期間預覽照新機型烘色（重切自癒）③編輯器尺寸不隨 DPI 熱切換重算（msw_rescale 未接）。
> - **⏳ 下一步**：Eric 說 OK → 發 build → 換 portable → 驗收：FD 同進切片看右側編輯器＋自動混色著色、拖曲線→重匯出比對 M6051 跟著變、FF 同進四料堆疊帶＋M6052、非同進機無編輯器無「混色」項、換機型來回切「混色」項正確出現/消失。

### （背景紀錄 2026-07-01）混色漸層整合進 Orca — 🔄 改走全原生（核心插碼模組已驗證）
> **🔄 2026-07-01 晚 架構轉向（Eric 定）**：放棄「嵌 web」，改 **全原生**。理由＝穩定度（拿掉 WebView2 執行環境依賴＋JS↔C++ 橋接這些活動零件）＋Eric「web 端不維護了」。三塊全做進 Orca：①核心插碼（C++ 後處理）②Orca 原生「預覽」頁依曲線著色 ③原生曲線編輯器面板。web 混色器（`D:\dev\ping-color-mixer`）退為「設計藍圖／驗證參照」。
> - ✅ **① 核心插碼模組完成＋邏輯已驗證（免 Orca build）**：`src/libslic3r/GCode/PingColorMix.hpp/.cpp`（零 Orca 依賴、純 std::；移植 mixer.ts/gradient.ts/quad.ts）。`build_mixed_gcode(gcode, recipe, out)`：掃 `;Z:` 逐層插 `M6051 S..`（雙料/FD 同進）或 `M6052 A.. B.. C.. D..`（四料/FF 同進）、剝既有 M605x（含 start 的 M6050 S0.5）、去重；z→t 用 `;Z:` min/max 正規化。含公開取樣 `sample_ratio`/`sample_quad_mix`/`mix_to_percents`（給預覽著色共用）。**驗證法（不用 build）**：Python 鏡像 C++ 邏輯 vs web 真實 `buildMixGcode`/`buildQuadGcode`，4 recipe（linear/step/smooth 雙料＋rainbow 四料）**djb2 hash＋長度逐字元全相同** → C++ 演算法忠實無誤（C++ 語法待 Orca build 驗）。驗證腳本在 scratchpad `mirror.py`。
> - ⏳ **① 剩整合**：模組接進 Orca 輸出/上傳點（用 Orca 層 z 範圍當 min/max、讀「混色配方」設定）＋ CMakeLists 加檔 → 需 build。
> - ⏳ **② 原生預覽著色**（GCodeViewer 依混色曲線把各層染色）、**③ 原生曲線編輯器面板**（照 web 藍圖用 wxWidgets 重建：拖點/三模式/四料堆疊帶/範本）。
> - ⚠ **下面「Phase 1/Phase 2 嵌 web」段是已放棄路線**，保留當紀錄。web 端 `main.ts` 的嵌入模式改動＋`resources/web/mixer/` 打包**未 push、可留可刪**（嵌 web 不做了）。

> **📋 下一棒：native 三塊實作計畫（讀這段就能接）**
> - **共用資料模型**：`PingMix::Recipe`（已在 `PingColorMix.hpp` 定義：kind Dual/Quad、mode Linear/Step/Smooth、stops/qstops、min_flow）。①②③ 都用它。
> - **① 接進 Orca（先做、最小可驗）**：
>   1. CMake：把 `PingColorMix.cpp` 加進 `src/libslic3r/CMakeLists.txt`（libslic3r 目標的來源清單）。
>   2. 配方儲存：先在 GUI 層存一份 `Recipe`（Plater 或 MainFrame 成員），編輯器（③）更新它；未接編輯器前可**硬寫一條測試曲線**先驗管線。
>   3. Call site：切片完成後（`Plater.cpp on_slicing_completed` 9395）或匯出/上傳前，若「同進機型＋有配方」→ 讀 `get_current_slice_result()->filename` 的 gcode → `build_mixed_gcode(gcode, recipe, out)` → 覆寫該檔（保留原檔供改曲線重插，不必重切）。同進判定＝printer `model_id`/name 含「同進」（FD→Dual、FF→Quad）。**模組內部自己用 `;Z:` min/max，不必外傳 z 範圍。**
>   4. 驗證：硬寫曲線→切片→開輸出的 gcode 檢查 M6051/M6052 逐層對（可再用 `mirror.py` 對照）。**這步是第一次 build。**
> - **② 原生預覽著色**：`src/slic3r/GUI/GCodeViewer.cpp` 有多種 color mode（依類型/線材/速度…）。加一個「混色」mode：每個 move 依其層 z→t→`sample_ratio`/`sample_quad_mix`→混成 RGB（雙料 blend color1/2；四料需**再移植 quad.ts `mixRgb`** 的 linear-RGB 加權）。研究重點＝GCodeViewer 的 Extrusion color 陣列怎麼填、per-move 怎麼拿到層 z。改曲線→重算著色即時更新。
> - **③ 原生曲線編輯器**：wxWidgets 自繪面板，照 web 藍圖（`ping-color-mixer/src/curveEditor.ts`＝雙料拖點曲線、`quadEditor.ts`＝四料堆疊比例帶、`overlay.ts`）重建：拖點調比例/高度、雙擊增刪點、三模式(漸層/階梯/平滑)、四料堆疊帶、範本(同進/雙色過渡/彩虹)、配方另存/載入。放在「預覽」頁側欄或「混色」分頁（與預覽著色同頁最順）。編輯→更新 `Recipe`→觸發 ② 重著色。
> - **驗證省 build 心法（本專案・重要）**：本機**無 C++ 編譯器**（MSVC 未配置、不在 PATH），Orca build ~2h 很貴。**純邏輯 C++ 要驗，就用 Python 鏡像該邏輯、對照 web 混色器真實輸出做 djb2 hash 比對**（scratchpad `mirror.py` 是範本；今天 ① 就這樣零 build 驗過）。GUI/著色類無法這樣驗的，才進 build，且**累積多塊一次 build**、build 前先問 Eric。
> - **web 藍圖 dev server**：`cd D:\dev\ping-color-mixer && npm run dev` → localhost:5173（取 ground truth／看 UX 藍圖用）。

### （已放棄路線·紀錄）混色嵌 web — Phase 1 完成實測、Phase 2 剩純 C++
> 目標：把 web 混色器（mixer.ping3dp.com，repo `D:\dev\ping-color-mixer`）嵌成 Orca 一個「混色」分頁，切片後直接調色階、免匯出/丟檔；輸出的混色 gcode 回 Orca 原生上傳。架構定案（Eric）：**獨立「混色」分頁、切片後亮起、同進機型才啟用**。
- **機制**：純 post-slice——混色器在每個 `;Z:` 層標記插 `M6051 S<比例>`（雙料/FD 同進）或 `M6052`（四料/FF 同進），比例來自高度→比例曲線。不動切片。**FD 同進 start_gcode 的 `M6050 S0.5` 被混色器剝掉沒關係（Eric 確認：M6051 從第 0 層全控）；FF 同進 start_gcode 是 `T5`（非 M605x、不被剝）。**
- **✅ Phase 1（web 嵌入模式）完成＋瀏覽器實測 round-trip 過**（240 M6051）：`D:\dev\ping-color-mixer\src\main.ts` 加 `EMBED`(`?host=orca`)、`window.__pingHostLoad({name,gcode,mode,colors})`、`postToHost`(回傳 `window.wx`/Edge WebView2/iframe 父窗)、隱步驟1-2 CSS、ready handshake；測試台 `_orca_host_test.html`。tsc/build 過。**⚠️ 尚未 push（push 會部署 Vercel 上線站；嵌入模式是 gated 的、不影響標準站，push 與否 Eric 定）。**
- **✅ Phase 2 步驟 1（打包）完成**：`--base=./` 產相對路徑 dist（`dist-embed`）→ 複製進 `resources/web/mixer/`。執行期載入路徑＝`file://<resources_dir>/web/mixer/index.html?host=orca`（web 資源隨 build 出貨、query 可用，比照 web/guide）。
- **⏳ Phase 2 剩純 C++（步驟 2-5，勘查已定位接縫）**：
  1. 新分頁：`MainFrame::init_tabpanel`(MainFrame.cpp:1210) 建 `m_mixing_panel`（wxPanel+WebView 載 mixer）；`TabPosition` 加 `tpMixing`。Notebook 無 SetPageEnabled → 用 `InsertPage`/`RemovePage`（仿 `show_device` 1348 條件插頁）。
  2. 條件顯示：切片後(`update_slice_print_status` 2341)＋同進機型才插頁。**同進判定：printer 的 `model_id` 含「同進」(FD→2色 M6051) 或 FF 系列(→4色 M6052)**（FD 用中文「同進」、FF 範本 model_id 可能是 tongjin，實作時以 name/model_id 含「同進」＋FD/FF 前綴判）。
  3. 餵料：切片完成(`Plater.cpp on_slicing_completed` 9395)→`partplate_list.get_current_slice_result()->filename`(GCodeProcessorResult.filename)讀 gcode→`RunScript` 呼叫 `window.__pingHostLoad({name,gcode,mode,colors})`（colors 取料槽色）。
  4. webview 橋接：Orca `WebView.hpp`(CreateWebView/LoadUrl/RunScript)＋`wxEVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED`；handler 名 `wx`(WebView.cpp:300)。範式：`ModelMall.cpp`:100-137、`WipeTowerDialog.cpp`:432-498（收 JSON→CallAfter→RunScript）。web 端已用 `window.wx.postMessage(JSON)` 送 `ping-mixer:output {name,content,summary,doPrint}`。
  5. 回傳上傳：收 output→寫暫存 .gcode→`BackgroundSlicingProcess::prepare_upload` 設 `PrintHostUpload::source_path`→`PrintHostJobQueue::enqueue`（doPrint=上傳並列印）。
  6. **build（閘門）**：全寫完→**先確認才發 ~2h build**→Eric 實機驗「新比例吃得進去」。建議 build 前先 adversarial review C++ 降低白燒 build 風險。
- 勘查全紀錄：本 session workflow `wf_2edd472a-364`（9 代理，web×4+orca×5，接縫/檔案/行號都在）。

### ✅ 3in1 收成 2 槽 — 已做＋Eric 切片實測通過（FF600 3in1 body+SUP 分離正確、換料 137、洗料塔正常）
- **機制**：T4/T3 觸發放在**線材自己的 `filament_start_gcode`**。新建 2 支專用線材 **`PING PLA(3in1)`**(`T4`＝body 前三同動)＋**`PING SupPLA(3in1)`**(`T3`＝第四 SUP)，每口徑一支(@FF 0.4/0.6/1.0)、溫 210、只掛 FF600/FF800 3in1、註冊進 PING.json。
- **機器**(FF600/FF800 3in1 全口徑)：`default_filament_profile`→2 槽 `[PLA(3in1), SupPLA(3in1)]`；6 製程 `support_filament`/`support_interface_filament` 4→2；6 製程 `support_base_pattern`→`rectilinear`（消「不支援空心底座」警告）。
- **韌體對應(Eric 確認)**：T0/1/2→第1槽 body、T3→第2槽 SUP。
- ⚠️ **Orca 坑（已記入 SSOT core-rules ③）**：①新線材要獨立 alias 否則被併組選不到 ②要進 `PINGSlicer.conf` 可見清單才在快捷下拉出現 ③改 conf 要連 `# MD5 checksum` 重算(＝body UTF-8 MD5 大寫)否則重開被判損毀回退 ④切印表機 carry-over 會讓第 2 槽沒套 default，手選 SupPLA(3in1) 即可、fresh 安裝首選會套對。
- **支撐材顏色→淺灰 `#D3D3D3`**（8 支 Sup 線材，切片辨識用；原 #808080）。
- ⚠️ **全部只在 %APPDATA%+portable、未進產生器**（.bak-2slot/.bak-sbp/.bak-color 備份齊）。**下一步：整批（3in1 2槽＋FF四色/同進＋支撐色）編進 `embed_params.py` 產生器＋同步 repo。**
- 🔒 仍凍結：`T4→T012`/`T5→T0123` 命名、同進/3in1 M-code vs 留 T、真機 T 同動回抽。

### ✅ Apple Mac 簽名 — D-U-N-S 已到手 `656252039`（聯造，2026/6/21 核發，記進 ping-master）
- 下一步 Eric 做：辦 Apple Developer 公司帳號(US$99/年,填此號)→Mac 產憑證/密碼/Team ID→設 7 個 GitHub Secrets→跟我說「設好了」我改 `build_orca.yml` L166 條件啟用簽名。指南 `Apple簽名設定指南.html` 階段 1 已標完成。

---

**🏁🏁🏁🏁🏁 現況（2026-06-30 收工 — FF800 同進崩潰已修+驗證；FF 模式定義大整理；3in1 部分凍結等 Klipper）**

### ✅ FF800 同進切片崩潰 — 根因查實並修復、Eric 實測通過
- 真因＝**start_gcode 的 `T5`（FF 自訂進料巨集）被 slicer 當「切到第5噴頭」→ `GCodeProcessor::process_T`(`GCodeProcessor.cpp:5364`) 偵測 `eid>=filaments_count` 印 "Invalid T" 卻沒 return → `process_filament_change`→`m_filament_maps[eid]` 越界**。非 config、非 get_at（診斷 build 反證）。
- 修法 commit **`c9b4f8d7`**（ping/v3.5）：process_T 偵測無效 T 直接 return（T 仍輸出給韌體）。一次根治 0.4/0.6/1.0。**build run 28416466362**、Eric 實測 FF800 同進 0.4+0.6 圓柱切完不崩。**詳見 `SOP_加機型.md §2.5`（已回填正確真因）。**
- portable 已換裝此 build binary（舊備份 `D:\PING-Slicer-portable\_fixbuild_bak`、診斷版 `_prediag_bak`）。

### ✅ FF 模式定義大整理（材料數/層高/prime/support）— Eric 2026-06-30 逐項定
> ⚠ **以下 FF profile 改動全部只在 `%APPDATA%\PingSlicer\system\PING` + `D:\PING-Slicer-portable\resources\profiles\PING`，未進 repo / `embed_params.py` 產生器 → 重產會消失，驗收 OK 後務必編進產生器。** 各檔有 `.bak-*` 備份。
- **材料數定義**：四色＝**4 料**(4色PLA)；同進(四進一)＝**1 料**；3in1＝**2 料**(前三同動 body + 第四 SUP)。
- **四色**：預設 4 槽不同色 PLA(紅/綠/藍/琥珀 `#FF0000/#00B050/#0070C0/#FFC000`)；參數＝**PLA+PLA**（`support_z`=**0.3**）；prime **4 條**(T0~T3)。
- **3in1**：料槽 `[PLA,PLA,PLA,SupPLA]`；參數＝**PLA+SUP**（`support_z`=0）；層高 0.25/0.35/0.45；prime **2 條**＝**T4(前三同動)擠body + T3(第四)擠SUP**。
- **同進**：1 料；層高 0.25/0.35/0.45；prime **2 條**(T5)。**修了 FF800 同進 0.4 的 bug**(原誤用 T0/T1 雙噴頭 dance→改 T5)。
- **層高**(同進+3in1)：0.4→0.25/首0.3、0.6→0.35/首0.4、1.0→0.45/首0.5；製程**已改名**對齊(`0.25mm/0.35mm/0.45mm @...`，PING.json+機器引用同步、0斷鏈)。
- prime 幾何：FF800 Y-359、FF600 Y-280、X±100、每條 Y+2；同進 E60/條、3in1 E100/條(沿用原值，實機可調)。

### ✅ FF600-3in1 / FF800-3in1 模式加入 + wizard 修正
- 3in1 machine/process/PING.json 三處註冊本就齊全→確認可用。
- **wizard 家族分組修正**：`resources/web/guide/**21.js + 24.js**` 的 `strSeries` regex 原只去 `單料頭|同進`、漏 `3in1|單噴頭`→補上(repo+portable 都改)。**改 guide JS 後要清 `%LOCALAPPDATA%\PINGSlicer\EBWebView\{Cache,Code Cache}` 才生效**(重啟不夠)。詳見記憶 ping-machine-build-checklist。
- **machine_model_list 重排**：同型號變體相鄰(FF600 base/同進/3in1、FF800 同上、DL1016 殿後)；規則記進 **ping-ux LAY-11**。
- **FF800 單噴頭移除**(暫無此模式)：三處註冊移除、檔案改 `.bak-removed`。

### 🔒 凍結中（等 Klipper 韌體 session：「Blend mode implementation」/「Machine 192.168.2.135 anomaly」，可能動 Klipper C）
- **真機列印當掉**：T 同動模式下回抽是否真四顆同步(G10/G11 ALL_SYNC)＝韌體層問題，非 slicer。slicer 越界修正是獨立安全網、已生效。
- **3in1 收成「2 槽」**(目前 config 仍 4 槽[3PLA+1SUP])、**T4→T012 / T5→T0123 命名標準化**、**同進/3in1 觸發改 M-code vs 留 T** — 全等韌體方向定案再一起做。
- T4/T5 Klipper 巨集定義(前三同動/四全同動)在 `G:\我的雲端硬碟\2026claude\20260530 Klipper\...\Macro_T0_T1_T2_T3_T4_T7_T8.cfg`；雙料混色＝`M6050/M6051 S<比例>`(`Macro_M6050_for2.cfg`)。

### 📋 待辦（下一棒/跨 session）
- FF 模式定義已 send 給「0628 切片參數」session 同步進 ping-slicer。
- FF profile（含 prime/層高/材料/4色/3in1）驗收 OK 後**編進 embed_params.py 產生器**＋同步 repo resources。
- 韌體方向定案後：3in1→2槽+T012、prime 的 T 命名替換、決定同進/3in1 用 T 或 M-code。
- 此 GCodeProcessor 修正併入正式 Release（現只在 ping/v3.5 build 好未發版）。

---

**🏁🏁🏁🏁 現況（2026-06-29 收工 — 支撐/層高雙修正已發版；FF 同進/3in1 建於 portable；FF800 同進切片崩潰待查）**

### ✅ 已完成並發版（v3.5.3 + p200plus 重 build 重發 Release）
- **支撐預設修正**（v3.5 `76112998`／p200plus `54ba8dd6`）：葉檔攤平值夾帶 `rectilinear`/`tree_support_wall_count=0` 蓋掉 common 的「空心／樹狀牆1」→ 產生器 `embed_params.py` 組 proc 時 pop 這兩 key + 修現有葉檔；**ABS+SUP 黃金配方(normal/rectilinear)刻意不動**。
- **max_layer_height 全庫歸一＝0.75×口徑**（v3.5 `09eecb43`／p200plus `4371b5db`）：源檔一律塞 0.35,把 1.0 口徑標準層高 0.5 被 OrcaSlicer 自動 Reset 成 0.35（`ConfigManipulation.cpp:215`）。FD450/600/800 Pro 1.0（9 台）受惠。產生器機器產出時 `max_layer_height=0.75×口徑`。
- **已 push＋CI build（Build all, workflow_dispatch 手動觸發）＋更新 Release**。⚠ build 整體常顯示 failure（Flatpak/Unit Tests），看 **build_windows job 綠燈＋有 artifact** 才算成功（坑#10）。
- **官網下載方案規劃**（未動工）：`官網下載架構建議.html`。安裝檔放外部(GitHub Releases 過渡→Cloudflare R2 `download.ping3dp.com` 長期;ping3dp.com DNS 已在 Cloudflare),下載頁放 Vercel。**Google 雲端收納夾 `G:\我的雲端硬碟\2026claude\PING Slicer\`**（`PingSlicer-Windows.exe`/`PingSlicer-macOS.dmg` 穩定檔名、覆蓋更新→網站連結不變;`版本資訊.txt`）。下載頁原型 `下載頁_PingSlicer.html`。**之後新 build 好→覆蓋這兩檔＋更新版本資訊/下載頁版本號SHA**。R2 待 Eric 之後弄。
- 雜項：flush 自動計算彈窗→Eric 自行在 偏好設定 把 `auto_calculate_flush` 設 disabled。

### 🟡 FF 同進/3in1（★只在 portable + %APPDATA%,未進 repo/產生器！）
- 依「FF四料規格 V3.5_20260628」(`FF四料_3in1_同進_參數規格_V3.5_20260628.html`,切片參數線交付)建:**FF800 0.4 四色 + FF600/800 × {同進,3in1} × {0.4,0.6,1.0}**。
- 裝在 `D:\PING-Slicer-portable\resources\profiles\PING` 並同步 `%APPDATA%\PingSlicer\system\PING`（★★ **app 實際讀 %APPDATA%、非 portable resources**——見記憶 pingslicer-profiles-read-from-appdata）。
- ⚠ **尚未編進產生器 `embed_params.py`**→重產會消失。**確認全部可用後才正式編進產生器出貨。** FF800 機型 model 的 nozzle_diameter 已補 0.4。
- 建機器三個坑(已解、見記憶)：①註冊進 PING.json 的 machine_model_list/machine_list/process_list ②高流量線材 `compatible_printers` 要含新機型名(否則選了不顯示) ③加新機器會重置「已選印表機」→跳設定精靈,重選即可。
- 規格待校準(不擋):同進速度上限(Q值)、prime line E量、T4/T5 End-gcode 各噴頭吐洗、1.0 層高規格 0.5 vs 現有四色 0.35、介面密度/洗料塔 30/75/purge120 的 Orca 對應。

### 🔴 待查（最優先）：FF800 同進切片崩潰「非法存取」
- 症狀：FF800 同進切圓柱,**連正常切片(不勾花瓶)都在「產生 G-code 第400層 80%」閃退**。
- 決定性隔離(同一圓柱)：**FD800 Pro 同進 ✅／FF800 四色 ✅／FF800 同進 ❌**。
- 已排除：模型、FF800 床/硬體、FD 同進結構、高流量線材(換 PLA-220 也崩)、T5 起始 gcode(拿掉也崩)、per-extruder 陣列(機器+製程都已用 FD800 同進結構重建)。
- 結論：「FF800 × 同進」殘留某個**極小差異**＋引擎敏感(對應 OrcaSlicer #8292 spiral-vase 越界家族)。**下一棒：對 FF800 同進 vs FD800 Pro 同進 做 machine+process byte 級全 diff 找最後差異;或上 RelWithDebInfo debug build,在 `GCode.cpp:3567/3668 EXTRUDER_CONFIG(nozzle_diameter)`、`Config.hpp:617 get_at` 下中斷點抓越界。** portable 留了 `.bak*` 備份(8 machine/6 process)。

**🏁🏁🏁🏁 現況（2026-06-16 收工 — v3.5.3 通用版＋P200+ 客戶版雙線發布；本 session 跨 6/11–6/16、主線 23 commit＋p200plus 分支 4 commit 全 push）**

- ✅ **通用版 Release v3.5.3**：https://github.com/ericlee-lang/PING-Slicer/releases/tag/v3.5.3 已**更新到最新 build**（run `27539330060`・commit `88ca79af`；Windows installer＋Mac dmg，版本對齊 3.5.3）。本機 portable 已換裝（`-old-b14` 備份）。
- ✅ **P200+ 客戶專屬 Release**（獨立 prerelease，不在通用版）：https://github.com/ericlee-lang/PING-Slicer/releases/tag/p200plus （Mac dmg，分支 `ping/p200plus`・commit `eb8a365a`）。**過渡機客戶交付專用、與通用版分線維護。**
- ✅ **本 session 後續完成（6/12–6/16）**：
  1. **製程下拉截短**（@機型(口徑) 隱藏）：TabPresetComboBox TYPE_PRINT 用 alias（label(false)）、Tab.cpp 選擇回填走 get_preset_name_by_alias（`c720402a`）。**機型/線材維持全名**（per-nozzle/＠FF 同 alias 必須全名區分）。
  2. **首層速度 25→40**（參數端修 V2.1 容器堆疊取 global 25 而非 E0 蓋寫 40）（`a243ab26`）。
  3. **頂底實心填充交叉 45,135**（`solid_infill_rotate_template`，原垂直單向）（`e3774cd8`）。
  4. **組合製程連動線材**（手選製程→雙料兩槽自動配對：PLA+SUP→PLA-220+SupPLA 等；只在 Tab combo selection_changed 觸發、載專案不蓋）＋ **G-code 行視窗 NoBringToFrontOnFocus**（不再壓住「切片完成」通知關閉鈕）（`53a4412c`）。
  5. **gcode 頁首去重複 + 版本對齊**：`(PING Slicer V3.5 3.5.0)`→`(PING Slicer 3.5.3)`（header 去 app 名稱「 V3.5」＋ SoftFever_VERSION 3.5.0→3.5.3）（`95ed906e`/`88ca79af`）。
  6. **P200+ 完整客戶版**（衍生機型機制，主線 embed 邏輯＋ `ping/p200plus` 分支精簡）：床門開250/門關預擠200算(Y-90)/高200/套FP300/口徑0.4-0.6（去0.2）/命名「P200+」非FP200／床貼圖門關200橘圈／底板STL縮250切齊網格。`PING_ONLY=P200+` 環境變數觸發精簡 regen（只此一台、FF 線材砍）（`fc1ce2b9`→`53a7e610`→`18bbe8ff`→`bb29e1da`→`5e199c31`；分支 `0edca788`→`eb8a365a`）。
  7. **支撐通用優化**（全機型，fdm_process_ping_common）：`tree_support_wall_count=1`（1圈外牆）＋`support_base_pattern=hollow`（主體空心省料好拆）（`5e199c31`）。⚠ **通用版此改動待下次 build 才進安裝檔。**
  8. **DL1016（Dowell 第三方 XY 大機）本機注入**：XY 矩形床 1000×1600×600/單噴頭/2.85mm PLA/口徑0.8-1.2-1.6。`tools/ping/add_dl1016.py` 讀廠商 .3mf 注入本機 portable＋%APPDATA%，**不碰 repo、不上 release**（`6e77e978`）。⚠ **每次換新 portable 後需重跑 add_dl1016.py 重新注入。**
  9. **切片規則同步回報**（PM 6/15 協定）：本 session 確立的切片規則已 send_message 給「0615 切片參數 V3」session 收進 ping-slicer skill。
- 🆕 **規則變更（6/16 新增/確認）**：
  7. **支撐通用預設＝牆數1＋主體空心**（fdm_process_ping_common，全機型）。若只要某機型 override 到製程層。
  8. **P200+ 命名鐵則**：用「P200+」不用 FP200（客戶端既有名、要一致）；客戶專屬不進通用版（`PING_ONLY` 觸發）。
  9. **衍生機型機制**（BED_OVERRIDE）：吃他機 config 改列印範圍（area_diameter 縮 printable_area／prime_y_shift 移預擠／nozzles 限口徑／bed_texture 專屬貼圖）；床盤 STL 用 binary 縮放（XY 置中×scale、Z 厚不變）。
  10. **切片規則同步協定**（PM 定）：ORCA 收工碰切片規則→回報切片參數 session；動切片前先載 ping-slicer skill。
- 📌 **下一棒待辦（依優先序）**：
  1. 🔴 **Apple Mac 簽名**（Eric 決定辦公司帳號）：等 Eric 申請 D-U-N-S（1-2週）→辦 Apple Developer→產憑證→設 7 個 GitHub Secrets→**通知後我改 `build_orca.yml` L166 條件**（`github.repository=='OrcaSlicer/OrcaSlicer'`→`'ericlee-lang/PING-Slicer'`、ref 條件放寬 PING 分支）啟用簽名+公證。指南：`D:\dev\2026claude\20260604 ORCA客製\Apple簽名設定指南.html`。等待事項已寫 `待確認\`。
  2. **通用版支撐改動**（牆數1+空心）下次發版 build 才生效——累積到下批一起 build。
  3. FF600 0.4 首件實機驗（參數端標未實測）；閒置沖刷間隔規範值（與參數端）。
  4. 轉達工程端：KlipperScreen 出貨 image 加 `print_estimate_method: slicer`。
  5. DL1016 切片預覽若有異常回報（廠商參數未實機驗）。
  6. 舊 portable 備份 `-old-b8/b10/b12/b14` 確認穩定後清。

---

**🏁🏁🏁 背景（2026-06-11 收工 — Release v3.5.3 已發、B12 已換裝、全日 10 commit 全 push）**

- ✅ **Release v3.5.3 已發**：https://github.com/ericlee-lang/PING-Slicer/releases/tag/v3.5.3 （build B12=run `27353221446`・commit `438ee102`；Windows installer + **首發 Mac dmg**，繁中 notes）。**portable=B12 binary + profiles v37** 已換裝；`%APPDATA%` v37 同步。備份：`D:\PING-Slicer-portable-old-b8`/`-old-b10`（可刪）。
- ✅ **B8 六項總驗收全過**（使用者實測）：splash 透明✓ 主機清單瘦身✓ Fluidd metadata✓（estimated_time/M73 解析正常）檔名格式✓（修復後）對話框 logo✓（B10 改標題列後）線材清單✓（白名單修復後）。設備預設名一項未明測（程式在，無回報問題）。
- ✅ **本日完成（10 commit，74629eb9..438ee102）**：
  1. **閒置線材沖刷**（新功能，使用者需求「每層每支料都洗」）：`wipe_tower_max_idle_layers`（process、預設0；PING common=1）→ `ToolOrdering::insert_idle_purge_extruders()` 把閒置 N 層的線材插入該層工具序列→塔上照常規 toolchange 沖刷。首印層跳過（priming 已涵蓋）、單線材自動短路、UI 多線材頁+zh_TW 翻譯（`74629eb9`）。**已實測**：FD300 0.25 雙料 388 次換料、塔料 12.9g>模型——小口徑代價大，間隔規範值待定（調 5 可大幅回落）。
  2. **檔名模板 Non-ASCII 修**（B8 驗收抓到、匯出全炸）：模板「開頭/`}` 後」裸中文觸發 PlaceholderParser throw → 前綴包進字串字面值 `{"雙色_"}`（坑#17）。97 支 process+filename_tpl() 同步（`49fd9ee5`）。
  3. **對話框 logo→標題列左上**（使用者驗收回饋）：MsgDialog SetIcon(mainframe icon)+內容區品牌 logo 隱藏（語意圖示保留 64）；ErrorDialog 灰階圖移除（`38ee8805`）＋傳送框 Cancel 翻譯 L→_L（`0c648cbb`）。
  4. **線材選擇下拉顯示名稱**（支撐/筏層「2 PETG」對不上「PING SupPLA」）：DynamicFilamentList×2 改 alias/name（`9b84c293`）。
  5. **吃 6/11 參數端交付×2 波**（總說明 09:32 與 14:38 版）：速度兩線定稿進源檔（雙料/FP 60-80-150、單料頭/同進 50-60-150、首層25）→ **proc_overrides 大清理**（加速度/scarf/單料速度 override 拿掉、僅留 seam aligned）；SupPLA 210→220；SupABS 對值（type ABS/密度1.04/玻轉110/240-270/收縮99.7%/flow0.98）；**PING PETG - 235 新建**（48 檔指向；製程零差異→純線材切換、parse_dir 跳 _PETG）；**FF600 新增 0.4 口徑**（未實測！首件請驗）（`efb7eb22`/`3381b887`）。
  6. **高流量：兩級→收斂按噴頭一級**（★節「每口徑兩支」做完 191 支後使用者現場裁定「參數太多」推翻）：FD300 系/FP=只一般流量、FD450/600/800 Pro=整支高流量（75/100/150/75、唯一一級不帶尾碼）、FF 實機。製程回 98 支。HF_SPEED 口徑可調表保留——Q 值出來「哪口徑調多少」改一格重產（`438ee102`）。**此裁定與參數端★節規格不同，需轉達**。
  7. **flush 預設歸零三處**（FD300 同料仍跳 84=0.3×280；flush 參數是專案層 preset 帶不動）：AppConfig auto_calculate_flush 預設 disabled、PrintConfig flush_multiplier 0.3→0、GLCanvas3D「沖洗體積為0」警告停用（歸零=設計常態）。沖刷量=min purge 下限（主體15/SupPLA30）（`438ee102`）。
  8. **線材白名單廢除**（FD300 Pro 線材消失——8 支手維護線材 compatible_printers 是 B4 前舊清單）：手維護線材全機相容（封閉生態）、FF 高流量子 preset 維持口徑配對（`ba24317d`）。
  9. **新工具**：`verify_profiles.py`（參照完整性+檔名模板邊界防回歸，每次 regen 後跑）、`mo_patch.py`（新 UI 字串注入預存 .mo，坑#16 配套）、`monitor_print_time.py`（Moonraker 列印時間估計監測）、`diff_audit.py`。
  10. **「時間爆炸」客訴定案**（FD300 客戶端螢幕 7-8h 一直漲 vs 預估 2h30）：實測數據鏈完整——切片器預估極準（17.9 實測 vs 17.8 預估）、M73/metadata 全正常；爆炸=KlipperScreen 預設 auto 估計混「檔案進度外推」，前期灌水後收斂。**修法=機器端 KlipperScreen.conf `[main]` 加 `print_estimate_method: slicer`**（轉達工程端進出貨 image；客戶端同）。
- 🆕 **規則變更（新增）**：
  7. **高流量=按噴頭一級**（見上 6；★節兩級規格作廢）
  8. **flush 預設歸零**：倍數 0/自動計算停用/警告移除——沖刷量由 filament_minimal_purge_on_wipe_tower 控制
  9. **手維護線材不設 compatible_printers**（新機型永不漏）；FF 高流量子 preset 例外（口徑配對）
  10. **閒置沖刷預設=每層**（fdm_process_ping_common `wipe_tower_max_idle_layers=1`）；間隔規範值待與參數端定
- 📋 **轉達參數端**（新清單）：①6/11 交付已全吃進（速度/SupPLA220/SupABS/PETG-235/FF600 0.4）✓ ②**高流量規格收斂**：兩級→按噴頭一級（FD450+ 唯一高流量、FD300 系不出高流量），請更新★節規格表 ③SupPLA 物性 config 兩欄與 PLA 同值（密度1.24/玻轉60）——是否刻意？ ④閒置沖刷間隔規範值待裁定（小口徑每層代價大） ⑤Q 值出來後「哪口徑哪級調多少」→軟體端改 HF_SPEED 一格重產。**轉達工程端**：KlipperScreen 出貨 image 加 `print_estimate_method: slicer`。
- 📌 **下一棒待辦**：① FF600 0.4 首件實機驗證（參數端標未實測）② 閒置沖刷間隔規範值 ③ FD 雙料/FF 四色偶發閃退繼續觀察 ④ Mac dmg 交同事實測（首發、未簽名）⑤ E 版上架時 FAMS 加回 ⑥ `D:\PING-Slicer-portable-old-b8/-old-b10` 可清。

---

**🏁🏁 背景（2026-06-10 深夜收工 — 26 commit 全 push；B8 build 進行中）〔已全數完成，見上〕**

- 🔴 **下一棒最優先：B8 build（run `27314114488`）收尾**。B7 因 `PhysicalPrinterDialog.cpp set_value(0)` C2668 失敗、已修（`3262e208`）重發為 B8。B8 完成後依序：
  1. `gh run view 27314114488` 確認 build_windows success（坑#10：Unit Tests/Flatpak 紅 X 不算）
  2. `gh run download 27314114488 -n PING_Slicer_Windows_V3.5.0_portable -D <暫存>` → app 關閉 → 換 `D:\PING-Slicer-portable`（舊版先 mv 備份）→ **repo `resources/profiles/PING` 重新 mirror 上去**（artifact resources=commit 當下，本地 v31 較新需確認一致）
  3. **總驗收**：①重切+上傳→Fluidd 監控頁 metadata 齊全、切片≠Unknown（gcode 頁首已改 `OrcaSlicer 2.3.2 (PING Slicer…)` 開頭）②splash **邊角透出桌面**（v2 wxImage 全程合成；若仍黑＝再戰）③實體列印設備預設名=機型 ④主機類型只剩 Octo/Klipper、代理只剩 Moonraker ⑤對話框 logo 變小 ⑥檔名 `易拆_名_ABS_6g_1h10m` 格式
  4. **下載 Mac**：artifact `PING_Slicer_Mac_universal_*`（.app/dmg/磁碟區已 PING 化、bundle id=com.ping3dp）→ 交使用者（Mac 未簽名：第一次右鍵→打開）
  5. **發 Release v3.5.3**：Windows installer + Mac dmg + 繁中 notes（v3.5.2 已過時：缺下午全部）
- ✅ **本日完成（26 commit，cb0c792b..3262e208）**：B4 完整 F 系列 136-config 重嵌（18 機型/52 機台/97 製程）→ E 版下架＋排序＋FD300 Pro 照片＋床板縮放 → wizard 連動真因根治（wxString locale）＋槽數同步 ＋檔名格式（模式/重量/時間佔位符）＋監控 metadata 頁首 ×2 修 → 雙料製程恢復 V3.0 組合維度＋組合別參數（SUP z=0/無SUP 1層/ABS raft2+首層線寬150%/ABS+SUP 黃金支撐配方）→ 接縫定稿＋清理量二修＋換層回抽關 → B7 四項 native（splash v2/設備名/清單瘦身/logo）→ Mac 出貨 PING 化 → Stealth 頁移除＋縮圖×18＋info/question 去魚 → 升級手冊 HTML。
- 🆕 **規則變更（推翻舊鐵則，勿沿用！）**：
  1. **§8 Scarf 斜拼接縫規範廢除**（external/10%/8 來自網路參考、實測不佳）→ **斜拼=無、接縫位置=對齊**（最佳ABS定稿）
  2. **清理量 30/60 作廢** → **主體=15、SupPLA=30**（SupABS=15；FF 高流量維持 120 換色用）；倍數=0 停用矩陣
  3. **換層回抽=關**（全機型機台層，花瓶縫線）
  4. **製程維度：口徑 → 口徑×材料組合**（雙料每口徑 4 支：PLA+SUP/PLA+PLA/ABS+SUP/ABS+ABS，恢復 V3.0）
  5. **檔名規格**：`{模式}_{名}_{線材}_{重量}_{時間}`；模式=單料/易拆/雙色/Mix/四色（組合直判）；重量 395g/≥1kg→2.3kg；時間 15m/7h15m/1d8h（佔位符 `total_weight_str`/`print_time_hm`，Print.cpp）
  6. **gcode 頁首必須以 OrcaSlicer 開頭**（`OrcaSlicer 2.3.2 (PING Slicer …)`——Moonraker regex 識別，升級 base 時更新版號）
- ⚠️ **刻意狀態（別「修」掉）**：gen_ping_profiles=DEPRECATED 鎖（PING_FORCE_GEN=1 才能跑）；E 版 config 留在參數端交付夾（上架=FAMS 加回）；FF 清理量 120 是故意；`D:\PING-Slicer-portable-old-b5`=B5 備份可刪；v3.5.2 Release 過時勿再發給人。
- 📋 **轉達參數端**（清單累計）：①加速度已套✓ ②scarf 作廢（維持源檔 none） ③單料頭/同進速度殘值仍未套（embed override 撐著） ④清理量→主體15/SupPLA30 ⑤組合別製程差異（SUP z0/無SUP 1層/ABS raft2+首層150%/黃金支撐）進源檔 ⑥換層回抽=0 ⑦接縫位置=aligned。源檔套完→拿掉 embed override。

---

**🏁 背景（2026-06-10 下午 — v3.5.2 發布時點；以下內容部分已被上方推翻）**
- ✅ **Release v3.5.2 已發**：https://github.com/ericlee-lang/PING-Slicer/releases/tag/v3.5.2 （build run `27251862431`・commit `8e24ea73`；Windows/macOS 編譯成功，Linux/Flatpak 失敗=Docker Hub 網路 flake 無關）。**新 portable 已部署 `D:\PING-Slicer-portable`**（舊版備份 `D:\PING-Slicer-portable-old-0606build`）。
- 🎯 **wizard 連動「真因」根治（兩 session 懸案結案）**：`WebGuideDialog.cpp::save_userguide_models` 用 **wxString 隱式轉碼（系統 locale）比對機型名 → 含中文(UTF-8)名在 CP950 下轉換失敗成空字串 → 任兩中文機型名相等 → 跨家族互相連動**。先前「FD300 前綴比對」結論作廢（使用者發現「勾任一單料頭/同進→全部跨家族連動、純英數名不受影響」的決定性規律；1in/2mix 改名實驗驗證理論後修正）。修法：`std::string` 位元組比對＋`nozzle_selected` 改用 JS 送來的實際勾選口徑（順帶根治「勾一口徑→全口徑啟用」）。`8df074a8`。
- ✅ **B5 實機驗證全過（2026-06-10）**：繁中✓、精靈勾選各自獨立＋口徑精確✓、切機線材槽數自動 1/2/4（`03610af9` Tab.cpp+GUI_App.cpp 完全同步）✓、FF/FD 大機床板滿版（`8e24ea73` 床 STL 依直徑 450/600/800 縮放）✓。
- ⬜ **splash 仍黑底（使用者選「先收工」，列後續）**：素材 PNG 是去背的（RGBA、27%透明已驗），黑底=native 合成鏈 alpha 丟失（wxGraphicsContext/wxBitmap MSW 轉換）。下次修法方向：跳過 wxGraphicsContext，直接從 PNG 組 premultiplied BGRA buffer 餵 UpdateLayeredWindow；動態文字（版本/載入中）用「已知底色區塊」貼入避開 alpha。雙螢幕觀察（副螢幕透出背景）= alpha 半生效的佐證。
- 🔍 **FD 雙料/FF 四色切片偶發閃退**：無法穩定重現、**未定根因**（「Invalid T command (T1)」僅為候選）。已揭露於 release notes。每次閃退記操作步驟→查 `%APPDATA%\PINGSlicer\log` 對時間點，累積規律再修。
- 📋 **下一棒優先**：① splash 真透明（上方修法）；② 閃退觀察；③ 參數端修正清單②③（Scarf/單料頭速度——源檔仍未套，embed override 暫補著，套了之後可拿掉 override）；④ FF 換色洗料量（實機 120 vs 30/60 規則）待裁定；⑤ macOS bundle 名/dmg 等剩餘 native 待辦。

---

**🟢🟢 背景（2026-06-10 第二波 — B4 完整 F 系列 136-config 重嵌完成：25 機型/73 機台/73 製程，PING.json v19，待使用者測）**
- ✅ **embed_params.py 全面重寫（v2）**：吃參數端正式交付 `G:\...\PING Slicer V3.5\F系列參數\`（11 機型夾、136 config）。結構：7 個 FD 雙料家族（FD300/E/Pro/E Pro/450/600/800 Pro）×3 模式（雙料=家族名/單料頭/同進）×3 口徑 ＋ FP300/FP300 E（單料 0.2/0.4/0.6）＋ FF600/FF800（四進一出四色 0.6/1.0，preset 名不帶 Pro）。雙料 4 組合共用機台/製程（取 PLA+SUP 母檔），靠線材選擇。**printer_model 去「PING 」前綴**（延續既有命名）。
- ✅ **FF 高流量線材**：4 個口徑別子 preset `PING PLA/SupPLA - 高流量 @FF 0.6/1.0`（alias 顯示母名；FF600/FF800 共用已驗證同值；0.6/1.0 流量/溫度/PA 不同故分開；清洗量維持實機 120——FF 換色洗料量待裁定，FD 的 30/60 不適用）。
- ✅ **參數端已套修正清單①④**：源檔加速度（300=3000/450+=1500/travel=3000，**FF 也套了 1500**）＋倍數 0。**②Scarf ③單料頭速度源檔未套** → embed override 補（FD/FP：scarf external/10%/8＋單料頭模式 250/60/40；FF 不 override 維持實機）。**注意 2.3.2 無 `has_scarf_joint_seam` key，scarf 以 `seam_slope_type=external` 啟用**；機台/製程不再嵌專案層 key（修掉啟動 log incorrect keys 噪音）。
- ✅ **wizard 分組改「家族」**：guide/{21,24} `strSeries=ModelName.replace(/\s*(單料頭|同進)$/,'')` → 11 家族各一列（FD300 一列 3 卡、FD300 E 一列 3 卡…）。**16 張新封面**沿用家族照（cover 以機型名解析，坑#11）。
- ✅ **gen_ping_profiles.py 加防呆**：DEPRECATED，重跑會覆蓋正式 preset，需 `set PING_FORCE_GEN=1`。
- ✅ **參照完整性全驗證通過**＋已同步 %APPDATA%/portable（**PING.json v19**）。⚠ 已知：FD 雙料/FF 四色切片可能觸發「Invalid T command」閃退（native，B5 修——SEMM=1 下 T 指令驗證用擠出機數而非線材數）；精靈 單料頭↔同進 連動＋勾一口徑全口徑啟用（native，已接受）。
- 📋 機型命名空間注意：FD300 家族 12 個 model 共用「FD300」前綴，精靈連動 bug 可能擴大到 E/Pro 變體間（同類無害瑕疵）。

---

**（背景）2026-06-10 第一波 — FD300 材料擴充 + FP300 衍生（已被上方 B4 取代部分內容）**
- ✅ **v3.5.1 已發布並安裝驗證**（繁中 OK）。安裝版 `C:\Program Files\PING Slicer V3.5\`；所有 PING app 共用 `%APPDATA%\PINGSlicer\system`。**測試一律用 portable `D:\PING-Slicer-portable`**（Program Files 不可寫，需管理員）。
- ✅ **End G-code 改正常收尾已 commit（`6b2d126a`）**：27 機台＋產生器，移除退料 `G1 E-500`（退料交韌體；機器端已有退料功能）。與參數端最新交付一致（§五 基本收尾）。
- 🔚 **conflation 結論＝接受為已知 native bug（不修）**：去空格實驗證明根因是 native「FD300 前綴比對」非空格 → resource 無解。**已 revert 去空格**，FD300 維持三機型（`FD300`／`FD300 同進`／`FD300 單料頭`，**有空格名**）。深查 native（`PresetComboBoxes.cpp:1211` 去重、`WebGuideDialog.cpp:440` 噴嘴存全清單、`Preset.cpp:738`、`PresetBundle.cpp:2927`）→ **主畫面「列印設備」下拉本來就依 printer_model 去重，三模式已能各自選＋各自切噴嘴**（Option A，不需改 native；合併成單一 model 會弄壞 `get_similar_printer_preset` 換噴嘴）。連動（單料頭↔同進）＋噴嘴全選（勾一口徑→三口徑，根因 L440）只影響精靈「啟用清單」、**不影響切片**，使用者**決定接受**。
- ✅ **FD300 材料擴充（吃參數端 2026-06-09 新 18-config 交付）**：新建 `PING ABS - 250`（type ABS/250/床100；對交付說明 §三，16 值已驗）；雙料 `default_filament_profile`→`[PING PLA - 220, PING SupPLA]`（SupPLA 既有、已是 PETG/210/`GPINGSPLA`、免動）→ FD300 雙料可選 **PLA+SUP/PLA+PLA/ABS+SUP/ABS+ABS**（靠線材槽）；**單料頭/同進製程速度對齊雙料母檔**（travel400→250、填充300→60、support100→40，×3口徑×2模式）；**移除過時 `PING SUP - 220`**（embed_params §3a/DEF_FIL 已同步止血）。
- ✅ **FP300 衍生（暫定）**：從 FD300 單料頭衍生（0.4/0.6 直接、**0.2 套口徑連動** 層高0.1/首層0.12/線寬0.2/預擠E16）；`printable_height=300`（使用者確認，非骨架的 270）；**高速值未套**（用單料頭正常速，使用者同意），待參數端 FP300 正式定稿再正規嵌。沿用骨架檔名/setting_id、免動 PING.json 結構。
- 📦 **已 mirror 同步** `%APPDATA%\system` + portable，**PING.json v14**、參照完整性通過。⚠ **尚未 commit**（工作樹 ~21 檔：ABS-250 新增、SUP-220 刪、FD300/FP300/process 改、embed_params、本檔）。
- ⚠️ **產生器 `embed_params.py` 已對不上新 18-config 交付**（已止血兩行不再洗回 SUP-220，但仍漏 ABS、誤判「同進」檔名為單噴頭）→ **重寫前勿重跑**（任務 B4）。**參數端來源**：`G:\我的雲端硬碟\2026claude\20260603 切片參數\PING Slicer V3.5\orca_fd300_定稿\`（18 config＋交付說明）＋ zip `FD300_Orca參數_交付軟體端_20260609.zip`。

---

**現況（2026-06-08・本 session 大量進展；resources 多已 portable 驗證，原生待 build）**
- ✅ **已發 Release v3.5.1**（2026-06-08，繁中＋全部修正，給同事）：https://github.com/ericlee-lang/PING-Slicer/releases/tag/v3.5.1 （build run `27128055141`・commit `e496f8cf`）。**修好 v3.5.0「只剩英文」**（坑#16；.mo 已打包並實機驗證繁中 OK）。下方「待 build 的 6 commit」+ 停用自動更新器**皆已 build 進此版**。⚠ 內含**已知 bug**：wizard 單料頭↔同進 連動（§4 待辦1，**已確認是真 bug**、已揭露於 release notes、不影響切片）。
- （舊）~~已發 Release v3.5.0~~ 是英文版（.mo 沒打包，坑 #16）→ 已被 v3.5.1 取代。
- 選機精靈：已做「**同系列分列**」（FP300 一列、FD300 三模式一列）——**使用者已驗證 ✓**。
- 機型命名：兩進一出 → **FD300 同進**、單噴頭 → **FD300 單料頭**（全中文；**棄用 Mix50**：四料是 25% 混料非 50%，數字不通用，改全中文。**勿再用 Mix50**）。三台共用 FD300 照片。
- 切片命名規範（§8）、Scarf 接縫、去金魚 logo、列印加速度規範、SupPLA 清洗量、**線材預設色**——皆已套用（多在下面 commit）。

**版本 / commit 狀態（分支 `ping/v3.5`，全部已 push）**
- **已發 Release v3.5.0**（run 27108286233・commit `4eb0162b`）：https://github.com/ericlee-lang/PING-Slicer/releases/tag/v3.5.0
  - 含：同進改名+命名規範+加速度+SupPLA+去金魚logo+Scarf（`b762903f`，PING.json v08）、GLCanvas3D停PLA/PETG警告（`4eb0162b`）、CSS選機頁+inherits+線材槽patch（`0a626ad5`）。
  - ⚠ **此 Release 沒有以下**（commit 都在 `4eb0162b` 之後，未進任何 Release）：
- **待下次 build 的 commit（已 push、未 build）**：
  - `134bab83` splash per-pixel 去背（**原生・未經 build 驗證**，可能需微調；坑 #15）
  - `1c85381c` i18n：收進 42 個 .mo → 安裝版有繁中+多國（坑 #16）
  - `f091d952` 捷徑名加 V3.5（桌面+開始選單，CMakeLists CPack/NSIS）
  - `f50ada0f` wizard 選機頁同系列分列（web・**已驗證**）
  - `fc9f8d6a` wizard 全選/清空改 native querySelectorAll（web・**已驗證快**）
  - `05d852c3` 線材預設色 一般橘 `#EA4E16` / 支撐灰 `#808080`（PING.json **v09**；生成器同步，但 embed_params 的 -220 變體色待補）
- **參數規範（使用者定）**：加速度 300機普/內/外=3000、450+=1500、travel兩組3000（27製程，生成器同步）；SupPLA 清洗量 60；線材色 橘/灰。

⚠ **重要觀念（避免混淆）**：portable（`D:\PING-Slicer-portable`）的 **binary 是 6/6 舊 build**，我只同步 resources 上去 → portable 能測**資源面**（wizard/profiles/色/.mo），**原生面**（splash/捷徑/語言載入）要 build 才有。安裝版 v3.5.0 是 6/8 新編（原生有，但缺上面那批 resources/native commit）。

**下一棒最優先（2026-06-09 第二 session 後）**：① **等使用者回報 conflation 測試結果**（resource 變通做法已套用＋同步，測法見 §0 🎯）——✅ 成功＝`git add -A && git commit`（改名去空格＋Mix300移除＋JS正則＋產生器同步，產生器已一致可放心 commit）、併入下次 build；❌ 失敗＝`git checkout -- . && git clean -fd resources/profiles/PING` revert 改名，改走 native log+build（§4 待辦1）。② 湊齊其餘 native 待辦（splash／macOS bundle／自動更新器 title logo）一次 build 重發 Release。**（原 ①「測試」已套用待測、②「End G-code commit＋清 Mix300」已完成＝`6b2d126a`＋已清。2026-06-08 的「下一棒」已過時，保留作背景。）**

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

15. **【i18n 安裝版只剩英文】產 `.mo` 的 `gettext_po_to_mo` 是獨立 custom target、不在預設 build，CI 從不執行 → 安裝版 `resources/i18n` 全空 → 語言清單只剩 English。** CMakeLists L761 命名已是 `${SLIC3R_APP_KEY}.mo`(=PINGSlicer.mo) 是對的，但根本沒被產生。`.po` 在 `localization/i18n/*/`，repo 的 `resources/i18n` 原本 0 個 .mo（被 `.gitignore` `*.mo` 擋）。**解法（坑#16 已用）**：把可用 portable 的 21 種語言 .mo（OrcaSlicer.mo + PINGSlicer.mo 各 21）收進 repo `resources/i18n/`，`.gitignore` 加例外 `!resources/i18n/**/*.mo`，build 直接打包。app key=PINGSlicer → app 找 `PINGSlicer.mo`（坑 #5）。**需 build 才進安裝版**。

16-2.【檔名/gcode 模板鐵則】**PlaceholderParser 模板的「rule 邊界」（開頭、`}` 之後）不可出現裸非 ASCII 字元**——pre-skip skipper 遇 char<0 直接 throw「Non-ASCII7 characters...」，匯出即炸。text 區「中段」中文沒事（lexeme）、**字串字面值內中文合法**（`raw[lexeme['"'...utf8char...]]`，PlaceholderParser.cpp L2245）→ 中文前綴一律寫成 `{"雙色_"}` 形式。`verify_profiles.py` 已含此防回歸檢查。

17. **app 開著時「不可」同步 `%APPDATA%\PINGSlicer\system`**——robocopy /MIR 換檔瞬間與 app 記憶體狀態不一致，會切出「鬼參數」結果（實案：塔完全沒洗料、整支純色；重開 app 即恢復）。**同步 profiles 跟換 portable 一樣：先關 app**。

18. **機器螢幕「時間一直漲」不是切片器問題**：KlipperScreen 預設（auto）混「檔案進度外推」（duration/file_progress），列印前期因首層慢+換料塔，外推灌水到 7-8h 且持續上升、過半才收斂。切片器 estimated_time/M73 都正常（實測誤差 <1%）。修法=機器端 `KlipperScreen.conf` `[main]` 加 `print_estimate_method: slicer`。診斷工具：`tools/ping/monitor_print_time.py <host>`。

19. **flush（沖刷矩陣/倍數）是「專案層」參數，preset 帶不動**（SKIP 清單實證：flush_volumes_matrix/flush_multiplier 進 machine preset 會被剝除）。要改預設只能動 native：AppConfig（auto_calculate_flush）+ PrintConfig（flush_multiplier default）——B12 已歸零。同理可推：任何 SKIP 清單裡的 key 都別想用 preset 交付。

20. **【衍生機型床渲染】床有三層、各自獨立**：①`printable_area`（多邊形）→白網格邊界 ②`bed_texture`（PNG，machine_model 層）→床面貼圖、**鋪滿 printable_area 的 bounding box**（`3DBed.cpp` tex_coords=(床點−bbox_min)/bbox_size）③`bed_model`（STL）→3D 床盤、可比 printable_area 大。**P200+ 案例**：白網格250(printable_area)＋深灰盤300(借 FD300 STL)不一致→使用者要切齊。**畫床標示圈**（如門關200橘圈）＝改 bed_texture：圓床貼圖鋪滿 bbox，直徑D的圈在貼圖中心半徑 (D/bbox)×全寬（200/250=0.8）。**縮床盤**＝binary STL 縮放（80byte header＋uint32 count＋每三角形50byte；XY 各頂點(x−cx)×scale 置中縮放、**Z 厚度不縮**）。`P200+_buildplate_texture.png`/`P200+_buildplate_model.stl` 即此法產出。BED_OVERRIDE 統一掛 bed_texture/nozzles/area_diameter/prime_y_shift。

21. **【Mac 簽名 CI 已內建、只缺憑證】** `.github/workflows/build_orca.yml` L165–217 有完整 codesign＋notarytool＋staple 流程，但 `if: github.repository=='OrcaSlicer/OrcaSlicer' && (main||release/)` **鎖死只在原版跑** → PING fork 走 L219「不簽名」路徑。啟用＝①Eric 辦 Apple Developer 公司帳號（需 D-U-N-S，免費1-2週）②設 7 個 Secrets（BUILD_CERTIFICATE_BASE64/P12_PASSWORD/KEYCHAIN_PASSWORD/MACOS_CERTIFICATE_ID/APPLE_DEV_ACCOUNT/TEAM_ID/APP_PWD）③改 L166 條件成 PING repo＋ref 放寬。指南：`..\Apple簽名設定指南.html`。未簽名過渡＝教同事「右鍵→打開」一次裝（別雙擊）。

20. **splash per-pixel 去背（layered window）機制 + 風險**：白底來源是 `MakeBitmap()` 用 `*wxWHITE` 填滿 700×450 畫布，再疊**去背的** `splash_logo.png`(透明處透出白)。修法（`134bab83`，**僅 MSW・未經 build 驗證**）：新增 `GUI/SplashLayered.cpp/.hpp`（Win32 `UpdateLayeredWindow` + premultiplied BGRA；`windows.h` 用 `wx/msw/wrapwin.h` **隔離在獨立 TU**，否則 `DrawText` 等巨集會汙染 GUI_App.cpp）；`SplashScreen` 加 `render_layered()`（wxGraphicsContext 在透明圖上重合成 logo+版本字+載入字）+ `SetText`/建構子 MSW 分支；CMakeLists 列入新檔。⚠ **runtime 風險**：wxGraphicsContext→bitmap 的 alpha 是否正確、premultiply 是否雙重、layered 視窗序列——build 後若 splash 不對（黑/全透/邊緣暗）多半是這幾點，需微調。非 MSW 維持原白底（編譯安全）。

---

## 3. ✅ 正確的客製化流程

1. **先判斷：資源檔 還是 原生 code？**（見坑 #3）
   - 對話框文字/logo（About、splash）→ 原生；設定精靈頁 → WEB（`resources/web/guide/`）；機型/製程/線材 profile → 資源；配色 → 兩邊；App 名稱 → `version.inc` + `libslic3r.h`。
2. **資源檔改動**：repo 改 → 同步 `D:\PING-Slicer-portable\resources` + `%APPDATA%\PINGSlicer\system` →（動 profile 就 `PING.json` version +1）→ **同步改產生器**（`embed_params.py`/`gen_ping_profiles.py`）避免重生跑掉 → 重開 portable 測。**不 build。**
3. **原生改動**：改 `src/` → commit → `gh workflow run "Build all" --ref ping/v3.5` → ~50min。
4. **嵌入參數定稿**：`python tools/ping/embed_params.py "<定稿資料夾>"` → 同步。
5. **取 build portable**：`gh run download <run_id> -R ericlee-lang/PING-Slicer -n PING_Slicer_Windows_V3.5.0_portable -D <dir>`；新 binary 要疊最新 `resources/profiles/PING` + `.mo`(複製成 PINGSlicer.mo)。
6. **換 portable（✅ 2026-07-02/03 三次實證的完整流程）**：
   1. **app 完全關閉**（tasklist 查 ping-slicer.exe；開著換會出鬼參數，坑#17）。
   2. `mv` 舊 portable 備份 → `mv` 新 artifact 進去。
   3. **profiles 對策二選一**：(a) repo 資源＝活狀態時（比對過）→ 直接用 artifact 資源；(b) 活狀態較新→ 從備份 `cp` 回 `resources/profiles/PING`＋`PING.json`。
   4. **DL1016 回注**（本機注入、永不進 repo/Release）：G 槽 Dowell 源**已失蹤**，`add_dl1016.py` 跑不了——改從 **`D:\dev\2026claude\20260604 ORCA客製\DL1016_本機注入備援\`**（11 檔＋`PING.json_註冊條目.json`）複製檔案＋把註冊條目 append 進 PING.json 四清單（機型殿後）。
   5. **鏡像到 `%APPDATA%\PINGSlicer\system`**（app 實際讀這裡，portable resources 只是複製源）；資源版號 > %APPDATA% 版號時 app 也會自動重複製——但**自動重複製會洗掉 DL1016**，所以要嘛先回注再鏡像、要嘛保持版號相等自己鏡像。
   6. 驗收腳本心法：Python 比對 portable PING.json 與 %APPDATA% 四清單全等＋DL1016 檔數＋exe mtime＋`PINGSlicer.mo` 存在。
   ↳ 發對外 Release 而主工作區有別條 session 未推 commit 時：**用 `git worktree add <tmp> <sha> -b release/x.y.z` 隔離開分支改版號**，不動主工作區（2026-07-03 v3.5.4 實證）。

---

## 4. 進度

### ✅ 已完成
- 品牌：app 名稱、splash、About 框、配色青綠→橘、預設繁中、移除 Bambu 雲端。
- 選機精靈頁修復(CSS)、vendor 載入修復(製程 inherits)、FD300 自動 2 卷(原生 patch)。
- 去金魚 logo、機型改名(同進/單料頭)+切片命名規範+Scarf 接縫(§8)。
- **列印加速度規範**(300=3000 / 450+=1500 / travel 3000)、**SupPLA 清洗量 60**、**線材預設色**(一般橘/支撐灰)。
- **i18n .mo 收進 repo**(修安裝版只剩英文；坑 #16)、**捷徑加 V3.5**、**splash per-pixel 去背**(原生・未經 build 驗證；坑 #15)。
- **wizard 選機頁同系列分列**(FP300一列/FD300三模式一列) + 全選/清空 native 化(皆已驗證)。
- **清掉測試殘留 user presets**(`FD300 同進 0.25` / `0.125mm @FD300 (0.25) - 複製` / `PING PLA - 210`，本 session 已刪)。
- FD300 定稿參數：3 機台變體 × 3 口徑。

### ⬜ 待辦（給下一棒・依優先序）
1. **【確認真 bug・待修】wizard「FD300 單料頭 ↔ 同進」conflation**（2026-06-08 實機 JS 探針 + 存檔重現 + conf 比對，**已確認**；先前「疑似殘留」的判斷是**錯的**）：
   - **乾淨重現**：選機頁「全部清空」→ 只勾單料頭（在 `CheckBoxOnclick` 插 `alert` 探針確認 DOM 只有單料頭=true、同進全 false）→ 確定 → 重開 → **同進也被勾**；反向（只勾同進 → 單料頭復活）亦然。`PINGSlicer.conf` 的 `models` 存檔即含兩個。
   - **已排除（別再查）**：① **JS 點擊乾淨**——探針 2 次證實點單料頭時同進 DOM 不變、反之亦然；② **非「作用中印表機鎖定」**——把非作用中的單料頭整個取消，它仍復活；③ **非同系列連動**——同系列的**基本款 FD300 可正常被移除**，只有單料頭↔同進鎖死。
   - **連動在 native「確定 → SaveProfile/apply_config 套用」這一步**（JS 送出 `data` 只有同進，conf 卻變兩個）。但讀碼：`SaveProfile`（L610，`set_vendors(empty)` 後只對 `nozzle_selected` 非空的 model 寫 `set_variant`）+ `apply_config`（L880 `app_config->set_vendors(m_appconfig_new)` 整個取代）+ `save_userguide_models`（L425 精確 `compare`）**全部讀起來乾淨**。→ 真因是**隱蔽交互**，疑似 wizard 結束後「重載 active 印表機 preset」把單料頭一起拉回，且似與「同進為作用中」有關。
   - **下一步（兩條，給下一棒）**：① **免 build**：把 active 印表機換成 FP300/基本款，再測單料頭——確認連動是否綁「同進是作用中」，能縮小修法範圍；② **加 native log + build**：`SaveProfile` 的 set_variant 迴圈 L658/665 **已有 `BOOST_LOG_TRIVIAL(info)`**，但目前 log level 過濾掉 info（`debug_*.log` 只剩 error/warning）→ 需把 log level 開到 info（或改 BOOST 等級）再 build，即可抓到「誰把單料頭寫回 app_config」。同時查 wizard 後 `GUI_App::load_current_presets` / `PresetBundle` 對 active 印表機的 re-enable 邏輯。
   - **影響**：wizard「啟用清單」連動，**不影響切片**——兩 preset 各自獨立、主畫面選任一個都能正確切片。已於 **v3.5.1 release notes 揭露為已知問題**。
   - **診斷探針位置**：暫存測試版 `D:\PING-Slicer-v35x-new\resources\web\guide\{21,24}\*.js` 的 `CheckBoxOnclick` 加了 `alert` dump（**repo 乾淨、未動**）；要再測直接看那支或重加。
2. **湊齊後一次 build + 重發 Release**：上面「待 build」6 個 commit（splash/語言/捷徑/wizard×2/色）一起 build → 重發 v3.5.x（給同事繁中＋全部修正）。⚠ splash 未測，build 後先確認 splash 顯示 OK，可能需微調再 build。`gh workflow run "Build all" --ref ping/v3.5`。
3. **剩餘 native 待辦**（與上 build 同批做）：macOS bundle 名/dmg、自動更新器停用(`check_new_version_sf`)、工具列 title logo、splash「V3.5」字位(去背後可能要重對)。
4. **wizard 卡片改模式示意圖**：使用者要把機器照換成「雙料/單料/同進」模式示意圖（目前先保留 FD300 照）。卡片 cover = `resources/profiles/PING/<機型>_cover.png`(坑#11)。
5. **線材頁只留 PING**：wizard `guide/22` 過濾掉 OrcaFilamentLibrary 廠牌。
6. **繼續切片參數**：材料溫度/支撐/速度（材料相關放 filament preset，§8；值是參數人員源檔）。
7. **嵌入其他機型參數**：`匯出_3mf\` 的 FD600/FF600/FF800/FP300（擴 `embed_params.py` 支援 .3mf）。
8. **FP300 口徑對齊**：規格 MD 確認 0.2 vs 0.25、有無 0.8（§5）。
9. **embed_params 補線材色**：-220 變體色已設於 profile，但 `embed_params.py` 未加色邏輯（regen 會洗掉；`gen_ping_profiles.py` 已加）。

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
（2026-06-11・ping/v3.5，全部已 push；Release v3.5.3 = 438ee102）
438ee102 高流量收斂按噴頭一級 + flush 預設歸零（AppConfig/PrintConfig/GLCanvas3D）
ba24317d 手維護線材移除機台白名單（修 FD300 Pro 線材消失）
3381b887 ★品質兩級製程 + PETG-235 + FF600 0.4（後被 438ee102 收斂）
9b84c293 線材選擇下拉顯示線材名稱（alias）取代 filament type
efb7eb22 吃 6/11 參數端交付——速度兩線定稿 + SupPLA 220 + SupABS 對值
0c648cbb 傳送對話框 Cancel 翻譯 L→_L
38ee8805 對話框品牌 logo 移至標題列左上角（app icon）
49fd9ee5 檔名模板中文前綴包進字串字面值——修 Non-ASCII7 匯出炸錯
74629eb9 換料塔閒置線材定期沖刷 wipe_tower_max_idle_layers
3c3df21c docs(handoff): 2026-06-10 深夜收工

（2026-06-09・ping/v3.5，已 push）
6b2d126a End G-code 改正常收尾（移除退料 G1 E-500；27 機台 preset＋gen_ping_profiles.py）
cb0c792b docs: 確認 單料頭↔同進 conflation 為真 bug + 發布 v3.5.1 + 升級 playbook
e496f8cf 停用線上自動更新器 check_new_version_sf
（⏳ 工作樹未 commit・待 conflation 測試：改名去空格 FD300同進/單料頭＋移除Mix300＋JS正則分組＋embed_params 同步，PING.json v12）

（本 session 2026-06-08・ping/v3.5，皆已 push；前 6 個「待下次 build」）
05d852c3 線材預設色 橘#EA4E16/支撐灰#808080 (PING.json v09)
fc9f8d6a wizard 全選/清空 改 native querySelectorAll
f50ada0f wizard 選機頁同系列分列 (已驗證)
f091d952 捷徑名加 V3.5 (CMakeLists CPack/NSIS)
1c85381c i18n 收進 42 個 .mo → 安裝版繁中 (坑#16)
134bab83 splash per-pixel 去背 (原生・未測；坑#15)
4eb0162b GLCanvas3D 停 PLA/PETG 警告        ← 已進 Release v3.5.0 (build 27108286233)
b762903f 同進改名+命名規範+加速度+SupPLA+去金魚logo+Scarf  ← 已進 v3.5.0 (PING.json v08)
0a626ad5 CSS選機頁+製程inherits+原生線材槽patch          ← 已進 v3.5.0 (更早 build 27049518615)
（更早）446b7099 About框PING化 ｜ e357e7c3 FD300三模式+embed_params ｜ 69b7c750 web精靈去PING前綴+跳Bambu
```

---

## 7. 使用者的硬性偏好

- **一律繁體中文**回覆。
- **PING 相關成品一律套 PING CIS**（動手前載 `ping-cis` skill；Raised Orange `#EA4E16` 僅 accent ~5%、白底為主、禁大面積橘、Logo 用 assets 原檔不可重畫）。**給人閱讀文件優先單檔 HTML**（離線、不引 CDN/網路字型）；機器/AI 用途檔（README、設定檔）才用 Markdown。
- **切片參數由「另一個人」負責**：軟體端只做功能 + 把標準參數嵌進去；參數值是他的源檔（值有錯提醒他改源檔）。
- **效率**：能免 build 就免 build；native 改動批次化、一次 build。
- AGPL 合規：保留 LICENSE、About 標註 based on OrcaSlicer + 源碼連結、不可寫 "All Rights Reserved"、不打包 Bambu 閉源 DLL。

---

## 8. 切片命名規範
> 🆕 **2026-06-10 變更**：①本節 Scarf 接縫規範**已廢除**（實測不佳）→ 斜拼=無、位置=對齊；②製程命名升級為「口徑×組合」：雙料=`0.2mm PLA+SUP @FD300 (0.4)`（下拉顯示 `0.2mm PLA+SUP`）。以下原文供歷史參照。

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
