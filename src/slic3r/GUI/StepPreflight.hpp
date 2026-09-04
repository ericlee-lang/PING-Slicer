#ifndef slic3r_GUI_StepPreflight_hpp_
#define slic3r_GUI_StepPreflight_hpp_

#include <string>
#include "libslic3r/Format/STEP.hpp"

/* 【2026-08-24・牌 c-0824-VIBE-02】STEP 匯入前哨。

   為什麼要有這一支：`Model::read_from_step()` 在 load() 與 mesh() 之間留了一個 callback，
   ORCA 原本在三個呼叫點各自寫了一份「讀 app_config → 開 StepMeshDialog → 回傳 1 或 -1」的
   相同 lambda。前哨要加的判定與善後如果照抄三份，就會有三份可以各自長歪的版本。
   這裡把整段收成兩支函式，呼叫點只剩兩行。

   🔴 這條動線在任何情況下都不阻止切片與列印（Eric 2026-08-24 立為鐵則）。
      攔截只發生在「匯入之前」，而且對話框的預設動作就是照樣匯入；
      模型進盤面之後不留旗標、不加切片前檢查、不做二次確認。
      判定錯誤、或使用者不打算改圖，最壞的結果就是他多看到一段字。 */

namespace Slic3r { namespace GUI {

/* 一次匯入可能含好幾個 STEP 檔，所以這是**整批**的累計結果，不是單檔的。
   （初版寫成單檔覆蓋式，多檔拖放時前面的破圖檔會被最後一個無聲蓋掉。） */
struct StepPreflightResult
{
    // 使用者在某個檔的對話框裡按了「開啟 STEP 修補工具」⇒ 中止那個檔的匯入，整批結束後開修補頁。
    bool        repair_requested  = false;
    // 對話框沒跳（使用者勾過「不再顯示」），但確實有檔沒有實心結構
    // ⇒ 匯入照常完成，改用通知條講，不擋任何人。
    bool        warn_after_import = false;
    // 第一個沒有實心結構的檔名（通知條要講「拖哪一個檔」用的）。
    std::string file_name;
    // 這批裡總共幾個沒有實心結構 —— 多於一個時通知條要講清楚，不能只報一個檔名。
    int         no_solid_count = 0;
    /* 【2026-09-04・牌 c-0904-STEP-01】通知條點名的那個檔（＝第一個）是「連殼都沒有」的空檔嗎。
       空檔與「只有殼」兩種破法要講不同的話，否則會講出「沒有實心結構」這種
       對空檔而言不算錯、但完全沒幫上忙的句子。 */
    bool        first_has_no_geometry = false;
};

/* 交給 Model::read_from_step() 當 step_mesh_fn 用。
   回傳值沿用它既有的語意：1＝繼續匯入，-1＝中止。 */
int step_import_gate(Slic3r::Step&       file,
                     const std::string&  path,
                     double&             linear_value,
                     double&             angle_value,
                     bool&               is_split,
                     StepPreflightResult& out);

/* 匯入流程結束之後呼叫（不論成功、失敗或中止都要呼叫，它自己判斷該不該做事）。
   放在 read_from_step 之外是因為「開修補頁」會切換主畫面分頁，
   不能在還握著匯入進度對話框的時候做。 */
void step_preflight_followup(const StepPreflightResult& out);

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_StepPreflight_hpp_
