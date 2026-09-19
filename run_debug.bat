@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ShadeLawcro V1.0 Runtime Debug

set "LOG=%~dp0runtime_error.txt"

echo ======================================== > "%LOG%"
echo ShadeLawcro V1.0 Runtime Debug >> "%LOG%"
echo Started: %date% %time% >> "%LOG%"
echo Folder: %CD% >> "%LOG%"
echo EXE: ShadeLawcroV1.exe >> "%LOG%"
echo ======================================== >> "%LOG%"
echo. >> "%LOG%"

echo ========================================
echo ShadeLawcro V1.0 Runtime Debug
echo ========================================
echo.
echo EXE: %CD%\ShadeLawcroV1.exe
echo Log: %LOG%
echo.

if not exist "ShadeLawcroV1.exe" (
  echo ERROR: ShadeLawcroV1.exe not found.
  echo ERROR: ShadeLawcroV1.exe not found. >> "%LOG%"
  echo Run build.bat first.
  echo.
  pause
  exit /b 1
)

echo Starting executable...
echo Starting executable... >> "%LOG%"
echo. >> "%LOG%"

echo --- STDOUT/STDERR --- >> "%LOG%"
cmd /c ""%CD%\ShadeLawcroV1.exe" >> "%LOG%" 2>&1"
set "APP_RC=%errorlevel%"

echo. >> "%LOG%"
echo --- PROCESS EXIT CODE: %APP_RC% --- >> "%LOG%"
echo Finished: %date% %time% >> "%LOG%"

echo.
echo ========================================
echo Program exited. Exit code: %APP_RC%
echo ========================================
echo.
echo Runtime log saved to:
echo %LOG%
echo.
echo Open runtime_error.txt and send me the contents.
echo.
pause
endlocal
