// PING 照片磚 AI 金鑰設定框——實作。裁定與範圍見 PingAiKeyDialog.hpp 檔頭。

#include "PingAiKeyDialog.hpp"

#include "slic3r/Utils/PingAiKeyStore.hpp"
#include "slic3r/Utils/Http.hpp"

#include <wx/app.h>
#include <wx/button.h>
#include <wx/checkbox.h>
#include <wx/colour.h>
#include <wx/dialog.h>
#include <wx/msgdlg.h>
#include <wx/sizer.h>
#include <wx/statline.h>
#include <wx/stattext.h>
#include <wx/textctrl.h>

#include <atomic>
#include <memory>
#include <string>

namespace Slic3r {
namespace GUI {

namespace {

/* 測試連線打的端點。挑「列出模型」是因為它**不會產生費用也不會生圖**，
   卻能同時回答兩件事：金鑰對不對（401）、連不連得上（逾時／DNS）。
   ⚠ P3「丑」要接產品內生圖時，供應商與端點請從這裡延伸，不要各處各寫一份。 */
const char* PING_AI_PROBE_URL = "https://api.openai.com/v1/models";
const long  PING_AI_PROBE_TIMEOUT_S = 10;

wxString u8(const std::string& s) { return wxString::FromUTF8(s.c_str()); }
wxString u8(const char* s)        { return wxString::FromUTF8(s); }

class PingAiKeyDialog : public wxDialog
{
public:
    explicit PingAiKeyDialog(wxWindow* parent);
    ~PingAiKeyDialog() override { *m_alive = false; }

private:
    void build();
    void refresh();                    // 依「有沒有金鑰」切換兩種狀態，不重開視窗
    void on_save();
    void on_test();
    void on_remove();
    void set_note(const wxString& text, bool is_error);

    // 這個框可能在 HTTP 回來之前就被關掉；回呼一律先問這面旗子。
    std::shared_ptr<std::atomic<bool>> m_alive = std::make_shared<std::atomic<bool>>(true);

    wxStaticText* m_state_line = nullptr;   // 已存：遮罩；未存：欄位說明
    wxStaticText* m_note       = nullptr;   // 錯誤／結果訊息（FBK-11：要講缺什麼）
    wxTextCtrl*   m_input      = nullptr;
    wxCheckBox*   m_show       = nullptr;
    wxButton*     m_save       = nullptr;
    wxButton*     m_test       = nullptr;
    wxButton*     m_change     = nullptr;
    wxButton*     m_remove     = nullptr;
    wxButton*     m_close      = nullptr;

