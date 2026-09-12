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
// 用**最重的合法案**（quad 400mm、K=產品上限、gridMax 預設 3200）：延遲問題只在重案有意義。
// 【K 上限 48→8＝Eric 2026-08-02 裁 B】0802 的 17.6s/4.3s 是 K48 時代的數字；上限改 8 後
// 本量測要重跑重判（mesh 分塊讓步已另證 17.6→1.4s）。
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
#include <cstdlib>          // getenv／atoi（段界延遲的 env 覆寫）
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
    const char* trigger_stage; // 這個 stage 的「段末事件」一到就送 cancel
    double      trigger_end_pct = 0; // 該段結束時的**累計** pct（見下）
    // 結果
    bool   done = false, cancelled_ok = false, cancel_sent = false;
    /* 【C-2 第 6 項】cancel_sent＝「觸發點到了、已排定要取消」；cancel_dispatched＝「200ms
       延遲窗過了、真的送出去了」。兩者要分開：job 若在延遲窗內就自己結束，latencyMs 會拿到
       一個上一支探針留下的 m_cancel_at ⇒ 算出一個**看起來很正常的假數字**。 */
    bool   cancel_dispatched = false;
    double trigger_at_ms = 0;  // job 起跑到觸發點
    double latency_ms = 0;     // cancel → terminal
    std::string terminal_code;
};

/* ⚠ 首跑教訓（0802）：progress 的 pct 是**全程累計值**（stageBase＋權重×frac），不是單段 0〜1。
   一版用 `pct>=1.0` 當觸發 ⇒ 四支探針全部「觸發段未出現」——量測自己誠實喊了失效（這正是
   當初把「cancel 沒送出」設計成顯性欄位的原因，不然就是四個假 0ms）。
   段末累計值抄自 engine.js 的 STAGE_WEIGHT（那邊是 SSOT）：
     decode:0.02 grid:0.10 suggest:0.03 quantize:0.45 filter:0.25 metric:0.03 mesh:0.12
   權重若改，這裡的探針會**大聲失效**（又回到「觸發段未出現」），不會靜默量錯。 */

class CancelLatRun;
std::unique_ptr<CancelLatRun> g_cancel_lat;

