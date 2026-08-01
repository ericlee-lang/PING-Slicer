// =====================================================================
// 照片磚 C-1 活體實測（2026-08-01 二版・照片磚線 PT）
//
// 為什麼要這支：C-1 的驗收條件原文是「協定單元測 **＋過期丟棄實測**」。
// 單元測證的是框架邏輯；但「生成中真的按取消」「生成到一半換機器」「引擎行程真的死掉」
// 這些在真 app 裡沒跑過——沒跑過就不算驗過（單次成功≠做好了；閘門③已經給過教訓：
// 閘門①全綠，換組參數立刻讓 app 猝死）。
//
// 【二版改了什麼（Codex 對抗審查回應）】
//   #8  舊的 C 段是**空值假綠燈**：舊 job 根本沒回過 terminal（被 epoch 過濾器丟掉），
//       `oldJobReturnedSuccess:false` 只是預設值；報告自己寫 supersededStatusSeen:false
//       卻標 pass。二版改成逐 jobId 記帳：兩個 job 都必須恰好終結一次、舊的不得成功、
//       新的成功後還要熬過**隔離觀察窗**確認舊 job 不會再回來；另加 C2 讓
//       **引擎頁自己**收到第二個 generate（產品路徑是宿主先收斂，頁面那條分支原本從沒被命中）。
//   #4  新增 F/G/H 段：**真的去殺引擎子行程**。重建路徑先前從未被實際觸發過，
//       REBUILD_CAP 也就談不上是保險絲。F＝殺一次，證重建真的發生且能復原；
//       G＝連殺 20 秒，證它不會謊報成功也不會卡死；
//       H＝把引擎頁導向不存在的位址（每次重建必失敗），證 cap 真的會截停——
//       H 是後補的：G 原本想用連殺證 cap，實測引擎每次 ~380ms 就復原、計數歸零，
//       那是量測方法追不上，不是保險絲的行為，硬標 pass 就會變成另一個假綠燈。
//   #1  測試類別自己違反 RAII（`delete this`、裸 new wxTimer、裸 new host）——已全部改掉。
//   #14 報告改用真正的 JSON writer（PhotoTileGateJson.hpp）：失敗訊息含換行／控制字元時，
//       手拼版會產出非法 JSON，正好在最需要讀報告的時候讀不到。
//
// 判準先寫死，量測後不得調整。
// =====================================================================

#include "PhotoTileSmoke.hpp"
#include "PhotoTileEngineHost.hpp"
#include "PhotoTileCapability.hpp"
#include "PhotoTileGateJson.hpp"

#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "libslic3r/Preset.hpp"
#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/Utils.hpp"

#include <chrono>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include <boost/log/trivial.hpp>
#include <boost/nowide/fstream.hpp>

#include <wx/app.h>
#include <wx/filename.h>
#include <wx/image.h>
#include <wx/timer.h>

#ifdef _WIN32
    #include <windows.h>
    #include <tlhelp32.h>
#endif

