# =====================================================================
# phototile_warmup_probe.ps1 — C-2 第 3 項「閒置預熱」產品路徑探針（照片磚線 PT-16）
#
# 為什麼存在：預熱的價值＝「使用者還沒動作，引擎就已經就緒」。這件事**閘門看不到**
# （閘門模式一律不預熱＝黃金基準零擾動），只能在**正式模式**下觀察產品自己的行為。
# 本探針全自動：起 app → 完全不碰它 → 看 log 與行程 → 收工，人不必當碼表。
#
# 三個要回答的問題（對應 handoff 的 P1/P2/P3）：
#   1. 選中照片磚機時，引擎是不是在使用者動作前就 Ready 了？（engineReadyMs 有值＝是）
#   2. kill switch 關掉後，是不是真的完全不預熱？（-Mode cold 應該 engineProcs=0）
#   3. 非照片磚機是不是不付這份記憶體？（log 應見「跳過」，engineProcs=0）
#
# ⚠ 紀律：
#   ‧ 一律帶 -DataDir 隔離資料夾，**絕不碰 %APPDATA%\PingSlicer**（Eric 的正式參數在那）。
#   ‧ 偵測到別的 ping-slicer.exe 在跑就拒跑（可能是 Eric 的正式版或別線的實例）。
#   ‧ 收工用 WM_CLOSE（等同使用者關窗），順便再驗一次 B-2：關窗後引擎行程要全退。
#
# 用法：
#   powershell -File phototile_warmup_probe.ps1 -Mode warm -OutJson warm.json
#   powershell -File phototile_warmup_probe.ps1 -Mode cold -OutJson cold.json
# =====================================================================
param(
  [ValidateSet('warm','cold')] [string]$Mode = 'warm',   # warm=預熱開（產品預設）／cold=kill switch 對照組
  [int]$WarmupDelayMs = 5000,                            # 覆寫預設 15 秒，免得每輪空等
  [int]$ObserveSec    = 60,                              # 起動後觀察多久（全程不做任何使用者動作）
  [string]$Exe        = 'D:\ping-slicer-c1\build\src\Release\ping-slicer.exe',
  [string]$DataDir    = 'D:\ping-slicer-c1\_smokedata',
  [string]$OutJson    = ''
)

$ErrorActionPreference = 'Stop'

Add-Type @"
using System; using System.Text; using System.Collections.Generic; using System.Runtime.InteropServices;
public class PingWin {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern bool PostMessageW(IntPtr h, uint m, IntPtr w, IntPtr l);
  // 主框＝該 PID 底下「可見且有標題」的 top-level 視窗。
  // ⚠ 不可用 Process.MainWindowHandle／CloseMainWindow()：照片磚隱形宿主也是 top-level wxFrame
  //   （1×1、永不 Show），實測 WM_CLOSE 會打到它 ⇒ app 完全沒收到關窗、20 秒後被強殺，
  //   於是「關窗後引擎全退」這條 B-2 迴歸等於沒驗到（2026-08-04 PT-16 踩到）。
  public static List<IntPtr> VisibleTopLevel(uint pid) {
    var r = new List<IntPtr>();
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p);
      if (p == pid && IsWindowVisible(h)) { var sb = new StringBuilder(512); GetWindowTextW(h, sb, 512);
        if (sb.Length > 0) r.Add(h); } return true; }, IntPtr.Zero);
    return r;
  }
  public static void Close(IntPtr h) { PostMessageW(h, 0x0010, IntPtr.Zero, IntPtr.Zero); }  // WM_CLOSE（實測對本 app 無效，保留供診斷）
  public static string Title(IntPtr h) { var sb = new StringBuilder(512); GetWindowTextW(h, sb, 512); return sb.ToString(); }
  // 人的閒置時間（SOP §18 第一道閘門：問「人在不在」，不是問「機器忙不忙」）
  [StructLayout(LayoutKind.Sequential)] public struct LII { public uint cbSize; public uint dwTime; }
  [DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LII p);
  [DllImport("kernel32.dll")] public static extern uint GetTickCount();
  public static uint IdleMs() { LII l = new LII(); l.cbSize = (uint)Marshal.SizeOf(l); GetLastInputInfo(ref l); return GetTickCount() - l.dwTime; }
}
"@ -ErrorAction SilentlyContinue

