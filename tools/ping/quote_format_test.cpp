// 離線驗 quote.txt 契約合規性：不啟動 Slicer、不切片，只測純函式 ping_quote_format_txt。
#include "PingQuotePack.hpp"
#include <clocale>
#include <cstdio>
#include <locale>
#include <string>
#include <vector>

using namespace Slic3r::GUI;

static int g_fail = 0;
static void check(bool ok, const char *name)
{
    ::printf("%s  %s\n", ok ? "[PASS]" : "[FAIL]", name);
    if (!ok) ++g_fail;
}
static bool has(const std::string &s, const std::string &needle) { return s.find(needle) != std::string::npos; }

static PingQuotePack make_sample()
{
    PingQuotePack p;
    p.generator = "PING Slicer 3.6.0";
    p.generated_at = "2026-08-10T16:30:00+08:00";
    p.printer = "FD300";
    p.nozzle = 0.4;            p.has_nozzle = true;
    p.layer_height = 0.2;      p.has_layer_height = true;
    p.process_preset = "0.2mm @FD300 同進 (0.4)";
    p.infill_density = 15;     p.has_infill = true;
    p.support = "none";
    p.wall_loops = 2;          p.has_wall_loops = true;
    p.process_file = "process.json";
    p.mode = "per_object";

    PingQuoteObject a;
    a.name = "治具A";
    a.filaments = {"PING TPE - 210", "PING SupTPE"};
    a.size_x = 118.4; a.size_y = 62.0; a.size_z = 12.5; a.has_size = true;
    a.weight_g = 13.18; a.has_weight = true;
    a.weight_by_filament = {12.28, 0.90};
    a.time_s = 2963; a.has_time = true;
    a.filament_changes = 33; a.has_changes = true;
    a.image = "obj1.png";
    p.objects.push_back(a);

    PingQuoteObject b;
    b.name = "輪圈";
    b.filaments = {"PING PLA - 220"};
    b.size_x = 360.4; b.size_y = 360.4; b.size_z = 113.72; b.has_size = true;
    b.weight_g = 1093.0; b.has_weight = true;
    b.weight_by_filament = {1093.0};
    b.time_s = 107280; b.has_time = true;
    b.image = "obj2.png";
    p.objects.push_back(b);
    return p;
}

