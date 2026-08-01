#ifndef slic3r_GUI_PhotoTileCapability_hpp_
#define slic3r_GUI_PhotoTileCapability_hpp_

// =====================================================================
// 照片磚「機器能力判定」單一來源（C-1，2026-08-01・照片磚線 PT）
//
// 為什麼要收斂成一支：現況是各處自己用機型名字串判（自動選機 resolver 在
// GUI_App.cpp、後處理閘門在 BackgroundSlicingProcess.cpp、拖放在 Plater.cpp），
// 判準一旦漂移就會出現「這裡認得、那裡不認得」的鬼故事。Codex C 案審查 #15
// 明確要求收斂成 **單一 capability predicate**，供拖放／側卡／生成共用。
//
// 判準（沿用全庫既有慣例，不改 preset schema——那會動到整包 bundle，超出最小改）：
//   printer_model 含「同進照片磚」；FD 開頭＝dual（雙料 M6051）、FF 開頭＝quad（四料 M6052）
//   口徑一律讀 **effective nozzle_diameter**（機器實際噴嘴），不是面板選的值。
// preset 欄位化（phototile_mode）列為後續硬化項，不擋 C 案。
// =====================================================================

#include <string>

namespace Slic3r {
class Preset;
namespace GUI {

struct PhotoTileCapability
{
    bool        is_photo_tile = false;   // 這台機是不是照片磚機
    std::string mode;                    // "dual"｜"quad"（非照片磚機＝空）
    double      nozzle_mm  = 0.0;        // effective nozzle（讀 nozzle_diameter[0]）
    std::string preset_name;             // 判定所依據的 preset 名（診斷用）
    std::string family;                  // "FD"／"FF"（診斷用）
};

// 單一判定：任一 preset
PhotoTileCapability photo_tile_capability_of(const Preset& preset);
// 單一判定：目前選中的機器（拖放／側卡／生成三處都該問這個）
PhotoTileCapability photo_tile_capability_of_selected_printer();
// 便利型（等價於 photo_tile_capability_of_selected_printer().is_photo_tile）
bool current_printer_is_photo_tile();

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_PhotoTileCapability_hpp_
