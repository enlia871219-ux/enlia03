@echo off
cd /d "%~dp0"
if exist "ShadeLawcroV1.exe" start "" "ShadeLawcroV1.exe"
if not exist "ShadeLawcroV1.exe" (
  echo EXE not found. Run build.bat first.
  pause
)
exit
