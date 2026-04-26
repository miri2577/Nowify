@echo off
setlocal
set PYTHONIOENCODING=utf-8
set MUSEUM_CATEGORIES=photograph
set MUSEUM_COUNT=50
set MUSEUM_OUT=C:\Users\mirkorichter\museum_photographs

"C:\Users\mirkorichter\AppData\Local\Programs\Python\Python312\python.exe" -u "%~dp0scrape_museums.py"
echo.
echo ---------------------------------------
echo done. images in %MUSEUM_OUT%
pause
