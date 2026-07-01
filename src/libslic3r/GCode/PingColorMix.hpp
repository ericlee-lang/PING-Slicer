#ifndef slic3r_GCode_PingColorMix_hpp_
#define slic3r_GCode_PingColorMix_hpp_

// PING 混色漸層——核心插碼（原生移植自 web 版 mixer.ts / gradient.ts / quad.ts，已驗證邏輯）。
// 對切好的 G-code 逐層插入混色指令：
//   雙料（FD 同進）→ M6051 S<比例>            （2 料混一噴頭）
//   四料（FF 同進）→ M6052 A<> B<> C<> D<>   （4 料混一噴頭，整數百分比、和=100）
// 掃 `;Z:<height>` 層標記、剝掉既有 M6050/M6051/M6052（含 start_gcode 的 M6050 S0.5）、
// 依「混色配方」曲線算該層比例、去重（比例沒變不重下）。
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

// —— 主插碼 ——
// 對 gcode 逐層插入混色指令；z→t 用 gcode 內 ;Z: 的 min/max 正規化（同 web 預覽）。
// 回傳插入的指令數；結果寫入 out。gcode 無 ;Z: 或曲線空 → 原樣回傳、count=0。
int build_mixed_gcode(const std::string& gcode, const Recipe& recipe, std::string& out);

} // namespace PingMix
} // namespace Slic3r

#endif // slic3r_GCode_PingColorMix_hpp_
