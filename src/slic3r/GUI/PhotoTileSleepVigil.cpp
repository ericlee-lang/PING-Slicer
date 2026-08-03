// =====================================================================
// 照片磚 C-1 閘門②：過夜睡眠守夜（2026-08-01・產品宿主版・照片磚線 PT）
//
// 為什麼要重做一支：0731 那次守夜用的是 **C-0 的 C# spike 宿主**（當時 C++ 宿主還沒編過），
// 只能算「產品引擎頁在別的殼裡撐過一次睡眠」。Codex 重要 #13 點名兩件事，兩件都成立：
//   ① 受測的宿主不是產品宿主  ⇒ 本檔改用 PhotoTileEngineHost（產品真正在用的那一個）
//   ② resume 事件被重複計數  ⇒ 本檔完全不聽電源事件，改用「單調鐘 vs 牆鐘落差」偵測
//   ③ 只睡了 6.4 分鐘        ⇒ 本檔要求**三個**通過的睡眠週期才收工
//
// 【為什麼不聽 WM_POWERBROADCAST】0731 的守夜把 Windows 同一次喚醒發的兩個事件
// （kind 18 與 kind 7）各算一次，報告寫「睡眠事件 2」其實是一次睡眠。要修就得引進
// suspend epoch 去重——但那是在補一個自找的麻煩。落差偵測**在結構上不可能重複計數**：
// 一段落差就是一次事件，沒有「同一次睡眠兩個通知」的概念。
//
// 【偵測原理】睡眠期間 steady_clock（QPC）停走、system_clock（牆鐘）照走，而且
// 心跳計時器整段不會觸發。所以每 5 秒的心跳只要看到「牆鐘跳了 ≥ SLEEP_MIN_SEC」，
// 就是睡過（S3 凍結 QPC，S0 現代待機則是計時器被凍結，兩種都抓得到）。
//
// 【判定・誠實三檔（沿用 0731 的標法，不放水）】
//   真睡過且每次醒來 SHA 全等基準 ＝ 過
//   SHA 不符                       ＝ 敗（觸發轉 A 評估）
//   完全沒睡到                     ＝ inconclusive，**不算過**
//
// 【2026-08-02 二版：窗口語意修正＋電源環境自檢】0801 那夜守了 18 小時、`sleepsDetected: 0`。
// 事後查機器實況才知道**不是使用者忘了睡**：本機電源計畫在 **AC（插電）下「睡眠」與「休眠」
// 的閒置逾時都是 0＝永不**，所以插著電的機器在結構上不可能自己睡；而窗口 13:04 起算、
// 隔天 07:04 到期，機器偏偏 09:12 才進睡眠（一路睡到 15:40＝6.5 小時）——
// **守夜窗在真正的睡眠開始前兩小時就自己收工了**。等於整夜白燒，隔天才發現。
// 兩個修：
//   ① 窗口不再是「16 小時就判 INCONCLUSIVE 收工」，預設拉到 72 小時＝守到驗滿為止，
//      橫跨數夜也沒關係（判準沒放寬，只是別在還能等的時候提早宣布沒等到）。
//   ② 起跑就把電源環境查出來寫進報告；若「插電且永不自動睡」就當場大聲警告，
//      並讓 INCONCLUSIVE 的結論**自己說出原因**——而不是留一句「沒睡到」讓人隔天猜。
//
// 跑法：`--datadir D:\ping-slicer-c1\_vigildata` ＋ `PING_PHOTOTILE_SMOKE=vigil`
//       （可選 PING_PHOTOTILE_VIGIL_HOURS、PING_PHOTOTILE_VIGIL_OUT）
// 報告每次事件都即時落檔＝中途斷電也留得住已驗到的東西。
// =====================================================================

#include "PhotoTileSmoke.hpp"
#include "PhotoTileEngineHost.hpp"
#include "PhotoTileGateJson.hpp"

#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "libslic3r/Utils.hpp"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include <boost/log/trivial.hpp>
#include <boost/nowide/fstream.hpp>

#include <wx/app.h>
#include <wx/datetime.h>
#include <wx/timer.h>

#ifdef _WIN32
#include <windows.h>
#endif

