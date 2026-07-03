#include "PingColorMix.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cctype>

namespace Slic3r {
namespace PingMix {

static inline double clampd(double v, double lo, double hi) { return v < lo ? lo : (v > hi ? hi : v); }

// —— 雙料取樣：對應 gradient.ts sampleRatio + main.ts ratioAt 的 clamp —— //
double sample_ratio(const std::vector<Stop>& stops_in, double t, CurveMode mode)
{
    if (stops_in.empty()) return clampd(t, MIN_S, MAX_S);
    std::vector<Stop> s = stops_in;
    std::sort(s.begin(), s.end(), [](const Stop& a, const Stop& b) { return a.pos < b.pos; });
    double raw;
    if (t <= s.front().pos) {
        raw = s.front().ratio;
    } else if (t >= s.back().pos) {
        raw = s.back().ratio;
    } else {
        size_t i = 0;
        while (i < s.size() - 1 && t > s[i + 1].pos) ++i;
        const Stop& a = s[i];
        const Stop& b = s[i + 1];
        double span = (b.pos - a.pos) != 0.0 ? (b.pos - a.pos) : 1.0;
        double f = (t - a.pos) / span;
        if (mode == CurveMode::Step) {
            raw = a.ratio;
        } else if (mode == CurveMode::Smooth) {
            // Catmull-Rom（通過各控制點）
            double p0 = s[i >= 1 ? i - 1 : 0].ratio;
            double p1 = a.ratio;
            double p2 = b.ratio;
            double p3 = s[std::min(s.size() - 1, i + 2)].ratio;
            double f2 = f * f, f3 = f2 * f;
            raw = 0.5 * (2 * p1 + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f2 + (-p0 + 3 * p1 - 3 * p2 + p3) * f3);
        } else {
            raw = a.ratio + (b.ratio - a.ratio) * f; // Linear
        }
    }
    return clampd(raw, MIN_S, MAX_S);
}

// —— 四料：把任意四非負數修成合法配比（每料≥min、和=1），對應 quad.ts normalizeMix —— //
static void normalize_mix(const double in[4], double min_flow, double out[4])
{
    double raw[4];
    for (int i = 0; i < 4; ++i) raw[i] = (std::isfinite(in[i]) && in[i] > 0) ? in[i] : 0.0;
    double excess[4]; double ex_sum = 0;
    for (int i = 0; i < 4; ++i) { excess[i] = std::max(0.0, raw[i] - min_flow); ex_sum += excess[i]; }
    double free = 1.0 - 4.0 * min_flow;
    if (ex_sum <= 1e-9) { out[0] = out[1] = out[2] = out[3] = 0.25; return; }
    for (int i = 0; i < 4; ++i) out[i] = min_flow + (excess[i] / ex_sum) * free;
}

// 公開包裝（編輯器低流量切換時整條曲線重新正規化）
void normalize_quad_mix(const double in[4], double min_flow, double out[4])
{
    normalize_mix(in, min_flow, out);
}

// —— 四料取樣：對應 quad.ts sampleQuadMix —— //
void sample_quad_mix(const std::vector<QuadStop>& stops_in, double t, CurveMode mode,
                     double min_flow, double out_mix[4])
{
    if (stops_in.empty()) { out_mix[0] = out_mix[1] = out_mix[2] = out_mix[3] = 0.25; return; }
    std::vector<QuadStop> s = stops_in;
    std::sort(s.begin(), s.end(), [](const QuadStop& a, const QuadStop& b) { return a.pos < b.pos; });
    if (t <= s.front().pos) { for (int k = 0; k < 4; ++k) out_mix[k] = s.front().mix[k]; return; }
    if (t >= s.back().pos)  { for (int k = 0; k < 4; ++k) out_mix[k] = s.back().mix[k];  return; }
    size_t i = 0;
    while (i < s.size() - 1 && t > s[i + 1].pos) ++i;
    const QuadStop& a = s[i];
    const QuadStop& b = s[i + 1];
    double span = (b.pos - a.pos) != 0.0 ? (b.pos - a.pos) : 1.0;
    double f = (t - a.pos) / span;
    if (mode == CurveMode::Step) { for (int k = 0; k < 4; ++k) out_mix[k] = a.mix[k]; return; }
    if (mode == CurveMode::Smooth) {
        const QuadStop& sp0 = s[i >= 1 ? i - 1 : 0];
        const QuadStop& sp3 = s[std::min(s.size() - 1, i + 2)];
        double f2 = f * f, f3 = f2 * f, tmp[4];
        for (int k = 0; k < 4; ++k) {
            double v0 = sp0.mix[k], v1 = a.mix[k], v2 = b.mix[k], v3 = sp3.mix[k];
            tmp[k] = 0.5 * (2 * v1 + (-v0 + v2) * f + (2 * v0 - 5 * v1 + 4 * v2 - v3) * f2 + (-v0 + 3 * v1 - 3 * v2 + v3) * f3);
        }
        normalize_mix(tmp, min_flow, out_mix);
        return;
    }
    for (int k = 0; k < 4; ++k) out_mix[k] = a.mix[k] + (b.mix[k] - a.mix[k]) * f; // Linear
}

// —— 配比→整數百分比（和=100，最大餘數法）：對應 quad.ts mixToPercents —— //
void mix_to_percents(const double mix[4], int out_pct[4])
{
    double exact[4]; int fl[4]; int sum = 0;
    for (int i = 0; i < 4; ++i) { exact[i] = mix[i] * 100.0; fl[i] = (int)std::floor(exact[i]); sum += fl[i]; }
    int rest = 100 - sum;
    int order[4] = {0, 1, 2, 3};
    std::sort(order, order + 4, [&](int a, int b) { return (exact[b] - fl[b]) < (exact[a] - fl[a]); });
    for (int k = 0; k < 4 && rest > 0; ++k, --rest) fl[order[k]]++;
    for (int i = 0; i < 4; ++i) out_pct[i] = fl[i];
}

// —— 內部小工具 —— //
static inline bool is_word_char(char c) { return std::isalnum((unsigned char)c) || c == '_'; }

// 含 M6050/M6051/M6052（word boundary），對應 /M605[012]\b/
static bool has_mix_cmd(const std::string& s)
{
    size_t pos = 0;
    while ((pos = s.find("M605", pos)) != std::string::npos) {
        size_t d = pos + 4;
        if (d < s.size() && (s[d] == '0' || s[d] == '1' || s[d] == '2')) {
            size_t after = d + 1;
            if (after >= s.size() || !is_word_char(s[after])) return true;
        }
        pos += 4;
    }
    return false;
}

// 去頭尾空白（對應 JS trim）
static std::string trim(const std::string& s)
{
    size_t a = 0, b = s.size();
    while (a < b && std::isspace((unsigned char)s[a])) ++a;
    while (b > a && std::isspace((unsigned char)s[b - 1])) --b;
    return s.substr(a, b - a);
}

// 若 trimmed 以 ";Z:" 起頭，回傳其高度值到 z、成功回 true
static bool parse_z_marker(const std::string& trimmed, double& z)
{
    if (trimmed.compare(0, 3, ";Z:") != 0) return false;
    const char* p = trimmed.c_str() + 3;
    char* end = nullptr;
    double v = std::strtod(p, &end);
    if (end == p) return false;   // 沒解析到數字
    z = v;
    return true;
}

// —— 主插碼 —— //
int build_mixed_gcode(const std::string& gcode, const Recipe& recipe, std::string& out)
{
    // 切行（含 \r?\n）：以 '\n' 分割、去每行尾端 '\r'
    std::vector<std::string> lines;
    {
        size_t start = 0;
        while (true) {
            size_t nl = gcode.find('\n', start);
            std::string line = gcode.substr(start, nl == std::string::npos ? std::string::npos : nl - start);
            if (!line.empty() && line.back() == '\r') line.pop_back();
            lines.push_back(std::move(line));
            if (nl == std::string::npos) break;
            start = nl + 1;
        }
    }

    // Pass 1：找 ;Z: 的 min/max（做 z→t 正規化，同 web 預覽）
    bool have_z = false; double minZ = 0, maxZ = 0;
    for (const auto& raw : lines) {
        std::string t = trim(raw);
        double z;
        if (parse_z_marker(t, z)) {
            if (!have_z) { minZ = maxZ = z; have_z = true; }
            else { minZ = std::min(minZ, z); maxZ = std::max(maxZ, z); }
        }
    }
    double range = (maxZ - minZ) != 0.0 ? (maxZ - minZ) : 1.0;

    // 曲線空 → 不插、原樣回傳
    bool empty_recipe = (recipe.kind == MixKind::Dual && recipe.stops.empty())
                     || (recipe.kind == MixKind::Quad && recipe.qstops.empty());

    // Pass 2：剝既有 M605x、逐層插入、去重
    out.clear();
    out.reserve(gcode.size() + gcode.size() / 20);
    std::string last;
    int count = 0;
    bool in_body = false;                        // 第一個 ;Z: 之後才算列印本體
    for (size_t li = 0; li < lines.size(); ++li) {
        const std::string& raw = lines[li];
        std::string t = trim(raw);
        double z;
        const bool is_z = parse_z_marker(t, z);
        if (is_z) in_body = true;
        // 只剝「列印本體」的既有混色指令；start_gcode 預擠區（第一層之前）的同步指令
        //（FD 同進 M6050 S0.5 / FF 同進 M6052 A25 B25 C25 D25）必須保留 → 預擠才會兩/四邊同進。
        // 第 0 層起由逐層插入的 M6051/M6052 接管曲線。
        if (in_body && has_mix_cmd(t)) continue;
        if (li) out.push_back('\n');
        out += raw;
        if (empty_recipe || !have_z) continue;
        if (!is_z) continue;
        double tt = clampd((z - minZ) / range, 0.0, 1.0);
        char buf[64];
        std::string cmd;
        if (recipe.kind == MixKind::Quad) {
            double mix[4]; int pct[4];
            sample_quad_mix(recipe.qstops, tt, recipe.mode, recipe.min_flow, mix);
            mix_to_percents(mix, pct);
            std::snprintf(buf, sizeof(buf), "M6052 A%d B%d C%d D%d", pct[0], pct[1], pct[2], pct[3]);
            cmd = buf;
        } else {
            double s = sample_ratio(recipe.stops, tt, recipe.mode); // 已 clamp [MIN_S,MAX_S]
            std::snprintf(buf, sizeof(buf), "M6051 S%.4f", s);
            cmd = buf;
        }
        if (cmd != last) { out.push_back('\n'); out += cmd; last = cmd; ++count; }
    }
    return count;
}

// —— 預設配方 —— //
Recipe default_recipe(MixKind kind)
{
    Recipe r;
    r.kind = kind;
    r.mode = CurveMode::Linear;
    if (kind == MixKind::Quad)
        r.qstops = { {0.0, {0.25, 0.25, 0.25, 0.25}}, {1.0, {0.25, 0.25, 0.25, 0.25}} };
    else
        r.stops = { {0.0, 0.5}, {1.0, 0.5} };
    return r;
}

// —— 顏色（移植 web quad.ts mixRgb / curveEditor.ts lerpHex）—— //
static int hex_digit(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

void parse_hex_color(const std::string& hex, int out_rgb[3])
{
    out_rgb[0] = out_rgb[1] = out_rgb[2] = 136; // web fallback #888888
    size_t start = (!hex.empty() && hex[0] == '#') ? 1 : 0;
    size_t n = hex.size() - start;
    if (n == 3) { // #rgb → #rrggbb（三位全合法才回填，與 6 碼分支一致）
        int tmp[3];
        for (int i = 0; i < 3; ++i) {
            int d = hex_digit(hex[start + i]);
            if (d < 0) return;
            tmp[i] = d * 17;
        }
        out_rgb[0] = tmp[0]; out_rgb[1] = tmp[1]; out_rgb[2] = tmp[2];
    } else if (n >= 6) {
        int tmp[3];
        for (int i = 0; i < 3; ++i) {
            int hi = hex_digit(hex[start + 2 * i]);
            int lo = hex_digit(hex[start + 2 * i + 1]);
            if (hi < 0 || lo < 0) return;
            tmp[i] = hi * 16 + lo;
        }
        out_rgb[0] = tmp[0]; out_rgb[1] = tmp[1]; out_rgb[2] = tmp[2];
    }
}

void dual_color(double ratio_e1, const int c1[3], const int c2[3], int out_rgb[3])
{
    // web lerpHex(c2, c1, r)：逐通道 c2 + (c1-c2)*r、round 到整數
    for (int i = 0; i < 3; ++i) {
        double v = c2[i] + (c1[i] - c2[i]) * ratio_e1;
        out_rgb[i] = (int)std::lround(clampd(v, 0.0, 255.0));
    }
}

void quad_color(const double mix[4], const int colors[4][3], int out_rgb[3])
{
    // web mixRgb：gamma 純冪次 2.2（非分段 sRGB），linear 加權平均 → clamp → 轉回 sRGB
    double lin[3] = {0, 0, 0};
    for (int i = 0; i < 4; ++i)
        for (int c = 0; c < 3; ++c)
            lin[c] += mix[i] * std::pow(colors[i][c] / 255.0, 2.2);
    for (int c = 0; c < 3; ++c) {
        double srgb = std::pow(clampd(lin[c], 0.0, 1.0), 1.0 / 2.2);
        out_rgb[c] = (int)std::lround(clampd(srgb * 255.0, 0.0, 255.0));
    }
}

// —— 配方序列化 —— //
std::string recipe_to_string(const Recipe& recipe)
{
    char buf[128];
    std::string s = recipe.mode == CurveMode::Step ? "step" : (recipe.mode == CurveMode::Smooth ? "smooth" : "linear");
    s += ';';
    if (recipe.kind == MixKind::Quad) {
        // 四料要保留 min_flow（低流量 0.05／預設 0.10）——影響 Smooth normalize 與拖曳 clamp
        std::snprintf(buf, sizeof(buf), "mf=%.3f;", recipe.min_flow);
        s += buf;
    }
    if (recipe.kind == MixKind::Quad) {
        for (size_t i = 0; i < recipe.qstops.size(); ++i) {
            const QuadStop& q = recipe.qstops[i];
            std::snprintf(buf, sizeof(buf), "%s%.4f:%.4f|%.4f|%.4f|%.4f", i ? "," : "",
                          q.pos, q.mix[0], q.mix[1], q.mix[2], q.mix[3]);
            s += buf;
        }
    } else {
        for (size_t i = 0; i < recipe.stops.size(); ++i) {
            std::snprintf(buf, sizeof(buf), "%s%.4f:%.4f", i ? "," : "", recipe.stops[i].pos, recipe.stops[i].ratio);
            s += buf;
        }
    }
    return s;
}

bool recipe_from_string(const std::string& s, Recipe& recipe)
{
    size_t semi = s.find(';');
    if (semi == std::string::npos) return false;
    std::string mode_s = s.substr(0, semi);
    CurveMode mode;
    if (mode_s == "linear") mode = CurveMode::Linear;
    else if (mode_s == "step") mode = CurveMode::Step;
    else if (mode_s == "smooth") mode = CurveMode::Smooth;
    else return false;

    std::vector<Stop> stops;
    std::vector<QuadStop> qstops;
    size_t pos = semi + 1;

    // 選配欄位 mf=<min_flow>;（四料低流量持久化；舊格式沒有此欄位＝沿用預設）
    double min_flow = recipe.min_flow;
    if (s.compare(pos, 3, "mf=") == 0) {
        size_t semi2 = s.find(';', pos);
        if (semi2 == std::string::npos) return false;
        char* end = nullptr;
        const double v = std::strtod(s.c_str() + pos + 3, &end);
        if (end == s.c_str() + pos + 3) return false;
        if (v > 0.0 && v <= 0.25) min_flow = v;
        pos = semi2 + 1;
    }

    while (pos < s.size()) {
        size_t comma = s.find(',', pos);
        std::string tok = s.substr(pos, comma == std::string::npos ? std::string::npos : comma - pos);
        size_t colon = tok.find(':');
        if (colon == std::string::npos) return false;
        char* end = nullptr;
        double p = std::strtod(tok.c_str(), &end);
        if (end != tok.c_str() + colon) return false;
        std::string vals = tok.substr(colon + 1);
        if (recipe.kind == MixKind::Quad) {
            QuadStop q; q.pos = p;
            const char* vp = vals.c_str();
            for (int i = 0; i < 4; ++i) {
                q.mix[i] = std::strtod(vp, &end);
                if (end == vp) return false;
                vp = end;
                if (i < 3) { if (*vp != '|') return false; ++vp; }
            }
            qstops.push_back(q);
        } else {
            Stop st; st.pos = p;
            st.ratio = std::strtod(vals.c_str(), &end);
            if (end == vals.c_str()) return false;
            stops.push_back(st);
        }
        if (comma == std::string::npos) break;
        pos = comma + 1;
    }
    // 值域消毒（AppConfig 可能被手改/損壞；正常編輯器路徑本來就恆合法）
    if (recipe.kind == MixKind::Quad) {
        if (qstops.size() < 2) return false;
        for (QuadStop& q : qstops) {
            q.pos = clampd(q.pos, 0.0, 1.0);
            double fixed[4];
            normalize_mix(q.mix, min_flow, fixed);   // 保證每料 ≥ min_flow、和=1
            for (int k = 0; k < 4; ++k) q.mix[k] = fixed[k];
        }
        recipe.qstops = std::move(qstops);
        recipe.min_flow = min_flow;
    } else {
        if (stops.size() < 2) return false;
        for (Stop& st : stops) {
            st.pos = clampd(st.pos, 0.0, 1.0);
            st.ratio = clampd(st.ratio, MIN_S, MAX_S);
        }
        recipe.stops = std::move(stops);
    }
    recipe.mode = mode;
    return true;
}

} // namespace PingMix
} // namespace Slic3r