int main()
{
    // ── 案例 1：發包單範例重現
    const std::string s = ping_quote_format_txt(make_sample());
    ::printf("---- 產出 ----\n%s--------------\n", s.c_str());

    check(s.rfind("### PING 報價資訊 v1 ###\n", 0) == 0, "頭標記在第一行");
    check(s.size() >= 12 && s.compare(s.size() - 12, 12, "### END ###\n") == 0, "尾標記在最後一行");
    check(has(s, "\nschema=1\n"), "schema=1");
    check(has(s, "\nprinter=FD300\n"), "printer");
    check(has(s, "\nnozzle=0.4\n"), "nozzle 0.4 不長出多餘的零");
    check(has(s, "\nlayer_height=0.2\n"), "layer_height 0.2 不長出多餘的零");
    check(has(s, "\nprocess_preset=0.2mm @FD300 同進 (0.4)\n"), "process_preset 原樣");
    check(has(s, "\ninfill_density=15\n"), "infill 純數字不帶 %");
    check(!has(s, "infill_density=15%"), "infill 不得帶 %");
    check(has(s, "\nprocess_file=process.json\n"), "process_file");
    check(has(s, "\nmode=per_object\n"), "mode");
    check(has(s, "\nobjects=2\n"), "objects=2");
    check(has(s, "\n[object 1]\n"), "[object 1] 區塊");
    check(has(s, "\n[object 2]\n"), "[object 2] 區塊");
    check(has(s, "\nfilaments=PING TPE - 210;PING SupTPE\n"), "filaments 以分號分隔");
    check(has(s, "\nsize_x=118.40\n") && has(s, "\nsize_z=12.50\n"), "size 固定兩位小數");
    check(has(s, "\nweight_g=13.18\n"), "weight_g 兩位小數");
    check(has(s, "\nweight_by_filament=12.28;0.90\n"), "weight_by_filament 分號分隔");
    check(has(s, "\ntime_s=2963\n"), "time_s 為整數秒");
    check(!has(s, "m") || !has(s, "time_s=49m"), "time_s 不得輸出 49m23s 這類文字");
    check(has(s, "\nfilament_changes=33\n"), "filament_changes");
    check(has(s, "\nimage=obj1.png\n") && has(s, "\nimage=obj2.png\n"), "image 對得上");
    // 單料件沒有 filament_changes → 整行不得出現在第二段
    {
        const size_t o2 = s.find("[object 2]");
        check(s.find("filament_changes", o2) == std::string::npos, "沒給的 filament_changes 整行省略");
    }

    // ── 案例 2：抓不到的值一律整行省略，絕不輸出 0／空字串
    {
        PingQuotePack p;
        p.printer = "FD300";
        PingQuoteObject o;
        o.name = "只有名字";     // 其餘全部沒值
        p.objects.push_back(o);
        const std::string t = ping_quote_format_txt(p);
        ::printf("---- 缺值案 ----\n%s--------------\n", t.c_str());
        check(!has(t, "weight_g"), "沒重量→不出現 weight_g（不得填 0）");
        check(!has(t, "time_s"), "沒時間→不出現 time_s");
        check(!has(t, "size_x"), "沒尺寸→不出現 size_x");
        check(!has(t, "nozzle"), "沒噴嘴→不出現 nozzle");
        check(!has(t, "=0\n") && !has(t, "=\n") && !has(t, "null"), "全檔不得有 =0／空值／null");
        check(has(t, "\nobjects=1\n"), "objects=1");
    }

    // ── 案例 3：切失敗的物件整段不輸出，且 objects 要跟著少
    {
        PingQuotePack p;
        PingQuoteObject ok1; ok1.name = "好的";
        PingQuoteObject bad; bad.name = "壞的"; bad.error = "slicing failed";
        PingQuoteObject ok2; ok2.name = "也好的";
        p.objects = {ok1, bad, ok2};
        const std::string t = ping_quote_format_txt(p);
        check(has(t, "\nobjects=2\n"), "失敗件不計入 objects");
        check(!has(t, "壞的"), "失敗件整段不輸出");
        check(has(t, "[object 1]") && has(t, "[object 2]") && !has(t, "[object 3]"), "區塊編號連續不跳號");
    }

    // ── 案例 4：值裡的分號要轉全形，否則會破壞分隔語意
    {
        PingQuotePack p;
        PingQuoteObject o; o.name = "A;B";
        o.filaments = {"料;X"};
        p.objects.push_back(o);
        const std::string t = ping_quote_format_txt(p);
        check(!has(t, "name=A;B"), "物件名的半形分號不得原樣輸出");
        check(has(t, "name=A\xEF\xBC\x9B" "B"), "物件名分號轉全形");
        check(has(t, "filaments=\xE6\x96\x99\xEF\xBC\x9B" "X"), "線材名分號轉全形");
    }

    // ── 案例 4b：PING 真實存在的細口徑／薄層高，不得被四捨五入掉
    //    （0.25 口徑機型、0.125mm 層高製程都是現役的）
    {
        PingQuotePack p;
        p.nozzle = 0.25;        p.has_nozzle = true;
        p.layer_height = 0.125; p.has_layer_height = true;
        PingQuoteObject o; o.name = "細噴嘴件";
        p.objects.push_back(o);
        const std::string t = ping_quote_format_txt(p);
        check(has(t, "\nnozzle=0.25\n"), "0.25 口徑不得被截成 0.2");
        check(has(t, "\nlayer_height=0.125\n"), "0.125 層高不得被截成 0.13");
    }

    // ── 案例 5：多份複製件
    {
        PingQuotePack p;
        PingQuoteObject o; o.name = "夾具"; o.instances = 3;
        p.objects.push_back(o);
        const std::string t = ping_quote_format_txt(p);
        check(has(t, "\ninstances=3\n"), "多份時輸出 instances");
    }
    {
        PingQuotePack p;
        PingQuoteObject o; o.name = "夾具"; o.instances = 1;
        p.objects.push_back(o);
        check(!has(ping_quote_format_txt(p), "instances"), "單份時不輸出 instances");
    }

    /* ── 案例 6：語系免疫（2026-08-15 補；在此之前本測試完全沒有 locale 案）
       PingQuoteFormat.cpp 檔頭最在意的就是這條：逗號小數的系統語系下若輸出
       `weight_g=71,42`，報價系統照 key=value 解析不是失敗就是只讀到 71＝算錯錢。
       但本測試一直沒有任何一案會踩到 locale，等於那條規則沒有守門員——
       0815 把 to_chars 換成 ostringstream 時才發現這個缺口，順手補上。
       ⚠ 一定要「兩種都設」：snprintf/std::to_string 吃 setlocale(LC_NUMERIC)，
         未 imbue 的 ostream 吃 std::locale::global()，只設一種會漏掉另一條路。 */
    {
        const char *saved = ::setlocale(LC_NUMERIC, nullptr);
        std::string saved_s = saved ? saved : "C";
        bool applied = (::setlocale(LC_NUMERIC, "de-DE") != nullptr);
        std::locale saved_global;
        bool global_applied = false;
        try { saved_global = std::locale::global(std::locale("de-DE")); global_applied = true; }
        catch (...) { /* 該語系不存在就只測 setlocale 那條路 */ }

        if (!applied && !global_applied) {
            ::printf("[SKIP]  逗號小數語系不可用，語系免疫案跳過\n");
        } else {
            PingQuotePack p;
            p.nozzle = 0.4;       p.has_nozzle = true;
            p.layer_height = 0.2; p.has_layer_height = true;
            PingQuoteObject o; o.name = "語系件"; o.weight_g = 71.42; o.has_weight = true;
            p.objects.push_back(o);
            const std::string t = ping_quote_format_txt(p);
            check(has(t, "weight_g=71.42"), "逗號小數語系下仍輸出小數點（weight_g）");
            check(!has(t, "71,42"), "逗號小數語系下不得出現逗號小數");
            check(has(t, "\nnozzle=0.4\n"), "逗號小數語系下 nozzle 仍是小數點");
        }
        if (global_applied) std::locale::global(saved_global);
        ::setlocale(LC_NUMERIC, saved_s.c_str());
    }

    ::printf("\n%s  失敗 %d 項\n", g_fail == 0 ? "全部通過" : "有失敗", g_fail);
    return g_fail == 0 ? 0 : 1;
}
