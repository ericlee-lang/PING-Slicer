// =====================================================================
// 照片磚 C-1 黃金閘門（2026-08-02・照片磚線 PT・Codex 重要 #12 的答案）
//
// 【一版黃金六案哪裡不夠】0731 的黃金比對跑在瀏覽器裡，Codex 點名三件，實查後三件都成立：
//   ① **沒比整包 SHA**：只逐 entry 比雜湊。entry 全同但封裝方式改了（壓縮參數、
//      entry 順序、額外檔案）＝同一份「通過」的報告照樣蓋不住真正的位元組變動。
//   ② **自製 unzipper 不驗 central directory／CRC**：拿一個比產品寬鬆的解析器去證明
//      產品讀得到，等於沒證明。本檔改用 **app 自己在用的 miniz**（open_zip_reader 會讀
//      central directory；extract 會比對 CRC32）——寬鬆的那個解析器從此不參與判定。
//   ③ **沒走 C++ 宿主路徑**：證的是「瀏覽器裡的引擎 ≡ 瀏覽器裡的工作室」，
//      而產品實際走的是隱形宿主。本檔六案全部經 **PhotoTileEngineHost** 產生。
//
// 【還有一件是我自己查出來的，比上面三件更根本】
//   一版黃金的**輸入圖從來沒有被保存過**：工作室 index.html 每次載入都現場用 Canvas
//   重畫（`makeDemo()`，含 `fillText('F', ...)` 的 **bold 64px Arial**），黃金 runner
//   再從 `#srcCanvas` 即時取像素。也就是說——
//     ‧ 換一台機器／換一版瀏覽器，字體光柵化不同 ⇒ 輸入圖就不同 ⇒ 六個 SHA 全部失效
//     ‧ 而且沒有任何存檔可以回頭對照「當初那張圖到底長怎樣」
//   ⇒ 那組黃金**在結構上不可重現**，它只在產生它的那一次有效。所以 #12 說的
//     「保存 immutable golden」不是加分項，是這組資產能不能存在的前提。
//   本檔的作法：輸入 PNG 與六個 3MF 一起凍成不可變檔，輸入自己也押 SHA。
//
// 【驗什麼（每案 metadata off／on 各一輪）】
//   1. 整包 SHA-256 ＋ 位元組數（宿主算的，與閘門①／守夜同一個口徑）
//   2. entry 全集＋逐 entry SHA（用 app 的 miniz；CRC 由 miniz 解壓時把關）
//   3. **真 importer 開得起來**：Model::read_from_file ⇒ 物件／volume／三角面數
//   4. **save-reopen**：store_bbs_3mf 存一份、再讀回來，三個數字必須一致
//   5. **中文路徑**：同一份檔複製到含中文的資料夾，再用真 importer 開一次
//   6. metadata-on 的 entry 全集 ＝ off 的全集 ＋ `Metadata/ping_phototile.json`
//      （＋內嵌原圖）；**off 的位元組必須與黃金全等**＝刻意留的保命索
//
// 【第一次跑＝建基準】沒有 manifest 就寫一份並誠實標 `BASELINE_CREATED`（不是 PASS）。
// 跑法：`PING_PHOTOTILE_SMOKE=golden`（可選 `PING_PHOTOTILE_GOLDEN_DIR`）
// =====================================================================

#include "PhotoTileSmoke.hpp"
#include "PhotoTileEngineHost.hpp"
#include "PhotoTileGateJson.hpp"

#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "libslic3r/Model.hpp"
#include "libslic3r/PrintConfig.hpp"
#include "libslic3r/Utils.hpp"
#include "libslic3r/miniz_extension.hpp"
#include "libslic3r/Format/bbs_3mf.hpp"

#include <chrono>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include <boost/filesystem.hpp>
#include <boost/log/trivial.hpp>
#include <boost/nowide/fstream.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>

#include <openssl/sha.h>

#include <wx/app.h>
#include <wx/utils.h>

namespace pt = boost::property_tree;
namespace fs = boost::filesystem;

