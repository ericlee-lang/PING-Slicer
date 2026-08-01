// 照片磚機器能力判定——單一來源實作。規格見 PhotoTileCapability.hpp 檔頭。

#include "PhotoTileCapability.hpp"

#include "GUI_App.hpp"
#include "libslic3r/Preset.hpp"
#include "libslic3r/PresetBundle.hpp"

namespace Slic3r { namespace GUI {

namespace {
// 全庫既有慣例：機型名帶「同進照片磚」。改判準＝改這一行，不要散在各處。
const char* PHOTO_TILE_MARKER = "同進照片磚";
} // namespace

PhotoTileCapability photo_tile_capability_of(const Preset& preset)
{
    PhotoTileCapability cap;
    const ConfigOptionString* pm = preset.config.option<ConfigOptionString>("printer_model");
    if (pm == nullptr || pm->value.find(PHOTO_TILE_MARKER) == std::string::npos)
        return cap;

    cap.is_photo_tile = true;
    cap.preset_name   = preset.name;
    // FD＝雙料同進（M6051）／FF＝四料同進（M6052）。判家族用機型名開頭，與自動選機同準。
    if (pm->value.rfind("FD", 0) == 0)      { cap.family = "FD"; cap.mode = "dual"; }
    else if (pm->value.rfind("FF", 0) == 0) { cap.family = "FF"; cap.mode = "quad"; }

    // effective nozzle：以機器實際噴嘴為準（C-0 §1：生成不再讀面板選的口徑）。
    if (const auto* nd = preset.config.option<ConfigOptionFloats>("nozzle_diameter"))
        if (!nd->values.empty())
            cap.nozzle_mm = nd->values.front();
    // 後備：某些 preset 只有 printer_variant（字串口徑）時仍給得出值
    if (cap.nozzle_mm <= 0.0)
        if (const auto* pv = preset.config.option<ConfigOptionString>("printer_variant"))
            try { cap.nozzle_mm = std::stod(pv->value); } catch (...) {}
    return cap;
}

PhotoTileCapability photo_tile_capability_of_selected_printer()
{
    PresetBundle* bundle = wxGetApp().preset_bundle;
    if (bundle == nullptr)
        return PhotoTileCapability();
    return photo_tile_capability_of(bundle->printers.get_edited_preset());
}

bool current_printer_is_photo_tile()
{
    return photo_tile_capability_of_selected_printer().is_photo_tile;
}

}} // namespace Slic3r::GUI
