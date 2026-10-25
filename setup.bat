@echo off
cd /d "%~dp0"
python -m pip install -U -r requirements.txt
python test_key.py
pause
