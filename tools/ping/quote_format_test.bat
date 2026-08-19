@echo off
chcp 65001 >nul
REM ---------------------------------------------------------------------
REM 報價包 quote.txt 契約合規性離線測試
REM
REM 為什麼有這支：quote.txt 是交給代印報價系統解析的**介面契約產物**，格式錯了
REM 對方就長不出報價列。這支不啟動 Slicer、不切片、不需要 GL，幾秒鐘就跑完，
REM 所以每次動到 PingQuoteFormat.cpp 都應該重跑一次。
REM
REM ⚠ REPO 一律由 %~dp0 從腳本自己的位置推回去，**不要寫死路徑**。
REM   舊版寫死 D:\ping-slicer-c1（指向開發線的純 ASCII symlink），2026-08-19 把報價包
REM   移植到出貨線與照片磚線之後那就變成地雷：在出貨線的 repo 裡跑這支，測到的其實是
REM   開發線的碼——**綠燈但驗錯了東西**，而且不會有任何徵兆。
REM   （中文路徑不是問題：%~dp0 是執行期展開的，實測 cd 與 cl 都吃得下；
REM     真正吃不下中文的是「寫死在批次檔裡的字面路徑」。上面那行 chcp 同理。）
REM ---------------------------------------------------------------------
setlocal
set REPO=%~dp0..\..
set GUI=%REPO%\src\slic3r\GUI
set OUT=%TEMP%\ping_quote_format_test

call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if not exist "%OUT%" mkdir "%OUT%"
cd /d "%OUT%"

cl /nologo /std:c++17 /EHsc /utf-8 /I"%GUI%" "%REPO%\tools\ping\quote_format_test.cpp" "%GUI%\PingQuoteFormat.cpp" /Fe:quote_format_test.exe
if errorlevel 1 (
    echo [BUILD FAILED]
    exit /b 1
)

chcp 65001 >nul
"%OUT%\quote_format_test.exe"
exit /b %ERRORLEVEL%
