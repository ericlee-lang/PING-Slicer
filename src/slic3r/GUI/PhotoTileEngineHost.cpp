// 照片磚隱形引擎宿主（C-1）——實作。規格＝PhotoTileEngineHost.hpp 檔頭與
// tools/ping/phototile_protocol.md。Windows 走 WebView2 COM；其餘平台誠實不可用。
//
// 四項驗證（連號／塊數／總長度／SHA-256）與 engine_protocol.js 的 createAssembler
// 逐條對應；改一邊就要改另一邊＋補測（協定 §9）。

#include "PhotoTileEngineHost.hpp"

#include "GUI_App.hpp"
#include "libslic3r/Utils.hpp"

#include <algorithm>
#include <chrono>
#include <deque>
#include <fstream>
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

constexpr int    PROTOCOL_VERSION   = 1;        // 與 engine_protocol.js 同步
constexpr size_t INJECT_CHUNK_CHARS = 192 * 1024;
constexpr size_t INJECT_BATCH       = 8;        // 每次 CallAfter 派發幾塊＝攤平 UI 執行緒成本
constexpr int    READY_TIMEOUT_MS   = 15000;    // C-0 §3.2 noready 負測即此值
constexpr int    REBUILD_CAP        = 3;        // C-0 §3.2 crashx4 負測即此上限
constexpr long long MAX_IMAGE_BYTES = 64LL * 1024LL * 1024LL;   // 同 WebViewDialog.cpp:301

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

std::string ptree_to_json(const pt::ptree& tree)
{
    std::ostringstream ss;
    pt::write_json(ss, tree, false);
    std::string s = ss.str();
    s.erase(std::remove(s.begin(), s.end(), '\n'), s.end());
    return s;
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

// 逐鍵嚴格相等——鏡像 engine_protocol.js 的 envEqual（含「鍵數不同即不等」）
bool ptree_equal(const pt::ptree& a, const pt::ptree& b)
{
    if (a.size() != b.size())
        return false;
    if (a.empty())
        return a.data() == b.data();
    auto ia = a.begin();
    auto ib = b.begin();
    for (; ia != a.end() && ib != b.end(); ++ia, ++ib) {
        if (ia->first != ib->first)   return false;
        if (!ptree_equal(ia->second, ib->second)) return false;
    }
    return true;
}

double now_ms()
{
    using namespace std::chrono;
    return duration_cast<duration<double, std::milli>>(steady_clock::now().time_since_epoch()).count();
}

} // namespace

// ===================== 共用狀態 =====================
struct PhotoTileEngineHost::Impl
{
    PhotoTileEngineHost::ProgressFn on_progress;
    PhotoTileEngineHost::ResultFn   on_result;
    PhotoTileEngineHost::StatusFn   on_status;

    bool        ready = false;
    bool        busy  = false;
    bool        creating = false;
    std::string active_job;
    int         rebuild_count = 0;

    struct Transfer {
        bool        active = false;
        std::string job_id;
        size_t      size = 0, chunks = 0, received = 0;
        std::string sha256;
        std::vector<unsigned char> bytes;
    } xfer;

    PhotoTileEngineResult     pending;      // result 訊息先到、bytes 隨後
    bool                      pending_valid = false;

    PhotoTileEngineSmokeStats smoke;
    bool                      smoke_on = false;
    double                    last_heartbeat_ms = 0;
    std::vector<double>       heartbeat_drifts;

    void status(const std::string& s, const std::string& detail)
    {
        BOOST_LOG_TRIVIAL(info) << "PhotoTileEngineHost [" << s << "] " << detail;
        if (on_status) on_status(s, detail);
    }
    void fail_job(const std::string& job_id, const std::string& code, const std::string& msg)
    {
        BOOST_LOG_TRIVIAL(warning) << "PhotoTileEngineHost job 失敗 " << job_id << " " << code << " " << msg;
        PhotoTileEngineResult r;
        r.ok = false; r.job_id = job_id; r.error_code = code; r.error_message = msg;
        busy = false; active_job.clear(); xfer = Transfer(); pending_valid = false;
        if (on_result) on_result(r);
    }

#ifdef _WIN32
    Microsoft::WRL::ComPtr<ICoreWebView2Environment> env;
    Microsoft::WRL::ComPtr<ICoreWebView2Controller>  controller;
    Microsoft::WRL::ComPtr<ICoreWebView2>            webview;
    wxFrame*                     host_frame = nullptr;    // 建了但**永不 Show()**
    std::unique_ptr<wxTimer>     ready_timer;
    std::deque<std::string>      inject_queue;            // 待派發的注入訊息
    bool                         inject_pumping = false;
    PhotoTileEngineRequest       queued_request;          // ready 之前先收著
    bool                         has_queued_request = false;