namespace Slic3r { namespace GUI {

namespace {

double gg_now_ms()
{
    using namespace std::chrono;
    return duration_cast<duration<double, std::milli>>(steady_clock::now().time_since_epoch()).count();
}

std::string gg_sha256(const unsigned char* data, size_t len)
{
    unsigned char digest[SHA256_DIGEST_LENGTH];
    SHA256(data, len, digest);
    static const char* hex = "0123456789abcdef";
    std::string out;
    out.reserve(SHA256_DIGEST_LENGTH * 2);
    for (int i = 0; i < SHA256_DIGEST_LENGTH; ++i) {
        out += hex[digest[i] >> 4];
        out += hex[digest[i] & 0x0F];
    }
    return out;
}

bool write_bytes(const std::string& path_utf8, const std::vector<unsigned char>& bytes)
{
    try {
        boost::nowide::ofstream f(path_utf8, std::ios::binary);
        if (!f) return false;
        if (!bytes.empty()) f.write((const char*) bytes.data(), (std::streamsize) bytes.size());
        return f.good();
    } catch (...) { return false; }
}

std::vector<unsigned char> read_bytes(const std::string& path_utf8)
{
    std::vector<unsigned char> out;
    try {
        boost::nowide::ifstream f(path_utf8, std::ios::binary);
        if (!f) return out;
        f.seekg(0, std::ios::end);
        const std::streamoff n = f.tellg();
        f.seekg(0, std::ios::beg);
        if (n > 0) { out.resize((size_t) n); f.read((char*) out.data(), n); }
    } catch (...) { out.clear(); }
    return out;
}

// ── zip 檢查：用 **app 自己的 miniz**，不用任何自製解析器 ────────────────
struct ZipInspect
{
    bool ok = false;                       // central directory 讀得到、每個 entry 都解得出來
    std::string error;
    std::vector<std::string> names;        // 依 zip 內順序（順序本身也是資產的一部分）
    std::map<std::string, std::string> sha;// name → sha256
};

ZipInspect inspect_zip(const std::string& path_utf8)
{
    ZipInspect z;
    mz_zip_archive zip;
    mz_zip_zero_struct(&zip);
    if (!open_zip_reader(&zip, path_utf8)) { z.error = "open_zip_reader 失敗（central directory 讀不到）"; return z; }

    /* 【二輪 I7】先做 miniz 的全檔驗證：local header vs central directory 一致性、
       descriptor、壓縮資料完整性——「entry 各自解得開」不等於「整包結構自洽」。 */
    if (!mz_zip_validate_archive(&zip, MZ_ZIP_FLAG_VALIDATE_HEADERS_ONLY)) {
        z.error = "mz_zip_validate_archive 失敗（local/central 不一致或結構損壞）";
        close_zip_reader(&zip);
        return z;
    }

    const mz_uint n = mz_zip_reader_get_num_files(&zip);
    for (mz_uint i = 0; i < n; ++i) {
        mz_zip_archive_file_stat st;
        if (!mz_zip_reader_file_stat(&zip, i, &st)) {
            z.error = "file_stat 失敗 @" + std::to_string((int) i);
            close_zip_reader(&zip);
            return z;
        }
        /* 【二輪 I7】目錄項與重名一律 FAIL：本產出永遠不該有目錄項；重名 entry 在
           std::map 會後蓋前＝比對看不見第二份（Codex 指出的靜默洞）。 */
        if (st.m_is_directory) {
            z.error = std::string("非預期的目錄項：") + st.m_filename;
            close_zip_reader(&zip);
            return z;
        }
        const std::string name = st.m_filename;
        if (z.sha.count(name)) {
            z.error = "重名 entry：" + name;
            close_zip_reader(&zip);
            return z;
        }
        size_t sz = 0;
        /* extract_to_heap 會解壓並**比對 CRC32**——這就是一版自製 unzipper 缺的那一道。
           解不出來或 CRC 不符都會回 nullptr，於是「檔案壞掉」不可能靜默通過。 */
        void* p = mz_zip_reader_extract_to_heap(&zip, i, &sz, 0);
        if (!p) {
            z.error = std::string("extract 失敗（CRC 或壓縮資料損壞）：") + st.m_filename;
            close_zip_reader(&zip);
            return z;
        }
        z.names.push_back(name);
        z.sha[name] = gg_sha256((const unsigned char*) p, sz);
        mz_free(p);
    }
    close_zip_reader(&zip);
    z.ok = true;
    return z;
}

// ── 真 importer：開得起來、而且說得出裡面有什麼 ──────────────────────────
struct ModelStat
{
    bool ok = false;
    std::string error;
    int objects = 0, volumes = 0;
    long long facets = 0;
    /* 【二輪 I8】語意 digest：三個數字擋不住「extruder 全變 1／零件名丟失／型別變了」這類
       真實劣化（照片磚的多零件配色**全靠 per-volume extruder**——丟了就是單色磚，面數不變）。
       digest 內容＝每 object：名稱｜instance 數；每 volume：名稱｜型別｜extruder｜面數，
       依序串接後 SHA-256。幾何逐頂點 hash 列 C-2（成本高、面數已在）。 */
    std::string semantic_sha;

