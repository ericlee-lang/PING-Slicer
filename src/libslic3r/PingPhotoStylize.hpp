#ifndef slic3r_PingPhotoStylize_hpp_
#define slic3r_PingPhotoStylize_hpp_

// PING 照片磚「本地風格化」——把照片壓成乾淨的平色塊，再交給既有的量化鏈。
//
// 為什麼要有這支（規格 R6-9）：
//   工作室按下「本地款式」時，ptApply() **只做三件事**——設料數／設料色／設色階數。
//   款式庫裡那一行 pipeline（bilateral → mean-shift → k-means → medianBlur）
//   是 dev 端 `照片磚管線/pipeline.py` 的**流程紀錄**，產品從來沒有執行過它。
//   ⇒ 「本地款式」在產品裡的實質是一組預設參數，不是一種畫風。本檔就是把那條管線搬進產品。
//
// 演算法正本＝`照片磚管線/pipeline.py` 的 generate_local()（第 71–97 行）。
//   四支呼叫與參數**逐字照抄**，不得自行「優化」：那些數字是 0814–0815 用四個題材實跑調出來的，
//   改任何一個都等於換一種畫風，要先有新的實測才准動。
//
// 刻意與 pipeline.py 不同的一處（只有這一處）：
//   pipeline.py 自己在兩支料色之間算 K 階漸層；本檔**改由呼叫端把 K 個顏色直接傳進來**（ramp）。
//   理由＝色階梯已經在 2026-08-22 收斂成單一來源（開發線＝engine.js 的 dualLadder，由
//   PhotoTileEngine.dualLadder 匯出給頁面用）。在 C++ 再算一份就是第三份梯子，
//   而「同一條梯子有兩份實作」正是本專案一再付學費的失效形態。
//
// 效能（2026-08-22 實測，OpenCV C++、代用柯基 1024×1536）：
//   400px 0.75s／600px 0.96s／800px 2.14s／1200px 4.34s／3200px 11.65s
//   最終標籤逐格一致率（vs 1200px）：400px 97.27%／600px 98.35%／800px 99.00%
//   ⇒ 產品用 800px。dev 端原本是 1200，但那不是必要的——風格化本來就是抹掉細節的步驟，
//     在低解析度做完再讓格點取樣器放大，資訊沒有損失。
//
// 相依：OpenCV（core + imgproc + imgcodecs）——本 repo 早已 find_package/link
//   （src/libslic3r/CMakeLists.txt:501、584；SkipPartCanvas.cpp 已在用 imgproc）。零新相依。

#include <string>
#include <vector>

namespace Slic3r {

struct PhotoStylizeParams
{
    std::string src_path;                 // 來源影像的檔案路徑（宿主手上的暫存檔）
    int         work_width = 800;         // 風格化工作寬度（px）。見檔頭的解析度實測
    int         tones      = 4;           // k-means 的 K ＝ 磚的色階數（頁面用 ptTones 決定）
    // K 個顏色，index 0 ＝最亮端、index tones-1 ＝最暗端。
    // 由呼叫端（頁面）從**唯一那條色階梯**算好傳進來，本檔不自己算（見檔頭）。
    std::vector<std::string> ramp_hex;
};

struct PhotoStylizeResult
{
    bool                       ok = false;
    std::string                error;        // 給人看的訊息（失敗時才有值）
    std::vector<unsigned char> png;          // 成功時的輸出 PNG 位元組
    int                        width  = 0;
    int                        height = 0;
    double                     elapsed_ms = 0.0;
};

// 同步執行；呼叫端自行決定要不要丟背景執行緒（800px 約 2 秒，不該卡 UI 執行緒）。
// 失敗一律回 ok=false ＋ error，**不丟例外、不回半成品**——上層要能誠實把失敗講給使用者看。
PhotoStylizeResult ping_photo_stylize(const PhotoStylizeParams& params);

} // namespace Slic3r

#endif // slic3r_PingPhotoStylize_hpp_
