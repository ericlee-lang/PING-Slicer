# SOP — PING Slicer 內部測試版發布

> 適用範圍：正式維護線的 Windows installer／portable 完成 build 後，更新內部共用下載資料夾。
> 固定入口：`G:\我的雲端硬碟\2026claude\PING Slicer`。
> 原則：根目錄永遠是最新版；舊版只移入 `old\`，不刪除；更新後必須做雲端端讀回驗證。

## 1. 發布權威與前置閘門

1. 正式版本只從 `release/v3.6`（或後續正式 `release/*`）發；照片磚只從 `ping/photo-tile` 發。
2. 工作樹必須乾淨，記錄 commit SHA 與 Actions run ID。
3. 執行 `python tools/ping/verify_profiles.py`，並完成精靈 JavaScript 語法檢查。
4. Windows 產品 job 必須成功且 installer／portable artifacts 都存在。整體 workflow 因既知 Flatpak／Unit Tests 失敗而紅，不等於 Windows 產品失敗；判斷時看產品 job 與 artifact，不只看總結顏色。

## 2. 下載與完整性驗證

1. 優先由 GitHub Actions artifact 下載。若 `gh` 登入失效，可用公開 artifact ID 的 `nightly.link` 取得 wrapper zip。
2. 同時讀 GitHub artifact metadata 的官方 `digest`；wrapper zip 的 SHA-256 必須與官方 digest 完全一致，不一致就停止發布。
3. installer artifact 是 wrapper zip：解開後取其中的 `.exe` 作為最終檔。
4. portable artifact 本身就是發行 zip：只改成正式檔名，不再重新壓縮。
5. 計算並記錄最終 installer／portable SHA-256、檔案大小、commit SHA、run ID。

## 3. Portable 離線驗證

1. 解開 portable 到 staging，不直接在共用資料夾驗。
2. 核對 `resources/profiles/PING.json` 的 bundle 版號。
3. 核對本版應有機型／製程都存在，明確排除項目也確實不存在。
4. 若本版改了精靈、提示、色票或排序，先以 portable 做畫面驗收；正式對外前再做代表機型切片與 G-code 檢查。

## 4. 更新固定共用資料夾

1. 在 workspace staging 準備好新 installer、portable、`版本資訊.txt`；不要直接在雲端同步資料夾下載／解壓。
2. 先把新檔複製到根目錄，核對同步路徑中的 SHA-256。
3. 解析並再次確認根目錄及 `old\` 的絕對路徑都位於 `G:\我的雲端硬碟\2026claude\PING Slicer` 範圍內，再進行移動。
4. 把上一版 installer、portable、上一版版本資訊移入 `old\`；版本資訊改名含版本與日期，例如 `版本資訊_V3.5.5_r6_2026-07-14.txt`。只移動，不刪除。
5. 根目錄最後只保留：`old\`、最新版 installer、最新版 portable、`版本資訊.txt`。
6. `版本資訊.txt` 至少寫：版本、日期、兩檔 SHA-256、主要變更、bundle 版號、commit/run、已知 workflow 紅燈原因、明確排除項目。

## 5. 完成判定

1. 從 Google Drive／同步端重新列出根目錄與 `old\`，確認遠端實際狀態，不只看本機檔案總管。
2. 下載或讀回 `版本資訊.txt`，確認內容是新版本且編碼正常。
3. 回報四項證據：固定資料夾、版本、兩檔 SHA-256、舊版已歸檔位置。

## 6. V3.6 已驗證範例（2026-07-16）

- Binary commit：`52a4b935`
- GitHub Actions run：`29427421714`
- Installer：`PING_Slicer_Windows_Installer_V3.6.0.exe`
  SHA-256：`5864F15DFA373321DCB6EAACA17AB16656C912213A73F54A4DA89DF8630213BC`
- Portable：`PING_Slicer_Windows_V3.6.0_portable.zip`
  SHA-256：`310C217AABAA0DFEAF90A81DF990019B33B65B30EB4EEFBB3B07C384847056E3`
- Portable 核對：bundle v51、Classic 八機存在、DL1016 不存在。
