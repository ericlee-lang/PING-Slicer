#ifndef slic3r_GCode_PingCycleTower_hpp_
#define slic3r_GCode_PingCycleTower_hpp_

// PING 照片磚「每層循環洗料塔」（WT 線，2026-09-08；計畫正本＝設計提案/照片磚循環洗料塔_20260908_01a07fef/CLAUDE_PLAN.md）
//
// 一份資料驅動三件事：塔路徑（真實 offset 圈）、寫出順序（塔段配方由深到淺→離塔→模型段由淺到深）、用料／時間統計
// （擠出走 GCode::extrude_path ⇒ 預覽與統計吃的就是這批 G1）。離線對照答案＝照片磚_循環洗料塔/cycle_core.py（fixture 12/12）。
//
// 料路 ID：E0＝第 1 路最淺（雙料 M6051 S1／四料 A100）；塔內順序**由內往外**＝E(n-1)…E0；換料只在圈界。
// ⇒ 最深的那一路在最內圈、最淺的 E0 在最外圈（Eric 2026-09-09），塔的外皮與 brim 統一是最淺色、垂直方向無色變。
// 純 E0 判定看**配方權重**（雙料 S==1；四料 A==100 其餘 0），不看預覽色。
//
// 設定載體＝PrintObjectConfig 的 ping_pt_cycle*（工作室寫進 3MF 物件層 metadata；未開＝本檔完全不介入，行為與舊版逐位相同）。

#include <map>
#include <string>
#include <vector>
#include <memory>
#include "../libslic3r.h"
#include "../Polygon.hpp"
#include "../Polyline.hpp"
#include "../Point.hpp"

namespace Slic3r {

class Print;
class PrintObject;
class Model;

namespace PingCycle {

struct Settings {
    bool                enabled   = false;
    std::string         mode;                 // "dual" | "quad"
    std::vector<int>    laps;                 // 由外往內每段圈數：dual {1,3}＝E1,E0（E0 2→3＝Eric 0909 實印裁）；quad {1,1,1,2}＝E3,E2,E1,E0（Eric 0908 第 4 階段裁；原 2,4／2,2,2,4）
    float               size_mm   = 0.f;      // 0＝預設 25 mm 固定（Eric 2026-09-08；原式 44 × 口徑/0.4 已停用）
    float               gap_mm    = 15.f;     // 塔與模型外緣距離
    float               brim_mm   = 8.f;      // 首層外擴 brim（用第一段的料）
    int                 channels() const { return (int) laps.size(); }
    int                 total_laps() const { int n = 0; for (int l : laps) n += l; return n; }
};

// 一個材料段：由內往外連續幾圈同一純料配方（loops[0]＝最內圈）
struct Stage {
    std::string channel;      // "E3"…"E0"
    std::string recipe_cmd;   // "M6051 S1" | "M6052 A100 B0 C0 D0" …
    int         first_lap = 0, last_lap = 0;   // 1-based
};

// 某個層高下的整塔幾何（圈的中心線，已含塔位置、scaled 座標）
struct LayerGeometry {
    float                 layer_height = 0.f;
    float                 width        = 0.f;   // 線寬
    float                 spacing      = 0.f;   // 線道間距（Flow）
    double                mm3_per_mm   = 0.;
    std::vector<Polyline> loops;                // **由內往外**，每圈閉合（首尾同點），從接縫起
    std::vector<Polyline> brim_loops;           // 首層用：由內往外的外擴圈（接在**最後一段＝最淺**之後）
    std::string           problem;              // 非空＝幾何不合法（分裂／消失／空腔封閉）
};

// 從 Print 讀設定、palette、幾何位置；不合法回 nullptr 並在 why 說明
std::unique_ptr<class Tower> create(const Print& print, std::string& why);

// 純料配方命令（給 ToolOrdering／GCode 共用）
const char* pure_recipe(const std::string& mode, const std::string& channel);
bool        is_pure_light_recipe(const std::string& cmd);   // 雙料 S==1；四料 A==100 其餘 0
// 配方的「亮度分數」0..1（1＝最淺、0＝最深）。Eric 2026-09-09 裁「丙」：
//   雙料＝S（E0 佔比）；四料＝(A×3 + B×2 + C×1 + D×0) / 300
// ＝把塔自己就在用的「E0 最淺、E3 最深」假設一路用到混合配方上，不必另取線材色。
// 解析不出來回 -1（呼叫端據此維持原生順序，不要當成最深）。
double      light_score(const std::string& cmd);

// 讀某台 print 是否任何物件開了循環塔（ToolOrdering 用）
bool enabled_for(const Print& print);
// 從模型零件名收 palette（tool→配方命令），照片磚不合法回 false（與 GUI 端 collect 同一支判定）
bool collect_palette(const Model& model, std::map<int, std::string>& palette, std::string& reason);

class Tower {
public:
    const Settings&                      settings() const { return m_settings; }
    const std::vector<Stage>&            stages()   const { return m_stages; }
    const std::map<int, std::string>&    palette()  const { return m_palette; }
    // 純 E0 的虛擬槽（0-based）
    const std::vector<unsigned int>&     pure_light_tools() const { return m_pure_light_tools; }
    float                                nozzle_mm() const { return m_nozzle; }
    float                                size_mm()   const { return m_size; }
    Point                                center()    const { return m_center; }   // scaled
    // 該層高的幾何（快取）；problem 非空＝這層不能做塔
    const LayerGeometry&                 geometry_for(float layer_height, bool first_layer);
    // 離線報表用：塔外輪廓（scaled，已含位置）
    const Polygon&                       outline() const { return m_outline; }

    Tower(Settings s, std::map<int, std::string> palette, float nozzle, Point center, float size, float bed_check_note_ignored);

private:
    Settings                        m_settings;
    std::vector<Stage>              m_stages;
    std::map<int, std::string>      m_palette;
    std::vector<unsigned int>       m_pure_light_tools;
    float                           m_nozzle = 0.4f;
    float                           m_size   = 44.f;
    Point                           m_center;
    Polygon                         m_outline;      // scaled，已平移到 m_center
    std::map<int, LayerGeometry>    m_cache;        // key = round(layer_height*1000)
    void build_outline();
};

} // namespace PingCycle
} // namespace Slic3r

#endif // slic3r_GCode_PingCycleTower_hpp_
