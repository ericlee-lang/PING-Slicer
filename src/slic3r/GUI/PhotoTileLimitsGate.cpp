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
// 記憶體峰值由外部（PowerShell）以 1Hz 取樣 msedgewebview2.exe 進程樹，
// 與 C-0 §4.3 同法；本檔只負責跑案例與寫結果。
// =====================================================================

#include "PhotoTileSmoke.hpp"
#include "PhotoTileEngineHost.hpp"

#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "libslic3r/Utils.hpp"

#include <algorithm>
#include <chrono>
#include <sstream>
#include <string>
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
};

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
                if (drift > m_drift_max) m_drift_max = drift;
            }
            m_last_beat = t;
        });

        // ① 合法上限（C-0 §4.2 的包絡案）／② 同案降階／③ 大圖超限／④ 大圖不設限
        m_cases.push_back({ "legal-max-quad-K48",      "quad", 400.0, 48, 0,    0,        false, true,  "" });
        m_cases.push_back({ "downshift-gridMax1600",   "quad", 400.0, 48, 1600, 0,        false, true,  "" });
        m_cases.push_back({ "oversize-image-capped",   "dual",  60.0,  6, 0,    8000000LL, true,  false, "image_too_large" });
        m_cases.push_back({ "oversize-image-uncapped", "dual",  60.0,  6, 800,  0,        true,  true,  "" });
    }
    ~LimitsRun() override { m_beat.Stop(); delete m_host; }

    void start()
    {
        install_crash_probe();
        breadcrumb("--- 閘門③ 起跑 ---");
        m_t0 = lg_now_ms();
        m_beat.Start(10);
        m_small = write_big_image(480, 360, "phototile_limits_small.png");
        // 8000×6000＝48M 像素（C-0 §4.2 用過的高像素輸入量級）
        m_big   = write_big_image(8000, 6000, "phototile_limits_big.png");
        if (!m_host->start()) { finish("host_start_failed"); return; }
        run_case();
    }

private:
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
        req.want_metadata      = false;
        m_case_t0 = lg_now_ms();
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 閘門③ 起跑案例 " << c.label
                                   << "（mode=" << c.mode << " size=" << c.size_mm << " K=" << c.klevels
                                   << " gridMax=" << c.grid_max << " maxPx=" << c.max_pixels
                                   << " bigImage=" << (c.use_big_image ? 1 : 0) << "）";
        write_report(false, "case_start:" + c.label);
        breadcrumb("[case] 起跑 " + c.label);
        m_host->generate(req);
    }

    void on_result(const PhotoTileEngineResult& r)
    {
        const LimitsCase& c = m_cases[m_index];
        const double ms = lg_now_ms() - m_case_t0;
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
        if (m_index == 0) m_grid_full = grid_w * grid_h;
        if (m_index == 1) m_grid_down = grid_w * grid_h;

        std::ostringstream o;
        o << "    { \"label\": \"" << c.label << "\", \"ok\": " << (r.ok ? "true" : "false")
          << ", \"asExpected\": " << (as_expected ? "true" : "false")
          << ", \"errorCode\": \"" << r.error_code << "\""
          << ", \"ms\": " << (long) ms
          << ", \"bytes\": " << r.three_mf.size()
          << ", \"gridW\": " << grid_w << ", \"gridH\": " << grid_h << ", \"parts\": " << parts
          << ", \"gridMax\": " << c.grid_max << ", \"maxDecodedPixels\": " << c.max_pixels << " }";
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
          << "  \"_note\": \"照片磚 C-1 閘門③：OOM／低記憶體 gate（逐案落地，未跑完也有紀錄）\",\n"
          << "  \"final\": " << (final_done ? "true" : "false") << ", \"why\": \"" << why << "\",\n"
          << "  \"casesRun\": \"" << m_rows.size() << "/" << m_cases.size() << "\",\n"
          << "  \"nextCase\": \"" << (m_index < m_cases.size() ? m_cases[m_index].label : std::string("-")) << "\",\n"
          << "  \"uiDriftMaxMs\": " << (long) m_drift_max << ",\n"
          << "  \"elapsedMs\": " << (long) (lg_now_ms() - m_t0) << ",\n"
          << "  \"cases\": [\n";
        for (size_t i = 0; i < m_rows.size(); ++i) j << m_rows[i] << (i + 1 < m_rows.size() ? ",\n" : "\n");
        j << "  ]\n}\n";
        try { boost::nowide::ofstream f(data_dir() + "/phototile_limits_report.json"); f << j.str(); }
        catch (...) {}
    }

    void finish(const std::string& why)
    {
        if (m_finished) return;
        m_finished = true;
        m_beat.Stop();

        const bool pass_downshift = m_grid_full > 0 && m_grid_down > 0 && m_grid_down < m_grid_full;
        const bool pass_drift     = m_drift_max <= 1000.0;
        const bool pass_all       = m_all_ok && pass_downshift && pass_drift && why == "done";

        std::ostringstream j;
        j << "{\n"
          << "  \"_note\": \"照片磚 C-1 閘門③：OOM／低記憶體 gate（降階有效性＋超限誠實報錯）\",\n"
          << "  \"ok\": " << (pass_all ? "true" : "false") << ", \"why\": \"" << why << "\",\n"
          << "  \"allCasesAsExpected\": " << (m_all_ok ? "true" : "false") << ",\n"
          << "  \"gridCellsFull\": " << m_grid_full << ", \"gridCellsDownshifted\": " << m_grid_down
          << ", \"downshiftEffective\": " << (pass_downshift ? "true" : "false") << ",\n"
          << "  \"uiDriftMaxMs\": " << (long) m_drift_max << ", \"passDrift\": " << (pass_drift ? "true" : "false") << ",\n"
          << "  \"totalMs\": " << (long) (lg_now_ms() - m_t0) << ",\n"
          << "  \"cases\": [\n";
        for (size_t i = 0; i < m_rows.size(); ++i) j << m_rows[i] << (i + 1 < m_rows.size() ? ",\n" : "\n");
        j << "  ]\n}\n";

        const std::string path = data_dir() + "/phototile_limits_report.json";
        try { boost::nowide::ofstream f(path); f << j.str(); }
        catch (...) { BOOST_LOG_TRIVIAL(warning) << "閘門③ 報告寫檔失敗"; }
        BOOST_LOG_TRIVIAL(info) << "PhotoTile 閘門③ 報告：" << path;

        m_host->shutdown();
        wxTheApp->CallAfter([this]() {
            delete this;
            if (wxGetApp().mainframe) wxGetApp().mainframe->Close(true);
        });
    }

    PhotoTileEngineHost*     m_host;
    wxTimer                  m_beat;
    std::vector<LimitsCase>  m_cases;
    std::vector<std::string> m_rows;
    std::string              m_small, m_big;
    size_t                   m_index = 0;
    double                   m_t0 = 0, m_case_t0 = 0, m_last_beat = 0, m_drift_max = 0;
    long long                m_grid_full = 0, m_grid_down = 0;
    bool                     m_all_ok = true, m_finished = false;
};

} // namespace

void run_photo_tile_limits_gate()
{
    (new LimitsRun())->start();
}

}} // namespace Slic3r::GUI
