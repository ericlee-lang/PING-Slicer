#ifndef slic3r_GUI_SplashLayered_hpp_
#define slic3r_GUI_SplashLayered_hpp_

// PING: 啟動畫面 per-pixel 去背（桌面透出）。
// Win32 UpdateLayeredWindow 需要 <windows.h>，其巨集(DrawText/GetObject…)會破壞 GUI_App.cpp
// 內大量 wx 呼叫，故把 Win32 部分隔離在 SplashLayered.cpp。
// 非 __WXMSW__ 平台為 no-op（splash 維持原本不透明顯示）。

class wxWindow;
class wxBitmap;

namespace Slic3r { namespace GUI {

// 把含 alpha 的 argb 點陣圖，以 per-pixel alpha 貼到 win（layered window），背後桌面透出。
void update_splash_layered(wxWindow* win, const wxBitmap& argb);

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_SplashLayered_hpp_
