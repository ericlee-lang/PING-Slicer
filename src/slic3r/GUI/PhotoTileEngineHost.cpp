// 照片磚隱形引擎宿主（C-1 加固版）——實作。設計約束 A/B/C/D 見 .hpp 檔頭。
// 四項驗證（連號／塊數／總長度／SHA-256）與 engine_protocol.js 逐條對應。

#include "PhotoTileEngineHost.hpp"

#include "GUI_App.hpp"
#include "libslic3r/Utils.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <deque>
#include <sstream>
#include <thread>

#include <boost/log/trivial.hpp>
#include <boost/nowide/fstream.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>

#include <openssl/sha.h>

#include <wx/app.h>
#include <wx/base64.h>
#include <wx/frame.h>
#include <wx/timer.h>

#ifdef _WIN32
    #include <wrl.h>
    #include <wrl/event.h>
    #include <WebView2.h>
    #include <WebView2EnvironmentOptions.h>
#endif

namespace pt = boost::property_tree;

namespace Slic3r { namespace GUI {

namespace {

constexpr int    PROTOCOL_VERSION   = 1;
constexpr size_t INJECT_CHUNK_CHARS = 192 * 1024;
constexpr size_t INJECT_BATCH       = 8;
constexpr int    READY_TIMEOUT_MS   = 15000;
constexpr int    REBUILD_CAP        = 3;
constexpr long long MAX_IMAGE_BYTES = 64LL * 1024LL * 1024LL;

std::string sha256_hex(const unsigned char* data, size_t len)
{
    unsigned char digest[SHA256_DIGEST_LENGTH];
    SHA256(data, len, digest);
    static const char* hex = "0123456789abcdef";
    std::string out(SHA256_DIGEST_LENGTH * 2, '0');
    for (int i = 0; i < SHA256_DIGEST_LENGTH; ++i) {
        out[i * 2]     = hex[digest[i] >> 4];
        out[i * 2 + 1] = hex[digest[i] & 0x0f];
    }
    return out;
}

/* ⚠ write_json 對「純量節點」會丟例外（boost 無法把裸值寫成 JSON 文件）——
   2026-07-31 閘門③即因 env:null 炸掉整個 app。一律吞掉並回空字串。 */
std::string ptree_to_json(const pt::ptree& tree)
{
    try {
        std::ostringstream ss;
        pt::write_json(ss, tree, false);
        std::string s = ss.str();
        s.erase(std::remove(s.begin(), s.end(), '\n'), s.end());
        return s;
    } catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(warning) << "PhotoTileEngineHost: ptree 轉 JSON 失敗（" << e.what() << "）";
        return std::string();
    }
}

bool json_from_string(const std::string& text, pt::ptree& out)
{
    try {
        std::istringstream ss(text);
        pt::read_json(ss, out);
        return true;
    } catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(warning) << "PhotoTileEngineHost: JSON 解析失敗 " << e.what();
        return false;
    }
}

/* 環境快照比對：①按鍵查找不看順序 ②數值容忍（0.4 與 "0.4" 相同）
   ③鍵數不同仍判過期。實測依據：2026-08-01 活體實測 D 項——JSON 往返會重排鍵序、
   數值會變字串，逐位置比對永遠判不相等。 */
bool leaf_equal(const std::string& a, const std::string& b)
{
    if (a == b) return true;
    try {
        size_t ia = 0, ib = 0;
        const double da = std::stod(a, &ia), db = std::stod(b, &ib);
        if (ia == a.size() && ib == b.size()) return da == db;
    } catch (...) {}
    return false;
}
bool ptree_equal(const pt::ptree& a, const pt::ptree& b)
{
    if (a.size() != b.size())
        return false;
    if (a.empty())
        return leaf_equal(a.data(), b.data());
    for (const auto& kv : a) {
        const auto other = b.get_child_optional(pt::ptree::path_type(kv.first, '\0'));
        if (!other) return false;
        if (!ptree_equal(kv.second, *other)) return false;
    }
    return true;
}

double now_ms()
{
    using namespace std::chrono;
    return duration_cast<duration<double, std::milli>>(steady_clock::now().time_since_epoch()).count();
}

#ifdef _WIN32
// UTF-8 ↔ UTF-16。⚠ 不可用 std::wstring(begin,end) 逐位元組拓寬（中文會變亂碼）。
std::wstring utf8_to_wide(const std::string& s)
{
    if (s.empty()) return std::wstring();
    const int n = ::MultiByteToWideChar(CP_UTF8, 0, s.data(), (int) s.size(), nullptr, 0);
    std::wstring w((size_t) n, L'\0');
    ::MultiByteToWideChar(CP_UTF8, 0, s.data(), (int) s.size(), &w[0], n);
    return w;
}
std::string wide_to_utf8(const wchar_t* s)
{
    if (!s) return std::string();
    const int n = ::WideCharToMultiByte(CP_UTF8, 0, s, -1, nullptr, 0, nullptr, nullptr);
    if (n <= 1) return std::string();
    std::string out((size_t) n - 1, '\0');
    ::WideCharToMultiByte(CP_UTF8, 0, s, -1, &out[0], n, nullptr, nullptr);
    return out;
}
std::string hex_hr(long hr)
{
    char buf[32];
    ::snprintf(buf, sizeof(buf), "0x%08lX", (unsigned long) hr);
    return buf;
}
#endif

/* host→page 訊息一律手組 JSON（boost ptree 會把數值寫成字串，引擎頁嚴格比較會拒收） */
std::string json_escape(const std::string& s)
{
    std::string out;
    out.reserve(s.size() + 8);
    for (unsigned char c : s) {
        switch (c) {
        case '"':  out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n";  break;
        case '\r': out += "\\r";  break;
        case '\t': out += "\\t";  break;
        default:
            if (c < 0x20) { char buf[8]; ::snprintf(buf, sizeof(buf), "\\u%04x", c); out += buf; }
            else          out += (char) c;
        }
    }
    return out;
}
std::string jkv(const std::string& k, const std::string& v) { return "\"" + json_escape(k) + "\":\"" + json_escape(v) + "\""; }
std::string jkn(const std::string& k, double v)
{
    std::ostringstream ss;
    if (v == (long long) v) ss << (long long) v; else ss << v;
    return "\"" + json_escape(k) + "\":" + ss.str();
}
std::string jkb(const std::string& k, bool v) { return "\"" + json_escape(k) + "\":" + (v ? "true" : "false"); }

} // namespace