    bool same_as(const ModelStat& o) const
    { return ok && o.ok && objects == o.objects && volumes == o.volumes && facets == o.facets &&
             semantic_sha == o.semantic_sha; }
    std::string brief() const
    { return std::to_string(objects) + " 物件／" + std::to_string(volumes) + " volume／" +
             std::to_string(facets) + " 三角面／語意 " + semantic_sha.substr(0, 12); }
};

ModelStat import_3mf(const std::string& path_utf8)
{
    ModelStat s;
    try {
        /* ⚠ 旗標一定要帶 `LoadModel`：預設只有 AddDefaultInstances ⇒ **幾何根本不會被載入**，
           importer 會在最後看到 objects 為空而丟「該檔案為空」——0802 首跑十二案全紅就是踩這個，
           而且錯得很像產品缺陷（zip 明明驗過 5 個 entry、CRC 全過）。
           正解＝照 app 自己開 3MF 的旗標組合（Plater.cpp:8221）：AddDefaultInstances | LoadModel。 */
        Model m = Model::read_from_file(path_utf8, nullptr, nullptr,
                                        LoadStrategy::AddDefaultInstances | LoadStrategy::LoadModel);
        s.objects = (int) m.objects.size();
        std::string sem;                       // 語意 digest 的原文（二輪 I8）
        for (const ModelObject* o : m.objects) {
            s.volumes += (int) o->volumes.size();
            sem += "O|" + o->name + "|inst=" + std::to_string(o->instances.size()) + "\n";
            for (const ModelVolume* v : o->volumes) {
                const long long fc = (long long) v->mesh().facets_count();
                s.facets += fc;
                const int ext = v->config.has("extruder") ? v->config.option("extruder")->getInt() : 0;
                sem += "V|" + v->name + "|t=" + std::to_string((int) v->type()) +
                       "|e=" + std::to_string(ext) + "|f=" + std::to_string(fc) + "\n";
            }
        }
        s.semantic_sha = gg_sha256((const unsigned char*) sem.data(), sem.size());
        s.ok = true;
    } catch (const std::exception& e) {
        s.error = std::string("importer 丟例外：") + e.what();
    } catch (...) {
        s.error = "importer 丟非標準例外";
    }
    return s;
}

// save-reopen：存回去再讀一次，三個數字要一致
ModelStat save_reopen(const std::string& src_utf8, const std::string& dst_utf8, std::string& store_err)
{
    ModelStat s;
    try {
        // 同上：沒有 LoadModel 就載不到幾何（0802 第二次踩同一顆——改的時候漏了這一支）
        Model m = Model::read_from_file(src_utf8, nullptr, nullptr,
                                        LoadStrategy::AddDefaultInstances | LoadStrategy::LoadModel);
        DynamicPrintConfig cfg;
        StoreParams sp;
        sp.path   = dst_utf8.c_str();
        sp.model  = &m;
        sp.config = &cfg;
        if (!store_bbs_3mf(sp)) { store_err = "store_bbs_3mf 回 false"; return s; }
    } catch (const std::exception& e) {
        store_err = std::string("存檔丟例外：") + e.what();
        return s;
    } catch (...) {
        store_err = "存檔丟非標準例外";
        return s;
    }
    return import_3mf(dst_utf8);
}

struct GoldenCase
{
    std::string label;
    std::string mode;
    double      noise_mm = 2.0;
    bool        pillar   = true;
    bool        teeth    = false;
    bool        p2a      = false;
};

// 一案跑兩輪（metadata off／on）的其中一輪
struct GoldenJob
{
    size_t case_index = 0;
    bool   metadata   = false;
    /* 【C-2 slots 反向測】探針案＝dual-default 同參數＋固定 slots，不進基準 manifest、
       不與基準比對；斷言＝生成成功且整包 SHA ≠ dual-default(off)。
       為什麼要有：C-1 的 12 案全是自動配色案，「slots 直通」那條路從來沒被走過——
       不帶 slots 的請求字串與 C-1 全等（保命索），帶了就**必須**改變輸出，否則＝直通沒生效。 */
    bool   slots_probe = false;