namespace Slic3r { namespace GUI {

namespace {

double lv_now_ms()
{
    using namespace std::chrono;
    return duration_cast<duration<double, std::milli>>(steady_clock::now().time_since_epoch()).count();
}

/* 殺掉 WebView2 browser 行程的**所有子行程**（renderer／GPU／utility）。
   為什麼是「所有子行程」而不是精準挑 renderer：要精準分辨得讀每個行程的命令列
   （--type=renderer），那要 WMI 或 NtQueryInformationProcess，為了一個測試鉤子不值得。
   殺全部一定含 renderer ⇒ 必定觸發 RENDER_PROCESS_EXITED（宿主判定為 fatal）；
   順帶會產生 GPU/utility 的事件，正好驗證「依 kind 分流、不吃重建額度」那段。
   ⚠ 只殺我們自己那顆 browser 行程的子代——宿主用專屬 user data folder
   （data_dir()/webview2_phototile），不會誤傷別人的 WebView2。 */
int lv_kill_children(unsigned int parent_pid, std::vector<unsigned int>* killed_out = nullptr)
{
#ifdef _WIN32
    if (parent_pid == 0) return 0;
    HANDLE snap = ::CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32W pe {};
    pe.dwSize = sizeof(pe);
    std::vector<unsigned int> children;
    if (::Process32FirstW(snap, &pe)) {
        do {
            if (pe.th32ParentProcessID == (DWORD) parent_pid)
                children.push_back((unsigned int) pe.th32ProcessID);
        } while (::Process32NextW(snap, &pe));
    }
    ::CloseHandle(snap);

    int killed = 0;
    for (unsigned int pid : children) {
        HANDLE h = ::OpenProcess(PROCESS_TERMINATE, FALSE, (DWORD) pid);
        if (h == nullptr) continue;
        if (::TerminateProcess(h, 1)) {
            ++killed;
            if (killed_out) killed_out->push_back(pid);
        }
        ::CloseHandle(h);
    }
    return killed;
#else
    (void) parent_pid; (void) killed_out;
    return 0;
#endif
}

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

// 判準（寫死）
constexpr int  QUARANTINE_MS      = 3000;    // 新案成功後，舊案不得再回來的觀察窗
constexpr int  REBUILD_READY_MS   = 25000;   // 殺掉引擎後必須在此時間內重新就緒
constexpr int  STORM_WINDOW_MS    = 20000;   // 連殺風暴長度
constexpr int  STORM_TICK_MS      = 120;     // 連殺輪詢間隔
constexpr int  STORM_RECOVER_MS   = 30000;   // 風暴後必須在此時間內回應（成功或誠實失敗）
constexpr int  FUSE_WINDOW_MS     = 90000;   // 保險絲觀察窗（3 次 ready 逾時 ≈ 45s，給兩倍裕度）
constexpr int  EXPECTED_REBUILD_CAP = 3;     // 與宿主 REBUILD_CAP 同值（不同步就是缺陷）

class LiveRun;
std::unique_ptr<LiveRun> g_live_run;         // 唯一擁有者（取代原本的 `delete this`）

class LiveRun : public wxEvtHandler
{
public:
    LiveRun() : m_host(new PhotoTileEngineHost())
    {
        m_host->set_result_handler([this](const PhotoTileEngineResult& r) { on_result(r); });
        m_host->set_status_handler([this](const std::string& s, const std::string& d) {
            m_log.push_back("[host] " + s + " " + d);
            m_status_seen[s] += 1;
            if (s == "superseded")  m_superseded_detail = d;
            if (s == "rebuilding")  {
                m_rebuilding_seen = true;
                // F 段的證據要在 F 段當下就固定下來——這個 handler 是全域的，
                // 後面 G/H 還會再發 rebuilding，直接共用一個欄位會讓 F 的報告顯示 H 的資料。
                if (m_phase == "rebuild" && m_rebuild_detail.empty()) m_rebuild_detail = d;
                m_last_rebuild_detail = d;
            }
            if (s == "ready")       on_engine_ready();
            if (s == "unavailable") on_engine_unavailable(d);
        });
    }
    ~LiveRun() override = default;            // host／timers 都是 unique_ptr，自動收

    void start()
    {
        m_t0 = lv_now_ms();
        m_image = write_photo_tile_test_image(480, 360, "phototile_live_input.png");
        check_capability();                       // A：不需要引擎，先做
        if (!m_host->start()) { finish("host_start_failed"); return; }
        m_phase = "cancel";
        start_long_job("live-cancel");
        schedule([this]() { cancel_now(); }, 4000);   // 跑 4 秒後下取消
    }

private:
    // ---------------- 基礎設施 ----------------
    // 計時器由本物件持有（Codex #1：原本每次 schedule 都 new 一顆、永不釋放）
    void schedule(std::function<void()> fn, int ms)
    {
        m_timers.push_back(std::unique_ptr<wxTimer>(new wxTimer(this)));
        wxTimer* t = m_timers.back().get();
        Bind(wxEVT_TIMER, [t, fn](wxTimerEvent&) { t->Stop(); fn(); }, t->GetId());
        t->StartOnce(ms);
    }

    void note_terminal(const PhotoTileEngineResult& r)
    {
        m_terminal_count[r.job_id] += 1;
        if (m_terminal_count[r.job_id] == 1) {
            m_terminal_code[r.job_id] = r.ok ? std::string("success") : r.error_code;
            m_terminal_at_ms[r.job_id] = lv_now_ms() - m_t0;
        }
        if (r.ok) m_success_jobs.insert(r.job_id);
    }

    // ---------------- A：capability predicate ＋ effective nozzle ----------------
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
        m_cap_pass = photo > 0 && photo == photo_with_nozzle && normal > 0;
    }

    // ---------------- job 送出 ----------------
    PhotoTileEngineRequest base_request(const std::string& job_id) const
    {
        PhotoTileEngineRequest req;
        req.job_id        = job_id;
        req.image_path    = m_image;
        req.want_metadata = false;
        req.env_json      = ENV_A;
        req.pillar = false; req.teeth = false; req.p2a_block = false;
        return req;
    }
    // 長案（quad K48／400mm）＝有足夠時間可取消／被 supersede／被殺
    void start_long_job(const std::string& job_id, bool page_supersede = false)
    {
        PhotoTileEngineRequest req = base_request(job_id);
        req.mode     = "quad";  req.nozzle = 0.4;
        req.width_mm = 400.0;   req.height_mm = 400.0; req.thick_mm = 6.0;
        req.klevels  = 48;      req.noise_mm  = 0.0;
        req.test_page_supersede = page_supersede;
        m_job_t0 = lv_now_ms();
        m_current_job = job_id;
        m_log.push_back("[case] 起跑長案 " + job_id);
        m_host->generate(req);
    }
    void start_short_job(const std::string& job_id, bool page_supersede = false)
    {
        PhotoTileEngineRequest req = base_request(job_id);
        req.mode     = "dual";  req.nozzle = 0.4;
        req.width_mm = 60.0;    req.height_mm = 45.0;  req.thick_mm = 6.0;
        req.klevels  = 6;       req.noise_mm  = 2.0;
        req.test_page_supersede = page_supersede;
        m_job_t0 = lv_now_ms();
        m_current_job = job_id;
        m_log.push_back("[case] 起跑短案 " + job_id);
        m_host->generate(req);
    }