namespace Slic3r { namespace GUI {

namespace {

constexpr int    HEARTBEAT_MS      = 5000;   // 心跳間隔
constexpr double SLEEP_MIN_SEC     = 60.0;   // 牆鐘落差達此值＝判定睡過（避開一般排程抖動）
constexpr int    SETTLE_MS         = 15000;  // 喚醒後先讓系統穩定（網路/顯示/USB 都在恢復）
constexpr int    TARGET_CYCLES     = 3;      // 要驗滿三個睡眠週期
/* 0801 用 16（實跑時以環境變數給 18）——**太短**：機器 09:12 才睡，窗 07:04 就到期了。
   守夜是被動等待，等不到不是失敗、是還沒等到；提早收工只會產出一份沒有資訊量的
   INCONCLUSIVE。預設拉到 72 小時＝可以橫跨三夜，判準一個字都沒放寬。 */
constexpr int    DEFAULT_MAX_HOURS = 72;

double steady_ms()
{
    using namespace std::chrono;
    return duration_cast<duration<double, std::milli>>(steady_clock::now().time_since_epoch()).count();
}
double wall_sec()
{
    using namespace std::chrono;
    return duration_cast<duration<double>>(system_clock::now().time_since_epoch()).count();
}
/* 不含睡眠時間的單調鐘（二輪 B5 的關鍵材料）：QueryUnbiasedInterruptTime 在 S3/S4 期間停走。
   Windows 的 steady_clock＝QPC＝含睡眠，拿它跟牆鐘比會兩邊一起跳、量不到落差。 */
double unbiased_sec()
{
#ifdef _WIN32
    ULONGLONG t100ns = 0;
    if (::QueryUnbiasedInterruptTime(&t100ns)) return (double) t100ns / 1e7;
#endif
    using namespace std::chrono;
    return duration_cast<duration<double>>(steady_clock::now().time_since_epoch()).count();
}
std::string wall_text()
{
    return into_u8(wxDateTime::Now().Format("%Y-%m-%d %H:%M:%S"));
}

/* Windows 的 ::getenv() 回的是**系統 ANSI 碼頁**字串（本機＝CP950）。
   路徑一旦含中文，拿去餵 nowide::ofstream（吃 UTF-8）就是無效序列 ⇒ 開檔失敗。
   2026-08-01 實錄：守夜的 PING_PHOTOTILE_VIGIL_OUT 指到含中文的資料夾，
   報告整份沒寫出來、而且**完全沒有訊息**（見下方 write_report 的第二個修）。
   一律走 wxWidgets 取環境變數（內部是 wide API），轉成 UTF-8 才安全。 */
std::string env_utf8(const char* name)
{
    wxString v;
    if (!wxGetEnv(wxString::FromUTF8(name), &v)) return std::string();
    return into_u8(v);
}

/* ── 電源環境自檢（2026-08-02 新增）────────────────────────────────────
   守夜唯一的失效模式就是「機器根本沒睡」，而那件事**開跑前就查得出來**：
   電源計畫的睡眠／休眠閒置逾時是 0 就代表永不自動睡。0801 白守一夜的代價
   是隔天才知道，所以這段不是裝飾——它把「等不到」從隔天的謎題變成起跑時的警告。

   為什麼動態載入 PowrProf.dll：只為了讀兩個設定值就去改 CMake 連 PowrProf.lib
   不划算，而且讀不到也不該讓守夜起不來（查不到就記 -1，照常守）。 */
struct PowerEnv
{
    bool probed          = false;
    bool on_ac           = true;
    long ac_standby_sec  = -1;   // -1＝查不到；0＝永不自動進入睡眠
    long dc_standby_sec  = -1;
    long ac_hibernate_sec = -1;
    long dc_hibernate_sec = -1;

