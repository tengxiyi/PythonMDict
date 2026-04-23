@echo off
title GeekDictionary Build Tool (FINAL RELEASE)
echo ==========================================
echo      GeekDictionary Nuitka Build Tool
echo           [ FINAL RELEASE MODE ]
echo ==========================================

REM 1. 尝试激活虚拟环境
if exist "venv_build\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call venv_build\Scripts\activate.bat
)

REM 2. 检查 Nuitka
python -c "import nuitka" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Nuitka is not installed!
    pause
    exit /b
)

echo.
echo [INFO] Starting Final Compilation... 
echo [INFO] This will hide the console window.

REM 3. 执行 Nuitka 打包命令
REM [关键] --windows-disable-console 已启用
REM [关键] OpenCC 和 Fonts 数据目录已包含
python -m nuitka ^
    --standalone ^
    --mingw64 ^
    --show-progress ^
    --show-memory ^
    --enable-plugin=pyside6 ^
    --windows-disable-console ^
    --windows-icon-from-ico=app_icon.ico ^
    --include-data-dir=fonts=fonts ^
    --include-data-dir=venv_build\Lib\site-packages\opencc=opencc ^
    --output-dir=dist_nuitka ^
    --main=main.py

echo.
echo ==========================================
if %errorlevel% equ 0 (
    echo [SUCCESS] Build finished!
    echo.
    echo Your final software is ready at:
    echo dist_nuitka\main.dist
    echo.
    echo You can now zip this folder and share it!
) else (
    echo [FAILURE] Build failed.
)
echo ==========================================

pause