function Get-EngineProcs {
  # 照片磚引擎樹＝命令列帶 webview2_phototile 的 msedgewebview2（宿主自己的 user data 資料夾）
  Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'webview2_phototile' }
}

function Get-EngineMemMB {
  $ps = Get-EngineProcs
  if (-not $ps) { return 0 }
  $ids = $ps | Select-Object -ExpandProperty ProcessId
  $sum = 0
  foreach ($id in $ids) {
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($p) { $sum += $p.WorkingSet64 }
  }
  return [math]::Round($sum / 1MB, 1)
}

function Get-EngineCpuSec {
  # 引擎樹累計 CPU 時間（秒）。閒置預熱不該讓機器變鈍——頁面端是零計時器紀律（C-0 §3.2），
  # 就緒後這個值應該幾乎不再增加。兩點取樣相減＝閒置期真實 CPU 佔用。
  $ps = Get-EngineProcs
  if (-not $ps) { return 0 }
  $sum = 0.0
  foreach ($id in ($ps | Select-Object -ExpandProperty ProcessId)) {
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($p) { $sum += $p.TotalProcessorTime.TotalSeconds }
  }
  return [math]::Round($sum, 2)
}

# ── 0. 守衛：別踩到別人的實例 ───────────────────────────────────────────────
$existing = Get-Process -Name 'ping-slicer' -ErrorAction SilentlyContinue
if ($existing) {
  Write-Error ("已有 {0} 個 ping-slicer.exe 在跑（PID: {1}）——可能是 Eric 的正式版或別線的實例，本探針拒跑。" -f `
    $existing.Count, (($existing | Select-Object -ExpandProperty Id) -join ','))
  exit 2
}
if (-not (Test-Path $Exe))     { Write-Error "找不到 exe：$Exe"; exit 2 }
if (-not (Test-Path $DataDir)) { Write-Error "找不到 datadir：$DataDir（探針只在隔離 datadir 上跑）"; exit 2 }

$logDir = Join-Path $DataDir 'log'
$before = @()
if (Test-Path $logDir) { $before = Get-ChildItem $logDir -Filter '*.log*' -File | Select-Object -ExpandProperty FullName }

# ── 1. 起 app（環境變數只給子行程）─────────────────────────────────────────
$env:PING_PHOTOTILE_WARMUP_DELAY_MS = "$WarmupDelayMs"
if ($Mode -eq 'cold') { $env:PING_PHOTOTILE_NO_WARMUP = '1' } else { Remove-Item Env:\PING_PHOTOTILE_NO_WARMUP -ErrorAction SilentlyContinue }
Remove-Item Env:\PING_PHOTOTILE_SMOKE -ErrorAction SilentlyContinue   # 正式模式：一定不能設

$t0 = Get-Date
$proc = Start-Process -FilePath $Exe -ArgumentList @('--datadir', $DataDir) -PassThru
Write-Host ("[{0}] 起 app PID={1}（mode={2}, warmupDelay={3}ms）" -f $t0.ToString('HH:mm:ss'), $proc.Id, $Mode, $WarmupDelayMs)

# ── 2. 觀察窗：全程不碰它，只看行程與 log ──────────────────────────────────
$engineFirstSeenMs = $null
$peakProcs = 0
$peakMemMB = 0
$cpuMark = $null; $cpuMarkAt = $null    # 引擎出現後 10 秒開始算閒置 CPU（避開建立期）
for ($i = 0; $i -lt $ObserveSec; $i++) {
  Start-Sleep -Seconds 1
  if ($proc.HasExited) { break }
  $ps = @(Get-EngineProcs)
  if ($ps.Count -gt 0) {
    if ($null -eq $engineFirstSeenMs) {
      $engineFirstSeenMs = [int]((Get-Date) - $t0).TotalMilliseconds
      Write-Host ("[+{0}ms] 引擎行程出現：{1} 顆" -f $engineFirstSeenMs, $ps.Count)
    }
    if ($ps.Count -gt $peakProcs) { $peakProcs = $ps.Count }
    $m = Get-EngineMemMB
    if ($m -gt $peakMemMB) { $peakMemMB = $m }
    if ($null -eq $cpuMark -and ((Get-Date) - $t0).TotalMilliseconds -gt ($engineFirstSeenMs + 10000)) {
      $cpuMark = Get-EngineCpuSec; $cpuMarkAt = Get-Date
    }
  }
}
# 閒置期 CPU 佔用（全機百分比）：就緒之後這段時間，引擎樹到底吃掉多少 CPU
$idleCpuPct = $null
if ($null -ne $cpuMark) {
  $wall = ((Get-Date) - $cpuMarkAt).TotalSeconds
  if ($wall -gt 3) {
    $delta = (Get-EngineCpuSec) - $cpuMark
    $idleCpuPct = [math]::Round(($delta / $wall) * 100.0, 2)
  }
}

$idleProcs = @(Get-EngineProcs).Count
$idleMemMB = Get-EngineMemMB

# ── 3. 讀 log（本輪新生的那份）──────────────────────────────────────────────
$logFile = $null
if (Test-Path $logDir) {
  $cand = Get-ChildItem $logDir -Filter '*.log*' -File | Sort-Object LastWriteTime -Descending
  foreach ($c in $cand) { if ($before -notcontains $c.FullName -or $c.LastWriteTime -gt $t0) { $logFile = $c.FullName; break } }
}
$lines = @()
if ($logFile) { $lines = Get-Content $logFile -Encoding UTF8 -ErrorAction SilentlyContinue }

function Find-Line([string]$pattern) {
  $hit = $lines | Where-Object { $_ -match $pattern } | Select-Object -First 1
  if ($hit) { return $hit.Trim() } else { return '' }
}

$lineScheduled = Find-Line '預熱：排程'
$lineFired     = Find-Line '預熱：點火'
$lineSkipped   = Find-Line '預熱：跳過'
$lineNoSched   = Find-Line '預熱：不排程'
$lineReady     = Find-Line 'PhotoTileEngineHost \[ready\]'
$lineExit      = Find-Line '~GUI_App: exit'

# ── 4. 收工：WM_CLOSE（等同使用者關窗）＋ 驗引擎行程全退（B-2 迴歸）─────────
$closedGracefully = $false
$closedTitle = ''
$closeMethod  = ''
if (-not $proc.HasExited) {
  $wins = [PingWin]::VisibleTopLevel([uint32]$proc.Id)
  $hwnd = if ($wins.Count -gt 0) { $wins[0] } else { [IntPtr]::Zero }
  if ($hwnd -ne [IntPtr]::Zero) { $closedTitle = [PingWin]::Title($hwnd) }
  <# 「人閒置」要扣掉**自己上一輪的合成輸入**（2026-08-04 PT-16 實測）：
     SOP §18 記著 SetCursorPos／SetForegroundWindow／PrintWindow 不更新 GetLastInputInfo，
     **但 keybd_event／SendInput 會**——本探針上一輪的 Alt+F4 就把哨兵歸零，下一輪誤判「人回來了」。
     解法＝注入時把「注入時刻＋當時的人閒置秒數」記檔；下一輪若量到的最後輸入就是自己那一下，
     人的真實閒置＝當時值＋已過時間（下限估計，寧可低估不可高估）。 #>
  $selfFile = Join-Path $env:TEMP 'ping_phototile_probe_selfinput.txt'
  $rawIdle  = [double]([PingWin]::IdleMs()) / 1000
  $lastInputAt = (Get-Date).AddSeconds(-$rawIdle)
  $idleSec = [math]::Round($rawIdle, 1)
  if (Test-Path $selfFile) {
    try {
      $parts = (Get-Content $selfFile -Raw).Trim() -split '\|'
      $selfAt = [datetime]::Parse($parts[0]); $selfIdle = [double]$parts[1]
      if ([math]::Abs(($lastInputAt - $selfAt).TotalSeconds) -lt 3) {
        $idleSec = [math]::Round($selfIdle + ((Get-Date) - $selfAt).TotalSeconds, 1)
        Write-Host ("（最後一次輸入是本工具上輪的 Alt+F4，扣除後人的閒置估 {0} 秒）" -f $idleSec)
      }
    } catch {}
  }
  <# 關窗方法的選擇（2026-08-04 PT-16 實測）：
     ‧ 外部 PostMessage(WM_CLOSE) 對這支 app **無效**——log 連 `received close_widow` 都不會出現
       （wx 那邊沒把它轉成 wxEVT_CLOSE_WINDOW）。用它等於沒關，B-2 迴歸會假失敗。
     ‧ Alt+F4 有效（實測 3 秒內收乾淨到 `~GUI_App: exit`），但它是**合成輸入**
       ⇒ 依 SOP §18／認領簿「現場人＝CONTROL」，人若在機台前一律不送，改成強殺並誠實標記。 #>
  if ($hwnd -ne [IntPtr]::Zero -and $idleSec -ge 150) {
    $closeMethod = 'alt-f4'
    Write-Host ("Alt+F4 關窗：'{0}'（人閒置 {1} 秒 ≥150 ⇒ 可用合成輸入）" -f $closedTitle, $idleSec)
    $drive = Join-Path $PSScriptRoot 'ui_drive.ps1'
    # 先記帳再注入：記「注入時刻｜當時人的閒置秒數」，供下一輪扣除自身影響
    Set-Content -Path $selfFile -Value ((Get-Date).ToString('o') + '|' + $idleSec) -Encoding ASCII
    & powershell -NoProfile -ExecutionPolicy Bypass -File $drive -Hwnd ('0x' + $hwnd.ToInt64().ToString('X')) -Focus -Keys '%{F4}' | Out-Null
  } else {
    $closeMethod = 'skipped'
    Write-Host ("⚠ 不送合成輸入（人閒置 {0} 秒 <150 或找不到主框）⇒ 本輪不驗關窗" -f $idleSec)
  }
  for ($i = 0; $i -lt 25; $i++) { Start-Sleep -Seconds 1; if ($proc.HasExited) { $closedGracefully = $true; break } }
  if (-not $proc.HasExited) { Write-Host "⚠ 未自行退出，強殺（本輪 B-2 迴歸不算數）"; Stop-Process -Id $proc.Id -Force; Start-Sleep -Seconds 2 }
}
Start-Sleep -Seconds 3
$leftoverProcs = @(Get-EngineProcs).Count

Remove-Item Env:\PING_PHOTOTILE_WARMUP_DELAY_MS -ErrorAction SilentlyContinue
Remove-Item Env:\PING_PHOTOTILE_NO_WARMUP       -ErrorAction SilentlyContinue

# ── 5. 判定與報告 ───────────────────────────────────────────────────────────
# warm＝引擎必須在「使用者零動作」的情況下自己就緒；cold＝必須完全沒有引擎行程。
$ok = $false
if ($Mode -eq 'warm') { $ok = ($lineFired -ne '') -and ($lineReady -ne '') -and ($idleProcs -gt 0) }
else                  { $ok = ($lineNoSched -ne '') -and ($engineFirstSeenMs -eq $null) -and ($idleProcs -eq 0) }

$report = [ordered]@{
  _note              = 'C-2 第 3 項閒置預熱・產品路徑探針（正式模式、使用者零動作）'
  mode               = $Mode
  ok                 = $ok
  warmupDelayMs      = $WarmupDelayMs
  observeSec         = $ObserveSec
  engineFirstSeenMs  = $engineFirstSeenMs      # 從起 app 到引擎行程出現（使用者完全沒動作）
  enginePeakProcs    = $peakProcs
  engineIdleProcs    = $idleProcs
  engineIdleMemMB    = $idleMemMB              # 閒置預熱的記憶體代價（誠實回報給 Eric；他 0802 裁示時估「約 200MB」）
  enginePeakMemMB    = $peakMemMB
  engineIdleCpuPct   = $idleCpuPct             # 就緒後的閒置 CPU 佔用（零計時器紀律成立的話應接近 0）
  closedGracefully   = $closedGracefully       # false＝沒自行退出（被強殺）⇒ 本輪 B-2 迴歸不算數
  closeMethod        = $closeMethod            # alt-f4／skipped（人在機台前就不送合成輸入）
  closedWindowTitle  = $closedTitle            # 關的是哪個視窗（確認打對主框）
  leftoverProcsAfterClose = $leftoverProcs     # B-2 迴歸：關窗後必須 0
  logFile            = $logFile
  logScheduled       = $lineScheduled
  logFired           = $lineFired
  logSkipped         = $lineSkipped
  logNotScheduled    = $lineNoSched
  logEngineReady     = $lineReady
  logAppExit         = $lineExit
}

$json = $report | ConvertTo-Json -Depth 4
Write-Host $json
if ($OutJson) { Set-Content -Path $OutJson -Value $json -Encoding UTF8; Write-Host "報告已寫入 $OutJson" }
if ($ok) { exit 0 } else { exit 1 }





