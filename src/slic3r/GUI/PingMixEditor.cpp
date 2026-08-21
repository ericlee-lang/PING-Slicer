// PING 混色曲線編輯器實作（照 web 藍圖 curveEditor.ts / quadEditor.ts 1:1 重建互動與繪製規格）
#include "PingMixEditor.hpp"

#include "GUI_App.hpp"

#include <wx/sizer.h>
#include <wx/button.h>
#include <wx/checkbox.h>
#include <wx/stattext.h>
#include <wx/dcmemory.h>
#include <wx/dcgraph.h>
#include <wx/dcclient.h>
#include <wx/colordlg.h>
#include <wx/display.h>
#include <wx/popupwin.h>
#include <wx/timer.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <vector>

namespace Slic3r {
namespace GUI {

// —— 視覺常數（web 藍圖 §9）——
static const wxColour COL_CHARCOAL(0x20, 0x22, 0x21);   // 曲線/端點/強調文字
static const wxColour COL_ORANGE(0xEA, 0x4E, 0x16);     // 中間節點/active
static const wxColour COL_FRAME(0xCF, 0xCF, 0xCF);      // 外框
static const wxColour COL_LABEL(0x9A, 0x9A, 0x9A);      // 軸標
static const wxColour COL_PCT(0x66, 0x66, 0x66);        // 比例%
static const wxColour COL_POS(0xAA, 0xAA, 0xAA);        // 高度%
static const wxColour COL_PLOT_BG(0xFF, 0xFF, 0xFF);    // 繪圖區白底（顏色判讀基準，深色模式亦同）

// —— 深色提示框：仿畫布 ImGui canvas_tooltip 的長相（Eric 2026-07-17 指定樣式）——
// 規格照抄 GLCanvas3D::Tooltip::render＋ImGuiWrapper::COL_WINDOW_BACKGROUND：
// 底色 RGB(26,26,26)、整窗 alpha 0.8（=204，半透黑）、圓角 0、無尖角箭頭、
// 白字、顯示在滑鼠下方 16px、500ms 延遲。上一版用 wxRichToolTip 會自帶白框＋尖角氣泡（已撤）。
namespace {
class PingDarkTooltip : public wxPopupWindow
{
public:
    PingDarkTooltip(wxWindow* parent, const wxString& text)
        : wxPopupWindow(parent, wxBORDER_NONE)
    {
        m_pad = parent->FromDIP(5);
        // PING(2026-07-24 異常單 #24/#25)：量測改「彈窗自身 DC＋自身字型」＋上限寬自動折行。
        // 舊作法拿 parent DC 量「單行」定窗寬：跨 DPI 螢幕時量測與實繪比例不同、實繪偏寬
        // → 右端被窗框吃掉（#24「輸出 G-code 將依」後截斷）；單行長句貼螢幕右緣也易遮擋（#25）。
        // 折行＝逐字累積超過 max_w 換行；ASCII 連續段（如 G-code）不從中折斷。
        SetFont(wxGetApp().normal_font());
        wxClientDC dc(this);
        dc.SetFont(GetFont());
        const int max_w = FromDIP(300);
        const auto is_word = [](wxUniChar ch) {
            const wxUint32 v = ch.GetValue();
            return (v >= 'A' && v <= 'Z') || (v >= 'a' && v <= 'z') ||
                   (v >= '0' && v <= '9') || v == '-';
        };
        wxString line;
        for (size_t i = 0; i < text.length(); ++i) {
            line += text[i];
            if (dc.GetTextExtent(line).x <= max_w || line.length() <= 1)
                continue;
            size_t cut = line.length() - 1;   // 預設把最後一字移到下一行
            if (is_word(line[cut])) {          // ASCII 詞不折半：回退到詞首
                size_t ws = cut;
                while (ws > 0 && is_word(line[ws - 1])) --ws;
                if (ws > 0) cut = ws;
            }
            m_lines.push_back(line.Left(cut));
            line = line.Mid(cut);
        }
        if (!line.IsEmpty())
            m_lines.push_back(line);
        m_line_h = dc.GetCharHeight();
        int w = 0;
        for (const wxString& l : m_lines)
            w = std::max(w, dc.GetTextExtent(l).x);
        SetSize(wxSize(w + 2 * m_pad, m_line_h * (int) m_lines.size() + 2 * m_pad));
        SetBackgroundStyle(wxBG_STYLE_PAINT);
        SetTransparent(204);   // 0.8 × 255——整窗半透（白字會同帶 0.8，視覺與畫布提示一致）
        Bind(wxEVT_PAINT, [this](wxPaintEvent&) {
            wxPaintDC pdc(this);
            pdc.SetPen(*wxTRANSPARENT_PEN);
            pdc.SetBrush(wxBrush(wxColour(26, 26, 26)));
            pdc.DrawRectangle(GetClientRect());
            pdc.SetFont(GetFont());
            pdc.SetTextForeground(*wxWHITE);
            for (size_t i = 0; i < m_lines.size(); ++i)
                pdc.DrawText(m_lines[i], m_pad, m_pad + (int) i * m_line_h);
        });
    }
    void show_below_cursor()
    {
        // Position() 以「錨矩形」定位：錨＝滑鼠點往下 16px，超出螢幕會自動翻到上方
        Position(wxGetMousePosition(), wxSize(0, FromDIP(16)));
        Show();
    }
private:
    std::vector<wxString> m_lines;
    int                   m_line_h = 0;
    int                   m_pad = 0;
};
} // namespace

void bind_ping_dark_tooltip(wxWindow* target, const wxString& text)
{
    if (target == nullptr || text.IsEmpty())
        return;
    struct State { PingDarkTooltip* tip = nullptr; wxTimer timer; };
    auto st = std::make_shared<State>();
    st->timer.SetOwner(target);
    target->Bind(wxEVT_ENTER_WINDOW, [st](wxMouseEvent& e) {
        st->timer.StartOnce(500);   // 同畫布提示的 500ms 延遲
        e.Skip();
    });
    target->Bind(wxEVT_TIMER, [st, target, text](wxTimerEvent&) {
        if (st->tip == nullptr)
            st->tip = new PingDarkTooltip(target, text);
        st->tip->show_below_cursor();
    });
    auto hide = [st](wxEvent& e) {
        st->timer.Stop();
        if (st->tip != nullptr) { st->tip->Destroy(); st->tip = nullptr; }
        e.Skip();
    };
    target->Bind(wxEVT_LEAVE_WINDOW, hide);
    target->Bind(wxEVT_LEFT_DOWN, hide);
}

static wxColour ping_hex_to_wx(const std::string& hex)
{
    int rgb[3];
    PingMix::parse_hex_color(hex, rgb);
    return wxColour(rgb[0], rgb[1], rgb[2]);
}

// ============================ PingMixCanvas ============================

PingMixCanvas::PingMixCanvas(PingMixEditor* editor, wxWindow* parent)
    : wxWindow(parent, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxFULL_REPAINT_ON_RESIZE)
    , m_editor(editor)
{
    SetBackgroundStyle(wxBG_STYLE_PAINT);
    SetMinSize(wxSize(FromDIP(300), FromDIP(330)));
    Bind(wxEVT_PAINT, &PingMixCanvas::on_paint, this);
    Bind(wxEVT_LEFT_DOWN, &PingMixCanvas::on_left_down, this);
    Bind(wxEVT_MOTION, &PingMixCanvas::on_motion, this);
    Bind(wxEVT_LEFT_UP, &PingMixCanvas::on_left_up, this);
    Bind(wxEVT_LEFT_DCLICK, &PingMixCanvas::on_left_dclick, this);
    Bind(wxEVT_MOUSE_CAPTURE_LOST, &PingMixCanvas::on_capture_lost, this);
    Bind(wxEVT_SIZE, &PingMixCanvas::on_size, this);
}

void PingMixCanvas::on_size(wxSizeEvent& evt)
{
    Refresh();
    evt.Skip();
}

wxRect PingMixCanvas::plot_rect(const wxSize& size) const
{
    if (m_editor->is_quad()) {
        // quad：padL=26、padT=32、底 32；右側留 22px 預覽帶＋8 邊距＋12 間隔
        const int padL = FromDIP(26), padT = FromDIP(32), padB = FromDIP(32);
        const int prev_w = FromDIP(22);
        const int band_right = size.x - prev_w - FromDIP(8) - FromDIP(12);
        return wxRect(padL, padT, std::max(10, band_right - padL), std::max(10, size.y - padT - padB));
    }
    const int pad = FromDIP(32);
    return wxRect(pad, pad, std::max(10, size.x - 2 * pad), std::max(10, size.y - 2 * pad));
}

wxPoint PingMixCanvas::dual_to_screen(double pos, double ratio, const wxRect& plot) const
{
    // 左=E1 100%、右=E2 100%；下=底 0%、上=頂 100%
    const int x = plot.x + (int)std::lround((1.0 - ratio) * plot.width);
    const int y = plot.y + (int)std::lround((1.0 - pos) * plot.height);
    return wxPoint(x, y);
}

wxPoint PingMixCanvas::quad_to_screen(double pos, double cum, const wxRect& plot) const
{
    const int x = plot.x + (int)std::lround(cum * plot.width);
    const int y = plot.y + (int)std::lround((1.0 - pos) * plot.height);
    return wxPoint(x, y);
}

int PingMixCanvas::hit_dual_stop(const wxPoint& p, const wxRect& plot) const
{
    const auto& stops = m_editor->recipe().stops;
    const double R = FromDIP(13);
    for (size_t i = 0; i < stops.size(); ++i) {
        const wxPoint sp = dual_to_screen(stops[i].pos, stops[i].ratio, plot);
        if (std::hypot(double(p.x - sp.x), double(p.y - sp.y)) < R)
            return (int)i;
    }
    return -1;
}

int PingMixCanvas::hit_quad_handle(const wxPoint& p, const wxRect& plot) const
{
    const auto& qstops = m_editor->recipe().qstops;
    const int hx = plot.x - FromDIP(13);
    const double R = FromDIP(11);
    for (size_t i = 0; i < qstops.size(); ++i) {
        const int hy = plot.y + (int)std::lround((1.0 - qstops[i].pos) * plot.height);
        if (std::hypot(double(p.x - hx), double(p.y - hy)) < R)
            return (int)i;
    }
    return -1;
}

bool PingMixCanvas::hit_quad_divider(const wxPoint& p, const wxRect& plot, int& stop_idx, int& div_idx) const
{
    const auto& qstops = m_editor->recipe().qstops;
    const double R = FromDIP(9);
    for (size_t i = 0; i < qstops.size(); ++i) {
        const int y = plot.y + (int)std::lround((1.0 - qstops[i].pos) * plot.height);
        double cum = 0.0;
        for (int d = 0; d < 3; ++d) {
            cum += qstops[i].mix[d];
            const int x = plot.x + (int)std::lround(cum * plot.width);
            if (std::hypot(double(p.x - x), double(p.y - y)) < R) {
                stop_idx = (int)i;
                div_idx = d;
                return true;
            }
        }
    }
    return false;
}

void PingMixCanvas::on_paint(wxPaintEvent&)
{
    wxPaintDC pdc(this);
    const wxSize size = GetSize();
    if (size.x <= 0 || size.y <= 0)
        return;
    wxBitmap bmp(size.x, size.y);
    {
        wxMemoryDC mdc(bmp);
        wxGCDC dc(mdc);
        render(dc, size);
    }
    pdc.DrawBitmap(bmp, 0, 0);
}

void PingMixCanvas::render(wxDC& dc, const wxSize& size)
{
    // 面板底色（跟隨系統/深色模式），繪圖區固定白底做顏色判讀
    dc.SetBackground(wxBrush(GetParent()->GetBackgroundColour()));
    dc.Clear();
    if (m_editor->is_quad())
        render_quad(dc, size);
    else
        render_dual(dc, size);
}

// —— 雙料（curveEditor.ts）——
void PingMixCanvas::render_dual(wxDC& dc, const wxSize& size)
{
    const wxRect plot = plot_rect(size);
    const PingMix::Recipe& r = m_editor->recipe();
    const auto& colors = m_editor->state().colors;
    int c1[3], c2[3];
    PingMix::parse_hex_color(colors[0], c1);
    PingMix::parse_hex_color(colors[1], c2);

    // 繪圖區白底
    dc.SetPen(*wxTRANSPARENT_PEN);
    dc.SetBrush(wxBrush(COL_PLOT_BG));
    dc.DrawRectangle(plot);

    // 背景漸層：垂直 24 帶、帶中心取樣、透明度 0.22（wxGCDC 支援 alpha）。
    // ⚠ 帶區間不可重疊：alpha 疊加會讓重疊帶顏色加倍（Eric 實測抓到「頂端一截特別濃」）
    const int BG_STEPS = 24;
    for (int k = 0; k < BG_STEPS; ++k) {
        const double pos = (k + 0.5) / BG_STEPS; // 帶中心
        const double ratio = PingMix::sample_ratio(r.stops, pos, r.mode);
        int rgb[3];
        PingMix::dual_color(ratio, c1, c2, rgb);
        const int y1 = plot.y + (int)std::lround((1.0 - double(k + 1) / BG_STEPS) * plot.height);
        const int y0 = plot.y + (int)std::lround((1.0 - double(k) / BG_STEPS) * plot.height);
        dc.SetBrush(wxBrush(wxColour(rgb[0], rgb[1], rgb[2], 56))); // 0.22*255≈56
        dc.DrawRectangle(plot.x, y1, plot.width, std::max(1, y0 - y1));
    }

    // 外框
    dc.SetPen(wxPen(COL_FRAME, 1));
    dc.SetBrush(*wxTRANSPARENT_BRUSH);
    dc.DrawRectangle(plot);

    // 軸標
    wxFont small_font = GetFont();
    small_font.SetPointSize(std::max(6, small_font.GetPointSize() - 2));
    dc.SetFont(small_font);
    dc.SetTextForeground(COL_LABEL);
    dc.DrawText(wxString::FromUTF8("頂部 100%"), plot.x, plot.y - FromDIP(16));
    dc.DrawText(wxString::FromUTF8("底部 0%"), plot.x, plot.y + plot.height + FromDIP(4));
    dc.DrawRotatedText(wxString::FromUTF8("列印高度"), FromDIP(2), plot.y + plot.height / 2 + FromDIP(24), 90);
    {
        const wxString axis = wxString::FromUTF8("E1 ←  混色比例  → E2");
        const wxSize te = dc.GetTextExtent(axis);
        dc.DrawText(axis, plot.x + (plot.width - te.x) / 2, plot.y + plot.height + FromDIP(16));
    }

    // 曲線（先按 pos 排序）
    std::vector<PingMix::Stop> sorted = r.stops;
    std::sort(sorted.begin(), sorted.end(), [](const PingMix::Stop& a, const PingMix::Stop& b) { return a.pos < b.pos; });
    dc.SetPen(wxPen(COL_CHARCOAL, 2));
    if (r.mode == PingMix::CurveMode::Smooth) {
        const int N = 48;
        wxPoint prev = dual_to_screen(0.0, PingMix::sample_ratio(r.stops, 0.0, r.mode), plot);
        for (int k = 1; k <= N; ++k) {
            const double t = double(k) / N;
            const wxPoint cur = dual_to_screen(t, PingMix::sample_ratio(r.stops, t, r.mode), plot);
            dc.DrawLine(prev, cur);
            prev = cur;
        }
    } else if (r.mode == PingMix::CurveMode::Step) {
        for (size_t i = 1; i < sorted.size(); ++i) {
            const wxPoint a = dual_to_screen(sorted[i - 1].pos, sorted[i - 1].ratio, plot);
            const wxPoint b = dual_to_screen(sorted[i].pos, sorted[i].ratio, plot);
            dc.DrawLine(a.x, a.y, a.x, b.y); // 垂直（維持前一點比例到這個高度）
            dc.DrawLine(a.x, b.y, b.x, b.y); // 水平（跳變到這點比例）
        }
    } else {
        for (size_t i = 1; i < sorted.size(); ++i)
            dc.DrawLine(dual_to_screen(sorted[i - 1].pos, sorted[i - 1].ratio, plot),
                        dual_to_screen(sorted[i].pos, sorted[i].ratio, plot));
    }

    // 節點（畫原始陣列，index 對拖曳）
    wxFont tiny_font = GetFont();
    tiny_font.SetPointSize(std::max(6, tiny_font.GetPointSize() - 3));
    for (size_t i = 0; i < r.stops.size(); ++i) {
        const PingMix::Stop& st = r.stops[i];
        const wxPoint sp = dual_to_screen(st.pos, st.ratio, plot);
        const bool endpoint = (st.pos <= 0.0 || st.pos >= 1.0);
        if (endpoint) {
            const int s = FromDIP(5);
            dc.SetPen(wxPen(*wxWHITE, 2));
            dc.SetBrush(wxBrush(COL_CHARCOAL));
            dc.DrawRectangle(sp.x - s, sp.y - s, 2 * s, 2 * s);
        } else {
            dc.SetPen(wxPen(*wxWHITE, 2));
            dc.SetBrush(wxBrush(COL_ORANGE));
            dc.DrawCircle(sp, FromDIP(6));
        }
        dc.SetFont(tiny_font);
        dc.SetTextForeground(COL_PCT);
        dc.DrawText(wxString::Format("%d%%", (int)std::lround(st.ratio * 100)), sp.x + FromDIP(9), sp.y - FromDIP(6));
        if (!endpoint) {
            dc.SetTextForeground(COL_POS);
            const wxString ptxt = wxString::Format(wxString::FromUTF8("↕%d%%"), (int)std::lround(st.pos * 100));
            const wxSize te = dc.GetTextExtent(ptxt);
            dc.DrawText(ptxt, sp.x - FromDIP(9) - te.x, sp.y - FromDIP(6));
        }
    }
}

// —— 四料（quadEditor.ts）——
void PingMixCanvas::render_quad(wxDC& dc, const wxSize& size)
{
    const wxRect plot = plot_rect(size);
    const PingMix::Recipe& r = m_editor->recipe();
    const auto& hex_colors = m_editor->state().colors;
    int cols[4][3];
    for (int i = 0; i < 4; ++i)
        PingMix::parse_hex_color(hex_colors[i], cols[i]);

    // 邊界列（boundaryRows）：pos + 四料 mix
    struct Row { double pos; double mix[4]; };
    std::vector<Row> rows;
    std::vector<PingMix::QuadStop> sorted = r.qstops;
    std::sort(sorted.begin(), sorted.end(), [](const PingMix::QuadStop& a, const PingMix::QuadStop& b) { return a.pos < b.pos; });
    if (r.mode == PingMix::CurveMode::Smooth) {
        const int N = 64;
        for (int k = 0; k <= N; ++k) {
            Row row; row.pos = double(k) / N;
            PingMix::sample_quad_mix(r.qstops, row.pos, r.mode, r.min_flow, row.mix);
            rows.push_back(row);
        }
    } else {
        if (!sorted.empty() && sorted.front().pos > 0.0) {
            Row row; row.pos = 0.0;
            for (int k = 0; k < 4; ++k) row.mix[k] = sorted.front().mix[k];
            rows.push_back(row);
        }
        for (size_t i = 0; i < sorted.size(); ++i) {
            if (r.mode == PingMix::CurveMode::Step && i > 0) {
                Row jump; jump.pos = sorted[i].pos;  // 階梯：同高度先補前一節點值 → 垂直跳變
                for (int k = 0; k < 4; ++k) jump.mix[k] = sorted[i - 1].mix[k];
                rows.push_back(jump);
            }
            Row row; row.pos = sorted[i].pos;
            for (int k = 0; k < 4; ++k) row.mix[k] = sorted[i].mix[k];
            rows.push_back(row);
        }
        if (!sorted.empty() && sorted.back().pos < 1.0) {
            Row row; row.pos = 1.0;
            for (int k = 0; k < 4; ++k) row.mix[k] = sorted.back().mix[k];
            rows.push_back(row);
        }
    }

    // 繪圖區白底
    dc.SetPen(*wxTRANSPARENT_PEN);
    dc.SetBrush(wxBrush(COL_PLOT_BG));
    dc.DrawRectangle(plot);

    // 4 條堆疊帶：左邊界 cum[k]（下→上）＋右邊界 cum[k+1]（上→下），原色填滿
    for (int band = 0; band < 4; ++band) {
        std::vector<wxPoint> poly;
        poly.reserve(rows.size() * 2);
        for (const Row& row : rows) { // 下→上：左邊界
            double cum = 0.0;
            for (int k = 0; k < band; ++k) cum += row.mix[k];
            poly.push_back(quad_to_screen(row.pos, cum, plot));
        }
        for (auto it = rows.rbegin(); it != rows.rend(); ++it) { // 上→下：右邊界
            double cum = 0.0;
            for (int k = 0; k <= band; ++k) cum += it->mix[k];
            poly.push_back(quad_to_screen(it->pos, cum, plot));
        }
        dc.SetPen(*wxTRANSPARENT_PEN);
        dc.SetBrush(wxBrush(wxColour(cols[band][0], cols[band][1], cols[band][2])));
        dc.DrawPolygon((int)poly.size(), poly.data());
    }

    // 外框
    dc.SetPen(wxPen(COL_FRAME, 1));
    dc.SetBrush(*wxTRANSPARENT_BRUSH);
    dc.DrawRectangle(plot);

    // 右側預覽帶（與 3D 染色同一套 linear-RGB 混色）——同樣不可重疊（同雙料背景帶的教訓）
    const int prev_w = FromDIP(22);
    const int prev_x = size.x - prev_w - FromDIP(8);
    const int N = 64;
    for (int k = 0; k < N; ++k) {
        const double t = (k + 0.5) / N; // 帶中心
        double mix[4]; int rgb[3];
        PingMix::sample_quad_mix(r.qstops, t, r.mode, r.min_flow, mix);
        PingMix::quad_color(mix, cols, rgb);
        const int y1 = plot.y + (int)std::lround((1.0 - double(k + 1) / N) * plot.height);
        const int y0 = plot.y + (int)std::lround((1.0 - double(k) / N) * plot.height);
        dc.SetPen(*wxTRANSPARENT_PEN);
        dc.SetBrush(wxBrush(wxColour(rgb[0], rgb[1], rgb[2])));
        dc.DrawRectangle(prev_x, y1, prev_w, std::max(1, y0 - y1));
    }
    dc.SetPen(wxPen(COL_FRAME, 1));
    dc.SetBrush(*wxTRANSPARENT_BRUSH);
    dc.DrawRectangle(prev_x, plot.y, prev_w, plot.height);

    // 節點水平線＋手柄＋分隔點
    wxFont tiny_font = GetFont();
    tiny_font.SetPointSize(std::max(6, tiny_font.GetPointSize() - 3));
    dc.SetFont(tiny_font);
    for (size_t i = 0; i < r.qstops.size(); ++i) {
        const PingMix::QuadStop& q = r.qstops[i];
        const int y = plot.y + (int)std::lround((1.0 - q.pos) * plot.height);
        // 水平線（黑 32% 透明）
        dc.SetPen(wxPen(wxColour(0x20, 0x22, 0x21, 82), 1));
        dc.DrawLine(plot.x, y, plot.x + plot.width, y);
        // 左側手柄
        const int hx = plot.x - FromDIP(13);
        const bool endpoint = (q.pos <= 0.0 || q.pos >= 1.0);
        if (endpoint) {
            const int s = FromDIP(5);
            dc.SetPen(wxPen(*wxWHITE, 2));
            dc.SetBrush(wxBrush(COL_CHARCOAL));
            dc.DrawRectangle(hx - s, y - s, 2 * s, 2 * s);
        } else {
            dc.SetPen(wxPen(*wxWHITE, 2));
            dc.SetBrush(wxBrush(COL_ORANGE));
            dc.DrawCircle(hx, y, FromDIP(6));
            dc.SetTextForeground(COL_PCT);
            dc.DrawText(wxString::Format("%d%%", (int)std::lround(q.pos * 100)), hx - FromDIP(8), y - FromDIP(18));
        }
        // 分隔點（cum[1..3]）
        double cum = 0.0;
        for (int d = 0; d < 3; ++d) {
            cum += q.mix[d];
            const wxPoint dp = quad_to_screen(q.pos, cum, plot);
            const bool active = m_dragging && m_drag_stop == (int)i && m_drag_div == d;
            dc.SetPen(wxPen(active ? COL_ORANGE : COL_CHARCOAL, 2));
            dc.SetBrush(wxBrush(*wxWHITE));
            dc.DrawCircle(dp, FromDIP(5));
        }
    }

    // 拖曳中：右上即時配比；平時「預覽」標籤
    dc.SetFont(tiny_font);
    if (m_dragging && m_drag_stop >= 0 && m_drag_stop < (int)r.qstops.size()) { // 分隔點與手柄拖曳都顯示（web 規格）
        int pct[4];
        PingMix::mix_to_percents(r.qstops[m_drag_stop].mix, pct);
        const wxString info = wxString::Format(wxString::FromUTF8("E1 %d｜E2 %d｜E3 %d｜E4 %d %%"), pct[0], pct[1], pct[2], pct[3]);
        dc.SetTextForeground(COL_CHARCOAL);
        const wxSize te = dc.GetTextExtent(info);
        dc.DrawText(info, plot.x + plot.width - te.x, plot.y - FromDIP(16));
    } else {
        dc.SetTextForeground(COL_LABEL);
        dc.DrawText(wxString::FromUTF8("預覽"), prev_x, plot.y - FromDIP(16));
    }

    // 軸標與圖例
    dc.SetTextForeground(COL_LABEL);
    dc.DrawText(wxString::FromUTF8("頂部 100%"), plot.x, plot.y - FromDIP(16));
    dc.DrawText(wxString::FromUTF8("底部 0%"), plot.x, plot.y + plot.height + FromDIP(4));
    int lx = plot.x + FromDIP(64);
    const int ly = plot.y + plot.height + FromDIP(4);
    for (int k = 0; k < 4; ++k) {
        dc.SetPen(*wxTRANSPARENT_PEN);
        dc.SetBrush(wxBrush(wxColour(cols[k][0], cols[k][1], cols[k][2])));
        dc.DrawRectangle(lx, ly + FromDIP(2), FromDIP(9), FromDIP(9));
        dc.SetTextForeground(COL_PCT);
        dc.DrawText(wxString::Format("E%d", k + 1), lx + FromDIP(11), ly);
        lx += FromDIP(46);
    }
}

// —— 互動 —— //

void PingMixCanvas::on_left_down(wxMouseEvent& evt)
{
    const wxRect plot = plot_rect(GetSize());
    m_drag_stop = -1;
    m_drag_div = -1;
    if (m_editor->is_quad()) {
        int si, di;
        if (hit_quad_divider(evt.GetPosition(), plot, si, di)) {      // 分隔點優先（web 規格）
            m_drag_stop = si; m_drag_div = di;
        } else {
            const int h = hit_quad_handle(evt.GetPosition(), plot);
            if (h >= 0) m_drag_stop = h;
        }
    } else {
        m_drag_stop = hit_dual_stop(evt.GetPosition(), plot);
    }
    if (m_drag_stop >= 0) {
        m_dragging = true;
        if (!HasCapture()) CaptureMouse();
        Refresh();
    }
    evt.Skip();
}

void PingMixCanvas::on_motion(wxMouseEvent& evt)
{
    const wxRect plot = plot_rect(GetSize());
    if (!m_dragging || m_drag_stop < 0) {
        // 未拖曳：依 hover 目標換游標
        if (m_editor->is_quad()) {
            int si, di;
            if (hit_quad_divider(evt.GetPosition(), plot, si, di))
                SetCursor(wxCursor(wxCURSOR_SIZEWE));
            else if (hit_quad_handle(evt.GetPosition(), plot) >= 0)
                SetCursor(wxCursor(wxCURSOR_SIZENS));
            else
                SetCursor(wxCursor(wxCURSOR_ARROW));
        } else {
            SetCursor(hit_dual_stop(evt.GetPosition(), plot) >= 0 ? wxCursor(wxCURSOR_SIZING) : wxCursor(wxCURSOR_ARROW));
        }
        return;
    }

    PingMix::Recipe& r = m_editor->recipe();
    const double fx = double(evt.GetPosition().x - plot.x) / std::max(1, plot.width);   // 0..1（左→右）
    const double fy = 1.0 - double(evt.GetPosition().y - plot.y) / std::max(1, plot.height); // 0..1（下→上）

    if (m_editor->is_quad()) {
        if (m_drag_stop >= (int)r.qstops.size()) return;
        PingMix::QuadStop& q = r.qstops[m_drag_stop];
        if (m_drag_div >= 0) {
            // 切蛋糕：只動相鄰兩料，總和不變
            double cum_lo = 0.0;
            for (int k = 0; k < m_drag_div; ++k) cum_lo += q.mix[k];
            double cum_hi = cum_lo + q.mix[m_drag_div] + q.mix[m_drag_div + 1];
            // 手動 clamp（相鄰兩料都在下限時 lo==hi，std::clamp 遇 lo>hi 是 UB）
            double c = fx;
            if (c < cum_lo + r.min_flow) c = cum_lo + r.min_flow;
            if (c > cum_hi - r.min_flow) c = cum_hi - r.min_flow;
            q.mix[m_drag_div]     = c - cum_lo;
            q.mix[m_drag_div + 1] = cum_hi - c;
        } else {
            // 手柄：調高度；端點固定
            if (q.pos > 0.0 && q.pos < 1.0)
                q.pos = std::clamp(fy, 0.02, 0.98);
        }
    } else {
        if (m_drag_stop >= (int)r.stops.size()) return;
        PingMix::Stop& st = r.stops[m_drag_stop];
        st.ratio = std::clamp(1.0 - fx, PingMix::MIN_S, PingMix::MAX_S); // 左=E1 100%
        if (st.pos > 0.0 && st.pos < 1.0)
            st.pos = std::clamp(fy, 0.02, 0.98);
    }
    Refresh();
}

void PingMixCanvas::on_left_up(wxMouseEvent& evt)
{
    if (m_dragging) {
        m_dragging = false;
        m_drag_stop = -1;
        m_drag_div = -1;
        if (HasCapture()) ReleaseMouse();
        Refresh();
        m_editor->commit();  // 放開才 commit（拖曳中只重畫，避免逐幀重烘 1M vertex）
    }
    evt.Skip();
}

void PingMixCanvas::on_capture_lost(wxMouseCaptureLostEvent&)
{
    if (m_dragging) {
        m_dragging = false;
        m_drag_stop = -1;
        m_drag_div = -1;
        Refresh();
        m_editor->commit();
    }
}

void PingMixCanvas::on_left_dclick(wxMouseEvent& evt)
{
    const wxRect plot = plot_rect(GetSize());
    PingMix::Recipe& r = m_editor->recipe();
    const double fx = double(evt.GetPosition().x - plot.x) / std::max(1, plot.width);
    const double fy = 1.0 - double(evt.GetPosition().y - plot.y) / std::max(1, plot.height);

    if (m_editor->is_quad()) {
        const int h = hit_quad_handle(evt.GetPosition(), plot);
        if (h >= 0) {
            // 刪中間節點（端點永不可刪）
            if (r.qstops.size() > 2 && r.qstops[h].pos > 0.0 && r.qstops[h].pos < 1.0) {
                r.qstops.erase(r.qstops.begin() + h);
                Refresh();
                m_editor->commit();
            }
            return;
        }
        // Eric 2026-07-02 驗收回饋：「點兩下它就移除」——雙擊節點線上的任何東西
        //（分隔點、線本身）都視同刪該節點，不必精準點到左緣手柄（web 藍圖只認手柄，不直覺）
        auto try_delete = [&](int idx) {
            if (r.qstops.size() > 2 && r.qstops[idx].pos > 0.0 && r.qstops[idx].pos < 1.0) {
                r.qstops.erase(r.qstops.begin() + idx);
                Refresh();
                m_editor->commit();
            }
        };
        int si, di;
        if (hit_quad_divider(evt.GetPosition(), plot, si, di)) {
            try_delete(si);
            return;
        }
        // 節點水平線鄰近（±6px）也算「點到它」
        for (size_t i = 0; i < r.qstops.size(); ++i) {
            const int ly = plot.y + (int)std::lround((1.0 - r.qstops[i].pos) * plot.height);
            if (std::abs(evt.GetPosition().y - ly) <= FromDIP(6) &&
                evt.GetPosition().x >= plot.x && evt.GetPosition().x <= plot.x + plot.width) {
                try_delete((int)i);
                return;
            }
        }
        if (plot.Contains(evt.GetPosition())) {
            // 帶內空白雙擊：於該高度新增節點（值取當前曲線 → 外觀不變）
            PingMix::QuadStop q;
            q.pos = std::clamp(fy, 0.02, 0.98);
            PingMix::sample_quad_mix(r.qstops, q.pos, r.mode, r.min_flow, q.mix);
            r.qstops.push_back(q);
            Refresh();
            m_editor->commit();
        }
    } else {
        const int h = hit_dual_stop(evt.GetPosition(), plot);
        if (h >= 0) {
            if (r.stops.size() > 2 && r.stops[h].pos > 0.0 && r.stops[h].pos < 1.0) {
                r.stops.erase(r.stops.begin() + h);
                Refresh();
                m_editor->commit();
            }
            return;
        }
        if (plot.Contains(evt.GetPosition())) {
            PingMix::Stop st;
            st.pos = std::clamp(fy, 0.02, 0.98);
            st.ratio = std::clamp(1.0 - fx, PingMix::MIN_S, PingMix::MAX_S);
            r.stops.push_back(st);
            Refresh();
            m_editor->commit();
        }
    }
}

// ============================ PingMixEditor ============================

PingMixEditor::PingMixEditor(wxWindow* parent)
    : wxPanel(parent, wxID_ANY)
{
    // 編輯器整面白底（含深色模式——顏色判讀基準同 COL_PLOT_BG）。必須在建子控件前設定：
    // StaticBox/Button 建構時抓「當下的父背景色」清圓角外緣，父色沒先設好會殘灰方塊
    //（Eric 2026-07-17 回饋：收合/範本/模式鈕後方灰底；同 GUI_Preview 浮動混色鈕的修法）。
    SetBackgroundColour(COL_PLOT_BG);
    build_controls();
}

void PingMixEditor::build_controls()
{
    wxBoxSizer* vbox = new wxBoxSizer(wxVERTICAL);

    // 標題列：標題＋（右側）收合鈕——平常不用混色時收成右緣窄條，要用再展開（Eric 2026-07-02）
    wxBoxSizer* title_row = new wxBoxSizer(wxHORIZONTAL);
    // PING(2026-07-26 Eric)：開合處直寫狀態——展開＝「混色啟用」、收合浮鈕＝「混色停用」
    m_title = new wxStaticText(this, wxID_ANY, wxString::FromUTF8("混色啟用"));
    wxFont tf = m_title->GetFont();
    tf.SetWeight(wxFONTWEIGHT_BOLD);
    m_title->SetFont(tf);
    title_row->Add(m_title, 0, wxALIGN_CENTER_VERTICAL);
    title_row->AddStretchSpacer(1);
    // PING(2026-07-24 異常單 #25)：標籤去「 ▶」尾符——混排符號在 wxMSW 的量測與實繪寬度
    // 不一致（▶ 走字型 fallback），置中框據量測值算出來就偏斜；純中文單一字型段量測＝實繪。
    m_collapse_btn = new ::Button(this, wxString::FromUTF8("收合"));
    m_collapse_btn->SetStyle(ButtonStyle::Regular, ButtonType::Compact);
    bind_ping_dark_tooltip(m_collapse_btn,
        wxString::FromUTF8("收合並停用混色——輸出 G-code 恢復原樣不插混色指令；點右上「混色停用」重新啟用"));
    m_collapse_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        // B 案：收合＝混色關閉（輸出 gcode 還原原樣、預覽退出混色檢視）
        if (wxGetApp().plater() != nullptr)
            wxGetApp().plater()->set_ping_mix_enabled(false);
        if (m_toggle_cb) m_toggle_cb();
    });
    title_row->Add(m_collapse_btn, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(8));
    vbox->Add(title_row, 0, wxEXPAND | wxLEFT | wxTOP, FromDIP(8));

