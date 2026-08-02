// 照片磚 C-1 閘門①：wx 整合 smoke——量真實 wx 事件圈成本＋跨宿主黃金一致性。
// 規格與判準見 PhotoTileSmoke.hpp 檔頭。

#include "PhotoTileSmoke.hpp"
#include "PhotoTileEngineHost.hpp"
#include "PhotoTileGateJson.hpp"

#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "libslic3r/Utils.hpp"

#include <cstdlib>

#include <algorithm>
#include <chrono>
#include <memory>
#include <sstream>
#include <vector>

#include <boost/log/trivial.hpp>
#include <boost/nowide/fstream.hpp>

#include <wx/app.h>
#include <wx/filename.h>
#include <wx/image.h>
#include <wx/msgdlg.h>
#include <wx/timer.h>
#include <wx/window.h>

namespace Slic3r { namespace GUI {

// 守夜（spike 宿主）在 2026-07-31 的基準：同圖同參數
const char* PHOTOTILE_SMOKE_EXPECTED_SHA = "9fb88e34267c27006b20d8760bce4ee15e3aea31a7bf22956d5a47bc69aa29a9";

namespace {

double pct(const std::vector<double>& sorted, double p)
{
    if (sorted.empty()) return 0;
    size_t i = (size_t) (sorted.size() * p);
    if (i >= sorted.size()) i = sorted.size() - 1;
    return sorted[i];
}

// smoke 的生命週期綁在自己身上：跑完才自我銷毀（不擋 UI）
class SmokeRun;
std::unique_ptr<SmokeRun> g_smoke_run;   // 唯一擁有者（Codex #1：取代 `delete this`）

class SmokeRun : public wxEvtHandler
{
public:
    SmokeRun(wxWindow* parent, const std::string& expected_sha)
        : m_parent(parent), m_expected(expected_sha), m_host(new PhotoTileEngineHost())
    {
        m_host->enable_smoke_metrics(true);
        m_host->set_status_handler([this](const std::string& s, const std::string& d) {
            m_log << "[" << s << "] " << d << "\n";
            if (s == "ready" && m_ready_ms < 0) m_ready_ms = now_ms() - m_t0;   // 引擎冷啟動成本
            if (s == "unavailable") finish(false, "engine_unavailable: " + d);
        });
        m_host->set_progress_handler([this](const std::string&, const std::string& stage, const std::string&, double p) {
            m_last_stage = stage; m_last_pct = p;
        });
        m_host->set_result_handler([this](const PhotoTileEngineResult& r) { on_result(r); });

        // 10ms 心跳＝wx 事件圈的探針（比 C# 宿主的 1s 心跳細 100 倍）
        m_beat.SetOwner(this);
        Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
            const double t = now_ms();
            if (m_last_beat > 0) {
                const double drift = (t - m_last_beat) - 10.0;
                // 分相位記錄：冷啟動（app 初始化＋WebView2 首建＋頁面首載）與**穩態生成**
                // 是兩件事，混在一起量會分不出「引擎讓 UI 卡」還是「開機本來就慢」。
                if (drift > 0) {
                    m_drifts.push_back(drift);
                    if (m_round == 0 && !m_first_done) m_drifts_cold.push_back(drift);
                    else                               m_drifts_steady.push_back(drift);
                }
            }
            m_last_beat = t;
            m_host->smoke_heartbeat_tick(10.0);
        });
    }
    ~SmokeRun() override { m_beat.Stop(); }        // m_host 是 unique_ptr（Codex #1）

    void start()
    {
        m_image = write_photo_tile_test_image(480, 360, "phototile_smoke_input.png");
        m_t0 = now_ms();
        m_beat.Start(10);
        m_log << "測試圖：" << m_image << "\n";
        if (!m_host->start()) { finish(false, "host_start_failed"); return; }
        run_job();
    }

private:
    static double now_ms()
    {
        using namespace std::chrono;
        return duration_cast<duration<double, std::milli>>(steady_clock::now().time_since_epoch()).count();
    }

