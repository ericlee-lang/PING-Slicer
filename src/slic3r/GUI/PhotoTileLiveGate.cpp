// =====================================================================
// 照片磚 C-1 活體實測（2026-08-01・照片磚線 PT）
//
// 為什麼要這支：C-1 的驗收條件原文是「協定單元測 **＋過期丟棄實測**」。
// 單元測（29 過）證的是框架邏輯；但「生成中真的按取消」「生成到一半換機器」
// 這兩條在真 app 裡從沒跑過——沒跑過就不算驗過（單次成功≠做好了，這次閘門③
// 已經給過教訓：閘門①全綠，換組參數立刻讓 app 猝死）。
//
// 四項（判準先寫死，量測後不得調整）：
//   A capability predicate：掃 preset bundle，照片磚機必須被認出、
//     且 effective nozzle 讀得到（>0）；非照片磚機不得誤判。
//   B 生成中取消：長案跑到一半下 cancel ⇒ 必須回 `cancelled`、且**早於**該案正常耗時。
//   C supersede：長案進行中送新 job ⇒ 舊案不得回成功結果，新案要拿得到 3MF。
//   D 環境快照過期即棄：帶 env A 生成，結果的 env 必須原封等於 A，
//     且與 env B 比對必須判定為過期（＝上盤前擋得下來）。
// =====================================================================

#include "PhotoTileSmoke.hpp"
#include "PhotoTileEngineHost.hpp"
#include "PhotoTileCapability.hpp"

#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "libslic3r/Preset.hpp"
#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/Utils.hpp"

#include <chrono>
#include <sstream>
#include <string>
#include <vector>

#include <boost/log/trivial.hpp>
#include <boost/nowide/fstream.hpp>

#include <wx/app.h>
#include <wx/filename.h>
#include <wx/image.h>
#include <wx/timer.h>

namespace Slic3r { namespace GUI {

namespace {

double lv_now_ms()
{
    using namespace std::chrono;
    return duration_cast<duration<double, std::milli>>(steady_clock::now().time_since_epoch()).count();
}

std::string lv_write_image(int W, int H, const char* name)
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

std::string jbool(bool v) { return v ? "true" : "false"; }
std::string jesc(const std::string& s)
{
    std::string o;
    for (char c : s) { if (c == '"' || c == '\\') o += '\\'; o += c; }
    return o;
}

/* 故障注入矩陣（Codex 重要 #5 的答案）：讓真的引擎頁送出真的壞掉的傳輸，
   證明**產品在用的 C++ 四項驗證**真的擋得住。每案的期望錯誤碼＝協定 §7 的分類。
   ⚠ foreign_job 期望「完全不交付結果」——舊/他人 job 的訊息必須被 epoch 隔離丟棄，
   所以它的期望碼是空字串，改用逾時觀察窗判定。 */
struct FaultCase { const char* fault; const char* expect_code; };
static const FaultCase FAULTS[] = {
    { "chunk_skip",   "protocol_chunk_order"     },
    { "chunk_len",    "protocol_length_mismatch" },
    { "chunk_tamper", "protocol_sha_mismatch"    },
    { "no_length",    "protocol_length_mismatch" },
    { "end_chunks",   "protocol_chunk_count"     },
    { "end_size",     "protocol_length_mismatch" },
    { "no_sha",       "protocol_sha_mismatch"    },
    { "foreign_job",  ""                         },
};

const char* ENV_A = "{\"printerPresetName\":\"live-A\",\"nozzle\":0.4,\"plateRevision\":1}";
const char* ENV_B = "{\"printerPresetName\":\"live-A\",\"nozzle\":0.4,\"plateRevision\":2}";  // 只差換盤

class LiveRun : public wxEvtHandler
{
public:
    LiveRun() : m_host(new PhotoTileEngineHost())
    {
        m_host->set_result_handler([this](const PhotoTileEngineResult& r) { on_result(r); });
        m_host->set_status_handler([this](const std::string& s, const std::string& d) {
            m_log.push_back("[host] " + s + " " + d);
            if (s == "superseded") m_superseded_seen = true;
            if (s == "unavailable") finish("engine_unavailable");
        });
    }
    ~LiveRun() override { delete m_host; }

