#ifndef slic3r_GUI_SplashLayered_hpp_
#define slic3r_GUI_SplashLayered_hpp_

// PING: 啟動畫面 per-pixel 去背（桌面透出）。
// Win32 UpdateLayeredWindow 需要 <windows.h>，其巨集(DrawText/GetObject…)會破壞 GUI_App.cpp
// 內大量 wx 呼叫，故把 Win32 部分隔離在 SplashLayered.cpp。
// 非 __WXMSW__ 平台為 no-op（splash 維持原本不透明顯示）。
// v2(2026-06-10)：介面改收 wxImage——wxBitmap 經 MSW MemoryDC 後 ConvertToImage 會丟 alpha
// （透明處變不透明黑），改由呼叫端全程以 wxImage 合成、直接傳入。

class wxWindow;
class wxImage;

namespace Slic3r { namespace GUI {

// 把含 alpha 的 RGBA wxImage，以 per-pixel alpha 貼到 win（layered window），背後桌面透出。
void update_splash_layered(wxWindow* win, const wxImage& rgba);

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_SplashLayered_hpp_