    // 「以目前的供電狀態，機器不可能自己睡」——人不動手就一定守不到
    bool auto_sleep_impossible() const
    {
        const long standby = on_ac ? ac_standby_sec : dc_standby_sec;
        const long hib     = on_ac ? ac_hibernate_sec : dc_hibernate_sec;
        return standby == 0 && hib == 0;
    }
    std::string summary() const
    {
        if (!probed) return "查不到電源設定";
        auto t = [](long s) {
            if (s < 0) return std::string("?");
            if (s == 0) return std::string("永不");
            return std::to_string(s / 60) + " 分";
        };
        return std::string(on_ac ? "插電(AC)" : "電池(DC)") +
               "；AC 睡眠 " + t(ac_standby_sec) + "／休眠 " + t(ac_hibernate_sec) +
               "，DC 睡眠 " + t(dc_standby_sec) + "／休眠 " + t(dc_hibernate_sec);
    }
};

PowerEnv probe_power_env()
{
    PowerEnv e;
#ifdef _WIN32
    SYSTEM_POWER_STATUS sps{};
    if (::GetSystemPowerStatus(&sps)) {
        e.on_ac  = (sps.ACLineStatus == 1);
        e.probed = true;
    }
    // GUID 就地定義：不同 SDK 版本對這幾顆的宣告位置不一致，抄值最穩
    static const GUID kSleepSub  = { 0x238C9FA8, 0x0AAD, 0x41ED, { 0x83, 0xF4, 0x97, 0xBE, 0x24, 0x2C, 0x8F, 0x20 } };
    static const GUID kStandby   = { 0x29F6C1DB, 0x86DA, 0x48C5, { 0x9F, 0xDB, 0xF2, 0xB6, 0x7B, 0x1F, 0x44, 0xDA } };
    static const GUID kHibernate = { 0x9D7815A6, 0x7EE4, 0x497E, { 0x88, 0x88, 0x51, 0x5A, 0x05, 0xF0, 0x23, 0x64 } };

    typedef DWORD(WINAPI * FnGetScheme)(HKEY, GUID**);
    typedef DWORD(WINAPI * FnReadValue)(HKEY, const GUID*, const GUID*, const GUID*, LPDWORD);
    if (HMODULE h = ::LoadLibraryW(L"PowrProf.dll")) {
        auto get_scheme = (FnGetScheme)  ::GetProcAddress(h, "PowerGetActiveScheme");
        auto read_ac    = (FnReadValue)  ::GetProcAddress(h, "PowerReadACValueIndex");
        auto read_dc    = (FnReadValue)  ::GetProcAddress(h, "PowerReadDCValueIndex");
        GUID* scheme = nullptr;
        if (get_scheme && read_ac && read_dc &&
            get_scheme(nullptr, &scheme) == ERROR_SUCCESS && scheme) {
            DWORD v = 0;
            if (read_ac(nullptr, scheme, &kSleepSub, &kStandby,   &v) == ERROR_SUCCESS) e.ac_standby_sec   = (long) v;
            if (read_dc(nullptr, scheme, &kSleepSub, &kStandby,   &v) == ERROR_SUCCESS) e.dc_standby_sec   = (long) v;
            if (read_ac(nullptr, scheme, &kSleepSub, &kHibernate, &v) == ERROR_SUCCESS) e.ac_hibernate_sec = (long) v;
            if (read_dc(nullptr, scheme, &kSleepSub, &kHibernate, &v) == ERROR_SUCCESS) e.dc_hibernate_sec = (long) v;
            ::LocalFree(scheme);
            e.probed = true;
        }
        ::FreeLibrary(h);
    }
#endif
    return e;
}

/* ── 自動睡眠（opt-in，預設關）─────────────────────────────────────────
   `PING_PHOTOTILE_VIGIL_AUTOSLEEP=<n>`：自己讓機器睡 n 次（每次 AUTOSLEEP_SEC 秒），
   用 RTC 喚醒定時器叫醒。用途＝不必等三個晚上就能拿到**真實 S3 睡眠**的證據。
   ⚠ 這是真的把使用者的機器弄睡，所以：①預設關 ②只有人明確授權才設這個變數
     ③自動睡出來的週期會在報告裡標 `trigger:"auto"`，而且**短睡不得冒充過夜**
       （verdict 會走 PASS_SHORT，見 verdict()）。

   本機前置條件都查過了：S3 可用、AC 上 RTCWAKE=1（允許喚醒定時器）。 */
constexpr int DEFAULT_AUTOSLEEP_SEC = 180;

#ifdef _WIN32
// SetSuspendState 需要 SE_SHUTDOWN_NAME；沒有這一步會靜默失敗（回 FALSE 而已）
bool enable_shutdown_privilege()
{
    HANDLE tok = nullptr;
    if (!::OpenProcessToken(::GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &tok)) return false;
    TOKEN_PRIVILEGES tp{};
    tp.PrivilegeCount = 1;
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
    bool ok = ::LookupPrivilegeValueW(nullptr, SE_SHUTDOWN_NAME, &tp.Privileges[0].Luid) != 0;
    if (ok) {
        ::AdjustTokenPrivileges(tok, FALSE, &tp, sizeof(tp), nullptr, nullptr);
        ok = (::GetLastError() == ERROR_SUCCESS);
    }
    ::CloseHandle(tok);
    return ok;
}

HANDLE g_wake_timer = nullptr;

// 先設好喚醒定時器再睡；定時器一定要在睡之前設，睡著之後就沒人設得了
bool arm_wake_timer(int seconds, std::string& detail)
{
    if (!g_wake_timer) g_wake_timer = ::CreateWaitableTimerW(nullptr, TRUE, nullptr);
    if (!g_wake_timer) { detail = "CreateWaitableTimer 失敗 err=" + std::to_string((long) ::GetLastError()); return false; }
    LARGE_INTEGER due;
    due.QuadPart = -(LONGLONG) seconds * 10000000LL;   // 負值＝相對時間，單位 100ns
    if (!::SetWaitableTimer(g_wake_timer, &due, 0, nullptr, nullptr, TRUE /* fResume */)) {
        detail = "SetWaitableTimer 失敗 err=" + std::to_string((long) ::GetLastError());
        return false;
    }
    detail = std::to_string(seconds) + " 秒後由 RTC 喚醒";
    return true;
}

/* 【二輪 I9】suspend 失敗後必須拆掉已上膛的喚醒定時器：留著的話，使用者稍後的**真**睡眠
   會被這顆殘留 RTC 提早叫醒（把別人的夜攪了還查不到兇手）。 */
void cancel_wake_timer()
{
    if (g_wake_timer) ::CancelWaitableTimer(g_wake_timer);
}

bool suspend_now(std::string& detail)
{
    typedef BOOLEAN(WINAPI * FnSetSuspendState)(BOOLEAN, BOOLEAN, BOOLEAN);
    HMODULE h = ::LoadLibraryW(L"PowrProf.dll");
    if (!h) { detail = "載入 PowrProf.dll 失敗"; return false; }
    auto fn = (FnSetSuspendState) ::GetProcAddress(h, "SetSuspendState");
    bool ok = false;
    if (fn) ok = fn(FALSE /* 睡眠不休眠 */, FALSE, FALSE) != 0;
    else    detail = "取不到 SetSuspendState";
    ::FreeLibrary(h);
    if (fn && !ok) detail = "SetSuspendState 回 FALSE err=" + std::to_string((long) ::GetLastError());
    return ok;
}
#endif

class VigilRun;
std::unique_ptr<VigilRun> g_vigil;

class VigilRun : public wxEvtHandler
{
public:
    VigilRun() : m_host(new PhotoTileEngineHost())
    {
        const std::string hours_env = env_utf8("PING_PHOTOTILE_VIGIL_HOURS");
        m_max_hours = hours_env.empty() ? (double) DEFAULT_MAX_HOURS : ::atof(hours_env.c_str());
        const std::string sim_env = env_utf8("PING_PHOTOTILE_VIGIL_SIMULATE_WAKE");
        m_simulate_wakes = sim_env.empty() ? 0 : ::atoi(sim_env.c_str());
        const std::string auto_env = env_utf8("PING_PHOTOTILE_VIGIL_AUTOSLEEP");
        m_autosleep_left = auto_env.empty() ? 0 : ::atoi(auto_env.c_str());
        const std::string autos_env = env_utf8("PING_PHOTOTILE_VIGIL_AUTOSLEEP_SEC");
        m_autosleep_sec  = autos_env.empty() ? DEFAULT_AUTOSLEEP_SEC : ::atoi(autos_env.c_str());
        // 二輪 I9：秒數 clamp 60..3600——0/負值會讓定時器先於睡眠觸發＝失去喚醒保障
        m_autosleep_sec  = std::max(60, std::min(3600, m_autosleep_sec));
        const std::string out_env = env_utf8("PING_PHOTOTILE_VIGIL_OUT");
        m_out_path = !out_env.empty() ? out_env
                                      : data_dir() + "/phototile_vigil_report.json";

        m_host->set_status_handler([this](const std::string& s, const std::string& d) {
            add_event(s, d);
            if (s == "rebuilding")  ++m_rebuilds;
            if (s == "unavailable") { m_fatal = "引擎不可用：" + d; write_report(); }
        });
        m_host->set_result_handler([this](const PhotoTileEngineResult& r) { on_result(r); });

        m_beat.SetOwner(this);
        Bind(wxEVT_TIMER, [this](wxTimerEvent&) { heartbeat(); });
    }
    ~VigilRun() override { m_beat.Stop(); }