    void start()
    {
        m_t0 = lv_now_ms();
        m_image = lv_write_image(480, 360, "phototile_live_input.png");
        check_capability();                       // A：不需要引擎，先做
        if (!m_host->start()) { finish("host_start_failed"); return; }
        // ready 之後才會有第一個結果；用第一個長案起跑（B）
        m_phase = "cancel";
        start_long_job("live-cancel");
        schedule([this]() { cancel_now(); }, 4000);   // 跑 4 秒後下取消
    }

private:
    void schedule(std::function<void()> fn, int ms)
    {
        auto* t = new wxTimer(this);
        Bind(wxEVT_TIMER, [t, fn](wxTimerEvent&) { t->Stop(); fn(); }, t->GetId());
        t->StartOnce(ms);
    }

    // ---------- A：capability predicate ＋ effective nozzle ----------
    void check_capability()
    {
        PresetBundle* bundle = wxGetApp().preset_bundle;
        if (bundle == nullptr) { m_cap_note = "preset_bundle 為空"; return; }
        int photo = 0, normal = 0, photo_with_nozzle = 0, dual = 0, quad = 0;
        std::string sample;
        for (const Preset& preset : bundle->printers) {
            const PhotoTileCapability cap = photo_tile_capability_of(preset);
            if (cap.is_photo_tile) {
                ++photo;
                if (cap.nozzle_mm > 0.0) ++photo_with_nozzle;
                if (cap.mode == "dual") ++dual;
                if (cap.mode == "quad") ++quad;
                if (sample.empty())
                    sample = cap.preset_name + "｜" + cap.mode + "｜nozzle=" + std::to_string(cap.nozzle_mm);
            } else {
                ++normal;
            }
        }
        m_cap_photo = photo; m_cap_normal = normal; m_cap_with_nozzle = photo_with_nozzle;
        m_cap_dual = dual;   m_cap_quad = quad;     m_cap_sample = sample;
        // 判準：照片磚機認得出來（>0）、每一台都讀得到 effective nozzle、且有非照片磚機（不是全部誤判）
        m_cap_pass = photo > 0 && photo == photo_with_nozzle && normal > 0;
    }

    // ---------- 長案（quad K48／400mm）＝有足夠時間可取消／被 supersede ----------
    void start_long_job(const std::string& job_id)
    {
        PhotoTileEngineRequest req;
        req.job_id   = job_id;
        req.mode     = "quad";  req.nozzle = 0.4;
        req.width_mm = 400.0;   req.height_mm = 400.0; req.thick_mm = 6.0;
        req.klevels  = 48;      req.noise_mm  = 0.0;
        req.pillar   = false;   req.teeth = false;     req.p2a_block = false;
        req.image_path    = m_image;
        req.want_metadata = false;
        req.env_json      = ENV_A;
        m_job_t0 = lv_now_ms();
        m_current_job = job_id;
        m_log.push_back("[case] 起跑長案 " + job_id);
        m_host->generate(req);
    }
    void start_short_job(const std::string& job_id)
    {
        PhotoTileEngineRequest req;
        req.job_id   = job_id;
        req.mode     = "dual";  req.nozzle = 0.4;
        req.width_mm = 60.0;    req.height_mm = 45.0;  req.thick_mm = 6.0;
        req.klevels  = 6;       req.noise_mm  = 2.0;
        req.pillar   = false;   req.teeth = false;     req.p2a_block = false;
        req.image_path    = m_image;
        req.want_metadata = false;
        req.env_json      = ENV_A;
        m_job_t0 = lv_now_ms();
        m_current_job = job_id;
        m_log.push_back("[case] 起跑短案 " + job_id);
        m_host->generate(req);
    }