    void run_job()
    {
        PhotoTileEngineRequest req;
        req.job_id     = "smoke-" + std::to_string(m_round + 1);
        req.mode       = "dual";
        req.nozzle     = 0.4;
        req.width_mm   = 60.0;  req.height_mm = 45.0; req.thick_mm = 6.0;
        req.klevels    = 6;     req.noise_mm  = 2.0;
        req.pillar     = false; req.pillar_xy_mm = 25;
        req.teeth      = false; req.p2a_block = false;
        req.image_path = m_image;
        req.want_metadata = false;          // 與守夜基準同條件（metadata 會改變位元組）
        req.env_json   = "{\"smoke\":true}";
        m_job_t0 = now_ms();
        m_host->generate(req);
    }

    void on_result(const PhotoTileEngineResult& r)
    {
        const double ms = now_ms() - m_job_t0;
        if (!r.ok) { finish(false, "job_failed: " + r.error_code + " " + r.error_message); return; }
        m_shas.push_back(r.sha256);
        m_job_ms.push_back(ms);
        m_first_done = true;                       // 第一輪跑完＝冷啟動結束，之後算穩態
        m_log << "第 " << (m_round + 1) << " 輪：" << r.three_mf.size() << " bytes／"
              << (long) ms << " ms／sha " << r.sha256.substr(0, 12) << "…\n";
        // 環境快照原封回傳的驗證（過期即棄的前置條件）
        if (!PhotoTileEngineHost::env_is_fresh(r.env_json, "{\"smoke\":true}"))
            m_env_echo_ok = false;
        if (++m_round < 5) { run_job(); return; }     // 五輪＝1 冷啟動＋4 穩態（單次成功 ≠ 修好）
        finish(true, "done");
    }