    // 產出與判定
    bool        generated = false;
    std::string error_code, error_message;
    std::string sha_package;
    long long   bytes = 0;
    double      ms = 0;
    ZipInspect  zip;
    ModelStat   imported, reopened;
    std::string store_error;
    bool        chinese_path_ok = false;
    std::string chinese_path_error;
    // 與黃金 manifest 比對（只有 metadata=off 那輪才有黃金）
    bool        golden_known = false, golden_package_match = false, golden_entries_match = false;
    std::vector<std::string> entry_diffs;
};

class GoldenRun;
std::unique_ptr<GoldenRun> g_golden;

class GoldenRun : public wxEvtHandler
{
public:
    GoldenRun() : m_host(new PhotoTileEngineHost())
    {
        m_host->set_status_handler([this](const std::string& s, const std::string& d) {
            if (s == "unavailable") { m_fatal = "引擎不可用：" + d; conclude(); }
        });
        m_host->set_result_handler([this](const PhotoTileEngineResult& r) { on_result(r); });

        // 六案＝與 0731 黃金 runner 的 CASES 一一對應（tools/ping/phototile_golden_runner.html）
        m_cases.push_back({ "dual-default",  "dual", 2.0, true,  false, false });
        m_cases.push_back({ "quad-default",  "quad", 2.0, true,  false, false });
        m_cases.push_back({ "quad-p2a",      "quad", 2.0, true,  false, true  });
        m_cases.push_back({ "quad-nopillar", "quad", 2.0, false, false, false });
        m_cases.push_back({ "dual-teeth",    "dual", 2.0, true,  true,  false });
        m_cases.push_back({ "dual-noise0",   "dual", 0.0, true,  false, false });
        for (size_t i = 0; i < m_cases.size(); ++i) {
            m_jobs.push_back({ i, false });
            m_jobs.push_back({ i, true  });
        }
        // 第 13 案＝slots 反向測探針（排最後＝dual-default(off) 的 SHA 必已到手）
        GoldenJob probe;
        probe.case_index  = 0;      // 借 dual-default 的參數
        probe.metadata    = false;
        probe.slots_probe = true;
        m_jobs.push_back(probe);
    }
    ~GoldenRun() override = default;

    void start()
    {
        m_t0 = gg_now_ms();

        wxString dir;
        m_dir = (wxGetEnv("PING_PHOTOTILE_GOLDEN_DIR", &dir) && !dir.empty())
                    ? into_u8(dir) : (data_dir() + "/phototile_golden");
        m_out_dir       = m_dir + "/out";
        m_cn_dir        = m_dir + "/中文路徑測試";      // #12：中文路徑必須是常規驗證的一部分
        m_manifest_path = m_dir + "/golden_manifest.json";
        m_report_path   = data_dir() + "/phototile_golden_report.json";
        try {
            fs::create_directories(fs::path(m_dir));
            fs::create_directories(fs::path(m_out_dir));
            fs::create_directories(fs::path(m_cn_dir));
        } catch (const std::exception& e) {
            m_fatal = std::string("建立黃金資料夾失敗：") + e.what();
            conclude();
            return;
        }

        if (!prepare_input()) { conclude(); return; }
        load_manifest();
        if (!m_fatal.empty()) { conclude(); return; }   // B4：manifest 損壞＝fail-closed，不起跑

        if (!m_host->start()) { m_fatal = "宿主啟動失敗"; conclude(); return; }
        run_job();
    }

private:
    /* 輸入圖：有凍結檔就用凍結檔，沒有就造一張決定性的並**當場凍結**。
       絕不現場重畫——一版黃金就是死在「輸入每次現畫、從不存檔」。 */
    bool prepare_input()
    {
        m_input_path = m_dir + "/golden_input.png";
        if (!fs::exists(fs::path(m_input_path))) {
            const std::string gen = write_photo_tile_test_image(320, 240, "phototile_golden_input.png");
            try {
                fs::copy_file(fs::path(gen), fs::path(m_input_path));
            } catch (const std::exception& e) {
                m_fatal = std::string("凍結輸入圖失敗：") + e.what();
                return false;
            }
            m_input_frozen_now = true;
        }
        const std::vector<unsigned char> b = read_bytes(m_input_path);
        if (b.empty()) { m_fatal = "輸入圖讀不到或是空的：" + m_input_path; return false; }
        m_input_sha   = gg_sha256(b.data(), b.size());
        m_input_bytes = (long long) b.size();
        return true;
    }

