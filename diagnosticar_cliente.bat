@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Instala Python 3.11 o posterior de 64 bits con el lanzador py.
    echo Descarga oficial: https://www.python.org/downloads/windows/
    pause
    exit /b 1
)
py -3 diagnosticar.py self-test
if errorlevel 1 (
    echo La prueba local fallo. Conserva el mensaje de error para revisarlo.
    pause
    exit /b 1
)
py -3 diagnosticar.py diagnose %*
set "diag_result=%ERRORLEVEL%"
echo.
echo Este diagnostico no ejecuta ataques. Comparte el archivo diagnostico-cliente-*.json.
pause
exit /b %diag_result%
