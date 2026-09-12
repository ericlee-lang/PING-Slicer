#ifndef slic3r_PingAiImage_hpp_
#define slic3r_PingAiImage_hpp_

#include <string>
#include <vector>

/* PING 照片磚 AI 生圖（丙案／P3「丑」，2026-09-02）
 *
 * 【這一層在做什麼】把「一段 prompt」變成「一張 PNG 的位元組」。就這樣。
 *   不認識照片磚、不認識款式庫、不碰 UI、不決定要不要重試——那些都在上面。
 *   這樣切是為了讓**明文金鑰的觸及面積只有這一個檔**（見下）。
 *
 * 【為什麼不是寫在 GUI_App】取金鑰明文那支（存取層的 `load`）的呼叫點受閘門白名單管制
 *   （`tools/ping/verify_ai_key_hygiene.py` 的 PLAINTEXT_READERS）。GUI_App.cpp 是全專案
 *   最大、最多人改的檔——把明文取用點放進去，等於把白名單的摩擦力歸零。
 *   放這裡：**要拿到金鑰，就得先進到這個只有 200 行、檔頭寫著紀律的檔**。
 *   ⚠ 本檔頭刻意**不寫出那支的完整呼叫寫法**——閘門 C2 是純字串比對、不剝註解，
 *     寫全了會讓這個 .hpp 被判成「未授權的明文取用點」（實測會紅）。那份粗糙是刻意的：
 *     剝註解＝多開一條漏判的路，對安全閘門來說寧可誤報也不要漏報。
 *
 * 【已裁事項】規格正本＝`照片磚_核心規格.md` §9（Eric 2026-08-22 一輪八題）：
 *   R9-1 供應商＝OpenAI `gpt-image-2`（⚠ VibeCAD 線用的是 OpenRouter，不同帳不同金鑰，不要混）
 *   R9-2 金鑰＝客戶自己填（本層只負責用，存取在 PingAiKeyStore）
 *   R9-8 尺寸只有三種、由磚體長寬比自動挑；品質＝`low`
 *
 * 【失敗分類為什麼要分這麼細】R9-5 裁定「**只在自動驗沒過時重試**；逾時／網路錯／401 不重試」。
 *   要做到那件事，上層必須分得出「這張圖不合格」與「這次根本沒生成」——
 *   如果本層只回一個 bool，上層唯一能做的就是無差別重試，那正是 R9-5 要擋的「重複燒錢」。
 *   ⇒ `FailKind` 是**給重試策略用的**，不是給錯誤訊息用的。
 *
 * 🔴 三條紀律（與 PingAiKeyStore.hpp 檔頭同源，改碼前先讀那份）
 *   1. 明文不進網頁層：本層回給頁面的只有 PNG 位元組與白話錯誤字串。
 *   2. 明文不進 log：本檔任何 log 只印狀態、長度、耗時，不印值，也不印 header。
 *   3. 明文用完就地蓋掉，不留在堆疊上（同 PingAiKeyDialog::on_test 的作法）。
 *
 * ⚠ 跨平台：只用 std::string／std::vector 與既有的 Slic3r::Http，沒有 `#ifdef _WIN32`，
 *   不用 std::format／std::to_chars（Apple libc++ availability 標註會撞
 *   -mmacosx-version-min，0815 那輪 macOS CI 全紅的根因）。↳ SOP_內部測試版發布.md §1-2。
 */

namespace Slic3r {
namespace PingAiImage {

/* 失敗種類——**上層據此決定要不要重試**（R9-5），不是拿來顯示的。
   顯示用 Result::error（已經是白話中文）。 */
enum class FailKind {
    None = 0,
    NoKey,      // 沒存金鑰／保管庫讀不到 ⇒ 不重試，請使用者去填
    Auth,       // 401／403：金鑰不被接受 ⇒ 不重試（重試只會再錯一次）
    Quota,      // 429：額度用完或被限流 ⇒ 不重試（金鑰是對的，但現在打不通）
    Network,    // 連不上／逾時 ⇒ 不重試（R9-5：逾時重試只是重複燒錢）
    Response    // 連得上、回了，但回的東西不是我們要的（欄位缺、base64 壞）⇒ 不重試
};

struct Params
{
    /* 🔴 **要編輯的原圖**，不是選配。款式庫每一條 promptTemplate 都是
       「Convert **this** portrait/photo into…」＝它們全部假設有一張輸入圖
       ⇒ 走的是 images/**edits**（multipart 帶圖），不是純文字的 images/generations。
       dev 端 `照片磚管線/pipeline.py` 也是這樣打的（`draw.py --edit <src>`）——
       那是這條路的 ground truth，不是推理出來的。
       ⚠ 一律傳**使用者那張真照片**（GUI_App 的 origin），不要傳已經風格化／已經 AI 生過的圖，
         否則第二次生圖會在生成物上再生成一次，越滾越遠（同甲案的 origin 紀律）。 */
    std::string src_path;
    std::string prompt;                 // 已由上層把款式庫 promptTemplate 的佔位代換完
    std::string size    = "1024x1024";  // R9-8：只有 1024x1024／1536x1024／1024x1536
    std::string quality = "low";        // R9-8：預設 low（驗收時用數據比 low vs medium 再定案）
    long timeout_connect_s = 15;
    long timeout_max_s     = 180;       // 生圖是分鐘級的事，別用探針那種 10 秒
};

struct Result
{
    bool                       ok = false;
    std::vector<unsigned char> png;          // ok 時才有意義
    double                     elapsed_ms = 0;
    FailKind                   fail  = FailKind::None;
    std::string                error;        // 白話中文，可直接顯示給使用者
};

/* 每張的單價（新台幣）。R9-6：`gpt-image-2` 是固定級距計費 ⇒ 這是**精確值不是估計**，
   文案要寫「每張 NT$0.3」不要寫「約」。
   🔴 **資料正本＝`resources/web/phototile/款式庫_照片磚.json` 的 `constants.aiImage.unitCostNtd`**
      （頁面從那裡讀）。這裡是 C++ 側的第二份 ⇒ 已把兩者的一致性接進
      `tools/ping/verify_phototile_stylelib.py`：對不上就變紅。**改價只改 JSON，然後照閘門的話改這裡。** */
constexpr double UNIT_COST_NTD_LOW = 0.3;

// 這台機器上「現在能不能生圖」＝有沒有存金鑰。不取明文，可以隨便呼叫。
bool available();

// 同步呼叫（會阻塞）。⚠ 一定要在背景執行緒跑——生圖是數十秒的事。
Result generate(const Params& params);

// R9-8：照磚體長寬比挑生圖尺寸。回傳三種合法值之一，永遠不會回空字串。
std::string size_for_tile(double width_mm, double height_mm);

} // namespace PingAiImage
} // namespace Slic3r

#endif // slic3r_PingAiImage_hpp_
