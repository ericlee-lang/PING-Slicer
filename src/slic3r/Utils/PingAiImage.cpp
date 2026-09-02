#include "PingAiImage.hpp"

#include "PingAiKeyStore.hpp"
#include "Http.hpp"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>

#include <boost/filesystem.hpp>

#include <boost/beast/core/detail/base64.hpp>
#include <boost/log/trivial.hpp>
#include <nlohmann/json.hpp>

namespace Slic3r {
namespace PingAiImage {

namespace {

/* R9-1：供應商與模型已裁，換掉等於重做（金鑰框、測試連線、存取層整條都照 OpenAI 蓋）。
   🔴 端點是 **edits** 不是 generations：款式庫每一條 promptTemplate 都寫
      「Convert **this** portrait/photo into…」＝全部假設有一張輸入圖。
      ground truth＝dev 端 `照片磚管線/pipeline.py` 打的就是 `draw.py --edit <src>`
      （＝`client.images.edit(model, image, prompt, size, quality, n)`）。 */
const char* API_URL = "https://api.openai.com/v1/images/edits";
const char* MODEL   = "gpt-image-2";

/* R9-8：`gpt-image-2` 只有這三種尺寸，不是任意值。 */
const char* SIZE_SQUARE    = "1024x1024";
const char* SIZE_LANDSCAPE = "1536x1024";
const char* SIZE_PORTRAIT  = "1024x1536";

// 明文用完就地蓋掉（紀律 3）。std::fill 不會被最佳化掉的程度足夠本用途；
// 這一層真正的防線是「明文只在這個函式的生命週期內存在」。
void wipe(std::string& s)
{
    std::fill(s.begin(), s.end(), '\0');
    s.clear();
}

/* OpenAI 只收 png／jpeg／webp。**要明講型別**——`Http::form_add_file` 把 part 的
   Content-Type 寫死成 application/octet-stream，那正是「格式不合」400 的常見來源
   ⇒ 本檔改用 form_add_file_typed（2026-09-02 為此新增的多載）。
   認不得的副檔名**直接擋下並講人話**，不要送出去換一個看不懂的錯誤。 */
std::string mime_of(const std::string& path)
{
    std::string ext;
    const size_t dot = path.find_last_of('.');
    if (dot != std::string::npos)
        for (size_t i = dot + 1; i < path.size(); ++i)
            ext += static_cast<char>(std::tolower(static_cast<unsigned char>(path[i])));
    if (ext == "png")                   return "image/png";
    if (ext == "jpg" || ext == "jpeg")  return "image/jpeg";
    if (ext == "webp")                  return "image/webp";
    return std::string();
}

Result fail_with(FailKind kind, const std::string& message, double elapsed_ms)
{
    Result r;
    r.ok         = false;
    r.fail       = kind;
    r.error      = message;
    r.elapsed_ms = elapsed_ms;
    return r;
}

/* HTTP 狀態碼 → 重試策略分類（R9-5）。
   🔴 這裡的分類**只看「重試有沒有意義」**，不看嚴重程度：
      401 與 429 對使用者的感受天差地遠，但對重試策略是同一件事＝不要重試。 */
FailKind kind_of_status(unsigned status)
{
    if (status == 401 || status == 403)
        return FailKind::Auth;
    if (status == 429)
        return FailKind::Quota;
    return FailKind::Network;
}

std::string message_of_status(unsigned status, const std::string& error)
{
    if (status == 401 || status == 403)
        return "這把 AI 金鑰不被接受（可能貼錯或已失效）。請到「說明 → 設定 AI 生圖服務金鑰」換一把。";
    if (status == 429)
        return "AI 服務回覆額度用完或被限流——金鑰本身是對的，稍後再試。";
    if (status >= 500)
        return "AI 服務暫時異常（伺服器回 " + std::to_string(status) + "），請稍後再試。";
    if (status == 400)
        return "AI 服務不接受這次的生圖要求（400）。這通常是 prompt 或尺寸不合規，換一個款式再試。";
    return "連不上 AI 服務（" + (error.empty() ? std::string("沒有回應") : error) + "）。請確認網路。";
}

} // namespace

bool available()
{
    // 只問「有沒有」，不取明文 ⇒ 這支可以被任何人呼叫（含頁面可達的布林通道）。
    return PingAiKey::has();
}

std::string size_for_tile(double width_mm, double height_mm)
{
    /* R9-8：照磚體長寬比自動挑，不讓使用者選——選錯會讓 prompt 裡
       「Nothing narrower than {minPx} pixels」失準，而使用者沒有判斷依據。
       ⚠ 非法輸入（0／負數／NaN）一律回方形：這支的契約是「永遠回三種合法值之一」，
          回空字串會讓上層把非法值送進 API，換來一個看不懂的 400。 */
    if (!(width_mm > 0.0) || !(height_mm > 0.0))
        return SIZE_SQUARE;

    const double ratio = width_mm / height_mm;
    if (ratio >= 1.2)
        return SIZE_LANDSCAPE;
    if (ratio <= 1.0 / 1.2)
        return SIZE_PORTRAIT;
    return SIZE_SQUARE;
}

Result generate(const Params& params)
{
    const auto started = std::chrono::steady_clock::now();
    const auto ms_since = [&started]() {
        return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    };

    if (params.prompt.empty())
        return fail_with(FailKind::Response, "這個款式沒有可用的生圖描述，請換一個款式。", ms_since());

    /* 原圖是必要輸入（見 hpp 的 src_path 說明）。三種失敗要分開講，
       因為使用者能做的事完全不同：沒圖→去載入、格式不收→另存、檔不見→重載。 */
    if (params.src_path.empty())
        return fail_with(FailKind::Response, "還沒有可用的影像來源，請先載入一張照片。", ms_since());
    const boost::filesystem::path src(params.src_path);
    if (!boost::filesystem::exists(src))
        return fail_with(FailKind::Response, "找不到原始照片檔，請重新載入圖片再試。", ms_since());
    const std::string mime = mime_of(params.src_path);
    if (mime.empty())
        return fail_with(FailKind::Response,
                         "這個影像格式 AI 服務不收（只支援 PNG／JPG／WebP），請另存成 PNG 再試。",
                         ms_since());

    std::string secret;
    if (!PingAiKey::load(secret)) {   // ⚠ 全專案第二個明文取用點（閘門白名單管的就是這裡）
        wipe(secret);
        return fail_with(FailKind::NoKey,
                         "還沒有設定 AI 生圖金鑰。請到「說明 → 設定 AI 生圖服務金鑰」填一把再試。",
                         ms_since());
    }

    BOOST_LOG_TRIVIAL(info) << "PhotoTile AI 生圖：送出 model=" << MODEL
                            << ", size=" << params.size
                            << ", quality=" << params.quality
                            << ", prompt_len=" << params.prompt.size()
                            << ", src=" << src.filename().string();

    std::string response_body;
    std::string transport_error;
    unsigned    http_status = 0;
    bool        completed   = false;

    /* multipart：欄位名與 dev 端 client.images.edit(...) 的參數一一對應。
       ⚠ **不要**自己下 Content-Type header——multipart 的 boundary 由 curl 產生，
         手寫會把整個請求打壞。 */
    Http::post(std::string(API_URL))
        .header("Authorization", std::string("Bearer ") + secret)
        .form_add("model", MODEL)
        .form_add("prompt", params.prompt)
        .form_add("size", params.size)
        .form_add("quality", params.quality)
        .form_add("n", "1")
        .form_add_file_typed("image", src, src.filename().string(), mime)
        .timeout_connect(params.timeout_connect_s)
        .timeout_max(params.timeout_max_s)
        .on_complete([&response_body, &completed](std::string content, unsigned /*status*/) {
            response_body = std::move(content);
            completed     = true;
        })
        .on_error([&transport_error, &http_status](std::string /*content*/, std::string error, unsigned status) {
            transport_error = std::move(error);
            http_status     = status;
        })
        .perform_sync();

    // 紀律 3：明文用完就地蓋掉。Http 已經複製走它需要的那一份。
    wipe(secret);

    if (!completed)
        return fail_with(kind_of_status(http_status), message_of_status(http_status, transport_error), ms_since());

    /* 回來了，但回的是什麼要自己確認——「連得上」不等於「拿到圖」。
       gpt-image 系列固定回 base64（沒有 url 模式），欄位＝data[0].b64_json。 */
    std::string b64;
    try {
        const nlohmann::json parsed = nlohmann::json::parse(response_body);
        if (parsed.contains("error")) {
            const std::string upstream = parsed["error"].value("message", std::string());
            return fail_with(FailKind::Response,
                             "AI 服務回報錯誤：" + (upstream.empty() ? std::string("未說明原因") : upstream),
                             ms_since());
        }
        if (!parsed.contains("data") || !parsed["data"].is_array() || parsed["data"].empty())
            return fail_with(FailKind::Response, "AI 服務沒有回傳任何圖片。", ms_since());
        b64 = parsed["data"][0].value("b64_json", std::string());
    } catch (const std::exception&) {
        return fail_with(FailKind::Response, "AI 服務的回應讀不懂（不是預期的格式）。", ms_since());
    }

    if (b64.empty())
        return fail_with(FailKind::Response, "AI 服務回傳的圖片是空的。", ms_since());

    Result r;
    r.png.resize(boost::beast::detail::base64::decoded_size(b64.size()));
    const auto decoded = boost::beast::detail::base64::decode(r.png.data(), b64.data(), b64.size());
    r.png.resize(decoded.first);
    if (r.png.empty())
        return fail_with(FailKind::Response, "AI 服務回傳的圖片解不開。", ms_since());

    r.ok         = true;
    r.fail       = FailKind::None;
    r.elapsed_ms = ms_since();
    BOOST_LOG_TRIVIAL(info) << "PhotoTile AI 生圖：完成 bytes=" << r.png.size()
                            << ", " << r.elapsed_ms << " ms";
    return r;
}

} // namespace PingAiImage
} // namespace Slic3r
