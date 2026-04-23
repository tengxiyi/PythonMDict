@echo off
chcp 65001 >nul 2>&1
title GeekDictionary Build Tool (Release v3.0)
echo ==========================================
echo      GeekDictionary Nuitka Build Tool
echo           [ Release v3.0 Mode ]
echo ==========================================

REM 1. 尝试激活虚拟环境
if exist "venv_build\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call venv_build\Scripts\activate.bat
) else (
    echo [WARN] No virtual environment found, using system Python...
)

REM 2. 检查 Nuitka
python -c "import nuitka" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Nuitka is not installed! Run: pip install nuitka
    pause
    exit /b
)

echo.
echo [INFO] Starting Release Build for main_new.py ...
echo [INFO] Console window will be hidden.
echo.

REM 3. 清理旧的构建输出
if exist "dist_nuitka\main.dist" (
    echo [INFO] Cleaning old build output...
    rmdir /s /q "dist_nuitka\main.dist"
)

REM 4. 执行 Nuitka 打包命令
REM 使用 main_new.py 作为入口（重构后的模块化版本）
python -m nuitka ^
    --standalone ^
    --mingw64 ^
    --show-progress ^
    --show-memory ^
    --enable-plugin=pyside6 ^
    --windows-disable-console ^
    --windows-icon-from-ico=app_icon.ico ^
    --output-filename=GeekDictionary.exe ^
    --output-dir=dist_nuitka ^
    REM 数据文件：字体目录、主题配置文件
    --include-data-dir=fonts=fonts ^
    --include-data-file=theme_config.json=theme_config.json ^
    REM OpenCC 中文转换库数据
    --include-data-dir=venv_build\Lib\site-packages\opencc=opencc ^
    REM 主入口（重构后版本）
    --main=main_new.py

echo.
echo ==========================================
if %errorlevel% equ 0 (
    echo [SUCCESS] Build finished!
    echo.
    echo Your release package is at:
    echo   dist_nuitka\main.dist\
    echo.
    echo To distribute:
    echo   1. Navigate to dist_nuitka\main.dist\
    echo   2. ZIP the entire folder contents
    echo   3. Rename ZIP to GeekDictionary-v3.0.zip
) else (
    echo [FAILURE] Build failed with error code %errorlevel%.
)
echo ==========================================

pause