    bool m_entry_mode = false;   // true＝正在填（含「換一把」）
};

PingAiKeyDialog::PingAiKeyDialog(wxWindow* parent)
    : wxDialog(parent, wxID_ANY, u8("設定 AI 生圖服務金鑰"), wxDefaultPosition, wxDefaultSize,
               wxDEFAULT_DIALOG_STYLE)
{
    build();
    refresh();
}

void PingAiKeyDialog::build()
{
    wxBoxSizer* root = new wxBoxSizer(wxVERTICAL);
    const int pad = FromDIP(10);

    // 講人話：使用者不需要知道保管庫叫什麼、用什麼演算法（UX 七律 #4）。
    wxStaticText* intro = new wxStaticText(this, wxID_ANY,
        u8("填了才能使用需要 AI 的照片磚款式。\n"
           "金鑰只留在這台電腦，只有你這個電腦帳號解得開；"
           "不會跟著專案檔、匯出包或列印檔送出去。"));
    intro->Wrap(FromDIP(420));
    root->Add(intro, 0, wxALL, pad);

    m_state_line = new wxStaticText(this, wxID_ANY, wxEmptyString);
    root->Add(m_state_line, 0, wxLEFT | wxRIGHT | wxBOTTOM, pad);

    // FRM-06：欄位說明放標籤，不要只寫在 placeholder（一打字就消失＝標籤不見了）。
    m_input = new wxTextCtrl(this, wxID_ANY, wxEmptyString, wxDefaultPosition,
                             wxSize(FromDIP(420), -1), wxTE_PASSWORD | wxTE_PROCESS_ENTER);
    root->Add(m_input, 0, wxLEFT | wxRIGHT, pad);

    m_show = new wxCheckBox(this, wxID_ANY, u8("顯示金鑰"));
    root->Add(m_show, 0, wxLEFT | wxRIGHT | wxTOP, pad);

    m_note = new wxStaticText(this, wxID_ANY, wxEmptyString);
    m_note->Wrap(FromDIP(420));
    root->Add(m_note, 0, wxALL, pad);

    root->Add(new wxStaticLine(this), 0, wxEXPAND | wxLEFT | wxRIGHT, pad);

    wxBoxSizer* btns = new wxBoxSizer(wxHORIZONTAL);
    m_test   = new wxButton(this, wxID_ANY, u8("測試連線"));
    m_change = new wxButton(this, wxID_ANY, u8("換一把"));
    m_remove = new wxButton(this, wxID_ANY, u8("移除金鑰"));
    m_save   = new wxButton(this, wxID_ANY, u8("儲存"));
    m_close  = new wxButton(this, wxID_CANCEL, u8("關閉"));
    btns->Add(m_test, 0, wxRIGHT, FromDIP(6));
    btns->Add(m_change, 0, wxRIGHT, FromDIP(6));
    btns->Add(m_remove, 0, wxRIGHT, FromDIP(6));
    btns->AddStretchSpacer(1);
    btns->Add(m_save, 0, wxRIGHT, FromDIP(6));
    btns->Add(m_close, 0);
    root->Add(btns, 0, wxEXPAND | wxALL, pad);

    // 目前限開發者模式，寫在畫面上免得下一棒以為客戶看得到（Eric 0816 裁「先不對客戶露出」）。
    wxStaticText* devnote = new wxStaticText(this, wxID_ANY,
        u8("（此設定目前只在開發者模式出現，尚未對客戶開放）"));
    root->Add(devnote, 0, wxLEFT | wxRIGHT | wxBOTTOM, pad);

    SetSizerAndFit(root);

    m_show->Bind(wxEVT_CHECKBOX, [this](wxCommandEvent&) {
        // wxTE_PASSWORD 不能就地切換，換掉控制項的值最省事：重建太吵，改用「取值→換樣式」。
        const wxString v = m_input->GetValue();
        long style = m_show->GetValue() ? (m_input->GetWindowStyle() & ~wxTE_PASSWORD)
                                        : (m_input->GetWindowStyle() | wxTE_PASSWORD);
        wxTextCtrl* fresh = new wxTextCtrl(this, wxID_ANY, v, wxDefaultPosition,
                                           m_input->GetSize(), style | wxTE_PROCESS_ENTER);
        GetSizer()->Replace(m_input, fresh);
        m_input->Destroy();
        m_input = fresh;
        m_input->Bind(wxEVT_TEXT_ENTER, [this](wxCommandEvent&) { on_save(); });
        Layout();
        m_input->SetFocus();
    });

    m_input->Bind(wxEVT_TEXT_ENTER, [this](wxCommandEvent&) { on_save(); });
    m_save->Bind(wxEVT_BUTTON,   [this](wxCommandEvent&) { on_save(); });
    m_test->Bind(wxEVT_BUTTON,   [this](wxCommandEvent&) { on_test(); });
    m_remove->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { on_remove(); });
    m_change->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        m_entry_mode = true;
        set_note(wxEmptyString, false);
        refresh();
    });
}

void PingAiKeyDialog::set_note(const wxString& text, bool is_error)
{
    m_note->SetForegroundColour(is_error ? wxColour(0xC0, 0x39, 0x2B) : wxColour(0x1E, 0x7A, 0x3C));
    m_note->SetLabel(text);
    m_note->Wrap(FromDIP(420));
    Layout();
    Fit();
}

