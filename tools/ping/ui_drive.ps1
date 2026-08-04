# =====================================================================
# ui_drive.ps1 — 視窗座標點擊／打字／按鍵（照片磚線 PT-13，embedded 產品鏈驗收工具）
#
# 為什麼存在：AI-first——Release 版 embedded 頁沒有 console、也不勞人手點；
# 驗產品路徑需要「真的用滑鼠鍵盤走 UI」。本工具＝window_probe.ps1 的行動半邊：
# probe 拍照定座標 → 本工具下手 → probe 再拍照驗結果（閉環）。
#   ‧ 座標系＝GetWindowRect 的視窗座標（含標題列），與 window_probe 截圖同基準。
#   ‧ 先宣告 Per-Monitor DPI aware，物理像素對物理像素——否則 DPI 縮放下會點歪。
#   ‧ SetForegroundWindow 被前景鎖擋時，先送一下 Alt 再重試（經典解法）。
#
# 用法（可組合，執行順序＝Focus → Click → Text → Keys）：
#   powershell -File ui_drive.ps1 -Hwnd 0x230A42 -Focus
#   powershell -File ui_drive.ps1 -Hwnd 0x230A42 -ClickX 640 -ClickY 480
#   powershell -File ui_drive.ps1 -Hwnd 0x230A42 -Text 'C:\path\to\file.png' -Keys '{ENTER}'
# =====================================================================
param(
  [string]$Hwnd = '',            # 0x 開頭十六進位或十進位；空＝不聚焦、座標當螢幕絕對座標
  [switch]$Focus,
  [int]$ClickX = -1,
  [int]$ClickY = -1,
  [switch]$Double,
  [switch]$RightClick,
  [string]$Text = '',
  [string]$Keys = '',            # System.Windows.Forms.SendKeys 語法（{ENTER} ^v …）
  [int]$DelayMs = 150
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class PingUiDrive {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, int dx, int dy, uint data, UIntPtr extra);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern uint SendInput(uint n, INPUT[] inputs, int size);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public KEYBDINPUT ki; public long pad; }
  [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort vk, scan; public uint flags, time; public IntPtr extra; }
  public const uint LEFTDOWN = 0x02, LEFTUP = 0x04, RIGHTDOWN = 0x08, RIGHTUP = 0x10;
  // KEYEVENTF_UNICODE 打字：不吃鍵盤配置、可打中文路徑
  public static void TypeUnicode(string s) {
    foreach (char c in s) {
      var down = new INPUT { type = 1, ki = new KEYBDINPUT { vk = 0, scan = c, flags = 4, time = 0, extra = IntPtr.Zero } };
      var up   = new INPUT { type = 1, ki = new KEYBDINPUT { vk = 0, scan = c, flags = 4|2, time = 0, extra = IntPtr.Zero } };
      SendInput(1, new INPUT[]{ down }, Marshal.SizeOf(typeof(INPUT)));
      SendInput(1, new INPUT[]{ up },   Marshal.SizeOf(typeof(INPUT)));
      System.Threading.Thread.Sleep(3);
    }
  }
}
"@

# Per-Monitor-V2 DPI aware（-4）：讓 GetWindowRect/SetCursorPos 都吃物理像素
[void][PingUiDrive]::SetProcessDpiAwarenessContext([IntPtr](-4))

$h = [IntPtr]::Zero
if ($Hwnd) { $h = [IntPtr]([Convert]::ToInt64($Hwnd, $(if ($Hwnd -like '0x*') { 16 } else { 10 }))) }

if ($Focus -and $h -ne [IntPtr]::Zero) {
  [void][PingUiDrive]::SetForegroundWindow($h)
  Start-Sleep -Milliseconds 120
  if ([PingUiDrive]::GetForegroundWindow() -ne $h) {
    # 前景鎖：送一下 Alt 解鎖再試（keybd_event VK_MENU）
    [PingUiDrive]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
    [PingUiDrive]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
    [void][PingUiDrive]::SetForegroundWindow($h)
    Start-Sleep -Milliseconds 120
  }
  Write-Output ("FOCUS {0}" -f $(if ([PingUiDrive]::GetForegroundWindow() -eq $h) { 'ok' } else { 'FAILED' }))
}

if ($ClickX -ge 0 -and $ClickY -ge 0) {
  $sx = $ClickX; $sy = $ClickY
  if ($h -ne [IntPtr]::Zero) {
    $r = New-Object PingUiDrive+RECT
    [void][PingUiDrive]::GetWindowRect($h, [ref]$r)
    $sx = $r.L + $ClickX; $sy = $r.T + $ClickY
  }
  [void][PingUiDrive]::SetCursorPos($sx, $sy)
  Start-Sleep -Milliseconds 60
  $dn = $(if ($RightClick) { [PingUiDrive]::RIGHTDOWN } else { [PingUiDrive]::LEFTDOWN })
  $up = $(if ($RightClick) { [PingUiDrive]::RIGHTUP }   else { [PingUiDrive]::LEFTUP })
  [PingUiDrive]::mouse_event($dn, 0, 0, 0, [UIntPtr]::Zero)
  [PingUiDrive]::mouse_event($up, 0, 0, 0, [UIntPtr]::Zero)
  if ($Double) {
    Start-Sleep -Milliseconds 80
    [PingUiDrive]::mouse_event($dn, 0, 0, 0, [UIntPtr]::Zero)
    [PingUiDrive]::mouse_event($up, 0, 0, 0, [UIntPtr]::Zero)
  }
  Write-Output ("CLICK {0},{1} (screen {2},{3})" -f $ClickX, $ClickY, $sx, $sy)
}

if ($Text) {
  Start-Sleep -Milliseconds $DelayMs
  [PingUiDrive]::TypeUnicode($Text)
  Write-Output ("TYPE {0} chars" -f $Text.Length)
}

if ($Keys) {
  Start-Sleep -Milliseconds $DelayMs
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.SendKeys]::SendWait($Keys)
  Write-Output ("KEYS {0}" -f $Keys)
}
