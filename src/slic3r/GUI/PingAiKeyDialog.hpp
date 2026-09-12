#ifndef slic3r_GUI_PingAiKeyDialog_hpp_
#define slic3r_GUI_PingAiKeyDialog_hpp_

class wxWindow;

/* PING 照片磚 AI 金鑰設定框（P3「子」，2026-08-16）
 *
 * Eric 2026-08-16 三裁：
 *   裁一＝**C 案：由宿主開原生視窗**。不在照片磚工作室的網頁裡填——明文一個字都不進 WebView2。
 *         （安全比較與證據見 PingAiKeyStore.hpp 檔頭紀律 1。）
 *   裁二＝**乙：存與測分開**。存檔不自動打 API；旁邊給「測試連線」讓他當場按。
 *         理由：自動打會把「沒網路」誤報成「存檔失敗」，而金鑰其實是對的。
 *   裁三＝**做「子」，先不對客戶露出**。⇒ 入口掛在 helpMenu 且以 `developer_mode` 把關
 *         （沿用照片磚 smoke 那條的既有機制，見 MainFrame.cpp）。
 *
 * 原型（Eric 已實走並裁定）＝ 20260604 ORCA客製/原型_金鑰儲存介面_20260816.html
 */

namespace Slic3r {
namespace GUI {

// 開金鑰設定框（modal）。沒有金鑰＝填入畫面；已有金鑰＝遮罩＋測試／換一把／移除。
void show_ping_ai_key_dialog(wxWindow* parent);

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_PingAiKeyDialog_hpp_