// ===================== Impl：所有狀態與邏輯都在這裡 =====================
// 設計約束 A：外界（含所有非同步回呼）只透過 weak_ptr 取得它。
struct PhotoTileEngineHost::Impl : public std::enable_shared_from_this<PhotoTileEngineHost::Impl>
{
    // ---- 生命週期狀態機（設計約束 D）----
    enum class Stage { Stopped, CreatingEnv, CreatingController, Navigating, Ready, Rebuilding, Unavailable, Closing };
    Stage stage = Stage::Stopped;

    static const char* stage_name(Stage s)
    {
        switch (s) {
        case Stage::Stopped:            return "Stopped";
        case Stage::CreatingEnv:        return "CreatingEnv";
        case Stage::CreatingController: return "CreatingController";
        case Stage::Navigating:         return "Navigating";
        case Stage::Ready:              return "Ready";
        case Stage::Rebuilding:         return "Rebuilding";
        case Stage::Unavailable:        return "Unavailable";
        default:                        return "Closing";
        }
    }
    bool closing()  const { return stage == Stage::Closing; }
    bool building() const { return stage == Stage::CreatingEnv || stage == Stage::CreatingController ||
                                   stage == Stage::Navigating  || stage == Stage::Rebuilding; }

    PhotoTileEngineHost::ProgressFn on_progress;
    PhotoTileEngineHost::ResultFn   on_result;
    PhotoTileEngineHost::StatusFn   on_status;

    // ---- job epoch（設計約束 C）----
    bool               test_break_engine_url = false;   // 僅測試用（閘門 H：驗 REBUILD_CAP）
    unsigned long long epoch = 0;         // 每次 generate 遞增
    std::string        active_job;        // 目前唯一有效的 job
    bool               busy = false;
    int                rebuild_count = 0;

    struct Transfer {
        bool        active = false;
        std::string job_id;
        size_t      size = 0, chunks = 0, received = 0;
        std::string sha256;
        std::vector<unsigned char> bytes;
    } xfer;

    PhotoTileEngineResult     pending;
    bool                      pending_valid = false;
    PhotoTileEngineRequest    queued_request;
    bool                      has_queued_request = false;

    PhotoTileEngineSmokeStats smoke;
    bool                      smoke_on = false;
    double                    last_heartbeat_ms = 0;
    std::vector<double>       heartbeat_drifts;

    // ---- 外部 handler 一律獨立包覆（設計約束 B）：呼叫端丟例外不得殺掉宿主 ----
    template<class F> static void safe_call(const char* what, F&& f)
    {
        try { f(); }
        catch (const std::exception& e) { BOOST_LOG_TRIVIAL(error) << "PhotoTileEngineHost: " << what << " 丟出例外（已攔下）：" << e.what(); }
        catch (...)                     { BOOST_LOG_TRIVIAL(error) << "PhotoTileEngineHost: " << what << " 丟出未知例外（已攔下）"; }
    }
    void set_stage(Stage s, const std::string& detail = std::string())
    {
        if (stage == s) return;
        BOOST_LOG_TRIVIAL(info) << "PhotoTileEngineHost stage " << stage_name(stage) << " → " << stage_name(s)
                                << (detail.empty() ? "" : "（" + detail + "）");
        stage = s;
    }
    void status(const std::string& s, const std::string& detail)
    {
        BOOST_LOG_TRIVIAL(info) << "PhotoTileEngineHost [" << s << "] " << detail;
        if (on_status) safe_call("status handler", [&] { on_status(s, detail); });
    }
    /* 每個 job 只准交付一次 terminal 結果（Codex #8）。
       為什麼需要：supersede 時舊 job 會同時有兩個終結來源——宿主自己發的
       `superseded`，以及引擎頁被 cancel 後回來的 error（`error` 型別不在
       job-scoped 過濾清單內，因為那是「連 active 都還沒建立就失敗」的通道）。
       呼叫端（C-2 的上盤入口）看到同一個 job 終結兩次會很難寫對，所以在這裡收斂。
       只留最近 16 筆＝夠涵蓋任何合理的殘響延遲，又不會無限長大。 */
    std::deque<std::string> terminated;
    bool mark_terminal(const std::string& job_id)
    {
        if (job_id.empty()) return true;
        if (std::find(terminated.begin(), terminated.end(), job_id) != terminated.end()) {
            BOOST_LOG_TRIVIAL(info) << "PhotoTileEngineHost 忽略重複的 terminal 結果：" << job_id;
            return false;
        }
        terminated.push_back(job_id);
        while (terminated.size() > 16) terminated.pop_front();
        return true;
    }
    void deliver(const PhotoTileEngineResult& r)
    {
        if (!mark_terminal(r.job_id)) return;
        if (on_result) safe_call("result handler", [&] { on_result(r); });
    }
    /* 只有「目前 epoch 的 job」能改動狀態或交付結果。舊 job 遲到的失敗只通知、不清狀態。
       （Codex 阻斷 #3：舊 job 曾可清掉新 job 的 active state 或被當新結果交付） */
    void fail_job(const std::string& job_id, const std::string& code, const std::string& msg)
    {
        const bool is_active = !job_id.empty() && job_id == active_job;
        BOOST_LOG_TRIVIAL(warning) << "PhotoTileEngineHost job 失敗 " << job_id << "（active=" << active_job
                                   << "）" << code << " " << msg;
        PhotoTileEngineResult r;
        r.ok = false; r.job_id = job_id; r.error_code = code; r.error_message = msg;
        if (is_active) {
            busy = false; active_job.clear(); xfer = Transfer(); pending_valid = false;
        }
        deliver(r);
    }
    void fail_active_and_queued(const std::string& code, const std::string& msg)
    {
        if (!active_job.empty()) fail_job(active_job, code, msg);
        if (has_queued_request) {                       // 排隊中的 job 也要有交代（Codex #4）
            const std::string qid = queued_request.job_id;
            has_queued_request = false;
            PhotoTileEngineResult r;
            r.ok = false; r.job_id = qid; r.error_code = code; r.error_message = msg;
            deliver(r);
        }
    }

#ifdef _WIN32
    Microsoft::WRL::ComPtr<ICoreWebView2Environment> env;
    Microsoft::WRL::ComPtr<ICoreWebView2Controller>  controller;
    Microsoft::WRL::ComPtr<ICoreWebView2>            webview;
    EventRegistrationToken       token_message {};
    EventRegistrationToken       token_failed {};
    wxFrame*                     host_frame = nullptr;    // 建了但**永不 Show()**
    std::unique_ptr<wxTimer>     ready_timer;
    std::deque<std::string>      inject_queue;
    bool                         inject_pumping = false;