class CancelLatRun : public wxEvtHandler
{
public:
    CancelLatRun() : m_host(new PhotoTileEngineHost())
    {
        m_probes.push_back({ "grid",     "decode",   0.02 });
        m_probes.push_back({ "quantize", "suggest",  0.15 });   // 有 tick yield 的段＝對照組
        m_probes.push_back({ "filter",   "quantize", 0.60 });
        m_probes.push_back({ "mesh",     "metric",   0.88 });

        m_host->set_result_handler([this](const PhotoTileEngineResult& r) { on_result(r); });
        m_host->set_progress_handler([this](const std::string& job, const std::string& stage,
                                            const std::string&, double pct) {
            on_progress(job, stage, pct);
        });
        m_host->set_status_handler([this](const std::string& s, const std::string& d) {
            if (s == "unavailable") { m_fatal = "引擎不可用：" + d; conclude(); }
        });

        /* 【C-2 第 6 項】段界競態的延遲送出器。**只建一次、只 Bind 一次**（有別於本檔
           m_guard/m_gap 每次 reset 都再 Bind 一次的舊寫法——wxTimer 用 wxID_ANY 拿到的 id
           在物件銷毀後可能被重用，屆時舊的 lambda 也會跟著被叫到）。 */
        const char* dly = ::getenv("PING_PHOTOTILE_CANCELLAT_DELAY_MS");
        m_trigger_delay_ms = dly ? ::atoi(dly) : 200;
        if (m_trigger_delay_ms < 0) m_trigger_delay_ms = 0;
        m_delay.reset(new wxTimer(this));
        Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
            if (m_delay) m_delay->Stop();
            if (m_index >= m_probes.size() || m_delay_job.empty()) return;
            if (m_delay_job != m_current_job) return;      // 案子已換＝這顆遲到的取消不算數
            if (m_probes[m_index].done) return;            // 延遲窗內就結束了＝不再補送
            m_probes[m_index].cancel_dispatched = true;
            m_cancel_at = cl_now_ms();
            m_host->cancel(m_delay_job);
            BOOST_LOG_TRIVIAL(warning) << "PhotoTile 取消延遲探針 " << m_probes[m_index].name
                                       << "：延遲 " << m_trigger_delay_ms << "ms 後送出 cancel";
        }, m_delay->GetId());
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
        req.klevels    = 8;       req.noise_mm  = 0.0;   // 上限 8＝Eric 2026-08-02 裁 B（合法上限案跟著走）
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
        // 段末事件＝stage 相符且累計 pct 到段末值（pct 被引擎 toFixed(4)，容差 1e-4）
        if (stage == p.trigger_stage && pct + 1e-4 >= p.trigger_end_pct) {
            p.cancel_sent   = true;                 // 標在「決定要取消」的當下＝不會重複觸發
            p.trigger_at_ms = cl_now_ms() - m_job_t0;
            /* 【C-2 第 6 項】段界競態：觸發事件的語意是「**上一段**剛結束」，此刻引擎未必
               已經走進我們要量的那個同步大段。立刻送 cancel 有機會落在前一段還有 tick yield
               的尾巴上被秒回 ⇒ 量到的不是大段長度而是接近 0（0803 首輪 grid 探針 latencyMs=1
               正是這個形狀，而 grid 是公認的同步大段＝數字自相矛盾）。
               延遲一小段再送，確保 cancel 落在目標大段**裡面**；latencyMs 從實際送出算起，
               不含這段延遲，所以語意仍是「按下取消後要等多久」。 */
            m_delay_job = job;
            m_delay->StartOnce(m_trigger_delay_ms);
            BOOST_LOG_TRIVIAL(warning) << "PhotoTile 取消延遲探針 " << p.name << "：觸發段 "
                                       << stage << " 完成（job 第 " << (long) p.trigger_at_ms
                                       << "ms），將於 " << m_trigger_delay_ms << "ms 後送 cancel";
        }
    }

    void on_result(const PhotoTileEngineResult& r)
    {
        if (m_index >= m_probes.size() || r.job_id != m_current_job) return;
        Probe& p = m_probes[m_index];
        if (p.done) return;
        p.done          = true;
        p.terminal_code = r.ok ? "success" : r.error_code;
        if (m_delay) m_delay->Stop();                 // 還沒到點的延遲送出器：這案結束了就收掉
        if (p.cancel_dispatched) {
            p.latency_ms   = cl_now_ms() - m_cancel_at;
            p.cancelled_ok = (!r.ok && r.error_code == "cancelled");
        } else if (p.cancel_sent) {
            /* 觸發到了、但 job 在 200ms 延遲窗內就自己結束 ⇒ cancel 沒真的送出去。
               同樣是量測失效，要跟「觸發段沒出現」分開講，否則下一棒看不出是哪一種。 */
            p.terminal_code += "（觸發後、延遲窗內即結束，cancel 未送出）";
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
          << "  " << jfield("_case", "quad 400mm K=8（產品上限；二輪 I12 起報告寫實際請求值） gridMax=3200") << ",\n"
          << "  " << jfield("requestedK", 8) << ",\n"
          << "  " << jfield("_meaning", "latencyMs＝使用者按取消後實際要等的時間＝該同步大段的不可中斷長度") << ",\n"
          << "  " << jfield("triggerDelayMs", m_trigger_delay_ms) << ",\n"
          << "  " << jfield("_delayNote", "C-2 第 6 項：觸發（上一段結束）後等這麼久才送 cancel，"
                                          "確保落在目標大段裡面；latencyMs 不含這段延遲。"
                                          "PING_PHOTOTILE_CANCELLAT_DELAY_MS 可覆寫（0＝還原舊行為當對照組）") << ",\n"
          << "  " << jfield("totalMs", (long) (cl_now_ms() - m_t0)) << ",\n"
          << "  " << jstr("probes") << ": [\n";
        for (size_t i = 0; i < m_probes.size(); ++i) {
            const Probe& p = m_probes[i];
            j << "    { " << jfield("measures", p.name)
              << ", " << jfield("triggerStage", p.trigger_stage)
              << ", " << jfield("done", p.done)
              << ", " << jfield("cancelSent", p.cancel_sent)
              << ", " << jfield("cancelDispatched", p.cancel_dispatched)
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
    std::unique_ptr<wxTimer> m_guard, m_gap, m_delay;
    std::string m_image, m_current_job, m_fatal, m_delay_job;
    int         m_trigger_delay_ms = 200;      // C-2 第 6 項：段界競態緩衝
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
