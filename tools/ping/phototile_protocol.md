# 照片磚引擎協定（C-1・v1）

> 正本。JS 端實作＝`resources/web/phototile/engine_protocol.js`（單一份，勿在 engine.html 重寫規則）；
> C++ 端＝`PhotoTileEngineHost` 逐條鏡像。改協定＝**同時改本檔＋兩端＋單元測**，並升 `PROTOCOL_VERSION`。
>
> 血統：C-0 尖峰報告 §2.1（引擎契約）／§3.1–3.3（宿主實測與規格草案）／§5.2（行為矩陣）；
> C 案計畫 §3 C-1、§5 十一項裁決（Eric 2026-07-29 全項拍板）。

## 0. 名詞與角色

| 角色 | 是誰 | 職責 |
|---|---|---|
| 宿主 host | `PhotoTileEngineHost`（C++，隱藏視窗、永不 Show） | 生命週期、下指令、驗收 3MF、環境快照比對、進度／取消對接 UI |
| 引擎頁 page | `resources/web/phototile/engine.html`（隱形） | 純運算：生成 3MF、回報進度、可取消 |

**engine-neutral**：`request`／`result` 的欄位契約與傳輸層無關。日後若走 A 案（C++ 原生移植），
同一份 DTO 直接沿用、雙路黃金基準庫（`golden_report.json`）即為現成驗收（C-0 §6 轉 A 保留）。

## 1. 訊息共通規則

- 一律 JSON；每則帶 `v`（＝`PROTOCOL_VERSION`，目前 **1**）。版本不符＝立即誠實失敗，不做相容猜測。
- host→page 用 `cmd`；page→host 用 `type`。凡與作業相關者一律帶 `jobId`。
- **一次一個 job**。生成中收到新的 `generate`＝supersede：先 `cancel` 舊 job，page 回 `superseded`，再跑新的（不排隊；C-0 §5.2 矩陣 #8）。
- **零計時器**：page 側生成路徑不得使用 setTimeout／setInterval／rAF（隱形頁被節流到 ~1s/次）。讓步一律 MessageChannel。

## 2. 生命週期

```
runtime 檢測 → 建 env（獨立 user-data）→ 建 controller（隱藏 HWND＋IsVisible=false）
 → navigate(engine.html) → 等 ready（逾時 15s＝誠實不可用）
 → 服務 job … → ProcessFailed → 重建（上限 3 次，超限＝誠實不可用）
```

- `ready` **可能早於** `NavigationCompleted` 抵達 —— 兩種順序宿主都必須正確處理（C-0 §3.1 實測）。
- runtime 缺失／建立失敗＝**誠實不可用＋指引**，不得 fallback 回工作室頁（裁決 8）。
- 重建後首個結果必須通過同一份 SHA 驗證（重建前後同輸入應同輸出；不一致＝FAIL）。

## 3. 3MF 回傳與「成功」的定義

`result`（中繼資料）→ `begin` → `chunk × N`（96KB／塊）→ `end`。

宿主**唯有四項全過才可視為 success**，任一不符＝丟棄整份並回報協定錯誤（不得半成品上盤）：

1. 分塊**連號**（`index` 必須 0,1,2,… 連續，不接受亂序或重送）
2. **塊數**符合 `begin.chunks`／`end.chunks`
3. **總長度**符合 `begin.size`
4. 組裝後 **SHA-256** 等於 `end.sha256`

## 4. 訊息表

### host → page

| cmd | 欄位 | 說明 |
|---|---|---|
| `ping` | `seq` | 心跳；page 回 `pong`（帶 `busy`） |
| `imageBegin` | `jobId,mime,name,totalChars,chunks` | 影像注入開始（base64，192K 字元／塊＝現行 `WebViewDialog.cpp:333` 值） |
| `imageChunk` | `jobId,index,base64` | 序號必須連續，否則整批作廢 |
| `imageEnd` | `jobId,totalChars,chunks` | 字元數與塊數雙驗；過＝回 `imageAck` |
| `generate` | `jobId,request{...}` | 見 §5；影像取自本 job 的注入緩衝（或 `request.image`） |
| `cancel` | `jobId` | 合作式取消；page 回 `cancelAck{existed}` |

### page → host

| type | 欄位 | 說明 |
|---|---|---|
| `ready` | `engine,protocol,metadataSchema,hasMesh,limitsDefault,ua` | 握手 |
| `pong` | `seq,busy` | |
| `progress` | `jobId,stage,stageLabel,pct,elapsedMs` | 階段權重見 §6；合法上限案 quad K8 ≈20 秒（K 上限 48→8＝Eric 2026-08-02 裁 B，引擎 clamp 2..8）＝進度與取消是必備 |
| `imageAck` | `jobId,chars,chunks,mime` | |
| `result` | `jobId,ok,…` | 成功時含 `byteLength,sha256,chunks,palette,slots,stats,metadata,env,limits,diagnostics`；失敗時含 `error{code,message}` |
| `begin`／`chunk`／`end` | 見 §3 | |
| `superseded` | `jobId,by` | 舊 job 被新輸入取代 |
| `cancelAck` | `jobId,existed` | |
| `error` | `jobId,code,message` | 協定層錯誤（碼見 §7） |