    // 每個故障案：送一個小 job 並要求引擎頁刻意送壞傳輸，斷言宿主回報的錯誤碼
    void run_fault_case()
    {
        if (m_fault_index >= (int)(sizeof(FAULTS) / sizeof(FAULTS[0]))) { finish("done"); return; }
        const FaultCase& fc = FAULTS[m_fault_index];
        PhotoTileEngineRequest req;
        req.job_id   = std::string("live-fault-") + fc.fault;
        req.mode     = "dual";  req.nozzle = 0.4;
        req.width_mm = 60.0;    req.height_mm = 45.0;  req.thick_mm = 6.0;
        req.klevels  = 6;       req.noise_mm  = 2.0;
        req.pillar   = false;   req.teeth = false;     req.p2a_block = false;
        req.image_path    = m_image;
        req.want_metadata = false;
        req.env_json      = ENV_A;
        req.fault_inject  = fc.fault;
        m_job_t0 = lv_now_ms();
        m_current_job = req.job_id;
        m_log.push_back(std::string("[fault] 起跑 ") + fc.fault);
        m_host->generate(req);

        // 期望「不得交付」的案例：開一個觀察窗，時間到還沒收到結果＝通過（被正確丟棄）
        if (std::string(fc.expect_code).empty()) {
            const int idx = m_fault_index;
            schedule([this, idx]() {
                if (m_finished || m_fault_index != idx) return;    // 已經收到結果＝失敗路徑已記錄
                m_fault_rows.push_back(std::string("    { \"fault\": \"foreign_job\", \"expected\": ")
                    + "\"(不得交付)\", \"got\": \"(觀察窗內未交付)\", \"pass\": true }");
                m_log.push_back("[fault] foreign_job → 觀察窗內未交付（符合預期：被 epoch 隔離丟棄）");
                ++m_fault_index;
                m_host->cancel(m_current_job);
                run_fault_case();
            }, 12000);
        }
    }

    void cancel_now()
    {
        m_cancel_sent_ms = lv_now_ms() - m_job_t0;
        m_log.push_back("[case] 下取消 " + m_current_job);
        m_host->cancel(m_current_job);
    }

    void on_result(const PhotoTileEngineResult& r)
    {
        const double ms = lv_now_ms() - m_job_t0;
        m_log.push_back("[result] " + r.job_id + " ok=" + jbool(r.ok) + " err=" + r.error_code +
                        " ms=" + std::to_string((long) ms));

        if (m_phase == "cancel") {
            // B：必須是 cancelled，且明顯早於該案正常耗時（閘門③ 實測同案約 90s）
            m_cancel_code   = r.error_code;
            m_cancel_ms     = ms;
            m_cancel_pass   = (!r.ok && r.error_code == "cancelled" && ms < 30000.0);
            m_phase = "supersede";
            start_long_job("live-supersede-old");
            schedule([this]() {                       // 3 秒後丟新 job ⇒ 舊的應被取代
                m_log.push_back("[case] supersede：送出新 job");
                start_short_job("live-supersede-new");
            }, 3000);
            return;
        }
        if (m_phase == "supersede") {
            if (r.job_id == "live-supersede-old") {
                // 舊案**不得**回成功；回 cancelled 才是對的
                m_supersede_old_ok_result = r.ok;
                m_log.push_back("[case] 舊案回應 ok=" + jbool(r.ok) + " err=" + r.error_code);
                return;                               // 等新案的結果
            }
            m_supersede_new_ok = r.ok;
            m_supersede_pass   = r.ok && !m_supersede_old_ok_result;
            // D：環境快照——結果必須原封帶回 env A，且與 env B 比對要判定過期
            m_env_echo_raw   = r.env_json;
            m_env_echo_equal = PhotoTileEngineHost::env_is_fresh(r.env_json, ENV_A);
            m_env_stale_caught = !PhotoTileEngineHost::env_is_fresh(r.env_json, ENV_B);
            m_env_pass = m_env_echo_equal && m_env_stale_caught;
            m_phase = "faults";
            run_fault_case();
            return;
        }
        if (m_phase == "faults") {
            const FaultCase& fc = FAULTS[m_fault_index];
            const bool expect_silence = std::string(fc.expect_code).empty();
            bool ok_case;
            if (expect_silence) {
                ok_case = false;                       // 收到任何結果都算失敗（應該被丟棄才對）
                m_fault_rows.push_back(std::string("    { \"fault\": \"") + fc.fault +
                    "\", \"expected\": \"(不得交付)\", \"got\": \"" + (r.ok ? "success" : r.error_code) +
                    "\", \"pass\": false }");
            } else {
                ok_case = (!r.ok && r.error_code == fc.expect_code);
                m_fault_rows.push_back(std::string("    { \"fault\": \"") + fc.fault +
                    "\", \"expected\": \"" + fc.expect_code + "\", \"got\": \"" +
                    (r.ok ? "success" : r.error_code) + "\", \"pass\": " + (ok_case ? "true" : "false") + " }");
            }
            if (!ok_case) m_fault_pass = false;
            m_log.push_back(std::string("[fault] ") + fc.fault + " → " + (r.ok ? "success" : r.error_code) +
                            (ok_case ? "（符合預期）" : "（不符預期）"));
            ++m_fault_index;
            run_fault_case();
            return;
        }
    }

