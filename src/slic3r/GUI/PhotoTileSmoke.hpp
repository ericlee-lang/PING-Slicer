#ifndef slic3r_GUI_PhotoTileSmoke_hpp_
#define slic3r_GUI_PhotoTileSmoke_hpp_

// =====================================================================
// 照片磚 C-1 首站閘門①：wx 整合 smoke（2026-07-31・照片磚線 PT）
//
// C-0 §3.3／§4.3 誠實化後留下的缺口：「JS 生成不跑在 C++ UI 執行緒」已證實，
// 但 per-message 成本只有 **C# 宿主的代理量測**（常態 ≤38ms／36MB 注入段 871ms）。
// wx 事件圈的真實成本沒量過——那就是本檔要做的事。
//
// 量三件：
//   ① UI 事件圈心跳漂移（10ms 計時器；生成全程量 max/p95）＝卡頓的直接證據
//   ② 影像注入的 UI 執行緒成本（編碼已移到背景執行緒，這裡量派發段）
//   ③ 跨宿主黃金一致性：用**與過夜守夜完全相同**的圖與參數，
//      C++ 宿主產出的 3MF SHA-256 必須等於 spike 宿主的基準值
//      ⇒ 同時證明「產品宿主 ≡ spike 宿主 ≡ 產品引擎」。
//
// 判準（先寫死，避免事後合理化；任一不過＝回報 Eric 評估轉 A）：
//   - 心跳漂移 p95 ≤ 100ms、max ≤ 500ms
//   - dual 60×45 生成 ≤ 6s（C-0 瀏覽器基準 ~2.6s，宿主約 1.5× 上浮）
//   - SHA 與守夜基準一致、四項驗證全過
//
// 【2026-08-01 二版：判準拆兩段（Codex 重要 #6）】上面那組門檻**同時**套在兩個 verdict 上：
//   steady ＝第 2~5 輪（使用者反覆生成的真實情境）
//   startup＝含第 1 輪的全程（app 初始化＋WebView2 首建＋頁面首載）
// `ok` 只在兩者皆過時 true；只有 steady 過＝誠實標 `PASS_STEADY`，不是 PASS。
// ⚠ 不准為了讓 startup 變綠而放寬它的門檻——正解是產品做「閒置預熱」（開 app 就先建引擎），
//    預熱到位後 startup 自然會綠。這條寫在這裡是因為它已經被偷換過一次。
// =====================================================================

#include <string>

class wxWindow;

namespace Slic3r { namespace GUI {

// 跑 smoke（非阻塞：結果以對話框呈現、JSON 落 data_dir()/phototile_smoke_report.json）。
// expected_sha 留空＝只量效能不比對黃金。
void run_photo_tile_wx_smoke(wxWindow* parent, const std::string& expected_sha);

// 閘門③：OOM／低記憶體 gate（降階有效性＋超限誠實報錯）。實作＝PhotoTileLimitsGate.cpp
void run_photo_tile_limits_gate();

// C-1 活體實測：capability／取消／supersede／環境快照過期即棄。實作＝PhotoTileLiveGate.cpp
void run_photo_tile_live_gate();

// 閘門②：過夜睡眠守夜（**產品宿主**版）。實作＝PhotoTileSleepVigil.cpp
void run_photo_tile_sleep_vigil();

// 黃金閘門：六案經產品宿主產生，用 app 自己的 zip reader 與真 importer 驗。
// 實作＝PhotoTileGoldenGate.cpp（Codex 重要 #12）
void run_photo_tile_golden_gate();

// 取消延遲量測（#11 後半的「先量」；引擎零改動）。實作＝PhotoTileCancelLatency.cpp
void run_photo_tile_cancel_latency();

// 守夜基準（PhotoTileSleepVigil 2026-07-31，480×360 決定性測試圖／dual 60×45／K=6／無柱）
extern const char* PHOTOTILE_SMOKE_EXPECTED_SHA;

/* 各閘門共用的決定性測試圖（與 C# 守夜的 MakeTestImage 逐像素相同）。
   ⚠ 一定要共用同一支：三個閘門各抄一份的話，只要有人改了其中一份，
   SHA 比對就會靜默失去意義——那正是黃金比對最不該發生的失效模式。 */
std::string write_photo_tile_test_image(int W = 480, int H = 360,
                                        const char* name = "phototile_test_input.png");

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_PhotoTileSmoke_hpp_