    void start()
    {
        m_t0_steady     = steady_ms();
        m_last_wall     = wall_sec();
        m_last_unbiased = unbiased_sec();
        m_started_at  = wall_text();
        m_image = write_photo_tile_test_image();     // 與閘門①同一張決定性測試圖
        add_event("vigil_start", "產品宿主守夜開始；報告＝" + m_out_path);
        m_power = probe_power_env();
        add_event("power_env", m_power.summary());
        if (m_power.auto_sleep_impossible()) {
            /* 這是 0801 白守一夜的真因。起跑就喊出來，別讓它變成隔天的謎題。 */
            add_event("vigil_warning",
                      "⚠ 目前供電狀態下「睡眠」與「休眠」閒置逾時都是『永不』"
                      "⇒ 機器不會自己睡，除非有人手動睡眠／闔蓋／改電源設定，"
                      "否則本次守夜必然是 INCONCLUSIVE。");
            BOOST_LOG_TRIVIAL(warning)
                << "PhotoTile 守夜：機器在目前供電狀態下不會自動睡眠（" << m_power.summary() << "）";
        }
        write_report();
        if (!m_host->start()) { m_fatal = "宿主啟動失敗"; write_report(); return; }
        m_beat.Start(HEARTBEAT_MS);
        run_job("baseline");
    }

private:
    void run_job(const std::string& tag)
    {
        // 與閘門①／0731 守夜基準**完全相同**的參數：SHA 才有可比性
        PhotoTileEngineRequest req;
        req.job_id     = "vigil-" + tag;
        req.mode       = "dual";  req.nozzle = 0.4;
        req.width_mm   = 60.0;    req.height_mm = 45.0; req.thick_mm = 6.0;
        req.klevels    = 6;       req.noise_mm  = 2.0;
        req.pillar     = false;   req.teeth = false;    req.p2a_block = false;
        req.image_path = m_image;
        req.want_metadata = false;
        m_job_tag  = tag;
        m_job_t0   = steady_ms();
        m_job_in_flight = true;
        m_host->generate(req);
    }