    void send_json(const std::string& json)
    {
        if (!webview) return;
        const double t0 = now_ms();
        webview->PostWebMessageAsJson(std::wstring(json.begin(), json.end()).c_str());
        if (smoke_on)
            smoke.inject_dispatch_max_ms = (std::max)(smoke.inject_dispatch_max_ms, now_ms() - t0);
    }
#endif
};

PhotoTileEngineHost::PhotoTileEngineHost() : p(new Impl()) {}
PhotoTileEngineHost::~PhotoTileEngineHost() { shutdown(); }

void PhotoTileEngineHost::set_progress_handler(ProgressFn fn) { p->on_progress = std::move(fn); }
void PhotoTileEngineHost::set_result_handler(ResultFn fn)     { p->on_result   = std::move(fn); }
void PhotoTileEngineHost::set_status_handler(StatusFn fn)     { p->on_status   = std::move(fn); }
bool PhotoTileEngineHost::is_ready() const                    { return p->ready; }
bool PhotoTileEngineHost::is_busy() const                     { return p->busy; }
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
            size_t idx = (size_t)(sorted.size() * 0.95);
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
void PhotoTileEngineHost::shutdown() { if (p) { p->ready = false; p->busy = false; } }
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

// WebView2Loader.dll 隨 app 佈署（CMakeLists.txt:827/862）。動態載入＝不動連結設定，
// 且**載不到就是誠實不可用**——不像現行鏈那樣把 Create() 回傳值丟掉造成沉默假成功。
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