    void finish(const std::string& why)
    {
        if (m_finished) return;
        m_finished = true;
        const bool pass_all = m_cap_pass && m_cancel_pass && m_supersede_pass && m_env_pass && m_fault_pass && why == "done";

        std::ostringstream j;
        j << "{\n"
          << "  \"_note\": \"照片磚 C-1 活體實測：capability／取消／supersede／環境快照過期即棄\",\n"
          << "  \"ok\": " << jbool(pass_all) << ", \"why\": \"" << jesc(why) << "\",\n"
          << "  \"A_capability\": { \"pass\": " << jbool(m_cap_pass)
          << ", \"photoTilePrinters\": " << m_cap_photo
          << ", \"withEffectiveNozzle\": " << m_cap_with_nozzle
          << ", \"dual\": " << m_cap_dual << ", \"quad\": " << m_cap_quad
          << ", \"nonPhotoTilePrinters\": " << m_cap_normal
          << ", \"sample\": \"" << jesc(m_cap_sample) << "\" },\n"
          << "  \"B_cancel\": { \"pass\": " << jbool(m_cancel_pass)
          << ", \"errorCode\": \"" << jesc(m_cancel_code) << "\""
          << ", \"cancelSentAtMs\": " << (long) m_cancel_sent_ms
          << ", \"endedAtMs\": " << (long) m_cancel_ms << " },\n"
          << "  \"C_supersede\": { \"pass\": " << jbool(m_supersede_pass)
          << ", \"oldJobReturnedSuccess\": " << jbool(m_supersede_old_ok_result)
          << ", \"newJobSucceeded\": " << jbool(m_supersede_new_ok)
          << ", \"supersededStatusSeen\": " << jbool(m_superseded_seen) << " },\n"
          << "  \"D_envSnapshot\": { \"pass\": " << jbool(m_env_pass)
          << ", \"echoEqualsSent\": " << jbool(m_env_echo_equal)
          << ", \"staleDetected\": " << jbool(m_env_stale_caught)
          << ", \"sent\": \"" << jesc(ENV_A) << "\""
          << ", \"echoed\": \"" << jesc(m_env_echo_raw) << "\" },\n"
          << "  \"E_faultInjection\": { \"pass\": " << jbool(m_fault_pass)
          << ", \"casesRun\": " << m_fault_rows.size() << ", \"cases\": [\n";
        for (size_t i = 0; i < m_fault_rows.size(); ++i)
            j << m_fault_rows[i] << (i + 1 < m_fault_rows.size() ? ",\n" : "\n");
        j << "  ] },\n"
          << "  \"totalMs\": " << (long) (lv_now_ms() - m_t0) << ",\n"
          << "  \"log\": [\n";
        for (size_t i = 0; i < m_log.size(); ++i)
            j << "    \"" << jesc(m_log[i]) << "\"" << (i + 1 < m_log.size() ? ",\n" : "\n");
        j << "  ]\n}\n";

        const std::string path = data_dir() + "/phototile_live_report.json";
        try { boost::nowide::ofstream f(path); f << j.str(); } catch (...) {}
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 活體實測報告：" << path << "（pass=" << pass_all << "）";

        m_host->shutdown();
        wxTheApp->CallAfter([this]() {
            delete this;
            if (wxGetApp().mainframe) wxGetApp().mainframe->Close(true);
        });
    }

    PhotoTileEngineHost*     m_host;
    std::vector<std::string> m_log;
    std::string              m_image, m_phase, m_current_job, m_cancel_code, m_cap_sample, m_cap_note, m_env_echo_raw;
    double                   m_t0 = 0, m_job_t0 = 0, m_cancel_ms = 0, m_cancel_sent_ms = 0;
    int                      m_cap_photo = 0, m_cap_normal = 0, m_cap_with_nozzle = 0, m_cap_dual = 0, m_cap_quad = 0;
    bool                     m_cap_pass = false, m_cancel_pass = false, m_supersede_pass = false, m_env_pass = false;
    bool                     m_supersede_old_ok_result = false, m_supersede_new_ok = false, m_superseded_seen = false;
    bool                     m_env_echo_equal = false, m_env_stale_caught = false, m_finished = false;
    std::vector<std::string> m_fault_rows;
    int                      m_fault_index = 0;
    bool                     m_fault_pass = true;
};

} // namespace

void run_photo_tile_live_gate()
{
    (new LiveRun())->start();
}

}} // namespace Slic3r::GUI
