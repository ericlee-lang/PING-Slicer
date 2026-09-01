#include "StepPreflight.hpp"

#include <boost/filesystem/path.hpp>
#include <boost/format.hpp>
#include <boost/log/trivial.hpp>

#include "GUI_App.hpp"
#include "I18N.hpp"
#include "Plater.hpp"
#include "NotificationManager.hpp"
#include "StepMeshDialog.hpp"
#include "libslic3r/AppConfig.hpp"
#include "libslic3r/LocalesUtils.hpp"

namespace Slic3r { namespace GUI {

int step_import_gate(Slic3r::Step&        file,
                     const std::string&   path,
                     double&              linear_value,
                     double&              angle_value,
                     bool&                is_split,
                     StepPreflightResult& out)
{
    AppConfig* config = wxGetApp().app_config;

    double linear = string_to_double_decimal_point(config->get("linear_defletion"));
    if (linear <= 0) linear = 0.003;
    double angle = string_to_double_decimal_point(config->get("angle_defletion"));
    if (angle <= 0) angle = 0.5;
    const bool split_default = config->get_bool("is_split_compound");

    // 只走形狀樹計數，不做幾何運算 —— 放在網格化之前就是為了讓破圖檔不必先白跑一趟。
    const StepBRepCensus census = file.inspect_brep();

    if (census.has_no_solid()) {
        // 累計而非覆蓋：這一批的第一個破圖檔才是通知條要講的那個。
        if (out.no_solid_count == 0)
            out.file_name = boost::filesystem::path(path).filename().string();
        ++out.no_solid_count;
    }

    if (!config->get_bool("enable_step_mesh_setting")) {
        // 使用者關掉了匯入參數對話框。前哨不因此把它叫回來（那等於推翻他的選擇），
        // 改成匯入完成後用通知條講。
        linear_value = linear;
        angle_value  = angle;
        is_split     = split_default;
        out.warn_after_import = out.warn_after_import || census.has_no_solid();
        return 1;
    }

    StepMeshDialog mesh_dlg(nullptr, file, linear, angle, census);
    const int modal_result = mesh_dlg.ShowModal();

    if (mesh_dlg.repair_requested()) {
        // Eric 2026-08-24 裁 ①：取消這次匯入。
        // 修補完會另存新檔、要重新匯入一次，先匯進來的那顆等一下就得刪掉。
        out.repair_requested = true;
        return -1;
    }
    if (modal_result != wxID_OK)
        return -1;

    linear_value = mesh_dlg.get_linear_defletion();
    angle_value  = mesh_dlg.get_angle_defletion();
    is_split     = mesh_dlg.get_split_compound_value();
    return 1;
}

void step_preflight_followup(const StepPreflightResult& out)
{
    if (!out.repair_requested && !out.warn_after_import)
        return;

    Plater* plater = wxGetApp().plater();
    if (plater == nullptr || plater->get_notification_manager() == nullptr)
        return;
    NotificationManager* notify = plater->get_notification_manager();

    // 連續匯入好幾顆的時候不要疊一排；永遠只留最新的那一則。
    notify->close_notification_of_type(NotificationType::PINGStepNoSolid);

    if (out.repair_requested) {
        // 平台 guard 擋掉時它會自己說明原因並回 false —— 這時不要再接一句「請拖檔進去」。
        if (!wxGetApp().open_step_repair())
            return;

        /* Eric 2026-08-24 裁 ②：要顯示檔名。
           🔴 但**不是**顯示在修補頁上。那個頁面是 VibeCAD 的固定 release：
              它不讀任何 query param（實查 index.html 與 bundle 都沒有 location.search／URLSearchParams），
              而且契約 §4／§7 明訂固定 release 不可原地改、ORCA 只是薄宿主。
              要讓頁面自己講檔名，就得新增 host→page 命令 ⇒ protocolVersion 升 2 ⇒ 得等 1.1.0。
           ⇒ 檔名改由 ORCA 自己這一側的通知條講。使用者要的資訊拿到了，
              vendored 目錄一個位元組都沒動。 */
        notify->push_notification(
            NotificationType::PINGStepNoSolid,
            NotificationManager::NotificationLevel::ImportantNotificationLevel,
            (boost::format(_u8L("Drag this file into the defect check tool: %1%")) % out.file_name).str());
        return;
    }

    // out.warn_after_import：匯入已經照常完成，這裡純粹是告知。
    const std::string subject = out.no_solid_count > 1
        ? (boost::format(_u8L("%1% and %2% other files")) % out.file_name % (out.no_solid_count - 1)).str()
        : out.file_name;
    notify->push_notification(
        NotificationType::PINGStepNoSolid,
        NotificationManager::NotificationLevel::WarningNotificationLevel,
        (boost::format(_u8L("%1% has no solid body; the sliced result may not be what you expect.")) % subject).str(),
        _u8L("Open STEP defect check"),
        [](wxEvtHandler*) {
            wxGetApp().open_step_repair();
            return true;
        });
}

}} // namespace Slic3r::GUI