    void send_json(const std::string& json)
    {
        if (!webview || closing()) return;
        const double t0 = now_ms();
        const HRESULT hr = webview->PostWebMessageAsJson(utf8_to_wide(json).c_str());
        if (FAILED(hr)) {                               // Codex #2：HRESULT 不可忽略，否則 busy 永不結束
            status("post_failed", "送訊息給引擎失敗（HRESULT " + hex_hr(hr) + "）");
            fail_active_and_queued("internal", "與引擎的通訊中斷（HRESULT " + hex_hr(hr) + "）");
            return;
        }
        if (smoke_on)
            smoke.inject_dispatch_max_ms = (std::max)(smoke.inject_dispatch_max_ms, now_ms() - t0);
    }

    // 以下為生命週期與協定實作（全部是 Impl 的成員＝回呼不必捕捉 host 的 this）
    bool start_engine();
    void create_controller();
    void navigate_and_wait_ready();
    void handle_message_inner(const std::string& json);
    void pump_inject_queue();
    void on_process_failed(int kind);
    void try_rebuild(const std::string& why);
    bool generate(const PhotoTileEngineRequest& req);
    void cancel(const std::string& job_id);
    void shutdown();
#endif
};

// ===================== 對外薄殼 =====================
PhotoTileEngineHost::PhotoTileEngineHost() : p(std::make_shared<Impl>()) {}
PhotoTileEngineHost::~PhotoTileEngineHost() { shutdown(); }

void PhotoTileEngineHost::set_progress_handler(ProgressFn fn) { p->on_progress = std::move(fn); }
void PhotoTileEngineHost::set_result_handler(ResultFn fn)     { p->on_result   = std::move(fn); }
void PhotoTileEngineHost::set_status_handler(StatusFn fn)     { p->on_status   = std::move(fn); }
bool PhotoTileEngineHost::is_ready() const                    { return p->stage == Impl::Stage::Ready; }
bool PhotoTileEngineHost::is_busy() const                     { return p->busy; }
void PhotoTileEngineHost::test_break_engine_url(bool on) { p->test_break_engine_url = on; }

PhotoTileEngineDiag PhotoTileEngineHost::diagnostics() const
{
    PhotoTileEngineDiag d;
    d.stage         = Impl::stage_name(p->stage);
    d.rebuild_count = p->rebuild_count;
    d.busy          = p->busy;
    d.active_job    = p->active_job;
#ifdef _WIN32
    if (p->webview) {
        UINT32 pid = 0;
        if (SUCCEEDED(p->webview->get_BrowserProcessId(&pid))) d.browser_pid = (unsigned int) pid;
    }
#endif
    return d;
}

void PhotoTileEngineHost::enable_smoke_metrics(bool on)       { p->smoke_on = on; }
const PhotoTileEngineSmokeStats& PhotoTileEngineHost::smoke_stats() const { return p->smoke; }

void PhotoTileEngineHost::smoke_heartbeat_tick(double expected_interval_ms)
{
    const double t = now_ms();
    if (p->last_heartbeat_ms > 0) {
        const double drift = (t - p->last_heartbeat_ms) - expected_interval_ms;
        if (drift > 0) {
            p->heartbeat_drifts.push_back(drift);
            p->smoke.heartbeat_samples      = (int) p->heartbeat_drifts.size();
            p->smoke.heartbeat_drift_max_ms = (std::max)(p->smoke.heartbeat_drift_max_ms, drift);
            std::vector<double> sorted = p->heartbeat_drifts;
            std::sort(sorted.begin(), sorted.end());
            size_t idx = (size_t) (sorted.size() * 0.95);
            if (idx >= sorted.size()) idx = sorted.size() - 1;
            p->smoke.heartbeat_drift_p95_ms = sorted[idx];
        }
    }
    p->last_heartbeat_ms = t;
}

bool PhotoTileEngineHost::env_is_fresh(const std::string& result_env_json, const std::string& current_env_json)
{
    if (result_env_json.empty() || current_env_json.empty())
        return false;                       // 缺快照＝視為過期（不得預設放行）
    pt::ptree a, b;
    if (!json_from_string(result_env_json, a) || !json_from_string(current_env_json, b))
        return false;
    return ptree_equal(a, b);
}

#ifndef _WIN32
// ===================== 非 Windows：誠實不可用（C 案裁決 8） =====================
PhotoTileEngineHost::Availability PhotoTileEngineHost::check_runtime()
{
    Availability a;
    a.available = false;
    a.reason = "照片磚引擎目前僅支援 Windows（需 Microsoft Edge WebView2 執行環境）。"
               "請改用照片磚工作室產生 3MF 後匯入。";
    return a;
}
bool PhotoTileEngineHost::start()    { p->status("unavailable", check_runtime().reason); return false; }
void PhotoTileEngineHost::shutdown() { if (p) { p->stage = Impl::Stage::Closing; p->busy = false; } }
bool PhotoTileEngineHost::generate(const PhotoTileEngineRequest& req)
{
    p->fail_job(req.job_id, "engine_unavailable", check_runtime().reason);
    return false;
}
void PhotoTileEngineHost::cancel(const std::string&) {}

#else
// ===================== Windows：WebView2 隱形宿主 =====================
using Microsoft::WRL::Callback;
using Microsoft::WRL::ComPtr;
using Microsoft::WRL::Make;

namespace {

typedef HRESULT (STDMETHODCALLTYPE *PFN_CreateEnv)(PCWSTR, PCWSTR,
        ICoreWebView2EnvironmentOptions*, ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler*);
typedef HRESULT (STDMETHODCALLTYPE *PFN_GetVersion)(PCWSTR, LPWSTR*);

HMODULE loader_module()
{
    static HMODULE mod = ::LoadLibraryW(L"WebView2Loader.dll");
    return mod;
}
std::string engine_url()
{
    std::string url = "file://" + resources_dir() + "/web/phototile/engine.html";
    std::replace(url.begin(), url.end(), '\\', '/');
    return url;
}

/* noexcept 護欄（設計約束 A＋B 的合體）：
   非同步邊界只捕捉 weak_ptr；lock 不到（物件已死）或已 Closing 就安靜退場；
   任何例外一律在邊界收斂——**例外穿越 COM 回呼＝std::terminate＝app 猝死**。
   ⚠ COM 回呼本身必須是「具體簽章」的 lambda（WRL 無法推導可變參數泛型 lambda），
   所以護欄做成內層函式，由各回呼包住自己的主體。 */
// ⚠ ImplT 用型別參數：`Impl` 是 host 的 private 巢狀型別，匿名命名空間的自由函式
//    不得直接具名（會變成「找不到相符的多載」）。
template<class ImplT, class Fn>
void run_guarded(const std::weak_ptr<ImplT>& w, const char* what, Fn fn)
{
    auto impl = w.lock();
    if (!impl || impl->closing())
        return;
    try { fn(impl); }
    catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(error) << "PhotoTileEngineHost: " << what << " 例外（已攔下）：" << e.what();
    } catch (...) {
        BOOST_LOG_TRIVIAL(error) << "PhotoTileEngineHost: " << what << " 未知例外（已攔下）";
    }
}

} // namespace