    // PING(2026-07-09 Eric)：層級改「範本為主選」——範本列（同進/漸層…）排在前、帶選中狀態；
    // 曲線模式列（漸層/階梯/平滑）是漸層的細部選項，只在「非同進均分」時顯示（漸進揭露）。
    // 範本列＋低流量（軟體標準 Button：未選 Regular、選中 Confirm，見 sync_controls）
    wxBoxSizer* tpl_row = new wxBoxSizer(wxHORIZONTAL);
    for (int i = 0; i < 3; ++i) {
        m_tpl_btns[i] = new ::Button(this, " ");
        m_tpl_btns[i]->SetStyle(ButtonStyle::Regular, ButtonType::Compact);
        m_tpl_btns[i]->SetMinSize(wxSize(FromDIP(56), FromDIP(26)));
        m_tpl_btns[i]->Bind(wxEVT_BUTTON, [this, i](wxCommandEvent&) { on_template_clicked(i); });
        tpl_row->Add(m_tpl_btns[i], 0, wxRIGHT, FromDIP(4));
    }
    m_low_flow = new wxCheckBox(this, wxID_ANY, wxString::FromUTF8("低流量"));
    bind_ping_dark_tooltip(m_low_flow, wxString::FromUTF8("進階：單料下限 10% → 5%（韌體絕對下限）"));
    m_low_flow->Bind(wxEVT_CHECKBOX, [this](wxCommandEvent&) { on_low_flow_toggled(); });
    tpl_row->Add(m_low_flow, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, FromDIP(4));
    vbox->Add(tpl_row, 0, wxLEFT | wxTOP, FromDIP(8));