    void load_manifest()
    {
        if (!fs::exists(fs::path(m_manifest_path))) return;
        try {
            pt::ptree t;
            boost::nowide::ifstream f(m_manifest_path);
            pt::read_json(f, t);
            m_manifest_input_sha = t.get<std::string>("inputSha", "");
            for (const auto& kv : t.get_child("cases")) {
                GoldenRef g;
                g.sha_package = kv.second.get<std::string>("packageSha", "");
                g.bytes       = kv.second.get<long long>("bytes", 0);
                for (const auto& e : kv.second.get_child("entries"))
                    g.entries[e.first] = e.second.get_value<std::string>();
                m_golden[kv.first] = g;
            }
            m_manifest_loaded = true;
        } catch (const std::exception& e) {
            /* 【二輪 B4】manifest 存在但壞掉 ≠ 沒有基準：當「沒有」處理會讓下一輪**自動重凍**
               ＝把可能被竄改/截斷的狀態洗成新基準。fail-closed：判 FATAL、人來處理。 */
            m_golden.clear();
            m_manifest_loaded = false;
            m_fatal = std::string("manifest 存在但解析失敗（") + e.what() +
                      "）——拒絕自動重凍；請人工確認後手動刪除 " + m_manifest_path;
            BOOST_LOG_TRIVIAL(error) << "黃金 manifest 損壞，fail-closed：" << e.what();
        }
    }

    void run_job()
    {
        if (m_index >= m_jobs.size()) { conclude(); return; }
        const GoldenJob&   j = m_jobs[m_index];
        const GoldenCase&  c = m_cases[j.case_index];

        PhotoTileEngineRequest req;
        req.job_id     = "golden-" + c.label + (j.metadata ? "-meta" : "") + (j.slots_probe ? "-slots-probe" : "");
        req.mode       = c.mode;   req.nozzle = 0.4;
        req.width_mm   = 100.0;    req.height_mm = 75.0;  req.thick_mm = 6.0;
        req.klevels    = 8;        req.noise_mm  = c.noise_mm;
        req.pillar     = c.pillar; req.pillar_xy_mm = 25;
        req.teeth      = c.teeth;  req.p2a_block = c.p2a;
        req.image_path = m_input_path;
        req.want_metadata = j.metadata;
        req.embed_source  = j.metadata;     // metadata 關的那輪不得夾帶任何額外 entry
        if (j.slots_probe)                  // 紅/黑＝與自動配色（白＋主色）必不同的固定配色
            req.slots_json = "[{\"color\":\"#c0392b\"},{\"color\":\"#1a1a1a\"}]";
        m_job_t0 = gg_now_ms();
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 黃金閘門 " << req.job_id << " 起跑";
        m_host->generate(req);
    }