    void on_result(const PhotoTileEngineResult& r)
    {
        const double ms = steady_ms() - m_job_t0;
        m_job_in_flight = false;
        m_wake_pending  = false;
        if (!r.ok) {
            add_event("job_failed", m_job_tag + " → " + r.error_code + "：" + r.error_message);
            if (m_job_tag == "baseline") { m_fatal = "基準生成失敗：" + r.error_code; }
            else                         { m_mismatch = true; }   // 醒來後跑不出來＝閘門②失敗
            write_report();
            return;
        }
        if (m_job_tag == "baseline") {
            m_baseline_sha = r.sha256;
            m_baseline_bytes = (long long) r.three_mf.size();
            m_baseline_matches_smoke = (r.sha256 == std::string(PHOTOTILE_SMOKE_EXPECTED_SHA));
            add_event("baseline_ok", "SHA " + r.sha256 + "（" + std::to_string(m_baseline_bytes) +
                                     " bytes、" + std::to_string((long) ms) + "ms；與閘門①基準" +
                                     (m_baseline_matches_smoke ? "一致" : "**不一致**") + "）");
            add_event("vigil_armed", "現在可以讓機器睡覺了；喚醒後會自動重跑同一張圖並比對 SHA。"
                                     "需要 " + std::to_string(TARGET_CYCLES) + " 個睡眠週期。");
            write_report();
            maybe_autosleep();
            return;
        }
        // 醒來後的複跑
        Cycle c;
        c.index        = (int) m_cycles.size() + 1;
        c.trigger      = m_last_trigger;
        c.slept_minutes = m_last_slept_min;
        c.sha           = r.sha256;
        c.matches       = (r.sha256 == m_baseline_sha);
        c.ms            = ms;
        c.rebuilds      = m_rebuilds;
        m_cycles.push_back(c);
        if (!c.matches) m_mismatch = true;
        add_event("post_wake_check", "第 " + std::to_string(c.index) + " 輪：SHA " +
                                     (c.matches ? "一致" : "**不一致**") + "（睡 " +
                                     std::to_string((long) c.slept_minutes) + " 分、" +
                                     std::to_string((long) ms) + "ms、重建 " + std::to_string(c.rebuilds) + " 次）");
        write_report();
        if ((int) m_cycles.size() >= TARGET_CYCLES || m_mismatch) { conclude(); return; }
        maybe_autosleep();
    }

    /* 自動睡眠：等引擎回穩幾秒 → 先設 RTC 喚醒定時器 → 才叫系統睡。
       順序不能顛倒（睡著之後沒人設得了定時器），而且定時器設不起來就**不睡**——
       寧可少一個週期，也不要把使用者的機器弄睡卻叫不醒。 */
    void maybe_autosleep()
    {
        if (m_autosleep_left <= 0 || m_concluded) return;
#ifdef _WIN32
        m_sleep_timer.reset(new wxTimer(this));
        Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
            if (m_sleep_timer) m_sleep_timer->Stop();
            if (m_concluded || m_autosleep_left <= 0) return;
            if (!m_shutdown_priv_ok) {
                m_shutdown_priv_ok = enable_shutdown_privilege();
                if (!m_shutdown_priv_ok) {
                    add_event("autosleep_failed", "拿不到 SE_SHUTDOWN 權限，改為等待自然睡眠");
                    m_autosleep_left = 0; write_report(); return;
                }
            }
            std::string detail;
            if (!arm_wake_timer(m_autosleep_sec, detail)) {
                add_event("autosleep_failed", "喚醒定時器設定失敗（" + detail + "）⇒ 不睡，改為等待自然睡眠");
                m_autosleep_left = 0; write_report(); return;
            }
            --m_autosleep_left;
            m_autosleep_used = true;
            m_pending_auto   = true;
            add_event("autosleep_arm", "自動睡眠：" + detail + "（剩餘 " + std::to_string(m_autosleep_left) + " 次）");
            write_report();
            std::string serr;
            if (!suspend_now(serr)) {
                m_pending_auto = false;
                cancel_wake_timer();   // 二輪 I9：定時器已上膛但沒睡成＝必拆，防殘留早叫醒
                add_event("autosleep_failed", "SetSuspendState 失敗（" + serr + "）⇒ 喚醒定時器已取消、改為等待自然睡眠");
                m_autosleep_left = 0; write_report();
            }
        }, m_sleep_timer->GetId());
        m_sleep_timer->StartOnce(8000);
#endif
    }

