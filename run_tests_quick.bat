@echo off
setlocal

rem Ensure Python 3.14 path if installed in default user directory
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python314;%LOCALAPPDATA%\Programs\Python\Python314\Scripts;%PATH%"
)

set "PYTHONPATH=.;pylibs"

echo ============================================================
echo Running Quick Backend ^& Static Tests...
echo ============================================================
python -m pytest tests/ --ignore=tests/e2e -v --timeout=180
if errorlevel 1 (
    echo [ERROR] Quick tests failed!
    exit /b 1
)

echo.
echo ============================================================
echo [SUCCESS] Quick tests passed!
echo ============================================================
exit /b 0
