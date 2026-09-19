@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ShadeLawcro V1.0 Build

echo ShadeLawcro V1.0 build
echo Folder: %CD%
echo.

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    echo Python was not found.
    pause
    exit /b 1
  )
)

%PY% --version
if errorlevel 1 (
  echo Python could not be started.
  pause
  exit /b 1
)

echo.
echo [1/3] Installing packages...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo Package installation failed. See setup_log.txt if present.
  pause
  exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ShadeLawcroV1.exe del /q ShadeLawcroV1.exe
if exist ShadeLawcroV1.spec del /q ShadeLawcroV1.spec

echo.
echo [2/3] Cleaning done.
echo.
echo [3/3] Building EXE...
echo This can take several minutes.
echo.
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name ShadeLawcroV1 --distpath "%CD%" --workpath "%CD%\build" --specpath "%CD%" --add-data "assets;assets" --icon "assets\pookuro.ico" --exclude-module PySide6.Qt3D --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQuick3D --exclude-module PySide6.QtWebEngine --exclude-module PySide6.QtAsyncio --exclude-module PySide6.QtAxContainer main.py
set "BUILD_RC=%errorlevel%"

echo.
if %BUILD_RC%==0 if exist ShadeLawcroV1.exe (
  echo BUILD COMPLETE
  echo EXE: %CD%\ShadeLawcroV1.exe
) else (
  echo BUILD FAILED: executable was not created.
)

echo.
pause
endlocal
