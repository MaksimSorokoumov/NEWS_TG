@echo off
cd %~dp0
call .venv\Scripts\activate.bat
python new_tg_parser.py
pause 