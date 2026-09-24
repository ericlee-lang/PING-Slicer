// 測試版資料夾「首次只讀複製」的行為驗證 harness（不 build 整個 App）。
// seed_block.inc＝從本 repo 的 src/slic3r/GUI/GUI_App.cpp 原樣抽出（extract.cjs → %TEMP%\ping_dataroot_harness）。
// 跑法見同目錄 README.md（build_and_run.bat）。
#define PING_TEST_BUILD "T999"
#define SLIC3R_APP_KEY "PINGSlicer"
#include <boost/filesystem.hpp>
#include <boost/algorithm/string.hpp>
#include <boost/format.hpp>
#include <boost/nowide/fstream.hpp>
#include <boost/nowide/iostream.hpp>
#include <boost/nowide/filesystem.hpp>
#include <string>
#include <vector>
#include <map>
#include <sstream>

#include "seed_block.inc"

namespace fs = boost::filesystem;
static int g_fail = 0;
static void check(bool ok, const std::string& what)
{
    boost::nowide::cout << (ok ? "  PASS " : "  FAIL ") << what << "\n";
    if (!ok) ++g_fail;
}
static void put(const fs::path& p, const std::string& body)
{
    fs::create_directories(p.parent_path());
    boost::nowide::ofstream f(p.string(), std::ios::binary);
    f << body;
}
static std::string slurp(const fs::path& p)
{
    boost::nowide::ifstream f(p.string(), std::ios::binary);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}
// 整棵樹的快照：相對路徑 → 內容＋mtime（用來證明正式資料夾一個位元組、一個時間戳都沒動）
static std::map<std::string, std::string> snap(const fs::path& root)
{
    std::map<std::string, std::string> m;
    if (!fs::exists(root)) return m;
    for (fs::recursive_directory_iterator it(root), end; it != end; ++it) {
        const std::string rel = fs::relative(it->path(), root).generic_string();
        if (fs::is_regular_file(it->path()))
            m[rel] = slurp(it->path()) + "|mtime=" + std::to_string(fs::last_write_time(it->path()));
        else
            m[rel + "/"] = "dir|mtime=" + std::to_string(fs::last_write_time(it->path()));
    }
    return m;
}

