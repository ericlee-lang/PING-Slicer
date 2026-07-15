#ifndef slic3r_GUI_PingMixEditor_hpp_
#define slic3r_GUI_PingMixEditor_hpp_

// PING 混色曲線編輯器（原生 wxWidgets，照 web 藍圖 ping-color-mixer curveEditor.ts / quadEditor.ts 重建）
// - 雙料（FD 同進）：高度→E1 比例拖點曲線
// - 四料（FF 同進）：高度→四料堆疊比例帶
// 掛在「預覽」頁右側，僅同進機型顯示。編輯 → Plater::set_ping_mix_state()
// → AppConfig 持久化＋推進 BackgroundSlicingProcess＋GCodeViewer 重烘 per-layer 著色。

#include <wx/panel.h>
#include <wx/window.h>

#include "libslic3r/GCode/PingColorMix.hpp"
#include "Plater.hpp"
// PING(2026-07-09 Eric)：按鈕改用軟體標準 Button 元件（Widgets/Button 的 SetStyle
// Regular/Confirm＝全 app 統一的 hover/按壓/焦點/深色樣式），不再用原生 wxButton 硬塗色
#include "Widgets/Button.hpp"

class wxCheckBox;
class wxStaticText;

#include <functional>

namespace Slic3r {
namespace GUI {

class PingMixEditor;

// PING mix controls use one high-contrast tooltip treatment instead of mixing native light
// tooltips with the application's dark canvas tooltips (Eric 2026-07-15).
void bind_ping_dark_tooltip(wxWindow* target, const wxString& text);

// —— 自繪畫布（曲線／堆疊帶＋拖曳互動）——
class PingMixCanvas : public wxWindow
{
public:
    PingMixCanvas(PingMixEditor* editor, wxWindow* parent);

    // 拖曳中（update_from_plater 據此跳過狀態覆寫，避免切片完成事件插隊吃掉未 commit 的編輯）
    bool is_dragging() const { return m_dragging; }

private:
    void on_paint(wxPaintEvent& evt);
    void on_left_down(wxMouseEvent& evt);
    void on_motion(wxMouseEvent& evt);
    void on_left_up(wxMouseEvent& evt);
    void on_left_dclick(wxMouseEvent& evt);
    void on_capture_lost(wxMouseCaptureLostEvent& evt);
    void on_size(wxSizeEvent& evt);

    void render(wxDC& dc, const wxSize& size);
    void render_dual(wxDC& dc, const wxSize& size);
    void render_quad(wxDC& dc, const wxSize& size);

    // 雙料座標轉換（x=E1 比例(左=100%)、y=高度(下=0)）
    wxPoint dual_to_screen(double pos, double ratio, const wxRect& plot) const;
    // 四料：x=累積比例、y=高度
    wxPoint quad_to_screen(double pos, double cum, const wxRect& plot) const;
    wxRect  plot_rect(const wxSize& size) const;

    // 命中測試：回傳節點/分隔點 index，無命中回 -1
    int hit_dual_stop(const wxPoint& p, const wxRect& plot) const;
    int hit_quad_handle(const wxPoint& p, const wxRect& plot) const;        // 節點手柄（左側，調高度）
    bool hit_quad_divider(const wxPoint& p, const wxRect& plot, int& stop_idx, int& div_idx) const; // 分隔點（切蛋糕）

    PingMixEditor* m_editor;
    // 拖曳狀態
    int  m_drag_stop = -1;      // 進行中的節點 index（雙料節點／四料手柄）
    int  m_drag_div  = -1;      // 四料分隔點 index（0..2），-1=非分隔拖曳
    bool m_dragging  = false;
};

// —— 編輯器面板（模式/範本/色票列＋畫布）——
class PingMixEditor : public wxPanel
{
public:
    PingMixEditor(wxWindow* parent);

    // 依 Plater 目前狀態（機型/配方）重整 UI；同進機型回 true（呼叫端據此顯示/隱藏面板）
    bool update_from_plater();

    // 給畫布用
    bool is_quad() const { return m_is_quad; }
    Plater::PingMixState&       state()       { return m_state; }
    const Plater::PingMixState& state() const { return m_state; }
    PingMix::Recipe&       recipe()       { return m_is_quad ? m_state.quad : m_state.dual; }
    const PingMix::Recipe& recipe() const { return m_is_quad ? m_state.quad : m_state.dual; }

    // 拖曳中：只重畫畫布；放開/按鈕操作：commit 到 Plater（持久化＋BSP＋預覽重烘）
    void commit();
    void refresh_canvas();

    // 收合鈕按下時通知宿主（Preview）重排版面（收合狀態存 AppConfig ping_mix_editor_expanded）
    void set_toggle_callback(std::function<void()> cb) { m_toggle_cb = std::move(cb); }

private:
    void build_controls();
    void sync_controls();      // 依 m_state/m_is_quad 更新按鈕/勾選/色票外觀
    bool is_flat_tongjin() const;   // 曲線＝同進均分（雙 50/50、四 25×4）→ 隱藏模式列、亮「同進」
    void on_mode_clicked(int mode_idx);
    void on_template_clicked(int tpl_idx);
    void on_low_flow_toggled();
    void on_swatch_clicked(int idx);

    Plater::PingMixState m_state;
    bool m_is_quad = false;

    PingMixCanvas* m_canvas = nullptr;
    wxStaticText*  m_title  = nullptr;
    ::Button*      m_collapse_btn = nullptr;
    std::function<void()> m_toggle_cb;
    ::Button*      m_mode_btns[3] = { nullptr, nullptr, nullptr };   // 漸層/階梯/平滑
    ::Button*      m_tpl_btns[3]  = { nullptr, nullptr, nullptr };   // 同進/漸層(雙)or雙色(四)/彩虹(四)
    wxCheckBox*    m_low_flow     = nullptr;                          // 四料低流量進階（min_flow 0.10↔0.05）
    wxWindow*      m_swatches[4]  = { nullptr, nullptr, nullptr, nullptr }; // E1..E4 色票
    wxStaticText*  m_swatch_labels[4] = { nullptr, nullptr, nullptr, nullptr };
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_PingMixEditor_hpp_
