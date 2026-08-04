# =====================================================================
# window_probe.ps1 — 實查視窗標題＋離焦截圖（照片磚線 PT，C-2 第 7 項驗收工具）
#
# 為什麼存在：SOP §17——「掛了牌不等於掛得上——只有實查視窗才算數」。
# UI 的 ground truth＝實際視窗標題/像素，不是 code diff。
#   ‧ 標題：EnumWindows＋GetWindowTextW。⚠ P/Invoke 必須 CharSet=Unicode，
#     預設 ANSI 會把 UTF-16 標題讀成「每個標題只剩一個字元」的亂碼（0803 踩過）。
#   ‧ 截圖：PrintWindow＋PW_RENDERFULLCONTENT(0x2)——WebView2/GPU 合成內容
#     也抓得到，且**不奪焦點、不動滑鼠**＝與現場使用者零衝突（CONTROL 紅線）。
#
# 用法：
#   powershell -File window_probe.ps1                          # 列出所有 ping-slicer 視窗標題
#   powershell -File window_probe.ps1 -TargetPid 12345         # 只看該 PID
#   powershell -File window_probe.ps1 -TargetPid 12345 -Capture out.png   # 併抓第一個可見視窗
# =====================================================================
param(
  [int]$TargetPid = 0,
  [string]$NameLike = 'ping-slicer',
  [string]$Capture = ''
)

Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class PingWinProbe {
  public delegate bool EnumProc(IntPtr h, IntPtr lp);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lp);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public static List<object[]> ListWindows(uint pidFilter) {
    var found = new List<object[]>();
    EnumWindows(delegate(IntPtr h, IntPtr lp) {
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (pidFilter != 0 && pid != pidFilter) return true;
      if (!IsWindowVisible(h)) return true;
      var sb = new StringBuilder(512);
      GetWindowText(h, sb, 512);
      if (sb.Length > 0) found.Add(new object[] { h.ToInt64(), (long)pid, sb.ToString() });
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@

$pids = @()
if ($TargetPid -ne 0) { $pids = @([uint32]$TargetPid) }
else { $pids = @(Get-Process | Where-Object { $_.ProcessName -like "*$NameLike*" } | ForEach-Object { [uint32]$_.Id }) }
if (-not $pids.Count) { Write-Output "NO_PROCESS ($NameLike)"; exit 0 }

$firstHwnd = [IntPtr]::Zero
foreach ($p in $pids) {
  foreach ($w in [PingWinProbe]::ListWindows($p)) {
    Write-Output ("PID {0}`tHWND 0x{1:X}`t{2}" -f $w[1], $w[0], $w[2])
    if ($firstHwnd -eq [IntPtr]::Zero) { $firstHwnd = [IntPtr]$w[0] }
  }
}

if ($Capture -and $firstHwnd -ne [IntPtr]::Zero) {
  Add-Type -AssemblyName System.Drawing
  $r = New-Object PingWinProbe+RECT
  [void][PingWinProbe]::GetWindowRect($firstHwnd, [ref]$r)
  $w = [Math]::Max(1, $r.R - $r.L); $h = [Math]::Max(1, $r.B - $r.T)
  $bmp = New-Object System.Drawing.Bitmap($w, $h)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc()
  $ok = [PingWinProbe]::PrintWindow($firstHwnd, $hdc, 0x2)   # PW_RENDERFULLCONTENT
  $g.ReleaseHdc($hdc); $g.Dispose()
  $bmp.Save($Capture, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
  Write-Output ("CAPTURE {0} -> {1} ({2}x{3})" -f ($(if($ok){'ok'}else{'partial'}), $Capture, $w, $h))
}
