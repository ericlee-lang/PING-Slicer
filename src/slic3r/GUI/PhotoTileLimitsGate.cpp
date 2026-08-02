// =====================================================================
// 照片磚 C-1 首站閘門③：OOM／低記憶體 gate（2026-07-31・照片磚線 PT）
//
// 要證明的三件事（C-0 §4.3 殘餘風險 #4 列的硬化項）：
//   ① 合法上限案在本機能跑完，且峰值記憶體可量（C-0 觀測 1,303MB＝低規機的風險所在）
//   ② **降階真的有效**：gridMax 減半 ⇒ 格點數與耗時明顯下降（不是掛著好看的參數）
//   ③ **超限誠實報錯**：解碼後像素超過 maxDecodedPixels ⇒ 回 image_too_large，
//      app 不崩、UI 續跑；把上限拿掉則同一張圖可正常生成（證明擋下來的是規則、不是圖壞）
//
// 判準（先寫死）：
//   - 案 ③ 必須回 image_too_large（不是崩潰、不是逾時、不是別的錯）
//   - 案 ④（拿掉上限）必須成功 ⇒ 證明 ③ 的失敗來自規則本身
//   - 案 ② 的格點數必須 < 案 ① 的格點數
//   - 全程 app 不崩、心跳漂移 max ≤ 1000ms（大圖解碼期允許比閘門①寬）
//
// 【2026-08-02 二版：補 Codex 重要 #7 的三個缺口】一版只證明「本機 64GB 的功能性通過」，
// 不能外推成低規機安全。缺的三件現在都補進來了：
//   ④ **metadata-on**：產品的 opt-in 路徑會多出一份中繼資料，峰值沒量過就不能說量過了
//   ⑤ **48M 像素＋3200² 格點同時峰值**：一版的大圖案刻意 gridMax=800＋dual 60mm（＝降階過的），
//      兩個維度從沒同時拉滿過——那才是低規機真正會遇到的那一刀
//   ⑥ **限記憶體環境**：用 Job Object 把整個進程樹（含 WebView2 子行程）壓在一個上限內跑，
//      看它是誠實報錯還是崩潰。opt-in：`PING_PHOTOTILE_LIMITS_JOBMEM_MB=<MB>`
//
// 記憶體改成**本檔自己量**（1Hz），不再靠外部 PowerShell：
//   0731 回報過 4,026MB 後來更正為 2,140MB，錯因就是外部腳本把**全機器**的 msedgewebview2
//   都加總了。本檔改為從自己的 PID 出發、只沿父子鏈收自己那棵樹，並且**主程序與 WebView 樹
//   分開列**——量錯的那種錯法在結構上就發生不了。
// =====================================================================

#include "PhotoTileSmoke.hpp"
#include "PhotoTileEngineHost.hpp"
#include "PhotoTileGateJson.hpp"

#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "libslic3r/Utils.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cwchar>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <exception>
#include <typeinfo>

#include <boost/log/trivial.hpp>
#include <boost/nowide/fstream.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>

#include <wx/app.h>
#include <wx/filename.h>
#include <wx/image.h>
#include <wx/timer.h>
#include <wx/utils.h>

#ifdef _WIN32
#include <windows.h>
#include <tlhelp32.h>
#endif

namespace pt = boost::property_tree;

