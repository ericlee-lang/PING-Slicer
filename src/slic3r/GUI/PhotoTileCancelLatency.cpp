// =====================================================================
// 照片磚 C-1：取消延遲量測（2026-08-02・照片磚線 PT・Codex 重要 #11 後半的「先量」）
//
// 【為什麼是量測不是修改】#11 後半說 grid/filter/mesh 是同步大段、早期取消會等很久。
// 對策「分塊 yield」會動到生成路徑＝黃金位元組的風險區，所以裁定順序是**先量再改**：
// 沒有數字就去重構，等於拿黃金基準去賭一個感覺。
//
// 【量法】引擎一行不動。管線＝decode→[grid]→suggest→[quantize(有tick)]→[filter]→metric→[mesh]，
// 方括號＝沒有中途 yield 的同步大段；而每個大段的**前一段完成時都有 progress(stage,1)**。
// 所以宿主只要「看到觸發段完成就立刻送 cancel」，量 cancel→terminal 的時間，
// 就是那個同步大段的實際不可中斷長度＝使用者按取消後要等的時間。
//
//   探針            觸發（該段 progress=1）   量到的東西
//   grid            decode                    grid 大段
//   quantize(對照)  suggest                   quantize（有 tick yield，理論上快＝對照組）
//   filter          quantize                  filter 大段
//   mesh            metric                    mesh/zip 大段
//
// 用**最重的合法案**（quad 400mm K48、gridMax 預設 3200）：延遲問題只在重案有意義
// （0802 閘門③實測這個案全程 162.8s）。
//
// 【判定】這是量測，不設通過門檻（門檻要等數字出來跟 Eric 一起裁）；
// ok 只代表「四支探針都真的量到 cancelled terminal」＝量測本身有效。
// 跑法：PING_PHOTOTILE_SMOKE=cancellat
// =====================================================================

#include "PhotoTileSmoke.hpp"
#include "PhotoTileEngineHost.hpp"
#include "PhotoTileGateJson.hpp"

#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "libslic3r/Utils.hpp"

#include <chrono>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include <boost/log/trivial.hpp>
#include <boost/nowide/fstream.hpp>

#include <wx/app.h>
#include <wx/timer.h>

namespace Slic3r { namespace GUI {

namespace {

double cl_now_ms()
{
    using namespace std::chrono;
    return duration_cast<duration<double, std::milli>>(steady_clock::now().time_since_epoch()).count();
}

struct Probe
{
    const char* name;          // 量的是哪個同步大段
    const char* trigger_stage; // 這個 stage 完成（pct>=1）就送 cancel
    // 結果
    bool   done = false, cancelled_ok = false, cancel_sent = false;
    double trigger_at_ms = 0;  // job 起跑到觸發點
    double latency_ms = 0;     // cancel → terminal
    std::string terminal_code;
};

class CancelLatRun;
std::unique_ptr<CancelLatRun> g_cancel_lat;

class CancelLatRun : public wxEvtHandler
{
public:
    CancelLatRun() : m_host(new PhotoTileEngineHost())
    {
        m_probes.push_back({ "grid",     "decode"   });
        m_probes.push_back({ "quantize", "suggest"  });   // 有 tick yield 的段＝對照組
        m_probes.push_back({ "filter",   "quantize" });
        m_probes.push_back({ "mesh",     "metric"   });

        m_host->set_result_handler([this](const PhotoTileEngineResult& r) { on_result(r); });
        m_host->set_progress_handler([this](const std::string& job, const std::string& stage,
                                            const std::string&, double pct) {
            on_progress(job, stage, pct);
        });
        m_host->set_status_handler([this](const std::string& s, const std::string& d) {
            if (s == "unavailable") { m_fatal = "引擎不可用：" + d; conclude(); }
        });
    }
    ~CancelLatRun() override = default;

    void start()
    {
        m_t0 = cl_now_ms();
        m_image = write_photo_tile_test_image(480, 360, "phototile_cancellat_input.png");
        if (!m_host->start()) { m_fatal = "宿主啟動失敗"; conclude(); return; }
        run_probe();
    }

private:
    void run_probe()
    {
        if (m_index >= m_probes.size()) { conclude(); return; }
        Probe& p = m_probes[m_index];

        PhotoTileEngineRequest req;
        req.job_id     = std::string("cancellat-") + p.name;
        req.mode       = "quad";  req.nozzle = 0.4;
        req.width_mm   = 400.0;   req.height_mm = 400.0; req.thick_mm = 6.0;
        req.klevels    = 48;      req.noise_mm  = 0.0;
        req.pillar     = false;   req.teeth = false; req.p2a_block = false;
        req.image_path = m_image;
        req.want_metadata = false;
        m_current_job = req.job_id;
        m_job_t0      = cl_now_ms();
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 取消延遲探針 " << p.name
                                   << "（觸發段=" << p.trigger_stage << "）起跑";
        write_report(false);
        m_host->generate(req);

        /* 每支探針的守門逾時：重案全程 ~163s，300s 沒有 terminal＝取消機制本身壞了，
           記失敗、繼續下一支（不讓一支壞探針吊死整個量測）。 */
        m_guard.reset(new wxTimer(this));
        Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
            if (m_guard) m_guard->Stop();
            if (m_index < m_probes.size() && !m_probes[m_index].done) {
                Probe& gp = m_probes[m_index];
                gp.done = true;
                gp.terminal_code = "PROBE_TIMEOUT_300S";
                m_all_ok = false;
                m_host->cancel(m_current_job);   // 盡力而為，別讓下一支探針疊在殘案上
                next();
            }
        }, m_guard->GetId());
        m_guard->StartOnce(300000);
    }

