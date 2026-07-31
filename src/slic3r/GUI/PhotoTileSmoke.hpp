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
// =====================================================================

#include <string>

class wxWindow;

namespace Slic3r { namespace GUI {

// 跑 smoke（非阻塞：結果以對話框呈現、JSON 落 data_dir()/phototile_smoke_report.json）。
// expected_sha 留空＝只量效能不比對黃金。
void run_photo_tile_wx_smoke(wxWindow* parent, const std::string& expected_sha);

// 守夜基準（PhotoTileSleepVigil 2026-07-31，480×360 決定性測試圖／dual 60×45／K=6／無柱）
extern const char* PHOTOTILE_SMOKE_EXPECTED_SHA;

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_PhotoTileSmoke_hpp_
