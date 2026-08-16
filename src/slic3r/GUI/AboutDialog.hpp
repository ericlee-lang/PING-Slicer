#ifndef slic3r_GUI_AboutDialog_hpp_
#define slic3r_GUI_AboutDialog_hpp_

#include <wx/wx.h>
#include <wx/intl.h>
#include <wx/html/htmlwin.h>

#include "GUI_Utils.hpp"
#include "wxExtensions.hpp"

namespace Slic3r { 
namespace GUI {

// PING 2026-08-16: AboutDialogLogo removed - it was declared and defined but never
// instantiated anywhere in the tree (upstream dead code; predates PING's About
// branding in 7b52c6e448, traceable back to the BambuStudio import). The real About
// dialog builds its logo from PING_about.png in AboutDialog.cpp. Keeping it around
// cost us a misdiagnosis: a grep for resources/images/OrcaSlicer_192px.png hit this
// class and made it look like the About dialog depended on that asset, which nearly
// blocked unifying the icon set.

class CopyrightsDialog : public DPIDialog
{
public:
    CopyrightsDialog();
    ~CopyrightsDialog() {}

    struct Entry {
        Entry(const std::string &lib_name, const std::string &copyright, const std::string &link) : 
            lib_name(lib_name), copyright(copyright), link(link) {}

        std::string     lib_name;
        std::string     copyright;
        std::string   	link;
    };

protected:
    void on_dpi_changed(const wxRect &suggested_rect) override;
    
private:
    wxHtmlWindow*   m_html;
    std::vector<Entry> m_entries;

    void onLinkClicked(wxHtmlLinkEvent &event);
    void onCloseDialog(wxEvent &);

    void fill_entries();
    wxString get_html_text();
};



class AboutDialog : public DPIDialog
{
    ScalableBitmap  m_logo_bitmap;
    wxHtmlWindow*   m_html;
    wxStaticBitmap* m_logo;
    int             m_copy_rights_btn_id { wxID_ANY };
    int             m_copy_version_btn_id { wxID_ANY };
public:
    AboutDialog();

protected:
    void on_dpi_changed(const wxRect &suggested_rect) override;
    
private:
    void onLinkClicked(wxHtmlLinkEvent &event);
    void onCloseDialog(wxEvent &);
    void onCopyrightBtn(wxEvent &);
    void onCopyToClipboard(wxEvent&);
};

} // namespace GUI
} // namespace Slic3r

#endif
