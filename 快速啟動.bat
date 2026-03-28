@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM 這是您的自動投票機器人啟動器
REM 使用此檔案啟動，可以隨時修改 python 程式碼並立即生效，無需重新打包

echo 正在啟動集保自動投票助手...
echo 請勿關閉此視窗...

REM 請將下行改為您的 Python 絕對路徑 (例如 C:\Python311\python.exe)
python vote_gui.py

if %errorlevel% neq 0 (
    echo.
    echo [錯誤] 程式異常退出，錯誤代碼: %errorlevel%
    echo 請確認已安裝以下套件:
    echo   pip install pillow pyautogui pynput selenium pyperclip
)
pause