PhotoTileEngineHost::Availability PhotoTileEngineHost::check_runtime()
{
    Availability a;
    HMODULE mod = loader_module();
    if (!mod) {
        a.reason = "找不到 WebView2Loader.dll（安裝可能不完整）。請重新安裝 PING Slicer。";
        return a;
    }
    auto get_version = (PFN_GetVersion) ::GetProcAddress(mod, "GetAvailableCoreWebView2BrowserVersionString");
    if (!get_version) {
        a.reason = "WebView2Loader.dll 缺少版本查詢介面。請重新安裝 PING Slicer。";
        return a;
    }
    LPWSTR version = nullptr;
    const HRESULT hr = get_version(nullptr, &version);
    if (FAILED(hr) || version == nullptr) {
        a.reason = "本機未安裝 Microsoft Edge WebView2 執行環境，照片磚引擎無法啟動。"
                   "請先安裝 WebView2 Runtime（或向 PING 索取安裝檔）後再試。";
        return a;
    }
    a.available = true;
    a.runtime_version = wide_to_utf8(version);
    ::CoTaskMemFree(version);
    return a;
}

bool PhotoTileEngineHost::Impl::start_engine()
{
    // 狀態機（設計約束 D）：任何時刻只有一條建立路徑。Rebuilding 也算建立中，
    // 不會被 generate() 觸發第二次建環境（Codex 阻斷 #4 的雙重建立競賽）。
    if (stage == Stage::Ready || building())
        return true;
    if (stage == Stage::Closing)
        return false;

    const Availability avail = PhotoTileEngineHost::check_runtime();
    if (!avail.available) { set_stage(Stage::Unavailable); status("unavailable", avail.reason); return false; }

    auto create_env = (PFN_CreateEnv) ::GetProcAddress(loader_module(), "CreateCoreWebView2EnvironmentWithOptions");
    if (!create_env) {
        set_stage(Stage::Unavailable);
        status("unavailable", "WebView2Loader.dll 缺少建立介面。請重新安裝 PING Slicer。");
        return false;
    }
    if (!host_frame) {
        // 隱藏宿主視窗：**永不 Show()**。WebView2 controller 需要真 HWND。
        host_frame = new wxFrame(nullptr, wxID_ANY, "PING PhotoTile Engine", wxDefaultPosition,
                                 wxSize(1, 1), wxFRAME_TOOL_WINDOW | wxFRAME_NO_TASKBAR);
    }
    // 保險絲：頁面端已守零計時器紀律，這裡再關掉背景計時器節流（C-0 §3.2 第二道防線）
    auto options = Make<CoreWebView2EnvironmentOptions>();
    options->put_AdditionalBrowserArguments(L"--disable-background-timer-throttling");

    const std::wstring user_data = utf8_to_wide(data_dir() + "/webview2_phototile");
    set_stage(Stage::CreatingEnv);
    status("starting", "建立隱形引擎宿主…（runtime " + avail.runtime_version + "）");

    std::weak_ptr<Impl> w = shared_from_this();
    const HRESULT hr = create_env(nullptr, user_data.c_str(), options.Get(),
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [w](HRESULT result, ICoreWebView2Environment* environment) -> HRESULT {
                run_guarded(w, "environment 完成回呼", [&](std::shared_ptr<Impl> impl) {
                    if (FAILED(result) || environment == nullptr) {
                        impl->set_stage(Stage::Unavailable);
                        impl->status("unavailable", "WebView2 環境建立失敗（HRESULT " + hex_hr(result) + "）。");
                        impl->fail_active_and_queued("engine_unavailable", "引擎環境建立失敗。");
                        return;
                    }
                    impl->env = environment;
                    impl->create_controller();
                });
                return S_OK;
            }).Get());

    if (FAILED(hr)) {
        set_stage(Stage::Unavailable);
        status("unavailable", "WebView2 環境建立呼叫失敗（HRESULT " + hex_hr(hr) + "）。");
        return false;
    }
    return true;
}

void PhotoTileEngineHost::Impl::create_controller()
{
    if (closing() || !env || !host_frame) return;
    set_stage(Stage::CreatingController);

    std::weak_ptr<Impl> w = shared_from_this();
    const HRESULT hr = env->CreateCoreWebView2Controller((HWND) host_frame->GetHandle(),
        Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
            [w](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
              run_guarded(w, "controller 完成回呼", [&](std::shared_ptr<Impl> impl) {
                    if (FAILED(result) || controller == nullptr) {
                        // controller 失敗也要計入重建次數，否則 cap 形同虛設（Codex #4）。
                        // 走與崩潰／逾時同一支 try_rebuild＝保險絲只有一個實作（2026-08-01 統一）
                        impl->try_rebuild("controller 建立失敗（HRESULT " + hex_hr(result) + "）");
                        return;
                    }
                    impl->controller = controller;
                    impl->controller->put_IsVisible(FALSE);          // 隱形：連 1x1 都不畫
                    const HRESULT hr_core = impl->controller->get_CoreWebView2(&impl->webview);
                    if (FAILED(hr_core) || !impl->webview) {
                        impl->set_stage(Stage::Unavailable);
                        impl->status("unavailable", "取得 WebView2 核心介面失敗（HRESULT " + hex_hr(hr_core) + "）。");
                        impl->fail_active_and_queued("engine_unavailable", "引擎核心介面取得失敗。");
                        return;
                    }

                    std::weak_ptr<Impl> w2 = impl;
                    impl->webview->add_WebMessageReceived(
                        Callback<ICoreWebView2WebMessageReceivedEventHandler>(
                            [w2](ICoreWebView2*, ICoreWebView2WebMessageReceivedEventArgs* args) -> HRESULT {
                                run_guarded(w2, "WebMessageReceived", [&](std::shared_ptr<Impl> im) {
                                    LPWSTR raw = nullptr;
                                    // ⚠ UTF 轉換也必須在護欄內（Codex #2 指出原本在外面）
                                    if (args && SUCCEEDED(args->TryGetWebMessageAsString(&raw)) && raw) {
                                        const std::string json = wide_to_utf8(raw);
                                        ::CoTaskMemFree(raw);
                                        im->handle_message_inner(json);
                                    }
                                });
                                return S_OK;
                            }).Get(), &impl->token_message);

                    impl->webview->add_ProcessFailed(
                        Callback<ICoreWebView2ProcessFailedEventHandler>(
                            [w2](ICoreWebView2*, ICoreWebView2ProcessFailedEventArgs* args) -> HRESULT {
                                run_guarded(w2, "ProcessFailed", [&](std::shared_ptr<Impl> im) {
                                    COREWEBVIEW2_PROCESS_FAILED_KIND kind =
                                        COREWEBVIEW2_PROCESS_FAILED_KIND_BROWSER_PROCESS_EXITED;
                                    if (args) args->get_ProcessFailedKind(&kind);
                                    im->on_process_failed((int) kind);
                                });
                                return S_OK;
                            }).Get(), &impl->token_failed);

                    impl->navigate_and_wait_ready();
              });
              return S_OK;
            }).Get());

    if (FAILED(hr)) {
        set_stage(Stage::Unavailable);
        status("unavailable", "WebView2 controller 建立呼叫失敗（HRESULT " + hex_hr(hr) + "）。");
        fail_active_and_queued("engine_unavailable", "引擎建立失敗。");
    }
}

