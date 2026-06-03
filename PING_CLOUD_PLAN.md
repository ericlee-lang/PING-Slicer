# PING Slicer — 雲端整合規劃書（Bambu 架構解析 + PING 圖庫／生產列印件方案）

> 本文件為**參考規劃**，供 PING 決定自家雲端方向。內容基於 OrcaSlicer **v2.3.2** 實際源碼分析。
> 本階段（V3.5）的範圍是**移除 Bambu 雲端、介面乾淨化**；PING 自家雲端列為下一階段。

---

## 0. 一句話結論

- **Bambu 的聯網本體是「閉源二進位外掛」**（`BambuNetwork` DLL/dylib/so），不在原始碼裡，是 App 執行期才下載載入的；原始碼只有一層薄包裝。
- OrcaSlicer v2.3.2 已把網路層重構成**「註冊式工廠＋介面」**，原始碼內建 Orca / **Moonraker** / Qidi / Snapmaker 等非 Bambu 代理。
- **PING 機台跑 Klipper＝內建 Moonraker**，所以「連到生產列印件」最省力的官方路徑就是用 OrcaSlicer 內建的 **Moonraker 代理**，幾乎零開發。
- 「PING 圖庫」最省力＝用內建 WebView 指向 PING 自家網頁，PING 完全掌控網頁端。

---

## 1. Bambu 雲端是怎麼實作的？（你問的重點）

### 1.1 分層架構

```
GUI（登入鈕、Device 分頁、首頁 WebView、送印）
      │  呼叫
      ▼
NetworkAgent（開源・統一介面/委派）         src/slic3r/Utils/NetworkAgent.{hpp,cpp}
  ├─ ICloudServiceAgent（帳號/雲服務介面）   src/slic3r/Utils/ICloudServiceAgent.hpp
  │    ├─ OrcaCloudServiceAgent（開源・OAuth2 PKCE，連 Orca 雲）
  │    └─ BBLCloudServiceAgent（開源薄包裝 → 轉呼叫 Bambu DLL）
  └─ IPrinterAgent（印表機控制介面）          src/slic3r/Utils/IPrinterAgent.hpp
       ├─ BBLPrinterAgent（開源薄包裝 → Bambu DLL）
       ├─ MoonrakerPrinterAgent（開源・Klipper/Moonraker）★PING 可直接用
       ├─ OrcaPrinterAgent / QidiPrinterAgent / SnapmakerPrinterAgent
      │  以函式指標呼叫
      ▼
BBLNetworkPlugin（外掛載入器）              src/slic3r/Utils/BBLNetworkPlugin.{hpp,cpp}
  └─ 載入 BambuNetwork_v*.dll / .dylib / .so   ← 【閉源・不在 repo・執行期下載】
       介面定義：src/slic3r/Utils/bambu_networking.hpp（只有宣告，無實作）
      │  網路
      ▼
Bambu 伺服器：帳號 API、MQTT broker（裝置狀態/控制）、FTP（傳檔）、MakerWorld 模型庫
```

### 1.2 幾個關鍵事實

1. **外掛是閉源的、且不隨原始碼散布**：`bambu_networking.hpp` 只定義 C 介面（`PrintParams`、`on_message_fn` 回呼、錯誤碼、MQTT 訊息列舉）。真正的 MQTT/FTP/帳號實作在 `BambuNetwork` 動態庫裡，App 第一次要用網路功能時，從 Bambu 伺服器**下載 .dll.gz 到使用者快取**（`~/.cache/.../plugins/`），再用 `BBLNetworkPlugin` 以函式指標綁定（`get_start_print()`、`get_connect_printer()`…）。
   - → **對 PING 的意義**：我們移除雲端＝不觸發下載、不載入此 DLL，**完全不需要、也不會散布 Bambu 的任何二進位**（合規乾淨）。
2. **登入**：點帳號鈕 → `WebUserLoginDialog`（wxWebView 開登入網頁）拿 token → 存 OS 安全儲存（Windows 認證管理員 / macOS Keychain）。`UserManager` 維護登入狀態。
3. **裝置/送印**：`DeviceManager`/`MachineObject` 管理機台；送印 `SendJob` 分兩路：
   - **LAN**：直接 FTP 上傳 G-code 到 `機台IP:6969` + MQTT(`:8883`) 控制（需 access code）。
   - **Cloud**：透過 Bambu 雲端中繼（MQTT broker 在 Bambu 伺服器）。
4. **模型庫（MakerWorld）**：內嵌 `WebViewDialog`/`resources/web` 載入 Bambu 的網頁。

### 1.3 V3.5 移除 Bambu 雲端＝關掉哪些東西（最小清單）
- 不觸發外掛下載：跳過 `UpgradeNetworkJob` / `NetworkPluginDialog`。
- 隱藏帳號登入 UI：`BBLTopbar` 帳號鈕、`WebUserLoginDialog`/`OAuthDialog`/`PrinterCloudAuthDialog`。
- `NetworkAgentFactory` 不預設 BBL 代理。
- 首頁/模型庫 WebView 中性化（移除 MakerWorld/Bambu 連結）。
- **保留** `NetworkAgent`/`IPrinterAgent` 抽象層與 Moonraker 等 LAN 代理（日後 PING 要接才方便）。