    void on_progress(const std::string& job, const std::string& stage, double pct)
    {
        if (m_index >= m_probes.size() || job != m_current_job) return;
        Probe& p = m_probes[m_index];
        if (p.cancel_sent || p.done) return;
        if (stage == p.trigger_stage && pct >= 1.0) {
            p.cancel_sent   = true;
            p.trigger_at_ms = cl_now_ms() - m_job_t0;
            m_cancel_at     = cl_now_ms();
            m_host->cancel(job);
            BOOST_LOG_TRIVIAL(warning) << "PhotoTile 取消延遲探針 " << p.name << "：觸發段 "
                                       << stage << " 完成（job 第 " << (long) p.trigger_at_ms
                                       << "ms），cancel 已送";
        }
    }

    void on_result(const PhotoTileEngineResult& r)
    {
        if (m_index >= m_probes.size() || r.job_id != m_current_job) return;
        Probe& p = m_probes[m_index];
        if (p.done) return;
        p.done          = true;
        p.terminal_code = r.ok ? "success" : r.error_code;
        if (p.cancel_sent) {
            p.latency_ms   = cl_now_ms() - m_cancel_at;
            p.cancelled_ok = (!r.ok && r.error_code == "cancelled");
        } else {
            /* cancel 根本沒送出去＝觸發段的 progress 沒等到（例如整個 job 比預期早結束）。
               這是量測失效，不是產品失效——誠實記下，別讓它偽裝成「延遲 0ms」。 */
            p.terminal_code += "（觸發段未出現，cancel 未送）";
        }
        if (!p.cancelled_ok) m_all_ok = false;
        if (m_guard) m_guard->Stop();
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 取消延遲探針 " << p.name << "：terminal="
                                   << p.terminal_code << " 延遲=" << (long) p.latency_ms << "ms";
        next();
    }

    void next()
    {
        ++m_index;
        write_report(false);
        /* 探針之間隔 2 秒：讓上一案的殘響（宿主端清 active job）完全落定，
           確保下一支量到的是乾淨的單變數。 */
        m_gap.reset(new wxTimer(this));
        Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
            if (m_gap) m_gap->Stop();
            run_probe();
        }, m_gap->GetId());
        m_gap->StartOnce(2000);
    }

    void write_report(bool final_done)
    {
        std::ostringstream j;
        j << "{\n"
          << "  " << jfield("_note", "照片磚 C-1 取消延遲量測（#11 後半的「先量」；引擎零改動）") << ",\n"
          << "  " << jfield("final", final_done) << ",\n"
          << "  " << jfield("ok", m_all_ok && m_fatal.empty()) << ",\n"
          << "  " << jfield("fatal", m_fatal) << ",\n"
          << "  " << jfield("_case", "quad 400mm K48 gridMax=3200（0802 閘門③同案全程 162.8s）") << ",\n"
          << "  " << jfield("_meaning", "latencyMs＝使用者按取消後實際要等的時間＝該同步大段的不可中斷長度") << ",\n"
          << "  " << jfield("totalMs", (long) (cl_now_ms() - m_t0)) << ",\n"
          << "  " << jstr("probes") << ": [\n";
        for (size_t i = 0; i < m_probes.size(); ++i) {
            const Probe& p = m_probes[i];
            j << "    { " << jfield("measures", p.name)
              << ", " << jfield("triggerStage", p.trigger_stage)
              << ", " << jfield("done", p.done)
              << ", " << jfield("cancelSent", p.cancel_sent)
              << ", " << jfield("triggerAtMsIntoJob", (long) p.trigger_at_ms)
              << ", " << jfield("latencyMs", (long) p.latency_ms)
              << ", " << jfield("cancelledOk", p.cancelled_ok)
              << ", " << jfield("terminalCode", p.terminal_code) << " }"
              << (i + 1 < m_probes.size() ? ",\n" : "\n");
        }
        j << "  ]\n}\n";
        try {
            boost::nowide::ofstream f(data_dir() + "/phototile_cancellat_report.json");
            f << j.str();
        } catch (...) { BOOST_LOG_TRIVIAL(error) << "取消延遲報告寫檔失敗"; }
    }

    void conclude()
    {
        if (m_concluded) return;
        m_concluded = true;
        write_report(true);
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 取消延遲量測結束（ok=" << (m_all_ok && m_fatal.empty()) << "）";
        m_host->shutdown();
        wxTheApp->CallAfter([]() {
            g_cancel_lat.reset();
            if (wxGetApp().mainframe) wxGetApp().mainframe->Close(true);
        });
    }

    std::unique_ptr<PhotoTileEngineHost> m_host;
    std::vector<Probe>       m_probes;
    std::unique_ptr<wxTimer> m_guard, m_gap;
    std::string m_image, m_current_job, m_fatal;
    size_t      m_index = 0;
    double      m_t0 = 0, m_job_t0 = 0, m_cancel_at = 0;
    bool        m_all_ok = true, m_concluded = false;
};

} // namespace

void run_photo_tile_cancel_latency()
{
    g_cancel_lat.reset(new CancelLatRun());
    g_cancel_lat->start();
}

}} // namespace Slic3r::GUI