void PhotoTileEngineHost::Impl::navigate_and_wait_ready()
{
    if (closing() || !webview) return;
    set_stage(Stage::Navigating);

    // ready 逾時＝誠實失敗；只等 ready 不綁 NavigationCompleted（C-0 實測 ready 可能先到）
    if (!ready_timer) {
        ready_timer.reset(new wxTimer(host_frame));
        std::weak_ptr<Impl> w = shared_from_this();
        host_frame->Bind(wxEVT_TIMER, [w](wxTimerEvent&) {
            auto impl = w.lock();
            if (!impl || impl->closing() || impl->stage == Stage::Ready) return;
            Impl::safe_call("ready 逾時處理", [&] {
                /* 【2026-08-01 修】原本 ready 逾時直接判**永久**不可用——一次啟動慢
                   （機器忙、防毒掃描、剛從睡眠醒來）就讓照片磚整個 session 廢掉，而且
                   完全繞過重建狀態機與 REBUILD_CAP。閘門 G 實測抓到：連殺引擎時真正
                   截停的是這條路，不是 cap ⇒ cap 根本不是那個保險絲。
                   改成與行程崩潰走同一條路：算一次重建、受同一個 cap 節制。 */
                impl->fail_active_and_queued("engine_timeout", "引擎啟動逾時。");
                impl->try_rebuild("引擎頁未在 " + std::to_string(READY_TIMEOUT_MS / 1000) +
                                  " 秒內回報就緒（ready 握手逾時）");
            });
        });
    }
    ready_timer->StartOnce(READY_TIMEOUT_MS);

    /* 【僅測試用】把引擎頁指到一個不存在的位址 ⇒ 頁面永遠不會回報 ready ⇒ 每次都走 ready 逾時。
       用途＝**決定性地**驗證 REBUILD_CAP 真的會截停（閘門 H）。
       為什麼不用「連殺行程」驗：實測（0801 閘門 G）引擎每次都在 ~380ms 內復原、
       計數在穩定就緒時歸零，殺得再快也只是在賽跑，證不出保險絲——那是量測方法的問題，
       不是保險絲的問題。這裡改成讓每次重建都必定失敗，cap 才是唯一能停下來的東西。 */
    const std::string url = test_break_engine_url
        ? std::string("file:///%%%__phototile_engine_missing__%%%.html")
        : engine_url();
    const HRESULT hr = webview->Navigate(utf8_to_wide(url).c_str());
    if (FAILED(hr)) {
        set_stage(Stage::Unavailable);
        status("unavailable", "載入引擎頁失敗（HRESULT " + hex_hr(hr) + "）。");
        fail_active_and_queued("engine_unavailable", "引擎頁載入失敗。");
    }
}

/* 依 failure kind 分流（Codex #4）：
   - browser/render process exited：真的要重建
   - render unresponsive：只記錄（WebView2 會自行恢復；重複發事件不該吃掉重建額度）
   - GPU／utility／其他：記錄不重建（Chromium 自行復原） */
void PhotoTileEngineHost::Impl::on_process_failed(int kind)
{
    if (closing()) return;
    const bool fatal = (kind == COREWEBVIEW2_PROCESS_FAILED_KIND_BROWSER_PROCESS_EXITED ||
                        kind == COREWEBVIEW2_PROCESS_FAILED_KIND_RENDER_PROCESS_EXITED);
    if (!fatal) {
        status("process_warning", "引擎子行程異常（kind=" + std::to_string(kind) + "），不重建、續觀察。");
        return;
    }
    /* 【2026-08-01 修】同一次崩潰會連發多則 ProcessFailed（閘門 F 實測：一次殺掉
       5 個子行程 ⇒ 收到 3 則 fatal，rebuild_count 一口氣從 0 跳到 3）。
       cap 要數的是「崩潰事件」不是「通知則數」，否則**單一次崩潰就把保險絲燒掉**。
       已經在重建中就只記錄不計數——在飛的那條重建路徑會自己收斂或逾時。 */
    if (building()) {
        // 建立／重建**在飛的整段**都算同一次崩潰的餘波（不只 Rebuilding 那一瞬間）。
        // 這段期間真的又壞掉，由 ready 逾時當後手接住——它現在也走 try_rebuild、同受 cap 節制。
        status("process_warning", "建立／重建進行中又收到行程失敗通知（kind=" + std::to_string(kind) +
                                  "），視為同一次崩潰、不重複計數。");
        return;
    }
    fail_active_and_queued("engine_crashed", "引擎行程中止。");
    try_rebuild("引擎行程中止（kind=" + std::to_string(kind) + "）");
}

/* 所有「引擎壞了、想再站起來」的路徑唯一入口（行程崩潰／ready 逾時）。
   ⚠ 保險絲的語意就寫在這裡：連續失敗 REBUILD_CAP 次就停手、不再無限重試；
   計數只在**穩定就緒**時歸零（handle_message_inner 的 ready 分支）。
   日後任何新的失敗路徑都要走這支，不要再自己 set_stage(Unavailable) 繞過去。 */
void PhotoTileEngineHost::Impl::try_rebuild(const std::string& why)
{
    if (closing()) return;
    if (rebuild_count >= REBUILD_CAP) {
        set_stage(Stage::Unavailable);
        status("unavailable", "引擎連續重建 " + std::to_string(REBUILD_CAP) +
                              " 次仍失敗，已停止重試。請重開 PING Slicer。");
        fail_active_and_queued("engine_unavailable", "引擎無法建立。");
        return;
    }
    ++rebuild_count;
    set_stage(Stage::Rebuilding);
    status("rebuilding", why + "，第 " + std::to_string(rebuild_count) + " 次重建。");
    if (controller) { controller->Close(); controller.Reset(); }
    webview.Reset();
    create_controller();
}