---

## 2. PING 圖庫（model gallery）— 你的「連到一個圖庫」

### 方案 A（建議起步・最省力・零後端改 OrcaSlicer）
用 OrcaSlicer 內建的 **WebView 分頁**指向 **PING 自家網頁**（例如 `https://cloud.ping3dp.com/gallery`）。
- 改一行載入網址即可（`MainFrame` 載 WebView 的 URL 讀 config，預設 PING 網址）。
- 圖庫的瀏覽、分類、搜尋、下載 3MF/STL **全在 PING 網頁端做**，PING 100% 掌控，改版不必重編切片軟體。
- 下載模型：網頁可觸發 `orcaslicer://open?file=...` 或直接下載後由切片軟體開啟。

### 方案 B（中期・更整合）
實作 `ICloudServiceAgent` 的 model-mall 介面對接 PING API，讓「匯入模型」直接在切片軟體內列出 PING 圖庫品項。工程較大，方案 A 已能滿足 90% 需求。

**PING 需提供**：圖庫網頁（RWD）、模型下載端點；（選用）登入。

---

## 3. PING 生產列印件（print farm／送印佇列）— 你的「連到生產列印件」

### ★ 關鍵：PING 機台是 Klipper＝內建 Moonraker，OrcaSlicer 已原生支援

### 方案 A（建議起步・幾乎零開發）— 用內建 Moonraker 代理單機直送
- 機型 profile 已設 `host_type=octoprint`（Moonraker 相容）。使用者在「裝置」填機台 IP（Moonraker 預設 `:80/:7125`）。
- 切片後可直接 **上傳 G-code、開始列印、即時監看溫度/進度**——這正是 OrcaSlicer 連 Klipper 印表機的標準用法（`MoonrakerPrinterAgent`）。
- **PING 不必開發任何雲端**就能做到「切片→直送機台列印」。

### 方案 B（中期・多機看板）— WebView 接 PING 生產看板
- 在切片軟體內放一個「生產」WebView 分頁，指向 PING 自建的多機看板網頁（背後可用 Moonraker 的 API 聚合多台機況、排隊、歷史）。
- 適合「工廠多台機台集中管理」情境；軟體端只是一個瀏覽器視窗，PING 後端自由發揮。

### 方案 C（長期・深度整合）— 自家 PINGPrinterAgent / PINGCloudServiceAgent
- 仿原始碼內建的 `MoonrakerPrinterAgent`／`QidiPrinterAgent`／`SnapmakerPrinterAgent`，新增 `PINGPrinterAgent : IPrinterAgent`，把切片工作送進 **PING 自家雲端佇列**並回報狀態；登入可做 `PINGCloudServiceAgent : ICloudServiceAgent`（仿 `OrcaCloudServiceAgent` 的 OAuth2 PKCE）。
- 於 `NetworkAgentFactory::register_all_agents()` 註冊即可被選用，與既有架構無縫接合。
- **PING 需提供**：雲端 API 規格（auth、機台清單、上傳/送印、工作狀態/事件）、網域、TLS 憑證。

### 三方案比較

| 方案 | 開發量 | 需要 PING 後端 | 適用 |
|------|--------|----------------|------|
| A 內建 Moonraker 直送 | 幾乎 0 | 否（機台本身即可） | 單機/小量、最快上線 |
| B WebView 生產看板 | 小（一個分頁＋網頁） | 是（看板網頁，可用 Moonraker 聚合） | 多機集中管理 |
| C PINGPrinterAgent + 雲端 | 中大 | 是（完整雲端 API） | 品牌級雲端、跨網列印、帳號體系 |

---

## 4. 建議路線圖

- **Phase 1（V3.5，現在）**：移除 Bambu 雲端；機型 profile 內建 Moonraker（方案 3-A 直送可用）。
- **Phase 2**：上線 PING 圖庫網頁（2-A）＋ 生產看板網頁（3-B），用 WebView 接入。**此階段 PING 端只需做網頁，不必動切片軟體核心**，最划算。
- **Phase 3（視需求）**：要帳號體系、跨網雲端列印、與 ERP/MES 串接時，再做 `PINGCloudServiceAgent` + `PINGPrinterAgent`（3-C）。

> 換言之：你想要的「圖庫」與「生產列印件」，**Phase 2 用網頁就能達成且最省成本**；要更深的雲端整合再進 Phase 3。OrcaSlicer 的可插拔網路架構已替我們把接縫留好。

---

## 5. 程式接縫對照（給日後實作）

| 想做的事 | 接入點（檔案/類別） |
|----------|---------------------|
| 換首頁/圖庫/看板網址 | `MainFrame` 載入 WebView 的 URL（改讀 PING config） |
| 自家登入 | 新增 `PINGCloudServiceAgent : ICloudServiceAgent`（仿 `OrcaCloudServiceAgent`） |
| 送印到自家佇列 | 新增 `PINGPrinterAgent : IPrinterAgent`（仿 `MoonrakerPrinterAgent`），於 `NetworkAgentFactory` 註冊 |
| 單機直送（現成） | `MoonrakerPrinterAgent` + 機型 profile `host_type=octoprint` |
