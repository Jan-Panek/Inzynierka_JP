@echo off
cd /d "%~dp0"
cd Skrypty
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
pause