    void on_result(const PhotoTileEngineResult& r)
    {
        if (m_index >= m_jobs.size()) return;
        GoldenJob&        j = m_jobs[m_index];
        const GoldenCase& c = m_cases[j.case_index];
        j.ms = gg_now_ms() - m_job_t0;

        if (!r.ok) {
            j.error_code = r.error_code; j.error_message = r.error_message;
            m_all_ok = false;
            next();
            return;
        }
        j.generated   = true;
        j.sha_package = r.sha256;
        j.bytes       = (long long) r.three_mf.size();

        const std::string base = c.label + (j.metadata ? "_meta" : "") + (j.slots_probe ? "_slots_probe" : "");
        const std::string out  = m_out_dir + "/" + base + ".3mf";
        if (!write_bytes(out, r.three_mf)) {
            j.error_message = "寫檔失敗：" + out;
            m_all_ok = false;
            next();
            return;
        }

        // ① 真 zip reader（含 CRC）
        j.zip = inspect_zip(out);
        if (!j.zip.ok) m_all_ok = false;

        // ② 真 importer
        j.imported = import_3mf(out);
        if (!j.imported.ok) m_all_ok = false;

        // ③ save-reopen【二輪 I8 附註：resave 目的地改進中文資料夾＝「寫入中文路徑」也入保】
        j.reopened = save_reopen(out, m_cn_dir + "/" + base + "_resaved.3mf", j.store_error);
        if (!j.reopened.same_as(j.imported)) m_all_ok = false;

        // ④ 中文路徑：同一份檔搬進含中文的資料夾再開一次
        try {
            const std::string cn = m_cn_dir + "/" + base + ".3mf";
            if (fs::exists(fs::path(cn))) fs::remove(fs::path(cn));
            fs::copy_file(fs::path(out), fs::path(cn));
            const ModelStat cs = import_3mf(cn);
            j.chinese_path_ok = cs.same_as(j.imported);
            if (!j.chinese_path_ok) j.chinese_path_error = cs.ok ? ("內容不一致：" + cs.brief()) : cs.error;
        } catch (const std::exception& e) {
            j.chinese_path_error = std::string("中文路徑處理丟例外：") + e.what();
        }
        if (!j.chinese_path_ok) m_all_ok = false;

        /* 【C-2】slots 反向測探針：不進基準、不比基準——只斷言「帶 slots ⇒ 輸出必異」。
           與 dual-default(off) 位元組相同＝slots 直通沒生效（C-1 缺口的回歸線）。 */
        if (j.slots_probe) {
            if (m_dual_default_off_sha.empty()) {
                j.entry_diffs.push_back("slots 反向測：拿不到 dual-default(off) 的整包 SHA，無從比較");
                m_all_ok = false;
            } else if (j.sha_package == m_dual_default_off_sha) {
                j.entry_diffs.push_back("slots 反向測失敗：帶 slots 的輸出與 dual-default(off) 位元組相同＝slots 直通沒有生效");
                m_all_ok = false;
            }
            next();
            return;
        }
        if (!j.metadata && c.label == "dual-default")
            m_dual_default_off_sha = j.sha_package;   // 探針排最後＝此值必已就位

        // ⑤ 與黃金比對【二輪 B3：off 與 on **全部 12 案**都比整包 SHA＋entry 全集；
        //    先前只凍 off、on 只驗增量，verdict 卻宣稱 12 案全相符＝過度宣稱】
        {
            const std::string key = c.label + (j.metadata ? "_meta" : "");
            auto it = m_golden.find(key);
            if (it != m_golden.end()) {
                j.golden_known         = true;
                j.golden_package_match = (it->second.sha_package == j.sha_package && it->second.bytes == j.bytes);
                j.golden_entries_match = compare_entries(it->second.entries, j.zip.sha, j.entry_diffs);
                if (!j.golden_package_match || !j.golden_entries_match) m_all_ok = false;
            } else if (m_manifest_loaded) {
                /* 【二輪 B4】有基準檔卻缺這一案＝首輪凍出過不完整基準（fail-open 遺毒）。
                   缺基準不准靜默跳過——那正是「兩輪合謀假 PASS」的入口。 */
                j.entry_diffs.push_back("manifest 缺本案基準（" + key + "）＝基準不完整，判 FAIL");
                m_all_ok = false;
            }
        }
        if (!j.metadata) {
            m_off_entries[c.label] = j.zip.sha;
        } else {
            /* metadata-on 的 entry 全集必須恰好是 off 的全集 ＋ ping_phototile.json（＋內嵌原圖），
               共同 entry 一個位元組都不能動——「metadata 是 opt-in、不動黃金」的保命索。
               （B3 之後這是**第二道**不變量檢查，與整包基準比對並行，不再是唯一防線。） */
            auto off = m_off_entries.find(c.label);
            if (off != m_off_entries.end()) {
                for (const auto& kv : off->second) {
                    auto f = j.zip.sha.find(kv.first);
                    if (f == j.zip.sha.end())        j.entry_diffs.push_back("metadata-on 少了 " + kv.first);
                    else if (f->second != kv.second) j.entry_diffs.push_back("metadata-on 改動了 " + kv.first);
                }
                // 額外 entry 也擋（Codex：原版不拒絕多出來的檔）
                for (const auto& kv : j.zip.sha) {
                    if (off->second.count(kv.first)) continue;
                    if (kv.first == "Metadata/ping_phototile.json") continue;
                    if (kv.first.rfind("Metadata/ping_phototile_source.", 0) == 0) continue;
                    j.entry_diffs.push_back("metadata-on 多了非預期 entry " + kv.first);
                }
                bool has_meta = j.zip.sha.count("Metadata/ping_phototile.json") > 0;
                if (!has_meta) j.entry_diffs.push_back("metadata-on 沒有 Metadata/ping_phototile.json");
                if (!j.entry_diffs.empty()) m_all_ok = false;
            }
        }
        next();
    }

    static bool compare_entries(const std::map<std::string, std::string>& golden,
                                const std::map<std::string, std::string>& actual,
                                std::vector<std::string>& diffs)
    {
        for (const auto& kv : golden) {
            auto f = actual.find(kv.first);
            if (f == actual.end())            diffs.push_back("少了 entry " + kv.first);
            else if (f->second != kv.second)  diffs.push_back("entry 內容變了 " + kv.first);
        }
        for (const auto& kv : actual)
            if (golden.find(kv.first) == golden.end()) diffs.push_back("多了 entry " + kv.first);
        return diffs.empty();
    }

    void next() { ++m_index; write_report(false); run_job(); }

