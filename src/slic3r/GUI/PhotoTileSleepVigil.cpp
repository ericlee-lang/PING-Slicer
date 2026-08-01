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

namespace Slic3r { namespace GUI {

namespace {

constexpr int    HEARTBEAT_MS      = 5000;   // 心跳間隔
constexpr double SLEEP_MIN_SEC     = 60.0;   // 牆鐘落差達此值＝判定睡過（避開一般排程抖動）
constexpr int    SETTLE_MS         = 15000;  // 喚醒後先讓系統穩定（網路/顯示/USB 都在恢復）
constexpr int    TARGET_CYCLES     = 3;      // 要驗滿三個睡眠週期
constexpr int    DEFAULT_MAX_HOURS = 16;

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
        m_t0_steady   = steady_ms();
        m_last_wall   = wall_sec();
        m_started_at  = wall_text();
        m_image = write_photo_tile_test_image();     // 與閘門①同一張決定性測試圖
        add_event("vigil_start", "產品宿主守夜開始；報告＝" + m_out_path);
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
            return;
        }
        // 醒來後的複跑
        Cycle c;
        c.index        = (int) m_cycles.size() + 1;
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
        if ((int) m_cycles.size() >= TARGET_CYCLES || m_mismatch) conclude();
    }

    void heartbeat()
    {
        const double now_wall = wall_sec();
        double gap = now_wall - m_last_wall - (HEARTBEAT_MS / 1000.0);
        m_last_wall = now_wall;

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

        if (gap >= SLEEP_MIN_SEC) {
            // 一段落差＝一次睡眠。結構上不可能重複計數（不像電源事件會發兩次）。
            m_last_slept_min = gap / 60.0;
            m_wake_pending   = true;      // 這次喚醒的複跑還沒回來前，不再認第二次
            ++m_sleep_count;
            add_event("wake_detected", "偵測到睡眠 " + std::to_string((long) m_last_slept_min) +
                                       " 分鐘（牆鐘落差 " + std::to_string((long) gap) + " 秒）");
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
            add_event("window_expired", "守夜窗 " + std::to_string((long) m_max_hours) + " 小時到期");
            conclude();
        }
    }

    void conclude()
    {
        if (m_concluded) return;
        m_concluded = true;
        m_beat.Stop();
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
        if ((int) m_cycles.size() >= TARGET_CYCLES)
            return "PASS：" + std::to_string(TARGET_CYCLES) + " 個真實睡眠週期 SHA 全等基準";
        if (m_cycles.empty())                       return "INCONCLUSIVE：觀察窗內完全沒睡到";
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
          << "  " << jfield("simulatedWakeUsed", m_simulated_used) << ",\n"
          << "  " << jfield("countsAsGate2Evidence", !m_simulated_used && !m_cycles.empty()) << ",\n"
          << "  " << jfield("verifiedCycles", (int) m_cycles.size()) << ",\n"
          << "  " << jfield("rebuilds", m_rebuilds) << ",\n"
          << "  " << jfield("mismatch", m_mismatch) << ",\n"
          << "  " << jstr("cycles") << ": [\n";
        for (size_t i = 0; i < m_cycles.size(); ++i) {
            const Cycle& c = m_cycles[i];
            j << "    { " << jfield("cycle", c.index) << ", " << jfield("sleptMinutes", c.slept_minutes)
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
                   double ms = 0; int rebuilds = 0; };
    struct Event { double at_ms = 0; std::string wall, ev, detail; };

    std::unique_ptr<PhotoTileEngineHost> m_host;
    wxTimer                  m_beat;
    std::unique_ptr<wxTimer> m_settle_timer;
    std::vector<Cycle>       m_cycles;
    std::vector<Event>       m_events;
    std::string m_image, m_out_path, m_started_at, m_baseline_sha, m_job_tag, m_fatal;
    double      m_t0_steady = 0, m_last_wall = 0, m_job_t0 = 0, m_max_hours = DEFAULT_MAX_HOURS;
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