    void heartbeat()
    {
        /* 【二輪 B5】真正的雙鐘比對：睡眠落差 ＝ 牆鐘走掉的 − 單調鐘走掉的。
           一版只看「牆鐘 − 5 秒」＝把 NTP 前跳、modal/重載卡死 UI ≥65 秒都記成 natural 睡眠
           （0803 事故已示範 modal 能餓死佇列 65 秒以上——同機制就能偽造睡眠週期）。
           S3/S4 期間 QueryUnbiasedInterruptTime（不含睡眠）停走、牆鐘照走 ⇒ 兩鐘差＝真睡眠長度；
           NTP 跳／UI 卡死時兩鐘同步走 ⇒ 差≈0，不誤判。
           ⚠ steady_clock 在 Windows＝QPC＝**含**睡眠時間，所以這裡特別用 unbiased 時鐘。 */
        const double now_wall     = wall_sec();
        const double now_unbiased = unbiased_sec();
        double gap = (now_wall - m_last_wall) - (now_unbiased - m_last_unbiased);
        m_last_wall     = now_wall;
        m_last_unbiased = now_unbiased;

        /* 【僅測試用】PING_PHOTOTILE_VIGIL_SIMULATE_WAKE=n：在守夜開始 20 秒後
           注入 n 次假的睡眠落差。用途＝**在不真的讓機器睡覺的情況下**驗證喚醒之後那段
           （重跑基準案／SHA 比對／週期記帳）真的會動。
           為什麼要這個鉤：落差偵測本身只有三行、失效模式是「永遠不觸發」＝報告誠實寫
           INCONCLUSIVE，不會假 PASS；但喚醒後那段有真邏輯，沒跑過就不算驗過。
           ⚠ 它只偽造「落差」，SHA 比對仍是真的跑真引擎。 */
        if (m_simulate_wakes > 0 && (steady_ms() - m_t0_steady) > 20000.0 &&
            !m_job_in_flight && !m_wake_pending) {
            --m_simulate_wakes;
            gap = SLEEP_MIN_SEC * 2;                  // 假裝睡了兩分鐘
            m_simulated_used = true;
        }

        /* 【二輪 B5】守門條件補齊：複跑還沒回來（wake_pending）或 job 進行中不認新落差——
           一版這兩個守門只掛在模擬分支，真實分支漏了＝理論上可重複計數。 */
        if (gap >= SLEEP_MIN_SEC && !m_wake_pending && !m_job_in_flight) {
            // 一段雙鐘落差＝一次睡眠。
            m_last_slept_min = gap / 60.0;
            m_wake_pending   = true;      // 這次喚醒的複跑還沒回來前，不再認第二次
            ++m_sleep_count;
            m_last_trigger   = m_pending_auto ? "auto" : "natural";
            m_pending_auto   = false;
            add_event("wake_detected", "偵測到睡眠 " + std::to_string((long) m_last_slept_min) +
                                       " 分鐘（牆鐘落差 " + std::to_string((long) gap) + " 秒、觸發＝" +
                                       m_last_trigger + "）");
            write_report();
            // 讓系統先穩定再測——剛醒來時顯示/GPU/網路都還在恢復，這時候量到的不是常態
            m_settle_timer.reset(new wxTimer(this));
            Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
                if (m_settle_timer) m_settle_timer->Stop();
                if (m_concluded) return;
                add_event("post_wake_job", "喚醒後重跑基準案");
                run_job("wake-" + std::to_string(m_sleep_count));
            }, m_settle_timer->GetId());
            m_settle_timer->StartOnce(SETTLE_MS);
        }

