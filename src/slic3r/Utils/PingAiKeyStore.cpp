// PING 照片磚 AI 金鑰保管——實作。規格與三條紀律見 PingAiKeyStore.hpp 檔頭。

#include "PingAiKeyStore.hpp"

#include <wx/secretstore.h>
#include <wx/string.h>

#include <boost/log/trivial.hpp>

namespace Slic3r {
namespace PingAiKey {

namespace {

/* 🔴 這兩個常數＝既有使用者的金鑰找不找得回來的唯一依據。**改名等於所有人的金鑰消失**
   （舊項目還留在保管庫裡，程式卻再也不去問它）。真要改＝要寫搬移碼，不是改字串。
   閘門 tools/ping/verify_ai_key_hygiene.py 會確認這兩個字串只出現在本檔。 */
const char* SECRET_SERVICE = "PING-Slicer/AI-Image";
const char* SECRET_USER    = "default";

// 太短的字串幾乎都是「只貼到一半」。門檻刻意訂低（不猜特定廠商的金鑰格式，
// 免得換一家服務就把人擋在門外）——真正判斷對不對的是對話框的「測試連線」。
const size_t MIN_KEY_LEN = 6;

wxString service() { return wxString::FromUTF8(SECRET_SERVICE); }
wxString user()    { return wxString::FromUTF8(SECRET_USER); }

// 用完就把緩衝區蓋掉。不是強保證（std::string 可能已被複製過），但比留著好。
void wipe(std::string& s)
{
    for (size_t i = 0; i < s.size(); ++i)
        s[i] = '\0';
    s.clear();
}

} // namespace

bool available(std::string* why)
{
    wxSecretStore store = wxSecretStore::GetDefault();
    wxString      err;
    if (store.IsOk(&err)) return true;

    if (why != nullptr) {
        // 講人話：使用者不需要知道 wxSecretStore 是什麼。
        *why = "這台電腦的系統憑證保管庫目前不能用，金鑰無法安全儲存。";
        if (!err.empty())
            *why += std::string("（系統訊息：") + err.ToUTF8().data() + "）";
    }
    return false;
}

bool has()
{
    std::string tmp;
    bool        ok = load(tmp);
    wipe(tmp);
    return ok;
}

bool save(const std::string& key, std::string* err)
{
    auto fail = [err](const std::string& msg) {
        if (err != nullptr) *err = msg;
        return false;
    };

    // FBK-11：不要只回失敗，要講缺什麼。
    if (key.empty())
        return fail("還沒貼上金鑰——請把金鑰貼進上面的欄位再按儲存。");
    if (key.size() < MIN_KEY_LEN)
        return fail("這串看起來太短，可能只貼到一半。");

    std::string why;
    if (!available(&why))
        return fail(why);

    wxSecretStore store = wxSecretStore::GetDefault();
    wxSecretValue secret(wxString::FromUTF8(key.c_str()));
    if (!store.Save(service(), user(), secret))
        return fail("寫進系統憑證保管庫失敗，金鑰沒有存起來。");

    // ⚠ 只印狀態，永遠不印值（檔頭紀律 2）。
    BOOST_LOG_TRIVIAL(info) << "PingAiKey: key stored";
    return true;
}

bool load(std::string& out)
{
    out.clear();

    wxSecretStore store = wxSecretStore::GetDefault();
    if (!store.IsOk()) return false;

    wxString      found_user;
    wxSecretValue secret;
    if (!store.Load(service(), found_user, secret) || !secret.IsOk())
        return false;

    if (secret.GetSize() == 0) return false;
    out.assign(static_cast<const char*>(secret.GetData()), secret.GetSize());
    return !out.empty();
}

bool clear()
{
    wxSecretStore store = wxSecretStore::GetDefault();
    if (!store.IsOk()) return false;

    // 找不到項目也算成功——呼叫者要的結果是「現在沒有金鑰」，而那已經成立。
    store.Delete(service());
    BOOST_LOG_TRIVIAL(info) << "PingAiKey: key cleared";
    return true;
}

std::string masked()
{
    std::string key;
    if (!load(key)) return std::string();

    const size_t tail = 4;
    std::string  out  = "••••••••";
    // 🔴 只有「長到尾四碼不等於整串」時才顯示尾碼；否則一個字都不露。
    //    save() 已擋掉 <6 字，所以正常情況一定走上面那條；這裡是防呆，不是死碼——
    //    保管庫裡可能有舊版或別的工具寫進去的短值。
    if (key.size() > tail)
        out += key.substr(key.size() - tail);

    wipe(key);
    return out;
}

} // namespace PingAiKey
} // namespace Slic3r