    // 模式列：漸層/階梯/平滑（同進均分時整列隱藏，見 sync_controls）
    wxBoxSizer* mode_row = new wxBoxSizer(wxHORIZONTAL);
    const wxString mode_names[3] = { wxString::FromUTF8("漸層"), wxString::FromUTF8("階梯"), wxString::FromUTF8("平滑") };
    for (int i = 0; i < 3; ++i) {
        m_mode_btns[i] = new ::Button(this, mode_names[i]);
        m_mode_btns[i]->SetStyle(ButtonStyle::Regular, ButtonType::Compact);
        m_mode_btns[i]->SetMinSize(wxSize(FromDIP(56), FromDIP(26)));
        m_mode_btns[i]->Bind(wxEVT_BUTTON, [this, i](wxCommandEvent&) { on_mode_clicked(i); });
        mode_row->Add(m_mode_btns[i], 0, wxRIGHT, FromDIP(4));
    }
    vbox->Add(mode_row, 0, wxLEFT | wxTOP, FromDIP(8));

    // 色票列（E1..E4；雙料只顯示前兩個）
    wxBoxSizer* swatch_row = new wxBoxSizer(wxHORIZONTAL);
    for (int i = 0; i < 4; ++i) {
        m_swatch_labels[i] = new wxStaticText(this, wxID_ANY, wxString::Format("E%d", i + 1));
        swatch_row->Add(m_swatch_labels[i], 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(2));
        m_swatches[i] = new wxWindow(this, wxID_ANY, wxDefaultPosition, wxSize(FromDIP(22), FromDIP(22)), wxBORDER_SIMPLE);
        m_swatches[i]->SetCursor(wxCursor(wxCURSOR_HAND));
        m_swatches[i]->Bind(wxEVT_LEFT_DOWN, [this, i](wxMouseEvent&) { on_swatch_clicked(i); });
        swatch_row->Add(m_swatches[i], 0, wxRIGHT, FromDIP(8));
    }
    vbox->Add(swatch_row, 0, wxLEFT | wxTOP, FromDIP(8));