namespace Slic3r { namespace GUI {

namespace {

double lg_now_ms()
{
    using namespace std::chrono;
    return duration_cast<duration<double, std::milli>>(steady_clock::now().time_since_epoch()).count();
}

// 崩潰探針：2026-07-31 閘門③首跑 app 以 0xC0000409（ucrtbase fail-fast）死兩次，
// 但沒有任何線索指出是哪個例外。fail-fast 多半來自 std::terminate（未捕捉的 C++ 例外，
// 含跨執行緒／跨 COM 回呼逃逸的那種）——裝個 terminate handler 把型別與訊息落地，
// 就不用再靠猜。落點＝data_dir()/phototile_crash.txt（append，保留多次）。
void breadcrumb(const std::string& line)
{
    try {
        boost::nowide::ofstream f(data_dir() + "/phototile_crash.txt", std::ios::app);
        f << line << "\n";
    } catch (...) {}
}
void install_crash_probe()
{
    static bool installed = false;
    if (installed) return;
    installed = true;
    std::set_terminate([]() {
        std::string what = "(current_exception 為空＝可能是 abort/純 SEH)";
        try {
            if (auto e = std::current_exception()) std::rethrow_exception(e);
        } catch (const std::exception& ex) {
            what = std::string("std::exception[") + typeid(ex).name() + "] " + ex.what();
        } catch (...) {
            what = "非 std::exception 型別的例外";
        }
        breadcrumb("=== std::terminate ===");
        breadcrumb(what);
        ::abort();
    });
}

// 決定性大圖（與小圖同一條公式，只是尺寸不同）
std::string write_big_image(int W, int H, const char* name)
{
    wxImage img(W, H);
    unsigned char* d = img.GetData();
    for (int y = 0; y < H; ++y)
        for (int x = 0; x < W; ++x) {
            const size_t i = ((size_t) y * W + x) * 3;
            d[i]     = (unsigned char) ((x * 255) / W);
            d[i + 1] = (unsigned char) ((y * 255) / H);
            d[i + 2] = (unsigned char) ((x ^ y) & 0xFF);
        }
    const wxString path = wxFileName(from_u8(data_dir()), name).GetFullPath();
    img.SaveFile(path, wxBITMAP_TYPE_PNG);
    return into_u8(path);
}

/* ── 記憶體取樣：自己那棵樹，主程序與 WebView 分開列 ────────────────────
   量法錯過一次（把全機器 WebView2 加總＝4,026MB，實際 2,140MB），所以這裡的規則寫死：
   從自己的 PID 出發，只收「父是我」與「父的父是我」的 msedgewebview2（browser 與其子行程），
   別人的 WebView2 一律不算。單位一律 MB、取 PrivateUsage（commit）＝真正壓在記憶體上的量。 */
struct MemSample
{
    double main_mb = 0, webview_mb = 0;
    int    webview_procs = 0;
    double total_mb() const { return main_mb + webview_mb; }
};

#ifdef _WIN32
struct PT_PROC_MEM_EX
{
    DWORD  cb, PageFaultCount;
    SIZE_T PeakWorkingSetSize, WorkingSetSize;
    SIZE_T QuotaPeakPagedPoolUsage, QuotaPagedPoolUsage;
    SIZE_T QuotaPeakNonPagedPoolUsage, QuotaNonPagedPoolUsage;
    SIZE_T PagefileUsage, PeakPagefileUsage, PrivateUsage;
};
typedef BOOL(WINAPI* FnProcMem)(HANDLE, PT_PROC_MEM_EX*, DWORD);

double private_mb(DWORD pid)
{
    static FnProcMem fn = []() -> FnProcMem {
        if (HMODULE k = ::GetModuleHandleW(L"kernel32.dll"))
            return (FnProcMem) ::GetProcAddress(k, "K32GetProcessMemoryInfo");
        return nullptr;
    }();
    if (!fn) return 0.0;
    HANDLE h = ::OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return 0.0;
    PT_PROC_MEM_EX pm{};
    pm.cb = sizeof(pm);
    const double mb = fn(h, &pm, sizeof(pm)) ? (double) pm.PrivateUsage / (1024.0 * 1024.0) : 0.0;
    ::CloseHandle(h);
    return mb;
}
#endif

MemSample sample_memory()
{
    MemSample s;
#ifdef _WIN32
    const DWORD self = ::GetCurrentProcessId();
    s.main_mb = private_mb(self);

    HANDLE snap = ::CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return s;
    std::vector<std::pair<DWORD, DWORD>> wv;   // (pid, parent) 只收 msedgewebview2
    PROCESSENTRY32W pe{};
    pe.dwSize = sizeof(pe);
    if (::Process32FirstW(snap, &pe)) {
        do {
            if (::_wcsicmp(pe.szExeFile, L"msedgewebview2.exe") == 0)
                wv.emplace_back(pe.th32ProcessID, pe.th32ParentProcessID);
        } while (::Process32NextW(snap, &pe));
    }
    ::CloseHandle(snap);

    // 第一層＝父是我（browser 行程）；第二層＝父是第一層（renderer／GPU／utility）
    std::vector<DWORD> mine;
    for (const auto& p : wv) if (p.second == self) mine.push_back(p.first);
    const size_t first_level = mine.size();
    for (size_t i = 0; i < first_level; ++i)
        for (const auto& p : wv) if (p.second == mine[i]) mine.push_back(p.first);

    for (DWORD pid : mine) s.webview_mb += private_mb(pid);
    s.webview_procs = (int) mine.size();
#endif
    return s;
}

/* ── Job Object 記憶體上限（opt-in）─────────────────────────────────────
   低規機安全不能靠「本機 64GB 跑得動」推論。把自己丟進一個有 commit 上限的 job，
   之後建立的 WebView2 子行程會**繼承同一個 job**（Win8+ 支援巢狀 job，Chromium 自建的
   sandbox job 會掛在我們這顆下面），整棵樹就一起受限。
   ⚠ 這是刻意讓它撞牆的測試：撞到之後我們要的是「誠實報錯、app 續活」，不是「不會撞」。 */
bool apply_job_memory_limit(long mb, std::string& detail)
{
#ifdef _WIN32
    HANDLE job = ::CreateJobObjectW(nullptr, nullptr);
    if (!job) { detail = "CreateJobObject 失敗 err=" + std::to_string((long) ::GetLastError()); return false; }
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION li{};
    li.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_JOB_MEMORY;
    li.JobMemoryLimit = (SIZE_T) mb * 1024u * 1024u;
    if (!::SetInformationJobObject(job, JobObjectExtendedLimitInformation, &li, sizeof(li))) {
        detail = "SetInformationJobObject 失敗 err=" + std::to_string((long) ::GetLastError());
        ::CloseHandle(job);
        return false;
    }
    if (!::AssignProcessToJobObject(job, ::GetCurrentProcess())) {
        detail = "AssignProcessToJobObject 失敗 err=" + std::to_string((long) ::GetLastError());
        ::CloseHandle(job);
        return false;
    }
    detail = "整個進程樹的 commit 上限＝" + std::to_string(mb) + " MB";
    return true;   // 故意不 CloseHandle：job 要活到進程結束
#else
    (void) mb; detail = "非 Windows：不支援"; return false;
#endif
}

struct LimitsCase
{
    std::string label;
    std::string mode;
    double      size_mm      = 400.0;
    int         klevels      = 48;
    int         grid_max     = 0;          // 0＝引擎預設 3200
    long long   max_pixels   = 0;          // 0＝不設限
    bool        use_big_image = false;
    bool        expect_ok    = true;
    std::string expect_error;              // expect_ok=false 時必須等於這個碼
    bool        want_metadata = false;     // #7：產品 opt-in 路徑也要量峰值
    double      peak_main_mb = 0, peak_wv_mb = 0;   // 本案期間的峰值（跑完才填）
    int         peak_wv_procs = 0;
};

class LimitsRun;
std::unique_ptr<LimitsRun> g_limits_run;  // 唯一擁有者（Codex #1：取代 `delete this`）

class LimitsRun : public wxEvtHandler
{
public:
    LimitsRun() : m_host(new PhotoTileEngineHost())
    {
        m_host->enable_smoke_metrics(true);
        m_host->set_status_handler([this](const std::string& s, const std::string& d) {
            breadcrumb("[host] " + s + " " + d);
            if (s == "unavailable") finish("engine_unavailable: " + d);
        });
        m_host->set_result_handler([this](const PhotoTileEngineResult& r) { on_result(r); });
        m_beat.SetOwner(this);
        Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
            const double t = lg_now_ms();
            if (m_last_beat > 0) {
                const double drift = (t - m_last_beat) - 10.0;
                if (drift > m_drift_max)      m_drift_max = drift;
                /* 逐案也記一份：只有全域最大值的話，看到一個爆掉的數字**沒辦法知道是哪一案**，
                   也就沒辦法一次只改一個變數去定罪（0802 首跑就撞上這件事）。 */
                if (drift > m_drift_max_case) m_drift_max_case = drift;
            }
            m_last_beat = t;
        });

