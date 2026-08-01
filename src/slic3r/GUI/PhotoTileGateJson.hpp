#ifndef slic3r_GUI_PhotoTileGateJson_hpp_
#define slic3r_GUI_PhotoTileGateJson_hpp_

// =====================================================================
// 照片磚閘門報告用的最小 JSON writer（2026-08-01・Codex 次要 #14 的答案）
//
// 為什麼不用 boost::property_tree：ptree 會把所有數值寫成字串，
// 報告一旦被機器讀（守夜／CI／處置表引用）就得到處 Number() 轉——
// 2026-07-31 閘門①首跑就被這個坑擋下一次（engine.html §num 註解有記）。
//
// 為什麼原本手拼 JSON 是錯的：失敗訊息會含換行與控制字元（HRESULT 訊息、
// 引擎例外的 stack、Windows 錯誤字串都會），原本的跳脫只處理 " 與 \，
// **報告會變成非法 JSON**——閘門一失敗就讀不到報告，正是最需要它的時候。
//
// 這支只做一件事：把值正確轉成 JSON 字面。用法一律 jval(...)／jstr(...)，
// 不要再自己拼引號。
// =====================================================================

#include <cmath>
#include <cstdio>
#include <string>

namespace Slic3r { namespace GUI {

// 依 RFC 8259：跳脫 " \ 與所有 < 0x20 的控制字元（其餘位元組原樣輸出，UTF-8 直通）
inline std::string pt_json_escape(const std::string& s)
{
    std::string o;
    o.reserve(s.size() + 8);
    for (unsigned char c : s) {
        switch (c) {
        case '"':  o += "\\\""; break;
        case '\\': o += "\\\\"; break;
        case '\b': o += "\\b";  break;
        case '\f': o += "\\f";  break;
        case '\n': o += "\\n";  break;
        case '\r': o += "\\r";  break;
        case '\t': o += "\\t";  break;
        default:
            if (c < 0x20) {
                char buf[8];
                std::snprintf(buf, sizeof(buf), "\\u%04x", (unsigned) c);
                o += buf;
            } else {
                o += (char) c;
            }
        }
    }
    return o;
}

inline std::string jstr(const std::string& s) { return "\"" + pt_json_escape(s) + "\""; }
inline std::string jstr(const char* s)        { return jstr(std::string(s ? s : "")); }

inline std::string jval(bool v)          { return v ? "true" : "false"; }
inline std::string jval(int v)           { return std::to_string(v); }
inline std::string jval(long v)          { return std::to_string(v); }
inline std::string jval(long long v)     { return std::to_string(v); }
inline std::string jval(size_t v)        { return std::to_string(v); }
inline std::string jval(unsigned int v)  { return std::to_string(v); }

// double：NaN／Inf 在 JSON 沒有字面，誠實寫 null（不要寫成會炸 parser 的 nan）
inline std::string jval(double v)
{
    if (!std::isfinite(v)) return "null";
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.6g", v);
    return buf;
}

// "key": value
template<class T> inline std::string jfield(const char* key, const T& v) { return jstr(key) + ": " + jval(v); }
inline std::string jfield(const char* key, const std::string& v)         { return jstr(key) + ": " + jstr(v); }
inline std::string jfield(const char* key, const char* v)                { return jstr(key) + ": " + jstr(v); }

}} // namespace Slic3r::GUI

#endif // slic3r_GUI_PhotoTileGateJson_hpp_