    // 畫布
    m_canvas = new PingMixCanvas(this, this);
    vbox->Add(m_canvas, 1, wxEXPAND | wxALL, FromDIP(8));

    SetSizer(vbox);
}

bool PingMixEditor::update_from_plater()
{
    Plater* plater = wxGetApp().plater();
    if (plater == nullptr)
        return false;
    bool is_quad = false;
    // 照片磚機也是同進機，但混色對它不適用 ⇒ 這裡問「混色可不可用」而不是「是不是同進」，
    // 曲線面板才不會在照片磚機上被展開（Eric 2026-08-22 令）。
    const bool mix_ok = plater->is_ping_mix_available(&is_quad);
    // 拖曳中不覆寫狀態（切片完成事件可能插隊；未 commit 的編輯不能被吃掉），只回傳顯示判定
    if (m_canvas != nullptr && m_canvas->is_dragging())
        return mix_ok;
    m_is_quad = is_quad;
    m_state = plater->get_ping_mix_state();
    sync_controls();
    refresh_canvas();
    return mix_ok;
}

void PingMixEditor::sync_controls()
{
    // 標題
    m_title->SetLabel(m_is_quad ? wxString::FromUTF8("混色啟用（四料）")
                                : wxString::FromUTF8("混色啟用（雙料）"));

    // PING(2026-07-09 Eric)：同進（均分）＝不需要曲線模式 → 整列隱藏；選漸層/動過曲線才出現。
    const bool flat_tongjin = is_flat_tongjin();

    // 模式按鈕：選中＝軟體標準 Confirm（橘底白字＋hover #F0683A）、未選＝Regular（僅非同進時可見）
    const PingMix::CurveMode mode = recipe().mode;
    for (int i = 0; i < 3; ++i) {
        const bool active = (int)mode == i;
        m_mode_btns[i]->SetStyle(active ? ButtonStyle::Confirm : ButtonStyle::Regular, ButtonType::Compact);
        m_mode_btns[i]->SetMinSize(wxSize(FromDIP(56), FromDIP(26)));
        m_mode_btns[i]->Show(!flat_tongjin);
        m_mode_btns[i]->Refresh();
    }

    // 範本按鈕選中狀態：同進均分＝「同進」亮；雙料非均分＝「漸層」亮（四料非均分不特別亮——
    // 雙色/彩虹是一次性範本、非持續狀態）
    const int active_tpl = flat_tongjin ? 0 : (m_is_quad ? -1 : 1);
    for (int i = 0; i < 3; ++i) {
        const bool active = i == active_tpl;
        m_tpl_btns[i]->SetStyle(active ? ButtonStyle::Confirm : ButtonStyle::Regular, ButtonType::Compact);
        m_tpl_btns[i]->SetMinSize(wxSize(FromDIP(56), FromDIP(26)));
        m_tpl_btns[i]->Refresh();
    }

    // 範本按鈕
    if (m_is_quad) {
        m_tpl_btns[0]->SetLabel(wxString::FromUTF8("同進"));   // 四色均分
        m_tpl_btns[1]->SetLabel(wxString::FromUTF8("雙色"));   // 雙色過渡
        m_tpl_btns[2]->SetLabel(wxString::FromUTF8("彩虹"));
        m_tpl_btns[2]->Show();
        m_low_flow->Show();
        m_low_flow->SetValue(recipe().min_flow <= 0.051);
    } else {
        m_tpl_btns[0]->SetLabel(wxString::FromUTF8("同進"));   // 50/50 還原
        m_tpl_btns[1]->SetLabel(wxString::FromUTF8("漸層"));   // 5%→95%
        m_tpl_btns[2]->Hide();
        m_low_flow->Hide();
    }

    // 色票
    const int n = m_is_quad ? 4 : 2;
    for (int i = 0; i < 4; ++i) {
        const bool show = i < n;
        m_swatches[i]->Show(show);
        m_swatch_labels[i]->Show(show);
        if (show) {
            m_swatches[i]->SetBackgroundColour(ping_hex_to_wx(m_state.colors[i]));
            m_swatches[i]->Refresh();
        }
    }
    Layout();
}

