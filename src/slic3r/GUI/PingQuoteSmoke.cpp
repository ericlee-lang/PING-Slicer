#include "PingQuoteSmoke.hpp"
#include "PingQuotePack.hpp"

#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "Plater.hpp"

#include <boost/filesystem.hpp>
#include <boost/log/trivial.hpp>

#include <wx/timer.h>

#include <cstdlib>
#include <string>
#include <vector>

namespace Slic3r { namespace GUI {

static std::vector<std::string> split_semicolon(const std::string &s)
{
    std::vector<std::string> out;
    std::string              cur;
    for (char c : s) {
        if (c == ';') {
            if (!cur.empty()) out.push_back(cur);
            cur.clear();
        } else {
            cur += c;
        }
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

// 收工：把結論寫進 log 再關 app。
// **一律關閉、也一律回報**——smoke 最怕的是「不知道為什麼沒結果」，
// 所以失敗路徑也要留下明確的一行，不能安靜地死掉。
static void finish_smoke(MainFrame *frame, bool ok, const std::string &message)
{
    BOOST_LOG_TRIVIAL(warning) << "PING_QUOTE_SMOKE result=" << (ok ? "OK" : "FAIL") << " :: " << message;
    if (frame != nullptr)
        frame->CallAfter([frame]() { frame->Close(true); });
}

void run_ping_quote_smoke(MainFrame *frame)
{
    const char *out_env = ::getenv("PING_QUOTE_SMOKE");
    if (out_env == nullptr)
        return;   // 一般啟動：什麼都不做

    const std::string out_path = out_env;
    const char       *model_env = ::getenv("PING_QUOTE_SMOKE_MODEL");
    if (model_env == nullptr || out_path.empty()) {
        finish_smoke(frame, false, "PING_QUOTE_SMOKE / PING_QUOTE_SMOKE_MODEL 未正確設定");
        return;
    }

    std::vector<std::string> models = split_semicolon(model_env);
    for (const auto &m : models) {
        if (!boost::filesystem::exists(m)) {
            finish_smoke(frame, false, "找不到模型檔：" + m);
            return;
        }
    }

    const char *delay_env = ::getenv("PING_QUOTE_SMOKE_DELAY_MS");
    const int   delay_ms  = delay_env != nullptr ? ::atoi(delay_env) : 6000;

    auto launch = [frame, out_path, models]() {
        Plater *plater = wxGetApp().plater();
        if (plater == nullptr) {
            finish_smoke(frame, false, "plater 尚未就緒");
            return;
        }

        // 只載模型不載設定：smoke 要驗的是「目前這組 preset 下產出的報價包」，
        // 讓模型檔裡的設定覆蓋掉機型／製程就測不到我們想測的東西了。
        std::vector<size_t> loaded;
        try {
            loaded = plater->load_files(models, LoadStrategy::LoadModel);
        } catch (const std::exception &e) {
            finish_smoke(frame, false, std::string("載入模型失敗：") + e.what());
            return;
        }
        if (loaded.empty()) {
            finish_smoke(frame, false, "載入模型後盤上沒有東西");
            return;
        }

        BOOST_LOG_TRIVIAL(warning) << "PING_QUOTE_SMOKE: loaded " << loaded.size() << " model(s), generating...";

        PingQuoteOptions opts;
        opts.output_path = out_path;
        opts.silent      = true;   // 無人值守：一個 modal 都不能彈
        /* 還原檔跟著產品路徑走——**契約 v1.2 起產品預設是「含」**，所以 smoke 也預設含，
           smoke 驗到的才會是使用者真正會拿到的那顆包。
           ⚠ 這一段 2026-08-19 翻面過：v1.1 時代產品預設不含，這裡也就預設不含
           （`PING_QUOTE_SMOKE_3MF=1` 才開）。**當時的判準沒變、是產品的預設值變了**——
           判準永遠是「與產品路徑一致」，不是「小包比較快」。跟著改的話 smoke 會安靜地
           只驗一條使用者根本走不到的路徑。
           要測不含的那條（＝使用者把設定鍵關掉）：`PING_QUOTE_SMOKE_3MF=0`。
           舊腳本寫 `=1` 仍然是含，行為不變。 */
        {
            const char *w3mf = ::getenv("PING_QUOTE_SMOKE_3MF");
            opts.include_restore_3mf = !(w3mf != nullptr && std::string(w3mf) == "0");
        }
        opts.on_done     = [frame](bool ok, const std::string &msg) { finish_smoke(frame, ok, msg); };
        ping_quote_generate(plater, opts);
    };

    // 延後起跑，讓 app 自己的初始化（preset 載入、GL context 建立）先做完——
    // 縮圖那段需要可用的 GL context，太早跑會拿不到。
    if (delay_ms > 0) {
        auto *t = new wxTimer(frame);
        frame->Bind(wxEVT_TIMER, [t, launch](wxTimerEvent &) { t->Stop(); launch(); }, t->GetId());
        t->StartOnce(delay_ms);
    } else {
        frame->CallAfter(launch);
    }
}

}} // namespace Slic3r::GUI