std::string hex_hr(HRESULT hr)
{
    char buf[32];
    ::snprintf(buf, sizeof(buf), "0x%08lX", (unsigned long) hr);
    return buf;
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

bool PhotoTileEngineHost::start()
{
    if (p->ready || p->creating) return true;

    const Availability avail = check_runtime();
    if (!avail.available) { p->status("unavailable", avail.reason); return false; }

    auto create_env = (PFN_CreateEnv) ::GetProcAddress(loader_module(), "CreateCoreWebView2EnvironmentWithOptions");
    if (!create_env) { p->status("unavailable", "WebView2Loader.dll 缺少建立介面。請重新安裝 PING Slicer。"); return false; }

    if (!p->host_frame) {
        // 隱藏宿主視窗：**永不 Show()**。WebView2 controller 需要真 HWND
        //（message-only 視窗不支援），故用不進工作列的 tool window。
        p->host_frame = new wxFrame(nullptr, wxID_ANY, "PING PhotoTile Engine", wxDefaultPosition,
                                    wxSize(1, 1), wxFRAME_TOOL_WINDOW | wxFRAME_NO_TASKBAR);
    }

    // 保險絲（C-0 §3.2 第二道防線）：頁面端已守零計時器紀律，這裡再關掉背景計時器節流，
    // 免得日後有人在頁面加回計時器就悄悄變慢。
    auto options = Make<CoreWebView2EnvironmentOptions>();
    options->put_AdditionalBrowserArguments(L"--disable-background-timer-throttling");

    const std::wstring user_data = utf8_to_wide(data_dir() + "/webview2_phototile");
    p->creating = true;
    p->status("starting", "建立隱形引擎宿主…（runtime " + avail.runtime_version + "）");

    Impl* impl = p.get();
    const HRESULT hr = create_env(nullptr, user_data.c_str(), options.Get(),
        Callback<ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler>(
            [this, impl](HRESULT result, ICoreWebView2Environment* environment) -> HRESULT {
                if (FAILED(result) || environment == nullptr) {
                    impl->creating = false;
                    impl->status("unavailable", "WebView2 環境建立失敗（HRESULT " + hex_hr(result) + "）。");
                    return S_OK;
                }
                impl->env = environment;
                this->create_controller();
                return S_OK;
            }).Get());

    if (FAILED(hr)) {
        p->creating = false;
        p->status("unavailable", "WebView2 環境建立呼叫失敗（HRESULT " + hex_hr(hr) + "）。");
        return false;
    }
    return true;
}

void PhotoTileEngineHost::create_controller()
{
    Impl* impl = p.get();
    if (!impl->env || !impl->host_frame) return;

    const HRESULT hr = impl->env->CreateCoreWebView2Controller((HWND) impl->host_frame->GetHandle(),
        Callback<ICoreWebView2CreateCoreWebView2ControllerCompletedHandler>(
            [this, impl](HRESULT result, ICoreWebView2Controller* controller) -> HRESULT {
                impl->creating = false;
                if (FAILED(result) || controller == nullptr) {
                    impl->status("unavailable", "WebView2 controller 建立失敗（HRESULT " + hex_hr(result) + "）。");
                    return S_OK;
                }
                impl->controller = controller;
                impl->controller->put_IsVisible(FALSE);          // 隱形：連 1x1 都不畫
                impl->controller->get_CoreWebView2(&impl->webview);
                if (!impl->webview) {
                    impl->status("unavailable", "WebView2 取得核心介面失敗。");
                    return S_OK;
                }

                EventRegistrationToken token;
                impl->webview->add_WebMessageReceived(
                    Callback<ICoreWebView2WebMessageReceivedEventHandler>(
                        [this](ICoreWebView2*, ICoreWebView2WebMessageReceivedEventArgs* args) -> HRESULT {
                            LPWSTR raw = nullptr;
                            if (SUCCEEDED(args->TryGetWebMessageAsString(&raw)) && raw) {
                                const std::string json = wide_to_utf8(raw);
                                ::CoTaskMemFree(raw);
                                this->handle_message(json);
                            }
                            return S_OK;
                        }).Get(), &token);

                impl->webview->add_ProcessFailed(
                    Callback<ICoreWebView2ProcessFailedEventHandler>(
                        [this, impl](ICoreWebView2*, ICoreWebView2ProcessFailedEventArgs* args) -> HRESULT {
                            COREWEBVIEW2_PROCESS_FAILED_KIND kind = COREWEBVIEW2_PROCESS_FAILED_KIND_BROWSER_PROCESS_EXITED;
                            if (args) args->get_ProcessFailedKind(&kind);
                            impl->ready = false;
                            if (!impl->active_job.empty())
                                impl->fail_job(impl->active_job, "engine_crashed", "引擎行程中止，正在重建…");
                            if (impl->rebuild_count >= REBUILD_CAP) {
                                impl->status("unavailable", "引擎連續重建 " + std::to_string(REBUILD_CAP) +
                                                            " 次仍失敗，已停止重試。請重開 PING Slicer。");
                                return S_OK;
                            }
                            ++impl->rebuild_count;
                            impl->status("rebuilding", "引擎行程中止（kind=" + std::to_string((int) kind) +
                                                       "），第 " + std::to_string(impl->rebuild_count) + " 次重建。");
                            impl->controller.Reset();
                            impl->webview.Reset();
                            this->create_controller();
                            return S_OK;
                        }).Get(), &token);

                this->navigate_and_wait_ready();
                return S_OK;
            }).Get());

    if (FAILED(hr)) {
        impl->creating = false;
        impl->status("unavailable", "WebView2 controller 建立呼叫失敗（HRESULT " + hex_hr(hr) + "）。");
    }
}

void PhotoTileEngineHost::navigate_and_wait_ready()
{
    Impl* impl = p.get();
    if (!impl->webview) return;

    // ready 逾時＝誠實失敗（C-0 §3.2 noready 負測）。注意 ready 可能早於
    // NavigationCompleted 抵達——所以我們只等 ready，不綁導覽完成事件。
    if (!impl->ready_timer) {
        impl->ready_timer.reset(new wxTimer(impl->host_frame));
        impl->host_frame->Bind(wxEVT_TIMER, [impl](wxTimerEvent&) {
            if (impl->ready) return;
            impl->status("unavailable", "引擎頁未在 " + std::to_string(READY_TIMEOUT_MS / 1000) +
                                        " 秒內回報就緒（ready 握手逾時）。");
            if (!impl->active_job.empty())
                impl->fail_job(impl->active_job, "engine_timeout", "引擎啟動逾時。");
        });
    }
    impl->ready_timer->StartOnce(READY_TIMEOUT_MS);
    impl->webview->Navigate(utf8_to_wide(engine_url()).c_str());
}

void PhotoTileEngineHost::handle_message(const std::string& json)
{
    Impl* impl = p.get();
    const double t0 = now_ms();

    pt::ptree m;
    if (!json_from_string(json, m)) return;
    const int         v    = m.get<int>("v", 0);
    const std::string type = m.get<std::string>("type", "");
    const std::string job  = m.get<std::string>("jobId", "");

    if (v != PROTOCOL_VERSION) {
        impl->fail_job(job, "protocol_bad_version", "引擎頁協定版本不符（收到 " + std::to_string(v) + "）。");
        return;
    }

    if (type == "ready") {
        if (impl->ready_timer) impl->ready_timer->Stop();
        impl->ready = true;
        impl->status("ready", "引擎就緒（engine " + m.get<std::string>("engine", "?") +
                              "／protocol " + std::to_string(m.get<int>("protocol", 0)) + "）");
        if (impl->has_queued_request) {
            impl->has_queued_request = false;
            this->generate(impl->queued_request);
        }
    }
    else if (type == "progress") {
        if (impl->on_progress)
            impl->on_progress(job, m.get<std::string>("stage", ""), m.get<std::string>("stageLabel", ""),
                              m.get<double>("pct", 0.0));
    }
    else if (type == "result") {
        if (!m.get<bool>("ok", false)) {
            impl->fail_job(job, m.get<std::string>("error.code", "internal"),
                                m.get<std::string>("error.message", "引擎回報失敗"));
            return;
        }
        impl->pending = PhotoTileEngineResult();
        impl->pending.job_id  = job;
        impl->pending.sha256  = m.get<std::string>("sha256", "");
        impl->pending.wall_ms = m.get<int>("wallMs", 0);
        impl->pending.result_json = json;
        {
            auto env_node = m.get_child_optional("env");
            if (env_node) impl->pending.env_json = ptree_to_json(*env_node);
        }
        impl->pending_valid = true;
    }
    else if (type == "begin") {
        impl->xfer = Impl::Transfer();
        impl->xfer.active = true;
        impl->xfer.job_id = job;
        impl->xfer.size   = m.get<size_t>("size", 0);
        impl->xfer.chunks = m.get<size_t>("chunks", 0);
        impl->xfer.sha256 = m.get<std::string>("sha256", "");
        impl->xfer.bytes.reserve(impl->xfer.size);
    }
    else if (type == "chunk") {
        if (!impl->xfer.active || impl->xfer.job_id != job) {
            impl->fail_job(job, "protocol_job_mismatch", "收到不屬於目前作業的分塊。");
            return;
        }
        const size_t index = m.get<size_t>("index", 0);
        if (index != impl->xfer.received) {                       // ①連號
            impl->fail_job(job, "protocol_chunk_order",
                           "分塊序號不連續（期望 " + std::to_string(impl->xfer.received) +
                           "、收到 " + std::to_string(index) + "）。");
            return;
        }
        const wxMemoryBuffer buf = wxBase64Decode(m.get<std::string>("base64", ""));
        const size_t declared = m.get<size_t>("length", buf.GetDataLen());
        if (buf.GetDataLen() != declared) {                        // ③長度
            impl->fail_job(job, "protocol_length_mismatch",
                           "分塊長度不符（宣告 " + std::to_string(declared) +
                           "、實得 " + std::to_string(buf.GetDataLen()) + "）。");
            return;
        }
        const unsigned char* data = (const unsigned char*) buf.GetData();
        impl->xfer.bytes.insert(impl->xfer.bytes.end(), data, data + buf.GetDataLen());
        ++impl->xfer.received;
        if (impl->smoke_on) impl->smoke.chunks_received = (int) impl->xfer.received;
    }
    else if (type == "end") {
        if (!impl->xfer.active || impl->xfer.job_id != job) {
            impl->fail_job(job, "protocol_job_mismatch", "收到不屬於目前作業的結束訊息。");
            return;
        }
        if (impl->xfer.received != impl->xfer.chunks) {             // ②塊數
            impl->fail_job(job, "protocol_chunk_count",
                           "塊數不符（宣告 " + std::to_string(impl->xfer.chunks) +
                           "、實收 " + std::to_string(impl->xfer.received) + "）。");
            return;
        }
        if (impl->xfer.bytes.size() != impl->xfer.size) {           // ③總長度
            impl->fail_job(job, "protocol_length_mismatch",
                           "總長度不符（宣告 " + std::to_string(impl->xfer.size) +
                           "、實得 " + std::to_string(impl->xfer.bytes.size()) + "）。");
            return;
        }
        const std::string expect = m.get<std::string>("sha256", impl->xfer.sha256);
        const std::string got    = sha256_hex(impl->xfer.bytes.data(), impl->xfer.bytes.size());
        if (!expect.empty() && expect != got) {                     // ④SHA-256
            impl->fail_job(job, "protocol_sha_mismatch", "SHA-256 不符，已丟棄整份 3MF。");
            return;
        }
        if (!impl->pending_valid || impl->pending.job_id != job) {
            impl->fail_job(job, "protocol_bad_message", "收到 3MF 但沒有對應的 result 中繼資料。");
            return;
        }
        // 四項全過才算 success（協定 §3）
        PhotoTileEngineResult r = impl->pending;
        r.ok       = true;
        r.three_mf = std::move(impl->xfer.bytes);
        r.sha256   = got;
        impl->xfer = Impl::Transfer();
        impl->pending_valid = false;
        impl->busy = false;
        impl->active_job.clear();
        if (impl->on_result) impl->on_result(r);
    }
    else if (type == "superseded") {
        impl->status("superseded", "作業 " + job + " 已被新的輸入取代。");
    }
    else if (type == "error") {
        impl->fail_job(job, m.get<std::string>("code", "internal"), m.get<std::string>("message", ""));
    }
    else if (type == "imageAck") {
        impl->status("imageAck", "影像注入完成（" + std::to_string(m.get<size_t>("chars", 0)) + " 字元）。");
    }

    if (impl->smoke_on)
        impl->smoke.message_handle_max_ms = (std::max)(impl->smoke.message_handle_max_ms, now_ms() - t0);
}

bool PhotoTileEngineHost::generate(const PhotoTileEngineRequest& req)
{
    Impl* impl = p.get();
    if (!impl->ready) {
        impl->queued_request     = req;      // ready 之後自動補送
        impl->has_queued_request = true;
        return start();
    }
    if (impl->busy && !impl->active_job.empty() && impl->active_job != req.job_id)
        cancel(impl->active_job);            // supersede：引擎端也會自己收斂（協定 §1）

    impl->busy       = true;
    impl->active_job = req.job_id;
    impl->xfer       = Impl::Transfer();
    impl->pending_valid = false;

    // 影像讀檔＋base64＝**背景執行緒**（C-0 §3.3 ④：不要在 UI 執行緒付這筆帳）
    const std::string path   = req.image_path;
    const std::string job_id = req.job_id;
    PhotoTileEngineRequest req_copy = req;
    std::thread([this, impl, path, job_id, req_copy]() {
        const double t0 = now_ms();
        boost::nowide::ifstream input(path, std::ios::binary | std::ios::ate);
        if (!input) {
            wxTheApp->CallAfter([impl, job_id]() {
                impl->fail_job(job_id, "bad_image", "圖片無法讀取，請重新選擇檔案。"); });
            return;
        }
        const std::streamoff size = input.tellg();
        if (size <= 0 || size > MAX_IMAGE_BYTES) {
            wxTheApp->CallAfter([impl, job_id]() {
                impl->fail_job(job_id, "bad_image", "圖片檔案過大（上限 64 MB），請先縮小圖片再試。"); });
            return;
        }
        input.seekg(0, std::ios::beg);
        std::vector<unsigned char> bytes((size_t) size);
        if (!input.read((char*) bytes.data(), size)) {
            wxTheApp->CallAfter([impl, job_id]() {
                impl->fail_job(job_id, "bad_image", "圖片讀取失敗，請重新選擇檔案。"); });
            return;
        }
        const std::string b64 = wxBase64Encode(bytes.data(), bytes.size()).ToStdString();
        const double encode_ms = now_ms() - t0;

        // 副檔名 → mime（同 WebViewDialog::SendPendingPhotoTileImage 的對照）
        std::string ext = path.substr(path.find_last_of('.') + 1);
        std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
        std::string mime = "image/png";
        if (ext == "jpg" || ext == "jpeg") mime = "image/jpeg";
        else if (ext == "webp")            mime = "image/webp";
        else if (ext == "bmp")             mime = "image/bmp";

        const size_t chunks = (b64.size() + INJECT_CHUNK_CHARS - 1) / INJECT_CHUNK_CHARS;
        std::deque<std::string> queue;
        {
            pt::ptree begin;
            begin.put("v", PROTOCOL_VERSION);
            begin.put("cmd", "imageBegin");
            begin.put("jobId", job_id);
            begin.put("mime", mime);
            begin.put("totalChars", b64.size());
            begin.put("chunks", chunks);
            queue.push_back(ptree_to_json(begin));
        }
        for (size_t i = 0; i < chunks; ++i) {
            pt::ptree c;
            c.put("v", PROTOCOL_VERSION);
            c.put("cmd", "imageChunk");
            c.put("jobId", job_id);
            c.put("index", i);
            c.put("base64", b64.substr(i * INJECT_CHUNK_CHARS,
                                       (std::min)(INJECT_CHUNK_CHARS, b64.size() - i * INJECT_CHUNK_CHARS)));
            queue.push_back(ptree_to_json(c));
        }
        {
            pt::ptree end;
            end.put("v", PROTOCOL_VERSION);
            end.put("cmd", "imageEnd");
            end.put("jobId", job_id);
            end.put("totalChars", b64.size());
            end.put("chunks", chunks);
            queue.push_back(ptree_to_json(end));
        }
        queue.push_back(build_generate_command(req_copy));

        wxTheApp->CallAfter([this, impl, queue, encode_ms]() mutable {
            if (impl->smoke_on) impl->smoke.inject_encode_ms = encode_ms;
            for (auto& msg : queue) impl->inject_queue.push_back(std::move(msg));
            this->pump_inject_queue();
        });
    }).detach();

    return true;
}

// 分批派發＝把 247 則注入訊息攤平在多個事件圈迭代，別讓 UI 一次卡住
void PhotoTileEngineHost::pump_inject_queue()
{
    Impl* impl = p.get();
    if (impl->inject_queue.empty()) { impl->inject_pumping = false; return; }
    impl->inject_pumping = true;
    for (size_t i = 0; i < INJECT_BATCH && !impl->inject_queue.empty(); ++i) {
        impl->send_json(impl->inject_queue.front());
        impl->inject_queue.pop_front();
    }
    if (!impl->inject_queue.empty())
        wxTheApp->CallAfter([this]() { this->pump_inject_queue(); });
    else
        impl->inject_pumping = false;
}

std::string PhotoTileEngineHost::build_generate_command(const PhotoTileEngineRequest& req)
{
    pt::ptree msg, r, size, pillar, seam, limits;
    msg.put("v", PROTOCOL_VERSION);
    msg.put("cmd", "generate");
    msg.put("jobId", req.job_id);

    r.put("jobId", req.job_id);
    r.put("mode", req.mode);
    r.put("nozzle", req.nozzle);
    size.put("widthMm", req.width_mm);
    size.put("heightMm", req.height_mm);
    size.put("thickMm", req.thick_mm);
    r.add_child("size", size);
    r.put("klevels", req.klevels);
    r.put("noiseMm", req.noise_mm);
    pillar.put("enabled", req.pillar);
    pillar.put("xyMm", req.pillar_xy_mm);
    r.add_child("pillar", pillar);
    seam.put("teeth", req.teeth);
    seam.put("p2aBlock", req.p2a_block);
    r.add_child("seam", seam);
    if (req.grid_max > 0)            limits.put("gridMax", req.grid_max);
    if (req.max_decoded_pixels > 0)  limits.put("maxDecodedPixels", req.max_decoded_pixels);
    if (!limits.empty())             r.add_child("limits", limits);
    if (req.want_metadata) {
        pt::ptree md;
        md.put("groupUuid", req.group_uuid);
        md.put("embedSource", req.embed_source);
        md.put("createdBy", "PING-Slicer");
        r.add_child("metadata", md);
    }
    if (!req.env_json.empty()) {
        pt::ptree env;
        if (json_from_string(req.env_json, env)) r.add_child("env", env);
    }
    msg.add_child("request", r);
    return ptree_to_json(msg);
}

void PhotoTileEngineHost::shutdown()
{
    if (!p) return;
    if (p->ready_timer) { p->ready_timer->Stop(); p->ready_timer.reset(); }
    if (p->controller)  { p->controller->Close(); p->controller.Reset(); }
    p->webview.Reset();
    p->env.Reset();
    if (p->host_frame)  { p->host_frame->Destroy(); p->host_frame = nullptr; }
    p->ready = false;
    p->busy  = false;
}

void PhotoTileEngineHost::cancel(const std::string& job_id)
{
    if (!p->webview) return;
    pt::ptree msg;
    msg.put("v", PROTOCOL_VERSION);
    msg.put("cmd", "cancel");
    msg.put("jobId", job_id);
    p->send_json(ptree_to_json(msg));
}

#endif // _WIN32

}} // namespace Slic3r::GUI