// 同進均分判定：雙料＝所有節點 50/50、四料＝所有節點 25×4（拖過節點即非同進，模式列跟著現身）
bool PingMixEditor::is_flat_tongjin() const
{
    const PingMix::Recipe& r = recipe();
    if (m_is_quad) {
        for (const PingMix::QuadStop& q : r.qstops)
            for (int k = 0; k < 4; ++k)
                if (std::abs(q.mix[k] - 0.25) > 1e-6)
                    return false;
        return true;
    }
    for (const PingMix::Stop& st : r.stops)
        if (std::abs(st.ratio - 0.5) > 1e-6)
            return false;
    return true;
}

void PingMixEditor::commit()
{
    Plater* plater = wxGetApp().plater();
    if (plater != nullptr)
        plater->set_ping_mix_state(m_state);
    // 拖曳放開也走這裡：曲線一離開「同進均分」，範本亮燈與模式列要跟著換（漸進揭露）
    sync_controls();
}

void PingMixEditor::refresh_canvas()
{
    if (m_canvas != nullptr)
        m_canvas->Refresh();
}

void PingMixEditor::on_mode_clicked(int mode_idx)
{
    recipe().mode = (PingMix::CurveMode)mode_idx;
    sync_controls();
    refresh_canvas();
    commit();
}