    void run_fault_case()
    {
        if (m_fault_index >= (int)(sizeof(FAULTS) / sizeof(FAULTS[0]))) { begin_rebuild_phase(); return; }
        const FaultCase& fc = FAULTS[m_fault_index];
        PhotoTileEngineRequest req = base_request(std::string("live-fault-") + fc.fault);
        req.mode     = "dual";  req.nozzle = 0.4;
        req.width_mm = 60.0;    req.height_mm = 45.0;  req.thick_mm = 6.0;
        req.klevels  = 6;       req.noise_mm  = 2.0;
        req.fault_inject = fc.fault;
        m_job_t0 = lv_now_ms();
        m_current_job = req.job_id;
        m_log.push_back(std::string("[fault] 起跑 ") + fc.fault);
        m_host->generate(req);

        if (std::string(fc.expect_code).empty()) {     // 期望「不得交付」：開觀察窗
            const int idx = m_fault_index;
            schedule([this, idx]() {
                if (m_finished || m_fault_index != idx) return;
                m_fault_rows.push_back(std::string("    { ") + jfield("fault", "foreign_job") + ", "
                    + jfield("expected", "(不得交付)") + ", " + jfield("got", "(觀察窗內未交付)") + ", "
                    + jfield("pass", true) + " }");
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

    // ---------------- F/G：重建路徑（Codex 阻斷 #4） ----------------
    void begin_rebuild_phase()
    {
        m_phase = "rebuild";
        const PhotoTileEngineDiag d = m_host->diagnostics();
        m_browser_pid = d.browser_pid;
        m_rebuild_count_before = d.rebuild_count;
        m_log.push_back("[rebuild] 引擎 browser 行程 PID=" + std::to_string(m_browser_pid) +
                        "（stage=" + d.stage + "）");
        if (m_browser_pid == 0) {                       // 取不到 PID＝這段無法誠實驗證
            m_rebuild_note = "取不到 WebView2 browser 行程 PID，本段無法執行";
            begin_storm_phase();
            return;
        }
        start_long_job("live-rebuild-victim");
        schedule([this]() { kill_engine_now(); }, 3000); // 生成中途殺掉
    }

    void kill_engine_now()
    {
        if (m_finished) return;
        std::vector<unsigned int> killed;
        m_killed_count = lv_kill_children(m_browser_pid, &killed);
        m_kill_at_ms   = lv_now_ms() - m_t0;
        std::string ids;
        for (size_t i = 0; i < killed.size(); ++i) ids += (i ? "," : "") + std::to_string(killed[i]);
        m_log.push_back("[rebuild] 殺掉引擎子行程 " + std::to_string(m_killed_count) + " 個（PID " + ids + "）");
        if (m_killed_count == 0) {
            m_rebuild_note = "找不到可殺的引擎子行程";
            begin_storm_phase();
            return;
        }
        // 重建必須在觀察窗內回到就緒；逾時＝失敗（不重試、不放水）
        schedule([this]() {
            if (m_finished || m_phase != "rebuild" || m_rebuild_recovered) return;
            m_rebuild_note = "殺掉引擎後 " + std::to_string(REBUILD_READY_MS / 1000) + " 秒內未重新就緒";
            m_log.push_back("[rebuild] 逾時未重新就緒");
            begin_storm_phase();
        }, REBUILD_READY_MS);
    }

    void on_engine_ready()
    {
        if (m_phase == "rebuild" && m_killed_count > 0 && !m_rebuild_recovered) {
            m_rebuild_recovered  = true;
            m_rebuild_ready_ms   = (lv_now_ms() - m_t0) - m_kill_at_ms;
            const PhotoTileEngineDiag d = m_host->diagnostics();
            m_rebuild_count_after_ready = d.rebuild_count;   // 穩定就緒後應歸零
            m_log.push_back("[rebuild] 重新就緒（" + std::to_string((long) m_rebuild_ready_ms) +
                            "ms、rebuildCount=" + std::to_string(d.rebuild_count) + "）");
            // 復原後必須真的還能做事：再跑一個短案，成功才算 F 通過
            start_short_job("live-rebuild-after");
        }
    }

    void on_engine_unavailable(const std::string& detail)
    {
        if (m_phase == "fuse") {
            m_fuse_unavailable = true;
            m_fuse_detail  = detail;
            m_fuse_stage   = m_host->diagnostics().stage;
            m_fuse_at_ms   = (lv_now_ms() - m_t0) - m_fuse_started_ms;
            m_log.push_back("[fuse] 引擎判定 unavailable：" + detail);
            // 保險絲燒斷後，新請求仍必須**誠實失敗**（不得靜默、不得永遠 busy）
            start_short_job("live-after-fuse");
            schedule([this]() { finish("done"); }, 8000);
            return;
        }
        if (m_phase == "storm") { m_storm_unavailable = true; m_storm_detail = detail; return; }
        if (!m_finished) finish("engine_unavailable");
    }

    /* G 連殺風暴：不斷殺引擎子行程，看它會不會謊報成功或卡死。
       ⚠ 這一段**證不了 cap**——0801 實測引擎每次都在 ~380ms 內復原、計數在穩定就緒時歸零，
       殺得再快也只是在跟它賽跑。那是量測方法的極限，不是保險絲的行為。
       所以 G 的判準改成它真正證得了的事：連殺之下永不謊報成功、事後仍能復原。
       保險絲本身交給 H（決定性）去證。 */
    void begin_storm_phase()
    {
        m_phase = "storm";
        m_log.push_back("[storm] 開始連殺 " + std::to_string(STORM_WINDOW_MS / 1000) + " 秒");
        m_storm_timer.reset(new wxTimer(this));
        Bind(wxEVT_TIMER, [this](wxTimerEvent&) { storm_tick(); }, m_storm_timer->GetId());
        m_storm_timer->Start(STORM_TICK_MS);
        schedule([this]() {
            if (m_finished || m_phase != "storm") return;
            if (m_storm_timer) m_storm_timer->Stop();
            m_log.push_back("[storm] 連殺結束，觀察是否能復原");
            m_phase = "storm_recover";
            start_short_job("live-storm-after");
            schedule([this]() {                       // 復原觀察窗；沒回來就是卡死
                if (m_finished || m_phase != "storm_recover") return;
                m_storm_note = "連殺後 " + std::to_string(STORM_RECOVER_MS / 1000) + " 秒內沒有任何回應（疑似卡死）";
                m_log.push_back("[storm] " + m_storm_note);
                wait_ready_then_fuse(20);
            }, STORM_RECOVER_MS);
        }, STORM_WINDOW_MS);
    }

    void storm_tick()
    {
        if (m_finished || m_phase != "storm") { if (m_storm_timer) m_storm_timer->Stop(); return; }
        const PhotoTileEngineDiag d = m_host->diagnostics();
        if (d.browser_pid != 0) {
            const int n = lv_kill_children(d.browser_pid);
            if (n > 0) { m_storm_kills += 1; m_storm_procs_killed += n; }
        }
        m_storm_max_rebuild_count = (std::max)(m_storm_max_rebuild_count, d.rebuild_count);
    }

    /* H：REBUILD_CAP 是不是**有效的保險絲**（Codex 阻斷 #4 未證明的那一條）。
       做法＝讓引擎頁指到不存在的位址 ⇒ 每次建立都必定 ready 逾時 ⇒ 除了 cap 沒有別的東西
       能讓它停下來。判準：重建次數恰好 REBUILD_CAP 次、停手訊息點名 cap、
       之後的請求仍誠實失敗（不得永遠 busy）。 */
    /* H 開始前先等引擎回到穩定就緒——穩定就緒會把 rebuild_count 歸零，
       H 才是從乾淨狀態起算。0801 run3 實測就是踩這個：G 連殺後計數停在 2，
       H 只再重建一次就燒斷，我的斷言卻寫死「H 內要有 3 次」⇒ 誤判成失敗。
       等不到也照跑，但把起算值記進報告，斷言改用差值（不假設從 0 開始）。 */
    void wait_ready_then_fuse(int tries_left)
    {
        if (m_finished) return;
        if (m_host->diagnostics().stage == "Ready" || tries_left <= 0) {
            if (tries_left <= 0) m_fuse_note = "H 起跑前引擎未回到 Ready（起算計數見 rebuildCountAtStart）";
            begin_fuse_phase();
            return;
        }
        schedule([this, tries_left]() { wait_ready_then_fuse(tries_left - 1); }, 1000);
    }

    void begin_fuse_phase()
    {
        m_phase = "fuse";
        m_fuse_started_ms = lv_now_ms() - m_t0;
        m_rebuild_status_count_at_fuse_start = m_status_seen["rebuilding"];
        m_fuse_count_at_start = m_host->diagnostics().rebuild_count;
        m_log.push_back("[fuse] 起算重建計數＝" + std::to_string(m_fuse_count_at_start) +
                        "（stage=" + m_host->diagnostics().stage + "）");
        m_log.push_back("[fuse] 把引擎頁導向不存在的位址，逼每次重建都失敗");
        m_host->test_break_engine_url(true);
        const PhotoTileEngineDiag d = m_host->diagnostics();
        if (d.browser_pid != 0) lv_kill_children(d.browser_pid);   // 踢一腳，開始連續失敗
        // 每次 ready 逾時 15s × cap 次；給足裕度，逾時＝沒燒斷（誠實記為失敗）
        schedule([this]() {
            if (m_finished || m_phase != "fuse") return;
            m_fuse_note = "觀察窗內未見 cap 截停";
            m_log.push_back("[fuse] " + m_fuse_note);
            finish("done");
        }, FUSE_WINDOW_MS);
    }

    // ---------------- 結果分流 ----------------
    void on_result(const PhotoTileEngineResult& r)
    {
        const double ms = lv_now_ms() - m_job_t0;
        note_terminal(r);
        m_log.push_back("[result] " + r.job_id + " ok=" + jval(r.ok) + " err=" + r.error_code +
                        " ms=" + std::to_string((long) ms));

        if (m_phase == "cancel") {
            m_cancel_code = r.error_code;
            m_cancel_ms   = ms;
            m_cancel_pass = (!r.ok && r.error_code == "cancelled" && ms < 30000.0);
            m_phase = "supersede";
            start_long_job("live-supersede-old");
            schedule([this]() {
                m_log.push_back("[case] supersede（宿主收斂路徑）：送出新 job");
                start_short_job("live-supersede-new");
            }, 3000);
            return;
        }

        // C1：宿主收斂路徑。兩個 job 都要終結，新案成功後再熬過隔離觀察窗。
        if (m_phase == "supersede") {
            if (r.job_id == "live-supersede-old") return;      // 等新案
            if (r.job_id != "live-supersede-new") return;
            // D：環境快照——結果必須原封帶回 env A，且與 env B 比對要判定過期
            m_env_echo_raw     = r.env_json;
            m_env_echo_equal   = PhotoTileEngineHost::env_is_fresh(r.env_json, ENV_A);
            m_env_stale_caught = !PhotoTileEngineHost::env_is_fresh(r.env_json, ENV_B);
            m_env_pass         = m_env_echo_equal && m_env_stale_caught;
            m_phase = "supersede_quarantine";
            m_log.push_back("[case] 新案成功，進入隔離觀察窗 " + std::to_string(QUARANTINE_MS) + "ms");
            m_quarantine_old_terminals = m_terminal_count["live-supersede-old"];
            schedule([this]() { close_supersede_c1(); }, QUARANTINE_MS);
            return;
        }
        if (m_phase == "supersede_quarantine") {
            m_log.push_back("[case] ⚠ 隔離觀察窗內又收到結果：" + r.job_id);
            return;
        }

        // C2：頁面收斂路徑（讓引擎頁自己看到第二個 generate）
        if (m_phase == "page_supersede") {
            if (r.job_id != "live-page-new") return;
            m_phase = "faults";
            m_page_new_ok = r.ok;
            close_supersede_c2();
            run_fault_case();
            return;
        }

        if (m_phase == "faults") {
            const FaultCase& fc = FAULTS[m_fault_index];
            const bool expect_silence = std::string(fc.expect_code).empty();
            bool ok_case;
            if (expect_silence) {
                ok_case = false;
                m_fault_rows.push_back(std::string("    { ") + jfield("fault", fc.fault) + ", "
                    + jfield("expected", "(不得交付)") + ", "
                    + jfield("got", r.ok ? std::string("success") : r.error_code) + ", "
                    + jfield("pass", false) + " }");
            } else {
                ok_case = (!r.ok && r.error_code == fc.expect_code);
                m_fault_rows.push_back(std::string("    { ") + jfield("fault", fc.fault) + ", "
                    + jfield("expected", fc.expect_code) + ", "
                    + jfield("got", r.ok ? std::string("success") : r.error_code) + ", "
                    + jfield("pass", ok_case) + " }");
            }
            if (!ok_case) m_fault_pass = false;
            m_log.push_back(std::string("[fault] ") + fc.fault + " → " + (r.ok ? "success" : r.error_code) +
                            (ok_case ? "（符合預期）" : "（不符預期）"));
            ++m_fault_index;
            run_fault_case();
            return;
        }

        if (m_phase == "rebuild") {
            if (r.job_id == "live-rebuild-victim") {
                // 被殺當下進行中的 job 必須拿到誠實的失敗（不得靜默、不得假成功）
                m_victim_code = r.error_code;
                m_victim_pass = (!r.ok && r.error_code == "engine_crashed");
                m_log.push_back("[rebuild] 進行中的 job 終結＝" + r.error_code);
                return;
            }
            if (r.job_id == "live-rebuild-after") {
                m_after_ok = r.ok;
                m_log.push_back(std::string("[rebuild] 復原後的短案 ok=") + jval(r.ok));
                begin_storm_phase();
                return;
            }
            return;
        }

        if (m_phase == "storm") {
            // 風暴期間任何 job 都不得回報成功（引擎正在被殺，成功就是謊報）
            if (r.ok) { m_storm_lied = true; m_log.push_back("[storm] ⚠ 風暴中竟回報成功：" + r.job_id); }
            return;
        }
        if (m_phase == "storm_recover" && r.job_id == "live-storm-after") {
            m_storm_recovered   = true;
            m_storm_after_ok    = r.ok;
            m_storm_after_code  = r.ok ? std::string("success") : r.error_code;
            m_log.push_back("[storm] 風暴後回應＝" + m_storm_after_code);
            wait_ready_then_fuse(20);
            return;
        }
        if (m_phase == "fuse") {
            if (r.job_id == "live-after-fuse") {
                m_after_fuse_answered = true;
                m_after_fuse_code     = r.ok ? std::string("success") : r.error_code;
                m_log.push_back("[fuse] 保險絲燒斷後的請求回應＝" + m_after_fuse_code);
            }
            return;
        }
    }

    void close_supersede_c1()
    {
        const int old_terminals = m_terminal_count["live-supersede-old"];
        const int new_terminals = m_terminal_count["live-supersede-new"];
        m_c1_old_terminals = old_terminals;
        m_c1_new_terminals = new_terminals;
        m_c1_old_code      = m_terminal_code.count("live-supersede-old") ? m_terminal_code["live-supersede-old"] : std::string();
        m_c1_quarantine_clean = (old_terminals == m_quarantine_old_terminals);
        m_supersede_pass =
               old_terminals == 1                                    // 舊案恰好終結一次
            && new_terminals == 1                                    // 新案恰好終結一次
            && !m_success_jobs.count("live-supersede-old")            // 舊案不得成功
            &&  m_success_jobs.count("live-supersede-new")            // 新案必須成功
            &&  m_c1_quarantine_clean;                                // 觀察窗內舊案沒再回來
        m_log.push_back(std::string("[case] C1 supersede pass=") + jval(m_supersede_pass));

        // 接著跑 C2：頁面自己收斂
        m_phase = "page_supersede";
        start_long_job("live-page-old");
        schedule([this]() {
            m_log.push_back("[case] supersede（頁面收斂路徑）：不預先取消，直接送第二個 generate");
            start_short_job("live-page-new", /*page_supersede=*/true);
        }, 3000);
    }

    void close_supersede_c2()
    {
        const std::string expect = "live-page-old → live-page-new";
        m_page_detail_seen = m_superseded_detail;
        m_page_pass =
               m_superseded_detail == expect                         // 頁面那條分支真的被命中
            && m_terminal_count["live-page-old"] == 1
            && !m_success_jobs.count("live-page-old")
            && m_page_new_ok;
        m_log.push_back(std::string("[case] C2 頁面 supersede pass=") + jval(m_page_pass) +
                        "（detail=\"" + m_superseded_detail + "\"）");
    }

    // ---------------- 報告 ----------------
    void finish(const std::string& why)
    {
        if (m_finished) return;
        m_finished = true;

        m_rebuild_pass = m_victim_pass && m_rebuild_recovered && m_after_ok &&
                         m_rebuild_count_after_ready == 0 && m_killed_count > 0;
        // G：連殺之下不謊報、事後有回應（成功或誠實失敗都算，卡死才是失敗）
        m_storm_pass = m_storm_kills > 0 && !m_storm_lied && m_storm_recovered;
        // H：保險絲——重建恰好 cap 次、停手訊息點名 cap、之後的請求仍有誠實回應
        m_fuse_rebuild_attempts = m_status_seen["rebuilding"] - m_rebuild_status_count_at_fuse_start;
        /* 斷言用**差值**：H 不保證從計數 0 起跑（G 連殺可能讓引擎沒回到穩定就緒），
           寫死「H 內要有 3 次」會在 G 留下殘餘計數時誤判（0801 run3 實錄）。
           真正要證的是：從起算值開始，恰好補到 cap 就停手。 */
        m_fuse_pass = m_fuse_unavailable
                   && m_fuse_detail.find(std::to_string(EXPECTED_REBUILD_CAP)) != std::string::npos
                   && m_fuse_rebuild_attempts > 0
                   && (m_fuse_count_at_start + m_fuse_rebuild_attempts) == EXPECTED_REBUILD_CAP
                   && m_fuse_stage == "Unavailable"
                   && m_after_fuse_answered;

        const bool pass_all = m_cap_pass && m_cancel_pass && m_supersede_pass && m_page_pass &&
                              m_env_pass && m_fault_pass && m_rebuild_pass && m_storm_pass &&
                              m_fuse_pass && why == "done";

        std::ostringstream j;
        j << "{\n"
          << "  " << jfield("_note", "照片磚 C-1 活體實測二版：capability／取消／supersede×2／環境快照／故障注入／重建／連殺風暴／保險絲") << ",\n"
          << "  " << jfield("ok", pass_all) << ", " << jfield("why", why) << ",\n"

          << "  " << jstr("A_capability") << ": { " << jfield("pass", m_cap_pass)
          << ", " << jfield("photoTilePrinters", m_cap_photo)
          << ", " << jfield("withEffectiveNozzle", m_cap_with_nozzle)
          << ", " << jfield("dual", m_cap_dual) << ", " << jfield("quad", m_cap_quad)
          << ", " << jfield("nonPhotoTilePrinters", m_cap_normal)
          << ", " << jfield("note", m_cap_note)
          << ", " << jfield("sample", m_cap_sample) << " },\n"

          << "  " << jstr("B_cancel") << ": { " << jfield("pass", m_cancel_pass)
          << ", " << jfield("errorCode", m_cancel_code)
          << ", " << jfield("cancelSentAtMs", (long) m_cancel_sent_ms)
          << ", " << jfield("endedAtMs", (long) m_cancel_ms) << " },\n"

          << "  " << jstr("C1_supersede_host") << ": { " << jfield("pass", m_supersede_pass)
          << ", " << jfield("oldTerminals", m_c1_old_terminals)
          << ", " << jfield("newTerminals", m_c1_new_terminals)
          << ", " << jfield("oldTerminalCode", m_c1_old_code)
          << ", " << jfield("oldReturnedSuccess", (bool) m_success_jobs.count("live-supersede-old"))
          << ", " << jfield("newSucceeded", (bool) m_success_jobs.count("live-supersede-new"))
          << ", " << jfield("quarantineMs", QUARANTINE_MS)
          << ", " << jfield("quarantineClean", m_c1_quarantine_clean) << " },\n"

          << "  " << jstr("C2_supersede_page") << ": { " << jfield("pass", m_page_pass)
          << ", " << jfield("supersededDetail", m_page_detail_seen)
          << ", " << jfield("expectedDetail", "live-page-old → live-page-new")
          << ", " << jfield("oldTerminals", m_terminal_count["live-page-old"])
          << ", " << jfield("oldTerminalCode", m_terminal_code.count("live-page-old") ? m_terminal_code["live-page-old"] : std::string())
          << ", " << jfield("newSucceeded", m_page_new_ok) << " },\n"

          << "  " << jstr("D_envSnapshot") << ": { " << jfield("pass", m_env_pass)
          << ", " << jfield("echoEqualsSent", m_env_echo_equal)
          << ", " << jfield("staleDetected", m_env_stale_caught)
          << ", " << jfield("sent", std::string(ENV_A))
          << ", " << jfield("echoed", m_env_echo_raw) << " },\n"

          << "  " << jstr("E_faultInjection") << ": { " << jfield("pass", m_fault_pass)
          << ", " << jfield("casesRun", m_fault_rows.size()) << ", " << jstr("cases") << ": [\n";
        for (size_t i = 0; i < m_fault_rows.size(); ++i)
            j << m_fault_rows[i] << (i + 1 < m_fault_rows.size() ? ",\n" : "\n");
        j << "  ] },\n"

          << "  " << jstr("F_rebuild") << ": { " << jfield("pass", m_rebuild_pass)
          << ", " << jfield("browserPid", m_browser_pid)
          << ", " << jfield("childProcessesKilled", m_killed_count)
          << ", " << jfield("rebuildCountBeforeKill", m_rebuild_count_before)
          << ", " << jfield("inflightJobTerminalCode", m_victim_code)
          << ", " << jfield("inflightFailedHonestly", m_victim_pass)
          << ", " << jfield("rebuildingStatusSeen", m_rebuilding_seen)
          << ", " << jfield("rebuildingDetail", m_rebuild_detail)
          << ", " << jfield("_lastRebuildDetailWholeRun", m_last_rebuild_detail)
          << ", " << jfield("recoveredReady", m_rebuild_recovered)
          << ", " << jfield("recoverMs", (long) m_rebuild_ready_ms)
          << ", " << jfield("rebuildCountAfterReady", m_rebuild_count_after_ready)
          << ", " << jfield("jobAfterRebuildSucceeded", m_after_ok)
          << ", " << jfield("note", m_rebuild_note) << " },\n"

          << "  " << jstr("G_killStorm") << ": { " << jfield("pass", m_storm_pass)
          << ", " << jfield("_what", "連殺 20 秒下：不得謊報成功、事後必須有回應（不是卡死）")
          << ", " << jfield("killRounds", m_storm_kills)
          << ", " << jfield("processesKilled", m_storm_procs_killed)
          << ", " << jfield("maxRebuildCountSeen", m_storm_max_rebuild_count)
          << ", " << jfield("liedSuccessDuringStorm", m_storm_lied)
          << ", " << jfield("answeredAfterStorm", m_storm_recovered)
          << ", " << jfield("afterStormCode", m_storm_after_code)
          << ", " << jfield("becameUnavailable", m_storm_unavailable)
          << ", " << jfield("unavailableDetail", m_storm_detail)
          << ", " << jfield("note", m_storm_note) << " },\n"

          << "  " << jstr("H_rebuildCapFuse") << ": { " << jfield("pass", m_fuse_pass)
          << ", " << jfield("_what", "引擎頁導向不存在位址 ⇒ 每次重建必失敗；只有 REBUILD_CAP 能讓它停手")
          << ", " << jfield("expectedCap", EXPECTED_REBUILD_CAP)
          << ", " << jfield("rebuildCountAtStart", m_fuse_count_at_start)
          << ", " << jfield("rebuildAttempts", m_fuse_rebuild_attempts)
          << ", " << jfield("becameUnavailable", m_fuse_unavailable)
          << ", " << jfield("unavailableDetail", m_fuse_detail)
          << ", " << jfield("stageAfterFuse", m_fuse_stage)
          << ", " << jfield("blewAtMs", (long) m_fuse_at_ms)
          << ", " << jfield("laterRequestAnswered", m_after_fuse_answered)
          << ", " << jfield("laterRequestCode", m_after_fuse_code)
          << ", " << jfield("note", m_fuse_note) << " },\n"

          << "  " << jstr("statusCounts") << ": {";
        {
            bool first = true;
            for (const auto& kv : m_status_seen) {
                j << (first ? " " : ", ") << jfield(kv.first.c_str(), kv.second);
                first = false;
            }
        }
        j << " },\n"
          << "  " << jfield("totalMs", (long) (lv_now_ms() - m_t0)) << ",\n"
          << "  " << jstr("log") << ": [\n";
        for (size_t i = 0; i < m_log.size(); ++i)
            j << "    " << jstr(m_log[i]) << (i + 1 < m_log.size() ? ",\n" : "\n");
        j << "  ]\n}\n";

        const std::string path = data_dir() + "/phototile_live_report.json";
        try { boost::nowide::ofstream f(path); f << j.str(); } catch (...) {}
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 活體實測報告：" << path << "（pass=" << pass_all << "）";

        m_host->shutdown();
        wxTheApp->CallAfter([]() {
            g_live_run.reset();                       // RAII：擁有者釋放，取代 `delete this`
            if (wxGetApp().mainframe) wxGetApp().mainframe->Close(true);
        });
    }

    // ---------------- 狀態 ----------------
    std::unique_ptr<PhotoTileEngineHost>   m_host;
    std::vector<std::unique_ptr<wxTimer>>  m_timers;
    std::unique_ptr<wxTimer>               m_storm_timer;
    std::vector<std::string>               m_log;
    std::map<std::string, int>             m_status_seen, m_terminal_count;
    std::map<std::string, std::string>     m_terminal_code;
    std::map<std::string, double>          m_terminal_at_ms;
    std::set<std::string>                  m_success_jobs;

    std::string m_image, m_phase, m_current_job, m_cancel_code, m_cap_sample, m_cap_note, m_env_echo_raw;
    double      m_t0 = 0, m_job_t0 = 0, m_cancel_ms = 0, m_cancel_sent_ms = 0;
    bool        m_finished = false;

    // A
    int  m_cap_photo = 0, m_cap_normal = 0, m_cap_with_nozzle = 0, m_cap_dual = 0, m_cap_quad = 0;
    bool m_cap_pass = false;
    // B
    bool m_cancel_pass = false;
    // C1
    bool m_supersede_pass = false, m_c1_quarantine_clean = false;
    int  m_c1_old_terminals = 0, m_c1_new_terminals = 0, m_quarantine_old_terminals = 0;
    std::string m_c1_old_code;
    // C2
    bool m_page_pass = false, m_page_new_ok = false;
    std::string m_superseded_detail, m_page_detail_seen;
    // D
    bool m_env_pass = false, m_env_echo_equal = false, m_env_stale_caught = false;
    // E
    std::vector<std::string> m_fault_rows;
    int  m_fault_index = 0;
    bool m_fault_pass = true;
    // F
    unsigned int m_browser_pid = 0;
    int    m_killed_count = 0, m_rebuild_count_before = 0, m_rebuild_count_after_ready = -1;
    double m_kill_at_ms = 0, m_rebuild_ready_ms = 0;
    bool   m_rebuilding_seen = false, m_rebuild_recovered = false, m_victim_pass = false;
    bool   m_after_ok = false, m_rebuild_pass = false;
    std::string m_victim_code, m_rebuild_detail, m_last_rebuild_detail, m_rebuild_note;
    // G：連殺風暴
    int    m_storm_kills = 0, m_storm_procs_killed = 0, m_storm_max_rebuild_count = 0;
    bool   m_storm_lied = false, m_storm_recovered = false, m_storm_after_ok = false;
    bool   m_storm_unavailable = false, m_storm_pass = false;
    std::string m_storm_detail, m_storm_note, m_storm_after_code;
    // H：REBUILD_CAP 保險絲
    double m_fuse_started_ms = 0, m_fuse_at_ms = 0;
    int    m_fuse_rebuild_attempts = 0, m_rebuild_status_count_at_fuse_start = 0, m_fuse_count_at_start = 0;
    bool   m_fuse_unavailable = false, m_fuse_pass = false, m_after_fuse_answered = false;
    std::string m_fuse_detail, m_fuse_note, m_fuse_stage, m_after_fuse_code;
};

} // namespace

void run_photo_tile_live_gate()
{
    g_live_run.reset(new LiveRun());
    g_live_run->start();
}

}} // namespace Slic3r::GUI
