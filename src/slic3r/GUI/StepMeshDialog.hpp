#ifndef _STEP_MESH_DIALOG_H_
#define _STEP_MESH_DIALOG_H_

#include <thread>
#include "GUI_App.hpp"
#include "GUI_Utils.hpp"
#include "libslic3r/Format/STEP.hpp"
#include "Widgets/Button.hpp"
class Button;

class StepMeshDialog : public Slic3r::GUI::DPIDialog
{
public:
    /* 【2026-08-24・牌 c-0824-VIBE-02】census 帶預設值＝fail-open：
       任何沒經過前哨閘門、直接 new 這個對話框的路徑，行為與改動前完全相同（不顯示警示帶）。 */
    StepMeshDialog(wxWindow* parent, Slic3r::Step& file, double linear_init, double angle_init,
                   const Slic3r::StepBRepCensus& census = Slic3r::StepBRepCensus{});
    ~StepMeshDialog() override;
    // 使用者按了「開啟 STEP 修補工具」。對話框以 wxID_CANCEL 收掉（Eric 2026-08-24 裁：取消這次匯入）。
    inline bool repair_requested() const { return m_repair_requested; }
    void on_dpi_changed(const wxRect& suggested_rect) override;
    inline double get_linear_defletion() {
        double value;
        if (m_linear_last.ToDouble(&value)) {
            return value;
        }else {
            return m_last_linear;
        }
    }
    inline double get_angle_defletion() {
        double value;
        if (m_angle_last.ToDouble(&value)) {
            return value;
        } else {
            return m_last_angle;
        }
    }
    inline bool get_split_compound_value() {
        return m_split_compound_checkbox->GetValue();
    }
private:
    Slic3r::Step& m_file;
    bool m_repair_requested = false;
    wxCheckBox* m_checkbox = nullptr;
    wxCheckBox* m_split_compound_checkbox = nullptr;
    wxString m_linear_last;
    wxString m_angle_last;
    wxStaticText* mesh_face_number_text;
    double m_last_linear = 0.003;
    double m_last_angle = 0.5;
    unsigned int m_mesh_number = 0;
    boost::thread* m_task {nullptr};
    bool validate_number_range(const wxString& value, double min, double max);
    void update_mesh_number_text();
    void on_task_done(wxCommandEvent& event);
    void stop_task();
};

#endif  // _STEP_MESH_DIALOG_H_