#ifndef slic3r_GCode_PingColorMix_hpp_
#define slic3r_GCode_PingColorMix_hpp_

// PING 混色漸層——核心插碼（原生移植自 web 版 mixer.ts / gradient.ts / quad.ts，已驗證邏輯）。
// 對切好的 G-code 逐層插入混色指令：
//   雙料（FD 同進）→ M6051 S<比例>            （2 料混一噴頭）
//   四料（FF 同進）→ M6052 A<> B<> C<> D<>   （4 料混一噴頭，整數百分比、和=100）
// 掃 `;Z:<height>` 層標記，於第一層起逐層插混色指令；剝掉「列印本體」既有 M6050/M6051/M6052、
// 但保留第一層之前（start_gcode 預擠區）的同步指令（FD M6050 S0.5 / FF M6052 A25 B25 C25 D25）
// 讓預擠兩/四邊同進；依「混色配方」曲線算該層比例、去重（比例沒變不重下）。
// 本檔零 Orca 依賴（純 std::），可獨立 g++ 編譯驗證。
#include <string>
#include <vector>

namespace Slic3r {
namespace PingMix {

// 曲線插值模式（對應 web 三種）
enum class CurveMode { Linear, Step, Smooth };

// 混色種類：雙料=M6051、四料=M6052
enum class MixKind { Dual, Quad };

// 雙料控制點：pos=高度位置(0 底~1 頂)、ratio=E1 佔比
struct Stop { double pos; double ratio; };

// 四料控制點：pos=高度位置、mix[4]=E1..E4 佔比（和=1）
struct QuadStop { double pos; double mix[4]; };

// 混色比例安全範圍（雙料）：不可純色，兩料各留 5% 持續滲出防堵頭
constexpr double MIN_S = 0.05;
constexpr double MAX_S = 0.95;

struct Recipe {
    MixKind               kind     = MixKind::Dual;
    CurveMode             mode     = CurveMode::Linear;
    std::vector<Stop>     stops;              // 雙料曲線
    std::vector<QuadStop> qstops;             // 四料曲線
    double                min_flow = 0.10;    // 四料每料下限（進階模式 0.05）
};

// —— 取樣（公開以便預覽著色/測試共用）——
// 雙料：位置 t(0~1) → E1 比例（已 clamp 到 [MIN_S, MAX_S]）
double sample_ratio(const std::vector<Stop>& stops, double t, CurveMode mode);
// 四料：位置 t(0~1) → 四料配比（和=1、每料≥min_flow）
void   sample_quad_mix(const std::vector<QuadStop>& stops, double t, CurveMode mode,
                       double min_flow, double out_mix[4]);
// 四料配比 → 整數百分比（和=100，最大餘數法）
void   mix_to_percents(const double mix[4], int out_pct[4]);
// 四料：把任意四非負數修成合法配比（每料≥min_flow、和=1）——編輯器低流量收緊時用
void   normalize_quad_mix(const double in[4], double min_flow, double out[4]);

// —— 主插碼 ——
// 對 gcode 逐層插入混色指令；z→t 用 gcode 內 ;Z: 的 min/max 正規化（同 web 預覽）。
// 回傳插入的指令數；結果寫入 out。gcode 無 ;Z: 或曲線空 → 原樣回傳、count=0。
int build_mixed_gcode(const std::string& gcode, const Recipe& recipe, std::string& out);

// —— 預設配方（＝web 範本「同進」：行為等同韌體原生 50/50、四色 25×4）——
Recipe default_recipe(MixKind kind);

// —— 顏色（預覽著色用，移植自 web quad.ts mixRgb / curveEditor.ts lerpHex）——
// 解析 "#rrggbb"（容忍 "#rgb" 縮寫）→ rgb 各 0~255；失敗回中灰 136（web fallback #888888）
void parse_hex_color(const std::string& hex, int out_rgb[3]);
// 雙料：sRGB 空間逐通道線性內插（web lerpHex(c2, c1, ratio)：混合色 = c2 + (c1-c2)*ratioE1）
void dual_color(double ratio_e1, const int c1[3], const int c2[3], int out_rgb[3]);
// 四料：linear 空間（gamma 純冪次 2.2）加權平均後轉回 sRGB（web mixRgb）
void quad_color(const double mix[4], const int colors[4][3], int out_rgb[3]);

// —— 配方序列化（AppConfig 持久化用；純文字緊湊格式，非 JSON）——
// 雙料 "linear;0:0.5,1:0.5"、四料 "smooth;0:0.25|0.25|0.25|0.25,..."（分號前=mode）
std::string recipe_to_string(const Recipe& recipe);
// 失敗（格式壞）回 false、recipe 不動；kind 由呼叫端先設好（決定解析 stops 或 qstops）
bool recipe_from_string(const std::string& s, Recipe& recipe);

} // namespace PingMix
} // namespace Slic3r

#endif // slic3r_GCode_PingColorMix_hpp_