    /* 【二輪 B4：fail-closed】只有 **12/12 全部生成且全檢查通過**（m_all_ok）才寫 manifest。
       先前失敗案被靜默跳過＝首輪凍出殘缺基準、第二輪缺案不比對 ⇒ 兩輪合謀假 PASS。
       凍不出來就誠實回 FAIL_BASELINE_NOT_FROZEN，寧可再跑一輪，不留半套基準。 */
    bool manifest_complete_and_green() const
    {
        if (m_index < m_jobs.size() || !m_all_ok) return false;
        for (const GoldenJob& job : m_jobs)
            if (!job.generated || !job.zip.ok) return false;
        return true;
    }

    void write_manifest()
    {
        std::ostringstream j;
        j << "{\n"
          << "  " << jfield("_note", "照片磚黃金基準（不可變）：輸入 PNG 與 12 案（六案×metadata off/on）的整包 SHA／entry 雜湊【二輪 B3 起含 on 案】") << ",\n"
          << "  " << jfield("inputSha", m_input_sha) << ",\n"
          << "  " << jfield("inputBytes", m_input_bytes) << ",\n"
          << "  " << jstr("cases") << ": {\n";
        bool first = true;
        for (const GoldenJob& job : m_jobs) {
            if (job.slots_probe) continue;   // 探針不進基準：舊 12 鍵 manifest 繼續有效
            const std::string key = m_cases[job.case_index].label + (job.metadata ? "_meta" : "");
            if (!first) j << ",\n";
            first = false;
            j << "    " << jstr(key) << ": { " << jfield("packageSha", job.sha_package)
              << ", " << jfield("bytes", job.bytes) << ", " << jstr("entries") << ": {";
            bool fe = true;
            for (const auto& kv : job.zip.sha) {
                if (!fe) j << ",";
                fe = false;
                j << " " << jfield(kv.first.c_str(), kv.second);
            }
            j << " } }";
        }
        j << "\n  }\n}\n";
        try {
            boost::nowide::ofstream f(m_manifest_path);
            f << j.str();
        } catch (...) { BOOST_LOG_TRIVIAL(error) << "黃金 manifest 寫檔失敗：" << m_manifest_path; }
    }

    std::string verdict() const
    {
        if (!m_fatal.empty())   return "FAIL：" + m_fatal;
        if (!m_manifest_loaded) {
            /* ⚠ 建基準的那一輪**也會做** zip／importer／save-reopen／中文路徑的檢查，
               verdict 不能只寫「已建基準」把紅的蓋掉（0802 首跑教訓）。
               【二輪 B4】而且**沒有全綠就不寫 manifest**——半套基準比沒有基準更毒。 */
            if (!manifest_complete_and_green())
                return "FAIL_BASELINE_NOT_FROZEN：本輪有案未生成或檢查未過（見 cases 逐項），"
                       "**不寫 manifest**——半套基準會讓下一輪的缺案靜默不比對";
            return "BASELINE_CREATED：12/12 全綠，已凍結輸入圖與 12 案基準（off＋on）；"
                   "**建基準不等於通過**，下一次跑才會有比對結果";
        }
        if (m_input_sha != m_manifest_input_sha)
            return "FAIL：輸入圖與基準不同（基準 " + m_manifest_input_sha.substr(0, 12) +
                   "…／本次 " + m_input_sha.substr(0, 12) + "…）⇒ 其餘比對全部無意義";
        return m_all_ok ? "PASS：12 案（六案 × metadata off／on）**逐案對凍結基準**整包 SHA＋entry 全集相符；"
                          "slots 反向測（帶 slots ⇒ 輸出必異）通過；"
                          "真 importer／save-reopen（含語意 digest）／中文路徑全部通過"
                        : "FAIL：見 cases 內逐項";
    }

