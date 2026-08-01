#ifndef slic3r_GUI_PhotoTileEngineHost_hpp_
#define slic3r_GUI_PhotoTileEngineHost_hpp_

// =====================================================================
// 照片磚隱形引擎宿主（C-1，2026-08-01 加固版・照片磚線 PT）
//
// 什麼是它：以「永不顯示」的 WebView2 載入 resources/web/phototile/engine.html，
// 用 job 協定驅動它產生照片磚 3MF。使用者看不到這個 webview。
//
// 為什麼不沿用 WebViewPanel（C-0 §3.3 三個親驗的不可沿用點）：
//   ① WebViewPanel::load_url() 必 Show()/Raise()/SetFocus()
//   ② Windows 分支 Create() 回傳值被無視 ⇒ runtime 真缺失時是沉默假成功
//   ③ 完全沒有 ready 握手／逾時／崩潰重建的概念
//
// 【2026-08-01 加固】Codex 對抗審查（4 阻斷）後的結構改動——這四點是**設計約束**，
// 日後 C-2/C-3 往上加東西時不得破壞：
//   A. 狀態一律由 `shared_ptr<Impl>` 持有，**所有非同步邊界只捕捉 weak_ptr**
//      （COM 回呼／背景執行緒／CallAfter／wxTimer）。shutdown() 先標 Closing 再拆，
//      晚到的回呼 lock 不到或看到 Closing 就安靜退場 ⇒ 消滅 use-after-free。
//   B. **每個邊界都是 noexcept trampoline**：例外一律在邊界收斂（穿越 COM 回呼＝
//      std::terminate＝app 猝死，2026-07-31 已實錄一次）。外部 handler 亦獨立包覆。
//   C. **job epoch**：每次 generate 遞增；工作執行緒、注入佇列、頁面訊息全部帶 epoch，
//      對不上就丟棄 ⇒ 舊 job 不可能清掉新 job 的狀態或交付舊 3MF。
//   D. **序列化生命週期狀態機**（Stopped→CreatingEnv→CreatingController→Navigating→
//      Ready→Rebuilding→Unavailable/Closing）：任何時刻只有一條建立路徑在跑，
//      重建依 failure kind 分流，連續失敗計數在穩定就緒後歸零。
//
// 協定正本＝tools/ping/phototile_protocol.md；JS 端＝engine_protocol.js。
// 平台：目前僅 Windows（WebView2）；其他平台誠實不可用（C 案裁決 8）。
// =====================================================================

#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace Slic3r { namespace GUI {

struct PhotoTileEngineRequest
{
    std::string job_id;
    std::string mode  = "dual";      // dual | quad
    double      nozzle = 0.4;        // effective nozzle（機器實際噴嘴，不是面板選的）
    double      width_mm = 100.0, height_mm = 75.0, thick_mm = 6.0;
    int         klevels = 8;
    double      noise_mm = 2.0;
    bool        pillar = true;
    int         pillar_xy_mm = 25;
    bool        teeth = false;
    bool        p2a_block = false;   // 裁決 7：實印終驗前預設關

    int         grid_max = 0;        // 0＝引擎預設（3200）
    long long   max_decoded_pixels = 0;

    std::string image_path;          // 原圖檔；宿主自行讀取＋base64（背景執行緒）
    bool        want_metadata = true;// 寫入 3MF 的 ping_phototile.json（裁決 6）
    bool        embed_source  = true;
    std::string group_uuid;
    std::string env_json;            // 環境快照；引擎原封回傳，上盤前再比一次

    // 故障注入（**僅測試用**，產品路徑一律空）：讓引擎頁刻意送出壞掉的傳輸，
    // 用來證明 C++ 端的四項驗證真的擋得住。值＝協定文件 §9 的 fault 代碼。
    std::string fault_inject;
};

struct PhotoTileEngineResult
{
    bool        ok = false;
    std::string job_id;
    std::string error_code;
    std::string error_message;
    std::vector<unsigned char> three_mf;
    std::string sha256;
    std::string result_json;
    std::string env_json;
    int         wall_ms = 0;
};

struct PhotoTileEngineSmokeStats
{
    int    heartbeat_samples = 0;
    double heartbeat_drift_max_ms = 0;
    double heartbeat_drift_p95_ms = 0;
    double inject_encode_ms = 0;
    double inject_dispatch_max_ms = 0;
    double message_handle_max_ms = 0;
    int    chunks_received = 0;
};

class PhotoTileEngineHost
{
public:
    struct Availability
    {
        bool        available = false;
        std::string reason;
        std::string runtime_version;
    };

    using ProgressFn = std::function<void(const std::string& job_id, const std::string& stage,
                                          const std::string& stage_label, double pct)>;
    using ResultFn   = std::function<void(const PhotoTileEngineResult&)>;
    using StatusFn   = std::function<void(const std::string& status, const std::string& detail)>;

    PhotoTileEngineHost();
    ~PhotoTileEngineHost();

    static Availability check_runtime();

    bool start();
    void shutdown();
    bool is_ready() const;
    bool is_busy() const;

    bool generate(const PhotoTileEngineRequest& req);
    void cancel(const std::string& job_id);

    void set_progress_handler(ProgressFn fn);
    void set_result_handler(ResultFn fn);
    void set_status_handler(StatusFn fn);

    // 環境快照比對（鏡像 engine_protocol.js 的 envEqual）：不相等＝結果丟棄。
    // 比對規則：按鍵查找（不看順序）＋數值容忍，但鍵數不同仍判過期。
    static bool env_is_fresh(const std::string& result_env_json, const std::string& current_env_json);

    void enable_smoke_metrics(bool on);
    const PhotoTileEngineSmokeStats& smoke_stats() const;
    void smoke_heartbeat_tick(double expected_interval_ms);

private:
    struct Impl;
    std::shared_ptr<Impl> p;   // ⚠ 非同步邊界只准捕捉 weak_ptr（見檔頭 A）
};

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_PhotoTileEngineHost_hpp_
