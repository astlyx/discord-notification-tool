@echo off
title Discord Notification Tool - Build

echo.
echo  ================================================
echo   Discord Notification Tool - EXE Builder
echo  ================================================
echo.

:: Python check
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found!
    echo  Download it from https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo  [OK] %PY_VER% found.
echo.

:: Install dependencies
echo  [1/3] Installing dependencies...
echo  ------------------------------------------------
python -m pip install --quiet --upgrade discord.py PyQt6 requests pyinstaller
if errorlevel 1 (
    echo.
    echo  [ERROR] Package installation failed!
    pause
    exit /b 1
)
echo  [OK] All packages ready.
echo.

:: Check main.py
if not exist "main.py" (
    echo  [ERROR] main.py not found in this folder!
    echo  build.bat and main.py must be in the same directory.
    pause
    exit /b 1
)

:: Clean old build files
echo  [2/3] Cleaning old build files...
if exist "build" rmdir /s /q "build"
if exist "dist"  rmdir /s /q "dist"
del /q *.spec 2>nul
echo  [OK] Cleaned.
echo.

:: Build with PyInstaller
echo  [3/3] Building EXE (this may take a while)...
echo  ------------------------------------------------
python -m PyInstaller --onefile --noconsole --name "DiscordNotificationTool" --collect-all PyQt6 --hidden-import discord --hidden-import discord.ext.commands --hidden-import requests main.py

if errorlevel 1 (
    echo.
    echo  [ERROR] Build failed! Check the error above.
    pause
    exit /b 1
)

:: Copy config.json
if exist "config.json" (
    copy /y "config.json" "dist\config.json" >nul
    echo  [OK] config.json copied to dist folder.
)

echo.
echo  ================================================
echo   BUILD COMPLETED SUCCESSFULLY!
echo   EXE: dist\DiscordNotificationTool.exe
echo  ================================================
echo.
echo  NOTE: config.json must always be in the same folder as the EXE.
echo.

set /p OPEN_FOLDER=Open dist folder? (Y/N): 
if /i "%OPEN_FOLDER%"=="Y" explorer dist

pause