    void write_report(bool final_done)
    {
        std::ostringstream j;
        j << "{\n"
          << "  " << jfield("_note", "照片磚 C-1 黃金閘門（產品宿主路徑＋app 自己的 zip reader＋真 importer）") << ",\n"
          << "  " << jfield("final", final_done) << ",\n"
          << "  " << jfield("verdict", verdict()) << ",\n"
          << "  " << jfield("allOk", m_all_ok) << ",\n"
          << "  " << jfield("manifestLoaded", m_manifest_loaded) << ",\n"
          << "  " << jfield("manifestPath", m_manifest_path) << ",\n"
          << "  " << jstr("input") << ": { " << jfield("path", m_input_path) << ", "
          << jfield("sha256", m_input_sha) << ", " << jfield("bytes", m_input_bytes) << ", "
          << jfield("frozenThisRun", m_input_frozen_now) << ", "
          << jfield("_note", "一版黃金的輸入是工作室 Canvas 現場重畫（含 Arial 字體光柵化）且從未存檔"
                             "⇒ 換機器／換瀏覽器就不可重現。本檔起改為凍結檔並押 SHA。") << " },\n"
          << "  " << jfield("jobsRun", std::to_string(m_index) + "/" + std::to_string(m_jobs.size())) << ",\n"
          << "  " << jfield("totalMs", (long) (gg_now_ms() - m_t0)) << ",\n"
          << "  " << jstr("cases") << ": [\n";
        for (size_t i = 0; i < m_index && i < m_jobs.size(); ++i) {
            const GoldenJob&  job = m_jobs[i];
            const GoldenCase& c   = m_cases[job.case_index];
            j << "    { " << jfield("label", c.label)
              << ", " << jfield("metadata", job.metadata)
              << ", " << jfield("slotsProbe", job.slots_probe)
              << ", " << jfield("generated", job.generated)
              << ", " << jfield("errorCode", job.error_code)
              << ", " << jfield("errorMessage", job.error_message)
              << ", " << jfield("packageSha", job.sha_package)
              << ", " << jfield("bytes", job.bytes)
              << ", " << jfield("ms", (long) job.ms)
              << ", " << jfield("zipOk", job.zip.ok)
              << ", " << jfield("zipError", job.zip.error)
              << ", " << jfield("entryCount", (int) job.zip.names.size())
              << ", " << jfield("importOk", job.imported.ok)
              << ", " << jfield("importDetail", job.imported.ok ? job.imported.brief() : job.imported.error)
              << ", " << jfield("saveReopenOk", job.reopened.same_as(job.imported))
              << ", " << jfield("saveReopenDetail", job.store_error.empty()
                                    ? (job.reopened.ok ? job.reopened.brief() : job.reopened.error)
                                    : job.store_error)
              << ", " << jfield("chinesePathOk", job.chinese_path_ok)
              << ", " << jfield("chinesePathError", job.chinese_path_error)
              << ", " << jfield("goldenKnown", job.golden_known)
              << ", " << jfield("goldenPackageMatch", job.golden_package_match)
              << ", " << jfield("goldenEntriesMatch", job.golden_entries_match)
              << ", " << jstr("diffs") << ": [";
            for (size_t k = 0; k < job.entry_diffs.size(); ++k)
                j << (k ? ", " : "") << jstr(job.entry_diffs[k]);
            j << "], " << jstr("entries") << ": [";
            for (size_t k = 0; k < job.zip.names.size(); ++k)
                j << (k ? ", " : "") << jstr(job.zip.names[k]);
            j << "] }" << (i + 1 < m_index ? ",\n" : "\n");
        }
        j << "  ]\n}\n";
        try {
            boost::nowide::ofstream f(m_report_path);
            f << j.str();
        } catch (...) { BOOST_LOG_TRIVIAL(error) << "黃金閘門報告寫檔失敗：" << m_report_path; }
    }

    void conclude()
    {
        if (m_concluded) return;
        m_concluded = true;
        // 【二輪 B4】fail-closed：12/12 全綠才凍基準
        if (!m_manifest_loaded && m_fatal.empty() && manifest_complete_and_green()) write_manifest();
        write_report(true);
        BOOST_LOG_TRIVIAL(warning) << "PhotoTile 黃金閘門結束：" << verdict() << "（報告 " << m_report_path << "）";
        m_host->shutdown();
        wxTheApp->CallAfter([]() {
            g_golden.reset();
            if (wxGetApp().mainframe) wxGetApp().mainframe->Close(true);
        });
    }

    struct GoldenRef
    {
        std::string sha_package;
        long long   bytes = 0;
        std::map<std::string, std::string> entries;
    };

    std::unique_ptr<PhotoTileEngineHost> m_host;
    std::vector<GoldenCase> m_cases;
    std::vector<GoldenJob>  m_jobs;
    std::map<std::string, GoldenRef> m_golden;
    std::map<std::string, std::map<std::string, std::string>> m_off_entries;
    std::string m_dir, m_out_dir, m_cn_dir, m_manifest_path, m_report_path;
    std::string m_input_path, m_input_sha, m_manifest_input_sha, m_fatal;
    std::string m_dual_default_off_sha;    // slots 反向測的比較對象（dual-default off 整包 SHA）
    long long   m_input_bytes = 0;
    size_t      m_index = 0;
    double      m_t0 = 0, m_job_t0 = 0;
    bool        m_all_ok = true, m_concluded = false;
    bool        m_manifest_loaded = false, m_input_frozen_now = false;
};

} // namespace

void run_photo_tile_golden_gate()
{
    g_golden.reset(new GoldenRun());
    g_golden->start();
}

}} // namespace Slic3r::GUI
