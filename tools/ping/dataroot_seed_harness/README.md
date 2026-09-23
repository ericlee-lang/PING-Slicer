# 測試版資料夾「首次只讀複製」harness

版本治理第 4 件（Eric 2026-09-24 裁；牌 `c-0924-DR-01`）：測試版改用 `PINGSlicer-Internal`，
第一次開時從正式版**只讀**複製一次。這支 harness 在**不 build 整個 App** 的情況下，
把 `src/slic3r/GUI/GUI_App.cpp` 裡那段輔助函式**原樣抽出來**（`extract.cjs`）編成小程式，
在 `%TEMP%` 底下造一棵假的正式資料夾跑六種情境：

1. 第一次開：該抄的都抄到、備份／log／cache／ota／照片磚隱形宿主 WebView 不抄、**正式資料夾逐檔內容與時間戳不變**
2. 第二次開：已有 Internal ⇒ 不再抄（測試版自己改過的不被蓋回）
3. 上次抄到一半留下 `.seeding` ⇒ 重來、不留半套
4. 這台沒有正式版 ⇒ 不抄、從空白開始
5. 防呆：target 與 official 同一處 ⇒ 什麼都不做
6. 網頁儲存區只抄 `Local Storage`／`IndexedDB`，不抄快取、登入資料、鎖檔

跑法（Windows，需 VS2022 BuildTools、node、本機 c1 deps 的 boost）：

```bat
tools\ping\dataroot_seed_harness\build_and_run.bat
```

最後一行 `EXIT=0` 且 `結果：ALL PASS 0` 才算過。產物全在 `%TEMP%\ping_dataroot_harness`，不進 repo。

**2026-09-24 首跑就抓到一個真 bug**：`exists(target, ec) || ec` 在 Windows 上「不存在」也會設 `ec`
⇒ 永遠不抄、連一行 log 都沒有（已改成看 `file_status` 型別）。突變測試（不跳過 log＋誤寫正式資料夾）三條轉紅。
