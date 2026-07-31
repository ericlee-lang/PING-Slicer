#ifndef slic3r_GUI_PhotoTileEngineHost_hpp_
#define slic3r_GUI_PhotoTileEngineHost_hpp_

// =====================================================================
// 照片磚隱形引擎宿主（C-1，2026-07-31・照片磚線 PT）
//
// 什麼是它：以「永不顯示」的 WebView2 載入 resources/web/phototile/engine.html，
// 用 job 協定驅動它產生照片磚 3MF。使用者看不到這個 webview。
//
// 為什麼不沿用 WebViewPanel（C-0 §3.3 三個親驗的不可沿用點）：
//   ① WebViewPanel::load_url() 必 Show()/Raise()/SetFocus()（WebViewDialog.cpp:259-268）
//   ② Windows 分支 new WebViewEdge 永不為 null、Create() 回傳值被無視
//      （Widgets/WebView.cpp:274）⇒ runtime 真的缺失時是**沉默假成功**
//   ③ 完全沒有 ready 握手／逾時／崩潰重建的概念
//
// 協定正本＝tools/ping/phototile_protocol.md；JS 端＝resources/web/phototile/
// engine_protocol.js。**本檔的驗證規則必須與該檔逐條一致**（四項驗證：
// 連號／塊數／總長度／SHA-256；全過才算 success）。
//
// 平台：目前僅 Windows（WebView2）。其他平台一律回報「誠實不可用」＋指引
// （C 案裁決 8），不 fallback 回工作室頁。
// =====================================================================

#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace Slic3r { namespace GUI {

// 生成請求。夾值與預設值由引擎負責（engine.js normalizeRequest），
// 這裡只做「宿主知道、引擎不知道」的欄位（影像檔路徑、環境快照、限額）。
struct PhotoTileEngineRequest
{
    std::string job_id;
    std::string mode  = "dual";      // dual | quad
    double      nozzle = 0.4;        // 0.4 | 0.6 | 1.0＝機器 effective nozzle（不是面板選的）
    double      width_mm = 100.0, height_mm = 75.0, thick_mm = 6.0;
    int         klevels = 8;
    double      noise_mm = 2.0;
    bool        pillar = true;
    int         pillar_xy_mm = 25;
    bool        teeth = false;
    bool        p2a_block = false;   // 裁決 7：實印終驗前預設關

    // 低規機保護（C-0 §4.3）。gridMax 預設＝工作室現值；0＝用引擎預設。
    int         grid_max = 0;
    long long   max_decoded_pixels = 0;

    std::string image_path;          // 原圖檔；宿主自行讀取＋base64（編碼在背景執行緒）
    bool        want_metadata = true;// 寫入 3MF 的 ping_phototile.json（裁決 6）
    bool        embed_source  = true;
    std::string group_uuid;          // 物件身分（C-2 原子替換用）
    std::string env_json;            // 環境快照；引擎原封回傳，上盤前再比一次
};

struct PhotoTileEngineResult
{
    bool        ok = false;
    std::string job_id;
    std::string error_code;          // 引擎層或協定層錯誤碼（見協定 §7）
    std::string error_message;
    std::vector<unsigned char> three_mf;
    std::string sha256;
    std::string result_json;         // palette／slots／stats／metadata／diagnostics 原文
    std::string env_json;            // 引擎回傳的環境快照（呼叫端負責比對過期）
    int         wall_ms = 0;
};

// wx 整合 smoke（C-1 首站閘門①）用的量測。C-0 只有 C# 代理量測，
// 這裡量的是**真的 wx 事件圈**。
struct PhotoTileEngineSmokeStats
{
    int    heartbeat_samples = 0;
    double heartbeat_drift_max_ms = 0;   // 心跳漂移最大值（UI 卡頓的直接證據）
    double heartbeat_drift_p95_ms = 0;
    double inject_encode_ms = 0;         // base64 編碼耗時（應在背景執行緒）
    double inject_dispatch_max_ms = 0;   // 單次注入分塊派發的 UI 執行緒成本
    double message_handle_max_ms = 0;    // 單則 page→host 訊息的處理成本
    int    chunks_received = 0;
};

class PhotoTileEngineHost
{
public:
    struct Availability
    {
        bool        available = false;
        std::string reason;      // 不可用時給使用者看的原因（誠實不可用＋指引）
        std::string runtime_version;
    };

    using ProgressFn = std::function<void(const std::string& job_id, const std::string& stage,
                                          const std::string& stage_label, double pct)>;
    using ResultFn   = std::function<void(const PhotoTileEngineResult&)>;
    using StatusFn   = std::function<void(const std::string& status, const std::string& detail)>;

    PhotoTileEngineHost();
    ~PhotoTileEngineHost();

    // WebView2 runtime 檢測——**建立前**先問，缺失即誠實不可用（裁決 8）。
    static Availability check_runtime();

    // 建立隱形宿主並等 ready 握手（非阻塞；成敗走 status callback）。
    // 重複呼叫安全：已就緒＝直接回 true。
    bool start();
    void shutdown();
    bool is_ready() const;
    bool is_busy() const;

    // 送出生成請求。生成中再送＝supersede（引擎端取消舊 job）。
    bool generate(const PhotoTileEngineRequest& req);
    void cancel(const std::string& job_id);

    void set_progress_handler(ProgressFn fn);
    void set_result_handler(ResultFn fn);
    void set_status_handler(StatusFn fn);   // ready／unavailable／rebuild／superseded…

    // 環境快照比對（鏡像 engine_protocol.js 的 envEqual）：不相等＝結果丟棄。
    static bool env_is_fresh(const std::string& result_env_json, const std::string& current_env_json);

    // 閘門①用：開啟量測（心跳探針由呼叫端驅動 tick）
    void enable_smoke_metrics(bool on);
    const PhotoTileEngineSmokeStats& smoke_stats() const;
    void smoke_heartbeat_tick(double expected_interval_ms);

private:
    // 內部流程（Windows 實作；非 Windows 不會被呼叫到）
    void create_controller();
    void navigate_and_wait_ready();
    void handle_message(const std::string& json);        // 護欄：吞掉一切例外（COM 回呼不得逃逸）
    void handle_message_inner(const std::string& json);  // 真正的分派邏輯
    void pump_inject_queue();
    static std::string build_generate_command(const PhotoTileEngineRequest& req);

    struct Impl;
    std::unique_ptr<Impl> p;
};

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_PhotoTileEngineHost_hpp_
