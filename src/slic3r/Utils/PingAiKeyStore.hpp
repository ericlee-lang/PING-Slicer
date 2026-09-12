#ifndef slic3r_PingAiKeyStore_hpp_
#define slic3r_PingAiKeyStore_hpp_

#include <string>

/* PING 照片磚 AI 風格化 — 金鑰保管（P3「子」，2026-08-16）
 *
 * 【商業模式】Eric 2026-08-16 裁：**客戶自己填自己的金鑰**（不是 PING 統一出金鑰），
 *   所以產品必須有地方讓他存；存的東西是客戶的錢，安全等級照憑證處理。
 *
 * 【存哪】只走系統憑證保管庫（Windows 認證管理員／macOS Keychain／Linux libsecret），
 *   ＝ wxSecretStore。**刻意不做加密檔後備**——理由不是懶：
 *   本 repo 既有的 OrcaCloudServiceAgent 檔案後備是拿 machine_identifier() 當金鑰，
 *   那是**綁機器**；Eric 要的是**綁使用者**（同一台電腦的另一個 Windows 帳號不該讀得到）。
 *   ⇒ 保管庫不可用時 **fail-closed：明講失敗，不偷偷落檔**。
 *
 * 【三條不可退讓的紀律】（這一層存在的意義就是這三條，改碼前先讀）
 *   1. 明文**不進網頁層**。整支照片磚工作室頁面（WebView2）不知道有金鑰這回事——
 *      因為那個 app 的頁面有現成偵錯埠（SOP_WebView2隱形宿主與跨層協定.md §十九，
 *      `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9223`），
 *      我們自己天天拿探針去讀它。明文放那裡＝放進一個固定被讀的地方。
 *   2. 明文**不進任何會被備份／同步／打包／回報的載體**：不進 AppConfig（PINGSlicer.conf 會被
 *      備份與 %APPDATA% 同步）、不進 3mf／專案檔／匯出包、不進 log（本檔任何 log 只印狀態不印值）。
 *   3. `load()` 是**唯一**能取出明文的入口，呼叫點受閘門白名單管制
 *      （tools/ping/verify_ai_key_hygiene.py）。要新增呼叫點＝**必須改白名單**，
 *      改白名單會逼下一棒回頭讀這段話。
 *
 * 【範圍】本檔只管「存、取、刪、有沒有」。產品內真的打 API 生圖＝P3「丑」，尚未做
 *   （Eric 2026-08-16 裁「做子」）；今天生圖仍在 dev 側 照片磚管線/pipeline.py。
 *
 * ⚠ 跨平台：本檔只用 wxSecretStore 與 std::string，**沒有任何 `#ifdef _WIN32` 分支**，
 *   也不用 std::to_chars／std::format（Apple libc++ 對它們有 availability 標註，撞
 *   -mmacosx-version-min=10.15）。這兩個坑就是 0815 那輪 Linux／macOS CI 全紅的根因，
 *   見 SOP_內部測試版發布.md §1-2。
 */

namespace Slic3r {
namespace PingAiKey {

// 憑證保管庫在這台機器上可不可用。不可用時 why 會帶回可以直接顯示給使用者的白話原因。
bool available(std::string* why = nullptr);

// 有沒有存過金鑰（不取出明文）。
bool has();

// 存。key 為空或過短會被擋下並在 err 說明「缺什麼」，不是只回 false。
bool save(const std::string& key, std::string* err = nullptr);

// 取出明文。⚠ 呼叫點受閘門白名單管制，新增呼叫點請先讀本檔檔頭第 3 條。
bool load(std::string& out);

// 刪除。找不到也回 true（結果就是「現在沒有金鑰」）。
bool clear();

// 顯示用遮罩，例："••••••••1234"；沒有金鑰時回空字串。永遠不回明文。
std::string masked();

} // namespace PingAiKey
} // namespace Slic3r

#endif // slic3r_PingAiKeyStore_hpp_
