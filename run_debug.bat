@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ShadeLawcro V1.0 Runtime Debug

echo ========================================
echo ShadeLawcro V1.0 Runtime Debug
echo Folder: %CD%
echo EXE: ShadeLawcroV1.exe
echo ========================================
echo.

if not exist "ShadeLawcroV1.exe" (
  echo ERROR: ShadeLawcroV1.exe not found.
  echo Run build.bat first.
  echo.
  pause
  exit /b 1
)

echo Starting executable...
echo If the program crashes, the error should appear below.
echo.
"ShadeLawcroV1.exe"
set "APP_RC=%errorlevel%"

echo.
echo ========================================
echo Program exited. Exit code: %APP_RC%
echo ========================================
echo.
pause
endlocal
