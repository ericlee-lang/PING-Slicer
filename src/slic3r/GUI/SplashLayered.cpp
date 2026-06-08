#include "SplashLayered.hpp"

#ifdef __WXMSW__

#include <wx/msw/wrapwin.h>   // 隔離 windows.h（避免巨集污染其他翻譯單元）
#include <wx/window.h>
#include <wx/bitmap.h>
#include <wx/image.h>
#include <wx/gdicmn.h>
#include <cstring>

namespace Slic3r { namespace GUI {

void update_splash_layered(wxWindow* win, const wxBitmap& argb)
{
    if (win == nullptr || !argb.IsOk())
        return;

    wxImage img = argb.ConvertToImage();
    if (!img.IsOk())
        return;
    if (!img.HasAlpha())
        img.InitAlpha();

    const int width  = img.GetWidth();
    const int height = img.GetHeight();
    if (width <= 0 || height <= 0)
        return;

    const unsigned char* rgb   = img.GetData();    // RGBRGB...（無 alpha 交錯）
    const unsigned char* alpha = img.GetAlpha();   // 單獨 alpha plane

    // 建立 32-bit top-down DIB（biHeight 負值 = top-down）
    BITMAPINFO bi;
    std::memset(&bi, 0, sizeof(bi));
    bi.bmiHeader.biSize        = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth       = width;
    bi.bmiHeader.biHeight      = -height;
    bi.bmiHeader.biPlanes      = 1;
    bi.bmiHeader.biBitCount    = 32;
    bi.bmiHeader.biCompression = BI_RGB;

    void*   bits     = nullptr;
    HDC     screenDC = ::GetDC(NULL);
    HDC     memDC    = ::CreateCompatibleDC(screenDC);
    HBITMAP dib      = ::CreateDIBSection(screenDC, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    if (dib == NULL || bits == nullptr) {
        if (dib) ::DeleteObject(dib);
        ::DeleteDC(memDC);
        ::ReleaseDC(NULL, screenDC);
        return;
    }
    HBITMAP oldBmp = (HBITMAP)::SelectObject(memDC, dib);

    // 寫入 premultiplied BGRA（UpdateLayeredWindow 要求 premultiplied alpha）
    unsigned char* dst = static_cast<unsigned char*>(bits);
    const int n = width * height;
    for (int i = 0; i < n; ++i) {
        const unsigned char a = (alpha != nullptr) ? alpha[i] : 255;
        const unsigned char r = rgb[i * 3 + 0];
        const unsigned char g = rgb[i * 3 + 1];
        const unsigned char b = rgb[i * 3 + 2];
        dst[i * 4 + 0] = (unsigned char)(b * a / 255);  // Blue
        dst[i * 4 + 1] = (unsigned char)(g * a / 255);  // Green
        dst[i * 4 + 2] = (unsigned char)(r * a / 255);  // Red
        dst[i * 4 + 3] = a;                             // Alpha
    }

    HWND hwnd = (HWND)win->GetHandle();
    if (hwnd != NULL) {
        LONG_PTR ex = ::GetWindowLongPtr(hwnd, GWL_EXSTYLE);
        if ((ex & WS_EX_LAYERED) == 0)
            ::SetWindowLongPtr(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED);

        const wxPoint sp = win->GetScreenPosition();
        POINT         ptDst = { sp.x, sp.y };
        SIZE          sz    = { width, height };
        POINT         ptSrc = { 0, 0 };
        BLENDFUNCTION bf;
        bf.BlendOp             = AC_SRC_OVER;
        bf.BlendFlags          = 0;
        bf.SourceConstantAlpha = 255;
        bf.AlphaFormat         = AC_SRC_ALPHA;

        ::UpdateLayeredWindow(hwnd, screenDC, &ptDst, &sz, memDC, &ptSrc, 0, &bf, ULW_ALPHA);
    }

    ::SelectObject(memDC, oldBmp);
    ::DeleteObject(dib);
    ::DeleteDC(memDC);
    ::ReleaseDC(NULL, screenDC);
}

}} // namespace Slic3r::GUI

#else // !__WXMSW__

class wxWindow;
class wxBitmap;
namespace Slic3r { namespace GUI {
void update_splash_layered(wxWindow*, const wxBitmap&) {}
}} // namespace Slic3r::GUI

#endif // __WXMSW__
