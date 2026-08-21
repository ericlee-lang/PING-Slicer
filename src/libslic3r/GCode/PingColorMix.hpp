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
#include <map>
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

// 照片磚 3MF 匯入時的純資料描述。tool 是 0-based（T0, T1...）。
struct PhotoPartAssignment {
    int         tool = -1;
    std::string name;
};

enum class PhotoPaletteStatus {
    NotPhotoTile, // 沒有任何可辨識的照片磚配方，普通專案不動
    Valid,        // 所有列印零件都有配方，且槽號從 T0 連續排列
    Invalid       // 僅部分零件有配方，或槽號／配方衝突
};

struct PhotoPalette {
    std::map<int, std::string> recipes; // tool -> M6051/M6052
    std::vector<std::string>   colors;  // tool -> #RRGGBB；舊檔無顏色資料時留空
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
// dual_cmd＝雙料指令字：Klipper 現行機 M6051（預設）；Classic 前代 DUAL（Marlin 韌體）
// 只認 M6050 舊格式（Eric 2026-07-26 裁「用舊的方法安插」），由呼叫端依機型傳入。
// 兩者同為 S 單參數同構；剝除規則（has_mix_cmd）涵蓋 M6050/1/2＝重匯出不會雙插。
int build_mixed_gcode(const std::string& gcode, const Recipe& recipe, std::string& out,
                      const char* dual_cmd = "M6051");

// —— 預設配方（＝web 範本「同進」：行為等同韌體原生 50/50、四色 25×4）——
Recipe default_recipe(MixKind kind);

// —— 顏色（預覽著色用，移植自 web quad.ts mixRgb / curveEditor.ts lerpHex）——
// 解析 "#rrggbb"（容忍 "#rgb" 縮寫）→ rgb 各 0~255；失敗回中灰 136（web fallback #888888）
void parse_hex_color(const std::string& hex, int out_rgb[3]);
// 雙料：sRGB 空間逐通道線性內插（web lerpHex(c2, c1, ratio)：混合色 = c2 + (c1-c2)*ratioE1）
void dual_color(double ratio_e1, const int c1[3], const int c2[3], int out_rgb[3]);
// 四料：linear 空間（gamma 純冪次 2.2）加權平均後轉回 sRGB（web mixRgb）
void quad_color(const double mix[4], const int colors[4][3], int out_rgb[3]);

// —— 照片磚（多零件 3MF 的 T→M605x 後處理）——
// 原型輸出的 3MF 每個零件名稱自帶配比（配比隨模型走，重存/複製不掉）：
//   四料 "零件色3 A70 B30 C0 D0" → 指令 "M6052 A70 B30 C0 D0"（整數、和=100）
//   雙料 "零件色3 S0.72"          → 指令 "M6051 S0.72"（0~1）
// 只認「名稱尾端」的 pattern（前面至少要有一個名稱 token）；數字 token 逐字沿用
// （不重新格式化浮點）。四料驗和=100（±0.5 容差）。不是配比名稱 → 回 false。
bool parse_photo_part_name(const std::string& name, std::string& out_cmd);

// 新版照片磚名稱可在配方前攜帶預覽色：
//   "零件色3 #7F7F7F S0.5" / "零件色3 #C07055 A70 B30 C0 D0"
// 嵌入色優先；舊雙料檔無嵌入色時，提供 S0=黑、S1=白的中性灰階診斷色。
// 四料舊檔無法從配比反推實際原料色，因此回 false。
bool parse_photo_part_color(const std::string& name, std::string& out_color);

// 全有全無的指派完整性檢查，供匯入 UI 與 G-code 後處理共用。
// Invalid 時 reason 為可記錄／顯示的英文原因；NotPhotoTile 不顯示警告。
PhotoPaletteStatus collect_photo_palette(const std::vector<PhotoPartAssignment>& parts,
                                         PhotoPalette& out,
                                         std::string& reason);

// palette：0-based 工具號（＝零件 extruder-1，見 3MF part metadata extruder）→ 混色指令。
// 掃 gcode，把「整行 T<n>」（n 在 palette 內）換成對應 M605x（原 T 號留在行尾註解供追溯）；
// 其他一律不動——含 M104/M107 等「帶 T 參數」的行、palette 外的 T（如手測 T5）、
// start 預擠區的 M6050/M6052 同步指令。輸出天然冪等（換過的行不再是 T 開頭）。
// 回傳替換數；palette 空 → 原樣回傳、count=0。
int build_photo_tile_gcode(const std::string& gcode,
                           const std::map<int, std::string>& palette,
                           std::string& out);

// —— 配方序列化（AppConfig 持久化用；純文字緊湊格式，非 JSON）——
// 雙料 "linear;0:0.5,1:0.5"、四料 "smooth;0:0.25|0.25|0.25|0.25,..."（分號前=mode）
std::string recipe_to_string(const Recipe& recipe);
// 失敗（格式壞）回 false、recipe 不動；kind 由呼叫端先設好（決定解析 stops 或 qstops）
bool recipe_from_string(const std::string& s, Recipe& recipe);

// —— 機型判準（GUI 與 worker 共用同一把尺；純字串比對、無 Orca 依賴）——
// 照片磚機（FD300／FF600／FF800 同進照片磚）本身就帶整套逐零件配方（T→M605x，見
// build_photo_tile_gcode），跟「隨高度變化的混色曲線」是兩套互斥的東西。
// Eric 2026-08-22 令「照片磚的混色功能拿掉，因為它本身就有特殊的配置」。
// 字串判準沿用既有先例（GUI_App.cpp 照片磚自動選機也是認 printer_model 含「同進照片磚」）。
// ⚠ 同字串另住 GUI_App.cpp 的 ping_resolve_photo_tile_printer()——判準要改就兩處一起改。
//   （開發線已把這類判定收斂成 PhotoTileCapability 模組；出貨線沒有那支，故落在這裡。）
inline bool is_photo_tile_printer(const std::string& printer_model)
{
    return printer_model.find("同進照片磚") != std::string::npos;
}

// 混色曲線適用的機型＝同進、且不是照片磚機。
// ⚠ GUI 藏鈕不等於功能關掉：worker 端也要用這把尺，否則在照片磚機上開一個「非照片磚」模型
//    （沒有零件配方＝走原混色路徑）時，看不見的 AppConfig 開關仍會讓曲線插進 G-code。
inline bool printer_supports_color_mix(const std::string& printer_model)
{
    return printer_model.find("同進") != std::string::npos && !is_photo_tile_printer(printer_model);
}

} // namespace PingMix
} // namespace Slic3r

#endif // slic3r_GCode_PingColorMix_hpp_
