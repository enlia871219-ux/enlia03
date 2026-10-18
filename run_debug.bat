@echo off
cd /d "%~dp0"
if exist "LawcroV1.exe" (
  "LawcroV1.exe"
) else (
  echo EXE not found. Run build.bat first.
  pause
)
