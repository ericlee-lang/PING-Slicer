@echo off
rem Test-build data root seeding harness (card c-0924-DR-01). See README.md.
rem Needs: VS2022 BuildTools, node, and the prebuilt boost in the local c1 deps tree.
set BOOST_ROOT=D:\ping-slicer-c1\deps\build\OrcaSlicer_dep\usr\local
set OUT=%TEMP%\ping_dataroot_harness
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
node "%~dp0extract.cjs" || exit /b 1
rem boost libs in deps are named vc144; local cl auto-links vc143 - disable auto-link and list them
cl /nologo /utf-8 /EHsc /std:c++17 /MD /O1 /DWIN32_LEAN_AND_MEAN /DNOMINMAX /DBOOST_ALL_NO_LIB ^
  /I "%OUT%" /I "%BOOST_ROOT%\include\boost-1_84" ^
  "%~dp0harness.cpp" /Fo:"%OUT%\\" /Fe:"%OUT%\harness.exe" ^
  /link /LIBPATH:"%BOOST_ROOT%\lib" ^
  libboost_filesystem-vc144-mt-x64-1_84.lib libboost_nowide-vc144-mt-x64-1_84.lib libboost_atomic-vc144-mt-x64-1_84.lib || exit /b 1
"%OUT%\harness.exe" "%OUT%\run"
echo EXIT=%ERRORLEVEL%
