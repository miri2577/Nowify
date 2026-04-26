@echo off
setlocal
set PYTHONIOENCODING=utf-8
set MUSEUM_CATEGORIES=painting
set MUSEUM_COUNT=250
set MUSEUM_OUT=C:\Users\mirkorichter\museum_paintings

"C:\Users\mirkorichter\AppData\Local\Programs\Python\Python312\python.exe" -u "%~dp0scrape_museums.py"
echo.
echo ---------------------------------------
echo done. images in %MUSEUM_OUT%
pause
