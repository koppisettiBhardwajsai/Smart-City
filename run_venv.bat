@echo off
cd /d "%~dp0"
echo Starting CityApp Server using Virtual Environment...
".venv\Scripts\python.exe" manage.py runserver
pause