        const double elapsed_h = (steady_ms() - m_t0_steady) / 3600000.0;
        if (elapsed_h >= m_max_hours && !m_concluded) {
            add_event("window_expired", "守夜窗 " + std::to_string((long) m_max_hours) + " 小時到期（" +
                                        std::to_string(m_sleep_count) + " 次睡眠／" +
                                        std::to_string(m_cycles.size()) + " 輪已驗）");
            conclude();
        }
    }

    void conclude()
    {
        if (m_concluded) return;
        m_concluded = true;
        m_beat.Stop();
        cancel_wake_timer();   // 二輪 I9：收工時拆掉任何仍上膛的 RTC 定時器
        add_event("vigil_end", verdict());
        write_report();
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 守夜結束：" << verdict() << "（報告 " << m_out_path << "）";
        m_host->shutdown();
        /* 跑完自己關掉 app：守夜是無人值守跑的（整夜），關掉才能讓自動化收報告、
           也不會一直佔著 OrcaSlicer.dll 讓下一次建置 LNK1104（0801 實際踩過一次）。
           PING_PHOTOTILE_VIGIL_KEEP_OPEN=1 可留著（人要親眼看結論時用）。 */
        const std::string keep = env_utf8("PING_PHOTOTILE_VIGIL_KEEP_OPEN");
        const bool  keep_open = !keep.empty() && keep != "0";
        wxTheApp->CallAfter([keep_open]() {
            g_vigil.reset();
            if (!keep_open && wxGetApp().mainframe) wxGetApp().mainframe->Close(true);
        });
    }

    // 誠實三檔：沒睡到就是 inconclusive，不准當作過
    std::string verdict() const
    {
        /* ⚠ 只要用過模擬喚醒，這份報告就**不得**標成閘門②通過——它驗的是喚醒後那段
           程式碼，不是機器真的睡過。標成 PASS 就會變成我們正在消滅的那種假綠燈
           （0801 Codex 審查的核心指控就是「報告自己寫著沒命中卻標 pass」）。 */
        const std::string sim = m_simulated_used ? "（含模擬喚醒，不算閘門②證據）" : "";
        if (!m_fatal.empty())                       return "FAIL：" + m_fatal + sim;
        if (m_mismatch)                             return "FAIL：喚醒後結果與基準不符" + sim;
        if (m_simulated_used)
            return "SIMULATED：喚醒後路徑已驗（" + std::to_string(m_cycles.size()) +
                   " 輪 SHA 全等），但睡眠是**模擬**的 ⇒ 閘門② 仍未通過";
        if ((int) m_cycles.size() >= TARGET_CYCLES) {
            /* 【二輪 I13】基準若與閘門①黃金不一致，「每次醒來都一樣」只證明**穩定地錯**——
               不得當閘門②證據。一版把這欄寫進報告卻沒進 verdict（假綠燈家族）。 */
            if (!m_baseline_matches_smoke)
                return "RESUME_STABLE_BUT_GOLDEN_MISMATCH：睡眠喚醒後輸出穩定，"
                       "但基準本身 ≠ 閘門①黃金 ⇒ **不算閘門②證據**，先查基準為何漂移";
            /* 【二輪 B5④】命名照證據強度分三級，「過夜」門檻＝單一週期 ≥6 小時：
               60 分鐘只是「較長的 resume」，叫 PASS 會讓人以為過夜證完了（Codex 直球打中）。 */
            double longest = 0;
            for (const Cycle& c : m_cycles) longest = std::max(longest, c.slept_minutes);
            if (longest < 60.0)
                return "PASS_SHORT：" + std::to_string(TARGET_CYCLES) +
                       " 個真實睡眠週期 SHA 全等基準，但最長只睡 " + std::to_string((long) longest) +
                       " 分鐘" + (m_autosleep_used ? "（自動觸發）" : "") +
                       " ⇒ **過夜**仍未證明，閘門②維持 PARTIAL";
            if (longest < 360.0)
                return "PASS_RESUME：" + std::to_string(TARGET_CYCLES) +
                       " 個真實睡眠週期 SHA 全等基準（最長 " + std::to_string((long) longest) +
                       " 分）＝多次 suspend/resume 已證；**整夜（≥6h 單一週期）另計、尚未達成**";
            return "PASS_OVERNIGHT：" + std::to_string(TARGET_CYCLES) +
                   " 個真實睡眠週期 SHA 全等基準，且最長單一週期 " + std::to_string((long) longest) +
                   " 分（≥6h）＝**過夜**證據成立";
        }
        if (m_cycles.empty())
            /* 「沒睡到」要**自己說出為什麼**。0801 那份報告只寫了「完全沒睡到」，
               隔天得反查 Windows 事件記錄與電源計畫才知道是機器設定不可能睡。 */
            return std::string("INCONCLUSIVE：觀察窗內完全沒睡到") +
                   (m_power.auto_sleep_impossible()
                        ? "——本機在" + std::string(m_power.on_ac ? "插電" : "電池") +
                          "狀態下睡眠與休眠的閒置逾時都是『永不』，機器不可能自己睡；"
                          "要嘛人工睡眠／闔蓋，要嘛改電源設定，否則再守幾夜結果一樣（" +
                          m_power.summary() + "）"
                        : "");
        return "PARTIAL：只驗到 " + std::to_string(m_cycles.size()) + " / " +
               std::to_string(TARGET_CYCLES) + " 個睡眠週期";
    }

    void add_event(const std::string& ev, const std::string& detail)
    {
        Event e;
        e.at_ms  = steady_ms() - m_t0_steady;
        e.wall   = wall_text();
        e.ev     = ev;
        e.detail = detail;
        m_events.push_back(e);
        BOOST_LOG_TRIVIAL(info) << "PhotoTile 守夜 [" << ev << "] " << detail;
    }

    void write_report()
    {
        std::ostringstream j;
        j << "{\n"
          << "  " << jfield("_note", "照片磚 C-1 閘門②：產品宿主過夜睡眠守夜（PhotoTileEngineHost）") << ",\n"
          << "  " << jfield("host", "product (PhotoTileEngineHost)") << ",\n"
          << "  " << jfield("verdict", verdict()) << ",\n"
          << "  " << jfield("startedAt", m_started_at) << ",\n"
          << "  " << jfield("maxHours", m_max_hours) << ",\n"
          << "  " << jfield("targetCycles", TARGET_CYCLES) << ",\n"
          << "  " << jfield("baselineSha", m_baseline_sha) << ",\n"
          << "  " << jfield("baselineBytes", m_baseline_bytes) << ",\n"
          << "  " << jfield("baselineMatchesGate1", m_baseline_matches_smoke) << ",\n"
          << "  " << jfield("sleepsDetected", m_sleep_count) << ",\n"
          << "  " << jstr("powerEnv") << ": { "
          << jfield("probed", m_power.probed) << ", "
          << jfield("onAC", m_power.on_ac) << ", "
          << jfield("acStandbyIdleSec", (int) m_power.ac_standby_sec) << ", "
          << jfield("acHibernateIdleSec", (int) m_power.ac_hibernate_sec) << ", "
          << jfield("dcStandbyIdleSec", (int) m_power.dc_standby_sec) << ", "
          << jfield("dcHibernateIdleSec", (int) m_power.dc_hibernate_sec) << ", "
          << jfield("autoSleepImpossible", m_power.auto_sleep_impossible()) << ", "
          << jfield("summary", m_power.summary()) << " },\n"
          << "  " << jfield("simulatedWakeUsed", m_simulated_used) << ",\n"
          << "  " << jfield("autoSleepUsed", m_autosleep_used) << ",\n"
          << "  " << jfield("autoSleepSec", m_autosleep_sec) << ",\n"
          << "  " << jfield("countsAsGate2Evidence", !m_simulated_used && !m_cycles.empty()) << ",\n"
          << "  " << jfield("verifiedCycles", (int) m_cycles.size()) << ",\n"
          << "  " << jfield("rebuilds", m_rebuilds) << ",\n"
          << "  " << jfield("mismatch", m_mismatch) << ",\n"
          << "  " << jstr("cycles") << ": [\n";
        for (size_t i = 0; i < m_cycles.size(); ++i) {
            const Cycle& c = m_cycles[i];
            j << "    { " << jfield("cycle", c.index) << ", " << jfield("trigger", c.trigger)
              << ", " << jfield("sleptMinutes", c.slept_minutes)
              << ", " << jfield("sha256", c.sha) << ", " << jfield("matchesBaseline", c.matches)
              << ", " << jfield("ms", (long) c.ms) << ", " << jfield("rebuilds", c.rebuilds) << " }"
              << (i + 1 < m_cycles.size() ? ",\n" : "\n");
        }
        j << "  ],\n"
          << "  " << jstr("events") << ": [\n";
        for (size_t i = 0; i < m_events.size(); ++i) {
            const Event& e = m_events[i];
            j << "    { " << jfield("atMs", (long) e.at_ms) << ", " << jfield("wall", e.wall)
              << ", " << jfield("ev", e.ev) << ", " << jfield("detail", e.detail) << " }"
              << (i + 1 < m_events.size() ? ",\n" : "\n");
        }
        j << "  ]\n}\n";
        /* 寫檔失敗**不得靜默**：守夜是無人值守跑整夜的，報告寫不出來又不吭聲，
           隔天只會看到「什麼都沒有」而完全不知道發生什麼事（2026-08-01 已實際踩過一次）。
           第一次失敗大聲記一筆，之後不再洗版。 */
        bool wrote = false;
        try {
            boost::nowide::ofstream f(m_out_path);
            if (f) { f << j.str(); wrote = f.good(); }
        } catch (const std::exception& e) {
            if (!m_write_failed) BOOST_LOG_TRIVIAL(error) << "PhotoTile 守夜報告寫檔丟例外：" << e.what();
        } catch (...) {}
        if (!wrote && !m_write_failed) {
            m_write_failed = true;
            BOOST_LOG_TRIVIAL(error) << "PhotoTile 守夜報告寫不進 " << m_out_path
                                     << "（之後不再重複回報；請確認路徑存在且可寫）";
        }
    }

    struct Cycle { int index = 0; double slept_minutes = 0; std::string sha; bool matches = false;
                   double ms = 0; int rebuilds = 0; std::string trigger = "natural"; };
    struct Event { double at_ms = 0; std::string wall, ev, detail; };

    std::unique_ptr<PhotoTileEngineHost> m_host;
    PowerEnv                 m_power;
    wxTimer                  m_beat;
    std::unique_ptr<wxTimer> m_settle_timer;
    std::unique_ptr<wxTimer> m_sleep_timer;
    std::string              m_last_trigger = "natural";
    int                      m_autosleep_left = 0, m_autosleep_sec = DEFAULT_AUTOSLEEP_SEC;
    bool                     m_autosleep_used = false, m_pending_auto = false, m_shutdown_priv_ok = false;
    std::vector<Cycle>       m_cycles;
    std::vector<Event>       m_events;
    std::string m_image, m_out_path, m_started_at, m_baseline_sha, m_job_tag, m_fatal;
    double      m_t0_steady = 0, m_last_wall = 0, m_last_unbiased = 0, m_job_t0 = 0, m_max_hours = DEFAULT_MAX_HOURS;
    double      m_last_slept_min = 0;
    long long   m_baseline_bytes = 0;
    int         m_sleep_count = 0, m_rebuilds = 0, m_simulate_wakes = 0;
    bool        m_job_in_flight = false, m_simulated_used = false, m_wake_pending = false;
    bool        m_write_failed = false;
    bool        m_mismatch = false, m_concluded = false, m_baseline_matches_smoke = false;
};

} // namespace

void run_photo_tile_sleep_vigil()
{
    g_vigil.reset(new VigilRun());
    g_vigil->start();
}

}} // namespace Slic3r::GUI
