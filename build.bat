@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [CompanionDeck] 首次打包，正在创建虚拟环境...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo [CompanionDeck] 创建虚拟环境失败，请确认已安装 Python 3.10+，并加入 PATH
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    ".venv\Scripts\python.exe" -m pip install pyinstaller >nul
) else (
    if not exist ".venv\Lib\site-packages\PyInstaller" (
        ".venv\Scripts\python.exe" -m pip install pyinstaller >nul
    )
)

echo [CompanionDeck] 开始打包...
".venv\Scripts\python.exe" -m PyInstaller companion-deck.spec --noconfirm
if errorlevel 1 (
    echo [CompanionDeck] 打包失败
    pause
    exit /b 1
)

echo.
echo [CompanionDeck] 打包完成！
echo   产物：dist\CompanionDeck.exe
echo   双击即可运行（无需安装 Python），可拷贝到任意 Windows 电脑使用
echo.
pause