void PingAiKeyDialog::refresh()
{
    std::string why;
    if (!PingAiKey::available(&why)) {
        // fail-closed：保管庫不能用就明講，不提供「先存檔案裡」這種安慰劑。
        m_state_line->SetLabel(u8(why));
        m_input->Hide(); m_show->Hide();
        m_save->Hide(); m_test->Hide(); m_change->Hide(); m_remove->Hide();
        Layout(); Fit();
        return;
    }

    const std::string mask = PingAiKey::masked();
    const bool        have = !mask.empty();
    const bool        entry = m_entry_mode || !have;

    m_state_line->SetLabel(entry ? u8("AI 生圖服務 API 金鑰")
                                 : u8("目前的金鑰：" + mask));

    m_input->Show(entry);
    m_show->Show(entry);
    m_save->Show(entry);
    m_test->Show(!entry);
    m_change->Show(!entry);
    m_remove->Show(!entry);

    if (entry) {
        m_input->SetValue(wxEmptyString);
        m_input->SetFocus();
        m_save->SetDefault();
    }
    Layout();
    Fit();
}

void PingAiKeyDialog::on_save()
{
    const std::string key = m_input->GetValue().ToUTF8().data();
    std::string err;
    if (!PingAiKey::save(key, &err)) {
        set_note(u8(err), true);     // FBK-11：說缺什麼，不是只把鈕變灰
        return;
    }
    m_entry_mode = false;
    m_input->SetValue(wxEmptyString);
    set_note(u8("已儲存。可以按「測試連線」當場確認這把金鑰能不能用。"), false);
    refresh();
}

void PingAiKeyDialog::on_test()
{
    std::string key;
    if (!PingAiKey::load(key)) {          // ⚠ 唯一的明文取用點（閘門白名單管的就是這裡）
        set_note(u8("讀不到已存的金鑰，請重新填一次。"), true);
        return;
    }

    m_test->Enable(false);
    set_note(u8("測試中…"), false);       // 有等待就要有回饋（全域 UI 標準）

    auto alive = m_alive;
    auto done  = [this, alive](const wxString& msg, bool is_error) {
        if (!*alive) return;
        wxTheApp->CallAfter([this, alive, msg, is_error]() {
            if (!*alive) return;
            m_test->Enable(true);
            set_note(msg, is_error);
        });
    };

    Http::get(std::string(PING_AI_PROBE_URL))
        .header("Authorization", std::string("Bearer ") + key)
        .timeout_connect(PING_AI_PROBE_TIMEOUT_S)
        .timeout_max(PING_AI_PROBE_TIMEOUT_S)
        .on_complete([done](std::string /*body*/, unsigned /*status*/) {
            done(u8("✓ 連線正常，這把金鑰可以用。"), false);
        })
        .on_error([done](std::string /*body*/, std::string error, unsigned status) {
            // 裁二乙的重點：把「金鑰不對」與「連不上」分開講，不要混成一句失敗。
            if (status == 401 || status == 403)
                done(u8("✕ 這把金鑰不被接受（可能貼錯或已失效），請換一把。"), true);
            else if (status == 429)
                done(u8("✕ 這個帳號目前額度用完或被限流——金鑰本身是對的。"), true);
            else
                done(u8("✕ 連不上 AI 服務（" + (error.empty() ? std::string("沒有回應") : error)
                        + "）。請確認網路，金鑰不一定有問題。"), true);
        })
        .perform();

    // 明文用完就地蓋掉，不留在這個函式的堆疊上（Http 已經複製走它需要的那份）。
    for (size_t i = 0; i < key.size(); ++i) key[i] = '\0';
}

void PingAiKeyDialog::on_remove()
{
    // FBK-12：高後果操作要雙重確認，而且**先講後果再問要不要**。
    wxMessageDialog confirm(this,
        u8("移除後，需要 AI 的款式會回到鎖住狀態，只剩本地款式可用。\n\n"
           "已經做好的照片磚不受影響。要再用 AI 款式就得重新貼一次金鑰——"
           "本程式不會留副本，請確認你自己還有那把金鑰。"),
        u8("移除金鑰？"), wxYES_NO | wxNO_DEFAULT | wxICON_WARNING);
    confirm.SetYesNoLabels(u8("確定移除"), u8("取消"));
    if (confirm.ShowModal() != wxID_YES) return;

    PingAiKey::clear();
    m_entry_mode = false;
    set_note(u8("已移除。需要 AI 的款式現在是鎖住的。"), false);
    refresh();
}

} // namespace

void show_ping_ai_key_dialog(wxWindow* parent)
{
    PingAiKeyDialog dlg(parent);
    dlg.ShowModal();
}

} // namespace GUI
} // namespace Slic3r
