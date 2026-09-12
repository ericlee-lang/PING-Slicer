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

// 一段的規格：這一段要**同時**擠出的料路 ＋ 連續幾圈。
// channels 只有 1 支＝純料；多支＝等比混合一起擠。
// 🔴 Eric 2026-09-10（牌 c-0910-WT-10）：四料改成「深色三支一起洗 2 圈 → 純白洗 4 圈」——
//    2/3/4 三支深色互相汙染不影響結果，分三段各洗一圈是白花料與時間；真正要洗乾淨的是最後那段白色，
//    所以把省下來的圈數全給白色（白 2→4 圈＝洗料量 2.2 倍，全塔總量只多 18%）。
struct StageSpec {
    std::vector<int> channels;   // 料路索引 0＝E0（第 1 路最淺／白）…3＝E3；quad 對應 M6052 的 A/B/C/D
    int              laps = 1;
};

struct Settings {
    bool                   enabled = false;
    std::string            mode;              // "dual" | "quad"
    std::vector<StageSpec> stages;            // **由內往外**：stages[0]＝最內圈那一段（最深），最後一段＝最外圈（純 E0 最淺）
                                              // 預設 dual {E1:1, E0:3}（E0 2→3＝Eric 0909 實印裁）；quad {E1+E2+E3:2, E0:4}（Eric 0910）
    float                  size_mm = 0.f;     // 0＝預設 25 mm 固定（Eric 2026-09-08；原式 44 × 口徑/0.4 已停用）
    float                  gap_mm  = 15.f;    // 塔與模型外緣距離
    float                  brim_mm = 8.f;     // 首層外擴 brim（用**最後一段**＝最淺那段的料，見 GCode.cpp）
    int                    stage_count() const { return (int) stages.size(); }
    int                    total_laps() const { int n = 0; for (const StageSpec& s : stages) n += s.laps; return n; }
};

// 一個材料段：由內往外連續幾圈同一配方（loops[0]＝最內圈）
struct Stage {
    std::string channel;      // 段標籤，只進 G-code 註解："E0"｜"E1+E2+E3"…
    std::string recipe_cmd;   // "M6051 S1" | "M6052 A100 B0 C0 D0" | "M6052 A0 B34 C33 D33" …
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
// 一段的配方指令：channels 單支＝純料、多支＝等比混合，餘數給**第一支**
//（例：quad {E1,E2,E3} → "M6052 A0 B34 C33 D33"＝Eric 2026-09-10 指定的比例）。
std::string recipe_for(const std::string& mode, const std::vector<int>& channels);
// 段標籤（"E0"｜"E1+E2+E3"），只進 G-code 註解
std::string stage_label(const std::vector<int>& channels);
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
