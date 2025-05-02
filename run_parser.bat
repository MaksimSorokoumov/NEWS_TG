@echo off
cd %~dp0

REM Проверяем существование виртуального окружения
if not exist ".venv\Scripts\activate.bat" (
    echo Виртуальное окружение не найдено. Создайте его командой:
    echo python -m venv .venv
    pause
    exit /b
)

REM Активируем окружение и запускаем основной скрипт
call .venv\Scripts\activate.bat
python main.py run

pause 