void PhotoTileEngineHost::Impl::handle_message_inner(const std::string& json)
{
    const double t0 = now_ms();
    pt::ptree m;
    if (!json_from_string(json, m)) return;
    const int         v    = m.get<int>("v", 0);
    const std::string type = m.get<std::string>("type", "");
    const std::string job  = m.get<std::string>("jobId", "");

    if (v != PROTOCOL_VERSION) {
        fail_job(job, "protocol_bad_version", "引擎頁協定版本不符（收到 " + std::to_string(v) + "）。");
        return;
    }

    // ready 以外的 job 訊息，一律只接受目前 active job（設計約束 C）
    const bool job_scoped = (type == "progress" || type == "result" || type == "begin" ||
                             type == "chunk"    || type == "end");
    if (job_scoped && job != active_job) {
        BOOST_LOG_TRIVIAL(warning) << "PhotoTileEngineHost 丟棄過期 job 的訊息：" << type << " " << job
                                   << "（active=" << active_job << "）";
        return;                                  // 舊 job 的殘響：丟棄，不得改動狀態
    }

    if (type == "ready") {
        if (ready_timer) ready_timer->Stop();
        set_stage(Stage::Ready);
        rebuild_count = 0;                       // 穩定就緒＝連續失敗數歸零（Codex #4）
        status("ready", "引擎就緒（engine " + m.get<std::string>("engine", "?") +
                        "／protocol " + std::to_string(m.get<int>("protocol", 0)) + "）");
        if (has_queued_request) {
            has_queued_request = false;
            PhotoTileEngineRequest q = queued_request;
            generate(q);
        }
    }
    else if (type == "progress") {
        if (on_progress)
            safe_call("progress handler", [&] {
                on_progress(job, m.get<std::string>("stage", ""), m.get<std::string>("stageLabel", ""),
                            m.get<double>("pct", 0.0));
            });
    }
    else if (type == "result") {
        if (!m.get<bool>("ok", false)) {
            fail_job(job, m.get<std::string>("error.code", "internal"),
                          m.get<std::string>("error.message", "引擎回報失敗"));
            return;
        }
        pending = PhotoTileEngineResult();
        pending.job_id  = job;
        pending.sha256  = m.get<std::string>("sha256", "");
        pending.wall_ms = m.get<int>("wallMs", 0);
        pending.result_json = json;
        {   // env 可能是 null（純量節點），不可拿去 write_json
            auto env_node = m.get_child_optional("env");
            if (env_node && !env_node->empty()) pending.env_json = ptree_to_json(*env_node);
        }
        pending_valid = true;
    }
    else if (type == "begin") {
        xfer = Transfer();
        xfer.active = true;
        xfer.job_id = job;
        xfer.size   = m.get<size_t>("size", 0);
        xfer.chunks = m.get<size_t>("chunks", 0);
        xfer.sha256 = m.get<std::string>("sha256", "");
        if (xfer.size == 0 || xfer.chunks == 0) {
            fail_job(job, "protocol_bad_message", "begin 缺少 size／chunks，無法驗收。");
            return;
        }
        xfer.bytes.reserve(xfer.size);
    }
    else if (type == "chunk") {
        if (!xfer.active) { fail_job(job, "protocol_chunk_order", "chunk 早於 begin。"); return; }
        const size_t index = m.get<size_t>("index", (size_t) -1);
        if (index != xfer.received) {                                  // ①連號
            fail_job(job, "protocol_chunk_order",
                     "分塊序號不連續（期望 " + std::to_string(xfer.received) + "、收到 " + std::to_string(index) + "）。");
            return;
        }
        auto declared_opt = m.get_optional<size_t>("length");
        if (!declared_opt) {                                           // 長度必填（Codex #5：原本缺就跳過檢查）
            fail_job(job, "protocol_length_mismatch", "分塊缺少 length 欄位，無法驗收。");
            return;
        }
        const wxMemoryBuffer buf = wxBase64Decode(m.get<std::string>("base64", ""));
        if (buf.GetDataLen() != *declared_opt) {                       // ③長度
            fail_job(job, "protocol_length_mismatch",
                     "分塊長度不符（宣告 " + std::to_string(*declared_opt) +
                     "、實得 " + std::to_string(buf.GetDataLen()) + "）。");
            return;
        }
        if (xfer.bytes.size() + buf.GetDataLen() > xfer.size) {        // 溢出上限也要擋
            fail_job(job, "protocol_length_mismatch", "分塊總長超過 begin 宣告的大小。");
            return;
        }
        const unsigned char* data = (const unsigned char*) buf.GetData();
        xfer.bytes.insert(xfer.bytes.end(), data, data + buf.GetDataLen());
        ++xfer.received;
        if (smoke_on) smoke.chunks_received = (int) xfer.received;
    }
    else if (type == "end") {
        if (!xfer.active) { fail_job(job, "protocol_bad_message", "end 早於 begin。"); return; }
        // end 自報的塊數／大小必須與 begin 一致（Codex #5：原本完全沒檢查）
        // 【二輪 I14】而且**兩欄必填**：optional 讀取＝整欄省略照樣 success，
        // 一輪處置表寫「必須一致」其實只擋了「有值且不同」——省略比說謊更容易。
        auto end_chunks = m.get_optional<size_t>("chunks");
        auto end_size   = m.get_optional<size_t>("size");
        if (!end_chunks) { fail_job(job, "protocol_bad_message", "end 缺 chunks 欄位（必填）。"); return; }
        if (!end_size)   { fail_job(job, "protocol_bad_message", "end 缺 size 欄位（必填）。");   return; }
        if (end_chunks && *end_chunks != xfer.chunks) {
            fail_job(job, "protocol_chunk_count",
                     "end 宣告塊數與 begin 不符（begin " + std::to_string(xfer.chunks) +
                     "、end " + std::to_string(*end_chunks) + "）。");
            return;
        }
        if (end_size && *end_size != xfer.size) {
            fail_job(job, "protocol_length_mismatch",
                     "end 宣告大小與 begin 不符（begin " + std::to_string(xfer.size) +
                     "、end " + std::to_string(*end_size) + "）。");
            return;
        }
        if (xfer.received != xfer.chunks) {                            // ②塊數
            fail_job(job, "protocol_chunk_count",
                     "塊數不符（宣告 " + std::to_string(xfer.chunks) + "、實收 " + std::to_string(xfer.received) + "）。");
            return;
        }
        if (xfer.bytes.size() != xfer.size) {                          // ③總長度
            fail_job(job, "protocol_length_mismatch",
                     "總長度不符（宣告 " + std::to_string(xfer.size) + "、實得 " + std::to_string(xfer.bytes.size()) + "）。");
            return;
        }
        const std::string expect = m.get<std::string>("sha256", xfer.sha256);
        const std::string got    = sha256_hex(xfer.bytes.data(), xfer.bytes.size());
        if (expect.empty()) {                                          // ④SHA-256：不得有空門
            fail_job(job, "protocol_sha_mismatch", "引擎未提供 SHA-256，無法驗收，已丟棄整份 3MF。");
            return;
        }
        if (expect != got) {
            fail_job(job, "protocol_sha_mismatch", "SHA-256 不符，已丟棄整份 3MF。");
            return;
        }
        if (!pending_valid || pending.job_id != job) {
            fail_job(job, "protocol_bad_message", "收到 3MF 但沒有對應的 result 中繼資料。");
            return;
        }
        PhotoTileEngineResult r = pending;
        r.ok       = true;
        r.three_mf = std::move(xfer.bytes);
        r.sha256   = got;
        xfer = Transfer();
        pending_valid = false;
        busy = false;
        active_job.clear();
        deliver(r);
    }
    else if (type == "superseded") {
        // 兩個 jobId 都寫進 detail：閘門要能斷言「頁面那條 supersede 分支真的被命中」，
        // 而不是只看到一句人話（Codex #8）。格式固定＝ old → by，勿改。
        status("superseded", job + " → " + m.get<std::string>("by", ""));
    }
    else if (type == "error") {
        fail_job(job, m.get<std::string>("code", "internal"), m.get<std::string>("message", ""));
    }
    else if (type == "imageAck") {
        status("imageAck", "影像注入完成（" + std::to_string(m.get<size_t>("chars", 0)) + " 字元）。");
    }

    if (smoke_on)
        smoke.message_handle_max_ms = (std::max)(smoke.message_handle_max_ms, now_ms() - t0);
}

