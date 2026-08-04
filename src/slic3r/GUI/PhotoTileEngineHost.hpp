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

    /* 【C-2 2026-08-04 補】使用者在工作室挑的料色（engine.js 的 `slots`，JSON 陣列原文）。
       空＝引擎自動建議配色（＝C-1 的行為）。**這是 C-1 的產品缺口**：C-1 的閘門全是自動
       配色案，宿主從來沒有把使用者選的顏色送下去；工作室一旦改走宿主，不補這欄就會靜默
       丟掉使用者的配色。刻意做成「非空才寫進請求」＝不帶時位元組與 C-1 全等，黃金 12 案基準不受影響。 */
    std::string slots_json;

    std::string image_path;          // 原圖檔；宿主自行讀取＋base64（背景執行緒）
    bool        want_metadata = true;// 寫入 3MF 的 ping_phototile.json（裁決 6）
    bool        embed_source  = true;
    std::string group_uuid;
    std::string env_json;            // 環境快照；引擎原封回傳，上盤前再比一次

    // 故障注入（**僅測試用**，產品路徑一律空）：讓引擎頁刻意送出壞掉的傳輸，
    // 用來證明 C++ 端的四項驗證真的擋得住。值＝協定文件 §9 的 fault 代碼。
    std::string fault_inject;

    // 【僅測試用】不對進行中的舊 job 預先送 cancel，讓**引擎頁自己**收到第二個
    // generate ⇒ 走它的 supersede 分支。產品路徑一律 false（宿主先收斂比較快）。
    // 為什麼要有：Codex 重要 #8——原本的 supersede 案從沒命中頁面那條分支，
    // 報告自己寫著 supersededStatusSeen:false 卻標 pass。
    bool test_page_supersede = false;
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

// 宿主內部狀態的唯讀快照。用途＝閘門要能斷言「重建真的發生過」而不是只看日誌；
// browser_pid 讓測試找得到引擎行程去殺（Codex 阻斷 #4：重建路徑從未被實際觸發過）。
struct PhotoTileEngineDiag
{
    std::string  stage;              // Stopped/CreatingEnv/.../Ready/Rebuilding/Unavailable/Closing
    int          rebuild_count = 0;  // 連續重建計數（穩定 ready 後歸零）
    unsigned int browser_pid = 0;    // WebView2 browser 行程 PID；0＝取不到
    bool         busy = false;
    std::string  active_job;
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

    /* 【C-2 第 5 項・定罪儀器】result 傳輸段在 UI 執行緒上的**累積**佔用。
       為什麼要另外量：既有的 uiDriftMaxMs／message_handle_max_ms 都是「最久的**一次**」，
       但 80MB＝96KB×833 塊＝833 則訊息，使用者感覺到的那幾秒是**總和**不是單則
       ——最大單則只有幾 ms 的情況下，總和照樣可以是好幾秒，而 max 型指標會回報「沒事」。
       兩種數字都要，缺一就會把「833 次小卡」誤讀成健康。全部只在 smoke_on 時累計。 */
    double xfer_ui_total_ms      = 0;   // begin+chunk+end 三型訊息的 UI 執行緒耗時總和
    double xfer_parse_total_ms   = 0;   //   其中 JSON 剖析（ptree）的總和——payload 就塞在 JSON 裡
    double xfer_parse_max_ms     = 0;   //   單則剖析最久
    long long xfer_json_bytes    = 0;   //   剖析過的 JSON 文字總長（配 parse_total 算 MB/s）
    double chunk_decode_total_ms = 0;   //   其中 wxBase64Decode 的總和
    double chunk_decode_max_ms   = 0;   //   單塊解碼最久
    double end_sha_ms            = 0;   // end 對整包算一次 sha256 的耗時（單一大操作嫌疑）
    double end_total_ms          = 0;   // end 整則訊息的耗時（含 sha＋deliver）
    double xfer_wall_ms          = 0;   // begin→end 的牆鐘時間（配 xfer_ui_total_ms 算佔用率）
    int    xfer_msgs             = 0;   // 傳輸段訊息則數（begin+chunk+end）
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

    /* 覆審 I-4：產品路徑的解碼後像素 OOM 帽建議值——依可用實體記憶體推
       （可用 /8 份同時活著 /4 bytes-per-px），夾 8e6～48e6；查不到＝保守 8e6。
       C-1 實測：48Mpx＋quad 在 4GB Job Object 下 engine_crashed；帶帽對照案誠實回
       image_too_large。放這裡（而非 GUI_App）＝winapi 只留在已含 Windows 標頭的檔。 */
    static long long suggest_max_decoded_pixels();

    bool start();
    void shutdown();
    bool is_ready() const;
    bool is_busy() const;

    bool generate(const PhotoTileEngineRequest& req);
    void cancel(const std::string& job_id);

    void set_progress_handler(ProgressFn fn);
    void set_result_handler(ResultFn fn);
    void set_status_handler(StatusFn fn);

    /* 【C-2 第 2 項・一輪 #9】current-env provider：回傳「此刻」的環境快照 JSON
       （產品端＝選中的印表機 preset 名＋專案檔名）。設定後 generate() 會在
       req.env_json 為空時自動蓋章 ⇒ 呼叫端忘不掉（覆審 #9 建議修法：納入 host API，
       stale 成功不可能離開 guard）；上盤入口再用 env_is_fresh 比對、過期即棄。
       閘門／煙測不註冊 ⇒ 請求位元組與 C-1 全等，黃金 12 案基準不受影響。
       只會在 UI 執行緒被呼叫（generate 與上盤入口都在 UI 執行緒）。 */
    using EnvProviderFn = std::function<std::string()>;
    void set_current_env_provider(EnvProviderFn fn);

    // 環境快照比對（鏡像 engine_protocol.js 的 envEqual）：不相等＝結果丟棄。
    // 比對規則：按鍵查找（不看順序）＋數值容忍，但鍵數不同仍判過期。
    static bool env_is_fresh(const std::string& result_env_json, const std::string& current_env_json);

    PhotoTileEngineDiag diagnostics() const;

    // 【僅測試用】把引擎頁導到不存在的位址：之後每次建立都會 ready 逾時 ⇒
    // 可決定性地驗證 REBUILD_CAP 真的會截停（閘門 H）。產品路徑永不呼叫。
    void test_break_engine_url(bool on);

    void enable_smoke_metrics(bool on);
    const PhotoTileEngineSmokeStats& smoke_stats() const;
    void smoke_heartbeat_tick(double expected_interval_ms);

private:
    struct Impl;
    std::shared_ptr<Impl> p;   // ⚠ 非同步邊界只准捕捉 weak_ptr（見檔頭 A）
};

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_PhotoTileEngineHost_hpp_
