// =====================================================================
// PING 報價包 — quote.txt 格式產生器（介面契約 v1.1）
//
// 這一段刻意與 PingQuotePack.cpp 分開放：它是**純函式**，不碰 GUI、不碰 GL、
// 不碰切片引擎，只依賴 PingQuotePack.hpp 與標準函式庫。
//
// 為什麼要拆：quote.txt 是交給代印報價系統解析的**契約產物**，格式錯了對方就長不出
// 報價列。拆開之後這支可以用一個獨立小程式離線驗（不必啟動整個 Slicer、不必真的切片），
// 契約合規性就能在每次改動後很便宜地重驗一次 —— tools/ping/quote_format_test.bat
//
// ⚠ 動這個檔＝動介面契約。欄位的新增／改名／改語意／改單位都要兩邊同意，
//   不得單方變更（見 PingQuotePack.hpp 檔頭）。
// =====================================================================

#include "PingQuotePack.hpp"

#include <charconv>
#include <cmath>
#include <string>
#include <system_error>
#include <vector>

namespace Slic3r { namespace GUI {

// ---------------------------------------------------------------------
// 數值格式化
//
// 【一律用 std::to_chars，不用 snprintf 也不用 std::to_string】
// 這兩者都吃 `LC_NUMERIC`：在逗號小數的系統語系下會輸出 `weight_g=71,42`，
// 報價系統照 key=value 解析不是失敗就是只讀到 71 —— 直接算錯錢。
// 本 fork 只在特定 scope 用 RAII 的 CNumericLocalesSetter，GUI 執行緒**沒有**
// 全域強制 C locale（GUI_App.cpp 那行 wxSetlocale(LC_NUMERIC,"C") 是註解掉的），
// 所以不能假設「反正跑起來是 C locale」。
// to_chars 定義上就與 locale 無關，而且不必把 libslic3r 拉進這個 TU（離線測試才編得動）。
//
// 失敗回傳空字串 ⇒ 呼叫端整行不輸出（符合契約「抓不到的值整行省略」）。
// ---------------------------------------------------------------------
static std::string fixed(double v, int decimals)
{
    if (!std::isfinite(v))
        return std::string();
    char       buf[64];
    const auto r = std::to_chars(buf, buf + sizeof(buf), v, std::chars_format::fixed, decimals);
    if (r.ec != std::errc())
        return std::string();
    return std::string(buf, r.ptr);
}

// 口徑與層高**不能用固定小數位**。PING 實際存在 0.25 口徑與 0.125mm 層高：
//   固定 1 位 ⇒ 0.25 變 "0.2"；固定 2 位 ⇒ 0.125 變 "0.13"。
// 兩者都是靜默把數字改掉，報價系統收到的會是錯的機器設定。
// 所以這兩欄一律「取到三位，再把尾隨的零與小數點去掉」：0.4→"0.4"、0.25→"0.25"、0.125→"0.125"。
static std::string trimmed(double v, int max_decimals)
{
    std::string s = fixed(v, max_decimals);
    if (s.empty())
        return s;
    if (s.find('.') != std::string::npos) {
        while (!s.empty() && s.back() == '0') s.pop_back();
        if (!s.empty() && s.back() == '.') s.pop_back();
    }
    return s.empty() ? std::string("0") : s;
}

// 四捨五入到兩位（＝實際會送出去的精度）。
// 一致性檢查一律拿這個比，不要拿原始 double 比——契約要求的是「送出去的數字相加相等」，
// 檢查原始值通過、印出來卻對不上，等於沒檢查。
static double round2(double v) { return std::round(v * 100.0) / 100.0; }

// 契約：`;` 是分隔符，值本身不得包含 `;`（物件名若含分號改成全形「；」）。
// 順手把換行也清掉——名稱裡有換行會直接切斷 key=value 結構。
//
// ⚠ 值內的 `=` 刻意**不動**：改了會把客戶的檔名弄壞。契約 4-4 需補一句
//   「接收端只以第一個 `=` 分隔」，此事已列入回報代印線清單。
static std::string sanitize_value(const std::string &in)
{
    std::string out;
    out.reserve(in.size());
    for (char c : in) {
        if (c == ';')
            out += "\xEF\xBC\x9B"; // 全形分號 U+FF1B
        else if (c == '\r' || c == '\n')
            out += ' ';
        else
            out += c;
    }
    return out;
}

static std::string join_semicolon(const std::vector<std::string> &v)
{
    std::string out;
    for (size_t i = 0; i < v.size(); ++i) {
        if (i) out += ";";
        out += v[i];
    }
    return out;
}

std::string ping_quote_format_txt(const PingQuotePack &pack)
{
    std::string s;
    s += "### PING 報價資訊 v1 ###\n";
    s += "schema=1\n";
    if (!pack.generator.empty())      s += "generator=" + sanitize_value(pack.generator) + "\n";
    if (!pack.generated_at.empty())   s += "generated_at=" + pack.generated_at + "\n";
    if (!pack.printer.empty())        s += "printer=" + sanitize_value(pack.printer) + "\n";
    if (pack.has_nozzle) {
        const std::string v = trimmed(pack.nozzle, 3);
        if (!v.empty())               s += "nozzle=" + v + "\n";
    }
    if (pack.has_layer_height) {
        const std::string v = trimmed(pack.layer_height, 3);
        if (!v.empty())               s += "layer_height=" + v + "\n";
    }
    if (!pack.process_preset.empty()) s += "process_preset=" + sanitize_value(pack.process_preset) + "\n";
    // 使用者手動改過參數（代印線 Q5 採用）。沒改就整行省略。
    if (pack.process_modified)        s += "process_modified=1\n";
    if (pack.has_infill)              s += "infill_density=" + std::to_string(pack.infill_density) + "\n";
    if (!pack.support.empty())        s += "support=" + pack.support + "\n";
    if (pack.has_wall_loops)          s += "wall_loops=" + std::to_string(pack.wall_loops) + "\n";
    if (!pack.process_file.empty())   s += "process_file=" + pack.process_file + "\n";
    // restore_file 只在還原檔真的進包時才寫（代印線指出的一致性要求）。
    if (!pack.restore_file.empty())   s += "restore_file=" + pack.restore_file + "\n";

    // 只數真的有輸出的物件（切失敗的那件整段不出現，objects 必須與區塊數一致）
    int emitted = 0;
    for (const auto &o : pack.objects)
        if (o.error.empty()) ++emitted;

    s += "mode=" + pack.mode + "\n";
    s += "objects=" + std::to_string(emitted) + "\n";
    // 有物件切失敗時一定要講。否則輸出「少一件但內部完全自洽」，
    // 報價系統無從得知，業務就漏報了那一件的錢。
    // （此欄尚未進契約 v1.1，但契約明訂不認識的欄位會忽略；已列入回報清單。）
    if (pack.objects_failed > 0)
        s += "objects_failed=" + std::to_string(pack.objects_failed) + "\n";

    int idx = 0;
    for (const auto &o : pack.objects) {
        if (!o.error.empty())
            continue;
        ++idx;
        s += "\n[object " + std::to_string(idx) + "]\n";
        s += "name=" + sanitize_value(o.name) + "\n";

        // ── 重量：一律用「即將送出的兩位小數」判斷，不是用原始 double
        const double wr = round2(o.weight_g);
        // 有重量、但四捨五入後變成 0.00 ⇒ 整行省略。
        // 印 0.00 會被報價系統當成「這件真的 0 克」拿去算錢＝免費送人。
        const bool weight_ok = o.has_weight && wr > 0.0;
        std::string weight_str = weight_ok ? fixed(o.weight_g, 2) : std::string();

        // 料名與逐料重量是**兩個獨立欄位**：重量對不上不代表料名是錯的，
        // 不要一起吞掉（少送 filaments 等於白白讓報價單少一項資訊）。
        std::vector<std::string> fils;
        for (const auto &f : o.filaments)
            fils.push_back(sanitize_value(f));

        std::vector<std::string> parts;
        bool                     breakdown_ok = !o.weight_by_filament.empty() &&
                                                o.weight_by_filament.size() == o.filaments.size();
        if (breakdown_ok) {
            double sum_rounded = 0.;
            for (size_t i = 0; i < o.weight_by_filament.size(); ++i) {
                const double raw = o.weight_by_filament[i];
                const double r   = round2(raw);
                if (r <= 0.0 && raw > 0.0) { breakdown_ok = false; break; }  // 正值被印成 0.00
                const std::string ps = fixed(raw, 2);
                if (ps.empty()) { breakdown_ok = false; break; }
                parts.push_back(ps);
                sum_rounded += r;
            }
            // 契約：相加必須等於 weight_g。比的是**捨入後**的值，因為那才是對方會看到的數字。
            if (breakdown_ok && weight_ok && std::fabs(sum_rounded - wr) > 0.005)
                breakdown_ok = false;
        }
        if (!breakdown_ok) parts.clear();   // 只丟重量明細，料名保留

        if (!fils.empty())        s += "filaments=" + join_semicolon(fils) + "\n";
        if (o.has_size) {
            const std::string x = fixed(o.size_x, 2), y = fixed(o.size_y, 2), z = fixed(o.size_z, 2);
            if (!x.empty() && !y.empty() && !z.empty()) {
                s += "size_x=" + x + "\n";
                s += "size_y=" + y + "\n";
                s += "size_z=" + z + "\n";
            }
        }
        if (!weight_str.empty()) s += "weight_g=" + weight_str + "\n";
        if (!parts.empty())      s += "weight_by_filament=" + join_semicolon(parts) + "\n";
        if (o.has_time)          s += "time_s=" + std::to_string(o.time_s) + "\n";
        if (o.has_changes)       s += "filament_changes=" + std::to_string(o.filament_changes) + "\n";
        if (o.instances > 1)     s += "instances=" + std::to_string(o.instances) + "\n";
        // 僅在該物件有物件層級參數覆寫時才給（契約 4-3）
        if (!o.process_file.empty()) s += "process_file=" + o.process_file + "\n";
        if (!o.image.empty())    s += "image=" + o.image + "\n";
    }

    s += "### END ###\n";
    return s;
}

}} // namespace Slic3r::GUI
