@echo off
setlocal EnableExtensions EnableDelayedExpansion

for /f "tokens=3" %%V in ('findstr /B /C:"version = " pyproject.toml') do set "VERSION=%%~V"
set "VERSION=%VERSION:"=%"
if not defined VERSION set "VERSION=0.0.0"

set "OS=windows"
set "ARCH=%PROCESSOR_ARCHITECTURE%"
if /I "%PROCESSOR_ARCHITECTURE%"=="AMD64" set "ARCH=x86_64"
if /I "%PROCESSOR_ARCHITECTURE%"=="X86" set "ARCH=x86"
if /I "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=arm64"

set "TARGET_SUFFIX=%VERSION%-%OS%-%ARCH%"
set "BIN_NAME_CLI=tomi3-grub-read-save-cli-%TARGET_SUFFIX%"
set "BIN_NAME_GUI=tomi3-grub-read-save-gui-%TARGET_SUFFIX%"
set "BIN_NAME_MONITOR=tomi3-grub-monitor-live-%TARGET_SUFFIX%"

call pyinstaller --onefile --console --name "%BIN_NAME_CLI%" extract_grub_count_from_save.py
call pyinstaller --onefile --windowed --name "%BIN_NAME_GUI%" extract_grub_count_from_save_gui.py
call pyinstaller --onefile --console --name "%BIN_NAME_MONITOR%" monitor_grub_count.py

endlocal