std::string build_generate_command_impl(const PhotoTileEngineRequest& req)
{
    std::string r = "{" + jkv("jobId", req.job_id) + "," + jkv("mode", req.mode) + "," +
                    jkn("nozzle", req.nozzle) + "," +
                    "\"size\":{" + jkn("widthMm", req.width_mm) + "," + jkn("heightMm", req.height_mm) + "," +
                                   jkn("thickMm", req.thick_mm) + "}," +
                    jkn("klevels", req.klevels) + "," + jkn("noiseMm", req.noise_mm) + "," +
                    "\"pillar\":{" + jkb("enabled", req.pillar) + "," + jkn("xyMm", req.pillar_xy_mm) + "}," +
                    "\"seam\":{" + jkb("teeth", req.teeth) + "," + jkb("p2aBlock", req.p2a_block) + "}";
    if (req.grid_max > 0 || req.max_decoded_pixels > 0) {
        r += ",\"limits\":{";
        bool first = true;
        if (req.grid_max > 0)           { r += jkn("gridMax", req.grid_max); first = false; }
        if (req.max_decoded_pixels > 0) { if (!first) r += ","; r += jkn("maxDecodedPixels", (double) req.max_decoded_pixels); }
        r += "}";
    }
    /* C-2：使用者挑的料色。**只在非空時寫入** ⇒ 不帶 slots 的路徑（C-1 閘門、黃金 12 案）
       產生的請求字串與 C-1 完全同字，位元組基準不受影響。 */
    if (!req.slots_json.empty())
        r += ",\"slots\":" + req.slots_json;
    if (req.want_metadata)
        r += ",\"metadata\":{" + jkv("groupUuid", req.group_uuid) + "," +
             jkb("embedSource", req.embed_source) + "," + jkv("createdBy", "PING-Slicer") + "}";
    if (!req.env_json.empty())
        r += ",\"env\":" + req.env_json;
    if (!req.fault_inject.empty())            // 測試用故障注入（產品路徑一律空）
        r += "," + jkv("faultInject", req.fault_inject);
    r += "}";
    return "{" + jkn("v", PROTOCOL_VERSION) + "," + jkv("cmd", "generate") + "," +
           jkv("jobId", req.job_id) + ",\"request\":" + r + "}";
}