        // ① 合法上限（C-0 §4.2 的包絡案）／② 同案降階／③ 大圖超限／④ 大圖不設限
        m_cases.push_back({ "legal-max-quad-K48",      "quad", 400.0, 48, 0,    0,        false, true,  "" });
        m_cases.push_back({ "downshift-gridMax1600",   "quad", 400.0, 48, 1600, 0,        false, true,  "" });
        m_cases.push_back({ "oversize-image-capped",   "dual",  60.0,  6, 0,    8000000LL, true,  false, "image_too_large" });
        m_cases.push_back({ "oversize-image-uncapped", "dual",  60.0,  6, 800,  0,        true,  true,  "" });
        // ⑤【#7】metadata-on：產品的 opt-in 路徑會多產一份中繼資料，峰值沒量過就不能說量過
        m_cases.push_back({ "legal-max-quad-K48-metadata", "quad", 400.0, 48, 0, 0,       false, true,  "", true });
        // ⑥【#7】48M 像素 × 3200² 格點**同時**拉滿——一版的大圖案是 dual 60mm＋gridMax 800（降過階的），
        //         兩個維度從沒同時到頂過，而那正是低規機真正會遇到的那一刀
        m_cases.push_back({ "peak-48Mpx-x-fullgrid-quad", "quad", 400.0, 48, 0, 0,        true,  true,  "" });
    }
    ~LimitsRun() override { m_beat.Stop(); stop_sampler(); }   // m_host 是 unique_ptr（Codex #1）

