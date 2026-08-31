#ifndef slic3r_GUI_WebView_hpp_
#define slic3r_GUI_WebView_hpp_

#include <wx/webview.h>

class WebView
{
public:
    static wxWebView *CreateWebView(wxWindow *parent, wxString const &url);
#if wxUSE_WEBVIEW_EDGE
    static bool CheckWebViewRuntime();
    static bool DownloadAndInstallWebViewRuntime();
#endif
    static void LoadUrl(wxWebView * webView, wxString const &url);

    static bool RunScript(wxWebView * webView, wxString const & msg);

    static void RecreateAll();

    /* 【2026-08-23】resources 目錄的虛擬主機名（單一真實來源；WebViewDialog 組 URL 時共用）。
       `.invalid` 是 RFC 2606 保留字尾，保證永遠不會解析到真的網路主機。 */
    static wxString virtual_host() { return "ping-resources.invalid"; }
};

#endif // !slic3r_GUI_WebView_hpp_