bool PhotoTileEngineHost::Impl::generate(const PhotoTileEngineRequest& req)
{
    if (closing()) return false;
    if (stage != Stage::Ready) {
        // 建立／重建中：排隊。被覆寫的排隊 job 要有交代（Codex #4）
        if (has_queued_request && queued_request.job_id != req.job_id) {
            PhotoTileEngineResult r;
            r.ok = false; r.job_id = queued_request.job_id; r.error_code = "cancelled";
            r.error_message = "已被更新的請求取代（引擎尚未就緒）。";
            deliver(r);
        }
        queued_request     = req;
        has_queued_request = true;
        return start_engine();
    }
    /* supersede（Codex #8）：舊 job **必須拿到 terminal 結果**。
       原本只送 cancel 給引擎頁、等頁面回 cancelled——但那個回應的 jobId 已經不是
       active_job 了，會被 epoch 過濾器丟掉 ⇒ 呼叫端手上留下一個永遠不會結束的 job
       （2026-08-01 的活體報告因此拿到 oldJobReturnedSuccess:false 的**空值假綠燈**）。
       現在由宿主自己終結，不依賴頁面的回應。 */
    std::string superseded_job;
    if (busy && !active_job.empty() && active_job != req.job_id) {
        superseded_job = active_job;
        if (!req.test_page_supersede)
            cancel(superseded_job);          // 產品路徑：宿主先收斂（比等頁面快）
        // test_page_supersede＝故意不預先取消，讓引擎頁自己收到第二個 generate、
        // 走它的 supersede 分支（那條分支原本從沒被命中過）。
    }

    ++epoch;
    const unsigned long long my_epoch = epoch;
    busy       = true;
    active_job = req.job_id;
    xfer       = Transfer();
    pending_valid = false;

    // 影像讀檔＋base64＝背景執行緒（C-0 §3.3 ④）。整段包在 try/catch 內：
    // 例外逃出 thread function＝std::terminate（設計約束 B）。
    const std::string path   = req.image_path;
    const std::string job_id = req.job_id;
    PhotoTileEngineRequest req_copy = req;
    std::weak_ptr<Impl> w = shared_from_this();

    std::thread([w, path, job_id, req_copy, my_epoch]() {
        std::string error;
        std::deque<std::string> queue;
        double encode_ms = 0;
        try {
            const double t0 = now_ms();
            boost::nowide::ifstream input(path, std::ios::binary | std::ios::ate);
            if (!input) error = "圖片無法讀取，請重新選擇檔案。";
            std::vector<unsigned char> bytes;
            if (error.empty()) {
                const std::streamoff size = input.tellg();
                if (size <= 0 || size > MAX_IMAGE_BYTES)
                    error = "圖片檔案過大（上限 64 MB），請先縮小圖片再試。";
                else {
                    input.seekg(0, std::ios::beg);
                    bytes.resize((size_t) size);
                    if (!input.read((char*) bytes.data(), size))
                        error = "圖片讀取失敗，請重新選擇檔案。";
                }
            }
            if (error.empty()) {
                const std::string b64 = wxBase64Encode(bytes.data(), bytes.size()).ToStdString();
                encode_ms = now_ms() - t0;

                std::string ext = path.substr(path.find_last_of('.') + 1);
                std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
                std::string mime = "image/png";
                if (ext == "jpg" || ext == "jpeg") mime = "image/jpeg";
                else if (ext == "webp")            mime = "image/webp";
                else if (ext == "bmp")             mime = "image/bmp";

                const size_t chunks = (b64.size() + INJECT_CHUNK_CHARS - 1) / INJECT_CHUNK_CHARS;
                queue.push_back("{" + jkn("v", PROTOCOL_VERSION) + "," + jkv("cmd", "imageBegin") + "," +
                                jkv("jobId", job_id) + "," + jkv("mime", mime) + "," +
                                jkn("totalChars", (double) b64.size()) + "," + jkn("chunks", (double) chunks) + "}");
                for (size_t i = 0; i < chunks; ++i)
                    queue.push_back("{" + jkn("v", PROTOCOL_VERSION) + "," + jkv("cmd", "imageChunk") + "," +
                                    jkv("jobId", job_id) + "," + jkn("index", (double) i) + "," +
                                    jkv("base64", b64.substr(i * INJECT_CHUNK_CHARS,
                                        (std::min)(INJECT_CHUNK_CHARS, b64.size() - i * INJECT_CHUNK_CHARS))) + "}");
                queue.push_back("{" + jkn("v", PROTOCOL_VERSION) + "," + jkv("cmd", "imageEnd") + "," +
                                jkv("jobId", job_id) + "," + jkn("totalChars", (double) b64.size()) + "," +
                                jkn("chunks", (double) chunks) + "}");
                queue.push_back(build_generate_command_impl(req_copy));
            }
        } catch (const std::exception& e) {
            error = std::string("影像處理失敗：") + e.what();
        } catch (...) {
            error = "影像處理發生未知錯誤。";
        }

        // 回 UI 執行緒：weak 鎖不到（宿主已死）就安靜退場；epoch 對不上＝這個 job 已過期
        wxTheApp->CallAfter([w, job_id, my_epoch, error, queue, encode_ms]() mutable {
            auto impl = w.lock();
            if (!impl || impl->closing()) return;
            Impl::safe_call("影像注入回主緒", [&] {
                if (my_epoch != impl->epoch) {
                    BOOST_LOG_TRIVIAL(info) << "PhotoTileEngineHost 丟棄過期 job 的注入資料：" << job_id;
                    return;
                }
                if (!error.empty()) { impl->fail_job(job_id, "bad_image", error); return; }
                if (impl->smoke_on) impl->smoke.inject_encode_ms = encode_ms;
                for (auto& msg : queue) impl->inject_queue.push_back(std::move(msg));
                impl->pump_inject_queue();
            });
        });
    }).detach();

    /* 舊 job 的 terminal 結果排在**新 job 狀態全部就位之後**才發：
       同步 deliver 會讓呼叫端在 generate() 內部重入（handler 可能又呼叫 generate），
       CallAfter 把它推到下一輪事件圈，順序仍保證「舊的先終結、新的後回來」
       （新 job 至少要等影像編碼＋注入，不可能更早）。 */
    if (!superseded_job.empty()) {
        const std::string by = req.job_id;
        wxTheApp->CallAfter([w, superseded_job, by]() {
            auto impl = w.lock();
            if (!impl || impl->closing()) return;
            Impl::safe_call("supersede 終結", [&] {
                PhotoTileEngineResult r;
                r.ok = false; r.job_id = superseded_job; r.error_code = "superseded";
                r.error_message = "作業已被新的請求（" + by + "）取代。";
                impl->deliver(r);
            });
        });
    }

    return true;
}

void PhotoTileEngineHost::Impl::pump_inject_queue()
{
    if (closing() || inject_queue.empty()) { inject_pumping = false; return; }
    inject_pumping = true;
    for (size_t i = 0; i < INJECT_BATCH && !inject_queue.empty(); ++i) {
        send_json(inject_queue.front());
        inject_queue.pop_front();
    }
    if (!inject_queue.empty()) {
        std::weak_ptr<Impl> w = shared_from_this();
        wxTheApp->CallAfter([w]() { run_guarded(w, "注入分批派發", [](std::shared_ptr<Impl> impl) { impl->pump_inject_queue(); }); });
    } else {
        inject_pumping = false;
    }
}

void PhotoTileEngineHost::Impl::cancel(const std::string& job_id)
{
    if (!webview || closing()) return;
    send_json("{" + jkn("v", PROTOCOL_VERSION) + "," + jkv("cmd", "cancel") + "," + jkv("jobId", job_id) + "}");
}

void PhotoTileEngineHost::Impl::shutdown()
{
    // 先標 Closing：所有晚到的回呼（COM／thread／CallAfter／timer）看到就安靜退場，
    // 不會再碰任何已拆掉的東西（設計約束 A）。
    set_stage(Stage::Closing);
    busy = false;
    has_queued_request = false;
    inject_queue.clear();
    if (ready_timer) { ready_timer->Stop(); ready_timer.reset(); }
    if (webview) {
        webview->remove_WebMessageReceived(token_message);
        webview->remove_ProcessFailed(token_failed);
    }
    if (controller) { controller->Close(); controller.Reset(); }
    webview.Reset();
    env.Reset();
    if (host_frame) { host_frame->Destroy(); host_frame = nullptr; }
}

bool PhotoTileEngineHost::start()                                  { return p->start_engine(); }
void PhotoTileEngineHost::shutdown()                               { if (p) p->shutdown(); }
bool PhotoTileEngineHost::generate(const PhotoTileEngineRequest& r){ return p->generate(r); }
void PhotoTileEngineHost::cancel(const std::string& job_id)        { p->cancel(job_id); }

#endif // _WIN32

}} // namespace Slic3r::GUI