    void start()
    {
        install_crash_probe();
        breadcrumb("--- 閘門③ 起跑 ---");

        /* 限記憶體模式（opt-in）：要在**建立 WebView2 之前**套用，子行程才會繼承這顆 job。 */
        wxString jm;
        if (wxGetEnv("PING_PHOTOTILE_LIMITS_JOBMEM_MB", &jm) && !jm.empty()) {
            m_jobmem_mb      = ::atol(into_u8(jm).c_str());
            m_jobmem_applied = apply_job_memory_limit(m_jobmem_mb, m_jobmem_detail);
            BOOST_LOG_TRIVIAL(warning) << "PhotoTile 閘門③ 限記憶體模式："
                                       << (m_jobmem_applied ? "已套用－" : "套用失敗－") << m_jobmem_detail;
            breadcrumb("[jobmem] " + std::string(m_jobmem_applied ? "applied " : "failed ") + m_jobmem_detail);
        }

        m_t0 = lg_now_ms();
        m_beat.Start(10);
        start_sampler();
        m_small = write_big_image(480, 360, "phototile_limits_small.png");
        // 8000×6000＝48M 像素（C-0 §4.2 用過的高像素輸入量級）
        m_big   = write_big_image(8000, 6000, "phototile_limits_big.png");
        if (!m_host->start()) { finish("host_start_failed"); return; }
        run_case();
    }

private:
    /* 取樣跑在**背景執行緒**：CreateToolhelp32Snapshot 掃全機器行程要十幾毫秒，
       放在 UI 執行緒上量到的 uiDriftMaxMs 就變成「量測工具自己造成的漂移」＝自證的假數據。 */
    void start_sampler()
    {
        /* 取樣本身也是嫌疑犯。要證明「漂移不是量測工具自己造成的」，就得有辦法把它關掉重跑
           ——一次只改一個變數。`PING_PHOTOTILE_LIMITS_NO_MEMSAMPLE=1` 就是那個開關。 */
        wxString off;
        if (wxGetEnv("PING_PHOTOTILE_LIMITS_NO_MEMSAMPLE", &off) && off == "1") {
            m_sampler_disabled = true;
            BOOST_LOG_TRIVIAL(warning) << "PhotoTile 閘門③：記憶體取樣已停用（對照組）";
            return;
        }
        m_sampling.store(true);
        m_sampler = std::thread([this]() {
            while (m_sampling.load()) {
                const MemSample s = sample_memory();
                const long main_kb = (long) (s.main_mb * 1024.0);
                const long wv_kb   = (long) (s.webview_mb * 1024.0);
                if (main_kb > m_peak_main_kb.load()) m_peak_main_kb.store(main_kb);
                if (wv_kb   > m_peak_wv_kb.load())   m_peak_wv_kb.store(wv_kb);
                if (s.webview_procs > m_peak_wv_procs.load()) m_peak_wv_procs.store(s.webview_procs);
                for (int i = 0; i < 10 && m_sampling.load(); ++i)   // 1Hz，但 100ms 就能收工
                    std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
        });
    }
    void stop_sampler()
    {
        m_sampling.store(false);
        if (m_sampler.joinable()) m_sampler.join();
    }
    void reset_case_peaks()
    {
        m_peak_main_kb.store(0);
        m_peak_wv_kb.store(0);
        m_peak_wv_procs.store(0);
        m_drift_max_case = 0;
    }

    void run_case()
    {
        if (m_index >= m_cases.size()) { finish("done"); return; }
        const LimitsCase& c = m_cases[m_index];
        PhotoTileEngineRequest req;
        req.job_id     = "limits-" + std::to_string(m_index + 1);
        req.mode       = c.mode;
        req.nozzle     = 0.4;
        req.width_mm   = c.size_mm; req.height_mm = c.size_mm; req.thick_mm = 6.0;
        req.klevels    = c.klevels; req.noise_mm  = 0.0;
        req.pillar     = false;     req.teeth = false; req.p2a_block = false;
        req.grid_max           = c.grid_max;
        req.max_decoded_pixels = c.max_pixels;
        req.image_path         = c.use_big_image ? m_big : m_small;
        req.want_metadata      = c.want_metadata;
        m_case_t0 = lg_now_ms();
        reset_case_peaks();      // 峰值逐案獨立，才知道是哪一案把記憶體頂上去的
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 閘門③ 起跑案例 " << c.label
                                   << "（mode=" << c.mode << " size=" << c.size_mm << " K=" << c.klevels
                                   << " gridMax=" << c.grid_max << " maxPx=" << c.max_pixels
                                   << " bigImage=" << (c.use_big_image ? 1 : 0)
                                   << " metadata=" << (c.want_metadata ? 1 : 0) << "）";
        write_report(false, "case_start:" + c.label);
        breadcrumb("[case] 起跑 " + c.label);
        m_host->generate(req);
    }

    void on_result(const PhotoTileEngineResult& r)
    {
        LimitsCase& c = m_cases[m_index];
        const double ms = lg_now_ms() - m_case_t0;
        c.peak_main_mb  = m_peak_main_kb.load() / 1024.0;
        c.peak_wv_mb    = m_peak_wv_kb.load() / 1024.0;
        c.peak_wv_procs = m_peak_wv_procs.load();
        if (c.peak_main_mb + c.peak_wv_mb > m_peak_total_mb) m_peak_total_mb = c.peak_main_mb + c.peak_wv_mb;
        long grid_w = 0, grid_h = 0, parts = 0;
        if (r.ok && !r.result_json.empty()) {
            try {
                std::istringstream ss(r.result_json);
                pt::ptree t; pt::read_json(ss, t);
                grid_w = t.get<long>("stats.gridW", 0);
                grid_h = t.get<long>("stats.gridH", 0);
                parts  = t.get<long>("stats.parts", 0);
            } catch (...) {}
        }
        const bool as_expected = c.expect_ok ? r.ok
                                             : (!r.ok && r.error_code == c.expect_error);
        if (!as_expected) m_all_ok = false;
        // 用 label 比對而不是索引：#7 在中間插了新案，索引式比對會靜默對錯人
        if (c.label == "legal-max-quad-K48")    m_grid_full = (long long) grid_w * grid_h;
        if (c.label == "downshift-gridMax1600") m_grid_down = (long long) grid_w * grid_h;
        if (c.label == "legal-max-quad-K48")          m_bytes_meta_off = (long long) r.three_mf.size();
        if (c.label == "legal-max-quad-K48-metadata") m_bytes_meta_on  = (long long) r.three_mf.size();
        /* 失敗時只有兩種：**誠實失敗**（引擎回一個代碼）與崩潰／掛死。限記憶體模式下
           我們要的答案正是前者，所以它必須是報告裡一個獨立、看得見的欄位。 */
        const bool honest_failure = !r.ok && !r.error_code.empty();

        std::ostringstream o;
        o << "    { " << jfield("label", c.label)
          << ", " << jfield("ok", r.ok)
          << ", " << jfield("asExpected", as_expected)
          << ", " << jfield("honestFailure", honest_failure)
          << ", " << jfield("errorCode", r.error_code)
          << ", " << jfield("errorMessage", r.error_message)
          << ", " << jfield("ms", (long) ms)
          << ", " << jfield("bytes", (long long) r.three_mf.size())
          << ", " << jfield("metadata", c.want_metadata)
          << ", " << jfield("gridW", grid_w) << ", " << jfield("gridH", grid_h)
          << ", " << jfield("parts", parts)
          << ", " << jfield("gridMax", c.grid_max)
          << ", " << jfield("maxDecodedPixels", c.max_pixels)
          << ", " << jfield("bigImage", c.use_big_image)
          << ", " << jfield("peakMainMB", c.peak_main_mb)
          << ", " << jfield("peakWebViewMB", c.peak_wv_mb)
          << ", " << jfield("peakTotalMB", c.peak_main_mb + c.peak_wv_mb)
          << ", " << jfield("webViewProcs", c.peak_wv_procs)
          << ", " << jfield("uiDriftMaxMsThisCase", (long) m_drift_max_case) << " }";
        m_rows.push_back(o.str());
        write_report(false, "in_progress");
        breadcrumb("[case] 結束 " + c.label + " ok=" + (r.ok ? "1" : "0") + " err=" + r.error_code);
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 閘門③ " << c.label << " → " << (as_expected ? "符合預期" : "不符預期")
                                << "（" << (long) ms << "ms" << (r.ok ? "" : "，" + r.error_code) << "）";
        ++m_index;
        run_case();
    }

    // 每跑完一案就落地一次＝崩潰也留得下證據（首跑 app fail-fast 卻查不出死在哪一案的教訓）
    void write_report(bool final_done, const std::string& why)
    {
        std::ostringstream j;
        j << "{\n"
          << "  " << jfield("_note", "照片磚 C-1 閘門③：OOM／低記憶體 gate（逐案落地，未跑完也有紀錄）") << ",\n"
          << "  " << jfield("final", final_done) << ", " << jfield("why", why) << ",\n"
          << "  " << jfield("casesRun", std::to_string(m_rows.size()) + "/" + std::to_string(m_cases.size())) << ",\n"
          << "  " << jfield("nextCase", m_index < m_cases.size() ? m_cases[m_index].label : std::string("-")) << ",\n"
          << "  " << jfield("uiDriftMaxMs", (long) m_drift_max) << ",\n"
          << "  " << jfield("elapsedMs", (long) (lg_now_ms() - m_t0)) << ",\n"
          << jobmem_json()
          << "  " << jstr("cases") << ": [\n";
        for (size_t i = 0; i < m_rows.size(); ++i) j << m_rows[i] << (i + 1 < m_rows.size() ? ",\n" : "\n");
        j << "  ]\n}\n";
        try { boost::nowide::ofstream f(data_dir() + "/phototile_limits_report.json"); f << j.str(); }
        catch (...) {}
    }

    std::string jobmem_json() const
    {
        std::ostringstream o;
        o << "  " << jstr("memoryLimit") << ": { "
          << jfield("requestedMB", (int) m_jobmem_mb) << ", "
          << jfield("applied", m_jobmem_applied) << ", "
          << jfield("detail", m_jobmem_detail) << " },\n";
        return o.str();
    }

    void finish(const std::string& why)
    {
        if (m_finished) return;
        m_finished = true;
        m_beat.Stop();
        stop_sampler();

        const bool pass_downshift = m_grid_full > 0 && m_grid_down > 0 && m_grid_down < m_grid_full;
        const bool pass_drift     = m_drift_max <= 1000.0;
        const bool pass_all       = m_all_ok && pass_downshift && pass_drift && why == "done";
        /* 「跑到最後、沒有一案是崩潰或掛死」——限記憶體模式下這是主要問句。
           ⚠ 它**不是** ok 的替代品：所有案都誠實報錯也會讓 noCrash 為真而 ok 為假，
           那正確地代表「這個記憶體上限下閘門③不通過，但產品沒崩」。 */
        const bool no_crash = (why == "done");

        std::ostringstream j;
        j << "{\n"
          << "  " << jfield("_note", "照片磚 C-1 閘門③：OOM／低記憶體 gate（降階有效性＋超限誠實報錯＋峰值記憶體）") << ",\n"
          << "  " << jfield("ok", pass_all) << ", " << jfield("why", why) << ",\n"
          << "  " << jfield("allCasesAsExpected", m_all_ok) << ", " << jfield("noCrash", no_crash) << ",\n"
          << "  " << jfield("gridCellsFull", m_grid_full) << ", " << jfield("gridCellsDownshifted", m_grid_down)
          << ", " << jfield("downshiftEffective", pass_downshift) << ",\n"
          << "  " << jfield("bytesMetadataOff", m_bytes_meta_off) << ", " << jfield("bytesMetadataOn", m_bytes_meta_on)
          << ", " << jfield("metadataDeltaBytes", m_bytes_meta_on - m_bytes_meta_off) << ",\n"
          << "  " << jfield("peakTotalMB", m_peak_total_mb) << ",\n"
          << "  " << jfield("uiDriftMaxMs", (long) m_drift_max) << ", " << jfield("passDrift", pass_drift) << ",\n"
          << "  " << jfield("totalMs", (long) (lg_now_ms() - m_t0)) << ",\n"
          << jobmem_json()
          << "  " << jstr("cases") << ": [\n";
        for (size_t i = 0; i < m_rows.size(); ++i) j << m_rows[i] << (i + 1 < m_rows.size() ? ",\n" : "\n");
        j << "  ]\n}\n";

        const std::string path = data_dir() + "/phototile_limits_report.json";
        try { boost::nowide::ofstream f(path); f << j.str(); }
        catch (...) { BOOST_LOG_TRIVIAL(warning) << "閘門③ 報告寫檔失敗"; }
        BOOST_LOG_TRIVIAL(info) << "PhotoTile 閘門③ 報告：" << path;

        m_host->shutdown();
        wxTheApp->CallAfter([]() {
            g_limits_run.reset();                 // RAII：擁有者釋放，取代 `delete this`
            if (wxGetApp().mainframe) wxGetApp().mainframe->Close(true);
        });
    }

    std::unique_ptr<PhotoTileEngineHost> m_host;
    wxTimer                  m_beat;
    std::vector<LimitsCase>  m_cases;
    std::vector<std::string> m_rows;
    std::string              m_small, m_big;
    size_t                   m_index = 0;
    double                   m_t0 = 0, m_case_t0 = 0, m_last_beat = 0, m_drift_max = 0, m_drift_max_case = 0;
    bool                     m_sampler_disabled = false;
    long long                m_grid_full = 0, m_grid_down = 0;
    long long                m_bytes_meta_off = 0, m_bytes_meta_on = 0;
    bool                     m_all_ok = true, m_finished = false;

    // 記憶體取樣（背景執行緒）與限記憶體模式
    std::thread              m_sampler;
    std::atomic<bool>        m_sampling{false};
    std::atomic<long>        m_peak_main_kb{0}, m_peak_wv_kb{0};
    std::atomic<int>         m_peak_wv_procs{0};
    double                   m_peak_total_mb = 0;
    long                     m_jobmem_mb = 0;
    bool                     m_jobmem_applied = false;
    std::string              m_jobmem_detail;
};

} // namespace

void run_photo_tile_limits_gate()
{
    g_limits_run.reset(new LimitsRun());
    g_limits_run->start();
}

}} // namespace Slic3r::GUI
