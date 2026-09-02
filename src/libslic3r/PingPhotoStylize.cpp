// PING 照片磚「本地風格化」實作。裁定、演算法出處與參數理由見 PingPhotoStylize.hpp 檔頭。

#include "PingPhotoStylize.hpp"

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>

#include <boost/nowide/fstream.hpp>
#include <boost/log/trivial.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <utility>

namespace Slic3r {

namespace {

// "#RRGGBB" → BGR（OpenCV 的順序）。解不出來回 false，呼叫端一律 fail-closed。
bool hex_to_bgr(const std::string& hex, cv::Vec3b& out)
{
    if (hex.size() != 7 || hex[0] != '#')
        return false;
    auto nib = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    int v[6];
    for (int i = 0; i < 6; ++i) {
        v[i] = nib(hex[i + 1]);
        if (v[i] < 0) return false;
    }
    out = cv::Vec3b(static_cast<uchar>(v[4] * 16 + v[5]),   // B
                    static_cast<uchar>(v[2] * 16 + v[3]),   // G
                    static_cast<uchar>(v[0] * 16 + v[1]));  // R
    return true;
}

// 讀檔案位元組再 imdecode——**不要用 cv::imread**：它吃的是本地 8-bit 路徑，
// Windows 上遇到中文路徑會靜默讀不到（回空 Mat），而使用者的照片放在中文資料夾是常態。
bool imread_utf8(const std::string& path, cv::Mat& out)
{
    boost::nowide::ifstream in(path.c_str(), std::ios::binary);
    if (!in.good())
        return false;
    std::vector<unsigned char> bytes((std::istreambuf_iterator<char>(in)),
                                      std::istreambuf_iterator<char>());
    in.close();
    if (bytes.empty())
        return false;
    out = cv::imdecode(cv::Mat(1, static_cast<int>(bytes.size()), CV_8UC1, bytes.data()),
                       cv::IMREAD_COLOR);
    return !out.empty();
}

} // namespace

PhotoStylizeResult ping_photo_stylize(const PhotoStylizeParams& params)
{
    PhotoStylizeResult res;
    const auto t_begin = std::chrono::steady_clock::now();

    // ── 前置驗證：全部 fail-closed，訊息要講得出「下一步做什麼」 ──────────────
    const int K = params.tones;
    if (K < 2 || K > 8) {
        res.error = "色階數超出範圍（2~8），無法風格化。";
        return res;
    }
    // ramp 的意義依對映模式而異（見 .hpp）：Rank ⇒ 恰 K 階的梯子；NearestDistinct ⇒ ≥K 個候選色（四料最多 64）。
    const int  N    = static_cast<int>(params.ramp_hex.size());
    const bool rank = (params.mapping == PhotoStylizeMapping::Rank);
    if (rank ? (N != K) : (N < K || N > 64)) {
        res.error = rank ? "色階顏色數量與色階數不符，無法風格化。"
                         : "候選色數量不足或超出上限（64），無法風格化。";
        return res;
    }
    std::vector<cv::Vec3b> ramp(N);
    for (int i = 0; i < N; ++i) {
        if (!hex_to_bgr(params.ramp_hex[i], ramp[i])) {
            res.error = "色階顏色格式錯誤，無法風格化。";
            return res;
        }
    }
    const int work_w = std::max(64, std::min(2400, params.work_width));

    cv::Mat img;
    if (!imread_utf8(params.src_path, img)) {
        res.error = "讀不到來源影像，請重新載入圖片再試。";
        return res;
    }

    try {
        // ── ① 縮到工作解析度 ─────────────────────────────────────────────
        // INTER_AREA＝縮圖專用（做面積平均），與 pipeline.py 同；用 INTER_LINEAR 會留下鋸齒
        // 給後面的 mean-shift 當成邊界抓，畫面會多出假的色塊邊。
        if (img.cols != work_w) {
            const int h = std::max(1, static_cast<int>(std::lround(
                static_cast<double>(img.rows) * work_w / img.cols)));
            cv::resize(img, img, cv::Size(work_w, h), 0, 0, cv::INTER_AREA);
        }

        // ── ② 邊緣保留平滑 ×3（pipeline.py：bilateralFilter(9, 60, 12) 跑三次）──
        // 跑三次不是筆誤：單次 sigma 拉大會糊掉邊界，多次小 sigma 才能「面平掉、邊留著」。
        for (int i = 0; i < 3; ++i) {
            cv::Mat tmp;
            cv::bilateralFilter(img, tmp, 9, 60, 12);
            img = tmp;
        }

        // ── ③ mean-shift 成塊（sp=18, sr=32, maxLevel=2）────────────────────
        // 這一步才是「變成海報」的那一步：把相近顏色收斂到同一個模式，產生真正的平色塊。
        // 也是全鏈最慢的一步（800px 約佔一半時間）。
        {
            cv::Mat tmp;
            cv::pyrMeanShiftFiltering(img, tmp, 18, 32, 2);
            img = tmp;
        }

        // ── ④ Lab 空間 k-means 分 K 群 ────────────────────────────────────
        // 在 Lab 上分群＝按「人眼看起來的差異」分，不是按 RGB 數值距離分。
        cv::Mat rgb_f;
        cv::cvtColor(img, rgb_f, cv::COLOR_BGR2RGB);
        rgb_f.convertTo(rgb_f, CV_32FC3, 1.0 / 255.0);
        cv::Mat lab;
        cv::cvtColor(rgb_f, lab, cv::COLOR_RGB2Lab);
        cv::Mat samples = lab.reshape(1, lab.rows * lab.cols);   // N×3 float

        cv::Mat labels, centers;
        const cv::TermCriteria crit(cv::TermCriteria::EPS + cv::TermCriteria::MAX_ITER, 40, 0.3);
        cv::kmeans(samples, K, labels, crit, 5, cv::KMEANS_PP_CENTERS, centers);

        cv::Mat L = labels.reshape(1, img.rows);
        L.convertTo(L, CV_8U);

        // ── ⑤ 形態學清理（medianBlur 5 再 7）──────────────────────────────
        // 對「標籤圖」取中位數＝把散在色塊裡的孤點併回去。先 5 再 7 是 pipeline.py 的順序。
        for (int ks : {5, 7}) {
            cv::Mat tmp;
            cv::medianBlur(L, tmp, ks);
            L = tmp;
        }

        std::vector<cv::Vec3b> cluster_color(K);
        if (rank) {
            // ── ⑥a 雙料：套色階，最暗的群配最暗的階 ──────────────────────────
            // 🔴 排序依據是 centers 的 L*（第 0 欄）。配反了整張變負片——pipeline.py 的
            //    註解就寫著這件事，是實際踩過的。
            std::vector<int> order(K);
            std::iota(order.begin(), order.end(), 0);
            std::sort(order.begin(), order.end(), [&centers](int a, int b) {
                return centers.at<float>(a, 0) < centers.at<float>(b, 0);   // L* 由小到大＝暗→亮
            });
            // ramp[0] ＝最亮端（料A）… ramp[K-1] ＝最暗端（料B）
            // ⇒ 最暗的群（order[0]）要拿 ramp[K-1]。
            for (int r = 0; r < K; ++r)
                cluster_color[order[r]] = ramp[K - 1 - r];
        } else {
            // ── ⑥b 四料：每群配「最近、且與已配過的顏色相距 ≥3 ΔE」的候選色 ────────
            // （Eric 2026-09-03 裁③，離線用 10 張 AI 圖 × 兩個四料款式實測導出）
            // 四料的調色盤不是一維梯子（6 條兩兩色階線 × K 階，最多 64 色），沒有「亮→暗」可排，
            // 改在 Lab 上找最近候選。**不重複**是為了保住款式設計的 K 階：純最近會讓兩群併成
            // 同一色（實測約一半案例少一階＝雙料「身體消失」那型）。候選色之間本來就有相距不到
            // 3 ΔE 的近親（深藍 vs 近黑），只比 index 的「不重複」會挑到肉眼同色的另一格，
            // 所以判準是 ΔE ≥ 3。大群先挑：主色先拿到最貼近的候選，小群退讓。
            cv::Mat pal_bgr(1, N, CV_8UC3);
            for (int i = 0; i < N; ++i)
                pal_bgr.at<cv::Vec3b>(0, i) = ramp[i];
            cv::Mat pal_f, pal_lab;
            cv::cvtColor(pal_bgr, pal_f, cv::COLOR_BGR2RGB);
            pal_f.convertTo(pal_f, CV_32FC3, 1.0 / 255.0);
            cv::cvtColor(pal_f, pal_lab, cv::COLOR_RGB2Lab);   // 與影像同一條轉換，才能同尺度比距離
            const auto lab_dist = [](const cv::Vec3f& a, const cv::Vec3f& b) {
                const cv::Vec3f d = a - b;
                return std::sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
            };
            std::vector<int> sizes(K, 0);
            for (int y = 0; y < L.rows; ++y) {
                const uchar* lrow = L.ptr<uchar>(y);
                for (int x = 0; x < L.cols; ++x)
                    if (lrow[x] < K) ++sizes[lrow[x]];
            }
            std::vector<int> order(K);
            std::iota(order.begin(), order.end(), 0);
            std::sort(order.begin(), order.end(), [&sizes](int a, int b) { return sizes[a] > sizes[b]; });
            std::vector<int> picked;
            picked.reserve(K);
            for (const int c : order) {
                const cv::Vec3f center(centers.at<float>(c, 0), centers.at<float>(c, 1), centers.at<float>(c, 2));
                std::vector<std::pair<float, int>> ds;
                ds.reserve(N);
                for (int i = 0; i < N; ++i)
                    ds.emplace_back(lab_dist(center, pal_lab.at<cv::Vec3f>(0, i)), i);
                std::sort(ds.begin(), ds.end());
                int pick = ds.front().second;              // 全部都太近時退回純最近（誠實：寧可少一階也不亂配）
                for (const auto& di : ds) {
                    const int i = di.second;
                    bool near_taken = false;
                    for (const int p : picked)
                        if (lab_dist(pal_lab.at<cv::Vec3f>(0, i), pal_lab.at<cv::Vec3f>(0, p)) < 3.0f) {
                            near_taken = true;
                            break;
                        }
                    if (!near_taken) { pick = i; break; }
                }
                picked.push_back(pick);
                cluster_color[c] = ramp[pick];
            }
        }

        cv::Mat out(img.rows, img.cols, CV_8UC3);
        for (int y = 0; y < img.rows; ++y) {
            const uchar*  lrow = L.ptr<uchar>(y);
            cv::Vec3b*    orow = out.ptr<cv::Vec3b>(y);
            for (int x = 0; x < img.cols; ++x) {
                const int c = lrow[x];
                orow[x] = (c >= 0 && c < K) ? cluster_color[c] : ramp[0];
            }
        }

        // ── ⑦ 編成 PNG（無損：這張圖要再被量化，JPEG 的塊狀雜訊會被當成真的邊界）──
        std::vector<unsigned char> png;
        if (!cv::imencode(".png", out, png) || png.empty()) {
            res.error = "風格化結果編碼失敗。";
            return res;
        }

        res.ok     = true;
        res.png    = std::move(png);
        res.width  = out.cols;
        res.height = out.rows;
    } catch (const cv::Exception& e) {
        BOOST_LOG_TRIVIAL(error) << "ping_photo_stylize OpenCV 例外：" << e.what();
        res.ok = false;
        res.error = "風格化過程發生錯誤，請重試或改用其他款式。";
        return res;
    } catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(error) << "ping_photo_stylize 例外：" << e.what();
        res.ok = false;
        res.error = "風格化過程發生錯誤，請重試或改用其他款式。";
        return res;
    }

    res.elapsed_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - t_begin).count();
    BOOST_LOG_TRIVIAL(info) << "PhotoTile 風格化完成：" << res.width << "x" << res.height
                            << "、K=" << K << (rank ? "、對映=rank" : "、對映=nearest") << "、候選=" << N
                            << "、" << res.elapsed_ms << " ms、" << res.png.size() << " bytes";
    return res;
}

} // namespace Slic3r