void PingMixEditor::on_template_clicked(int tpl_idx)
{
    PingMix::Recipe& r = recipe();
    if (m_is_quad) {
        const double MIN = r.min_flow;
        const double MAX = 1.0 - 3.0 * MIN;
        if (tpl_idx == 0) {        // 四色同進
            r.qstops = { {0.0, {0.25, 0.25, 0.25, 0.25}}, {1.0, {0.25, 0.25, 0.25, 0.25}} };
        } else if (tpl_idx == 1) { // 雙色過渡 E1→E2
            r.qstops = { {0.0, {MAX, MIN, MIN, MIN}}, {1.0, {MIN, MAX, MIN, MIN}} };
        } else {                   // 彩虹 E1→E2→E3→E4
            r.qstops = { {0.0,       {MAX, MIN, MIN, MIN}},
                         {1.0 / 3.0, {MIN, MAX, MIN, MIN}},
                         {2.0 / 3.0, {MIN, MIN, MAX, MIN}},
                         {1.0,       {MIN, MIN, MIN, MAX}} };
        }
        // 套範本不改 mode（web 規格）
    } else {
        if (tpl_idx == 0) {        // 同進＝還原 50/50，並強制回 linear（web 規格）
            r.stops = { {0.0, 0.5}, {1.0, 0.5} };
            r.mode = PingMix::CurveMode::Linear;
        } else {                   // 漸層 5%→95%
            r.stops = { {0.0, PingMix::MIN_S}, {1.0, PingMix::MAX_S} };
        }
    }
    sync_controls();
    refresh_canvas();
    commit();
}

