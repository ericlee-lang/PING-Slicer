@echo off
REM ---------------------------------------------------------------------
REM 報價包 quote.txt 契約合規性離線測試
REM
REM 為什麼有這支：quote.txt 是交給代印報價系統解析的**介面契約產物**，格式錯了
REM 對方就長不出報價列。這支不啟動 Slicer、不切片、不需要 GL，幾秒鐘就跑完，
REM 所以每次動到 PingQuoteFormat.cpp 都應該重跑一次。
REM
REM ⚠ 路徑用 D:\ping-slicer-c1（指向專案的純 ASCII symlink）——
REM   批次檔吃不了專案路徑裡的中文，直接用會變成找不到檔案。
REM ---------------------------------------------------------------------
setlocal
set REPO=D:\ping-slicer-c1
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
