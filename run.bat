@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [CompanionDeck] 首次运行，正在创建虚拟环境并安装依赖...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo [CompanionDeck] 创建虚拟环境失败，请确认已安装 Python 3.10+，并加入 PATH
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
echo [CompanionDeck] 正在启动，请用手机浏览器访问终端中显示的局域网地址...
".venv\Scripts\python.exe" -m deck
pause