void PingMixEditor::on_low_flow_toggled()
{
    PingMix::Recipe& r = recipe();
    r.min_flow = m_low_flow->GetValue() ? 0.05 : 0.10;
    if (!m_low_flow->GetValue()) {
        // 收緊回 10%：對所有節點重新正規化（web 規格）
        for (PingMix::QuadStop& q : r.qstops) {
            double fixed[4];
            PingMix::normalize_quad_mix(q.mix, r.min_flow, fixed);
            for (int k = 0; k < 4; ++k) q.mix[k] = fixed[k];
        }
    }
    refresh_canvas();
    commit();
}

void PingMixEditor::on_swatch_clicked(int idx)
{
    wxColourData data;
    data.SetColour(ping_hex_to_wx(m_state.colors[idx]));
    wxColourDialog dlg(this, &data);

    // Native colour dialogs otherwise choose a system-default position that may be on the
    // opposite side of a wide window. Re-anchor it beside the swatch and keep it on-screen.
    const wxRect anchor = m_swatches[idx]->GetScreenRect();
    const auto display_idx = wxDisplay::GetFromWindow(m_swatches[idx]);
    const wxRect work_area = wxDisplay(display_idx != wxNOT_FOUND ? display_idx : 0u).GetClientArea();
    dlg.Bind(wxEVT_SHOW, [this, &dlg, anchor, work_area](wxShowEvent& event) {
        event.Skip();
        if (!event.IsShown())
            return;
        dlg.CallAfter([this, &dlg, anchor, work_area]() {
            const wxSize dialog_size = dlg.GetSize();
            const int gap = FromDIP(8);
            int x = anchor.GetRight() + gap;
            if (x + dialog_size.x > work_area.GetRight())
                x = anchor.GetLeft() - dialog_size.x - gap;
            const int max_x = std::max(work_area.GetLeft(), work_area.GetRight() - dialog_size.x + 1);
            const int max_y = std::max(work_area.GetTop(), work_area.GetBottom() - dialog_size.y + 1);
            x = std::clamp(x, work_area.GetLeft(), max_x);
            const int y = std::clamp(anchor.GetTop(), work_area.GetTop(), max_y);
            dlg.Move(wxPoint(x, y));
        });
    });
    if (dlg.ShowModal() == wxID_OK) {
        const wxColour c = dlg.GetColourData().GetColour();
        char buf[8];
        std::snprintf(buf, sizeof(buf), "#%02X%02X%02X", c.Red(), c.Green(), c.Blue());
        m_state.colors[idx] = buf;
        sync_controls();
        refresh_canvas();
        commit();
    }
}

} // namespace GUI
} // namespace Slic3r