int main(int argc, char** argv)
{
    boost::nowide::nowide_filesystem();                  // 與 App 一致（OrcaSlicer.cpp:1213）
    const fs::path base = fs::path(argv[1]);
    fs::remove_all(base);
    const fs::path roam = base / "Roaming", official = roam / "PINGSlicer", internal = roam / "PINGSlicer-Internal";

    // ── 假的正式資料夾（形狀照 2026-09-24 本機 %APPDATA%\PINGSlicer 實際列出的項目）
    put(official / "PINGSlicer.conf", "{conf}");
    put(official / "PINGSlicer.conf.bak", "bak");
    put(official / "PINGSlicer.conf.bak-3in1rename0817", "bak2");
    put(official / "PING.bak-pvaslope0724" / "x.json", "b");
    put(official / "bak-user-phototile-20260719" / "u.json", "b");
    put(official / "user_backup-v3.6.0" / "u.json", "b");
    put(official / "user_backup_20260718142549.zip", "zip");
    put(official / "system.bak-supz0817" / "PING.json", "b");
    put(official / "log" / "debug.log", "log");
    put(official / "cache" / "c.bin", "c");
    put(official / "ota" / "o.bin", "o");
    put(official / "webview2_phototile" / "EBWebView" / "x", "w");
    put(official / "system" / "PING.json", "{sys}");
    put(official / "system" / "PING" / "machine" / "DL1016.json", "{dl1016}");
    put(official / "user" / "default" / "filament" / "PLA 白（自訂）.json", "{pla}");
    put(official / "printers" / "p.json", "{p}");
    put(official / "phototile" / "material_library.json", "{lib}");
    put(official / "phototile_smoke_report.json", "{smoke}");
    const auto before = snap(official);

    boost::nowide::cout << "[1] 第一次開測試版：從正式版只讀複製\n";
    ping_seed_test_data_dir(internal);
    check(fs::is_directory(internal), "Internal 夾已建立");
    check(!fs::exists(fs::path(internal.string() + ".seeding")), "沒有殘留 .seeding 暫存夾");
    for (const char* rel : {"PINGSlicer.conf", "system/PING.json", "system/PING/machine/DL1016.json",
                            "user/default/filament/PLA 白（自訂）.json", "printers/p.json", "phototile/material_library.json",
                            "phototile_smoke_report.json", "_PING_TEST_DATA_ROOT_README.txt"})
        check(fs::is_regular_file(internal / fs::path(rel)), std::string("有抄：") + rel);
    check(slurp(internal / "phototile" / "material_library.json") == "{lib}", "材料庫內容一致");
    for (const char* rel : {"PINGSlicer.conf.bak", "PINGSlicer.conf.bak-3in1rename0817", "PING.bak-pvaslope0724",
                            "bak-user-phototile-20260719", "user_backup-v3.6.0", "user_backup_20260718142549.zip",
                            "system.bak-supz0817", "log", "cache", "ota", "webview2_phototile"})
        check(!fs::exists(internal / fs::path(rel)), std::string("沒抄：") + rel);
    check(snap(official) == before, "🔴 正式資料夾逐檔內容與時間戳完全沒變");

    boost::nowide::cout << "[2] 第二次開：已有 Internal ⇒ 永不再抄（測試版自己改過的不被蓋掉）\n";
    put(internal / "PINGSlicer.conf", "{changed-by-test-build}");
    put(official / "user" / "new_after.json", "{new}");
    const auto before2 = snap(official);
    ping_seed_test_data_dir(internal);
    check(slurp(internal / "PINGSlicer.conf") == "{changed-by-test-build}", "測試版改過的 conf 沒被正式版蓋回");
    check(!fs::exists(internal / "user" / "new_after.json"), "之後正式版新增的檔不會再被抄過來");
    check(snap(official) == before2, "🔴 正式資料夾仍完全沒變");

    boost::nowide::cout << "[3] 中途被關掉留下的 .seeding：下次重來、不留半套\n";
    const fs::path internal3 = roam / "Case3" / "PINGSlicer-Internal";
    put(roam / "Case3" / "PINGSlicer" / "PINGSlicer.conf", "{c3}");
    put(fs::path(internal3.string() + ".seeding") / "half.txt", "half");
    ping_seed_test_data_dir(internal3);
    check(fs::is_regular_file(internal3 / "PINGSlicer.conf"), "重來後有完整內容");
    check(!fs::exists(internal3 / "half.txt"), "上次半套的殘檔沒混進來");
    check(!fs::exists(fs::path(internal3.string() + ".seeding")), "暫存夾已清掉");

    boost::nowide::cout << "[4] 這台沒有正式版：不抄、從空白開始（交給 App 自己建）\n";
    const fs::path internal4 = roam / "Case4" / "PINGSlicer-Internal";
    fs::create_directories(roam / "Case4");
    ping_seed_test_data_dir(internal4);
    check(!fs::exists(internal4), "沒有正式版就不建 Internal（App 後面會自己建空的）");

    boost::nowide::cout << "[5] 防呆：target 與 official 同一處（app 名沒換成功）⇒ 什麼都不做\n";
    const auto before5 = snap(official);
    check(!ping_seed_once(official, official, ping_skip_data_entry, "設定資料夾"), "回傳 false");
    check(snap(official) == before5, "🔴 正式資料夾完全沒變");

    boost::nowide::cout << "[6] 網頁儲存區：只抄 Local Storage／IndexedDB，不抄快取、登入資料、鎖檔\n";
    const fs::path loff = base / "Local" / "PINGSlicer" / "EBWebView", lint = base / "Local" / "PINGSlicer-Internal" / "EBWebView";
    put(loff / "Default" / "Local Storage" / "leveldb" / "000003.log", "{ls}");
    put(loff / "Default" / "Local Storage" / "leveldb" / "CURRENT", "MANIFEST-000001");
    put(loff / "Default" / "Local Storage" / "leveldb" / "LOCK", "");
    put(loff / "Default" / "IndexedDB" / "x.db", "{idb}");
    put(loff / "Default" / "Login Data", "{secret}");
    put(loff / "Default" / "Cache" / "Cache_Data" / "f", "c");
    put(loff / "Default" / "History", "h");
    put(loff / "Local State", "{state}");
    const auto beforeL = snap(loff);
    ping_seed_once(loff, lint, ping_skip_webview_entry, "網頁儲存區", {"Default/Local Storage", "Default/IndexedDB"});
    check(slurp(lint / "Default" / "Local Storage" / "leveldb" / "000003.log") == "{ls}", "Local Storage 內容已抄");
    check(fs::is_regular_file(lint / "Default" / "Local Storage" / "leveldb" / "CURRENT"), "leveldb CURRENT 已抄");
    check(!fs::exists(lint / "Default" / "Local Storage" / "leveldb" / "LOCK"), "鎖檔 LOCK 沒抄");
    check(fs::is_regular_file(lint / "Default" / "IndexedDB" / "x.db"), "IndexedDB 已抄");
    check(!fs::exists(lint / "Default" / "Login Data"), "WebView 登入資料沒抄");
    check(!fs::exists(lint / "Default" / "Cache"), "快取沒抄");
    check(!fs::exists(lint / "Default" / "History"), "歷程沒抄");
    check(!fs::exists(lint / "Local State"), "Local State 沒抄（WebView2 自己建）");
    check(snap(loff) == beforeL, "🔴 正式版網頁儲存區完全沒變");

    boost::nowide::cout << "── 記錄訊息（App 會補寫進 log）\n";
    for (const auto& m : ping_seed_messages())
        boost::nowide::cout << "  " << m << "\n";
    boost::nowide::cout << (g_fail ? "結果：FAIL " : "結果：ALL PASS ") << g_fail << "\n";
    return g_fail ? 1 : 0;
}