    void finish(bool ok, const std::string& why)
    {
        if (m_finished) return;
        m_finished = true;
        m_beat.Stop();

        std::sort(m_drifts.begin(), m_drifts.end());
        std::sort(m_drifts_cold.begin(), m_drifts_cold.end());
        std::sort(m_drifts_steady.begin(), m_drifts_steady.end());
        const double drift_max = m_drifts.empty() ? 0 : m_drifts.back();
        const double drift_p95 = pct(m_drifts, 0.95);
        const double cold_max  = m_drifts_cold.empty() ? 0 : m_drifts_cold.back();
        const double sdy_max   = m_drifts_steady.empty() ? 0 : m_drifts_steady.back();
        const double sdy_p95   = pct(m_drifts_steady, 0.95);
        const auto&  st        = m_host->smoke_stats();
        const bool   sha_same  = !m_shas.empty() &&
                                 std::all_of(m_shas.begin(), m_shas.end(),
                                             [this](const std::string& s) { return s == m_shas[0]; });
        const bool   golden_ok = m_expected.empty() || (!m_shas.empty() && m_shas[0] == m_expected);
        const double job_max   = m_job_ms.empty() ? 0 : *std::max_element(m_job_ms.begin(), m_job_ms.end());

        /* 【2026-08-01 二版・Codex 重要 #6】判準拆成兩個獨立 verdict，不再用一個
           被偷偷放寬的 pass 蓋掉真相。原委：檔頭寫的是「全程」，實作卻在看到冷啟動
           7.2s／漂移 5.6s 的數據**之後**改成只看穩態——那是先射箭再畫靶。
           現在：
             steady   ＝使用者反覆生成時 UI 卡不卡（原本的門檻，不放寬）
             startup  ＝含冷啟動的全程（app 初始化＋WebView2 首建＋頁面首載）
           `ok` 只在**兩個都過**時為 true。產品若要正當地把 cold 排除在外，
           必須先有「閒置預熱」（開 app 就先把引擎建好），那時 startup 才會自然變綠——
           在那之前 startup 紅就是紅，誠實標 PASS_STEADY。 */
        double sdy_job_max = 0;
        for (size_t i = 1; i < m_job_ms.size(); ++i) sdy_job_max = (std::max)(sdy_job_max, m_job_ms[i]);
        const bool pass_drift = sdy_p95 <= 100.0 && sdy_max <= 500.0;
        const bool pass_time  = sdy_job_max <= 6000.0;
        /* ⚠ 起跑延後（PING_PHOTOTILE_SMOKE_DELAY_MS）會把 app 自己的初始化排除在量測外——
           帶延後量到的 startup 數字**不是全程**。所以 startup 只有在 delay==0 時才算數，
           報告一律把延後量寫出來，避免「用延後量的數字宣稱全程過」這種第二次偷換。 */
        const char*  delay_env = ::getenv("PING_PHOTOTILE_SMOKE_DELAY_MS");
        const int    delay_ms  = delay_env ? ::atoi(delay_env) : 0;
        const bool   covers_app_init = (delay_ms == 0);

        const bool pass_steady   = ok && sha_same && golden_ok && m_env_echo_ok && pass_drift && pass_time;
        const bool pass_startup  = drift_p95 <= 100.0 && drift_max <= 500.0 && job_max <= 6000.0;
        const bool pass_all      = pass_steady && pass_startup && covers_app_init;
        const std::string verdict = !pass_steady ? std::string("FAIL")
                                  : (pass_all ? std::string("PASS") : std::string("PASS_STEADY"));

        std::ostringstream j;
        j << "{\n"
          << "  " << jfield("_note", "照片磚 C-1 閘門①：wx 整合 smoke（真 wx 事件圈量測＋跨宿主黃金）") << ",\n"
          // why／verdict／sha 一律走 writer：why 會塞引擎的失敗訊息（含換行與控制字元），
          // 手拼引號會讓報告在**最需要它的那一刻**變成非法 JSON（Codex 次要 #14）
          << "  " << jfield("ok", pass_all) << ", " << jfield("why", why) << ",\n"
          << "  " << jfield("verdict", verdict) << ",\n"
          << "  " << jfield("_verdictMeaning", "PASS＝含冷啟動全程都過｜PASS_STEADY＝穩態過但冷啟動超門檻（產品需閒置預熱才可排除 cold）｜FAIL＝穩態就不過") << ",\n"
          << "  \"steady\": { \"pass\": " << (pass_steady ? "true" : "false")
          << ", \"driftP95Ms\": " << (long) sdy_p95 << ", \"driftMaxMs\": " << (long) sdy_max
          << ", \"jobMsMax\": " << (long) sdy_job_max << " },\n"
          << "  \"startup\": { \"pass\": " << (pass_startup ? "true" : "false")
          << ", \"driftP95Ms\": " << (long) drift_p95 << ", \"driftMaxMs\": " << (long) drift_max
          << ", \"jobMsMax\": " << (long) job_max
          << ", \"startDelayMs\": " << delay_ms
          << ", \"coversAppInit\": " << (covers_app_init ? "true" : "false")
          << ", " << jfield("_note", "門檻與 steady 同（p95≤100／max≤500／單輪≤6000）；不另設寬鬆門檻。"
                                     "startDelayMs>0＝有延後起跑、app 初始化不在量測內 ⇒ 不得據此宣稱全程過") << " },\n"
          << "  \"rounds\": " << m_shas.size() << ", \"shaAllSame\": " << (sha_same ? "true" : "false") << ",\n"
          << "  " << jfield("sha256", m_shas.empty() ? std::string() : m_shas[0]) << ",\n"
          << "  " << jfield("expectedSha", m_expected) << ", \"matchesVigilBaseline\": " << (golden_ok ? "true" : "false") << ",\n"
          << "  \"envEchoOk\": " << (m_env_echo_ok ? "true" : "false") << ",\n"
          << "  \"jobMs\": [";
        for (size_t i = 0; i < m_job_ms.size(); ++i) j << (i ? ", " : "") << (long) m_job_ms[i];
        j << "],\n"
          << "  \"jobMsMaxAll\": " << (long) job_max << ", \"jobMsMaxSteady\": " << (long) sdy_job_max
          << ", \"passTime\": " << (pass_time ? "true" : "false") << ",\n"
          << "  \"wxHeartbeat10ms\": {\n"
          << "    \"_note\": \"冷啟動段（app 初始化＋WebView2 首建＋頁面首載）與穩態段分開；閘門看穩態\",\n"
          << "    \"samplesAll\": " << m_drifts.size()
          << ", \"driftP95MsAll\": " << (long) drift_p95 << ", \"driftMaxMsAll\": " << (long) drift_max << ",\n"
          << "    \"coldStart\": { \"samples\": " << m_drifts_cold.size() << ", \"driftMaxMs\": " << (long) cold_max << " },\n"
          << "    \"steady\": { \"samples\": " << m_drifts_steady.size()
          << ", \"driftP95Ms\": " << (long) sdy_p95 << ", \"driftMaxMs\": " << (long) sdy_max
          << ", \"pass\": " << (pass_drift ? "true" : "false") << " }\n  },\n"
          << "  \"hostReadyMs\": " << (long) m_ready_ms << ",\n"
          << "  \"hostStats\": { \"injectEncodeMs\": " << (long) st.inject_encode_ms
          << ", \"injectDispatchMaxMs\": " << (long) st.inject_dispatch_max_ms
          << ", \"messageHandleMaxMs\": " << (long) st.message_handle_max_ms
          << ", \"chunksReceived\": " << st.chunks_received << " },\n"
          << "  \"totalMs\": " << (long) (now_ms() - m_t0) << "\n}\n";

        const std::string path = data_dir() + "/phototile_smoke_report.json";
        try {
            boost::nowide::ofstream f(path);
            f << j.str();
        } catch (...) { BOOST_LOG_TRIVIAL(warning) << "smoke 報告寫檔失敗"; }

        // 無人值守模式（環境變數 PING_PHOTOTILE_SMOKE）：不彈對話框、跑完自己關 app，
        // 讓 AI 能自動跑閘門而不必勞人去點選單（AI-first 分工）。報告一律落檔。
        const char* headless = ::getenv("PING_PHOTOTILE_SMOKE");
        if (headless != nullptr) {
            BOOST_LOG_TRIVIAL(info) << "PhotoTile smoke 報告：" << path;
            m_host->shutdown();
            wxTheApp->CallAfter([]() {
                g_smoke_run.reset();                 // RAII：擁有者釋放，取代 `delete this`
                if (wxGetApp().mainframe) wxGetApp().mainframe->Close(true);
            });
            return;
        }

        wxString msg;
        msg << (pass_all ? "✅ 閘門① 通過\n\n" : "❌ 閘門① 未通過\n\n")
            << "生成三輪 SHA 一致：" << (sha_same ? "是" : "否") << "\n"
            << "與守夜基準相符：" << (golden_ok ? "是" : "否") << "\n"
            << "單輪最久：" << (long) job_max << " ms（門檻 6000）\n"
            << "wx 心跳漂移 p95／max：" << (long) drift_p95 << "／" << (long) drift_max << " ms（門檻 100／500）\n"
            << "注入編碼（背景執行緒）：" << (long) st.inject_encode_ms << " ms\n"
            << "單則訊息最久：" << (long) st.message_handle_max_ms << " ms\n\n"
            << "報告：" << from_u8(path);
        wxMessageBox(msg, "照片磚引擎 smoke（C-1 閘門①）", wxOK | (pass_all ? wxICON_INFORMATION : wxICON_WARNING), m_parent);

        m_host->shutdown();
        wxTheApp->CallAfter([]() { g_smoke_run.reset(); });
    }

    wxWindow*             m_parent;
    std::string           m_expected;
    std::unique_ptr<PhotoTileEngineHost> m_host;
    wxTimer               m_beat;
    std::vector<double>   m_drifts, m_drifts_cold, m_drifts_steady, m_job_ms;
    bool                  m_first_done = false;
    std::vector<std::string> m_shas;
    std::ostringstream    m_log;
    std::string           m_image, m_last_stage;
    double                m_last_pct = 0, m_last_beat = 0, m_t0 = 0, m_job_t0 = 0, m_ready_ms = -1;
    int                   m_round = 0;
    bool                  m_finished = false, m_env_echo_ok = true;
};

} // namespace

// 與 PhotoTileSleepVigil.MakeTestImage 逐像素相同的決定性測試圖（各閘門共用，宣告見 .hpp）。
// 只要解碼後像素相同，引擎輸出就該相同——PNG 編碼器差異不影響（rgb 值才進格點）。
std::string write_photo_tile_test_image(int W, int H, const char* name)
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

void run_photo_tile_wx_smoke(wxWindow* parent, const std::string& expected_sha)
{
    g_smoke_run.reset(new SmokeRun(parent, expected_sha));
    g_smoke_run->start();
}

}} // namespace Slic3r::GUI