## 5. request／result（engine-neutral DTO）

`request`：`jobId`／`mode`(dual\|quad)／`nozzle`(0.4\|0.6\|1.0)／`size{widthMm,heightMm,thickMm}`／
`klevels`／`noiseMm`／`pillar{enabled,xyMm}`／`seam{teeth,p2aBlock}`／`slots`(可省＝自動配色)／
`image`(ImageBitmap｜{mime,base64}｜{width,height,rgba})／`limits{gridMax,maxDecodedPixels}`／
`metadata{groupUuid,createdBy,embedSource}`／`env{...}`。

- 夾值範圍照工作室 UI；超界＝夾住並記入 `diagnostics.clamped`（不報錯）。`mode`／`nozzle` 非法＝報錯不猜。
- **原圖比例連動與 0.1mm 進位＝呼叫端職權**（C 案流中尺寸來自物件／面板，引擎只夾值不改比例；C-0 §2.1 註）。

### 5.1 `limits`（低規機保護・OOM gate）

| 欄位 | 預設 | 用途 |
|---|---|---|
| `gridMax` | 3200（＝工作室現值） | 長邊格數上限；宿主依可用實體記憶體降階 |
| `maxDecodedPixels` | 0＝不設限 | 解碼後像素上限；超過＝`image_too_large`（現行 C++ 只有 64MB 檔案上限、解碼後無上限） |

### 5.2 `env` 環境快照——過期即棄

宿主在 `generate` 帶入（欄位由宿主定義，建議：`printerPresetName`／`nozzle`／`plateId`／`plateRevision`／`projectRevision`），
引擎**原封回傳**於 `result.env`。**上盤前**再比一次現況：不相等＝丟棄結果＋通知使用者，不得寫回新情境（Codex #7）。
比較規則＝逐鍵嚴格相等（`envEqual`），新增欄位自動納入比較。

## 6. 進度階段與權重

`decode 0.02｜grid 0.10｜suggest 0.03｜quantize 0.45｜filter 0.25｜metric 0.03｜mesh 0.12`

- 權重來自 C-0 §4.1／§4.2 實測時間佔比，只用於顯示百分比。
- `quantize` 是唯一會長到分鐘級的段，因此在**列區塊**（64 列）邊界回報並讓步；
  其餘段在段邊界回報。**迴圈順序與算式不變** ⇒ 標籤結果與工作室逐位元一致。

## 7. 錯誤碼

- 引擎層（`engine.js`）：`bad_request`／`bad_image`／`image_too_large`／`mesh_module_missing`／`cancelled`／`internal`
- 協定層（`engine_protocol.js`）：`protocol_bad_message`／`protocol_bad_version`／`protocol_unknown_cmd`／
  `protocol_chunk_order`／`protocol_chunk_count`／`protocol_length_mismatch`／`protocol_sha_mismatch`／
  `protocol_job_mismatch`／`protocol_no_image`／`protocol_stale_env`

兩層不重疊；宿主據此分流（引擎層＝告訴使用者怎麼改，協定層＝重試或誠實不可用）。

## 8. 3MF 內的 metadata（schema v1）

只有 `request.metadata` 存在時才寫入（**opt-in**）：

- `Metadata/ping_phototile.json`：`schema`／`engine`／`groupUuid`／`mode`／`nozzle`／
  `canonical{widthMm,heightMm,thickMm}`／`params{klevels,noiseMm,pillar,seam,limits}`／`slots`／
  `palette[{index,hex,recipe}]`／`sourceImage{mime,byteLength,sha256,embedded,entry}`／`env`／`stats`
- `Metadata/ping_phototile_source.<ext>`：原圖位元組（裁決 6＝嵌原圖，save/reopen 可續調）

> 🔒 **保命索**：`metadata` 缺席時，3MF 的 zip entry 清單與內容與工作室（`index.html`）**完全相同**，
> 雙路黃金 oracle（`照片磚_C0尖峰產物/goldenrunner.html`，6/6 逐 entry SHA-256 全等）因此持續有效。
> 不得把 metadata 改成預設開——那會讓黃金基準失效。

## 9. 單元測

`node tools/ping/phototile_protocol_test.js` —— 涵蓋分塊往返、四項驗證的反向測試（亂序／少塊／長度竄改／SHA 竄改／
版本錯／jobId 不符）、影像注入分塊、環境快照過期判定。**改協定必須同時補測**。
